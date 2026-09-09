# Lead Engine — Technical System Design (v3, self-hosted / Vercel)

> v3 describes what is deployed. Reddit, Claude, NextAuth and the REST API routes
> from v2 were all dropped or replaced; see §17 for what changed and why.

Autonomously discover businesses with an *active digital problem*, judge intent,
enrich to contact, verify, prioritize, and serve them to a sales team through a
web dashboard. Deliver **Name + Phone + What they want + Why**, and learn from outcomes.

Cost target: **~$0/month** (Places inside its free credit, judge on a free tier).

---

## 0. High-level architecture

```
┌─ CRAWLER (Python) ─────────────────────┐
│  pipeline.py: DISCOVER → JUDGE →        │
│               ENRICH → VERIFY → DELIVER │
│  website_leads.py: DISCOVER→DIAGNOSE→   │  (no LLM, the defect is a fact)
│                    SCORE → DELIVER      │
│  Runs on GitHub Actions cron, every 6h  │  (NOT on Vercel — long job, timeouts)
└──────────────┬──────────────────────────┘
               │ upsert leads
               ▼
┌─ DATABASE — Postgres (Neon) ──┐
│  shared source of truth                 │
└──────────────┬──────────────────────────┘
               │ read leads / write status
               ▼
┌─ DASHBOARD (Next.js on Vercel) ────────┐
│  login + roles, board/detail/analytics, │
│  status + notes → FEEDBACK loop         │
└──────────────────────────────────────────┘
```

Three deployables, one shared DB. Clean seams: swap any layer without touching others.

---

## 1. Stack

| Layer            | Tech                                             | Cost | Why |
|------------------|--------------------------------------------------|------|-----|
| Crawler          | Python 3.12                                       | $0 | scrapers + APIs + LLM |
| Crawler schedule | **GitHub Actions cron** (`schedule:` every 6h)   | free | no VPS, no ops |
| Database         | **Postgres** — Neon (serverless)                | free tier | serverless-friendly, shared |
| Dashboard        | **Next.js** (App Router, RSC) on **Vercel**      | free tier | fast web app |
| Auth             | **custom**: HS256 JWT cookie (`jose`) + scrypt   | free | no dependency, no session table |
| ORM/queries      | `@neondatabase/serverless` tagged templates      | free | parameterized, edge-friendly |
| Phone verify     | `phonenumbers` (Python, local)                   | free | no API |
| Email discovery  | homepage regex scrape (`requests` + `re`)         | free | best-effort |
| Businesses       | Google Places API (New)                          | $200/mo free credit | reviews + phone in one call |
| Judge            | **OpenRouter** free-tier models, 3-deep fallback | $0 | intent classifier |

Dropped: Reddit/PRAW, Claude API, NextAuth, Resend, Hunter, PDL, Twilio, Slack,
Apify, LinkedIn (ToS-grey), BeautifulSoup (a regex covers the one field we want).

**Auth, concretely.** The cookie carries the email and nothing else; the role is
re-read from `users` on every request (`lib/auth.ts`), so disabling or demoting
someone takes effect on their next page load instead of at token expiry.
Passwords are stdlib scrypt with the cost parameters stored inside the hash
string, so raising them later still verifies every existing password. There is a
first-run bootstrap: while `users` is empty, `USERS={"you@co":"pw"}` from env is
accepted once, seeded as an admin with `must_change`, and ignored forever after.

---

## 2. Repo layout

