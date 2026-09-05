import { randomBytes, scrypt, timingSafeEqual } from "node:crypto";

/** scrypt from the standard library, so no password-hashing dependency.
 *  Cost parameters are stored with the hash, so raising them later still
 *  verifies every password already on disk. */
const N = 16384; // 128 * N * r = 16MB, inside Node's 32MB scrypt default
const R = 8;
const P = 1;
const KEYLEN = 64;

const derive = (pw: string, salt: Buffer, n: number, r: number, p: number) =>
  new Promise<Buffer>((resolve, reject) =>
    scrypt(pw, salt, KEYLEN, { N: n, r, p }, (err, key) => (err ? reject(err) : resolve(key))),
  );

export async function hashPassword(pw: string): Promise<string> {
  const salt = randomBytes(16);
  const key = await derive(pw, salt, N, R, P);
  return `scrypt$${N}$${R}$${P}$${salt.toString("hex")}$${key.toString("hex")}`;
}

const posInt = (v: string) => {
  const n = Number(v);
  return Number.isInteger(n) && n > 0 ? n : null;
};

export async function verifyPassword(pw: string, stored: string): Promise<boolean> {
  const [scheme, n, r, p, salt, hash] = stored.split("$");
  if (scheme !== "scrypt" || !salt || !hash) return false;
  // Fail closed on junk cost parameters: passing NaN to scrypt throws, and an
  // auth path must reject, never 500.
  const [cn, cr, cp] = [posInt(n), posInt(r), posInt(p)];
  if (cn === null || cr === null || cp === null) return false;
  const key = await derive(pw, Buffer.from(salt, "hex"), cn, cr, cp);
  const want = Buffer.from(hash, "hex");
  // length check first: timingSafeEqual throws on a mismatch
  return key.length === want.length && timingSafeEqual(key, want);
}

export const MIN_PASSWORD = 8;

/** Returns an error message, or null when the password is acceptable. */
export function checkPassword(pw: string, email?: string): string | null {
  if (pw.length < MIN_PASSWORD) return `Password must be at least ${MIN_PASSWORD} characters.`;
  if (pw.trim().length === 0) return "Password cannot be only spaces.";
  if (email && pw.toLowerCase() === email.toLowerCase()) return "Password cannot be your email.";
  if (/^change-?me$/i.test(pw)) return "Pick a real password.";
  return null;
}
