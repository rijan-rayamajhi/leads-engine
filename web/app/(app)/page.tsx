import Board from "@/components/board";
import { listLeads } from "@/lib/db";
import { requireSession } from "@/lib/auth";
import { currentMarket } from "@/lib/market";

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  const [{ email }, market] = await Promise.all([requireSession(), currentMarket()]);
  const leads = await listLeads(market);
  return <Board leads={leads} me={email} />;
}
