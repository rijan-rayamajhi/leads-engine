import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ArrowLeft, Phone, Mail, Globe, Briefcase, User, Star,
  ExternalLink, Check, Clock, X, MessageSquare, FileText, MapPin, Building2,
} from "lucide-react";
import { getActivity, getLead } from "@/lib/db";
import type { Activity } from "@/lib/db";
import ServiceIcon from "@/components/service-icon";
import { BTN, FIELD } from "@/components/ui";
import { ago, cleanName } from "@/lib/leads";
import { addNote, setStatus } from "@/app/actions";

export const dynamic = "force-dynamic";

/** The pipeline as the rep walks it. 'lost' sits outside the flow. */
const FLOW = ["new", "contacted", "replied", "meeting", "proposal", "won"];

const BUCKET: Record<string, string> = { HOT: "bg-hot", WARM: "bg-warm", QUALIFIED: "bg-cool" };

function Row({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-1 text-ink/60">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs text-ink/70">{label}</p>
        <div className="break-words font-medium">{value}</div>
      </div>
    </div>
  );
}

/** Status changes and notes on one rail, the reference's coloured dot timeline. */
function mark(a: Activity) {
  if (!a.status) return { tone: "bg-warm", icon: <MessageSquare size={14} strokeWidth={2} /> };
  if (a.status === "won") return { tone: "bg-won", icon: <Check size={15} strokeWidth={2.5} /> };
  if (a.status === "lost") return { tone: "bg-lost", icon: <X size={15} strokeWidth={2.5} /> };
  return { tone: "bg-cool", icon: <Clock size={14} strokeWidth={2} /> };
}

