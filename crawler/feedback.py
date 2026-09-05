"""Feedback loop: retune source_weights from real sales outcomes.

Win-rate per source (won / (won+lost)) -> a weight the Judge multiplies into
intent_score. More wins from a source => its future leads score higher.

Writes crawler/weights.json (an overlay load_config() merges over config.yaml
defaults), so hand-set defaults and comments stay intact. Sources with too few
decided leads keep their default weight — small samples don't move the dial.

ponytail: linear win-rate->weight heuristic. Swap for a trained model once
enough outcomes exist (plan Phase 9 "later"); the overlay interface won't change.
"""
import sys, json, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_env, load_config  # noqa: E402
import db  # noqa: E402

MIN_DECIDED = 5          # need this many won+lost before we trust a source
W_MIN, W_MAX = 0.5, 1.5  # clamp so one source can't dominate or vanish
OVERLAY = pathlib.Path(__file__).resolve().parent / "weights.json"


def weight_for(won, lost):
    """0.5..1.5 around neutral 1.0. win_rate 0->0.5, 0.5->1.0, 1.0->1.5."""
    rate = won / (won + lost)
    return round(max(W_MIN, min(W_MAX, 0.5 + rate)), 3)


def compute():
    """Return {source: weight} for sources with enough decided leads."""
    with db.conn() as c:
        rows = c.execute("""
            select source,
                   count(*) filter (where status = 'won')  as won,
                   count(*) filter (where status = 'lost') as lost
            from leads
            group by source
        """).fetchall()
    weights = {}
    for source, won, lost in rows:
        decided = (won or 0) + (lost or 0)
        if decided < MIN_DECIDED:
            print(f"  skip {source}: only {decided} decided (< {MIN_DECIDED})")
            continue
        w = weight_for(won, lost)
        weights[source] = w
        print(f"  {source}: {won}W/{lost}L -> weight {w}")
    return weights


def run():
    load_env()
    defaults = load_config()["source_weights"]
    print("== FEEDBACK == current weights:", defaults)
    tuned = compute()
    if not tuned:
        print("No source has enough outcomes yet; weights unchanged.")
        return
    OVERLAY.write_text(json.dumps(tuned, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OVERLAY.name}: {tuned}")


def _selfcheck():
    # more wins -> higher weight; all-loss floors at 0.5; all-win caps at 1.5
    assert weight_for(9, 1) > weight_for(1, 9)
    assert weight_for(0, 10) == W_MIN
    assert weight_for(10, 0) == W_MAX
    assert weight_for(5, 5) == 1.0
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        run()
