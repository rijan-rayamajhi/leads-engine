# Lead Engine — Technical System Design (v2, self-hosted / Vercel)

Autonomously discover businesses with an *active digital problem*, judge intent,
enrich to contact, verify, prioritize, and serve them to a sales team through a
web dashboard. Deliver **Name + Phone + What they want + Why**, and learn from outcomes.

Cost target: **~$0–5/month** (all free tiers except a few $ of Claude).

---

## 0. High-level architecture

```
┌─ CRAWLER (Python) ─────────────────────┐
│  DISCOVER → JUDGE → ENRICH → VERIFY     │
│  Runs on GitHub Actions cron, every 6h  │   (NOT on Vercel — long job, timeouts)
└──────────────┬──────────────────────────┘
               │ upsert leads
               ▼
┌─ DATABASE — Postgres (Neon) ──┐
│  shared source of truth                 │
└──────────────┬──────────────────────────┘
               │ read leads / write status
               ▼
┌─ DASHBOARD (Next.js on Vercel) ────────┐
│  per-rep login, list/filter/detail,     │
│  status updates → FEEDBACK loop         │
└──────────────────────────────────────────┘
```

Three deployables, one shared DB. Clean seams: swap any layer without touching others.

---

## 1. Stack

| Layer            | Tech                                             | Cost | Why |
|------------------|--------------------------------------------------|------|-----|
| Crawler          | Python 3.12                                       | ~$0–5 | scrapers + APIs + LLM |
| Crawler schedule | **GitHub Actions cron** (`schedule:` every 6h)   | free | no VPS, no ops |
| Database         | **Postgres** — Neon (serverless)                | free tier | serverless-friendly, shared |
| Dashboard        | **Next.js** (App Router, RSC) on **Vercel**      | free tier | fast web app |
| Auth             | **NextAuth** — email magic-link, rep allowlist   | free | per-rep identity for feedback |
| ORM/queries      | `postgres` (porsager) or Prisma                  | free | typed DB access |
| Phone verify     | `phonenumbers` (Python, local)                   | free | no API |
| Email discovery  | website scrape (BeautifulSoup)                    | free | best-effort |
| Reddit           | PRAW (official API)                              | free | intent posts |
| Businesses       | Google Places API                                | $200/mo free credit | reviews + phone |
| Judge            | Claude API (claude-sonnet-5)                     | ~$3–5/mo | intent classifier |

Dropped: Hunter, PDL, Twilio, Slack, Apify, LinkedIn (ToS-grey). Resend parked for future outreach.

---

## 2. Repo layout

```
lead-engine/
├─ crawler/                     # Python pipeline
│  ├─ pipeline.py               # orchestrator: --once / stage flags
│  ├─ config.yaml               # city, categories, services, thresholds
│  ├─ db.py                     # Postgres connection + upserts
│  ├─ sources/
│  │  ├─ places.py              # Google reviews + business harvest
│  │  └─ reddit.py              # PRAW intent posts
│  ├─ judge.py                  # rules + Claude classifier
│  ├─ enrich.py                 # phone (Places) + email (site scrape)
│  ├─ verify.py                 # phonenumbers + fuzzy dedupe
│  └─ requirements.txt
├─ web/                         # Next.js dashboard (Vercel root)
│  ├─ app/
│  │  ├─ page.tsx               # leads list + filters
│  │  ├─ leads/[id]/page.tsx    # lead detail + status
│  │  ├─ api/leads/route.ts     # GET list, PATCH status
│  │  └─ auth/…                 # NextAuth routes
│  ├─ lib/db.ts                 # Postgres queries
│  └─ package.json
├─ schema.sql                   # Postgres tables (shared)
├─ .github/workflows/crawl.yml  # cron every 6h → runs crawler
└─ README.md                    # setup + deploy
```

---

## 3. DISCOVER — source plugins

Each source emits one uniform record:

```python
Signal = {
  "source": "google_reviews" | "reddit",
  "who": str,            # business / poster name
  "text": str,           # review / post body
  "source_url": str,     # UNIQUE (dedupe key)
  "location": str | None,
  "posted_at": datetime,
  "raw": dict,           # rating, subreddit, etc.
}
```

| Source          | Tool               | Notes |
|-----------------|--------------------|-------|
| google_reviews  | Places details+reviews | name+phone+reviews in one shot |
| reddit          | PRAW keyword search | r/smallbusiness, r/startups, service keywords |

Sources run in a thread pool; a failing source never blocks the others.
New signals upserted to `raw_signals` (conflict on `source_url` = skip).

Adding a source later = one new file emitting `Signal`. Nothing downstream changes.

---

## 4. JUDGE — intent scoring

**Pass A — rules (free filter).** Phrase table maps text → candidate service; no match
+ no negative sentiment → dropped before any LLM cost.

```
website:  ["site is down","no website","website broken","can't find online"]
booking:  ["couldn't book","no online booking","never answers"]
chatbot:  ["no reply","slow response","need support bot"]
app:      ["app crashes","no online ordering","need an app"]
```

**Pass B — Claude classifier.** One structured call per survivor:

```json
{ "has_problem": true,
  "service": "website|chatbot|whatsapp_bot|ai_phone|mobile_app|custom_software|none",
  "intent": "actively_seeking|has_problem|vague",
  "summary": "one line: what they want",
  "why_contact": "one line: the pitch angle",
  "score": 0-100 }
```

`intent_score` = LLM score × source_weight × recency_decay (half-life 7d) + recency
bonus (<24h → +10). Weights in `config.yaml`, tuned by FEEDBACK. Output → `judged`.

---

## 5. ENRICH

