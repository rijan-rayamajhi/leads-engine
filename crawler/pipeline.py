"""End-to-end pipeline: DISCOVER -> JUDGE -> ENRICH -> VERIFY -> PRIORITIZE/DELIVER.

  python pipeline.py --once                 # full run
  python pipeline.py --once --city "Pokhara, Nepal"
  python pipeline.py --once --skip discover # reuse existing signals
"""
import sys, os, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402
from sources import places  # noqa: E402
import judge, enrich, verify  # noqa: E402


def bucket_for(score, th):
    if score is None:
        score = 0
    if score >= th["hot"]:
        return "HOT"
    if score >= th["warm"]:
        return "WARM"
    if score >= th["qualified"]:
        return "QUALIFIED"
    return "DROP"


def deliver(cfg):
    """Create leads from qualified judged signals (score >= qualified threshold)."""
    th = cfg["thresholds"]
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
            db.insert_lead(
                c, company_id=company_id, name=who, phone=phone, email=email,
                service=service, what_they_want=summary, evidence_quote=body,
                why_contact=why, source=source, source_url=url,
                intent_score=score, bucket=bucket_for(score, th))
            created += 1
    print(f"DELIVER: {created} new qualified leads")
    return created


def run(city=None, skip=()):
    load_env()
    cfg = load_config()
    if city:
        os.environ["CRAWL_CITY"] = city

    if "discover" not in skip:
        print("== DISCOVER =="); places.run()
    if "judge" not in skip:
        print("== JUDGE =="); judge.run()
    if "enrich" not in skip:
        print("== ENRICH =="); enrich.run()
    if "verify" not in skip:
        print("== VERIFY =="); verify.run()
    print("== DELIVER =="); deliver(cfg)


if __name__ == "__main__":
    a = sys.argv[1:]
    city = a[a.index("--city") + 1] if "--city" in a else None
    skip = a[a.index("--skip") + 1].split(",") if "--skip" in a else ()
    run(city=city, skip=skip)
