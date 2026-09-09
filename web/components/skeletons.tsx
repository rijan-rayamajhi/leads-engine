/** Loading skeletons, one composed shape per route. They mirror the real page's
 *  layout (same hero, same card grid, same table) so the swap to real content
 *  doesn't shift anything. Shape comes from radii + shadow-card, like every
 *  other surface; the shimmer is the .skeleton class. Each exported screen wraps
 *  itself in a single role=status/aria-busy region with an sr-only label, so a
 *  screen reader hears "Loading" once, not one announcement per block. */
import { Skeleton } from "./ui";

// Distinct string keys for static placeholder lists (index keys are lint-denied
// and meaningless here anyway - nothing reorders).
const keys = (n: number, p: string) => Array.from({ length: n }, (_, i) => `${p}${i}`);

function Busy({ label, children }: { label: string; children: React.ReactNode }) {
  // <output> carries an implicit role=status, so a reader announces the label
  // once while the region is busy.
  return (
    <output aria-busy="true" className="flex flex-col gap-5">
      <span className="sr-only">{label}</span>
      {children}
    </output>
  );
}

/* Hero: the muted label, the big display numeral, the caption line. */
function Hero() {
  return (
    <section className="flex flex-wrap items-end gap-x-6 gap-y-2">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-16 w-40 rounded-xl sm:h-20" />
      </div>
      <Skeleton className="mb-2 h-4 w-56" />
    </section>
  );
}

function LeadCardSkel() {
  return (
    <article className="flex flex-col gap-3 rounded-card bg-surface p-5 shadow-card">
      <header className="flex items-start gap-2">
        <Skeleton className="h-5 flex-1" />
        <Skeleton className="h-6 w-16" />
        <Skeleton className="h-5 w-6" />
      </header>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-4/5" />
      <div className="mt-1 flex items-center gap-2">
        <Skeleton className="h-9 w-28" />
        <Skeleton className="h-9 w-9" />
        <Skeleton className="ml-auto h-9 w-24" />
      </div>
    </article>
  );
}

function TableCard({ title = "w-40", rows = 5 }: { title?: string; rows?: number }) {
  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-card bg-surface p-5 shadow-card">
      <Skeleton className={`h-5 ${title}`} />
      <div className="flex flex-col gap-2.5 pt-1">
        {keys(rows, "row").map((k) => (
          <div key={k} className="flex items-center gap-3">
            <Skeleton className="h-4 flex-1" />
            <Skeleton className="h-4 w-10" />
            <Skeleton className="h-2 w-20 rounded-full" />
          </div>
        ))}
      </div>
    </section>
  );
}

export function BoardSkeleton() {
  return (
    <Busy label="Loading pipeline">
      <Hero />
      <section className="flex flex-wrap items-center gap-2">
        <Skeleton className="h-9 w-16" />
        <Skeleton className="h-9 w-24" />
        <Skeleton className="h-9 w-24" />
        <Skeleton className="h-9 w-28" />
        <Skeleton className="ml-auto h-9 w-48" />
        <Skeleton className="h-9 w-32" />
      </section>
      <section className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
        {keys(6, "lead").map((k) => (
          <LeadCardSkel key={k} />
        ))}
      </section>
    </Busy>
  );
}

export function AnalyticsSkeleton() {
  return (
    <Busy label="Loading analytics">
      <Hero />
      <div className="grid gap-4 lg:grid-cols-2">
        <TableCard rows={5} />
        <TableCard rows={6} />
        <TableCard rows={4} />
        <TableCard rows={3} />
      </div>
    </Busy>
  );
}

export function RunsSkeleton() {
  return (
    <Busy label="Loading crawler runs">
      <Hero />
      <TableCard title="w-36" rows={8} />
    </Busy>
  );
}

export function SettingsSkeleton() {
  return (
    <Busy label="Loading settings">
      <Hero />
      {keys(2, "form").map((k) => (
        <section key={k} className="flex flex-col gap-4 rounded-card bg-surface p-5 shadow-card">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-11 w-full" />
          <Skeleton className="h-11 w-full" />
          <Skeleton className="h-11 w-32" />
        </section>
      ))}
    </Busy>
  );
}

export function LeadDetailSkeleton() {
  return (
    <Busy label="Loading lead">
      <section className="flex flex-col gap-3 rounded-card bg-surface p-6 shadow-card">
        <div className="flex items-start gap-3">
          <Skeleton className="h-8 flex-1 rounded-xl" />
          <Skeleton className="h-7 w-20" />
        </div>
        <Skeleton className="h-4 w-2/3" />
        <div className="flex gap-2 pt-1">
          <Skeleton className="h-9 w-32" />
          <Skeleton className="h-9 w-28" />
        </div>
      </section>
      <div className="grid gap-4 lg:grid-cols-2">
        <TableCard title="w-28" rows={4} />
        <TableCard title="w-32" rows={4} />
      </div>
    </Busy>
  );
}
