import Image from "next/image";
import { requireSession } from "@/lib/auth";
import PasswordForm from "./password-form";

export const dynamic = "force-dynamic";

export default async function PasswordPage() {
  const { email, mustChange } = await requireSession();

  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden p-6">
      <div className="pointer-events-none absolute -left-32 -top-32 size-96 rounded-full bg-won opacity-50 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-24 size-96 rounded-full bg-warm opacity-50 blur-3xl" />

      <div className="relative w-full max-w-sm rounded-card bg-surface p-8 shadow-pop">
        <div className="mb-6 flex items-center gap-3">
          <Image src="/logo.png" alt="" width={44} height={44} priority className="size-11 object-contain" />
          <div>
            <h1 className="text-lg font-semibold leading-tight">
              {mustChange ? "Set your password" : "Change password"}
            </h1>
            <p className="text-sm text-muted">{email}</p>
          </div>
        </div>

        {mustChange && (
          <p className="mb-4 rounded-2xl bg-hot px-4 py-3 text-sm text-ink">
            Your password was set by an admin. Choose your own to continue.
          </p>
        )}

        <PasswordForm mustChange={mustChange} />
      </div>
    </div>
  );
}
