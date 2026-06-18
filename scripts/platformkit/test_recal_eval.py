"""Per-file test for scripts/platformkit/recal_eval (network-free, canned).

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_recal_eval.py -q
"""
from __future__ import annotations

from scripts.platformkit import recal_eval
from scripts.platformkit.recal_eval import _split_dates, _apply, run_eval


def test_split_dates_temporal_no_straddle():
    dates = ["d1", "d2", "d3", "d4"]  # 4 unique
    tr, te = _split_dates(dates, 0.65)  # round(2.6)=3 train, 1 test
    assert tr == {"d1", "d2", "d3"}
    assert te == {"d4"}
    assert tr.isdisjoint(te)  # no date in both


def test_split_dates_keeps_one_each_side():
    tr, te = _split_dates(["a", "b"], 0.99)  # would round to 2 train -> clamp 1
    assert len(tr) == 1 and len(te) == 1


def test_apply_uses_recal_on_test():
    # A fitted Shots map lifts the low region; an unfitted stat is identity.
    recal = {"Shots": {"x": [0.0, 0.5, 1.0], "y": [0.0, 0.9, 1.0], "n": 200}}
    pairs = [(0.5, 1), (0.0, 0)]
    out = _apply("Shots", pairs, recal)
    assert abs(out[0][0] - 0.9) < 1e-9   # 0.5 -> 0.9 via the map
    assert out[0][1] == 1                # outcome preserved
    ident = _apply("Goals", pairs, recal)  # not in table -> identity
    assert ident[0][0] == 0.5


def test_run_eval_on_canned_triples_split_sizes_and_no_raise(monkeypatch):
    # Stub backtest_pairs so the test is network/data-free. 4 dates; with
    # train_frac=0.5 -> 2 TRAIN dates, 2 TEST dates. Pairs route by date.
    triples = {
        "Shots": [
            (0.20, 0, "d1"), (0.30, 1, "d1"),
            (0.40, 0, "d2"), (0.50, 1, "d2"),
            (0.60, 1, "d3"), (0.25, 0, "d3"),
            (0.55, 1, "d4"), (0.35, 0, "d4"),
        ],
        "Goals": [(0.10, 0, "d1"), (0.90, 1, "d4")],
    }
    monkeypatch.setattr(recal_eval, "backtest_pairs",
                        lambda *a, **k: triples)
    res = run_eval(df=object(), train_frac=0.5)
    assert res["status"] == "ok"
    assert res["n_train_dates"] == 2 and res["n_test_dates"] == 2
    # Shots TEST pairs = the 4 from d3,d4; TRAIN = 4 from d1,d2.
    assert res["per_stat"]["Shots"]["n_test"] == 4
    assert res["per_stat"]["Shots"]["n_train"] == 4
    # Far below MIN_N -> nothing fitted -> recal stayed identity on TEST.
    assert res["fitted_oos_stats"] == []
    # identity recal => OOS delta is exactly zero (recal == raw).
    assert res["overall"]["oos_delta"]["brier"] == 0.0
    assert "DEFER" in res["verdict"]


def test_run_eval_empty_triples_never_raises(monkeypatch):
    # No pairs at all -> insufficient-dates status, never raises.
    monkeypatch.setattr(recal_eval, "backtest_pairs",
                        lambda *a, **k: {"Shots": []})
    out = run_eval(df=object(), train_frac=0.65)
    assert isinstance(out, dict) and out["status"] == "insufficient-dates"
