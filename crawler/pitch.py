"""PITCH: turn a lead's verified facts into something a rep can actually say.

Before this, 40 of 71 leads carried the byte-identical sentence "No website, so
customers searching online never find them." A rep reading their tenth one stops
reading, and the lead's real hook (4.6 stars, 892 reviews, a dentist in
Koramangala) was sitting unused in the row.

**The model never states a fact.** Every number and defect is passed IN, already
verified by sitecheck/Places, and the prompt forbids adding any others. The model
only chooses the framing. That is what stops a rep confidently telling a business
something false, which is the one failure mode that costs more than a missed lead.

If this stage is skipped or fails, leads keep their rule-written why_contact and
the pipeline is unharmed: AI enriches leads here, it never decides they exist.

  python pitch.py            # write pitches for leads that lack one
  python pitch.py --limit 5
"""
import re, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config, batched
import db, llm
import time

MAX_CHARS = 400   # a pitch a rep reads at a glance, not a paragraph

PROMPT = """You write one-line call openers for a digital-services agency in {city}.
A rep is about to phone this business. Give them the angle.

VERIFIED FACTS (these are checked; do not add, change or invent any others):
- Business: {name}
- Type: {category}
- Reputation: {reputation}
- Confirmed problem: {problem}
- What we would sell them: {service}

Return ONLY compact JSON:
{{"opener": "<=35 words the rep can say out loud, naming the specific problem and
what it costs this business. Concrete, no jargon, no greeting, no 'I hope'.>",
 "angle": "<=15 words: the commercial reason THIS business should care>"}}

Rules:
- Use only the facts above. Never state a number that is not listed.
- Never claim you visited, called, or are a customer.
- No exclamation marks, no 'revolutionary', no 'in today's digital world'.
- If the facts are thin, stay general rather than inventing detail.
"""


def reputation(rating, review_count):
    """A human phrase, or an honest blank. Never a fabricated number."""
    if rating and review_count:
        return f"{rating} stars across {review_count} Google reviews"
    if review_count:
        return f"{review_count} Google reviews"
    return "no reliable rating data"


# Batch header. The quality of these openers lives or dies on this prompt, so
# it teaches the craft (Gong's 300M-call analysis: a specific reason tied to the
# prospect lifts pickup ~2.1x) and shows the voice with worked examples. The
# number-guard in pitch_batch still rejects any invented figure per lead, so the
# example numbers below can't leak into a real pitch.
PROMPT_BATCH = """You write the ONE line a salesperson says when they cold-call a
local business for a digital-services agency. This is the hardest 10 seconds in
sales: sound generic and they hang up. Your line has to earn the next 20 seconds.

WHAT A GREAT OPENER DOES (learn the thinking, never copy the wording):
1. Opens with something REAL about THIS business - their reputation, their type,
   the exact problem found. Never a generic line about "today's digital world".
2. Names ONE concrete problem and its ACTUAL cost to them: lost bookings,
   customers landing on a competitor, calls going unanswered. Customers or money,
   never vague "online presence" or "digital footprint".
3. Sounds like a human talking out loud - short sentences, plain words, the way
   you'd tip off a friend. Not marketing copy.

NEVER: greetings ("Hi, I hope you're well"), buzzwords ("leverage", "solutions",
"revolutionary", "take your business to the next level", "in today's digital
world"), exclamation marks, or claiming you visited/called/are a customer.

GOOD - study the voice:
- Facts: Kamat's | restaurant | 4.6 stars / 892 reviews | problem: no website | sell: website
  opener: "Your 4.6 across nearly 900 reviews tells me people love the place - but there's no website, so anyone Googling 'restaurants near me' is landing on your competitors instead of you."
  angle: "A loved restaurant losing new diners to rivals who show up in search."
- Facts: Sunrise Dental | dentist | no rating data | problem: never answers the phone | sell: ai_phone
  opener: "A few reviews mention calling to book and nobody picking up. For a clinic that usually means the patient just booked with the dentist down the road instead."
  angle: "Every missed call is a booked appointment walking to a competitor."

BAD - never write like this (vague, salesy, no real hook):
  "In today's digital world, a strong online presence is essential. We offer
  website solutions to help take your business to the next level."

FACTS RULE: use ONLY each business's listed facts. Never state a number not
listed for it. If the facts are thin, stay general and human - do not invent detail.

Write ONE opener per business below.

Return ONLY compact JSON, one object per business, SAME ORDER, echoing the number as "i":
{"results":[{"i":0,"opener":"<=35 spoken words: the specific problem + its real cost, no greeting","angle":"<=15 words: the commercial reason THIS business should care"}, ...]}

BUSINESSES:
"""


