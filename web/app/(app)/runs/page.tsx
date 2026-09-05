import { AlertTriangle, Check, History, Loader, Search, Sparkles, X } from "lucide-react";
import { getRuns, type Run } from "@/lib/db";
import { ago, CRON_HOURS, runHealth } from "@/lib/leads";
import { currentMarket } from "@/lib/market";

export const dynamic = "force-dynamic";

function outcome(r: Run) {
  if (r.error) return { label: "failed", tone: "bg-lost", icon: <X size={13} strokeWidth={2.5} /> };
  if (!r.finished_at)
    return { label: "running", tone: "bg-hot", icon: <Loader size={13} strokeWidth={2} /> };
  return { label: "ok", tone: "bg-won", icon: <Check size={13} strokeWidth={2.5} /> };
}

function took(r: Run) {
  if (!r.finished_at) return "-";
  const s = Math.round(
    (new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000,
  );
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export default async function RunsPage() {
  const { runs, lastOk } = await getRuns(25, await currentMarket());
  const health = runHealth(lastOk);

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-wrap items-end gap-x-6 gap-y-1">
        <div>
          <p className="text-sm text-muted">Last successful crawl</p>
          <p className="numeral text-6xl leading-none sm:text-7xl">
            {health.everRan ? ago(lastOk!) : "never"}
          </p>
        </div>
        <p className="mb-2 text-sm text-muted">
          cron runs every {CRON_HOURS}h · {runs.length} recent runs
        </p>
      </section>

      {health.stale && (
        <p className="flex items-center gap-2 rounded-card bg-hot px-5 py-4 text-sm font-medium text-ink">
          <AlertTriangle size={16} strokeWidth={2} />
          {health.everRan
            ? `No successful crawl in ${Math.round(health.hours!)}h. The GitHub Action may be failing or disabled.`
            : "No crawl has ever recorded a run. Check the crawl workflow and its secrets."}
        </p>
      )}

      <section className="flex flex-col gap-3 rounded-card bg-surface p-5 shadow-card">
        <h2 className="flex items-center gap-2 font-semibold">
          <History size={16} strokeWidth={2} />
          Recent runs
        </h2>
        {runs.length === 0 ? (
          <p className="text-sm text-muted">Nothing yet. The next run writes a row here.</p>
        ) : (
          <div className="-mx-1 overflow-x-auto px-1">
        <table className="w-full min-w-lg text-sm">
            <thead className="text-xs text-muted">
              <tr className="text-left">
                <th className="pb-2 font-normal">Job</th>
                <th className="pb-2 font-normal">Started</th>
                <th className="pb-2 text-right font-normal">Took</th>
                <th className="pb-2 text-right font-normal">Signals</th>
                <th className="pb-2 text-right font-normal">Leads</th>
                <th className="pb-2 pl-4 font-normal">Result</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const o = outcome(r);
                const stages = Object.entries(r.stats ?? {});
                return (
                  <tr key={r.id} className="border-t border-line align-top">
                    <td className="py-2 pr-3">
                      <span className="flex items-center gap-1.5 font-medium">
                        {r.job === "gap" ? (
                          <Sparkles size={13} strokeWidth={2} />
                        ) : (
                          <Search size={13} strokeWidth={2} />
                        )}
                        {r.job}
                      </span>
                      {r.city && <span className="block text-xs text-muted">{r.city}</span>}
                    </td>
                    <td className="py-2 pr-3">
                      {ago(r.started_at)}
                      {stages.length > 0 && (
                        <span className="mt-1 flex flex-wrap gap-1">
                          {stages.map(([k, v]) => (
                            <span key={k} className="rounded-pill bg-sunken px-2 py-0.5 text-xs text-muted">
                              {k} {v}
                            </span>
                          ))}
                        </span>
                      )}
                      {r.error && (
                        <span className="mt-1 block rounded-2xl bg-sunken px-3 py-1.5 text-xs text-ink">
                          {r.error}
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-right tabular-nums text-muted">{took(r)}</td>
                    <td className="py-2 text-right tabular-nums">{r.signals_new ?? "-"}</td>
                    <td className="py-2 text-right tabular-nums">{r.leads_new ?? "-"}</td>
                    <td className="py-2 pl-4">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-xs font-medium text-ink ${o.tone}`}
                      >
                        {o.icon}
                        {o.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        )}
      </section>
    </div>
  );
}
