"""Lead factory: businesses whose web presence is VERIFIABLY broken or missing.

Produces every lead this system currently has. No LLM: the defect is a fact we
fetched, which is why a rep can open with it and be right.

  site does not load / parked / 5xx / 404 / broken TLS -> their site is failing them
  no website at all                                    -> they need one
  plain HTTP or a blank homepage                       -> they need a rebuild
  social page only                                     -> they need a real site
A business whose site is HEALTHY is not a lead. That check is what makes the
other 80% of the harvest addressable instead of silently skipped.

Was `gap.py`, which read like a side experiment rather than the module every
lead comes from.
"""
import json, os, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config, norm_name  # noqa: E402
import db, scoring, sitecheck  # noqa: E402

# leads.what_they_want, keyed by the evidence fragment before any colon
WHAT_THEY_WANT = {
    "no website found": "Needs a website",
    "social page only": "Needs a website beyond social media",
    "site problem": "Needs their website fixed or rebuilt",
}

NO_SITE = 70      # base for no website at all
SOCIAL_ONLY = 60  # a social page is something, so a weaker gap than nothing


class Diagnosis(tuple):
    """(service, pitch, base, evidence) with names, so the four call sites stop
    unpacking a bare tuple positionally."""
    __slots__ = ()

    def __new__(cls, service=None, pitch=None, base=None, evidence=None):
        return super().__new__(cls, (service, pitch, base, evidence))

    service = property(lambda self: self[0])
    pitch = property(lambda self: self[1])
    base = property(lambda self: self[2])
    evidence = property(lambda self: self[3])

    def __bool__(self):
        return self[0] is not None


def diagnose(website, issues=None) -> Diagnosis:
    """What is wrong with this business's web presence, if anything.

    `issues` is sitecheck's verdict on a real site: None means unchecked (fall
    back to presence only), [] means healthy and therefore NOT a lead.
    """
    if not website:
        return Diagnosis("website",
                         "No website, so customers searching online never find them.",
                         NO_SITE, "no website found")
    if sitecheck.is_social(website):
        return Diagnosis("website",
                         "Only a social page, with no real website to sell or book on.",
                         SOCIAL_ONLY, "social page only")
    if issues is None:
        return Diagnosis()                      # unchecked real site
    worst = sitecheck.worst(issues)
    if not worst:
        return Diagnosis()                      # healthy site
    issue = sitecheck.ISSUES[worst]
    return Diagnosis("website", issue.pitch, issue.base, f"site problem: {worst}")


def open_for_business(status):
    """Places businessStatus. None = older signal harvested before we asked for
    the field, so unknown counts as open rather than silently dropping history."""
    return status in (None, "", "OPERATIONAL")


def city_for(cfg):
    """Same resolution as sources/places.py: a --city run must tag its leads with
    the city it actually scanned, not the configured default."""
    return os.environ.get("CRAWL_CITY") or cfg["city"]


# ---------------------------------------------------------------- site verdicts

def load_verdicts(c, ttl_days):
    """P2: cached verdicts keyed by URL. Previously cached on `companies`, which
    a healthy business never has, so 207 of 213 healthy sites were refetched
    every six hours."""
    return dict(c.execute(
        "select url, issues from site_checks where checked_at > now() - make_interval(days => %s)",
        (ttl_days,)).fetchall())


def save_verdicts(c, verdicts):
    """Store every verdict, healthy ones included. That is the whole point."""
    for url, issues in verdicts.items():
        c.execute("""insert into site_checks (url, issues, checked_at)
                     values (%s, %s, now())
                     on conflict (url) do update
                       set issues = excluded.issues, checked_at = now()""",
                  (url, json.dumps(issues)))


def checkable(website):
    """A URL worth spending a request on: a real site, not a social page."""
    return bool(website) and not sitecheck.is_social(website)


# ------------------------------------------------------------------ lead making

def run():
    load_env()
    cfg = load_config()
    with db.conn() as c:
        run_id = db.start_run(c, "website_leads", city_for(cfg))
    stats, err = {}, None
    try:
        stats["leads"] = create_leads(cfg)
        stats["stale"] = recheck_open_leads(cfg)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        raise
    finally:
        with db.conn() as c:
            db.finish_run(c, run_id, leads_new=stats.get("leads"), stats=stats, error=err)
    return stats["leads"]


