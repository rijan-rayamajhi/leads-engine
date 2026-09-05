import AppShell from "@/components/app-shell";
import { redirect } from "next/navigation";
import { requireSession } from "@/lib/auth";
import { getMarkets, getSettings } from "@/lib/db";
import { currentMarket } from "@/lib/market";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const [session, markets, market] = await Promise.all([
    requireSession(),
    getMarkets(),
    currentMarket(),
  ]);
  if (session.mustChange) redirect("/password");
  const { email, role } = session;
  return (
    <AppShell email={email} role={role} markets={markets} market={market}>
      {children}
    </AppShell>
  );
}
