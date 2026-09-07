/** Session = an HS256 JWT in an httpOnly cookie carrying the email only.
 *  The role is loaded from the users table on every request, so demoting or
 *  disabling someone takes effect immediately instead of when a 30-day token
 *  expires. */
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SignJWT, jwtVerify } from "jose";
import { activeUser, findUserWithHash, userCount, type Role } from "./db";
import { hashPassword, verifyPassword } from "./password";
import { sql } from "./db";

const COOKIE = "le_session";
const MAX_AGE = 60 * 60 * 24 * 30; // 30 days

export type Session = { email: string; role: Role; mustChange: boolean };

function secret() {
  const s = process.env.AUTH_SECRET;
  if (!s) throw new Error("AUTH_SECRET not set");
  return new TextEncoder().encode(s);
}

// Bootstrap admin as JSON in env: USERS={"you@company.com":"pw"}. Only consulted
// while the users table is empty, then seeded in and ignored forever after.
function envUsers(): Record<string, string> {
  try {
    return JSON.parse(process.env.USERS || "{}");
  } catch {
    return {};
  }
}

async function setSessionCookie(email: string) {
  const token = await new SignJWT({ email })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${MAX_AGE}s`)
    .sign(secret());

  (await cookies()).set(COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE,
  });
}

/** P9: brute-force throttle. scrypt makes a guess slow, not impossible, and
 *  there was no attempt limit at all. Counted in Postgres rather than memory
 *  because serverless instances do not share state. */
const MAX_ATTEMPTS = 8;
const WINDOW_MINUTES = 15;

async function tooManyAttempts(email: string) {
  const [row] = (await sql`
    select count(*)::int as n from login_attempts
    where email = ${email} and at > now() - make_interval(mins => ${WINDOW_MINUTES})
  `) as { n: number }[];
  return row.n >= MAX_ATTEMPTS;
}

async function recordFailure(email: string) {
  await sql`insert into login_attempts (email) values (${email})`;
  // keep the table from growing forever; nothing older than the window matters
  await sql`delete from login_attempts where at < now() - make_interval(mins => ${WINDOW_MINUTES})`;
}

async function clearAttempts(email: string) {
  await sql`delete from login_attempts where email = ${email}`;
}

export type SignInResult =
  | { ok: true; mustChange: boolean }
  | { ok: false; reason: "bad" | "disabled" | "throttled" };

export async function signIn(email: string, password: string): Promise<SignInResult> {
  const e = email.trim().toLowerCase();
  if (!e || !password) return { ok: false, reason: "bad" };

  // Checked before the hash comparison, so a throttled attacker cannot even
  // spend our CPU, and before the user lookup so it covers unknown emails too.
  if (await tooManyAttempts(e)) return { ok: false, reason: "throttled" };

  const user = await findUserWithHash(e);
  if (user) {
    if (user.disabled_at) return { ok: false, reason: "disabled" };
    if (!(await verifyPassword(password, user.password_hash))) {
      await recordFailure(e);
      return { ok: false, reason: "bad" };
    }
    await clearAttempts(e);
    await setSessionCookie(e);
    return { ok: true, mustChange: user.must_change };
  }

  // First run: accept the env admin, seed them, and force a real password.
  if ((await userCount()) === 0) {
    const known = envUsers()[e];
    if (known && known === password) {
      await sql`
        insert into users (email, password_hash, role, must_change, created_by)
        values (${e}, ${await hashPassword(password)}, 'admin', true, 'bootstrap:env')`;
      await clearAttempts(e);
      await setSessionCookie(e);
      return { ok: true, mustChange: true };
    }
  }

  await recordFailure(e);
  return { ok: false, reason: "bad" };
}

export async function signOut() {
  (await cookies()).delete(COOKIE);
}

/** The cookie's claim only. Says nothing about whether the user still exists. */
async function tokenEmail(): Promise<string | null> {
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, secret());
    return typeof payload.email === "string" ? payload.email : null;
  } catch {
    return null; // expired or tampered
  }
}

export async function getSession(): Promise<Session | null> {
  const email = await tokenEmail();
  if (!email) return null;
  const u = await activeUser(email); // null when missing or disabled
  return u ? { email: u.email, role: u.role, mustChange: u.must_change } : null;
}

export async function requireSession(): Promise<Session> {
  const s = await getSession();
  if (!s) redirect("/login");
  return s;
}

export async function requireAdmin(): Promise<Session> {
  const s = await requireSession();
  if (s.role !== "admin") redirect("/");
  return s;
}