```
lead-engine/
├─ crawler/                     # Python pipeline
│  ├─ pipeline.py               # orchestrator: --once / --city / --skip
│  ├─ website_leads.py          # main factory: broken/missing sites, no LLM
│  ├─ scoring.py                # the one score + the one bucket rule
│  ├─ config.yaml               # city, categories, services, thresholds, phone_region
│  ├─ common.py                 # .env loader, config overlays, norm_name
│  ├─ db.py                     # Postgres connection + upserts + run rows
│  ├─ sources/places.py         # Google reviews + business harvest
│  ├─ judge.py                  # rules + OpenRouter classifier
│  ├─ pitch.py                  # AI call opener from verified facts
│  ├─ llm.py                    # shared OpenRouter client (judge + pitch)
│  ├─ sitecheck.py              # website health -> verifiable defects
│  ├─ enrich.py                 # phone (Places) + email (site scrape)
│  ├─ verify.py                 # phonenumbers + fuzzy dedupe
│  ├─ feedback.py               # outcomes → weights.json overlay
│  ├─ migrate_name_norm.py      # one-off: renormalize + merge company keys
│  └─ requirements.txt
├─ web/                         # Next.js dashboard (Vercel root)
│  ├─ app/
│  │  ├─ (app)/page.tsx             # board: leads + filters + pagination
│  │  ├─ (app)/leads/[id]/page.tsx  # detail: evidence, activity, status flow
│  │  ├─ (app)/analytics/page.tsx   # win rates per source/service/bucket
│  │  ├─ (app)/runs/page.tsx        # crawler health + recent runs
│  │  ├─ (app)/settings/page.tsx    # crawler config + team management
│  │  ├─ login/ · password/         # sign in, forced password change
│  │  └─ actions.ts                 # every mutation (server actions, no REST)
│  ├─ lib/                      # db, auth, password, leads, settings, market
│  └─ package.json
├─ schema.sql                   # Postgres tables (shared, idempotent)
├─ .github/workflows/crawl.yml     # cron every 6h → pipeline.py + website_leads.py
└─ .github/workflows/feedback.yml  # nightly → feedback.py
```

**No REST API.** Every mutation is a Next.js server action in `app/actions.ts`,
so there is no `/api/leads` route to keep in sync with the UI and no second
place to re-check authorization.

---

## 3. DISCOVER — source plugins

Each source emits one uniform record:

```python
Signal = {
  "source": "google_reviews",
  "who": str,            # business name
  "text": str,           # review body
  "source_url": str,     # UNIQUE (dedupe key)
  "location": str | None,
  "posted_at": datetime,
  "raw": dict,           # place_id, phone, website, rating, review_count
}
```

| Source          | Tool               | Notes |
|-----------------|--------------------|-------|
| google_reviews  | Places Text Search + reviews | name+phone+rating+reviews in one shot |

Search is paged (`pageToken`, up to `MAX_PAGES`). A single unpaged call returns
about 20 businesses, which capped every category — and so the whole pipeline —
regardless of how large the city was.

Reddit was removed: PRAW needs per-user credentials, the subreddits it searched
are mostly US-based, and none of its posts named a local business we could call.
Business phone/website/rating ride along in `raw_signals.raw`, so ENRICH and
`website_leads.py` reuse them without a second billed call.

A failing category is caught and skipped; one bad search never kills the run.
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

**Pass B — OpenRouter classifier.** One structured call per survivor, sent to a
three-model free-tier fallback list so an upstream rate-limit routes onward
instead of failing. 429s back off and retry; a row that still fails is skipped,
not fatal.

```json
{ "has_problem": true,
  "service": "website|chatbot|whatsapp_bot|ai_phone|mobile_app|custom_software|none",
  "intent": "actively_seeking|has_problem|vague",
  "summary": "one line: what they want",
  "why_contact": "one line: the pitch angle",
  "score": 0-100 }
```

`intent_score` = LLM score × intent_multiplier × source_weight × recency_decay
+ recency bonus (decay > 0.9 → +10). Weights in `config.yaml`, tuned by FEEDBACK.
Results are written back onto the `raw_signals` row (there is no separate
`judged` table).

Google reviews are listed in `NO_DECAY` and are not discounted for age at all.
A review saying "nobody ever answers the phone" describes a standing operational
fact, not a fading event. Decay was written for fresh forum intent and, applied
multiplicatively to year-old reviews, put a perfect score at 10 against a
threshold of 50 — which is why this path produced zero leads from 1,524 signals.
A genuinely perishable source gets a half-life in `HALF_LIFE` instead.