def create_leads(cfg):
    th, city = cfg["thresholds"], city_for(cfg)
    cat_weights = cfg.get("category_weights", {})
    ttl = cfg.get("site_check_ttl_days", 14)

    with db.conn() as c:
        # One row per business, with the age of its most recent review: a
        # business reviewed last week is trading and reachable (P1 freshness).
        rows = c.execute("""
            select distinct on (raw->>'place_id')
                who, raw->>'place_id', raw->>'website', raw->>'phone',
                (raw->>'rating')::float, (raw->>'review_count')::int,
                raw->>'category', raw->>'maps_uri', raw->>'business_status',
                (select extract(day from now() - max(posted_at))::int
                   from raw_signals r2
                  where r2.raw->>'place_id' = raw_signals.raw->>'place_id')
            from raw_signals
            where source='google_reviews' and raw->>'place_id' is not null
        """).fetchall()
        verdicts = load_verdicts(c, ttl)

    todo = sorted({
        w for _, _, w, phone, _, _, _, _, status, _ in rows
        if phone and open_for_business(status) and checkable(w) and w not in verdicts
    })
    if todo:
        print(f"  checking {len(todo)} websites ({len(verdicts)} cached, ttl {ttl}d)")
        fresh = sitecheck.check_many(todo)
        verdicts.update(fresh)
        with db.conn() as c:
            save_verdicts(c, fresh)

    created, healthy, closed = 0, 0, 0
    with db.conn() as c:
        for (who, pid, website, phone, rating, rc, cat, maps_uri, status,
             days_since_review) in rows:
            if not phone:
                continue                     # need a callable number
            if not open_for_business(status):
                closed += 1
                continue
            d = diagnose(website, verdicts.get(website) if website else None)
            if not d:
                healthy += 1
                continue
            url = maps_uri or f"https://www.google.com/maps/place/?q=place_id:{pid}"
            if c.execute("select 1 from leads where source_url=%s", (url,)).fetchone():
                continue                     # dedupe
            s = scoring.lead_score(d.base, rc, rating, days_since_review,
                                   cat_weights.get(cat or "-", 1.0))
            cid = db.upsert_company(c, norm_name(who), place_id=pid, phone=phone,
                                    website=website, category=cat, rating=rating,
                                    review_count=rc, city=city)
            if website:
                c.execute("update companies set site_issues=%s where id=%s",
                          (json.dumps(verdicts.get(website) or []), cid))
            evidence = (f"{cat or 'Business'}, {rating or '?'}★ ({rc or 0} reviews), "
                        f"{d.evidence}")
            db.insert_lead(
                c, company_id=cid, name=who, phone=phone, service=d.service,
                what_they_want=WHAT_THEY_WANT.get(d.evidence.split(":")[0],
                                                  "Needs a working website"),
                evidence_quote=evidence, why_contact=d.pitch,
                source="google_maps_gap", source_url=url, city=city,
                intent_score=s, bucket=scoring.bucket_for(s, th))
            created += 1

    print(f"WEBSITE LEADS: {created} created, {healthy} healthy sites skipped, "
          f"{closed} closed businesses skipped")
    return created


def recheck_open_leads(cfg):
    """P3: a lead whose defect has been fixed must leave the board.

    Only sites we can recheck cheaply, which means leads that HAVE a URL. A
    "no website at all" lead would need a fresh Places call to disprove, so it
    is left to the next harvest.
    """
    ttl = cfg.get("lead_recheck_ttl_days", 7)
    with db.conn() as c:
        rows = c.execute("""
            select l.id, c.website from leads l join companies c on c.id = l.company_id
            where l.stale_at is null and l.status = 'new' and c.website is not null
              and (l.rechecked_at is null or l.rechecked_at < now() - make_interval(days => %s))
              and l.found_at < now() - make_interval(days => %s)
        """, (ttl, ttl)).fetchall()
    urls = sorted({w for _, w in rows if checkable(w)})
    if not urls:
        return 0

    print(f"  rechecking {len(urls)} sites behind open leads")
    verdicts = sitecheck.check_many(urls)
    fixed = 0
    with db.conn() as c:
        save_verdicts(c, verdicts)
        for lid, website in rows:
            issues = verdicts.get(website)
            if issues is None:
                continue                     # social page, nothing to recheck
            if sitecheck.worst(issues):
                c.execute("update leads set rechecked_at=now() where id=%s", (lid,))
            else:
                c.execute("""update leads set rechecked_at=now(), stale_at=now()
                             where id=%s""", (lid,))
                fixed += 1
    print(f"  {fixed} leads retired: the defect is gone")
    return fixed


def _selfcheck():
    # a healthy real site is NOT a lead, which is the whole point of the check
    assert not diagnose("https://acme.com", [])
    # an unchecked real site is not a lead either, rather than a guessed one
    assert not diagnose("https://acme.com", None)
    assert diagnose("https://acme.com", []).service is None
    # missing and social sites need no fetch
    assert diagnose(None).base == NO_SITE
    assert diagnose("https://facebook.com/acme").base == SOCIAL_ONLY
    # a broken site outranks a missing one: they already paid for something failing
    assert diagnose("https://acme.com", ["dead"]).base > NO_SITE
    # the worst issue drives the pitch, and the fields are named not positional
    d = diagnose("https://acme.com", ["empty", "ssl"])
    assert d and d.service == "website" and d.evidence == "site problem: ssl"
    assert d.base == sitecheck.ISSUES["ssl"].base
    assert d.pitch == sitecheck.ISSUES["ssl"].pitch
    # every fragment maps to a what_they_want line
    for f in ["no website found", "social page only", "site problem: http"]:
        assert f.split(":")[0] in WHAT_THEY_WANT, f

    # closed businesses are dropped, unknown status is kept
    assert open_for_business(None) and open_for_business("OPERATIONAL")
    assert not open_for_business("CLOSED_PERMANENTLY")
    assert not open_for_business("CLOSED_TEMPORARILY")

    # only real sites are worth a request
    assert checkable("https://acme.com")
    assert not checkable(None) and not checkable("https://instagram.com/acme")
    print("website_leads selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        run()
