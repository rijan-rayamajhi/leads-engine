"""JUDGE: score raw_signals for digital-service intent.

Pass A (free): phrase rules drop obvious non-leads before any LLM cost.
Pass B: OpenRouter (free model) classifies survivors -> service, intent, summary, why_contact, score.
Final intent_score = LLM score * source_weight * recency_decay (+ recency bonus).
"""
import sys, time, pathlib
from datetime import datetime, UTC

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config
import db, llm

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


# P7. Decay was written for fresh forum intent and then applied to Google
# reviews, which are routinely a year old. Multiplied in, it made a perfect
# score on a 12-month-old review land at 10 against a threshold of 50, so the
# judge produced zero leads from 1,524 signals.
#
# A review that says "nobody ever answers the phone" describes a STANDING
# operational fact, not a fading event. Sources listed here are not decayed at
# all; a source whose signals really are perishable gets a half-life instead.
NO_DECAY = {"google_reviews"}
HALF_LIFE = {}          # source -> days; absent and not in NO_DECAY -> 30d
DEFAULT_HALF_LIFE = 30.0


def recency_decay(posted_at, source="google_reviews") -> float:
    """1.0 for fresh, halves every source half-life. Unknown date -> 0.7.
    Sources in NO_DECAY are never discounted for age."""
    if source in NO_DECAY:
        return 1.0
    hl = HALF_LIFE.get(source, DEFAULT_HALF_LIFE)
    if not posted_at:
        return 0.7
    if isinstance(posted_at, str):
        try:
            posted_at = datetime.fromisoformat(posted_at)   # handles a trailing Z
        except ValueError:
            return 0.7
    age_days = (datetime.now(UTC) - posted_at).total_seconds() / 86400
    return 0.5 ** (max(age_days, 0) / hl)


def final_score(llm_score, intent, source_weight, posted_at, source="google_reviews",
                service_weight=1.0) -> int:
    """service_weight comes from the feedback loop: a service that keeps closing
    scores its future leads higher, one that never closes scores them lower."""
    decay = recency_decay(posted_at, source)
    base = (llm_score * INTENT_MULT.get(intent, 0.5)
            * source_weight * service_weight * decay)
    # A freshness bonus only means something where decay is in play; for a
    # non-decaying source every signal would score it, which is no signal.
    bonus = 10 if (decay > 0.9 and source not in NO_DECAY) else 0
    return max(0, min(100, round(base + bonus)))


def classify(key, sig) -> dict:
    return llm.ask_json(
        PROMPT + f"\nSOURCE: {sig['source']}\nBUSINESS: {sig.get('who','')}\n"
                 f"TEXT: {sig.get('text','')}", key)


def run(limit=None):
    load_env()
    cfg = load_config()
    key = llm.key()
    weights = cfg["source_weights"]
    svc_weights = cfg.get("service_weights", {})

    # 1. Read rows + batch-drop rule failures (short DB session).
    with db.conn() as c:
        q = "select id, source, who, body, posted_at from raw_signals where judged_at is null"
        rows = c.execute(q + (f" limit {int(limit)}" if limit else "")).fetchall()
        # Rule filter applies to reviews (complaint language).
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
            time.sleep(llm.PACE)
        try:
            r = classify(key, {"source": source, "who": who, "text": body})
        except Exception as e:  # ponytail: skip a bad row, don't kill the run
            print(f"  classify failed id={sid}: {e}", file=sys.stderr)
            continue
        score = final_score(int(r.get("score", 0)), r.get("intent", "vague"),
                            weights.get(source, 1.0), posted_at, source,
                            svc_weights.get(r.get("service"), 1.0))
        updates.append((r.get("service"), r.get("intent"), score,
                        r.get("summary"), r.get("why_contact"), sid))

    # 3. Write results in one short DB session.
    with db.conn() as c:
        for u in updates:
            c.execute(
                "update raw_signals set judged_at=now(), service=%s, intent=%s, "
                "intent_score=%s, summary=%s, why_contact=%s where id=%s", u)
    print(f"  {len(updates)} scored by LLM")
    return len(updates)


def _selftest():
    assert passes_rules("their website is down for a week")
    assert not passes_rules("great food and lovely staff")
    # P7: reviews are not discounted for age, so a real complaint can qualify
    assert recency_decay(None, "google_reviews") == 1.0
    assert recency_decay(datetime(2020, 1, 1, tzinfo=UTC), "google_reviews") == 1.0
    assert final_score(80, "has_problem", 1.0, datetime(2020, 1, 1, tzinfo=UTC)) >= 50
    # a perishable source still decays
    assert recency_decay(None, "forum") == 0.7
    assert recency_decay(datetime(2020, 1, 1, tzinfo=UTC), "forum") < 0.01
    assert final_score(100, "actively_seeking", 1.0, None) <= 100
    assert final_score(0, "vague", 1.0, None) == 0
    hi = final_score(90, "actively_seeking", 1.0, datetime.now(UTC))
    lo = final_score(90, "vague", 0.9, None)
    assert hi > lo
    # a service the feedback loop likes must outscore one it does not
    now = datetime.now(UTC)
    assert (final_score(80, "has_problem", 1.0, now, service_weight=1.4)
            > final_score(80, "has_problem", 1.0, now, service_weight=0.6))
    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        lim = None
        if "--limit" in sys.argv:
            lim = sys.argv[sys.argv.index("--limit") + 1]
        run(lim)
