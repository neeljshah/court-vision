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


# ---------------------------------------------------------------------------
# New edge-case tests (cycle 54.5)
# ---------------------------------------------------------------------------

def _write_single_row(tmp_path, *, player, stat, line, over_odds=-110,
                      under_odds=-110, actual, date="2024-12-15",
                      opp="LAL", venue="home", fname="hist.csv"):
    path = tmp_path / fname
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "player", "opp", "venue", "stat",
                    "closing_line", "over_odds", "under_odds", "actual_value"])
        w.writerow([date, player, opp, venue, stat,
                    line, over_odds, under_odds, actual])
    return path


def test_push_handling_zero_pnl_and_counted(tmp_path, monkeypatch):
    """actual_value == closing_line -> 0 P&L, n_push=1, n_wins=0."""
    monkeypatch.setitem(
        _MOCK_PRED, ("Push Player", "pts"),
        {"pred": 30.0, "q": {"q10": 22.0, "q50": 30.0, "q90": 38.0}},
    )
    path = _write_single_row(
        tmp_path, player="Push Player", stat="pts",
        line=25.0, actual=25.0,  # push
    )
    s = bvc.run_backtest(
        str(path),
        threshold_edge=0.0,
        kelly=False,
        bankroll=100.0,
        predict_fn=_fake_predict,
        quantile_fn=_fake_quantile,
        progress=False,
    )
    assert s["n_rows"] == 1
    assert s["n_bets"] == 1            # bet was placed
    assert s["n_push"] == 1
    assert s["n_wins"] == 0
    assert s["total_pnl"] == pytest.approx(0.0)


def test_negative_ev_skip_when_prediction_matches_line(tmp_path, monkeypatch):
    """Force prob_over ~= 0.5 so both sides have negative EV; no bet placed."""
    # By patching _model_hit_prob to ~0.5 on both sides, EV at -110 is
    # 0.5*(100/110) - 0.5 = -0.0454 for both -> filtered.
    monkeypatch.setattr(
        bvc, "_model_hit_prob",
        lambda stat, pred, qint, line, side: 0.5,
    )
    monkeypatch.setitem(
        _MOCK_PRED, ("Coin Flip", "pts"),
        {"pred": 25.0, "q": {"q10": 18.0, "q50": 25.0, "q90": 32.0}},
    )
    path = _write_single_row(
        tmp_path, player="Coin Flip", stat="pts",
        line=25.0, actual=30.0,
    )
    s = bvc.run_backtest(
        str(path),
        threshold_edge=0.0,
        kelly=False,
        bankroll=100.0,
        predict_fn=_fake_predict,
        quantile_fn=_fake_quantile,
        progress=False,
    )
    assert s["n_rows"] == 1
    assert s["n_bets"] == 0
    assert s["total_pnl"] == pytest.approx(0.0)


def test_threshold_edge_filter_respects_signed_side(tmp_path, monkeypatch):
    """Edge +0.4 (OVER) filtered by threshold 0.5; UNDER with ev 0.6 bets.

    With -110 odds, b = 100/110 ~= 0.909. We craft prob_over=0.733 so that
    ev_over ~= 0.733*0.909 - 0.267 = 0.400 (below threshold 0.5), and
    prob_under = 0.838 so ev_under ~= 0.838*0.909 - 0.162 = 0.600 (above).
    """
    def _fake_hit(stat, pred, qint, line, side):
        return 0.7333 if side == "OVER" else 0.8380

    monkeypatch.setattr(bvc, "_model_hit_prob", _fake_hit)
    monkeypatch.setitem(
        _MOCK_PRED, ("Edge Player", "pts"),
        {"pred": 20.0, "q": {"q10": 14.0, "q50": 20.0, "q90": 26.0}},
    )
    # Actual below line so UNDER wins.
    path = _write_single_row(
        tmp_path, player="Edge Player", stat="pts",
        line=22.0, actual=18.0,
    )
    s = bvc.run_backtest(
        str(path),
        threshold_edge=0.5,
        kelly=False,
        bankroll=100.0,
        predict_fn=_fake_predict,
        quantile_fn=_fake_quantile,
        progress=False,
    )
    assert s["n_rows"] == 1
    assert s["n_bets"] == 1
    assert s["n_wins"] == 1
    # UNDER wins at -110 -> +0.909
    assert s["total_pnl"] == pytest.approx(100.0 / 110.0, rel=1e-6)
    assert s["bets"][0]["side"] == "UNDER"


