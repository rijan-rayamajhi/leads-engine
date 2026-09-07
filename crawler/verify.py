"""VERIFY: validate phones and merge duplicate companies.

- phone_valid via Google's libphonenumber (phonenumbers), free/local.
- fuzzy-dedupe companies by normalized name; merge dupes, re-point signals.
"""
import sys, pathlib
import phonenumbers
from rapidfuzz import fuzz

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config
import db

# Fallback region for numbers with no +country code. Market-dependent, so it
# comes from config (phone_region), overridable via the settings table like city.
DEFAULT_REGION = "NP"


def valid_phone(phone: str, region: str = DEFAULT_REGION) -> bool:
    if not phone:
        return False
    try:
        p = phonenumbers.parse(phone, region)
        return phonenumbers.is_valid_number(p)
    except phonenumbers.NumberParseException:
        return False


def same_business(place_id_a, phone_a, place_id_b, phone_b) -> bool:
    """Corroboration for a name match. Same Places id is proof; same phone is
    strong enough. Neither present means we do not know, so we do not merge."""
    if place_id_a and place_id_b:
        return place_id_a == place_id_b
    a, b = national(phone_a), national(phone_b)
    # both must actually contain digits: two junk phones would otherwise both
    # normalise to "" and compare equal, merging two unrelated businesses.
    return bool(a) and a == b


def national(phone: str) -> str:
    """Last 10 digits: the same line reaches us as '+91 80 4173 8861' from
    internationalPhoneNumber and '080 4173 8861' from the national field, so
    comparing all digits would call one business two."""
    d = "".join(ch for ch in (phone or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else d


def run(dupe_threshold=92):
    load_env()
    region = load_config().get("phone_region", DEFAULT_REGION)
    with db.conn() as c:
        rows = c.execute(
            "select id, name_norm, phone, place_id from companies order by id").fetchall()

        # 1. phone validation
        checked = 0
        for cid, _, phone, _ in rows:
            c.execute("update companies set phone_valid=%s where id=%s",
                      (valid_phone(phone, region), cid))
            checked += 1

        # 2. fuzzy dedupe: keep lowest id, merge others into it.
        # P8: a similar name is NOT enough. "swarna tours and travels" and
        # "krishna tours and travels" score 86 against a 92 threshold and are
        # different businesses; a false merge puts another company's phone on a
        # lead, so identity must be corroborated by place_id or phone.
        merged = 0
        seen = []  # (id, name_norm, phone, place_id)
        for cid, name, phone, place_id in rows:
            match = next(
                (kid for kid, kname, kphone, kpid in seen
                 if fuzz.token_sort_ratio(name, kname) >= dupe_threshold
                 and same_business(place_id, phone, kpid, kphone)), None)
            if match:
                # Every referrer must move before the delete, or the leads FK
                # aborts the whole run. gap.py leads all carry a company_id.
                c.execute("update raw_signals set company_id=%s where company_id=%s",
                          (match, cid))
                c.execute("update leads set company_id=%s where company_id=%s",
                          (match, cid))
                c.execute("delete from companies where id=%s", (cid,))
                merged += 1
            else:
                seen.append((cid, name, phone, place_id))
    print(f"verified: {checked} phones checked, {merged} duplicate companies merged")
    return checked


def _selftest():
    assert valid_phone("+977 1-4221119")       # valid Nepal landline
    assert valid_phone("+14155552671")          # valid US
    assert not valid_phone("")
    assert not valid_phone("123")
    # region only matters without a country code, and that is the bug it fixes
    assert valid_phone("08041738861", "IN")
    assert not valid_phone("08041738861", "NP")
    assert fuzz.token_sort_ratio("hair n shanti salon", "salon hair n shanti") >= 92

    # P8: the same name is not enough on its own
    assert same_business("p1", None, "p1", None)          # same Places id: proof
    assert not same_business("p1", None, "p2", None)      # different listings
    assert same_business(None, "+91 80 4173 8861", None, "08041738861")
    assert not same_business(None, "+91 80 4173 8861", None, "+91 99019 30684")
    assert not same_business(None, None, None, None)      # unknown -> do not merge
    assert not same_business("p1", "x", None, "y")        # no digits either side
    assert not same_business(None, "", None, "")          # empty phones never match
    assert national("+91 80-4173 8861") == national("080 4173 8861") == "8041738861"
    assert national("123") == "123"          # too short to normalise, compared as-is
    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        run()
