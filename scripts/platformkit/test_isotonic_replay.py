"""Tests for offline isotonic corrected-path replay."""
from scripts.platformkit.isotonic_replay import replay


def _ticks():
    rows = []
    for day in range(8):
        stamp = "2026-04-%02dT12:00:00Z" % (day + 1)
        for suffix, probability, outcome in (("LOSS", 0.9, 0.0), ("WIN", 0.1, 1.0)):
            for tick in range(3):
                rows.append({"game": "KXMLBGAME%02d%s" % (day, suffix), "timestamp": stamp,
                             "model_prob": probability, "market_prob": 0.5, "outcome": outcome})
    return rows


def test_overconfident_series_improves_oos_brier_and_loser_peaks():
    result = replay(_ticks())
    summary = result["summary"]
    assert summary["oos_brier"]["corrected"] < summary["oos_brier"]["raw"]
    assert all(corrected < raw for raw, corrected in zip(
        summary["loser_peak_quantiles"]["raw"], summary["loser_peak_quantiles"]["corrected"]))
