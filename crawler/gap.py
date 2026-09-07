"""GAP detector: turn harvested businesses into leads by VERIFIABLE digital gaps.

No LLM needed, the gap is a fact:
  site does not load / parked / broken TLS -> their site is failing them (strongest)
  no website at all                        -> needs a website
  no HTTPS, blank page, no mobile layout   -> needs a rebuild
  social-only page                         -> needs a real website
Score rises with how established the business is (rating x review_count): a
thriving 4.5* place with 300 reviews and a dead site is a hotter lead than a
quiet one. Every lead here has a phone (callable) and a checkable reason.

A business whose site is HEALTHY is not a lead. That check is what makes the
other 80% of the harvest addressable instead of silently skipped.
"""
import json, os, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config, norm_name  # noqa: E402
import db  # noqa: E402
import sitecheck  # noqa: E402

# what_they_want, keyed by the evidence fragment's first word
WANTS = {
    "no website found": "Needs a website",
    "social page only": "Needs a website beyond social media",
    "site problem": "Needs their website fixed or rebuilt",
}

NO_SITE = 70      # base for no website at all
SOCIAL_ONLY = 60  # a social page is something, so a weaker gap than nothing


def classify_gap(website, issues=None):
    """(service, pitch, base_score, evidence_fragment), or Nones if not a lead.

    `issues` is sitecheck's verdict on a real site: None means unchecked (fall
    back to presence only), [] means the site is healthy and this is NOT a lead.
    """
    if not website:
        return ("website", "No website, so customers searching online never find them.",
                NO_SITE, "no website found")
    if sitecheck.is_social(website):
        return ("website", "Only a social page, with no real website to sell or book on.",
                SOCIAL_ONLY, "social page only")
    if issues is None:
        return (None, None, None, None)   # unchecked real site: not a lead yet
    worst = sitecheck.worst(issues)
    if not worst:
        return (None, None, None, None)   # healthy site
    base, pitch = sitecheck.ISSUES[worst]
    return ("website", pitch, base, f"site problem: {worst}")


def score(rating, review_count, base, category_weight=1.0):
    """0-100. Base by gap strength, boosted by how established the business is,
    scaled by what the feedback loop has learned about this category."""
    rc = min((review_count or 0) / 10, 20)    # up to +20 for many reviews (established)
    rq = 10 if (rating or 0) >= 4.0 else 0    # +10 if well-liked (worth keeping online)
    return int(max(0, min((base + rc + rq) * category_weight, 100)))


def bucket_for(s, th):
    if s >= th["hot"]:
        return "HOT"
    if s >= th["warm"]:
        return "WARM"
    if s >= th["qualified"]:
        return "QUALIFIED"
    return "DROP"


def open_for_business(status):
    """Places businessStatus. None = older signal harvested before we asked for
    the field, so unknown counts as open rather than silently dropping history."""
    return status in (None, "", "OPERATIONAL")


def city_for(cfg):
    """Same resolution as sources/places.py: a --city run must tag its leads with
    the city it actually scanned, not the configured default."""
    return os.environ.get("CRAWL_CITY") or cfg["city"]


def run():
    load_env()
    cfg = load_config()
    with db.conn() as c:
        run_id = db.start_run(c, "gap", city_for(cfg))
    try:
        created = _run(cfg)
    except Exception as e:
        with db.conn() as c:
            db.finish_run(c, run_id, error=f"{type(e).__name__}: {e}")
        raise
    with db.conn() as c:
        db.finish_run(c, run_id, leads_new=created, stats={"leads": created})
    return created


