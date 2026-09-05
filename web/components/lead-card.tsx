"use client";
import Link from "next/link";
import { ExternalLink, Phone, UserPlus } from "lucide-react";
import ServiceIcon from "./service-icon";
import { Select } from "./ui";
import { STATUSES, cleanName } from "@/lib/leads";
import type { Lead } from "@/lib/db";

const BUCKET: Record<string, string> = {
  HOT: "bg-hot",
  WARM: "bg-warm",
  QUALIFIED: "bg-cool",
};

const STATUS_TONE: Record<string, string> = {
  new: "bg-sunken text-muted",
  contacted: "bg-cool text-ink",
  replied: "bg-cool text-ink",
  meeting: "bg-cool text-ink",
  proposal: "bg-cool text-ink",
  won: "bg-won text-ink",
  lost: "bg-lost text-ink",
};

export default function LeadCard({
  lead,
  me,
  onStatus,
  onClaim,
}: {
  lead: Lead;
  me: string;
  onStatus: (id: string, status: string) => void;
  onClaim: (id: string) => void;
}) {
  const mine = lead.assigned_to === me;
  const theirs = !!lead.assigned_to && !mine;

  return (
    <article
      className={`flex flex-col gap-3 rounded-card bg-surface p-5 shadow-card transition ${
        theirs ? "opacity-60" : ""
      }`}
    >
      <header className="flex items-start gap-2">
        <h3 title={lead.name ?? ""} className="line-clamp-2 flex-1 font-semibold leading-snug">
          <Link href={`/leads/${lead.id}`} className="hover:underline">
            {cleanName(lead.name)}
          </Link>
        </h3>
        <span
          className={`shrink-0 rounded-pill px-2.5 py-1 text-xs font-semibold text-ink ${
            BUCKET[lead.bucket ?? ""] ?? "bg-sunken"
          }`}
        >
          {lead.bucket}
        </span>
        <span className="shrink-0 pt-1 text-sm tabular-nums text-muted">{lead.intent_score}</span>
      </header>

      {/* Evidence first: it is the only line that differs lead to lead. The ask
          (what_they_want) is the service pill's job; the full text is on the detail page. */}
      {lead.evidence_quote && (
        <p className="-mt-1 line-clamp-2 text-sm">{lead.evidence_quote}</p>
      )}
      <p className="-mt-2 line-clamp-2 text-sm text-muted">{lead.why_contact}</p>

      <footer className="mt-auto flex flex-wrap items-center gap-2 pt-1">
        <span
          title={lead.what_they_want ?? ""}
          className="flex h-8 items-center gap-1.5 rounded-pill bg-sunken px-3 text-xs text-muted"
        >
          <ServiceIcon service={lead.service} />
          {lead.service}
        </span>

        {lead.phone && (
          <a
            href={`tel:${lead.phone.replace(/\s/g, "")}`}
            className="flex h-8 items-center gap-1.5 rounded-pill bg-won px-3 text-sm font-medium text-ink transition hover:opacity-85"
          >
            <Phone size={14} strokeWidth={2} />
            {lead.phone}
          </a>
        )}

        <Select
          size="xs"
          aria-label="Status"
          value={lead.status}
          onChange={(e) => onStatus(lead.id, e.target.value)}
          className={STATUS_TONE[lead.status] ?? "bg-sunken text-muted"}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>

        {theirs ? (
          <span
            title={`Claimed by ${lead.assigned_to}`}
            className="grid size-8 place-items-center rounded-full bg-warm text-xs font-semibold text-ink"
          >
            {lead.assigned_to![0]?.toUpperCase()}
          </span>
        ) : (
          <button
            onClick={() => onClaim(lead.id)}
            title={mine ? "Claimed by you, click to release" : "Claim this lead"}
            aria-label={mine ? "Release this lead" : "Claim this lead"}
            aria-pressed={mine}
            className={`grid size-8 place-items-center rounded-full text-sm font-semibold transition ${
              mine ? "bg-warm text-ink" : "bg-sunken text-muted hover:text-ink"
            }`}
          >
            {mine ? me[0]?.toUpperCase() : <UserPlus size={14} strokeWidth={1.75} />}
          </button>
        )}

        {lead.source_url && (
          <a
            href={lead.source_url}
            target="_blank"
            rel="noreferrer"
            title={`Open source: ${lead.source ?? ""}`}
            aria-label="Open source"
            className="ml-auto grid size-8 place-items-center rounded-full text-muted transition hover:bg-sunken hover:text-ink"
          >
            <ExternalLink size={15} strokeWidth={1.75} />
          </a>
        )}
      </footer>
    </article>
  );
}
