"""DISCOVER source: Google Places (New) -> businesses + their reviews as Signals.

Each review becomes one Signal. Business phone/website/rating ride along in raw
so ENRICH can reuse them without a second call.
"""
import os, sys, pathlib, time, requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join(
    "places." + f for f in [
        "id", "displayName", "nationalPhoneNumber", "internationalPhoneNumber",
        "websiteUri", "rating", "userRatingCount", "primaryTypeDisplayName",
        "formattedAddress", "reviews", "googleMapsUri",
    ]
)


def _search(query, key, retries=2):
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                SEARCH_URL,
                headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS,
                         "Content-Type": "application/json"},
                json={"textQuery": query, "languageCode": "en"},
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("places", [])
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(2 * (attempt + 1))  # backoff


def fetch(city, categories, key):
    """Return list of Signal dicts (one per review)."""
    signals = []
    for cat in categories:
        try:
            places = _search(f"{cat} in {city}", key)
        except requests.RequestException as e:
            print(f"  places search failed for {cat!r}: {e}", file=sys.stderr)
            continue
        for p in places:
            name = p.get("displayName", {}).get("text", "")
            phone = p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber")
            biz = {
                "place_id": p.get("id"), "phone": phone,
                "website": p.get("websiteUri"), "rating": p.get("rating"),
                "review_count": p.get("userRatingCount"),
                "category": p.get("primaryTypeDisplayName", {}).get("text"),
                "maps_uri": p.get("googleMapsUri"),
            }
            for i, rv in enumerate(p.get("reviews", [])):
                text = (rv.get("text") or {}).get("text", "").strip()
                if not text:
                    continue
                url = rv.get("googleMapsUri") or f"{biz['place_id']}#r{i}"
                signals.append({
                    "source": "google_reviews",
                    "who": name,
                    "text": text,
                    "source_url": url,
                    "location": p.get("formattedAddress"),
                    "posted_at": rv.get("publishTime"),
                    "raw": {**biz, "review_rating": rv.get("rating")},
                })
    return signals


def run():
    load_env()
    cfg = load_config()
    key = os.environ["GOOGLE_PLACES_KEY"]
    city = os.environ.get("CRAWL_CITY") or cfg["city"]
    print(f"Places: scanning {len(cfg['categories'])} categories in {city!r}")
    sigs = fetch(city, cfg["categories"], key)
    print(f"  collected {len(sigs)} review signals")
    with db.conn() as c:
        new = db.upsert_signals(c, sigs)
    print(f"  {new} new -> raw_signals ({len(sigs) - new} already seen)")
    return new


if __name__ == "__main__":
    run()
