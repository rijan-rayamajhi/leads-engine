"""ENRICH: qualified judged signals -> company records (phone, website, email).

Phone/website/rating already rode along from Places in raw_signals.raw, so the
only network work here is a best-effort website scrape for an email. Results are
cached in `companies` (keyed by normalized name) and linked back to the signal.
"""
import sys, re, pathlib, requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config, norm_name
import db

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
UA = {"User-Agent": "Mozilla/5.0 (lead-engine)"}
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")


def scrape_email(website: str):
    """Best-effort: find an email on the homepage. Returns None on any failure."""
    if not website:
        return None
    try:
        html = requests.get(website, timeout=10, headers=UA).text
    except requests.RequestException:
        return None
    m = re.search(r"mailto:([^\"'?>]+)", html)
    if m and EMAIL_RE.fullmatch(m.group(1).strip()):
        return m.group(1).strip()
    for m in EMAIL_RE.finditer(html):
        e = m.group(0)
        if not e.lower().endswith(IMG_EXT):
            return e
    return None


def run_leads():
    """P5: 0 of 78 leads had an email. enrich.run() only covers judged signals,
    and those are near zero, so the companies behind website leads were never
    scraped. A broken site still usually has a mailto: on it, and an email is
    the only follow-up channel after a missed call."""
    load_env()
    load_config()
    with db.conn() as c:
        rows = c.execute("""
            select distinct c.id, c.website from leads l join companies c on c.id = l.company_id
            where c.website is not null and c.email is null and l.stale_at is null
        """).fetchall()
    print(f"enriching {len(rows)} lead companies for an email")

    found = [(cid, scrape_email(w)) for cid, w in rows]
    found = [(cid, e) for cid, e in found if e]
    with db.conn() as c:
        for cid, email in found:
            c.execute("update companies set email=%s, enriched_at=now() where id=%s",
                      (email, cid))
            # mirror onto the leads, which is what the dashboard reads
            c.execute("""update leads set email=%s
                         where company_id=%s and email is null""", (email, cid))
    print(f"  {len(found)} emails found")
    return len(found)


def run():
    load_env()
    load_config()
    with db.conn() as c:
        # qualified = the judge tagged a real service (not 'none'), not yet enriched
        # Only google_reviews carry Places business data (phone/website).
        rows = c.execute("""
            select id, who, raw from raw_signals
            where service is not null and service <> 'none' and company_id is null
              and source = 'google_reviews'
        """).fetchall()
    print(f"enriching {len(rows)} qualified signals")

    enriched = []
    for sid, who, raw in rows:
        raw = raw or {}
        website = raw.get("website")
        email = scrape_email(website)
        enriched.append({
            "sid": sid, "name_norm": norm_name(who),
            "fields": {
                "place_id": raw.get("place_id"), "phone": raw.get("phone"),
                "email": email, "website": website,
                "category": raw.get("category"), "rating": raw.get("rating"),
                "review_count": raw.get("review_count"), "enriched_at": "now()",
            },
        })

    with db.conn() as c:
        for e in enriched:
            f = dict(e["fields"])
            f.pop("enriched_at")  # set via SQL now(), not param
            cid = db.upsert_company(c, e["name_norm"], **f)
            c.execute("update companies set enriched_at=now() where id=%s", (cid,))
            c.execute("update raw_signals set company_id=%s where id=%s", (cid, e["sid"]))
    print(f"  {len(enriched)} companies upserted + linked")
    return len(enriched)


if __name__ == "__main__":
    if "--leads" in sys.argv:
        run_leads()
    else:
        run()
