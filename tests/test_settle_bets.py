"""Tests for scripts/settle_bets.py — bet log + actuals -> P&L (cycle 69)."""
from __future__ import annotations

import csv
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.settle_bets as sb  # noqa: E402


def _bet(player, stat, line, side, odds=-110, kelly_stake=10.0,
          date="2026-05-24"):
    return {
        "timestamp": "2026-05-24T17:00", "date": date,
        "player": player, "stat": stat, "line": str(line),
        "side": side, "odds": str(odds), "kelly_stake": str(kelly_stake),
        "model": "0", "edge": "0", "prob": "0.55",
        "ev_per_dollar": "0.05", "kelly_pct": "1.0", "bankroll": "1000.00",
    }


def test_settle_returns_W_when_over_hits():
    """OVER 22.5 with actual 25.0 → win at -110 stake $10 → +$9.09 payout."""
    bet = _bet("Jokic", "PTS", 22.5, "OVER", odds=-110, kelly_stake=10.0)
    result, pnl = sb.settle(bet, actual=25.0)
    assert result == "W"
    # -110 payout for $10 stake = $10 * 100/110 = $9.0909
    assert pnl == pytest.approx(9.0909, abs=0.001)


def test_settle_returns_L_when_under_misses():
    """UNDER 22.5 with actual 25.0 → loss, stake $10 → -$10.0."""
    bet = _bet("Jokic", "PTS", 22.5, "UNDER", odds=-110, kelly_stake=10.0)
    result, pnl = sb.settle(bet, actual=25.0)
    assert result == "L"
    assert pnl == pytest.approx(-10.0)


def test_settle_returns_P_on_push():
    """Actual exactly equals line → push → pnl 0."""
    bet = _bet("Jokic", "PTS", 22.5, "OVER", odds=-110, kelly_stake=10.0)
    result, pnl = sb.settle(bet, actual=22.5)
    assert result == "P"
    assert pnl == 0.0


def test_settle_uses_flat_one_when_no_kelly_stake():
    bet = _bet("Jokic", "PTS", 22.5, "OVER", odds=-110, kelly_stake=0)
    bet["kelly_stake"] = ""    # no Kelly
    result, pnl = sb.settle(bet, actual=25.0)
    assert result == "W"
    # Flat $1 stake at -110 → $0.909 payout
    assert pnl == pytest.approx(0.9091, abs=0.001)


def test_settle_log_summary_arithmetic():
    """Mix of W / L / P / unmatched, verify summary fields."""
    bets = [
        _bet("Jokic", "PTS", 22.5, "OVER", kelly_stake=10),
        _bet("Curry", "FG3M", 4.5, "UNDER", kelly_stake=5),
        _bet("LeBron", "AST", 8.5, "OVER", kelly_stake=8),   # unmatched
        _bet("Tatum", "REB", 10.0, "OVER", kelly_stake=4),    # push
    ]
    actuals = {
        ("2026-05-24", "jokic",   "pts"):  25.0,   # over wins (+9.09)
        ("2026-05-24", "curry",   "fg3m"):  6.0,   # over hits → under loses (-5.0)
        # LeBron NOT in actuals — unmatched
        ("2026-05-24", "tatum",   "reb"):  10.0,   # push (0)
    }
    settled, s = sb.settle_log(bets, actuals)
    assert s["total"] == 4
    assert s["matched"] == 3
    assert s["unmatched"] == 1
    assert s["wins"] == 1
    assert s["losses"] == 1
    assert s["pushes"] == 1
    # PnL: +9.09 (Jokic) - 5.0 (Curry) + 0 (Tatum) = +4.09
    assert s["total_pnl"] == pytest.approx(4.0909, abs=0.001)
    # ROI on $10+$5+$4 = $19 stake → +4.09 / 19 = +21.5%
    assert s["roi_pct"] == pytest.approx(21.5, abs=0.1)


def test_load_actuals_normalizes_diacritics_and_case():
    """Player matching must work across 'Jokić' vs 'Jokic' vs 'JOKIC'."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv",
                                       encoding="utf-8") as fh:
        fh.write("date,player,stat,actual_value\n")
        fh.write("2026-05-24,Nikola Jokić,PTS,28.0\n")
        fh.write("2026-05-24,LEBRON JAMES,AST,11.0\n")
        path = fh.name
    try:
        out = sb.load_actuals(path)
    finally:
        os.unlink(path)
    # Both should be looked up by canonical key.
    assert ("2026-05-24", "nikola jokic", "pts") in out
    assert ("2026-05-24", "lebron james", "ast") in out


def test_load_actuals_returns_empty_on_missing_file():
    assert sb.load_actuals("/tmp/never_exists_xyz.csv") == {}


def test_write_settled_creates_dir_and_preserves_columns():
    bets = [_bet("Jokic", "PTS", 22.5, "OVER", kelly_stake=10)]
    actuals = {("2026-05-24", "jokic", "pts"): 25.0}
    settled, _ = sb.settle_log(bets, actuals)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "deep", "nested", "out.csv")
        n = sb.write_settled(out, settled)
        assert n == 1
        with open(out) as fh:
            row = next(csv.DictReader(fh))
        # Original columns preserved
        assert row["player"] == "Jokic"
        assert row["side"] == "OVER"
        # New columns present
        assert row["actual_value"] == "25"
        assert row["result"] == "W"
        assert "9.0909" in row["pnl"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
