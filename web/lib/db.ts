import { neon } from "@neondatabase/serverless";
import { unstable_cache } from "next/cache";
import { LEAD_LIMIT } from "./leads";
import { DEFAULTS, type Settings } from "./settings";

export const sql = neon(process.env.DATABASE_URL!);

export type Lead = {
  id: string;
  name: string | null;
  phone: string | null;
  email: string | null;
  service: string | null;
  what_they_want: string | null;
  evidence_quote: string | null;
  why_contact: string | null;
  source: string | null;
  source_url: string | null;
  intent_score: number | null;
  bucket: string | null;
  status: string;
  assigned_to: string | null;
  found_at: string;
  /** AI-written call opener. Null when the pitch stage has not run for this
   *  lead; why_contact is the rule-written fallback and is never null. */
  pitch: string | null;
  pitch_angle: string | null;
};


/** Board rows. DROP is stored but never shown, and so is a lead whose defect
 *  has since been fixed (stale_at set by website_leads.recheck_open_leads):
 *  opening a call with a claim the prospect can disprove is worse than silence.
 *  ponytail: capped at 500 and filtered in the browser. Instant, and 83 rows
 *  today. Move filters into this WHERE when the cap starts biting. */
async function listLeadsRaw(market = "all") {
  return (await sql`
    select id, name, phone, email, service, what_they_want, evidence_quote,
           why_contact, source, source_url, intent_score, bucket, status,
           assigned_to, found_at, pitch, pitch_angle
    from leads
    where bucket in ('HOT','WARM','QUALIFIED')
      and stale_at is null
      and (${market} = 'all' or city = ${market})
    order by case bucket when 'HOT' then 0 when 'WARM' then 1 else 2 end,
             intent_score desc nulls last,
             found_at desc
    limit ${LEAD_LIMIT}
  `) as Lead[];
}

export type LeadDetail = Lead & {
  city: string | null;
  category: string | null;
  rating: string | null;
  review_count: number | null;
  website: string | null;
  phone_valid: boolean | null;
};

export async function getLead(id: string) {
  const [row] = (await sql`
    select l.id, l.name, l.phone, l.email, l.service, l.what_they_want,
           l.evidence_quote, l.why_contact, l.source, l.source_url, l.intent_score,
           l.bucket, l.status, l.assigned_to, l.found_at, l.city,
           l.pitch, l.pitch_angle,
           c.category, c.rating, c.review_count, c.website, c.phone_valid
    from leads l left join companies c on c.id = l.company_id
    where l.id = ${id}
  `) as LeadDetail[];
  return row ?? null;
}

export type Activity = {
  id: number;
  user_email: string | null;
  status: string | null;   // null = a note, not a status change
  notes: string | null;
  updated_at: string;
};

export async function getActivity(leadId: string) {
  return (await sql`
    select id, user_email, status, notes, updated_at
    from outcomes where lead_id = ${leadId}
    order by updated_at desc, id desc
  `) as Activity[];
}

export type Breakdown = {
  dim: "source" | "service" | "bucket";
  key: string;
  total: number;
  worked: number;
  won: number;
  lost: number;
};

/** Win rates per dimension: the same numbers crawler/feedback.py retunes on. */
async function analyticsRaw(market = "all") {
  const [funnel, breakdown] = await Promise.all([
    sql`select status, count(*)::int as n from leads
        where (${market} = 'all' or city = ${market}) group by status`,
    sql`
      with base as (select * from leads where (${market} = 'all' or city = ${market}))
      select 'source' as dim, coalesce(source, '-') as key, count(*)::int as total,
             count(*) filter (where status <> 'new')::int as worked,
             count(*) filter (where status = 'won')::int  as won,
             count(*) filter (where status = 'lost')::int as lost
      from base group by source
      union all
      select 'service', coalesce(service, '-'), count(*)::int,
             count(*) filter (where status <> 'new')::int,
             count(*) filter (where status = 'won')::int,
             count(*) filter (where status = 'lost')::int
      from base group by service
      union all
      select 'bucket', coalesce(bucket, '-'), count(*)::int,
             count(*) filter (where status <> 'new')::int,
             count(*) filter (where status = 'won')::int,
             count(*) filter (where status = 'lost')::int
      from base group by bucket
    `,
  ]);
  return {
    funnel: funnel as { status: string; n: number }[],
    breakdown: breakdown as Breakdown[],
  };
}

export type Run = {
  id: number;
  job: string;
  city: string | null;
  started_at: string;
  finished_at: string | null;
  signals_new: number | null;
  leads_new: number | null;
  stats: Record<string, number> | null;
  error: string | null;
};

