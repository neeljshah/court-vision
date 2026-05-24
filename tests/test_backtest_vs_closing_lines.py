"""tests/test_backtest_vs_closing_lines.py — bet accounting + ROI math.

Mocks the production model + player-id resolver so the test runs offline in
under a second; the bet decision + settle logic is pure arithmetic.
"""
from __future__ import annotations

import csv
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts import backtest_vs_closing_lines as bvc


def _write_lines(tmp_path):
    path = tmp_path / "hist.csv"
    rows = [
        # date, player, opp, venue, stat, closing_line, over_odds, under_odds, actual_value
        ("2024-12-15", "Nikola Jokic",     "LAL", "home", "pts",  28.5, -110, -110, 32),  # model OVER, win
        ("2024-12-15", "Nikola Jokic",     "LAL", "home", "reb",  11.5, -110, -110, 14),  # model OVER, win
        ("2024-12-18", "Anthony Edwards",  "DEN", "away", "pts",  26.5, -110, -110, 24),  # model OVER, lose
        ("2024-12-20", "Jayson Tatum",     "NYK", "away", "ast",   5.5, -110, -110,  7),  # model OVER, win
        ("2024-12-22", "Luka Doncic",      "PHX", "home", "ast",   8.5, -110, -110,  6),  # model UNDER, win
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "player", "opp", "venue", "stat",
                    "closing_line", "over_odds", "under_odds", "actual_value"])
        for r in rows:
            w.writerow(r)
    return path


# Per-row deterministic model outputs: prediction + a wide-but-realistic
# q10/q50/q90 envelope so the calibrated normal gives confident probabilities.
_MOCK_PRED = {
    ("Nikola Jokic",    "pts"): {"pred": 31.0, "q": {"q10": 24.0, "q50": 31.0, "q90": 38.0}},  # >28.5 -> OVER
    ("Nikola Jokic",    "reb"): {"pred": 13.5, "q": {"q10":  9.0, "q50": 13.5, "q90": 18.0}},  # >11.5 -> OVER
    ("Anthony Edwards", "pts"): {"pred": 29.0, "q": {"q10": 22.0, "q50": 29.0, "q90": 36.0}},  # >26.5 -> OVER (loses, actual=24)
    ("Jayson Tatum",    "ast"): {"pred":  6.8, "q": {"q10":  3.0, "q50":  6.8, "q90": 10.5}},  # >5.5 -> OVER
    ("Luka Doncic",     "ast"): {"pred":  7.2, "q": {"q10":  3.5, "q50":  7.2, "q90": 11.0}},  # <8.5 -> UNDER
}


def _fake_predict(stat, prow, model_dir):
    name = prow.get("__player_name__")
    entry = _MOCK_PRED.get((name, stat))
    return entry["pred"] if entry else None


def _fake_quantile(stat, prow, model_dir):
    name = prow.get("__player_name__")
    entry = _MOCK_PRED.get((name, stat))
    return entry["q"] if entry else None


@pytest.fixture(autouse=True)
def _patch_io(monkeypatch):
    """Skip the slow nba_api roster fetch + gamelog file read.

    `_resolve_player_id` only needs to return *anything* non-None so the
    code path continues; `build_prediction_row` likewise just needs to
    yield a dict that the (mocked) predict_fn can read the player name
    out of.
    """
    monkeypatch.setattr(bvc, "_resolve_player_id",
                        lambda name: 1 if name else None)
    monkeypatch.setattr(bvc, "build_prediction_row",
                        lambda pid, opp, season, **kw: {
                            "__player_name__": kw.get("_player_name")
                        })

    # Wrap _score_row to inject the player name into the prow before
    # predict_fn sees it (build_prediction_row is mocked to read it).
    orig_score = bvc._score_row

    def _patched_score(row, gamelog_dir, model_dir,
                       predict_fn=None, quantile_fn=None):
        # Pre-resolve so the mocked build_prediction_row can stamp the name
        name = row["player"]
        original_bpr = bvc.build_prediction_row
        bvc.build_prediction_row = lambda *a, **kw: {
            "__player_name__": name
        }
        try:
            return orig_score(row, gamelog_dir, model_dir,
                              predict_fn=predict_fn, quantile_fn=quantile_fn)
        finally:
            bvc.build_prediction_row = original_bpr

    monkeypatch.setattr(bvc, "_score_row", _patched_score)


def test_backtest_records_expected_bets_and_roi(tmp_path):
    path = _write_lines(tmp_path)
    s = bvc.run_backtest(
        str(path),
        threshold_edge=0.0,
        kelly=False,
        bankroll=100.0,
        predict_fn=_fake_predict,
        quantile_fn=_fake_quantile,
        progress=False,
    )
    # All 5 rows should produce a bet — every mock has a clear edge
    assert s["n_rows"] == 5
    assert s["n_bets"] == 5
    # Wins: row 1 (Jokic pts), 2 (Jokic reb), 4 (Tatum ast), 5 (Luka UNDER ast). Loss: row 3 (Edwards pts).
    assert s["n_wins"] == 4

    # Flat $1 stake, -110 odds: each win = +0.909, each loss = -1.0
    # 4 wins, 1 loss -> P&L = 4 * 0.909 - 1.0 = 2.636
    assert s["total_stake"] == pytest.approx(5.0)
    assert s["total_pnl"]   == pytest.approx(4 * (100/110) - 1.0, rel=1e-6)
    # ROI = pnl / stake * 100
    expected_roi = 100.0 * s["total_pnl"] / s["total_stake"]
    assert s["roi_pct"] == pytest.approx(expected_roi, rel=1e-6)
    # Win % is 4/5 = 80
    assert s["win_pct"] == pytest.approx(80.0)

    # Per-stat breakdown
    assert s["per_stat"]["pts"]["n_bets"] == 2  # Jokic + Edwards
    assert s["per_stat"]["pts"]["n_wins"] == 1
    assert s["per_stat"]["reb"]["n_bets"] == 1
    assert s["per_stat"]["ast"]["n_bets"] == 2  # Tatum + Luka
    assert s["per_stat"]["ast"]["n_wins"] == 2


def test_backtest_threshold_edge_filters_marginal_bets(tmp_path):
    """A very high threshold should suppress every bet."""
    path = _write_lines(tmp_path)
    s = bvc.run_backtest(
        str(path),
        threshold_edge=10.0,    # impossible EV/$ — no bet should pass
        kelly=False,
        bankroll=100.0,
        predict_fn=_fake_predict,
        quantile_fn=_fake_quantile,
        progress=False,
    )
    assert s["n_bets"] == 0
    assert s["total_pnl"] == 0.0
    assert s["roi_pct"] == 0.0
