"""Feedback loop: retune scoring weights from real sales outcomes.

Win rate per dimension -> a multiplier the scorers fold into intent_score.
More wins from a slice => its future leads score higher.

Grouped by **source, service AND category**, not source alone: with one live
source, a source-only weight is structurally incapable of learning anything.
"clinics convert at 40%, gyms at 5%" is actionable; "google_maps_gap converts
at 22%" is not.

Writes crawler/weights.json, an overlay load_config() merges over config.yaml
defaults, so hand-set defaults and comments stay intact. Slices with too few
decided leads keep the neutral weight; small samples must not move the dial.

ponytail: linear win-rate->weight heuristic. Swap for a trained model once
enough outcomes exist (plan Phase 9 "later"); the overlay interface won't change.
"""
import sys, json, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402

MIN_DECIDED = 5          # need this many won+lost before we trust a slice
W_MIN, W_MAX = 0.5, 1.5  # clamp so one slice can't dominate or vanish
NEUTRAL = 1.0
OVERLAY = pathlib.Path(__file__).resolve().parent / "weights.json"

# dimension -> the SQL expression that slices leads by it
DIMENSIONS = {
    "source":   "coalesce(l.source, \'-\')",
    "service":  "coalesce(l.service, \'-\')",
    "category": "coalesce(c.category, \'-\')",
}


def weight_for(won, lost):
    """0.5..1.5 around neutral 1.0. win_rate 0->0.5, 0.5->1.0, 1.0->1.5."""
    rate = won / (won + lost)
    return round(max(W_MIN, min(W_MAX, 0.5 + rate)), 3)


def tally(rows):
    """Pure: [(key, won, lost)] -> {key: weight}, skipping thin slices."""
    out = {}
    for key, won, lost in rows:
        decided = (won or 0) + (lost or 0)
        if decided < MIN_DECIDED:
            print(f"    skip {key}: only {decided} decided (< {MIN_DECIDED})")
            continue
        out[key] = weight_for(won or 0, lost or 0)
        print(f"    {key}: {won}W/{lost}L -> {out[key]}")
    return out


def compute():
    """{dimension: {key: weight}} for every slice with enough decided leads."""
    weights = {}
    with db.conn() as c:
        for dim, expr in DIMENSIONS.items():
            print(f"  by {dim}:")
            rows = c.execute(f"""
                select {expr} as key,
                       count(*) filter (where l.status = \'won\')  as won,
                       count(*) filter (where l.status = \'lost\') as lost
                from leads l left join companies c on c.id = l.company_id
                group by 1
            """).fetchall()
            got = tally(rows)
            if got:
                weights[dim] = got
    return weights


def run():
    load_env()
    cfg = load_config()
    print("== FEEDBACK == current:", {d: cfg.get(f"{d}_weights", {}) for d in DIMENSIONS})
    tuned = compute()
    if not tuned:
        print("No slice has enough outcomes yet; weights unchanged.")
        return
    OVERLAY.write_text(json.dumps(tuned, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OVERLAY.name}: {tuned}")


def _selfcheck():
    # more wins -> higher weight; all-loss floors; all-win caps
    assert weight_for(9, 1) > weight_for(1, 9)
    assert weight_for(0, 10) == W_MIN
    assert weight_for(10, 0) == W_MAX
    assert weight_for(5, 5) == NEUTRAL
    # thin slices are dropped, not neutralised, so config defaults survive
    assert tally([("gym", 1, 1), ("clinic", 4, 1)]) == {"clinic": 1.3}
    assert tally([]) == {}
    # nulls from the DB must not crash the arithmetic
    assert tally([("x", 5, None)]) == {"x": W_MAX}
    assert set(DIMENSIONS) == {"source", "service", "category"}
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        run()
