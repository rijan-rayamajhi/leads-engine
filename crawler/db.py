"""Postgres (Neon) access: connection + upsert helpers. DATABASE_URL from env."""
import os, json
import psycopg

def conn():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg.connect(dsn, autocommit=True)


def ping() -> bool:
    """Cheap connectivity check for Phase 1 verify."""
    with conn() as c:
        c.execute("select 1")
    print("db ok")
    return True


def upsert_signal(c, sig: dict) -> bool:
    """Insert a raw signal; skip if source_url already seen. Returns True if new."""
    cur = c.execute(
        """insert into raw_signals (source, who, body, source_url, location, posted_at, raw)
           values (%s,%s,%s,%s,%s,%s,%s)
           on conflict (source_url) do nothing
           returning id""",
        (sig["source"], sig.get("who"), sig.get("text"), sig["source_url"],
         sig.get("location"), sig.get("posted_at"), json.dumps(sig.get("raw") or {})),
    )
    return cur.fetchone() is not None


def upsert_signals(c, sigs: list[dict], chunk=100) -> int:
    """Batch-insert signals (multi-row, on-conflict skip). Returns new-row count."""
    new = 0
    for i in range(0, len(sigs), chunk):
        batch = sigs[i:i + chunk]
        rows = [(s["source"], s.get("who"), s.get("text"), s["source_url"],
                 s.get("location"), s.get("posted_at"), json.dumps(s.get("raw") or {}))
                for s in batch]
        vals = ",".join(["(%s,%s,%s,%s,%s,%s,%s)"] * len(rows))
        flat = [x for r in rows for x in r]
        cur = c.execute(
            f"""insert into raw_signals
                (source, who, body, source_url, location, posted_at, raw)
                values {vals} on conflict (source_url) do nothing""",
            flat,
        )
        new += cur.rowcount
    return new


def upsert_company(c, name_norm, **fields):
    """Insert or update a company by normalized name. Returns company id."""
    cols = ["name_norm"] + list(fields)
    vals = [name_norm] + list(fields.values())
    placeholders = ",".join(["%s"] * len(vals))
    updates = ",".join(f"{k}=excluded.{k}" for k in fields) or "name_norm=excluded.name_norm"
    cur = c.execute(
        f"""insert into companies ({",".join(cols)}) values ({placeholders})
            on conflict (name_norm) do update set {updates}
            returning id""",
        vals,
    )
    return cur.fetchone()[0]


def insert_lead(c, **fields):
    cols = ",".join(fields)
    placeholders = ",".join(["%s"] * len(fields))
    cur = c.execute(
        f"insert into leads ({cols}) values ({placeholders}) returning id",
        list(fields.values()),
    )
    return cur.fetchone()[0]


if __name__ == "__main__":
    ping()


def start_run(c, job: str, city: str | None = None) -> int:
    """Open a run row. finished_at stays null until finish_run, so a killed job
    is visibly different from a job that never started."""
    cur = c.execute(
        "insert into runs (job, city) values (%s,%s) returning id", (job, city))
    return cur.fetchone()[0]


def finish_run(c, run_id, signals_new=None, leads_new=None, stats=None, error=None):
    c.execute(
        """update runs set finished_at=now(), signals_new=%s, leads_new=%s,
                           stats=%s, error=%s where id=%s""",
        (signals_new, leads_new, json.dumps(stats or {}), error, run_id))
