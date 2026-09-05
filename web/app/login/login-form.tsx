"use client";
import { useActionState } from "react";
import { login } from "@/app/actions";
import { BTN, FIELD } from "@/components/ui";

export default function LoginForm() {
  const [error, action, pending] = useActionState(login, null);

  return (
    <form action={action} className="flex flex-col gap-3">
      <input
        name="email"
        type="email"
        required
        autoComplete="email"
        placeholder="you@company.com"
        className={`${FIELD} h-11 w-full`}
      />
      <input
        name="password"
        type="password"
        required
        autoComplete="current-password"
        placeholder="Password"
        className={`${FIELD} h-11 w-full`}
      />
      {error && (
        <p role="alert" className="rounded-pill bg-lost px-4 py-2 text-sm text-ink">
          {error}
        </p>
      )}
      <button
        disabled={pending}
        className={BTN}
      >
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
