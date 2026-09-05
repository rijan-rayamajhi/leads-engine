"""DISCOVER source: RemoteOK free JSON API (no auth).

Companies posting dev/web/app roles = intent + budget for development work.
Contact is the job post URL (no phone). Pre-filtered to relevant roles to keep
LLM volume low (OpenRouter free = 50/day).
"""
import sys, re, pathlib, requests
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402

API = "https://remoteok.com/api"
UA = {"User-Agent": "Mozilla/5.0 (lead-engine)"}
RELEVANT = ("developer", "engineer", "web", "app", "mobile", "software",
            "chatbot", " ai ", "automation", "full stack", "frontend", "backend")
TAG_RE = re.compile(r"<[^>]+>")


def _relevant(job):
    hay = (job.get("position", "") + " " + " ".join(job.get("tags", []))).lower()
    return any(k in hay for k in RELEVANT)


def fetch(cap=20):
    try:
        r = requests.get(API, headers=UA, timeout=30)
        r.raise_for_status()
        jobs = r.json()
    except requests.RequestException as e:
        print(f"  RemoteOK failed: {e}", file=sys.stderr)
        return []
    signals = []
    for job in jobs:
        if not isinstance(job, dict) or "position" not in job:
            continue  # first element is a legal notice
        if not _relevant(job):
            continue
        desc = TAG_RE.sub(" ", job.get("description", "")).strip()
        text = (job["position"] + "\n\n" + desc)[:1500]
        url = job.get("url") or f"https://remoteok.com/remote-jobs/{job.get('id')}"
        signals.append({
            "source": "remoteok",
            "who": job.get("company", ""),
            "text": text,
            "source_url": url,
            "location": job.get("location") or "remote",
            "posted_at": job.get("date"),
            "raw": {"tags": job.get("tags"), "position": job.get("position")},
        })
        if len(signals) >= cap:
            break
    return signals


def run():
    load_env(); load_config()
    print("RemoteOK: fetching dev/web/app roles")
    sigs = fetch()
    print(f"  collected {len(sigs)} relevant jobs")
    with db.conn() as c:
        new = db.upsert_signals(c, sigs)
    print(f"  {new} new -> raw_signals ({len(sigs) - new} already seen)")
    return new


if __name__ == "__main__":
    run()
