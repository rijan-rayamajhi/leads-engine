"""JUDGE: score raw_signals for digital-service intent.

Pass A (free): phrase rules drop obvious non-leads before any LLM cost.
Pass B: OpenRouter (free model) classifies survivors -> service, intent, summary, why_contact, score.
Final intent_score = LLM score * source_weight * recency_decay (+ recency bonus).
"""
import os, sys, json, time, pathlib, requests
from datetime import datetime, timezone

# OpenRouter (OpenAI-compatible). Primary + fallbacks: if one free pool is
# rate-limited upstream, OpenRouter routes to the next automatically.
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = [  # OpenRouter caps the fallback array at 3
    "nvidia/nemotron-3-super-120b-a12b:free",
    "minimax/minimax-m3:free",
    "z-ai/glm-5.2:free",
]

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402

# Pass A: a rule hit means "possible problem" -> send to LLM. No hit -> drop.
RULE_PHRASES = [
    # website / digital presence
    "no website", "site is down", "website down", "website broken", "can't find online",
    "cant find online", "not on google", "outdated website", "slow website",
    # booking / ordering / chatbot / support
    "couldn't book", "cant book", "no online booking", "no online order",
    "can't order online", "never answers", "no reply", "didn't respond", "slow response",
    "hard to reach", "no response", "phone not working", "number not working",
    # app / software
    "app crashes", "app doesn't work", "need an app", "no app",
    # generic pain
    "unprofessional", "looks old", "hard to use", "confusing website", "no confirmation",
]

PROMPT = """You are qualifying a business lead for a digital-services agency that sells:
website, chatbot, whatsapp_bot, ai_phone, mobile_app, custom_software.

Below is a public review or post about/by a business. Decide if it reveals a DIGITAL
problem the agency could fix, and how strong the buying intent is.

Return ONLY compact JSON, no prose:
{"has_problem": bool,
 "service": one of website|chatbot|whatsapp_bot|ai_phone|mobile_app|custom_software|none,
 "intent": one of actively_seeking|has_problem|vague,
 "summary": "<=12 words: what they need",
 "why_contact": "<=15 words: the pitch angle",
 "score": 0-100}

Scoring: 90-100 explicitly seeking a solution; 60-89 clear active problem; 30-59 weak
signal; <30 no real digital need (praise, unrelated complaint). If has_problem is false,
service=none and score<30.
"""

INTENT_MULT = {"actively_seeking": 1.0, "has_problem": 0.85, "vague": 0.5}


def passes_rules(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in RULE_PHRASES)


# Per-source half-life: fresh intent (reddit/jobs) decays fast; a review problem
# from months ago is still a valid lead, so reviews decay slowly.
HALF_LIFE = {"google_reviews": 120.0, "reddit": 7.0, "job_board": 5.0}


def recency_decay(posted_at, source="google_reviews") -> float:
    """1.0 for fresh, halves every source half-life. Unknown date -> 0.7."""
    hl = HALF_LIFE.get(source, 30.0)
    if not posted_at:
        return 0.7
    if isinstance(posted_at, str):
        try:
            posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        except ValueError:
            return 0.7
    age_days = (datetime.now(timezone.utc) - posted_at).total_seconds() / 86400
    return 0.5 ** (max(age_days, 0) / hl)


def final_score(llm_score, intent, source_weight, posted_at, source="google_reviews") -> int:
    decay = recency_decay(posted_at, source)
    base = llm_score * INTENT_MULT.get(intent, 0.5) * source_weight * decay
    bonus = 10 if decay > 0.9 else 0  # very fresh
    return max(0, min(100, round(base + bonus)))


def classify(key, sig) -> dict:
    content = (PROMPT + f"\nSOURCE: {sig['source']}\nBUSINESS: {sig.get('who','')}\n"
               f"TEXT: {sig.get('text','')}")
    body = {"models": MODELS, "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": content}]}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(4):
        r = requests.post(OPENROUTER_URL, headers=headers, json=body, timeout=45)
        if r.status_code == 429:  # all free pools busy -> back off and retry
            time.sleep(6 * (attempt + 1))
            continue
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        start, end = text.find("{"), text.rfind("}")  # be robust to stray prose
        return json.loads(text[start:end + 1])
    r.raise_for_status()  # exhausted retries


def run(limit=None):
    load_env()
    cfg = load_config()
    key = os.environ["OPENROUTER_API_KEY"]
    weights = cfg["source_weights"]

    # 1. Read rows + batch-drop rule failures (short DB session).
    with db.conn() as c:
        q = "select id, source, who, body, posted_at from raw_signals where judged_at is null"
        rows = c.execute(q + (f" limit {int(limit)}" if limit else "")).fetchall()
        # Rule filter only applies to reviews (complaint language). Other sources
        # (reddit, jobs) are pre-filtered by their search -> straight to LLM.
        drop_ids = [sid for sid, src, _, body, _ in rows
                    if src == "google_reviews" and not passes_rules(body)]
        if drop_ids:
            c.execute(
                "update raw_signals set judged_at=now(), intent_score=0, "
                "service='none', intent='vague' where id = any(%s)", (drop_ids,))
    survivors = [r for r in rows if r[0] not in set(drop_ids)]
    print(f"judging {len(rows)}: {len(drop_ids)} dropped by rules, {len(survivors)} -> LLM")

    # 2. Slow LLM calls with NO DB connection held (network-drop safe).
    updates = []
    for i, (sid, source, who, body, posted_at) in enumerate(survivors):
        if i:
            time.sleep(4)  # OpenRouter free ~20 req/min
        try:
            r = classify(key, {"source": source, "who": who, "text": body})
        except Exception as e:  # ponytail: skip a bad row, don't kill the run
            print(f"  classify failed id={sid}: {e}", file=sys.stderr)
            continue
        score = final_score(int(r.get("score", 0)), r.get("intent", "vague"),
                            weights.get(source, 1.0), posted_at, source)
        updates.append((r.get("service"), r.get("intent"), score,
                        r.get("summary"), r.get("why_contact"), sid))

    # 3. Write results in one short DB session.
    with db.conn() as c:
        for u in updates:
            c.execute(
                "update raw_signals set judged_at=now(), service=%s, intent=%s, "
                "intent_score=%s, summary=%s, why_contact=%s where id=%s", u)
    print(f"  {len(updates)} scored by LLM")


def _selftest():
    assert passes_rules("their website is down for a week")
    assert not passes_rules("great food and lovely staff")
    assert recency_decay(None) == 0.7
    assert final_score(100, "actively_seeking", 1.0, None) <= 100
    assert final_score(0, "vague", 1.0, None) == 0
    hi = final_score(90, "actively_seeking", 1.0, datetime.now(timezone.utc))
    lo = final_score(90, "vague", 0.9, None)
    assert hi > lo
    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        lim = None
        if "--limit" in sys.argv:
            lim = sys.argv[sys.argv.index("--limit") + 1]
        run(lim)
