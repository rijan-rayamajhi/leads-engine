"""DISCOVER source: Reddit — people actively asking for digital work.

Uses Reddit's PUBLIC JSON search endpoint (no app, no OAuth, no keys). Searches
target subreddits for intent phrases; every hit is high-intent (search pre-filters).
Contact is the thread permalink (no phone). Be polite: descriptive UA + throttle.
"""
import sys, time, pathlib
from datetime import datetime, timezone
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402

UA = {"User-Agent": "lead-engine/1.0 (business lead research; contact via github)"}
QUERIES = [
    "need a website", "looking for a web developer", "need a developer",
    "hire a developer", "build an app", "need a mobile app", "need a chatbot",
    "whatsapp bot", "custom software", "need someone to build",
]


def _search(subs, query, limit=15):
    url = f"https://www.reddit.com/r/{'+'.join(subs)}/search.json"
    params = {"q": query, "restrict_sr": "on", "sort": "new",
              "t": "month", "limit": limit}
    for attempt in range(3):
        r = requests.get(url, params=params, headers=UA, timeout=30)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        return [c["data"] for c in r.json()["data"]["children"]]
    r.raise_for_status()


def fetch(subreddits):
    signals, seen = [], set()
    for q in QUERIES:
        try:
            posts = _search(subreddits, q)
        except requests.RequestException as e:
            print(f"  reddit search failed for {q!r}: {e}", file=sys.stderr)
            continue
        for p in posts:
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            body = (p.get("title", "") + "\n\n" + (p.get("selftext") or "")).strip()
            signals.append({
                "source": "reddit",
                "who": "u/" + (p.get("author") or "[deleted]"),
                "text": body,
                "source_url": "https://reddit.com" + p["permalink"],
                "location": None,
                "posted_at": datetime.fromtimestamp(p["created_utc"], tz=timezone.utc),
                "raw": {"subreddit": p.get("subreddit"), "score": p.get("score"),
                        "num_comments": p.get("num_comments"),
                        "title": p.get("title"), "query": q},
            })
        time.sleep(2)  # be polite to the public endpoint
    return signals


def run():
    load_env()
    cfg = load_config()
    subs = cfg.get("subreddits", ["smallbusiness", "startups", "Entrepreneur"])
    print(f"Reddit: searching {len(subs)} subreddits x {len(QUERIES)} queries (public JSON)")
    sigs = fetch(subs)
    print(f"  collected {len(sigs)} unique posts")
    with db.conn() as c:
        new = db.upsert_signals(c, sigs)
    print(f"  {new} new -> raw_signals ({len(sigs) - new} already seen)")
    return new


if __name__ == "__main__":
    run()
