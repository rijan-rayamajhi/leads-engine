import type { Lead } from "./db";

export type Filters = { bucket: string; status: string; service: string; q: string };

export const BUCKETS = ["HOT", "WARM", "QUALIFIED"];
export const STATUSES = ["new", "contacted", "replied", "meeting", "proposal", "won", "lost"];

/** Places names are SEO-stuffed: "Carpe Diem Bakery | Top Restaurant in Kathmandu".
 *  ponytail: first segment only; full name stays in the title attribute. */
export const cleanName = (n: string | null) => (n ?? "Unknown").split("|")[0].trim();

export function filterLeads(rows: Lead[], f: Filters) {
  const needle = f.q.trim().toLowerCase();
  return rows.filter((l) => {
    if (f.bucket !== "all" && l.bucket !== f.bucket) return false;
    if (f.status !== "all" && l.status !== f.status) return false;
    if (f.service !== "all" && l.service !== f.service) return false;
    if (!needle) return true;
    const hay = `${l.name} ${l.what_they_want} ${l.why_contact} ${l.evidence_quote} ${l.phone}`;
    return hay.toLowerCase().includes(needle);
  });
}

/** The hero: untouched, callable, worth calling. Same rule as the crawler's buckets. */
export function heroCounts(rows: Lead[], now = Date.now()) {
  return {
    ready: rows.filter(
      (l) => l.status === "new" && !!l.phone && (l.bucket === "HOT" || l.bucket === "WARM"),
    ).length,
    newToday: rows.filter((l) => now - new Date(l.found_at).getTime() < 86_400_000).length,
    byBucket: Object.fromEntries(
      BUCKETS.map((b) => [b, rows.filter((l) => l.bucket === b).length]),
    ) as Record<string, number>,
  };
}

/** Compact relative time for the activity rail: "just now", "4h", "2d", then a date. */
export function ago(iso: string, now = Date.now()) {
  const s = Math.floor((now - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 604_800) return `${Math.floor(s / 86_400)}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** Mirrors MIN_DECIDED in crawler/feedback.py. Below this a rate is noise, so
 *  the UI says how many more are needed instead of printing a fake 0% or 100%. */
export const MIN_DECIDED = 5;

export function winRate(won: number, lost: number) {
  const decided = won + lost;
  return {
    decided,
    enough: decided >= MIN_DECIDED,
    needed: Math.max(MIN_DECIDED - decided, 0),
    pct: decided ? Math.round((won / decided) * 100) : 0,
  };
}

/** Crawler cadence, from .github/workflows/crawl.yml. A run that hasn't landed
 *  in 1.5 cycles means the cron is broken, which is the whole point of /runs. */
export const CRON_HOURS = 6;

export function runHealth(lastOkIso: string | null, now = Date.now()) {
  if (!lastOkIso) return { everRan: false, stale: true, hours: null };
  const hours = (now - new Date(lastOkIso).getTime()) / 3_600_000;
  return { everRan: true, stale: hours > CRON_HOURS * 1.5, hours };
}

/** Rows listLeads will return at most. The board filters in the browser, so this
 *  is also the point past which it would silently show a subset; the UI says so
 *  when it is reached. */
export const LEAD_LIMIT = 500;

export const PAGE_SIZE = 24;

export function paginate<T>(items: T[], page: number, size = PAGE_SIZE) {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(Math.max(page, 1), pages); // clamp, so a stale page never blanks the list
  const start = (current - 1) * size;
  return {
    pages,
    current,
    slice: items.slice(start, start + size),
    from: items.length === 0 ? 0 : start + 1,
    to: Math.min(start + size, items.length),
  };
}

/** Page numbers to render: all of them while they fit, otherwise first, last and
 *  a window around the current page, with null marking an elided run. */
export function pageWindow(current: number, pages: number): (number | null)[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const near = [current - 1, current, current + 1].filter((n) => n > 1 && n < pages);
  const out: (number | null)[] = [1];
  if (near[0] > 2) out.push(null);
  out.push(...near);
  if (near[near.length - 1] < pages - 1) out.push(null);
  out.push(pages);
  return out;
}
