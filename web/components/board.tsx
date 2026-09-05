"use client";
import { useEffect, useOptimistic, useRef, useState, useTransition } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { setStatus, toggleClaim } from "@/app/actions";
import LeadCard from "./lead-card";
import { CHIP, Select } from "./ui";
import {
  BUCKETS,
  LEAD_LIMIT,
  STATUSES,
  filterLeads,
  heroCounts,
  pageWindow,
  paginate,
} from "@/lib/leads";
import type { Lead } from "@/lib/db";

const BUCKET: Record<string, string> = { HOT: "bg-hot", WARM: "bg-warm", QUALIFIED: "bg-cool" };

export default function Board({ leads, me }: { leads: Lead[]; me: string }) {
  const [rows, patch] = useOptimistic(leads, (state, p: Partial<Lead> & { id: string }) =>
    state.map((l) => (l.id === p.id ? { ...l, ...p } : l)),
  );
  const [, start] = useTransition();
  const [bucket, setBucket] = useState("all");
  const [status, setStatusF] = useState("all");
  const [service, setService] = useState("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  const services = [...new Set(rows.map((l) => l.service).filter(Boolean))] as string[];
  const filters = { bucket, status, service, q };
  const { ready, newToday, byBucket } = heroCounts(rows);
  const shown = filterLeads(rows, filters);

  const { slice, pages, current, from, to } = paginate(shown, page);

  // any filter change puts you back on page 1; page 4 of an old result set is
  // never what you meant
  useEffect(() => {
    setPage(1);
  }, [bucket, status, service, q]);

  function go(n: number) {
    setPage(n);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const filtered = bucket !== "all" || status !== "all" || service !== "all" || !!q.trim();
  const clear = () => {
    setBucket("all");
    setStatusF("all");
    setService("all");
    setQ("");
  };

  function changeStatus(id: string, next: string) {
    start(async () => {
      patch({ id, status: next });
      await setStatus(id, next);
    });
  }

  function claim(id: string) {
    start(async () => {
      const mine = rows.find((l) => l.id === id)?.assigned_to === me;
      patch({ id, assigned_to: mine ? null : me });
      await toggleClaim(id);
    });
  }

  // "/" jumps to search, Escape clears it. A rep scanning 80 cards keeps both hands home.
  const search = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(tag)) {
        e.preventDefault();
        search.current?.focus();
      } else if (e.key === "Escape" && document.activeElement === search.current) {
        setQ("");
        search.current?.blur();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);


  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-wrap items-end gap-x-6 gap-y-1">
        <div>
          <p className="text-sm text-muted">Ready to call</p>
          <p className="numeral text-7xl leading-none sm:text-8xl">{ready}</p>
        </div>
        <p className="mb-2 text-sm text-muted">
          {newToday} found today · {rows.length} in the pipeline
        </p>
      </section>

      <section className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setBucket("all")}
          className={`${CHIP} ${bucket === "all" ? "bg-ink text-white" : "bg-surface text-muted shadow-card hover:text-ink"}`}
        >
          All {rows.length}
        </button>
        {BUCKETS.map((b) => (
          <button
            key={b}
            onClick={() => setBucket(bucket === b ? "all" : b)}
            className={`${CHIP} ${
              bucket === b ? `${BUCKET[b]} text-ink` : "bg-surface text-muted shadow-card hover:text-ink"
            }`}
          >
            {b} {byBucket[b]}
          </button>
        ))}

        <label className="ml-auto flex h-9 items-center gap-2 rounded-pill bg-surface px-3 text-muted shadow-card transition focus-within:ring-2 focus-within:ring-ink">
          <Search size={15} strokeWidth={1.75} />
          <input
            ref={search}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search name, need, phone…"
            aria-label="Search leads"
            className="w-40 bg-transparent text-sm text-ink focus-visible:outline-none placeholder:text-muted sm:w-48"
          />
          {!q && (
            <kbd className="hidden rounded border border-line px-1.5 text-xs text-muted sm:block">
              /
            </kbd>
          )}
        </label>

        {services.length > 1 && (
          <Select
            aria-label="Filter by service"
            value={service}
            onChange={(e) => setService(e.target.value)}
            className="bg-surface text-muted shadow-card"
          >
            <option value="all">All services</option>
            {services.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        )}

        <Select
          aria-label="Filter by status"
          value={status}
          onChange={(e) => setStatusF(e.target.value)}
          className="bg-surface text-muted shadow-card"
        >
          <option value="all">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </section>

      {shown.length === 0 ? (
        <div className="grid place-items-center gap-3 rounded-card bg-surface p-12 text-center shadow-card">
          <p className="text-muted">
            {rows.length === 0
              ? "No leads yet. The crawler runs every 6 hours."
              : "No leads match these filters."}
          </p>
          {filtered && (
            <button onClick={clear} className={`${CHIP} bg-ink text-white`}>
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <>
          <section className="grid gap-3 xl:grid-cols-2">
            {slice.map((l) => (
              <LeadCard key={l.id} lead={l} me={me} onStatus={changeStatus} onClaim={claim} />
            ))}
          </section>

          <nav aria-label="Pagination" className="flex flex-wrap items-center justify-center gap-1.5">
            <p className="mr-auto text-sm text-muted">
              {from}-{to} of {shown.length}
              {rows.length >= LEAD_LIMIT && `, newest ${LEAD_LIMIT} loaded`}
            </p>

            {pages > 1 && (
              <>
                <button
                  onClick={() => go(current - 1)}
                  disabled={current === 1}
                  aria-label="Previous page"
                  className="grid size-9 place-items-center rounded-full bg-surface text-muted shadow-card transition hover:text-ink disabled:opacity-40 disabled:hover:text-muted"
                >
                  <ChevronLeft size={16} strokeWidth={2} />
                </button>

                {pageWindow(current, pages).map((n, i) =>
                  n === null ? (
                    <span key={`gap-${i}`} className="px-1 text-sm text-muted">
                      …
                    </span>
                  ) : (
                    <button
                      key={n}
                      onClick={() => go(n)}
                      aria-label={`Page ${n}`}
                      aria-current={n === current ? "page" : undefined}
                      className={`${CHIP} tabular-nums ${
                        n === current
                          ? "bg-ink text-white"
                          : "bg-surface text-muted shadow-card hover:text-ink"
                      }`}
                    >
                      {n}
                    </button>
                  ),
                )}

                <button
                  onClick={() => go(current + 1)}
                  disabled={current === pages}
                  aria-label="Next page"
                  className="grid size-9 place-items-center rounded-full bg-surface text-muted shadow-card transition hover:text-ink disabled:opacity-40 disabled:hover:text-muted"
                >
                  <ChevronRight size={16} strokeWidth={2} />
                </button>
              </>
            )}
          </nav>
        </>
      )}
    </div>
  );
}
