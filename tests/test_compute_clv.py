"""Tests for scripts/compute_clv.py — closing-line value tracker (cycle 75)."""
from __future__ import annotations

import csv
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.compute_clv as cc  # noqa: E402


def _bet(player, stat, line, side, odds=-110, kelly_stake=10.0):
    return {
        "timestamp": "2026-05-24T17:00", "date": "2026-05-24",
        "player": player, "stat": stat, "line": str(line),
        "side": side, "odds": str(odds), "kelly_stake": str(kelly_stake),
        "model": "0", "edge": "0", "prob": "0.55",
        "ev_per_dollar": "0.05", "kelly_pct": "1.0", "bankroll": "1000.00",
    }


def _close(line, over_odds=-110, under_odds=-110):
    return {"line": line, "over_odds": over_odds, "under_odds": under_odds}


# ── compute_one ──────────────────────────────────────────────────────────────

def test_over_bet_beats_close_when_line_moves_up():
    """LEGACY default-OFF behavior (clv_pts sign INVERTED, GRADING_SETTLE_CLV_AUDIT
    B-1). Kept as the byte-identical baseline: with CV_CLV_LINE_SIGN_FIX unset the
    OVER sign is placed-close, so OVER 22.5 vs close 21.5 -> +1.0. The CORRECT
    semantics (close 21.5 < placed 22.5 = a WORSE number for an OVER bettor ->
    negative) are asserted in TestClvSignFixCorrect under the flag."""
    bet = _bet("Jokic", "PTS", 22.5, "OVER", odds=-110)
    out = cc.compute_one(bet, _close(line=21.5))
    assert out["clv_pts"] == 1.0       # legacy (inverted) default
    assert out["beat_close"] == "Y"


def test_over_bet_loses_clv_when_line_moves_down_actually_means_close_above():
    """LEGACY default-OFF behavior (inverted). OVER 22.5 vs close 24.5 -> -2.0
    under the legacy sign; the CORRECT sign (close above placed = you got the
    better lower number = POSITIVE) is in TestClvSignFixCorrect."""
    bet = _bet("Jokic", "PTS", 22.5, "OVER", odds=-110)
    out = cc.compute_one(bet, _close(line=24.5))
    assert out["clv_pts"] == -2.0      # legacy (inverted) default
    assert out["beat_close"] == "N"


class TestClvSignFixCorrect:
    """CV_CLV_LINE_SIGN_FIX=1 -> the CORRECT CLV-line sign (B-1 fix). CLV is
    positive when you got a BETTER NUMBER than the close: OVER better = LOWER, so
    you beat the close when it closes HIGHER (closing - placed); UNDER better =
    HIGHER, so you beat when it closes LOWER (placed - closing)."""

    def test_over_close_above_is_positive(self, monkeypatch):
        monkeypatch.setenv("CV_CLV_LINE_SIGN_FIX", "1")
        bet = _bet("Jokic", "PTS", 22.5, "OVER", odds=-110)
        out = cc.compute_one(bet, _close(line=24.5))   # close ABOVE = favorable for OVER
        assert out["clv_pts"] == 2.0, "OVER beat the close (got the lower number) = positive"
        assert out["beat_close"] == "Y"

    def test_over_close_below_is_negative(self, monkeypatch):
        monkeypatch.setenv("CV_CLV_LINE_SIGN_FIX", "1")
        bet = _bet("Jokic", "PTS", 22.5, "OVER", odds=-110)
        out = cc.compute_one(bet, _close(line=21.5))   # close BELOW = unfavorable for OVER
        assert out["clv_pts"] == -1.0, "OVER lost CLV (close got the lower number)"
        assert out["beat_close"] == "N"

    def test_under_close_below_is_positive(self, monkeypatch):
        monkeypatch.setenv("CV_CLV_LINE_SIGN_FIX", "1")
        bet = _bet("Jokic", "PTS", 22.5, "UNDER", odds=-110)
        out = cc.compute_one(bet, _close(line=20.5))   # close BELOW = favorable for UNDER
        assert out["clv_pts"] == 2.0, "UNDER beat the close (got the higher number) = positive"
        assert out["beat_close"] == "Y"

    def test_under_close_above_is_negative(self, monkeypatch):
        monkeypatch.setenv("CV_CLV_LINE_SIGN_FIX", "1")
        bet = _bet("Jokic", "PTS", 22.5, "UNDER", odds=-110)
        out = cc.compute_one(bet, _close(line=24.5))   # close ABOVE = unfavorable for UNDER
        assert out["clv_pts"] == -2.0, "UNDER lost CLV (close got the higher number)"
        assert out["beat_close"] == "N"


