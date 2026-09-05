"""DISCOVER source: Hacker News "Seeking Freelancer" threads (free Algolia API).

The monthly "Ask HN: Freelancer? Seeking freelancer?" thread has two kinds of
top-level comments:
  SEEKING FREELANCER  -> a company/person describing work they need done = LEAD
  SEEKING WORK        -> a freelancer offering services            = NOT a lead
We fetch the newest thread and keep only SEEKING FREELANCER comments. Contact is
the HN comment link (no phone).
"""
import sys, re, pathlib, requests
from html import unescape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402

SEARCH = "https://hn.algolia.com/api/v1/search"  # relevance-ranked
ITEM = "https://hn.algolia.com/api/v1/items/{}"
UA = {"User-Agent": "lead-engine/1.0"}
TAG_RE = re.compile(r"<[^>]+>")


def _strip(html: str) -> str:
    return unescape(TAG_RE.sub(" ", html or "")).strip()


def _latest_thread_id():
    r = requests.get(SEARCH, params={
        "query": "Seeking freelancer", "tags": "story,author_whoishiring",
        "restrictSearchableAttributes": "title", "hitsPerPage": 20},
        headers=UA, timeout=30)
    r.raise_for_status()
    hits = [h for h in r.json().get("hits", [])
            if "freelancer" in (h.get("title") or "").lower()]
    hits.sort(key=lambda h: -(h.get("created_at_i") or 0))  # newest first
    return hits[0]["objectID"] if hits else None


def fetch(cap=30):
    tid = _latest_thread_id()
    if not tid:
        print("  no freelancer thread found", file=sys.stderr)
        return []
    r = requests.get(ITEM.format(tid), headers=UA, timeout=30)
    r.raise_for_status()
    thread = r.json()
    print(f"  thread: {thread.get('title')}")
    signals = []
    for c in thread.get("children", []):
        text = _strip(c.get("text"))
        if not text or "SEEKING FREELANCER" not in text.upper():
            continue  # skip SEEKING WORK + empty
        signals.append({
            "source": "hackernews",
            "who": c.get("author", ""),
            "text": text[:1500],
            "source_url": f"https://news.ycombinator.com/item?id={c.get('id')}",
            "location": None,
            "posted_at": c.get("created_at"),
            "raw": {"thread_id": tid},
        })
        if len(signals) >= cap:
            break
    return signals


def run():
    load_env(); load_config()
    print("HackerNews: latest 'Seeking Freelancer' thread")
    sigs = fetch()
    print(f"  collected {len(sigs)} SEEKING FREELANCER posts")
    with db.conn() as c:
        new = db.upsert_signals(c, sigs)
    print(f"  {new} new -> raw_signals ({len(sigs) - new} already seen)")
    return new


if __name__ == "__main__":
    run()
