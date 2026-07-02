"""Per-file tests for clv_result_reconciler."""
from __future__ import annotations

from scripts.platformkit.clv.clv_result_reconciler import (
    _close_implied_expectation, _duplicate_close_pairs, _record, _verdict,
    _zscore, reconcile_channel)


def _row(side, taken_decimal, close_home, close_away, unit_result, fair_close_prob,
         event_id="e1", channel="paper_pm", stake_units=1.0, clv_pct=1.0):
    return {
        "channel": channel, "status": "settled", "side": side,
        "taken_decimal": taken_decimal,
        "closing_decimal_home": close_home, "closing_decimal_away": close_away,
        "fair_close_prob": fair_close_prob, "clv_pct": clv_pct,
        "clv_status": "true_close", "unit_result": unit_result,
        "stake_units": stake_units, "event_id": event_id,
        "bet_id": "b-%s-%s" % (event_id, side),
    }


def test_record_counts_wlp_and_units():
    rows = [
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5),
        _row("home", 2.0, 2.0, 2.0, -1.0, 0.5),
        _row("home", 2.0, 2.0, 2.0, 0.0, 0.5),
    ]
    rec = _record(rows)
    assert rec == {"wins": 1, "losses": 1, "pushes": 1, "net_units": 0.0}


def test_close_implied_expectation_matches_fair_prob():
    # A single fair-coin bet at decimal 2.0: E[units] = 0.5*1 - 0.5*1 = 0, E[wins]=0.5.
    rows = [_row("home", 2.0, 2.0, 2.0, 1.0, 0.5)]
    exp = _close_implied_expectation(rows)
    assert exp["n_used"] == 1
    assert exp["exp_wins"] == 0.5
    assert exp["exp_units"] == 0.0


def test_close_implied_expectation_skips_bad_rows():
    rows = [_row("home", 2.0, 2.0, 2.0, 1.0, 0.5)]
    bad = dict(rows[0])
    bad.pop("fair_close_prob")
    exp = _close_implied_expectation(rows + [bad])
    assert exp["n_used"] == 1  # bad row silently skipped, never crashes


def test_zscore_none_when_no_se():
    assert _zscore(5.0, 4.0, None) is None
    assert _zscore(5.0, 4.0, 0.0) is None
    assert _zscore(6.0, 4.0, 2.0) == 1.0


def test_verdict_insufficient_data_below_min_n():
    v = _verdict(3, 0.1, 0.1)
    assert v.startswith("INSUFFICIENT_DATA")


def test_verdict_genuine_variance_within_band():
    v = _verdict(20, -0.5, -1.2)
    assert v.startswith("GENUINE_VARIANCE")


def test_verdict_divergent_worse():
    v = _verdict(20, -2.5, -0.3)
    assert v.startswith("DIVERGENT")
    assert "WORSE" in v


def test_verdict_divergent_better():
    v = _verdict(20, 2.5, 0.3)
    assert v.startswith("DIVERGENT")
    assert "BETTER" in v


def test_duplicate_close_pairs_counts_cross_event_only():
    rows = [
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="g1"),
        _row("away", 2.0, 2.0, 2.0, -1.0, 0.5, event_id="g1"),   # same event -> not counted
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="g2"),    # different event, same pair
    ]
    assert _duplicate_close_pairs(rows) == 1


def test_reconcile_channel_genuine_variance_synthetic():
    # 20 fair-coin bets, roughly half win -> should read GENUINE_VARIANCE.
    rows = []
    for i in range(20):
        won = i % 2 == 0
        rows.append(_row(
            "home", 2.0, 2.0, 2.0,
            unit_result=(1.0 if won else -1.0), fair_close_prob=0.5,
            event_id="g%d" % i, clv_pct=2.0,
        ))
    report = reconcile_channel("paper_pm", ledger=rows)
    assert report["n_measurable"] == 20
    assert report["record"]["wins"] == 10
    assert report["verdict"].startswith("GENUINE_VARIANCE")


def test_reconcile_channel_insufficient_data_small_n():
    rows = [_row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="g1")]
    report = reconcile_channel("paper_pm", ledger=rows)
    assert report["n_measurable"] == 1
    assert report["verdict"].startswith("INSUFFICIENT_DATA")


def test_reconcile_channel_ignores_other_channels_and_unmeasurable():
    rows = [
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="g1", channel="paper"),
        {"channel": "paper_pm", "status": "settled", "clv_status": "no_close",
         "event_id": "g2", "bet_id": "b-g2"},
    ]
    report = reconcile_channel("paper_pm", ledger=rows)
    assert report["n_measurable"] == 0
    assert report["verdict"].startswith("INSUFFICIENT_DATA")
