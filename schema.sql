-- Lead Engine schema (Postgres / Neon). Run once: psql "$DATABASE_URL" -f schema.sql

create table if not exists raw_signals (
  id          bigserial primary key,
  source      text not null,              -- 'google_reviews' | 'reddit'
  who         text,                       -- business / poster name
  body        text,                       -- review / post text
  source_url  text unique not null,       -- dedupe key
  location    text,
  posted_at   timestamptz,
  raw         jsonb,
  created_at  timestamptz default now(),
  -- JUDGE results (null until judged):
  judged_at    timestamptz,
  service      text,
  intent       text,          -- actively_seeking | has_problem | vague
  intent_score int,
  summary      text,
  why_contact  text
);

create table if not exists companies (
  id           bigserial primary key,
  name_norm    text unique not null,      -- normalized name for dedupe
  place_id     text,
  phone        text,
  phone_valid  boolean,
  email        text,
  website      text,
  category     text,
  rating       numeric,
  review_count int,
  enriched_at  timestamptz
);

create table if not exists leads (
  id              uuid primary key default gen_random_uuid(),
  company_id      bigint references companies(id),
  name            text,
  phone           text,
  email           text,
  service         text,                   -- website|chatbot|whatsapp_bot|ai_phone|mobile_app|custom_software
  what_they_want  text,
  evidence_quote  text,
  why_contact     text,
  source          text,
  source_url      text,
  intent_score    int,
  bucket          text,                   -- HOT|WARM|QUALIFIED|DROP
  status          text default 'new',     -- new|contacted|replied|meeting|proposal|won|lost
  assigned_to     text,
  found_at        timestamptz default now()
);

create table if not exists outcomes (
  id          bigserial primary key,
  lead_id     uuid references leads(id),
  user_email  text,
  status      text,
  notes       text,
  updated_at  timestamptz default now()
);

create index if not exists idx_leads_bucket_status_service on leads (bucket, status, service);
create index if not exists idx_leads_found_at on leads (found_at desc);

create table if not exists runs (
  id           bigserial primary key,
  job          text not null,              -- 'pipeline' | 'gap'
  city         text,
  started_at   timestamptz default now(),
  finished_at  timestamptz,                -- null = still running, or killed
  signals_new  int,
  leads_new    int,
  stats        jsonb,                      -- per-stage counts; new stages need no migration
  error        text
);

create index if not exists idx_runs_started_at on runs (started_at desc);

-- Crawler settings the dashboard can edit. One row per key; load_config() merges
-- these over config.yaml, so a rep can retarget a crawl without a commit.
create table if not exists settings (
  key        text primary key,           -- 'city' | 'categories' | 'thresholds'
  value      jsonb not null,
  updated_by text,
  updated_at timestamptz default now()
);

-- Market = the city the crawl targeted, NOT the business's address city.
-- (Valley suburbs like Lalitpur and Devanagari spellings would split one market
-- into phantom ones if this were parsed from the address.)
alter table leads     add column if not exists city text;
alter table companies add column if not exists city text;
create index if not exists idx_leads_city on leads (city);

-- rep -> user rename, idempotent so schema.sql stays safe to re-run
do $$ begin
  if exists (select 1 from information_schema.columns
             where table_name = 'outcomes' and column_name = 'rep_email') then
    alter table outcomes rename column rep_email to user_email;
  end if;
end $$;

-- App users. Disabled rather than deleted: outcomes.user_email,
-- leads.assigned_to and settings.updated_by all reference an email as text.
create table if not exists users (
  email         text primary key,
  password_hash text not null,
  role          text not null default 'user',    -- 'admin' | 'user'
  must_change   boolean not null default true,   -- admin-set password, changed on first login
  created_at    timestamptz default now(),
  created_by    text,
  disabled_at   timestamptz
);
