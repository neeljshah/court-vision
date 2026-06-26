"""Per-file tests for scripts.platformkit.pm_trading.scoreboard.

Run ONLY this file (full suite freezes the box):
    python -m pytest scripts/platformkit/pm_trading/test_scoreboard.py -q
"""
from __future__ import annotations

from scripts.platformkit.pm_trading.scoreboard import build_scoreboard


def _settled(sport, outcome, *, clv_pct=None, clv_is_proxy=False):
    r = {"status": "settled", "sport": sport, "outcome": outcome}
    if clv_pct is not None:
        r["clv_pct"] = clv_pct
        r["clv_is_proxy"] = clv_is_proxy
    return r


def test_n_settled_counts_all_settled_including_no_close():
    """The bug: a settled bet with no captured close (no clv_pct) was dropped from
    n_settled, so the UI showed 0 settled despite real settled bets. n_settled must
    count EVERY settled row; the no-close ones surface as n_no_close."""
    rows = [
        _settled("mlb", "win"),     # no close captured
        _settled("mlb", "loss"),    # no close captured
        _settled("soccer_intl", "push"),
        {"status": "open", "sport": "mlb"},   # not settled -> excluded
    ]
    b = build_scoreboard(rows=rows)
    assert b["n_settled"] == 3          # was 0 before the fix
    assert b["n_no_close"] == 3
    assert b["n_clv"] == 0
    # flat-unit record reflects the real settled outcomes, not just clv-bearing rows
    assert b["flat_unit_wins"] == 1
    assert b["flat_unit_losses"] == 1
    # no captured close -> CLV stats honestly null/insufficient, never fabricated
    assert b["mean_clv_pct"] == "INSUFFICIENT_DATA"
    assert b["pct_beat_close"] is None


def test_by_sport_counts_all_settled():
    rows = [
        _settled("mlb", "win"),
        _settled("mlb", "loss"),
        _settled("soccer_intl", "loss"),
    ]
    b = build_scoreboard(rows=rows)
    assert b["by_sport"]["mlb"]["n"] == 2
    assert b["by_sport"]["mlb"]["flat_unit_wins"] == 1
    assert b["by_sport"]["mlb"]["flat_unit_losses"] == 1
    assert b["by_sport"]["mlb"]["n_no_close"] == 2
    assert b["by_sport"]["soccer_intl"]["n"] == 1


def test_clv_stats_only_over_clv_subset():
    """When SOME rows have a close, n_settled still counts all; CLV stats use only
    the clv-bearing subset and pct_beat_close's denominator is that subset."""
    rows = [
        _settled("mlb", "win", clv_pct=2.0),     # beat close
        _settled("mlb", "loss", clv_pct=-1.0),   # missed close
        _settled("mlb", "win"),                  # no close -> excluded from CLV math
    ]
    b = build_scoreboard(rows=rows)
    assert b["n_settled"] == 3
    assert b["n_clv"] == 2          # only the two with a true close
    assert b["n_no_close"] == 1
    assert b["n_true_close"] == 2
    # 1 of 2 clv rows beat the close -> 50%, denominator is the clv subset (2), not 3
    assert b["pct_beat_close"] == 50.0
    assert b["flat_unit_wins"] == 2     # both wins count in the flat-unit record


def test_proxy_close_excluded_from_mean_but_counted():
    rows = [
        _settled("mlb", "win", clv_pct=3.0, clv_is_proxy=True),   # proxy: not in mean
        _settled("mlb", "loss", clv_pct=-2.0),                    # true close
    ]
    b = build_scoreboard(rows=rows)
    assert b["n_settled"] == 2
    assert b["n_proxy_close"] == 1
    assert b["n_true_close"] == 1
    # mean_clv_pct is over true closes only (the single -2.0), suppressed below MIN_CLV_N
    assert b["mean_clv_pct"] == "INSUFFICIENT_DATA"


def test_empty_ledger_is_zeros_not_a_crash():
    b = build_scoreboard(rows=[])
    assert b["n_settled"] == 0
    assert b["n_no_close"] == 0
    assert b["by_sport"] == {}
    assert b["mean_clv_pct"] == "INSUFFICIENT_DATA"
