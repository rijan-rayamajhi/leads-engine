"""End-to-end pipeline: DISCOVER -> JUDGE -> ENRICH -> VERIFY -> PRIORITIZE/DELIVER.

  python pipeline.py --once                 # full run
  python pipeline.py --once --city "Pokhara, Nepal"
  python pipeline.py --once --skip discover # reuse existing signals
"""
import sys, os, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config
import db, scoring
from sources import places
import judge, enrich, verify
from website_leads import city_for


def deliver(cfg):
    """Create leads from qualified judged signals (score >= qualified threshold)."""
    # P4: city_for, not cfg["city"]. A --city run must file its leads under the
    # market it actually scanned; this was fixed in website_leads.py and missed here.
    th, city = cfg["thresholds"], city_for(cfg)
    with db.conn() as c:
        rows = c.execute("""
            select rs.who, rs.body, rs.source, rs.source_url, rs.service,
                   rs.summary, rs.why_contact, rs.intent_score, rs.company_id,
                   co.phone, co.email
            from raw_signals rs left join companies co on co.id = rs.company_id
            where rs.intent_score >= %s
              and not exists (select 1 from leads l where l.source_url = rs.source_url)
        """, (th["qualified"],)).fetchall()
        created = 0
        for (who, body, source, url, service, summary, why, score,
             company_id, phone, email) in rows:
            # No phone, no email and no listing to open is not a lead, it is a
            # row a rep cannot act on. `url` is the Maps listing, so this only
            # ever fires on a signal that lost its source_url.
            if not (phone or email or url):
                continue
            db.insert_lead(
                c, company_id=company_id, name=who, phone=phone, email=email,
                service=service, what_they_want=summary, evidence_quote=body,
                why_contact=why, source=source, source_url=url, city=city,
                intent_score=score, bucket=scoring.bucket_for(score, th))
            created += 1
    print(f"DELIVER: {created} new qualified leads")
    return created


def run(city=None, skip=()):
    load_env()
    cfg = load_config()
    if city:
        os.environ["CRAWL_CITY"] = city

    # One runs row per invocation, so the dashboard can tell "cron never fired"
    # from "cron fired and crashed". Errors are recorded, then re-raised so the
    # GitHub Action still goes red.
    with db.conn() as c:
        run_id = db.start_run(c, "pipeline", city_for(cfg))
    stats, err = {}, None
    try:
        if "discover" not in skip:
            print("== DISCOVER =="); stats["signals"] = places.run()
        if "judge" not in skip:
            print("== JUDGE =="); stats["judged"] = judge.run()
        if "enrich" not in skip:
            print("== ENRICH =="); stats["enriched"] = enrich.run()
        if "verify" not in skip:
            print("== VERIFY =="); stats["phones_checked"] = verify.run()
        print("== DELIVER =="); stats["leads"] = deliver(cfg)
        # P5: find an email for the companies behind existing leads, so the
        # phone is not the only way to reach them.
        if "email" not in skip:
            print("== EMAIL ==")
            try:
                stats["emails"] = enrich.run_leads()
            except Exception as e:
                print(f"  email stage failed, leads stay phone-only: {e}", file=sys.stderr)
        # PITCH is not a stage here. It writes openers for every lead that
        # lacks one, so it has to run after BOTH factories; crawl.yml calls
        # pitch.py last. Running it here too pitched the judge's leads, then
        # ran again for website_leads', for two model batches instead of one.
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        raise
    finally:
        with db.conn() as c:
            db.finish_run(c, run_id, stats.get("signals"), stats.get("leads"), stats, err)


if __name__ == "__main__":
    a = sys.argv[1:]
    city = a[a.index("--city") + 1] if "--city" in a else None
    skip = a[a.index("--skip") + 1].split(",") if "--skip" in a else ()
    run(city=city, skip=skip)
