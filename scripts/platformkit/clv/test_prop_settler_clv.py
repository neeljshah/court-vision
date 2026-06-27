"""Tests for the prop_settler CLV hook (true_close when a captured prop close exists).

Per-file: python -m pytest scripts/platformkit/clv/test_prop_settler_clv.py -q
"""
from __future__ import annotations

from scripts.platformkit.bestbets import prop_settler as S


def _row(side="over", line=2.5, taken=1.90):
    return {"market_type": "prop", "status": "open", "sport": "mlb",
            "game_date": "2026-06-25", "prop_player": "Player A",
            "prop_stat": "Hits+Runs+RBIs", "line": line, "prop_side": side,
            "taken_decimal": taken, "stake_units": 1.0,
            "bet_id": "prop|2026-06-25|mlb|Player A|Hits+Runs+RBIs|2.5|over|dk"}


def test_no_close_fn_stays_no_close():
    s = S.settle_prop_row(_row(), realized=3.0)
    assert s["clv_status"] == "no_close"
    assert s["clv_pct"] is None and s["beat_close"] is None
    assert s["outcome"] == "win"  # realized 3 > line 2.5, over


def test_close_fn_yields_true_close_clv():
    # We took 1.90 (implied .526). Closing two-way 2.10/1.80 -> fair over < .526
    # in this devig -> negative CLV (took a worse-than-close price). Just assert the
    # CLV path fired and produced a real number + beat_close bool.
    close = {"over_dec": 2.10, "under_dec": 1.80, "source": "draftkings_live"}
    s = S.settle_prop_row(_row(side="over"), realized=3.0,
                          close_fn=lambda r: close)
    assert s["clv_status"] == "true_close"
    assert isinstance(s["clv_pct"], float)
    assert isinstance(s["beat_close"], bool)
    assert s["closing_decimal_home"] == 2.10  # Over
    assert s["closing_decimal_away"] == 1.80  # Under
    assert s["clv_is_proxy"] is False


def test_beat_close_true_when_taken_better_than_close():
    # Took 2.50 (cheap implied .40); closing two-way much shorter on over -> we beat it.
    close = {"over_dec": 1.50, "under_dec": 2.60, "source": "dk"}
    s = S.settle_prop_row(_row(side="over", taken=2.50), realized=3.0,
                          close_fn=lambda r: close)
    assert s["clv_status"] == "true_close"
    assert s["clv_pct"] > 0 and s["beat_close"] is True


def test_bad_close_falls_back_to_no_close():
    # close_fn raises -> settler must not crash, stays no_close
    def boom(r):
        raise RuntimeError("feed down")
    s = S.settle_prop_row(_row(), realized=3.0, close_fn=boom)
    assert s["clv_status"] == "no_close" and s["clv_pct"] is None