def _run(cfg):
    th, city = cfg["thresholds"], city_for(cfg)
    cat_weights = cfg.get("category_weights", {})
    ttl = cfg.get("site_check_ttl_days", 14)

    with db.conn() as c:
        rows = c.execute("""
            select distinct on (raw->>'place_id')
                who, raw->>'place_id', raw->>'website', raw->>'phone',
                (raw->>'rating')::float, (raw->>'review_count')::int,
                raw->>'category', raw->>'maps_uri', raw->>'business_status'
            from raw_signals
            where source='google_reviews' and raw->>'place_id' is not null
        """).fetchall()

        # Cached verdicts, so a 6-hourly cron does not re-fetch every homepage.
        cached = dict(c.execute("""
            select website, site_issues from companies
            where website is not null and site_checked_at > now() - make_interval(days => %s)
        """, (ttl,)).fetchall())

    # Real sites needing a fresh verdict. Social pages and missing sites need no
    # fetch at all, and a closed business is dropped before we spend a request.
    todo = sorted({
        w for who, pid, w, phone, rating, rc, cat, uri, status in rows
        if phone and open_for_business(status) and w and not sitecheck.is_social(w)
        and w not in cached
    })
    if todo:
        print(f"  checking {len(todo)} websites ({len(cached)} cached, ttl {ttl}d)")
        cached.update(sitecheck.check_many(todo))

    created, healthy, closed = 0, 0, 0
    with db.conn() as c:
        for who, pid, website, phone, rating, rc, cat, maps_uri, status in rows:
            if not phone:
                continue  # need a callable number
            if not open_for_business(status):
                closed += 1
                continue
            issues = cached.get(website) if website else None
            service, pitch, base, fragment = classify_gap(website, issues)
            if not service:
                healthy += 1
                continue
            url = maps_uri or f"https://www.google.com/maps/place/?q=place_id:{pid}"
            if c.execute("select 1 from leads where source_url=%s", (url,)).fetchone():
                continue  # dedupe
            s = score(rating, rc, base, cat_weights.get(cat or "-", 1.0))
            cid = db.upsert_company(c, norm_name(who), place_id=pid, phone=phone,
                                    website=website, category=cat, rating=rating,
                                    review_count=rc, city=city)
            if website:
                c.execute("""update companies set site_issues=%s, site_checked_at=now()
                             where id=%s""", (json.dumps(issues or []), cid))
            evidence = (f"{cat or 'Business'}, {rating or '?'}\u2605 ({rc or 0} reviews), "
                        f"{fragment}")
            db.insert_lead(
                c, company_id=cid, name=who, phone=phone, service=service,
                what_they_want=WANTS.get(fragment.split(":")[0], "Needs a working website"),
                evidence_quote=evidence, why_contact=pitch,
                source="google_maps_gap", source_url=url, city=city,
                intent_score=s, bucket=bucket_for(s, th))
            created += 1

        # Remember healthy sites too, or every run re-fetches them.
        for w, iss in cached.items():
            if not iss:
                c.execute("""update companies set site_issues='[]'::jsonb,
                             site_checked_at=now() where website=%s""", (w,))

    print(f"GAP: {created} leads created, {healthy} healthy sites skipped, "
          f"{closed} closed businesses skipped")
    return created


def _selfcheck():
    # a healthy real site is NOT a lead, which is the whole point of the check
    assert classify_gap("https://acme.com", [])[0] is None
    # an unchecked real site is not a lead either, rather than a guessed one
    assert classify_gap("https://acme.com", None)[0] is None
    # missing and social sites need no fetch
    assert classify_gap(None)[2] == NO_SITE
    assert classify_gap("https://facebook.com/acme")[2] == SOCIAL_ONLY
    # a broken site outranks a missing one: they already paid for something failing
    assert classify_gap("https://acme.com", ["dead"])[2] > NO_SITE
    # the worst issue drives the pitch
    svc, pitch, base, frag = classify_gap("https://acme.com", ["empty", "ssl"])
    assert svc == "website" and frag == "site problem: ssl"
    assert base == sitecheck.ISSUES["ssl"][0] and pitch == sitecheck.ISSUES["ssl"][1]
    # every fragment maps to a what_they_want line
    for f in ["no website found", "social page only", "site problem: http"]:
        assert f.split(":")[0] in WANTS, f

    # established businesses outscore quiet ones on the same gap
    assert score(4.5, 300, NO_SITE) > score(3.0, 2, NO_SITE)
    assert score(5.0, 10_000, NO_SITE) <= 100          # clamped
    # feedback weights move the score in the right direction, still clamped
    assert score(4.5, 100, NO_SITE, 1.4) > score(4.5, 100, NO_SITE, 0.6)
    assert 0 <= score(4.5, 100, NO_SITE, 0.0) <= 100

    # closed businesses are dropped, unknown status is kept
    assert open_for_business(None) and open_for_business("OPERATIONAL")
    assert not open_for_business("CLOSED_PERMANENTLY")
    assert not open_for_business("CLOSED_TEMPORARILY")

    assert bucket_for(95, {"hot": 90, "warm": 70, "qualified": 50}) == "HOT"
    assert bucket_for(10, {"hot": 90, "warm": 70, "qualified": 50}) == "DROP"
    print("gap selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        run()
