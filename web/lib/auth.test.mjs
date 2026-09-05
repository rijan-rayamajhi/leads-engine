/** Auth and permissions, against a running dev server:
 *    npm run dev   then   npm run test:auth
 *  Seeds two throwaway users, exercises every gate, removes them again. */
import assert from "node:assert/strict";
import { neon } from "@neondatabase/serverless";
import { hashPassword } from "./password.ts";

const BASE = process.env.BASE ?? "http://localhost:3000";
const sql = neon(process.env.DATABASE_URL);

const USER = "authtest-user@example.invalid";
const ADMIN = "authtest-admin@example.invalid";
const PW = "authtest-password";

const unescapeHtml = (s) =>
  s.replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");

/** Submit a form the way a browser without JS does: replay its hidden fields. */
async function submit(path, values, cookie) {
  const page = await (await fetch(BASE + path, { headers: cookie ? { cookie } : {} })).text();
  const form = [...page.matchAll(/<form.*?<\/form>/gs)]
    .map((m) => m[0])
    .find((f) => Object.keys(values).every((k) => f.includes(`name="${k}"`)));
  assert.ok(form, `no form on ${path} with fields ${Object.keys(values)}`);

  const body = new FormData();
  for (const [, name, value] of form.matchAll(/name="([^"]+)"(?:\s+value="([^"]*)")?/g))
    if (name.startsWith("$ACTION")) body.append(unescapeHtml(name), unescapeHtml(value ?? ""));
  for (const [k, v] of Object.entries(values)) body.append(k, v);

  return fetch(BASE + path, {
    method: "POST",
    body,
    redirect: "manual",
    headers: { Origin: BASE, ...(cookie ? { cookie } : {}) },
  });
}

const login = (email, password) => submit("/login", { email, password });
const visit = (path, cookie) =>
  fetch(BASE + path, { headers: cookie ? { cookie } : {}, redirect: "manual" });

async function seed() {
  const hash = await hashPassword(PW);
  for (const [email, role] of [[USER, "user"], [ADMIN, "admin"]])
    await sql`
      insert into users (email, password_hash, role, must_change, created_by)
      values (${email}, ${hash}, ${role}, false, 'auth.test')
      on conflict (email) do update
        set password_hash = excluded.password_hash, role = excluded.role,
            must_change = false, disabled_at = null`;
}
const cleanup = () => sql`delete from users where created_by = 'auth.test'`;

try {
  await seed();

  // bad credentials get no session
  for (const [email, password, why] of [
    [USER, PW + "x", "wrong password"],
    ["nobody@example.invalid", PW, "unknown email"],
    [USER, "", "empty password"],
  ]) {
    const r = await login(email, password);
    assert.equal(r.headers.get("set-cookie"), null, `${why} must not get a session`);
    assert.match(await r.text(), /Wrong email or password/);
  }

  // good credentials do
  const ok = await login(USER, PW);
  const userCookie = (ok.headers.get("set-cookie") ?? "").split(";")[0];
  assert.match(userCookie, /le_session=/, "valid login must set a session");
  assert.match(ok.headers.get("set-cookie"), /HttpOnly/i);

  // the gate: no cookie and a tampered cookie both bounce
  for (const cookie of [undefined, "le_session=garbage"]) {
    const r = await visit("/", cookie);
    assert.equal(r.status, 307);
    assert.match(r.headers.get("location"), /\/login$/);
  }

  // a real session gets in
  assert.equal((await visit("/", userCookie)).status, 200);

  // authorization: a normal user cannot reach settings, an admin can
  const gated = await visit("/settings", userCookie);
  assert.equal(gated.status, 307, "a normal user must not reach /settings");
  assert.match(gated.headers.get("location"), /\/$/);

  const adminLogin = await login(ADMIN, PW);
  const adminCookie = (adminLogin.headers.get("set-cookie") ?? "").split(";")[0];
  assert.equal((await visit("/settings", adminCookie)).status, 200, "an admin must reach /settings");

  // disabling takes effect on the next request, even with a live cookie
  await sql`update users set disabled_at = now() where email = ${USER}`;
  const afterDisable = await visit("/", userCookie);
  assert.equal(afterDisable.status, 307, "a disabled account's cookie must stop working");
  assert.match(afterDisable.headers.get("location"), /\/login$/);
  assert.match(await (await login(USER, PW)).text(), /disabled/, "and they cannot log back in");

  console.log("auth ok");
} finally {
  await cleanup();
}
