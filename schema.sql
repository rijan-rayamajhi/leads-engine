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
  rep_email   text,
  status      text,
  notes       text,
  updated_at  timestamptz default now()
);

create index if not exists idx_leads_bucket_status_service on leads (bucket, status, service);
create index if not exists idx_leads_found_at on leads (found_at desc);