The judge holds no DB connection across the LLM loop: it reads rows, closes,
calls the model for each survivor, then reopens to write. A network drop mid-run
costs the batch, never a stuck transaction.

---

## 4b. GAP — leads without an LLM

`website_leads.py` is the second lead factory and, today, the only one producing output.
It rereads the harvested businesses in `raw_signals.raw` and files a lead wherever
the gap is a checkable fact rather than a judgement call:

| Finding | Base | How it is verified |
|---------|------|--------------------|
| site does not load (survives a retry) | 72 | connection error |
| domain parked or for sale | 70 | marker text on the page |
| server error | 68 | HTTP 5xx |
| listing link 404s | 66 | HTTP 404 on the URL Google publishes |
| broken TLS certificate | 64 | SSL error |
| no website at all | 70 | Places has no `websiteUri` |
| serves plain HTTP | 56 | final URL is not https |
| homepage essentially blank | 52 | body under 1500 bytes |
| social page only | 60 | facebook / instagram / linktree |

**A healthy site means no lead.** That check is what makes the other 80% of the
harvest addressable: before it, 251 of 306 businesses were skipped purely
because a URL field was non-empty, and 24 of them had a real, verifiable defect.

Verdicts are cached in `site_checks`, keyed by URL, for `site_check_ttl_days`
(14). Keyed by URL rather than by company because a verdict is a property of a
URL, and because a HEALTHY business never gets a company row at all — caching on
`companies` cached 6 of 213 and refetched the rest every six hours.

**Leads are re-checked, and retired.** `recheck_open_leads` re-runs `sitecheck`
on the sites behind untouched leads older than `lead_recheck_ttl_days` (7). If
the defect is gone the lead gets `stale_at` and leaves the board: opening a call
with a claim the prospect can disprove in ten seconds is worse than silence.

**Precision over volume.** Two signals were tested and deliberately dropped: an
HTTP 403 is bot-blocking rather than a defect, and a missing viewport meta
misfired on the one JS-rendered site it flagged. `sitecheck` sends a real browser
UA, because a bespoke agent string gets blocked by WAFs and then misread as a
dead site. "Unreachable" survives a retry before it is asserted. Measured on 237
Bangalore businesses, the surviving signals corroborated 24/24 on re-check.

Score comes from `scoring.lead_score`: the defect's base, plus continuous,
log-scaled terms for review count, rating and review freshness, then scaled by
the category weight the feedback loop has learned. Every term is continuous on
purpose — the previous version capped the review term at 200 reviews and made
the rating a cliff at 4.0, which put 33 of 78 leads at exactly 100 and left a
rep working 47 HOT leads in effectively random order. A thriving 4.5★ place with 300 reviews and a dead
site is a hotter call than a quiet one. Every gap lead has a phone, or it is
skipped, and its evidence line states the fact a rep can verify in one look.
Businesses Places reports as closed are dropped before a request is spent.

---

## 4c. PITCH — the one place a model earns its keep

`pitch.py` turns a lead's verified facts into the sentence a rep says out loud.
Before it, 40 of 71 leads carried the byte-identical line "No website, so
customers searching online never find them", and each lead's real hook (4.5
stars, 517 reviews, a boutique in Bangalore) sat unused in the row.

**The model never states a fact.** Every number and defect is passed in, already
verified by `sitecheck` or Places, and the prompt forbids adding others. A
returned pitch is then scanned for numbers that are not in the lead's facts, and
one that invents a figure is *discarded* rather than corrected: the rule-written
`why_contact` is already accurate, so rejecting costs polish, not truth. A
hallucinated review count is the single output that can make a rep sound like a
liar on a live call.