function Rail({ items }: { items: Activity[] }) {
  if (!items.length)
    return (
      <p className="text-sm text-muted">
        No activity yet. Status changes and notes land here.
      </p>
    );
  return (
    <ol className="flex flex-col">
      {items.map((a, i) => {
        const { tone, icon } = mark(a);
        return (
          <li key={a.id} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className={`grid size-8 shrink-0 place-items-center rounded-full text-ink ${tone}`}>
                {icon}
              </span>
              {i < items.length - 1 && (
                <span className="my-1 w-0.5 flex-1 rounded-full bg-ink/10" />
              )}
            </div>
            <div className="min-w-0 pb-5">
              {a.status ? (
                <p className="text-sm">
                  Marked <span className="font-semibold">{a.status}</span>
                </p>
              ) : (
                <p className="whitespace-pre-wrap text-sm">{a.notes}</p>
              )}
              {a.status && a.notes && (
                <p className="mt-1 whitespace-pre-wrap rounded-2xl bg-sunken px-3 py-2 text-sm">
                  {a.notes}
                </p>
              )}
              <p className="mt-0.5 text-xs text-muted">
                {a.user_email} · {ago(a.updated_at)}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default async function LeadPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { id } = await params;
  const [lead, activity, { tab }] = await Promise.all([getLead(id), getActivity(id), searchParams]);
  if (!lead) notFound();
  const onActivity = tab === "activity";

  const at = FLOW.indexOf(lead.status);
  const lost = lead.status === "lost";
  const tel = lead.phone?.replace(/\s/g, "");

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-center gap-3">
        <Link
          href="/"
          aria-label="Back to pipeline"
          className="grid size-9 place-items-center rounded-full bg-surface text-muted shadow-card transition hover:text-ink"
        >
          <ArrowLeft size={17} strokeWidth={1.75} />
        </Link>
        <h1 title={lead.name ?? ""} className="text-2xl font-semibold">
          {cleanName(lead.name)}
        </h1>
        {lead.category && (
          <span className="rounded-pill bg-cool px-3 py-1 text-sm font-medium text-ink">
            {lead.category}
          </span>
        )}

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {tel && (
            <a
              href={`tel:${tel}`}
              className="flex h-9 items-center gap-1.5 rounded-pill bg-surface px-4 text-sm font-medium shadow-card transition hover:shadow-pop"
            >
              <Phone size={15} strokeWidth={2} />
              {lead.phone}
            </a>
          )}
          <form action={setStatus.bind(null, lead.id, "won")}>
          <button
            className={`h-9 rounded-pill px-5 text-sm font-semibold transition ${
              lead.status === "won" ? "bg-won text-ink" : "bg-surface text-muted shadow-card hover:text-ink"
            }`}
          >
            Won
          </button>
          </form>
          <form action={setStatus.bind(null, lead.id, "lost")}>
          <button
            className={`h-9 rounded-pill px-5 text-sm font-semibold transition ${
              lost ? "bg-lost text-ink" : "bg-surface text-muted shadow-card hover:text-ink"
            }`}
          >
            Lost
          </button>
          </form>
        </div>
      </header>

      <section className="flex items-end gap-3">
        <div>
          <p className="text-sm text-muted">Intent score</p>
          <p className="numeral text-7xl leading-none">{lead.intent_score}</p>
        </div>
        <span
          className={`mb-2 rounded-pill px-3 py-1 text-sm font-semibold text-ink ${
            BUCKET[lead.bucket ?? ""] ?? "bg-sunken"
          }`}
        >
          {lead.bucket}
        </span>
        {lost && (
          <span className="mb-2 rounded-pill bg-lost px-3 py-1 text-sm font-semibold text-ink">
            Lost
          </span>
        )}
      </section>

      {/* the reference's segmented bar: done = green + check, current = yellow + clock */}
      <div className={`-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 ${lost ? "opacity-50" : ""}`}>
        {FLOW.map((s, i) => {
          const done = !lost && i < at;
          const now = !lost && i === at;
          return (
            <form key={s} action={setStatus.bind(null, lead.id, s)} className="min-w-28 flex-1">
            <button
              title={`Mark ${s}`}
              className={`flex h-11 w-full items-center justify-between gap-2 rounded-pill px-4 text-sm font-medium transition ${
                done ? "bg-won text-ink" : now ? "bg-hot text-ink" : "bg-surface text-muted shadow-card hover:text-ink"
              }`}
            >
              <span className="truncate">{s}</span>
              {done && <Check size={15} strokeWidth={2.5} />}
              {now && <Clock size={15} strokeWidth={2} />}
            </button>
            </form>
          );
        })}
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[320px_1fr]">
        <div className="flex flex-col gap-4">
          <section className="flex flex-col gap-4 rounded-card bg-hot p-5 text-ink">
            <h2 className="font-semibold">Details</h2>
            <Row icon={<User size={15} />} label="Name" value={cleanName(lead.name)} />
            <Row
              icon={<Phone size={15} />}
              label="Phone"
              value={
                tel ? (
                  <a href={`tel:${tel}`} className="underline-offset-2 hover:underline">
                    {lead.phone}
                  </a>
                ) : (
                  <span className="text-ink/70">none</span>
                )
              }
            />
            <Row
              icon={<Mail size={15} />}
              label="Email"
              value={lead.email ?? <span className="text-ink/70">not found</span>}
            />
            <Row
              icon={<Globe size={15} />}
              label="Website"
              value={
                lead.website ? (
                  <a href={lead.website} target="_blank" rel="noreferrer" className="hover:underline">
                    {lead.website}
                  </a>
                ) : (
                  <span className="text-ink/70">none, this is the gap</span>
                )
              }
            />
            <Row icon={<Briefcase size={15} />} label="Category" value={lead.category ?? "-"} />
          </section>

          <section className="flex flex-col gap-4 rounded-card bg-warm p-5 text-ink">
            <h2 className="font-semibold">Signal</h2>
            <Row
              icon={<ServiceIcon service={lead.service} size={15} />}
              label="Service to pitch"
              value={lead.service}
            />
            <Row
              icon={<Star size={15} />}
              label="Reputation"
              value={
                lead.rating
                  ? `${Number(lead.rating).toFixed(1)}★ · ${lead.review_count ?? 0} reviews`
                  : "-"
              }
            />
            <Row
              icon={<Phone size={15} />}
              label="Phone checked"
              value={lead.phone_valid ? "valid" : "not verified"}
            />
            <Row
              icon={<ExternalLink size={15} />}
              label="Source"
              value={
                lead.source_url ? (
                  <a href={lead.source_url} target="_blank" rel="noreferrer" className="hover:underline">
                    {lead.source}
                  </a>
                ) : (
                  lead.source
                )
              }
            />
            <Row
              icon={<Building2 size={15} />}
              label="Market"
              value={lead.city ?? "-"}
            />
            <Row
              icon={<Clock size={15} />}
              label="Found"
              value={new Date(lead.found_at).toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            />
          </section>
        </div>

        <section className="flex h-fit flex-col gap-5 rounded-card bg-surface p-6 shadow-card">
          {/* tab strip, data-driven so Outreach is one more entry later */}
          <nav className="flex gap-2">
            {[
              { key: "evidence", label: "Evidence", icon: <FileText size={14} strokeWidth={2} /> },
              {
                key: "activity",
                label: `Activity${activity.length ? ` ${activity.length}` : ""}`,
                icon: <MessageSquare size={14} strokeWidth={2} />,
              },
            ].map((t) => {
              const on = (t.key === "activity") === onActivity;
              return (
                <Link
                  key={t.key}
                  href={`/leads/${lead.id}?tab=${t.key}`}
                  scroll={false}
                  className={`flex h-9 items-center gap-1.5 rounded-pill px-4 text-sm font-medium transition ${
                    on ? "bg-ink text-white" : "bg-sunken text-muted hover:text-ink"
                  }`}
                >
                  {t.icon}
                  {t.label}
                </Link>
              );
            })}
          </nav>

          {onActivity ? (
            <>
              <form action={addNote.bind(null, lead.id)} className="flex items-start gap-2">
                <textarea
                  name="note"
                  rows={2}
                  maxLength={2000}
                  required
                  placeholder="Take a note. What was said on the call?"
                  className={`${FIELD} flex-1 resize-y rounded-2xl py-2.5`}
                />
                <button className={BTN}>
                  Add
                </button>
              </form>
              <Rail items={activity} />
            </>
          ) : (
            <>
              <div>
                <p className="text-xs text-muted">What they want</p>
                <p className="text-lg">{lead.what_they_want}</p>
              </div>

              <div>
                <p className="text-xs text-muted">Why contact them</p>
                <p>{lead.why_contact}</p>
              </div>

              {lead.evidence_quote && (
                <div>
                  <p className="mb-1 text-xs text-muted">What the crawler saw</p>
                  <p className="rounded-2xl bg-sunken px-4 py-3 text-sm">{lead.evidence_quote}</p>
                </div>
              )}

              {lead.assigned_to && <p className="text-sm text-muted">Claimed by {lead.assigned_to}</p>}

              {lead.source_url && (
                <a
                  href={lead.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex h-9 w-fit items-center gap-1.5 rounded-pill bg-sunken px-4 text-sm transition hover:bg-line"
                >
                  <MapPin size={14} strokeWidth={2} /> Google Maps
                </a>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