async function getRunsRaw(limit = 25, market = "all") {
  const [runs, ok] = await Promise.all([
    sql`select id, job, city, started_at, finished_at, signals_new, leads_new, stats, error
        from runs where (${market} = 'all' or city = ${market})
        order by started_at desc limit ${limit}`,
    sql`select max(started_at) as at from runs
        where error is null and finished_at is not null
          and (${market} = 'all' or city = ${market})`,
  ]);
  return {
    runs: runs as Run[],
    lastOk: ((ok as { at: string | null }[])[0]?.at ?? null) as string | null,
  };
}

export async function getSettings(): Promise<Settings & { updated_by: string | null; updated_at: string | null }> {
  const rows = (await sql`select key, value, updated_by, updated_at from settings`) as {
    key: string;
    value: unknown;
    updated_by: string | null;
    updated_at: string;
  }[];
  const get = (k: string) => rows.find((r) => r.key === k);
  const newest = rows
    .filter((r) => r.updated_by && !r.updated_by.startsWith("seed:"))
    .toSorted((a, b) => +new Date(b.updated_at) - +new Date(a.updated_at))[0];
  return {
    city: (get("city")?.value as string) ?? DEFAULTS.city,
    categories: (get("categories")?.value as string[]) ?? DEFAULTS.categories,
    thresholds: (get("thresholds")?.value as Settings["thresholds"]) ?? DEFAULTS.thresholds,
    updated_by: newest?.updated_by ?? null,
    updated_at: newest?.updated_at ?? null,
  };
}

/** Markets that actually have leads; the switcher never offers an empty one. */
async function getMarketsRaw(): Promise<string[]> {
  const rows = (await sql`
    select city, count(*)::int as n from leads
    where city is not null group by city order by n desc`) as { city: string }[];
  return rows.map((r) => r.city);
}

export type Role = "admin" | "user";

export type AppUser = {
  email: string;
  role: Role;
  must_change: boolean;
  created_at: string;
  created_by: string | null;
  disabled_at: string | null;
};

/** Includes the hash, so this is only ever called from signIn. */
export async function findUserWithHash(email: string) {
  const [u] = (await sql`
    select email, role, must_change, created_at, created_by, disabled_at, password_hash
    from users where email = ${email}
  `) as (AppUser & { password_hash: string })[];
  return u ?? null;
}

/** Null when missing or disabled: a valid cookie must stop working immediately. */
export async function activeUser(email: string) {
  const [u] = (await sql`
    select email, role, must_change, created_at, created_by, disabled_at
    from users where email = ${email} and disabled_at is null
  `) as AppUser[];
  return u ?? null;
}

export async function listUsers() {
  return (await sql`
    select email, role, must_change, created_at, created_by, disabled_at
    from users order by disabled_at nulls first, role, email
  `) as AppUser[];
}

export async function userCount(): Promise<number> {
  const [r] = (await sql`select count(*)::int as n from users`) as { n: number }[];
  return r.n;
}

/** Active admins, used to stop the last one being demoted or disabled. */
export async function activeAdminCount(): Promise<number> {
  const [r] = (await sql`
    select count(*)::int as n from users where role = 'admin' and disabled_at is null
  `) as { n: number }[];
  return r.n;
}

/* listLeads/getMarkets hit a remote Neon DB (ap-southeast-1) on every page
   load. Cache them so navigation doesn't pay that round trip each time. The
   "leads" tag is busted by lead mutations (see app/actions.ts); the TTL is a
   backstop for crawler-inserted rows that don't go through an action.
   ponytail: market lens is a coarse key, fine at 83 rows. */
export const listLeads = unstable_cache(listLeadsRaw, ["listLeads"], {
  tags: ["leads"],
  revalidate: 30,
});

// Cities change only when the crawler finds a new market — a slow TTL is plenty.
export const getMarkets = unstable_cache(getMarketsRaw, ["getMarkets"], {
  tags: ["leads"],
  revalidate: 300,
});

// Analytics counts derive from lead status, which updateTag("leads") busts on a
// status change, so win rates stay fresh; the TTL is a backstop.
export const analytics = unstable_cache(analyticsRaw, ["analytics"], {
  tags: ["leads"],
  revalidate: 30,
});

// Runs only change when the crawler writes a row (never from a user action), so
// a short TTL is enough and no tag is needed to keep it correct.
export const getRuns = unstable_cache(getRunsRaw, ["getRuns"], {
  tags: ["leads"],
  revalidate: 60,
});
