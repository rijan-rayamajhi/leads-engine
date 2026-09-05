"""Shared helpers: load .env and config."""
import os, pathlib, yaml

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


def load_config():
    cfg = yaml.safe_load((ROOT / "crawler" / "config.yaml").read_text())
    # feedback loop writes crawler/weights.json; it overrides config defaults
    wf = ROOT / "crawler" / "weights.json"
    if wf.exists():
        import json
        cfg.setdefault("source_weights", {}).update(json.loads(wf.read_text()))
    return cfg
