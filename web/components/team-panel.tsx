"use client";
import { useActionState } from "react";
import { KeyRound, ShieldCheck, UserPlus, UserX } from "lucide-react";
import { addUser, setUserDisabled, setUserPassword, setUserRole } from "@/app/actions";
import { BTN, FIELD, Select } from "./ui";
import { MIN_PASSWORD } from "@/lib/password";
import type { AppUser } from "@/lib/db";

const field = `${FIELD} h-9 px-3.5`;

function Note({ state }: { state: { ok: boolean; message: string } | null }) {
  if (!state) return null;
  return (
    <p
      role="status"
      className={`rounded-pill px-4 py-2 text-sm text-ink ${state.ok ? "bg-won" : "bg-lost"}`}
    >
      {state.message}
    </p>
  );
}

export default function TeamPanel({ users, me }: { users: AppUser[]; me: string }) {
  const [added, addAction, adding] = useActionState(addUser, null);
  const [reset, resetAction, resetting] = useActionState(setUserPassword, null);
  const admins = users.filter((u) => u.role === "admin" && !u.disabled_at).length;

  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-4 rounded-card bg-surface p-5 shadow-card">
        <h2 className="flex items-center gap-2 font-semibold">
          <UserPlus size={16} strokeWidth={2} />
          Add someone
        </h2>
        <form action={addAction} className="flex flex-wrap items-end gap-2">
          <input
            name="email"
            type="email"
            required
            placeholder="name@company.com"
            aria-label="Email"
            className={`${field} w-56`}
          />
          <Select name="role" defaultValue="user" aria-label="Role" className="bg-sunken ring-1 ring-line">
            <option value="user">user</option>
            <option value="admin">admin</option>
          </Select>
          <input
            name="password"
            type="text"
            required
            minLength={MIN_PASSWORD}
            placeholder={`Initial password (${MIN_PASSWORD}+)`}
            aria-label="Initial password"
            className={`${field} w-52`}
          />
          <button disabled={adding} className={BTN}>
            {adding ? "Adding…" : "Add"}
          </button>
        </form>
        <Note state={added} />
        <p className="text-sm text-muted">
          Hand them this password yourself. They cannot reach the app until they replace it.
        </p>
      </section>

      <section className="flex flex-col gap-3 rounded-card bg-surface p-5 shadow-card">
        <h2 className="flex items-center gap-2 font-semibold">
          <ShieldCheck size={16} strokeWidth={2} />
          Team ({users.filter((u) => !u.disabled_at).length} active)
        </h2>
        <Note state={reset} />

        <ul className="flex flex-col">
          {users.map((u) => {
            const self = u.email === me;
            const off = !!u.disabled_at;
            return (
              <li
                key={u.email}
                className={`flex flex-wrap items-center gap-2 border-t border-line py-3 ${off ? "opacity-60" : ""}`}
              >
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-warm text-xs font-semibold text-ink">
                  {u.email[0]?.toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{u.email}</span>
                  <span className="text-xs text-muted">
                    {self && "you · "}
                    {off ? "disabled" : u.must_change ? "must change password" : "active"}
                  </span>
                </span>

                {self ? (
                  <span className="rounded-pill bg-sunken px-3 py-1.5 text-xs text-muted">
                    {u.role}
                    {admins === 1 && " · only admin"}
                  </span>
                ) : (
                  <>
                    <form action={resetAction} className="flex items-center gap-1.5">
                      <input type="hidden" name="email" value={u.email} />
                      <input
                        name="password"
                        type="text"
                        required
                        minLength={MIN_PASSWORD}
                        placeholder="new password"
                        aria-label={`New password for ${u.email}`}
                        className={`${field} w-40`}
                      />
                      <button
                        disabled={resetting}
                        title="Set password"
                        aria-label={`Set password for ${u.email}`}
                        className="grid size-9 place-items-center rounded-full bg-sunken text-muted transition hover:text-ink"
                      >
                        <KeyRound size={15} strokeWidth={1.75} />
                      </button>
                    </form>

                    <form action={setUserRole.bind(null, u.email, u.role === "admin" ? "user" : "admin")}>
                      <button
                        title={u.role === "admin" ? "Make a normal user" : "Make an admin"}
                        className="rounded-pill bg-sunken px-3 py-1.5 text-xs text-muted transition hover:text-ink"
                      >
                        {u.role}
                      </button>
                    </form>

                    <form action={setUserDisabled.bind(null, u.email, !off)}>
                      <button
                        title={off ? "Re-enable this account" : "Disable and release their leads"}
                        aria-label={off ? `Enable ${u.email}` : `Disable ${u.email}`}
                        className={`grid size-9 place-items-center rounded-full transition ${
                          off ? "bg-won text-ink" : "bg-sunken text-muted hover:bg-lost hover:text-ink"
                        }`}
                      >
                        <UserX size={15} strokeWidth={1.75} />
                      </button>
                    </form>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
