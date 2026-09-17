"""Fee-netted markout over paper maker fills (audit 2026-09-17 defects #9/#3).

Run: python -m pytest tests/platformkit/execution/test_markout.py -q
"""
from __future__ import annotations

from scripts.platformkit.execution.markout import markout, markout_summary


def _fill(side="yes", price=0.65, fee=0.01, game="g1"):
    return {"side": side, "price": price, "fee_units": fee, "qty": 1, "game_id": game}


def test_fee_is_always_subtracted_never_credited():
    assert abs(markout(_fill(), 0.70) - 0.04) < 1e-9          # +5pp gross, -1pp fee
    assert abs(markout(_fill(fee=-0.01), 0.70) - 0.04) < 1e-9  # magnitude, not signed
    assert abs(markout(_fill(), 0.65) - (-0.01)) < 1e-9        # flat -> we paid the fee


def test_no_side_is_scored_against_the_complement_of_the_mid():
    assert abs(markout(_fill("no", 0.35), 0.60) - 0.04) < 1e-9
    assert abs(markout(_fill("no", 0.35), 0.70) - (-0.06)) < 1e-9


def test_unusable_input_returns_none_never_a_flat_zero():
    assert markout(_fill(), None) is None
    assert markout(_fill(), 1.4) is None
    assert markout({"side": "buy", "price": 0.5}, 0.5) is None
    assert markout("not a fill", 0.5) is None


def test_summary_ci_resamples_whole_games():
    # 12 games, 4 fills each, all +4pp net: a real positive CI.
    fills = [_fill(game="g%d" % g) for g in range(12) for _ in range(4)]
    out = markout_summary(fills, [0.70] * len(fills))
    assert out["n"] == 48 and out["n_clusters"] == 12
    assert abs(out["mean_units"] - 0.04) < 1e-9
    assert out["ci_95_units"][0] > 0.0 and out["verdict"] == "POSITIVE"
    assert out["units"] == "probability_points" and out["edge_claimed"] is False


def test_too_few_clusters_is_insufficient_not_a_verdict():
    fills = [_fill(game="g%d" % g) for g in range(3)]
    out = markout_summary(fills, [0.70] * 3)
    assert out["n"] == 3 and out["verdict"] == "INSUFFICIENT"
    assert out["ci_95_units"] == [None, None]


def test_one_game_cannot_carry_the_whole_sample():
    # The Q17b lesson: everything in one cluster -> the CI must not certify it.
    fills = [_fill(game="only") for _ in range(40)]
    assert markout_summary(fills, [0.70] * 40)["verdict"] == "INSUFFICIENT"


def test_unscorable_fills_are_counted_not_dropped():
    fills = [_fill(game="g%d" % g) for g in range(6)]
    out = markout_summary(fills, [0.70, 0.70, None, 0.70, 0.70, 0.70])
    assert out["n"] == 5 and out["n_unscored"] == 1


def test_negative_series_reports_negative():
    fills = [_fill(game="g%d" % g) for g in range(12) for _ in range(4)]
    out = markout_summary(fills, [0.58] * len(fills))
    assert out["mean_units"] < 0.0
    assert out["ci_95_units"][1] < 0.0 and out["verdict"] == "NEGATIVE"