def build_item(lead, city):
    """One compact line per lead for the batch prompt, same verified facts as
    build_prompt feeds a single call."""
    return (f"City: {city or 'this city'} | Business: {lead['name'] or 'this business'} "
            f"| Type: {lead['category'] or 'local business'} "
            f"| Reputation: {reputation(lead.get('rating'), lead.get('review_count'))} "
            f"| Confirmed problem: "
            f"{lead['why_contact'] or lead['evidence_quote'] or 'weak online presence'} "
            f"| Sell: {lead['service'] or 'website'}")


def _align(results, n):
    """Map an LLM results array back to n inputs by echoed "i", else position."""
    by_i = {}
    for r in results:
        if isinstance(r, dict):
            try:
                by_i[int(r["i"])] = r
            except (KeyError, TypeError, ValueError):
                pass
    if len(by_i) == n and set(by_i) == set(range(n)):
        return [by_i[i] for i in range(n)]
    return [results[i] if i < len(results) and isinstance(results[i], dict) else None
            for i in range(n)]


def pitch_batch(items, key=None):
    """items: list of (lead, city). Returns list aligned to items of
    (opener, angle), or None where the model gave nothing usable or invented a
    number for that lead. One rejected lead never taints its batch-mates."""
    body = "\n".join(f"[{i}] {build_item(lead, city)}"
                     for i, (lead, city) in enumerate(items))
    out = llm.ask_json(PROMPT_BATCH + body, key)
    results = _align(out.get("results", []) if isinstance(out, dict) else [], len(items))
    aligned = []
    for (lead, _city), r in zip(items, results, strict=True):
        if not isinstance(r, dict):
            aligned.append(None)
            continue
        opener, angle = clean(r.get("opener")), clean(r.get("angle"), 120)
        if not opener or unverified_numbers(opener + " " + angle, lead):
            aligned.append(None)     # invented number or empty -> keep rule text
            continue
        aligned.append((opener, angle))
    return aligned


def build_prompt(lead, city):
    return PROMPT.format(
        city=city or "this city",
        name=lead["name"] or "this business",
        category=lead["category"] or "local business",
        reputation=reputation(lead.get("rating"), lead.get("review_count")),
        problem=lead["why_contact"] or lead["evidence_quote"] or "weak online presence",
        service=lead["service"] or "website",
    )


def allowed_numbers(lead):
    """Every number the model is permitted to say, as strings. Anything else in
    its output is invented."""
    ok = set()
    for v in (lead.get("rating"), lead.get("review_count")):
        if v in (None, 0):
            continue
        t = str(v)
        ok |= {t, t.rstrip("0").rstrip("."), t.replace(".", ""), f"{float(v):.1f}"}
    return {x for x in ok if x}


def unverified_numbers(text, lead):
    """Numbers in `text` that are not in the lead's verified facts.

    This is the guard that makes the module's promise real rather than a hope:
    a hallucinated review count is the one output that can make a rep sound
    like a liar on a live call, so a pitch containing one is thrown away.
    """
    allowed = allowed_numbers(lead)
    found = {n.replace(",", "") for n in re.findall(r"\d+(?:[.,]\d+)?", text or "")}
    return {n for n in found if n not in allowed}


def clean(text, limit=MAX_CHARS):
    """Models like to add a greeting or wrap things in quotes. Strip both."""
    t = " ".join(str(text or "").split()).strip('"“”\'')
    return t[:limit].rstrip()


