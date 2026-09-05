# Lead Engine — Implementation Plan

Build order for the v2 design (Neon + Vercel + GitHub Actions crawler).
Each phase is shippable on its own. Check boxes as you go.

Legend: 🔴 blocker (needs you) · ⚙️ code · ☁️ infra · ✅ verify

---

## Phase 0 — Prerequisites (you provide)

- [ ] 🔴 Confirm **city/area** for `config.yaml` (e.g. "Kathmandu, Nepal")
- [ ] 🔴 Confirm **services sold** (AI chatbot, WhatsApp bot, AI phone, website, mobile app, custom software)
- [ ] 🔴 Create **Google Cloud** project → enable **Places API** → get `GOOGLE_PLACES_KEY`
- [ ] 🔴 Get **Anthropic API key** (`ANTHROPIC_API_KEY`)
- [ ] 🔴 Create **Reddit app** (script type) → `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET`
- [ ] 🔴 Create **Neon** project → copy `DATABASE_URL`
- [ ] 🔴 Create **Resend** account → `RESEND_API_KEY` (for login emails)
- [ ] 🔴 GitHub repo created + Vercel account linked

---

## Phase 1 — Foundation (DB + config)

- [ ] ⚙️ Scaffold repo layout (`crawler/`, `web/`, `schema.sql`, `.github/`)
- [ ] ⚙️ Write `schema.sql` (raw_signals, companies, leads, outcomes + indexes)
- [ ] ☁️ Run `schema.sql` on Neon
- [ ] ⚙️ `crawler/config.yaml` (city, categories, services, thresholds, weights, TTL)
- [ ] ⚙️ `crawler/db.py` — Postgres connect + upsert helpers
- [ ] ⚙️ `crawler/requirements.txt` (psycopg, anthropic, praw, phonenumbers, rapidfuzz, beautifulsoup4, requests, pyyaml)
- [ ] ✅ `python -c "import db; db.ping()"` connects to Neon

---

## Phase 2 — DISCOVER (Google reviews first)

- [ ] ⚙️ `sources/places.py` — Text Search by city+category → business list
- [ ] ⚙️ Pull Place Details + reviews → emit `Signal[]`
- [ ] ⚙️ Upsert to `raw_signals` (skip on duplicate `source_url`)
- [ ] ✅ Run once → real rows land in `raw_signals`
- [ ] ✅ Self-check: dedupe works (re-run adds 0 new rows)

---

## Phase 3 — JUDGE (rules + Claude)

- [ ] ⚙️ `judge.py` Pass A — phrase-rule filter → candidate service / drop
- [ ] ⚙️ Pass B — Claude structured call → {has_problem, service, intent, summary, why_contact, score}
- [ ] ⚙️ Compute `intent_score` (LLM × source_weight × recency_decay + bonus)
- [ ] ⚙️ Write to `judged`
- [ ] ✅ Self-check: known "site is down" review scores high; irrelevant review dropped
- [ ] ✅ Cost check: only rule-survivors hit the LLM

---

## Phase 4 — ENRICH + VERIFY

- [ ] ⚙️ `enrich.py` — phone/website/rating from Places; email via site scrape
- [ ] ⚙️ Cache in `companies` (no re-enrich)
- [ ] ⚙️ `verify.py` — `phonenumbers` validate; business-real check
- [ ] ⚙️ Fuzzy dedupe (`rapidfuzz`) across sources; freshness TTL drop
- [ ] ✅ Self-check: bad phone flagged, duplicate business merged

---

## Phase 5 — Pipeline end-to-end

- [ ] ⚙️ `pipeline.py --once` runs DISCOVER→JUDGE→ENRICH→VERIFY→PRIORITIZE
- [ ] ⚙️ Write final `leads` rows with bucket + status='new'
- [ ] ✅ Full run produces callable leads in Neon (name, phone, what_they_want, why)
- [ ] ✅ Second run adds only new leads (idempotent)

---

## Phase 6 — Dashboard (Next.js on Vercel)

- [ ] ⚙️ Scaffold `web/` Next.js (App Router) + `lib/db.ts` (Neon)
- [ ] ⚙️ `app/page.tsx` — leads grouped by bucket + filter (service/status/search)
- [ ] ⚙️ `app/leads/[id]/page.tsx` — detail: phone `tel:` link, evidence, why_contact, source
- [ ] ⚙️ `app/api/leads/route.ts` — GET (filtered) + PATCH (status/assignment)
- [ ] ⚙️ Status dropdown → writes `leads.status` + `outcomes`
- [ ] ⚙️ Optional: lead assignment (claim)
- [ ] ☁️ Deploy to Vercel (root `web/`, set `DATABASE_URL`)
- [ ] ✅ Sales-eye check: open link, filter HOT, change a status, refresh persists

---

## Phase 7 — Auth (per-rep login)

- [ ] ⚙️ NextAuth email magic-link via **Resend**
- [ ] ⚙️ Rep email allowlist (only approved emails get in)
- [ ] ⚙️ Record `rep_email` on every status change
- [ ] ☁️ Set NextAuth + Resend env vars on Vercel
- [ ] ✅ Non-allowlisted email is rejected; allowlisted rep logs in + acts

---

## Phase 8 — Reddit source

- [ ] ⚙️ `sources/reddit.py` — PRAW keyword search over target subreddits
- [ ] ⚙️ Emit `Signal[]` into the same pipeline
- [ ] ✅ Reddit intent posts appear as leads alongside reviews

---

## Phase 9 — Automation + Feedback loop

- [ ] ⚙️ `.github/workflows/crawl.yml` — cron `0 */6 * * *` + manual dispatch
- [ ] ☁️ Add all secrets to GitHub Actions
- [ ] ✅ Scheduled run populates new leads automatically
- [ ] ⚙️ Nightly job: win-rate per source/service/score-band → retune `config.yaml`
- [ ] ✅ Feedback numbers move after status updates
- [ ] ⏳ Later: train scoring model once ≥50 outcomes exist

---

## Phase 10 — Hardening + handoff

- [ ] ⚙️ `README.md` — setup, keys, deploy, run-once, troubleshooting
- [ ] ⚙️ Error handling: source failure isolated, API ret/backoff
- [ ] ⚙️ Retention: purge DROP leads > 30d
- [ ] 🔴 Compliance sign-off for your country (calling/emailing rules)
- [ ] ✅ Give sales team the URL + short how-to

---

## Deferred (only when it hurts — YAGNI)

- Email discovery via Hunter/PDL (paid) — start with free site-scrape
- Outreach sequences via Resend (send stage)
- Job-board + LinkedIn sources
- Twilio phone line-type, Slack alerts
- Analytics dashboard / KPI charts

---

## Milestone summary

| Milestone | Phases | Outcome |
|-----------|--------|---------|
| **M1 — Crawler works** | 1–5 | real leads in Neon |
| **M2 — Team can use it** | 6–7 | dashboard + login live on Vercel |
| **M3 — Runs itself** | 8–9 | auto-refresh + learning loop |
| **M4 — Production** | 10 | documented, compliant, handed off |
