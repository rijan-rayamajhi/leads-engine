"use client";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Target, BarChart3, Activity, LogOut, Settings } from "lucide-react";
import { logout, setMarket } from "@/app/actions";
import { Select } from "./ui";

/* Rail holds 6 slots, uses 4. Outreach lands in slot 5 without a relayout.
   Left rail on desktop, bottom bar on a phone: same list, same order. */
const NAV: { href: string; label: string; icon: typeof Target; live: boolean; admin?: boolean }[] = [
  { href: "/", label: "Pipeline", icon: Target, live: true },
  { href: "/analytics", label: "Analytics", icon: BarChart3, live: true },
  { href: "/runs", label: "Crawler runs", icon: Activity, live: true },
  { href: "/settings", label: "Settings", icon: Settings, live: true, admin: true },
];

const Logo = ({ className = "" }) => (
  <Link href="/" aria-label="Lead Engine" className={`shrink-0 ${className}`}>
    <Image src="/logo.png" alt="" width={44} height={44} priority className="size-11 object-contain" />
  </Link>
);

export default function AppShell({
  email,
  role,
  markets,
  market,
  children,
}: {
  email: string;
  role: string;
  markets: string[];
  market: string;
  children: React.ReactNode;
}) {
  const path = usePathname();
  const base = "grid size-11 place-items-center rounded-2xl transition";
  // The market lens only changes what these pages show. On one lead, or on
  // settings, it would be a control that does nothing.
  const scoped = path === "/" || path.startsWith("/analytics") || path.startsWith("/runs");

  return (
    <div className="flex min-h-screen gap-3 p-3 sm:gap-4 sm:p-4">
      <nav
        aria-label="Sections"
        className="fixed inset-x-0 bottom-0 z-10 flex justify-around gap-2 border-t border-line bg-surface/95 px-3 py-2 backdrop-blur sm:sticky sm:top-4 sm:h-[calc(100vh-2rem)] sm:flex-col sm:justify-start sm:border-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none"
      >
        <Logo className="mb-2 hidden sm:grid" />
        {NAV.filter((n) => !n.admin || role === "admin").map(({ href, label, icon: Icon, live }) => {
          const active = live && (href === "/" ? path === "/" : path.startsWith(href));
          if (!live)
            return (
              <span
                key={href}
                title={`${label} (coming soon)`}
                aria-disabled="true"
                className={`${base} bg-surface text-muted/50 shadow-card`}
              >
                <Icon size={18} strokeWidth={1.75} />
              </span>
            );
          return (
            <Link
              key={href}
              href={href}
              title={label}
              aria-label={label}
              aria-current={active ? "page" : undefined}
              className={`${base} shadow-card ${
                active ? "bg-won text-ink" : "bg-surface text-muted hover:text-ink"
              }`}
            >
              <Icon size={18} strokeWidth={1.75} />
            </Link>
          );
        })}

        <div className="mt-auto hidden flex-col items-center gap-2 sm:flex">
          <span
            title={email}
            className="grid size-11 place-items-center rounded-full bg-warm text-sm font-semibold text-ink"
          >
            {email[0]?.toUpperCase()}
          </span>
          <form action={logout}>
            <button
              title={`Sign out (${email})`}
              aria-label="Sign out"
              className={`${base} bg-surface text-muted shadow-card hover:text-ink`}
            >
              <LogOut size={18} strokeWidth={1.75} />
            </button>
          </form>
        </div>
      </nav>

      {/* pb clears the fixed bottom bar on phones */}
      <div className="flex min-w-0 flex-1 flex-col gap-4 pb-20 sm:pb-0">
        <header className={`flex items-center gap-3 ${scoped ? "" : "sm:hidden"}`}>
          <Logo className="sm:hidden" />
          {scoped && (
          <form action={setMarket}>
            <Select
              name="market"
              defaultValue={market}
              aria-label="Market"
              onChange={(e) => e.currentTarget.form?.requestSubmit()}
              className="bg-cool text-ink"
            >
              <option value="all">All markets</option>
              {markets.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </form>
          )}

          <form action={logout} className="ml-auto flex items-center gap-2 sm:hidden">
            <span
              title={email}
              className="grid size-9 place-items-center rounded-full bg-warm text-sm font-semibold text-ink"
            >
              {email[0]?.toUpperCase()}
            </span>
            <button className="text-sm text-muted transition hover:text-ink">Sign out</button>
          </form>
        </header>

        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
