"""Per-file tests for grade_live.py (settle live predictions from finals).

Uses injected finals (no network) + a temp ledger. Run:
python -m pytest scripts/platformkit/pm_trading/test_grade_live.py -q
"""
import pathlib
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import grade_live as G  # noqa: E402


def _seed_ledger():
    from scripts.platformkit.ledger.ledger import append_prediction
    led = tempfile.mkdtemp(prefix="pm_grade_")
    # two MLB predictions, leak-free vintage (pred day == game day is OK)
    append_prediction("mlb", "pregame", "ml", "PHI", "MIA", 0.61, {"i": 1},
                      "2026-06-16T15:00:00+00:00", game_date="2026-06-16",
                      game_id="G1", base_dir=led)
    append_prediction("mlb", "pregame", "ml", "SEA", "BAL", 0.71, {"i": 2},
                      "2026-06-16T15:00:00+00:00", game_date="2026-06-16",
                      game_id="G2", base_dir=led)
    return led


def test_grade_fills_outcomes_from_injected_finals():
    from scripts.platformkit.ledger.ledger import read_ledger
    led = _seed_ledger()
    s = G.grade_from_ledger(base_dir=led, finals={"G1": 1, "G2": 0})
    assert s["matched"] == 2 and s["filled"] == 2
    df = read_ledger(base_dir=led)
    by_gid = {r["game_id"]: r["outcome"] for _, r in df.iterrows()}
    assert int(by_gid["G1"]) == 1 and int(by_gid["G2"]) == 0


def test_missing_final_leaves_ungraded():
    from scripts.platformkit.ledger.ledger import read_ledger
    led = _seed_ledger()
    s = G.grade_from_ledger(base_dir=led, finals={"G1": 1})  # G2 not final yet
    assert s["filled"] == 1
    df = read_ledger(base_dir=led)
    g2 = df[df["game_id"] == "G2"].iloc[0]
    assert g2["outcome"] != g2["outcome"] or g2["outcome"] is None  # NaN/None


def test_idempotent_no_overwrite():
    from scripts.platformkit.ledger.ledger import read_ledger
    led = _seed_ledger()
    G.grade_from_ledger(base_dir=led, finals={"G1": 1, "G2": 0})
    # second pass tries to FLIP results; already-graded rows are excluded from
    # the ungraded set, so nothing re-grades (double-protected by grade_outcomes).
    s2 = G.grade_from_ledger(base_dir=led, finals={"G1": 0, "G2": 1})
    assert s2["filled"] == 0 and s2["ungraded"] == 0
    df = read_ledger(base_dir=led)
    by_gid = {r["game_id"]: int(r["outcome"]) for _, r in df.iterrows()}
    assert by_gid["G1"] == 1 and by_gid["G2"] == 0  # original values intact


def test_empty_ledger_safe():
    led = tempfile.mkdtemp(prefix="pm_grade_empty_")
    s = G.grade_from_ledger(base_dir=led, finals={"G1": 1})
    assert s["filled"] == 0 and s["ungraded"] == 0


def test_fetch_mlb_finals_offline_returns_empty():
    # invalid date path / offline tolerance -> {} not an exception
    out = G.fetch_mlb_finals(date="1900-01-01")
    assert isinstance(out, dict)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
