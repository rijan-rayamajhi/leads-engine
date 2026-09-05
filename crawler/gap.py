"""GAP detector: turn harvested businesses into leads by VERIFIABLE digital gaps.

No LLM needed — the gap is a fact:
  no website          -> needs a website        (strongest)
  social-only page    -> needs a real website
Score rises with how established the business is (rating x review_count): a
thriving 4.5* place with 300 reviews and no site is a hotter lead than a quiet one.
Every lead here has a phone (callable) and a checkable reason.
"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402

SOCIAL = ("facebook.com", "instagram.com", "linktr.ee", "linktree")


def classify_gap(website):
    if not website:
        return ("website", "No website — invisible to customers searching online.")
    if any(s in website.lower() for s in SOCIAL):
        return ("website", "Only a social page — no real website to sell/book on.")
    return (None, None)  # has a proper site


def score(rating, review_count, social_only):
    """0-100. Base by gap strength, boosted by how established the business is."""
    base = 60 if social_only else 70          # no site is a stronger gap than social-only
    rc = min((review_count or 0) / 10, 20)    # up to +20 for many reviews (established)
    rq = 10 if (rating or 0) >= 4.0 else 0    # +10 if well-liked (worth keeping online)
    return int(min(base + rc + rq, 100))


def bucket_for(s, th):
    if s >= th["hot"]:
        return "HOT"
    if s >= th["warm"]:
        return "WARM"
    if s >= th["qualified"]:
        return "QUALIFIED"
    return "DROP"


def run():
    load_env()
    cfg = load_config()
    th = cfg["thresholds"]
    with db.conn() as c:
        rows = c.execute("""
            select distinct on (raw->>'place_id')
                who, raw->>'place_id', raw->>'website', raw->>'phone',
                (raw->>'rating')::float, (raw->>'review_count')::int,
                raw->>'category', raw->>'maps_uri'
            from raw_signals
            where source='google_reviews' and raw->>'place_id' is not null
        """).fetchall()

    created = 0
    with db.conn() as c:
        for who, pid, website, phone, rating, rc, cat, maps_uri in rows:
            if not phone:
                continue  # need a callable number
            service, pitch = classify_gap(website)
            if not service:
                continue  # has a real site -> not a gap lead
            url = maps_uri or f"https://www.google.com/maps/place/?q=place_id:{pid}"
            if c.execute("select 1 from leads where source_url=%s", (url,)).fetchone():
                continue  # dedupe
            social_only = bool(website)
            s = score(rating, rc, social_only)
            cid = db.upsert_company(c, who.lower().strip(), place_id=pid, phone=phone,
                                    website=website, category=cat, rating=rating,
                                    review_count=rc)
            evidence = (f"{cat or 'Business'}, {rating or '?'}★ ({rc or 0} reviews), "
                        f"{'social page only' if social_only else 'no website found'}")
            db.insert_lead(
                c, company_id=cid, name=who, phone=phone, service=service,
                what_they_want=("Needs a real website" if not social_only
                                else "Needs a website beyond social media"),
                evidence_quote=evidence, why_contact=pitch,
                source="google_maps_gap", source_url=url,
                intent_score=s, bucket=bucket_for(s, th))
            created += 1
    print(f"GAP: {created} website-gap leads created")
    return created


if __name__ == "__main__":
    run()
