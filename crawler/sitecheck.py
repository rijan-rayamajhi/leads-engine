"""Website health: turn a business's own site into verifiable evidence.

gap.py used to ask only "does Places have a websiteUri?", so 82% of harvested
businesses were invisible purely because a URL field was non-empty. A site that
does not load, has no TLS, or is a parked domain is a STRONGER lead than a
missing site: the owner already paid for something that is failing them.

Every issue carries a `base` score and a pitch line a rep can verify in one
look. Only claims that survive independent re-checking are here: measured on
237 Bangalore businesses, these signals corroborated 24/24.

Deliberately NOT checked:
  - HTTP 403: bot-blocking, says nothing about the site
  - missing viewport meta: misfired on the one JS-rendered site it flagged
    (Hard Rock Cafe), and a wrong claim on a call costs more than a missed lead
"""
import re, sys, concurrent.futures as cf
from typing import NamedTuple
import requests


class Issue(NamedTuple):
    """How bad the defect is, and the line a rep can say about it."""
    base: int
    pitch: str

# A real browser UA, because the question this module asks is literally "what
# does a customer's browser see?". A custom agent string gets blocked by common
# WAFs, which we then misread as a dead site (verified: one business returned
# 200 + 350KB to Chrome and a connection error to a bespoke agent).
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "en-US,en;q=0.9"}
TIMEOUT = 15
RETRIES = 1   # one retry: 12-way concurrency makes transient failures look fatal
SOCIAL = ("facebook.com", "instagram.com", "linktr.ee", "linktree")

# key -> Issue. Ordered strongest first; the worst issue wins.
ISSUES = {
    "dead":     Issue(72, "Their website does not load at all, so every search that finds them is a dead end."),
    "parked":   Issue(70, "Their domain is parked or for sale, so customers searching for them land on an ad page."),
    "server":   Issue(68, "Their website returns a server error, so customers cannot reach them online."),
    "notfound": Issue(66, "The website link on their Google listing opens a missing page, so customers hit a 404."),
    "ssl":      Issue(64, "Their site has a broken security certificate, so browsers warn customers away before they see it."),
    "http":     Issue(56, "Their site still serves over plain HTTP, so Chrome shows customers a Not Secure warning."),
    "empty":    Issue(52, "Their homepage is essentially blank, so there is nothing to convince a customer who arrives."),
}
ORDER = list(ISSUES)

PARKED_RE = re.compile(
    r"domain (?:is )?for sale|this domain is parked|buy this domain|"
    r"godaddy\.com/domains|sedo\.com/search|hugedomains", re.IGNORECASE)
def worst(issues):
    """The issue a rep should lead the call with, or None."""
    return next((k for k in ORDER if k in issues), None)


def classify(status_code, final_url, html, err=None):
    """Pure: map one fetch result to a list of issue keys. Testable offline."""
    if err == "ssl":
        return ["ssl"]
    if err:
        return ["dead"]
    if status_code == 403:
        return []                       # blocked us, says nothing about the site
    if status_code and status_code >= 500:
        return ["server"]
    if status_code == 404:
        # Their site may be fine; the URL Google sends customers to is not.
        # Still a real, checkable problem, but a different pitch from a dead host.
        return ["notfound"]
    if status_code and status_code >= 400:
        return ["dead"]
    issues = []
    if PARKED_RE.search(html or ""):
        issues.append("parked")
    if final_url and not final_url.lower().startswith("https"):
        issues.append("http")
    if len(html or "") < 1500:
        issues.append("empty")
    return issues


def check(url):
    """Fetch one homepage and classify it. Never raises.

    "Unreachable" is the claim most likely to embarrass a rep on a call, so it
    has to survive a retry before we assert it.
    """
    err = None
    for _ in range(RETRIES + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT, headers=UA, allow_redirects=True)
            return classify(r.status_code, str(r.url), r.text[:200_000])
        except requests.exceptions.SSLError:
            err = "ssl"          # a cert does not fix itself on retry
            break
        except requests.RequestException:
            err = "dead"
    return classify(None, None, None, err=err)


def check_many(urls, workers=12):
    """{url: [issue keys]} for many sites at once.Network-bound, so threads."""
    with cf.ThreadPoolExecutor(workers) as ex:
        return dict(zip(urls, ex.map(check, urls), strict=True))


def is_social(website):
    return bool(website) and any(s in website.lower() for s in SOCIAL)


def _selfcheck():
    # unambiguous defects
    assert classify(None, None, None, err="dead") == ["dead"]
    assert classify(None, None, None, err="ssl") == ["ssl"]
    assert classify(503, "https://x.com", "<html>" + "x" * 2000) == ["server"]
    # 404 is a broken listing link, not a dead host: different pitch, lower score
    assert classify(404, "https://x.com", "") == ["notfound"]
    assert ISSUES["notfound"][0] < ISSUES["dead"][0]
    assert classify(410, "https://x.com", "") == ["dead"]
    # 403 is bot-blocking, not a lead
    assert classify(403, "https://x.com", "") == []
    # plain HTTP on a real page
    full = "<html><body>" + "x" * 2000
    assert classify(200, "http://x.com", full) == ["http"]
    assert classify(200, "https://x.com", full) == []
    assert classify(200, "https://x.com", "<html></html>") == ["empty"]
    # a real page with no other defect is NOT a lead, viewport meta or not
    assert classify(200, "https://x.com", "<html>" + "x" * 2000) == []
    # parked wins over everything below it
    assert worst(classify(200, "http://x.com", "buy this domain " + "x" * 2000)) == "parked"
    # severity order holds, and every issue has a pitch
    assert worst(["empty", "dead"]) == "dead"
    assert worst([]) is None
    assert all(k in ISSUES for k in ORDER) and len(ORDER) == len(ISSUES)
    assert all(0 < ISSUES[k].base <= 100 and ISSUES[k].pitch.endswith(".") for k in ISSUES)
    # severity must strictly descend, or `worst` and the score disagree
    scores = [ISSUES[k].base for k in ORDER]
    assert scores == sorted(scores, reverse=True), scores
    assert is_social("https://facebook.com/x") and not is_social("https://acme.com")
    print("sitecheck selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    elif len(sys.argv) > 1:
        for u in sys.argv[1:]:
            iss = check(u)
            print(f"{u}: {iss or 'healthy'}" + (f"  -> {ISSUES[worst(iss)].pitch}" if iss else ""))
