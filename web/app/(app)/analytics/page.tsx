import { readFile } from "node:fs/promises";
import path from "node:path";
import { Check, X, Minus, Filter, Gauge, Package, Radio, SlidersHorizontal } from "lucide-react";
import { analytics, type Breakdown } from "@/lib/db";
import { currentMarket } from "@/lib/market";
import { MIN_DECIDED, STATUSES, winRate } from "@/lib/leads";

export const dynamic = "force-dynamic";

/** Magnitude by bar length, identity by the printed label. The pastels fail
 *  CVD separation as a categorical palette, so no series is encoded by colour. */
function Meter({ pct }: { pct: number }) {
  return (
    <div className="h-2 w-20 overflow-hidden rounded-full bg-sunken" aria-hidden>
      <div className="h-full rounded-full bg-won" style={{ width: `${Math.max(pct, 2)}%` }} />
    </div>
  );
}

function Table({ title, icon, rows }: { title: string; icon: React.ReactNode; rows: Breakdown[] }) {
  return (
    <section className="flex flex-col gap-3 rounded-card bg-surface p-5 shadow-card">
      <h2 className="flex items-center gap-2 font-semibold">
        {icon}
        {title}
      </h2>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">Nothing yet.</p>
      ) : (
        <div className="-mx-1 overflow-x-auto px-1">
        <table className="w-full min-w-lg text-sm">
          <thead className="text-xs text-muted">
            <tr className="text-left">
              <th className="pb-2 font-normal">Name</th>
              <th className="pb-2 text-right font-normal">Leads</th>
              <th className="pb-2 text-right font-normal">Worked</th>
              <th className="pb-2 text-right font-normal">Won</th>
              <th className="pb-2 text-right font-normal">Lost</th>
              <th className="pb-2 pl-4 font-normal">Win rate</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const { enough, pct, needed } = winRate(r.won, r.lost);
              return (
                <tr key={r.key} className="border-t border-line">
                  <td className="py-2 pr-2 font-medium">{r.key}</td>
                  <td className="py-2 text-right tabular-nums">{r.total}</td>
                  <td className="py-2 text-right tabular-nums text-muted">{r.worked}</td>
                  <td className="py-2 text-right tabular-nums">{r.won}</td>
                  <td className="py-2 text-right tabular-nums">{r.lost}</td>
                  <td className="py-2 pl-4">
                    {enough ? (
                      <span className="flex items-center gap-2">
                        <Meter pct={pct} />
                        <span className="tabular-nums">{pct}%</span>
                      </span>
                    ) : (
                      <span className="text-xs text-muted">{needed} more decided</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}

async function weights() {
  // crawler/weights.json is written nightly by feedback.py. Absent on a web-only
  // deploy (Vercel root is web/), and then the tables above are the whole story.
  try {
    const raw = await readFile(path.join(process.cwd(), "..", "crawler", "weights.json"), "utf8");
    return JSON.parse(raw) as Record<string, number>;
  } catch {
    return null;
  }
}

export default async function AnalyticsPage() {
  const [{ funnel, breakdown }, tuned] = await Promise.all([analytics(await currentMarket()), weights()]);

  const by = (d: Breakdown["dim"]) =>
    breakdown.filter((r) => r.dim === d).sort((a, b) => b.total - a.total);

  const count = (s: string) => funnel.find((f) => f.status === s)?.n ?? 0;
  const total = funnel.reduce((n, f) => n + f.n, 0);
  const won = count("won");
  const lost = count("lost");
  const { decided, enough, pct, needed } = winRate(won, lost);

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-wrap items-end gap-x-6 gap-y-1">
        <div>
          <p className="text-sm text-muted">
            {enough ? "Win rate" : "Outcomes decided"}
          </p>
          <p className="numeral text-7xl leading-none sm:text-8xl">
            {enough ? `${pct}%` : decided}
          </p>
        </div>
        <p className="mb-2 text-sm text-muted">
          {enough
            ? `${won} won · ${lost} lost of ${total} leads`
            : `${needed} more won/lost before a rate means anything · ${total} leads so far`}
        </p>
      </section>

      {/* Funnel: labelled stat row, not a chart. One stage holds almost everything. */}
      <section className="flex flex-col gap-3 rounded-card bg-surface p-5 shadow-card">
        <h2 className="flex items-center gap-2 font-semibold">
          <Filter size={16} strokeWidth={2} />
          Pipeline
        </h2>
        <div className="flex flex-wrap gap-1.5">
          {STATUSES.map((s) => {
            const n = count(s);
            const tone =
              s === "won" ? "bg-won" : s === "lost" ? "bg-lost" : n > 0 ? "bg-cool" : "bg-sunken";
            return (
              <div
                key={s}
                className={`flex min-w-28 flex-1 items-center justify-between gap-2 rounded-pill px-4 py-2.5 text-sm ${tone} ${
                  n > 0 ? "text-ink" : "text-muted"
                }`}
              >
                <span className="flex items-center gap-1.5">
                  {s === "won" && <Check size={14} strokeWidth={2.5} />}
                  {s === "lost" && <X size={14} strokeWidth={2.5} />}
                  {s !== "won" && s !== "lost" && n === 0 && <Minus size={14} strokeWidth={2} />}
                  {s}
                </span>
                <span className="font-semibold tabular-nums">{n}</span>
              </div>
            );
          })}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <Table title="By source" icon={<Radio size={16} strokeWidth={2} />} rows={by("source")} />
        <Table title="By service" icon={<Package size={16} strokeWidth={2} />} rows={by("service")} />
        <Table title="By score bucket" icon={<Gauge size={16} strokeWidth={2} />} rows={by("bucket")} />

        <section className="flex flex-col gap-3 rounded-card bg-surface p-5 shadow-card">
          <h2 className="flex items-center gap-2 font-semibold">
            <SlidersHorizontal size={16} strokeWidth={2} />
            Source weights
          </h2>
          <p className="text-sm text-muted">
            feedback.py folds these into every new score, nightly.
          </p>
          {tuned ? (
            <ul className="flex flex-col gap-2">
              {Object.entries(tuned).map(([source, w]) => (
                <li key={source} className="flex items-center justify-between border-t border-line pt-2 text-sm">
                  <span className="font-medium">{source}</span>
                  <span className="tabular-nums">{w.toFixed(3)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-2xl bg-sunken px-4 py-3 text-sm text-muted">
              Not tuned yet. Needs {MIN_DECIDED} decided leads on a source.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