def run(limit=None):
    load_env()
    cfg = load_config()
    key = llm.key()

    # Per-run cap: pitch the highest-intent leads first (SQL order), cap the
    # count; the rest keep their rule-written why_contact and pitch next cron.
    lc = cfg.get("llm", {})
    size = int(lc.get("batch_size", 15))
    cap = int(limit) if limit else int(lc.get("max_per_run", 200))
    with db.conn() as c:
        rows = c.execute("""
            select l.id, l.name, l.service, l.why_contact, l.evidence_quote, l.city,
                   c.category, c.rating, c.review_count
            from leads l left join companies c on c.id = l.company_id
            where l.pitch is null and l.bucket in ('HOT','WARM','QUALIFIED')
            order by l.intent_score desc nulls last
            limit %s
        """, (cap,)).fetchall()
    cols = ["id", "name", "service", "why_contact", "evidence_quote", "city",
            "category", "rating", "review_count"]
    leads = [dict(zip(cols, r, strict=True)) for r in rows]
    print(f"pitching {len(leads)} leads in batches of {size}")

    def flush(rows):
        """Short DB session, opened only once a batch is ready. Keeps the
        original property that no connection is held across a network call."""
        if not rows:
            return
        with db.conn() as c:
            for opener, angle, lid in rows:
                c.execute("""update leads set pitch=%s, pitch_angle=%s, pitch_at=now()
                             where id=%s""", (opener, angle, lid))

    # Slow calls with NO DB connection held, one call per batch of `size`.
    pending, done, failed, empty = [], 0, 0, 0
    for b, chunk in enumerate(batched(leads, size)):
        if b:
            time.sleep(llm.PACE)
        items = [(lead, lead["city"] or cfg.get("city")) for lead in chunk]
        try:
            got = pitch_batch(items, key)
        except llm.RateLimitError:
            # Quota spent; remaining leads keep their accurate rule-written
            # why_contact and get pitched on the next run. Stop, don't grind.
            print(f"  rate-limited, stopping after {done + len(pending)}/{len(leads)} pitched",
                  file=sys.stderr)
            break
        except Exception as e:   # ponytail: lose one batch, never kill the run
            print(f"  pitch batch failed ({len(chunk)} leads): {e}", file=sys.stderr)
            failed += len(chunk)
            continue
        for lead, res in zip(chunk, got, strict=True):
            if res:
                pending.append((res[0], res[1], lead["id"]))
            else:
                # No usable opener (empty or invented a number): the lead keeps
                # its accurate rule-written why_contact, so this costs polish only.
                empty += 1
        # Flush after each batch so a later crash never discards earlier work.
        if pending:
            flush(pending)
            done += len(pending)
            pending = []
            print(f"  {done} written so far", flush=True)

    print(f"  {done} written, {failed} failed, {empty} returned nothing "
          f"({len(leads)} attempted)")
    return done


def _selfcheck():
    # reputation never invents a number
    assert reputation(4.6, 892) == "4.6 stars across 892 Google reviews"
    assert reputation(None, 12) == "12 Google reviews"
    assert reputation(None, None) == "no reliable rating data"
    assert reputation(4.6, 0) == "no reliable rating data"

    # clean strips wrapping quotes, collapses whitespace, caps length
    assert clean('  "hello   there"  ') == "hello there"
    assert clean("“smart quotes”") == "smart quotes"
    assert len(clean("x" * 999)) == MAX_CHARS
    assert clean(None) == "" and clean("") == ""

    # every verified fact reaches the prompt, and the no-invention rule is in it
    lead = {"name": "Kamat's", "service": "website", "why_contact": "No website",
            "evidence_quote": "e", "category": "Restaurant",
            "rating": 4.6, "review_count": 892}
    pr = build_prompt(lead, "Bangalore, India")
    for must in ["Kamat's", "Restaurant", "4.6 stars across 892", "No website",
                 "website", "Bangalore, India", "do not add, change or invent"]:
        assert must in pr, must
    # a lead with nothing but a defect still produces a valid prompt
    thin = {"name": None, "service": None, "why_contact": None, "evidence_quote": None,
            "category": None, "rating": None, "review_count": None}
    assert "this business" in build_prompt(thin, None)

    # the number guard: verified figures pass, invented ones are caught
    assert allowed_numbers(lead) >= {"4.6", "892"}
    assert unverified_numbers("rated 4.6 stars by 892 reviewers", lead) == set()
    assert unverified_numbers("4.6 stars across 892 reviews", lead) == set()
    assert unverified_numbers("1,200 customers a month", lead) == {"1200"}
    assert unverified_numbers("you lose 40% of searches", lead) == {"40"}
    assert unverified_numbers("no numbers at all", lead) == set()
    # a lead with no rating data must not let ANY number through
    assert unverified_numbers("rated 5 stars", thin) == {"5"}
    assert allowed_numbers(thin) == set()
    # batch alignment mirrors judge's: echoed "i" wins, else positional
    assert _align([{"i": 1}, {"i": 0}], 2) == [{"i": 0}, {"i": 1}]
    assert _align([{"a": 1}], 2) == [{"a": 1}, None]
    assert _align("not a list" and [], 1) == [None]
    print("pitch selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        lim = sys.argv[sys.argv.index("--limit") + 1] if "--limit" in sys.argv else None
        run(lim)
