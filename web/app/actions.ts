"use server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { requireAdmin, requireSession, signIn, signOut } from "@/lib/auth";
import { findUserWithHash, sql } from "@/lib/db";
import { checkPassword, hashPassword, verifyPassword } from "@/lib/password";
import { parseSettings } from "@/lib/settings";
import { MARKET_COOKIE } from "@/lib/market";

export async function login(_prev: string | null, formData: FormData) {
  const r = await signIn(
    String(formData.get("email") ?? ""),
    String(formData.get("password") ?? ""),
  );
  if (!r.ok)
    return r.reason === "disabled"
      ? "That account has been disabled. Ask an admin."
      : "Wrong email or password.";
  redirect(r.mustChange ? "/password" : "/");
}

/** Also the voluntary change form. The current password is required even in the
 *  forced flow, so a stolen cookie alone cannot take over an account. */
export async function changePassword(_prev: unknown, formData: FormData) {
  const { email } = await requireSession();
  const current = String(formData.get("current") ?? "");
  const next = String(formData.get("next") ?? "");
  const confirm = String(formData.get("confirm") ?? "");

  const user = await findUserWithHash(email);
  if (!user || !(await verifyPassword(current, user.password_hash)))
    return { ok: false, message: "Current password is wrong." };
  if (next !== confirm) return { ok: false, message: "The two new passwords do not match." };

  const bad = checkPassword(next, email);
  if (bad) return { ok: false, message: bad };
  if (await verifyPassword(next, user.password_hash))
    return { ok: false, message: "That is already your password." };

  await sql`
    update users set password_hash = ${await hashPassword(next)}, must_change = false
    where email = ${email}`;
  redirect("/");
}

export async function logout() {
  await signOut();
  redirect("/login");
}

const STATUSES = ["new", "contacted", "replied", "meeting", "proposal", "won", "lost"];

/** Status change is also the feedback loop's only input; every one logs an outcome. */
export async function setStatus(id: string, status: string) {
  const { email } = await requireSession();
  if (!STATUSES.includes(status)) throw new Error(`bad status: ${status}`);
  await sql`update leads set status = ${status} where id = ${id}`;
  await sql`insert into outcomes (lead_id, user_email, status)
            values (${id}, ${email}, ${status})`;
  revalidatePath("/");
  revalidatePath(`/leads/${id}`);
}

/** Claim if free, release if mine, refuse if it's someone else's. */
export async function toggleClaim(id: string) {
  const { email } = await requireSession();
  const [row] = (await sql`
    update leads
       set assigned_to = case when assigned_to = ${email} then null else ${email} end
     where id = ${id} and (assigned_to is null or assigned_to = ${email})
    returning assigned_to`) as { assigned_to: string | null }[];
  revalidatePath("/");
  revalidatePath(`/leads/${id}`);
  return { ok: !!row, assigned_to: row?.assigned_to ?? null };
}

const NOTE_MAX = 2000;

/** A note is an outcome row with no status. It logs history without touching the lead. */
export async function addNote(id: string, formData: FormData) {
  const { email } = await requireSession();
  const note = String(formData.get("note") ?? "").trim();
  if (!note) return;
  if (note.length > NOTE_MAX) throw new Error(`note over ${NOTE_MAX} characters`);
  await sql`insert into outcomes (lead_id, user_email, notes)
            values (${id}, ${email}, ${note})`;
  revalidatePath(`/leads/${id}`);
}

