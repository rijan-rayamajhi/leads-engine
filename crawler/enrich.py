"""ENRICH: qualified judged signals -> company records (phone, website, email).

Phone/website/rating already rode along from Places in raw_signals.raw, so the
only network work here is a best-effort website scrape for an email. Results are
cached in `companies` (keyed by normalized name) and linked back to the signal.
"""
import os, sys, re, pathlib, requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
UA = {"User-Agent": "Mozilla/5.0 (lead-engine)"}
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")


def norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


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


def run():
    load_env()
    load_config()
    with db.conn() as c:
        # qualified = the judge tagged a real service (not 'none'), not yet enriched
        # Only google_reviews carry Places business data (phone/website). Reddit
        # leads have no company -> their contact is the thread permalink.
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


if __name__ == "__main__":
    run()