The stage runs last and its failure is caught, so a model outage costs nice copy
and never a lead. This is the shape every future use of AI here should take:
**AI enriches leads, it never decides they exist.**

---

## 5. ENRICH

```
who ─► Places Text Search ─► place_id ─► phone, website, address, rating, category
website ─► fetch homepage/contact ─► mailto: / email regex   (best-effort, free)
```
Missing phone → keep lead; contact = `source_url` (its Google Maps listing).
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
  Writes back to `leads.status` + logs to `outcomes` with the user's identity + timestamp.
- **Assignment:** claim a lead so two people don't double-call. Claims release
  automatically when an account is disabled.
- **Notes:** an `outcomes` row with no status, so history accrues without moving the lead.
- **Market lens:** a cookie, not a URL param, scoping the board, analytics and
  runs to one crawled city. Only markets that actually hold leads are offered.
- **Analytics:** win rate per source / service / bucket. Below 5 decided outcomes
  it says how many more are needed rather than printing a fake 0% or 100%.
- **Crawler runs:** every invocation writes a `runs` row, so "cron never fired"
  reads differently from "cron fired and crashed". Flags staleness past 1.5 cycles.
- **Settings (admin):** city, categories and thresholds, stored in the DB and
  merged over `config.yaml`, so retargeting a crawl needs no commit or redeploy.
  Changing thresholds re-buckets existing leads, since a bucket is only a view
  of a score. Also holds team management: add, disable, set password, change role.
- **Auth:** email + password, admin-provisioned, forced change on first login.
  Two independent guards stop the last active admin being demoted or disabled.

---

## 9. FEEDBACK — learning loop

Every status change → `outcomes(lead_id, user_email, status, notes, updated_at)`.

Nightly GitHub Action computes win rate per **source, service and category**, and
writes `weights.json`, an overlay merged over `config.yaml`. A slice with fewer
than 5 decided leads keeps the neutral 1.0, so a small sample cannot move the
dial. Weights clamp to 0.5–1.5 so no slice can dominate or vanish.

Grouping by three dimensions rather than source alone is what makes the loop
able to learn at all: with one live source, a source-only weight is structurally
incapable of saying anything. "Clinics convert at 40%, gyms at 5%" is actionable.

`judge.py` applies source × service; `website_leads.py` applies category. (Later) train a
model on features once ≥ ~50 outcomes exist; the overlay interface won't change.

> **Precondition.** `outcomes` is empty: nobody has called a lead yet, so the
> loop has no ground truth and every weight is neutral. Roughly 20 decided leads
> is the point where it starts to say anything.

---

## 10. Database schema (Postgres)