export async function saveSettings(_prev: unknown, formData: FormData) {
  const { email } = await requireAdmin();
  const parsed = parseSettings({
    city: String(formData.get("city") ?? ""),
    categories: String(formData.get("categories") ?? "").split("\n"),
    hot: String(formData.get("hot") ?? ""),
    warm: String(formData.get("warm") ?? ""),
    qualified: String(formData.get("qualified") ?? ""),
  });
  if (!parsed.ok) return { ok: false, message: parsed.error };

  const { city, categories, thresholds } = parsed.value;
  await sql`
    insert into settings (key, value, updated_by, updated_at) values
      ('city',       ${JSON.stringify(city)}::jsonb,       ${email}, now()),
      ('categories', ${JSON.stringify(categories)}::jsonb, ${email}, now()),
      ('thresholds', ${JSON.stringify(thresholds)}::jsonb, ${email}, now())
    on conflict (key) do update
      set value = excluded.value, updated_by = excluded.updated_by, updated_at = now()`;

  // bucket is a view of intent_score under the current thresholds, not a
  // historical fact, so existing leads move when the thresholds move.
  const moved = (await sql`
    with next as (
      select id, case
        when coalesce(intent_score, 0) >= ${thresholds.hot}       then 'HOT'
        when coalesce(intent_score, 0) >= ${thresholds.warm}      then 'WARM'
        when coalesce(intent_score, 0) >= ${thresholds.qualified} then 'QUALIFIED'
        else 'DROP' end as bucket
      from leads
    )
    update leads l set bucket = n.bucket
    from next n
    where n.id = l.id and l.bucket is distinct from n.bucket
    returning l.id`) as { id: string }[];

  revalidatePath("/settings");
  revalidatePath("/", "layout");
  return {
    ok: true,
    message:
      moved.length > 0
        ? `Saved. The next crawl uses these, and ${moved.length} existing lead${moved.length === 1 ? " was" : "s were"} re-bucketed.`
        : "Saved. The next crawl uses these.",
  };
}

export async function setMarket(formData: FormData) {
  await requireSession();
  const market = String(formData.get("market") ?? "all").slice(0, 120);
  (await cookies()).set(MARKET_COOKIE, market, {
    path: "/",
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 365,
  });
  revalidatePath("/", "layout");
}

const ROLES = ["admin", "user"];
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export async function addUser(_prev: unknown, formData: FormData) {
  const me = await requireAdmin();
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const role = String(formData.get("role") ?? "user");
  const password = String(formData.get("password") ?? "");

  if (!EMAIL_RE.test(email)) return { ok: false, message: "Enter a valid email address." };
  if (!ROLES.includes(role)) return { ok: false, message: "Unknown role." };
  const bad = checkPassword(password, email);
  if (bad) return { ok: false, message: bad };

  const rows = await sql`
    insert into users (email, password_hash, role, must_change, created_by)
    values (${email}, ${await hashPassword(password)}, ${role}, true, ${me.email})
    on conflict (email) do nothing
    returning email`;
  if (rows.length === 0) return { ok: false, message: "That email already has an account." };

  revalidatePath("/settings");
  return { ok: true, message: `${email} added. They must change this password on first login.` };
}

/** Admin sets a new password; the user is forced to replace it on next login. */
export async function setUserPassword(_prev: unknown, formData: FormData) {
  await requireAdmin();
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");

  const bad = checkPassword(password, email);
  if (bad) return { ok: false, message: `${email}: ${bad}` };

  const rows = await sql`
    update users set password_hash = ${await hashPassword(password)}, must_change = true
    where email = ${email} returning email`;
  if (rows.length === 0) return { ok: false, message: "No such user." };

  revalidatePath("/settings");
  return { ok: true, message: `Password set for ${email}. They must change it at next login.` };
}

/* Self-change is blocked on both actions below, and that is what keeps at least
   one active admin: demoting or disabling another admin means a second admin
   (you) already exists. */

export async function setUserRole(email: string, role: string) {
  const me = await requireAdmin();
  if (!ROLES.includes(role)) throw new Error(`unknown role: ${role}`);
  if (email === me.email) throw new Error("you cannot change your own role");
  await sql`update users set role = ${role} where email = ${email}`;
  revalidatePath("/settings");
}

export async function setUserDisabled(email: string, disabled: boolean) {
  const me = await requireAdmin();
  if (email === me.email) throw new Error("you cannot disable your own account");

  if (disabled) {
    await sql`update users set disabled_at = now() where email = ${email}`;
    // a disabled user cannot work their leads, so hand the claims back to the pool
    await sql`update leads set assigned_to = null where assigned_to = ${email}`;
  } else {
    await sql`update users set disabled_at = null where email = ${email}`;
  }
  revalidatePath("/settings");
  revalidatePath("/");
}