```
who ─► Places Text Search ─► place_id ─► phone, website, address, rating, category
website ─► fetch homepage/contact ─► mailto: / email regex   (best-effort, free)
```
Missing phone → keep lead; contact = `source_url` (e.g. Reddit thread).
Cached in `companies` (never re-enrich the same business).

---

## 6. VERIFY

- **Phone:** `phonenumbers` → valid + region + line type. Invalid → flag, don't drop.
- **Business real:** Places hit exists + review_count > 0.
- **Dedupe:** `rapidfuzz` on normalized name + phone across sources → merge, keep `sources[]`.
- **Freshness:** older than `freshness_ttl_days` (30) → drop.

Drop only if: no valid phone AND no email AND no usable source contact.

---

## 7. PRIORITIZE

```
HOT       90–100  → top of list, badge
WARM      70–89   → contact today
QUALIFIED 50–69   → nurture
DROP      <50     → stored, not shown
```
Thresholds in `config.yaml`.

---

## 8. DELIVER — the dashboard (Vercel)

Next.js reads `leads` from Postgres. Features for the sales team:

- **List view:** grouped by bucket (HOT/WARM/QUALIFIED), filter by service/status/search.
- **Lead card:** name, phone (click-to-call `tel:`), what_they_want, evidence quote,
  why_contact, source link, score.
- **Status dropdown:** new → contacted → replied → meeting → proposal → won/lost.
  Writes back to `leads.status` + logs to `outcomes` with the rep's identity + timestamp.
- **Assignment (optional):** claim a lead so two reps don't double-call.
- **Auth:** NextAuth email magic-link; only allowlisted rep emails get in.

API routes: `GET /api/leads` (filtered), `PATCH /api/leads/:id` (status/assignment).

---

## 9. FEEDBACK — learning loop

Every status change → `outcomes(lead_id, user_email, status, notes, updated_at)`.

Nightly GitHub Action:
- win-rate per **source**, **service**, **score band**.
- rewrite `config.yaml` source_weights + thresholds toward what converts.
- (later) train logistic model on features → score once ≥ ~50 outcomes.

---

## 10. Database schema (Postgres)

```sql
create table raw_signals (
  id bigserial primary key,
  source text, who text, text text,
  source_url text unique,
  location text, posted_at timestamptz,
  raw jsonb, created_at timestamptz default now()
);

create table companies (
  id bigserial primary key,
  name_norm text unique,
  place_id text, phone text, phone_valid bool,
  email text, website text, category text,
  rating numeric, review_count int,
  enriched_at timestamptz
);

create table leads (
  id uuid primary key default gen_random_uuid(),
  company_id bigint references companies(id),
  name text, phone text, email text,
  service text, what_they_want text, evidence_quote text,
  why_contact text, source text, source_url text,
  intent_score int, bucket text,
  status text default 'new',
  assigned_to text,
  found_at timestamptz default now()
);

create table outcomes (
  id bigserial primary key,
  lead_id uuid references leads(id),
  user_email text, status text, notes text,
  updated_at timestamptz default now()
);

create index on leads (bucket, status, service);
```

---

## 11. config.yaml (crawler)

```yaml
city: "Kathmandu, Nepal"
categories: [restaurant, retail, clinic, salon, hotel]
services: [website, chatbot, whatsapp_bot, ai_phone, mobile_app, custom_software]
thresholds: {hot: 90, warm: 70, qualified: 50}
source_weights: {reddit: 0.9, google_reviews: 1.0}
freshness_ttl_days: 30
env:
  DATABASE_URL:       ENV
  GOOGLE_PLACES_KEY:  ENV
  ANTHROPIC_API_KEY:  ENV
  REDDIT_CLIENT_ID:   ENV
  REDDIT_CLIENT_SECRET: ENV
```

---

## 12. Scheduling — GitHub Actions

```yaml
# .github/workflows/crawl.yml
name: crawl
on:
  schedule: [{cron: "0 */6 * * *"}]   # every 6h
  workflow_dispatch: {}
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install -r crawler/requirements.txt
      - run: python crawler/pipeline.py --once
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          GOOGLE_PLACES_KEY: ${{ secrets.GOOGLE_PLACES_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          REDDIT_CLIENT_ID: ${{ secrets.REDDIT_CLIENT_ID }}
          REDDIT_CLIENT_SECRET: ${{ secrets.REDDIT_CLIENT_SECRET }}
```

---

## 13. Deploy

1. **DB:** create Neon project → run `schema.sql` → copy `DATABASE_URL`.
2. **Crawler:** push repo → add secrets in GitHub → Actions runs on cron (or manual dispatch).
3. **Dashboard:** import repo to Vercel, root = `web/`, set `DATABASE_URL` + NextAuth vars →
   deploy → share the URL + add rep emails to the allowlist.

---

## 14. Compliance (confirm per country)

- B2B public business numbers: calling to offer service generally OK; verify locally.
- Email outreach (future, via Resend): honor GDPR/CAN-SPAM — opt-out, identity.
- Prefer official APIs (Places, Reddit) over ToS-grey scraping. LinkedIn excluded.
- Retention: purge DROP leads after 30d.

---

## 15. Cost

| Item | Cost |
|------|------|
| Google Places | $0 (inside $200/mo credit) |
| Claude Judge | ~$3–5/mo |
| Neon / Vercel / GitHub Actions | free tier |
| **Total** | **~$0–5/month** |

---

## 16. Build order

1. `schema.sql` + Neon + `crawler/db.py`
2. `sources/places.py` (first real data)
3. `judge.py` (rules + Claude)
4. `enrich.py` + `verify.py`
5. `pipeline.py --once` end-to-end → rows in Postgres
6. Next.js dashboard: list + filter + detail + status
7. NextAuth rep login
8. `sources/reddit.py`
9. GitHub Actions cron + nightly FEEDBACK retune
```