`schema.sql` is the source of truth and is safe to re-run: every statement is
`if not exists` or a guarded `do $$`. Beyond the four tables below it also holds
`runs` (crawl history), `settings` (dashboard-editable crawler config), `users`
(accounts), and the `city` / `company_id` columns added later.

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
source_weights: {google_reviews: 1.0}
freshness_ttl_days: 30
phone_region: NP        # ISO region for numbers with no +country code; must match `city`
```

Three layers, last one wins: `config.yaml` → `weights.json` (written nightly by
`feedback.py`) → the `settings` table (edited in the dashboard). `load_config()`
memoises the result, so one crawl sees one consistent config even if someone
saves settings mid-run, and a missing DB degrades to the file rather than failing.

Secrets are env-only, never in the file: `DATABASE_URL`, `GOOGLE_PLACES_KEY`,
`OPENROUTER_API_KEY`, plus `AUTH_SECRET` and `USERS` for the dashboard.

---

## 12. Scheduling — GitHub Actions

Two workflows, both with `workflow_dispatch` for manual runs:

| Workflow | Cron | Does |
|----------|------|------|
| `crawl.yml` | `0 */6 * * *` | `pipeline.py --once`, then `website_leads.py`, then `pitch.py`. Pitch runs last, once, because it writes an opener for every lead that lacks one and so must see both factories' output. Accepts a `city` input to retarget one run. `concurrency: crawl` so two never overlap. |
| `feedback.yml` | `0 2 * * *` | `feedback.py`, then commits `weights.json` if it changed. |

Secrets: `DATABASE_URL`, `GOOGLE_PLACES_KEY`, `OPENROUTER_API_KEY`.

`--city` sets `CRAWL_CITY`, which both `places.py` and `website_leads.py` read, so a
retargeted run tags its leads with the market it actually scanned.

---

## 13. Deploy

1. **DB:** create Neon project → run `schema.sql` → copy `DATABASE_URL`.
2. **Crawler:** push repo → add secrets in GitHub → Actions runs on cron (or manual dispatch).
3. **Dashboard:** import repo to Vercel, root = `web/`, set `DATABASE_URL`,
   `AUTH_SECRET` (`openssl rand -hex 32`) and `USERS` → deploy → sign in as the
   bootstrap admin, change the password, then add the team under Settings → Team.

---

## 14. Compliance (confirm per country)

- B2B public business numbers: calling to offer service generally OK; verify locally.
- Email outreach (not built): would need GDPR/CAN-SPAM opt-out + identity.
- Prefer official APIs (Places) over ToS-grey scraping. LinkedIn excluded.
- Retention: purge DROP leads after 30d.

---

## 15. Cost

| Item | Cost |
|------|------|
| Google Places | $0 (inside $200/mo credit) |
| Judge (OpenRouter free tier) | $0 |
| Neon / Vercel / GitHub Actions | free tier |
| **Total** | **~$0/month** |

---

## 16. Build order (done)

1. `schema.sql` + Neon + `crawler/db.py`
2. `sources/places.py` (first real data)
3. `judge.py` (rules + LLM)
4. `enrich.py` + `verify.py`
5. `pipeline.py --once` end-to-end → rows in Postgres
6. `website_leads.py` (the factory that actually produces leads)
7. Next.js dashboard: board, detail, analytics, runs, settings
8. Email/password auth, roles, team management
9. GitHub Actions cron + nightly feedback retune

Not built: retention purge of DROP leads older than 30d; a trained scoring model
to replace the linear win-rate heuristic; outreach/send.

**On the AI.** `pitch.py` is the one load-bearing use: it writes the call opener
from facts the rules already verified. The judge, by contrast, has produced
zero leads: the Pass A keyword list rejects 98% of signals before a model sees
one (1,496 of 1,524), and of the 28 that reached it, none cleared the threshold.
Every lead this system has ever produced came from a deterministic rule. The
honest read is that AI is not currently load-bearing here; the near-term use is
writing the pitch from evidence already verified, not deciding whether a lead
exists.

---

## 17. What changed from v2

| v2 said | Reality | Why |
|---------|---------|-----|
| Reddit via PRAW | removed | per-user creds, US-centric subs, no callable local businesses |
| Claude API judge | OpenRouter free models | the judge is a cheap classifier; free tier covers it |
| NextAuth magic-link + Resend | email/password, custom JWT + scrypt | no mail provider to own, and admin-provisioned accounts suit a small team |
| `GET/PATCH /api/leads` | server actions in `app/actions.ts` | one place to authorize, nothing to keep in sync |
| `judged` table | columns on `raw_signals` | one row per signal, no join |
| one lead factory | two (`pipeline.py`, `website_leads.py`) | verifiable gaps beat LLM judgement on aged reviews |
| single city | markets, DB-backed settings | retarget without a commit; leads keep the city they were found in |
| gap = missing `websiteUri` | website health check (`sitecheck.py`) | 82% of the harvest was skipped for having a non-empty URL field |
| weights per source | per source, service and category | one live source cannot teach a source-only weight anything |

Added since: `runs` (crawl observability), `settings` (editable config), `users`
(accounts + roles), `city` (market scoping), `feedback.py` (weight retuning).
