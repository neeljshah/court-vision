"""Tests for scripts/nightly_report.py (cycle 73)."""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.nightly_report as nr  # noqa: E402


# ── section_predictions ──────────────────────────────────────────────────────

def test_section_predictions_empty():
    out = nr.section_predictions([])
    assert "no predictions" in out


def test_section_predictions_aggregates_by_stat():
    rows = [
        {"player_id": "1", "game_id": "g1", "stat": "pts", "pred": "25.0"},
        {"player_id": "2", "game_id": "g1", "stat": "pts", "pred": "30.0"},
        {"player_id": "1", "game_id": "g1", "stat": "reb", "pred": "10.0"},
    ]
    out = nr.section_predictions(rows)
    assert "Total rows: **3**" in out
    assert "Unique players: **2**" in out
    assert "Games: **1**" in out
    # Mean PTS = 27.5
    assert "| PTS | 2 | 27.50 |" in out


# ── section_injuries ─────────────────────────────────────────────────────────

def test_section_injuries_empty():
    out = nr.section_injuries({})
    assert "no injury report" in out


def test_section_injuries_counts_by_status():
    payload = {
        "source_pdf": "ESPN", "fetched_at": "2026-05-24T17:00",
        "players": [
            {"team": "LAL", "name": "X", "status": "OUT", "reason": ""},
            {"team": "LAL", "name": "Y", "status": "DOUBTFUL", "reason": ""},
            {"team": "DEN", "name": "Z", "status": "OUT", "reason": ""},
        ],
    }
    out = nr.section_injuries(payload)
    assert "Players listed: **3**" in out
    assert "| OUT | 2 |" in out
    assert "| DOUBTFUL | 1 |" in out
    assert "ESPN" in out


# ── section_lineups ──────────────────────────────────────────────────────────

def test_section_lineups_counts_starters_and_status():
    payload = {
        "games": [
            {
                "home_team": "LAL", "away_team": "DEN",
                "home_lineup": {"status": "Confirmed", "starters": [{"name": f"S{i}"} for i in range(5)]},
                "away_lineup": {"status": "Expected", "starters": [{"name": f"S{i}"} for i in range(5)]},
            },
            {
                "home_team": "BOS", "away_team": "NYK",
                "home_lineup": {"status": "Expected", "starters": [{"name": f"H{i}"} for i in range(4)]},
                "away_lineup": {"status": "Projected", "starters": [{"name": f"A{i}"} for i in range(5)]},
            },
        ],
    }
    out = nr.section_lineups(payload)
    assert "Games covered: **2**" in out
    # 5+5 + 4+5 = 19
    assert "Total projected starters: **19**" in out
    assert "| Confirmed | 1 |" in out
    assert "| Expected | 2 |" in out
    assert "| Projected | 1 |" in out


# ── section_bets ─────────────────────────────────────────────────────────────

def test_section_bets_top_5_ranked_by_ev():
    rows = [
        {"player": f"P{i}", "stat": "pts", "line": "20.5", "side": "OVER",
         "edge": "1.0", "ev_per_dollar": str(0.10 - i * 0.01),
         "kelly_pct": "1.0", "kelly_stake": "10.0"}
        for i in range(8)
    ]
    out = nr.section_bets(rows)
    assert "Total bets logged: **8**" in out
    assert "Total Kelly stake: **$80.00**" in out
    # Top row should be P0 (highest EV 0.10), bottom of top-5 is P4 (EV 0.06).
    p0_idx = out.find("| P0 |")
    p4_idx = out.find("| P4 |")
    p5_idx = out.find("| P5 |")
    assert p0_idx > 0 and p0_idx < p4_idx     # P0 above P4
    # P5 not in top-5
    assert p5_idx == -1


# ── section_settled ──────────────────────────────────────────────────────────

def test_section_settled_record_and_pnl():
    rows = [
        {"player": "Jokic", "stat": "PTS", "line": "22.5", "side": "OVER",
         "result": "W", "pnl": "+9.09"},
        {"player": "Curry", "stat": "FG3M", "line": "4.5", "side": "UNDER",
         "result": "L", "pnl": "-10.00"},
        {"player": "Tatum", "stat": "REB", "line": "10.0", "side": "OVER",
         "result": "P", "pnl": "0.00"},
        {"player": "LeBron", "stat": "AST", "line": "8.5", "side": "OVER",
         "result": "NA", "pnl": ""},   # unmatched, no actuals
    ]
    out = nr.section_settled(rows)
    assert "Bets matched: **3** / 4 logged" in out
    assert "**1-1-1**" in out
    assert "Win rate: **50.0%**" in out
    # Total P&L = +9.09 - 10.00 + 0 = -0.91
    assert "-0.91" in out
    # Top wins / losses appear
    assert "Jokic" in out      # in wins section
    assert "Curry" in out      # in losses section


def test_section_settled_no_settled_file():
    out = nr.section_settled([])
    assert "no settled file" in out


# ── build_report end-to-end ──────────────────────────────────────────────────

def test_build_report_handles_all_missing_data():
    """If every artifact is missing, sections all show their 'no data' lines
    but the report still builds cleanly."""
    out = nr.build_report("2099-01-01")
    assert out.startswith("# NBA prediction report — 2099-01-01")
    # Every section's missing-data marker is present.
    assert "no predictions" in out
    assert "no injury report" in out
    assert "no lineup data" in out
    assert "no bets logged" in out
    assert "no settled file" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
