"use client";
import Link from "next/link";
import { useActionState } from "react";
import { changePassword } from "@/app/actions";
import { BTN, FIELD } from "@/components/ui";
import { MIN_PASSWORD } from "@/lib/password";

export default function PasswordForm({ mustChange }: { mustChange: boolean }) {
  const [state, action, pending] = useActionState(changePassword, null);
  const field = `${FIELD} h-11 w-full`;

  return (
    <form action={action} className="flex flex-col gap-3">
      <input
        name="current"
        type="password"
        required
        autoComplete="current-password"
        placeholder="Current password"
        className={field}
      />
      <input
        name="next"
        type="password"
        required
        minLength={MIN_PASSWORD}
        autoComplete="new-password"
        placeholder={`New password (${MIN_PASSWORD}+ characters)`}
        className={field}
      />
      <input
        name="confirm"
        type="password"
        required
        autoComplete="new-password"
        placeholder="Repeat new password"
        className={field}
      />
      {state && !state.ok && (
        <p role="alert" className="rounded-pill bg-lost px-4 py-2 text-sm text-ink">
          {state.message}
        </p>
      )}
      <button disabled={pending} className={BTN}>
        {pending ? "Saving…" : "Set password"}
      </button>
      {!mustChange && (
        <Link href="/" className="text-center text-sm text-muted transition hover:text-ink">
          Back to pipeline
        </Link>
      )}
    </form>
  );
}
