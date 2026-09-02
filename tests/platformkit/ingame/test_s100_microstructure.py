"""S100 per-file test -- the as-of guard, the touch imbalance, and the sign table.

No store on disk is read: every case is a hand-built frame.
Run: python -m pytest tests/platformkit/ingame/test_s100_microstructure.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s100_microstructure as s100


def _series():
    return [(10.0, "a"), (20.0, "b"), (30.0, "c")]


def test_as_of_is_strictly_before_the_tick():
    """THE guard: a row stamped AT the tick never reaches the feature."""
    assert s100.as_of(_series(), 20.0, 1e9) == (10.0, "a")
    assert s100.as_of(_series(), 20.001, 1e9) == (20.0, "b")
    assert s100.as_of(_series(), 10.0, 1e9) is None          # nothing precedes the first row


def test_as_of_respects_the_freshness_cap():
    assert s100.as_of(_series(), 35.0, 10.0) == (30.0, "c")
    assert s100.as_of(_series(), 45.0, 10.0) is None


@pytest.mark.parametrize("series", [
    [(50.0, "future"), (10.0, "past")], [(10.0, "a"), (60.0, "b"), (30.0, "c")],
    [(30.0, "a"), (5.0, "b"), (10.0, "c"), (40.0, "d")]])
def test_as_of_never_returns_a_row_at_or_after_the_tick(series):
    """The post-condition holds even on a mis-ordered series (it raises rather than leak)."""
    for when in (5.0, 10.0, 20.0, 30.0, 35.0, 50.0):
        try:
            hit = s100.as_of(series, when, 1e9)
        except s100.AsOfLeak:
            continue
        assert hit is None or hit[0] < when


def test_touch_imbalance_uses_the_best_price_on_each_ladder():
    # yes_asks is the RAW no_dollars ladder, so both sides take their MAX price.
    assert s100.touch_imbalance([[0.4, 30.0], [0.1, 999.0]], [[0.5, 10.0]]) == 0.5
    assert s100.touch_imbalance([], [[0.5, 10.0]]) is None
    assert s100.touch_imbalance([[0.4, 0.0]], [[0.5, 0.0]]) is None


def test_home_side_picks_the_trailing_team_code():
    assert s100.home_side("KXMLBGAME-26JUL111905KCBAL", ["KC", "BAL"]) == "BAL"
    assert s100.home_side("KXMLBGAME-26JUL071415MILSTLG1", ["MIL", "STL"]) == "STL"
    assert s100.home_side("KXMLBGAME-26JUL111905KCBAL", ["KC"]) is None


def _frame():
    return pd.DataFrame({
        "game": ["g1", "g1", "g1", "g2", "g2", "g2"],
        "d_market": [0.01, -0.01, 0.0, 0.02, -0.02, 0.01],
        "feat": [1.0, -1.0, 1.0, 1.0, -1.0, -1.0],
    })


def test_sign_accuracy_drops_held_quotes_and_clusters_by_game():
    row = s100.sign_accuracy(_frame(), "feat")
    assert row["n"] == 5 and row["n_games"] == 2 and row["n_zero_move_dropped"] == 1
    assert row["accuracy"] == pytest.approx(4.0 / 5.0)
    assert row["ci95_minus_half"][0] < row["accuracy"] - 0.5 < row["ci95_minus_half"][1]


def test_sign_accuracy_needs_two_clusters():
    one = _frame()[lambda f: f["game"] == "g1"]
    assert s100.sign_accuracy(one, "feat")["accuracy"] is None


def test_attach_features_reads_only_the_past_and_orients_the_away_ticker():
    ticks = pd.DataFrame({"game": ["KXMLBGAME-26JUL010000AAABBB"] * 2,
                          "t": [100.0, 200.0], "market": [0.5, 0.6]})
    sides = {"KXMLBGAME-26JUL010000AAABBB": {"away": "KXMLBGAME-26JUL010000AAABBB-AAA"}}
    ladders = {"KXMLBGAME-26JUL010000AAABBB-AAA": [(50.0, 0.4), (150.0, 0.8)]}
    out = s100.attach_features(ticks, {}, {}, ladders, sides, max_age=1000.0)
    # away ticker -> the sign flips; the second tick may not see its own 200.0 stamp
    assert list(out["depth_imbalance"]) == [-0.4, -0.8]
    assert list(out["imbalance_age_s"]) == [50.0, 50.0]
    assert out["spread_bp"].isna().all() and out["flow_60"].isna().all()


def test_attach_features_signs_trade_flow_over_the_window():
    ticks = pd.DataFrame({"game": ["E"] * 2, "t": [100.0, 500.0], "market": [0.5, 0.5]})
    trades = {"E-H": [(30.0, 1.0), (95.0, 1.0), (99.0, -1.0)]}
    out = s100.attach_features(ticks, {}, trades, {}, {"E": {"home": "E-H"}}, max_age=1000.0)
    assert list(out["last_trade_dir"]) == [-1.0, -1.0]
    assert out["flow_60"].tolist()[0] == 0.0        # (40s, 100s): +1 -1
    assert out["flow_300"].tolist()[0] == 1.0       # (-200s, 100s): +1 +1 -1
    assert pd.isna(out["flow_60"].tolist()[1])      # no trade in (440s, 500s)
