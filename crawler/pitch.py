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
from common import load_env, load_config
import db, llm
import time

MAX_CHARS = 400   # a pitch a rep reads at a glance, not a paragraph
FLUSH_EVERY = 10  # write partway through: a crash at lead 52 of 53 used to
                  # discard all 52, because results were held until the end

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


def write_one(lead, city, key=None):
    """Returns (opener, angle), or None if the model gave nothing usable or
    invented a number. Rejecting beats correcting: the rule-written why_contact
    is already accurate, so a discarded pitch costs polish, not truth."""
    r = llm.ask_json(build_prompt(lead, city), key)
    opener, angle = clean(r.get("opener")), clean(r.get("angle"), 120)
    if not opener:
        return None
    bogus = unverified_numbers(opener + " " + angle, lead)
    if bogus:
        raise ValueError(f"invented numbers {sorted(bogus)}")
    return (opener, angle)


def run(limit=None):
    load_env()
    cfg = load_config()
    key = llm.key()

    with db.conn() as c:
        rows = c.execute(f"""
            select l.id, l.name, l.service, l.why_contact, l.evidence_quote, l.city,
                   c.category, c.rating, c.review_count
            from leads l left join companies c on c.id = l.company_id
            where l.pitch is null and l.bucket in ('HOT','WARM','QUALIFIED')
            order by l.intent_score desc nulls last
            {f'limit {int(limit)}' if limit else ''}
        """).fetchall()
    cols = ["id", "name", "service", "why_contact", "evidence_quote", "city",
            "category", "rating", "review_count"]
    leads = [dict(zip(cols, r, strict=True)) for r in rows]
    print(f"pitching {len(leads)} leads")

    def flush(rows):
        """Short DB session, opened only once a batch is ready. Keeps the
        original property that no connection is held across a network call."""
        if not rows:
            return
        with db.conn() as c:
            for opener, angle, lid in rows:
                c.execute("""update leads set pitch=%s, pitch_angle=%s, pitch_at=now()
                             where id=%s""", (opener, angle, lid))

    # Slow calls with NO DB connection held, same shape as judge.run.
    pending, done, failed, empty = [], 0, 0, 0
    for i, lead in enumerate(leads):
        if i:
            time.sleep(llm.PACE)
        try:
            got = write_one(lead, lead["city"] or cfg.get("city"), key)
        except Exception as e:   # ponytail: skip a bad row, never kill the run
            print(f"  pitch failed {lead['name']!r}: {e}", file=sys.stderr)
            failed += 1
            continue
        if got:
            pending.append((got[0], got[1], lead["id"]))
            if len(pending) >= FLUSH_EVERY:
                flush(pending)
                done += len(pending)
                pending = []
                print(f"  {done} written so far", flush=True)
        else:
            # A silent None used to vanish here: one run wrote 28 of 68 and the
            # other 40 were unaccounted for, 16 of them because of this branch.
            empty += 1
            print(f"  no usable opener for {lead['name']!r}", file=sys.stderr)

    flush(pending)
    done += len(pending)
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
    print("pitch selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        lim = sys.argv[sys.argv.index("--limit") + 1] if "--limit" in sys.argv else None
        run(lim)