def test_under_bet_beats_close_when_line_moves_up():
    """UNDER 22.5 → closing line moves UP to 24.5 means I got a 2-point cushion."""
    bet = _bet("Jokic", "PTS", 22.5, "UNDER", odds=-110)
    out = cc.compute_one(bet, _close(line=24.5))
    assert out["clv_pts"] == 2.0
    assert out["beat_close"] == "Y"


def test_clv_cents_positive_when_odds_get_worse():
    """My OVER -110 → closing OVER -130 means the price moved against the bet,
    so I got the better price (positive CLV cents)."""
    bet = _bet("Jokic", "PTS", 22.5, "OVER", odds=-110)
    out = cc.compute_one(bet, _close(line=22.5, over_odds=-130))
    # -110 implied 0.5238, -130 implied 0.5652 → cents = +4.14
    assert out["clv_cents"] == pytest.approx(4.14, abs=0.05)
    assert out["beat_close"] == "Y"


def test_clv_cents_negative_when_odds_get_better():
    """My OVER -110 → closing OVER +100 means I overpaid; negative CLV cents."""
    bet = _bet("Jokic", "PTS", 22.5, "OVER", odds=-110)
    out = cc.compute_one(bet, _close(line=22.5, over_odds=100))
    # -110 implied 0.5238, +100 implied 0.5000 → cents = -2.38
    assert out["clv_cents"] == pytest.approx(-2.38, abs=0.05)
    assert out["beat_close"] == "N"


# ── load_closing_lines ───────────────────────────────────────────────────────

def test_load_closing_lines_normalizes_keys():
    """Player names with diacritics + uppercase stat all normalize."""
    fh = tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv",
                                       encoding="utf-8")
    fh.write("player,opp,venue,stat,line,over_odds,under_odds\n")
    fh.write("Nikola Jokić,LAL,home,PTS,28.5,-115,-105\n")
    fh.write("LeBron James,DEN,away,reb,8.5,-110,-110\n")
    fh.close()
    try:
        out = cc.load_closing_lines(fh.name)
    finally:
        os.unlink(fh.name)
    # Diacritic-stripped + lowercase keys
    assert ("nikola jokic", "pts") in out
    assert ("lebron james", "reb") in out
    assert out[("nikola jokic", "pts")]["line"] == 28.5
    assert out[("nikola jokic", "pts")]["over_odds"] == -115


def test_load_closing_lines_returns_empty_on_missing():
    assert cc.load_closing_lines("/tmp/never_exists_xyz.csv") == {}


# ── compute_clv summary ──────────────────────────────────────────────────────

def test_compute_clv_summary_arithmetic():
    bets = [
        _bet("Jokic", "PTS", 22.5, "OVER"),           # closes 20.5 → +2.0 CLV beat
        _bet("Curry", "FG3M", 5.5, "UNDER"),         # closes 4.5 → -1.0 CLV loss
        _bet("Tatum", "REB", 9.5, "OVER"),            # closes 9.5 → 0 CLV miss
        _bet("LeBron", "AST", 7.5, "OVER"),           # no closing line → NA
    ]
    closing = {
        ("jokic", "pts"):   _close(20.5),
        ("curry", "fg3m"):  _close(4.5),
        ("tatum", "reb"):   _close(9.5),
        # LeBron missing
    }
    rows, summary = cc.compute_clv(bets, closing)
    assert summary["total"] == 4
    assert summary["matched"] == 3
    assert summary["unmatched"] == 1
    assert summary["beat_close"] == 1     # only Jokic
    assert summary["beat_pct"] == pytest.approx(33.33, abs=0.1)
    assert summary["mean_clv_pts"] == pytest.approx(2.0, abs=0.01)
    # Unmatched bet gets NA beat_close
    lebron = [r for r in rows if r["player"] == "LeBron"][0]
    assert lebron["beat_close"] == "NA"


def test_round_trip_through_csv():
    """Output CSV preserves all input cols + adds 5 CLV cols."""
    bets = [_bet("Jokic", "PTS", 22.5, "OVER")]
    closing = {("jokic", "pts"): _close(20.5)}
    rows, _ = cc.compute_clv(bets, closing)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "clv.csv")
        n = cc.write_csv(out, rows)
        assert n == 1
        with open(out) as fh:
            row = next(csv.DictReader(fh))
        # Original bet log columns preserved.
        assert row["player"] == "Jokic"
        assert row["side"] == "OVER"
        # CLV columns added.
        for col in ("closing_line", "closing_odds", "clv_pts",
                     "clv_cents", "beat_close"):
            assert col in row, f"missing {col}"
        assert row["beat_close"] == "Y"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
