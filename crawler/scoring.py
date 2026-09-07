"""Lead scoring, shared by every factory so one threshold rule lives in one place.

P1 fix. The old website score saturated: base 70 + a review term capped at 200
reviews + a binary rating bonus put 33 of 78 leads at exactly 100 and 44 at 90+.
A rep opening 47 HOT leads was working a random order, which is the same as
having no score at all.

Every term here is continuous and log-scaled where the input is long-tailed, so
15,000 reviews outranks 200 instead of tying with it. Weights are chosen so a
realistic best case reaches ~100 and a realistic worst case sits near 50, which
keeps the whole 0-100 range in use.
"""
import math
import sys

# term ceilings. base (46-72, from sitecheck) + these = 100 at the very top.
MAX_REVIEWS = 16.0
MAX_RATING = 8.0
MAX_FRESH = 4.0

FRESH_DAYS, WARM_DAYS = 90, 365


def review_term(review_count):
    """Log-scaled: every 10x more reviews is worth a fixed step, so a 15,000
    review institution outranks a 200 review shop instead of tying at the cap."""
    n = max(review_count or 0, 0)
    return min(4.0 * math.log10(1 + n), MAX_REVIEWS)


def rating_term(rating):
    """Continuous from 3.0 up. The old cliff at 4.0 made 3.9 and 1.0 identical."""
    if not rating:
        return 0.0
    return max(0.0, min((float(rating) - 3.0) * 4.0, MAX_RATING))


def freshness_term(days_since_review):
    """A business reviewed last week is trading, staffed and reachable. One with
    no review in two years may not answer the phone at all."""
    if days_since_review is None:
        return 0.0
    if days_since_review <= FRESH_DAYS:
        return MAX_FRESH
    if days_since_review <= WARM_DAYS:
        return MAX_FRESH / 2
    return 0.0


def lead_score(base, review_count=None, rating=None, days_since_review=None,
               weight=1.0):
    """0-100. `base` is how bad the verified defect is; the rest is how much
    this business is worth calling about. `weight` is the feedback loop's."""
    raw = (base
           + review_term(review_count)
           + rating_term(rating)
           + freshness_term(days_since_review))
    return int(max(0, min(round(raw * weight), 100)))


def bucket_for(score, thresholds):
    """The ONE bucket rule. Previously duplicated in gap.py, pipeline.py and
    again as SQL in web/app/actions.ts."""
    s = score or 0
    if s >= thresholds["hot"]:
        return "HOT"
    if s >= thresholds["warm"]:
        return "WARM"
    if s >= thresholds["qualified"]:
        return "QUALIFIED"
    return "DROP"


def _selfcheck():
    # log scale: 10x reviews is a real step, and it never flattens early
    assert review_term(0) == 0
    for a, b in [(10, 100), (100, 1000), (1000, 10_000)]:
        assert review_term(b) - review_term(a) > 3, (a, b)
    # the old bug: 200 and 15000 reviews must NOT tie
    assert review_term(15_000) - review_term(200) > 4
    assert review_term(10**9) == MAX_REVIEWS      # still bounded
    assert review_term(None) == 0 and review_term(-5) == 0

    # rating is continuous, no cliff, and bounded both ends
    assert rating_term(3.0) == 0 and rating_term(None) == 0
    assert rating_term(1.0) == 0                  # never negative
    assert rating_term(5.0) == MAX_RATING
    assert rating_term(4.5) > rating_term(4.4) > rating_term(4.0)

    # freshness
    assert freshness_term(1) == MAX_FRESH
    assert freshness_term(200) == MAX_FRESH / 2
    assert freshness_term(9999) == 0
    assert freshness_term(None) == 0

    # ordering: the whole point. a stronger defect on a bigger business wins.
    dead_big = lead_score(72, 15_000, 4.8, 10)
    dead_small = lead_score(72, 5, 3.1, 900)
    missing_big = lead_score(70, 15_000, 4.8, 10)
    assert dead_big > missing_big > dead_small
    assert dead_big <= 100 and dead_small >= 50

    # no saturation: distinct inputs give distinct scores across the range
    scores = {lead_score(70, n, 4.4, 30) for n in (5, 50, 500, 5000, 50_000)}
    assert len(scores) == 5, scores

    # feedback weight moves it, clamped
    assert lead_score(70, 100, 4.4, 10, 1.3) > lead_score(70, 100, 4.4, 10, 0.7)
    assert 0 <= lead_score(70, 100, 4.4, 10, 0.0) <= 100

    th = {"hot": 90, "warm": 70, "qualified": 50}
    assert bucket_for(95, th) == "HOT" and bucket_for(70, th) == "WARM"
    assert bucket_for(50, th) == "QUALIFIED" and bucket_for(10, th) == "DROP"
    assert bucket_for(None, th) == "DROP"
    print("scoring selfcheck ok")


def _parity_check():
    """The SQL twin in schema.sql must agree with bucket_for for every input.
    Needs a database; run it after applying schema.sql."""
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    from common import load_env
    import db
    load_env()
    th = {"hot": 90, "warm": 70, "qualified": 50}
    cases = [None, 0, 1, 49, 50, 51, 69, 70, 71, 89, 90, 91, 100, 150]
    with db.conn() as c:
        for v in cases:
            (sql_result,) = c.execute(
                "select bucket_for(%s, %s, %s, %s)",
                (v, th["hot"], th["warm"], th["qualified"])).fetchone()
            mine = bucket_for(v, th)
            assert mine == sql_result, f"{v}: python={mine} sql={sql_result}"
    print(f"bucket_for parity ok across {len(cases)} inputs")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    elif "--parity" in sys.argv:
        _parity_check()
