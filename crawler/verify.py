"""VERIFY: validate phones and merge duplicate companies.

- phone_valid via Google's libphonenumber (phonenumbers), free/local.
- fuzzy-dedupe companies by normalized name; merge dupes, re-point signals.
"""
import sys, pathlib
import phonenumbers
from rapidfuzz import fuzz

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402

DEFAULT_REGION = "NP"  # fallback when a number has no +country code


def valid_phone(phone: str) -> bool:
    if not phone:
        return False
    try:
        p = phonenumbers.parse(phone, DEFAULT_REGION)
        return phonenumbers.is_valid_number(p)
    except phonenumbers.NumberParseException:
        return False


def run(dupe_threshold=92):
    load_env()
    load_config()
    with db.conn() as c:
        rows = c.execute("select id, name_norm, phone from companies").fetchall()

        # 1. phone validation
        checked = 0
        for cid, _, phone in rows:
            c.execute("update companies set phone_valid=%s where id=%s",
                      (valid_phone(phone), cid))
            checked += 1

        # 2. fuzzy dedupe: keep lowest id, merge others into it
        merged = 0
        seen = []  # (id, name_norm)
        for cid, name, _ in rows:
            match = next((kid for kid, kname in seen
                          if fuzz.token_sort_ratio(name, kname) >= dupe_threshold), None)
            if match:
                c.execute("update raw_signals set company_id=%s where company_id=%s",
                          (match, cid))
                c.execute("delete from companies where id=%s", (cid,))
                merged += 1
            else:
                seen.append((cid, name))
    print(f"verified: {checked} phones checked, {merged} duplicate companies merged")


def _selftest():
    assert valid_phone("+977 1-4221119")       # valid Nepal landline
    assert valid_phone("+14155552671")          # valid US
    assert not valid_phone("")
    assert not valid_phone("123")
    assert fuzz.token_sort_ratio("hair n shanti salon", "salon hair n shanti") >= 92
    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        run()
