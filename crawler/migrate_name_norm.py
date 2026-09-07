"""One-off: renormalize companies.name_norm and merge the rows that collide.

gap.py used to write a bare `who.lower().strip()` while enrich.py wrote the
punctuation-stripped norm_name(), so one business could hold two company rows.
Both writers now share common.norm_name; this brings existing rows in line.

  python migrate_name_norm.py            # dry run, prints the plan
  python migrate_name_norm.py --apply    # do it
"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, norm_name
import db


def plan(rows):
    """Group company ids by their renormalized key. Lowest id survives."""
    groups = {}
    for cid, name in rows:
        groups.setdefault(norm_name(name), []).append(cid)
    renames, merges = [], []
    for key, ids in groups.items():
        ids.sort()
        keep = ids[0]
        if len(ids) > 1:
            merges.append((keep, ids[1:]))
        current = next(n for c, n in rows if c == keep)
        if current != key:
            renames.append((keep, current, key))
    return renames, merges


def run(apply=False):
    load_env()
    with db.conn() as c:
        rows = c.execute("select id, name_norm from companies order by id").fetchall()
        renames, merges = plan(rows)

        print(f"{len(rows)} companies: {len(renames)} to rename, {len(merges)} groups to merge")
        for keep, drop in merges:
            print(f"  merge {drop} -> {keep}")
        for cid, old, new in renames:
            print(f"  rename {cid}: {old!r} -> {new!r}")
        if not apply:
            print("\ndry run, nothing written. Re-run with --apply.")
            return

        # Merge before rename: dropping the duplicates first frees the unique key.
        for keep, drop in merges:
            c.execute("update raw_signals set company_id=%s where company_id = any(%s)", (keep, drop))
            c.execute("update leads       set company_id=%s where company_id = any(%s)", (keep, drop))
            c.execute("delete from companies where id = any(%s)", (drop,))
        for cid, _, new in renames:
            c.execute("update companies set name_norm=%s where id=%s", (new, cid))
        print(f"applied: {sum(len(d) for _, d in merges)} rows merged, {len(renames)} renamed")


def _selfcheck():
    rows = [(1, "acme cafe"), (2, "acme-cafe!"), (3, "acme  cafe "), (4, "other")]
    renames, merges = plan(rows)
    assert merges == [(1, [2, 3])], merges          # all three collapse onto id 1
    assert renames == [], renames                    # id 1 already holds the key
    rows = [(5, "fit24 gym - the best")]
    renames, merges = plan(rows)
    assert merges == [] and renames == [(5, "fit24 gym - the best", "fit24 gym the best")]
    assert norm_name(norm_name("A-B!")) == norm_name("A-B!")  # idempotent
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        run(apply="--apply" in sys.argv)
