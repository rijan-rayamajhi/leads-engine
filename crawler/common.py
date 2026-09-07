"""Shared helpers: load .env and config."""
import os, pathlib, re, unicodedata, yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_env():
    """Load ROOT/.env into os.environ (no override of existing vars)."""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_CONFIG = None


def load_config(refresh=False):
    """config.yaml, then two overlays: weights.json (feedback loop) and the
    settings table (dashboard). Memoised so one crawl sees one consistent config
    even if someone saves settings mid-run."""
    global _CONFIG
    if _CONFIG is not None and not refresh:
        return _CONFIG

    cfg = yaml.safe_load((ROOT / "crawler" / "config.yaml").read_text())

    # feedback loop writes crawler/weights.json; it overrides config defaults
    wf = ROOT / "crawler" / "weights.json"
    if wf.exists():
        import json
        cfg.setdefault("source_weights", {}).update(json.loads(wf.read_text()))

    # dashboard-editable settings win over the file; missing DB is not fatal,
    # the crawler just falls back to config.yaml.
    try:
        import db
        with db.conn() as c:
            for key, value in c.execute("select key, value from settings").fetchall():
                cfg[key] = value
    except Exception as e:
        print(f"  settings overlay unavailable ({type(e).__name__}); using config.yaml")

    _CONFIG = cfg
    return cfg


def norm_name(name: str) -> str:
    """Normalized company key. Shared by every writer of companies.name_norm:
    two spellings of one business must collapse to the same row.

    NFKD first, so an accented letter folds to its ASCII base instead of being
    stripped: without it "cafe" and "café" become different keys and the dedupe
    this function exists for silently fails."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).strip()


def _selfcheck_norm_name():
    assert norm_name("café amudham") == norm_name("cafe amudham") == "cafe amudham"
    assert norm_name("Anna\u2019s Boutique") == "anna s boutique"
    assert norm_name("#One Salon") == "one salon"
    assert norm_name("flux.fit gym") == "flux fit gym"
    assert norm_name(None) == "" and norm_name("") == ""
    assert norm_name(norm_name("A-B!")) == norm_name("A-B!")  # idempotent
    print("norm_name selfcheck ok")


if __name__ == "__main__":
    _selfcheck_norm_name()