def test_kelly_stake_floor_skips_when_fraction_nonpositive(tmp_path, monkeypatch):
    """Even with --kelly, a non-positive Kelly fraction -> row skipped."""
    # Force prob just above break-even so EV is positive (passes _decide_bet
    # at threshold 0.0) but Kelly fraction is essentially zero / negative.
    # With -110 odds b=0.909, break-even p = 1/(b+1) = 0.524.
    # Pick p_over = 0.5241 -> ev_over ~= 0.5241*0.909 - 0.4759 = +0.0006 (>0),
    # kelly fraction f = (b*p - q)/b = (0.909*0.5241 - 0.4759)/0.909 ~= +0.0007.
    # That's *positive* but stake = round(f*100, 2) = round(0.07, 2) = 0.07.
    # To actually trip the "stake <= 0" floor we need p exactly at b/(b+1),
    # so f rounds to 0.00. Use p=0.5238 -> f ~= -2e-4 -> max(0, f)=0 -> skip.
    def _fake_hit(stat, pred, qint, line, side):
        # OVER: positive EV but kelly fraction == 0.
        # UNDER: negative EV (filtered by threshold).
        if side == "OVER":
            return 0.5238
        return 1 - 0.5238

    monkeypatch.setattr(bvc, "_model_hit_prob", _fake_hit)
    # Force ev_over slightly positive but kelly = 0 by tweaking: simplest is
    # to use a small bankroll so 0 < f*bankroll < 0.005 rounds to 0.0.
    monkeypatch.setitem(
        _MOCK_PRED, ("Kelly Zero", "pts"),
        {"pred": 20.0, "q": {"q10": 14.0, "q50": 20.0, "q90": 26.0}},
    )
    path = _write_single_row(
        tmp_path, player="Kelly Zero", stat="pts",
        line=22.0, actual=25.0,
    )
    # Tiny bankroll so any positive Kelly fraction also rounds to $0.00.
    s = bvc.run_backtest(
        str(path),
        threshold_edge=-1.0,   # let positive-EV through the decide gate
        kelly=True,
        bankroll=0.01,         # f * 0.01 rounds to 0.00 -> stake <=0 -> skip
        predict_fn=_fake_predict,
        quantile_fn=_fake_quantile,
        progress=False,
    )
    assert s["n_rows"] == 1
    assert s["n_bets"] == 0
    assert s["total_pnl"] == pytest.approx(0.0)


def test_multi_stat_interleaved_per_stat_breakdown(tmp_path):
    """3 rows {pts, reb, ast} at distinct odds -> per_stat has 3 entries."""
    path = tmp_path / "multi.csv"
    rows = [
        # PTS at -110: model OVER, wins
        ("2024-12-15", "Multi Pts", "LAL", "home", "pts",  25.0, -110, -110, 30),
        # REB at +120: model OVER, loses
        ("2024-12-16", "Multi Reb", "BOS", "home", "reb",  10.0, +120, -150, 8),
        # AST at -130: model UNDER, wins
        ("2024-12-17", "Multi Ast", "NYK", "away", "ast",   8.5, -110, -130, 6),
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "player", "opp", "venue", "stat",
                    "closing_line", "over_odds", "under_odds", "actual_value"])
        for r in rows:
            w.writerow(r)

    # Mocks: clear OVER edge for pts & reb, clear UNDER edge for ast.
    extras = {
        ("Multi Pts", "pts"): {"pred": 30.0, "q": {"q10": 24.0, "q50": 30.0, "q90": 36.0}},
        ("Multi Reb", "reb"): {"pred": 13.0, "q": {"q10":  9.0, "q50": 13.0, "q90": 17.0}},
        ("Multi Ast", "ast"): {"pred":  6.5, "q": {"q10":  3.0, "q50":  6.5, "q90": 10.0}},
    }
    _MOCK_PRED.update(extras)
    try:
        s = bvc.run_backtest(
            str(path),
            threshold_edge=0.0,
            kelly=False,
            bankroll=100.0,
            predict_fn=_fake_predict,
            quantile_fn=_fake_quantile,
            progress=False,
        )
    finally:
        for k in extras:
            _MOCK_PRED.pop(k, None)

    assert s["n_rows"] == 3
    assert s["n_bets"] == 3
    # Per-stat breakdown has all 3 keys.
    assert set(s["per_stat"].keys()) == {"pts", "reb", "ast"}
    assert s["per_stat"]["pts"]["n_bets"] == 1
    assert s["per_stat"]["pts"]["n_wins"] == 1
    assert s["per_stat"]["reb"]["n_bets"] == 1
    assert s["per_stat"]["reb"]["n_wins"] == 0   # OVER on reb=8 vs line=10 -> lose
    assert s["per_stat"]["ast"]["n_bets"] == 1
    assert s["per_stat"]["ast"]["n_wins"] == 1
    # PTS pnl: WIN at -110 -> +100/110
    assert s["per_stat"]["pts"]["pnl"] == pytest.approx(100.0 / 110.0, rel=1e-6)
    # REB pnl: LOSS at +120 over_odds -> -1.0 flat
    assert s["per_stat"]["reb"]["pnl"] == pytest.approx(-1.0)
    # AST pnl: UNDER won at -130 -> +100/130
    assert s["per_stat"]["ast"]["pnl"] == pytest.approx(100.0 / 130.0, rel=1e-6)


def test_bets_list_records_side_odds_and_stake_per_row(tmp_path):
    """The returned `bets` list mirrors n_bets and carries side/odds/stake."""
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
    assert len(s["bets"]) == s["n_bets"] == 5
    sides = [b["side"] for b in s["bets"]]
    # 4 OVERs (rows 1-4) + 1 UNDER (Luka row 5)
    assert sides.count("OVER") == 4
    assert sides.count("UNDER") == 1
    # Each bet should carry a positive stake and a numeric prob in [0, 1].
    for b in s["bets"]:
        assert b["stake"] == pytest.approx(1.0)
        assert 0.0 <= b["prob"] <= 1.0
        assert b["odds"] in (-110,)
