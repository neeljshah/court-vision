"""Tests for scripts/live_player.py (cycle 88m)."""
from __future__ import annotations

import csv
import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.live_player as lp  # noqa: E402


# ── project_final (pure pace + adjustments) ───────────────────────────────

def test_project_final_doubles_at_half_no_adjustments():
    assert lp.project_final(12.0, 0.5) == pytest.approx(24.0)


def test_project_final_zero_share_returns_current():
    assert lp.project_final(10.0, 0.0) == 10.0


def test_project_final_low_share_clamped():
    """Don't divide by tiny share -> absurd projection."""
    # share clamps at 0.05 -> remaining 0.95 -> 5.0 * (1/0.05) * 0.95 = 95
    assert lp.project_final(5.0, 0.01) == pytest.approx(100.0, abs=0.5)


def test_project_final_with_foul_factor():
    """foul_factor scales remaining-stat contribution only, not the already-played."""
    # 0.5 share -> remaining = 12, foul 0.5 -> remaining contributes 6 -> total 18
    assert lp.project_final(12.0, 0.5, foul_factor=0.5) == pytest.approx(18.0)


def test_project_final_with_blowout_factor_compounds():
    """Both factors multiply on the REMAINING portion."""
    # 0.5 share -> remaining = 12 base -> * 0.5 * 0.5 = 3 -> total 15
    assert lp.project_final(12.0, 0.5, foul_factor=0.5,
                              blowout_factor=0.5) == pytest.approx(15.0)


# ── foul_factor_for ────────────────────────────────────────────────────────

def test_foul_factor_table():
    # 5+ fouls
    assert lp.foul_factor_for(5, 3, 10.0) == 0.40
    assert lp.foul_factor_for(6, 4, 2.0) == 0.40
    # 4 fouls in Q3
    assert lp.foul_factor_for(4, 3, 5.0) == 0.55
    # 4 fouls Q4 with > 6 min left
    assert lp.foul_factor_for(4, 4, 8.0) == 0.65
    # 4 fouls late Q4
    assert lp.foul_factor_for(4, 4, 4.0) == 0.90
    # 3 fouls in Q2
    assert lp.foul_factor_for(3, 2, 8.0) == 0.80
    # baseline
    assert lp.foul_factor_for(0, 2, 8.0) == 1.0
    assert lp.foul_factor_for(2, 4, 8.0) == 1.0


# ── blowout_factor_for ────────────────────────────────────────────────────

def test_blowout_factor_pre_q4_returns_one():
    assert lp.blowout_factor_for(30, 1, 12.0, True, True) == 1.0
    assert lp.blowout_factor_for(30, 3, 12.0, True, True) == 1.0


def test_blowout_factor_close_q4_returns_one():
    """Even in Q4, a 10-point game isn't a blowout yet."""
    assert lp.blowout_factor_for(10, 4, 6.0, True, True) == 1.0


def test_blowout_factor_starter_on_leading_team_scales_down():
    # 20-pt margin Q4 starter on leading team -> 0.55
    assert lp.blowout_factor_for(20, 4, 8.0, True, True) == 0.55
    # 30+ pt blowout -> 0.25
    assert lp.blowout_factor_for(30, 4, 8.0, True, True) == 0.25


def test_blowout_factor_losing_starter_keeps_playing():
    """Down 25 in Q4, the LOSING starters chase — keep playing."""
    assert lp.blowout_factor_for(25, 4, 8.0, True, False) == 1.0


def test_blowout_factor_bench_gets_garbage_time_boost():
    """Down/Up 25 in Q4, bench player on either team gets extra minutes."""
    assert lp.blowout_factor_for(25, 4, 8.0, False, True) == 1.30
    assert lp.blowout_factor_for(35, 4, 8.0, False, False) == 1.50


# ── ledger + bet log loaders ─────────────────────────────────────────────

def _write_pred_ledger(tmp: str, date_str: str, rows):
    pred_dir = os.path.join(tmp, "data", "predictions")
    os.makedirs(pred_dir)
    path = os.path.join(pred_dir, f"{date_str}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "game_id", "player_id", "player", "team",
                    "opp", "venue", "stat", "pred"])
        for r in rows:
            w.writerow(r)
    return path


def test_load_pre_game_for_player_filters_to_one_player():
    with tempfile.TemporaryDirectory() as tmp:
        _write_pred_ledger(tmp, "2026-05-24", [
            ["2026-05-24", "g1", "1", "Nikola Jokic", "DEN", "LAL", "home", "pts", "28.5"],
            ["2026-05-24", "g1", "1", "Nikola Jokic", "DEN", "LAL", "home", "reb", "12.1"],
            ["2026-05-24", "g1", "2", "LeBron James", "LAL", "DEN", "home", "pts", "25.0"],
        ])
        out = lp.load_pre_game_for_player("Nikola Jokic", "2026-05-24",
                                              project_dir=tmp)
    assert out == {"pts": 28.5, "reb": 12.1}


def test_load_pre_game_diacritic_insensitive():
    """Lookup matches 'Jokić' to 'Jokic' rows in the ledger."""
    with tempfile.TemporaryDirectory() as tmp:
        _write_pred_ledger(tmp, "2026-05-24", [
            ["2026-05-24", "g1", "1", "Nikola Jokić", "DEN", "LAL", "home", "pts", "28.5"],
        ])
        out = lp.load_pre_game_for_player("Nikola Jokic", "2026-05-24",
                                              project_dir=tmp)
    assert out == {"pts": 28.5}


def test_load_bets_for_player_filters():
    with tempfile.TemporaryDirectory() as tmp:
        bets_dir = os.path.join(tmp, "data", "bets")
        os.makedirs(bets_dir)
        path = os.path.join(bets_dir, "2026-05-24.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "player", "stat", "line", "side", "odds"])
            w.writerow(["2026-05-24", "Nikola Jokic", "pts", "28.5", "OVER", "-110"])
            w.writerow(["2026-05-24", "LeBron James", "ast", "8.5", "UNDER", "-110"])
        out = lp.load_bets_for_player("Nikola Jokic", "2026-05-24", project_dir=tmp)
    assert len(out) == 1
    assert out[0]["stat"] == "pts"


# ── render integration ─────────────────────────────────────────────────────

def test_render_no_snapshot_returns_clear_message(monkeypatch):
    monkeypatch.setattr(lp, "find_player_snapshot",
                          lambda name, pid, date: None)
    out = lp.render("Nobody", None, "2026-05-24")
    assert "no live snapshot" in out


def test_render_with_snapshot_shows_player_stats(monkeypatch):
    fake = {
        "player": {"name": "Nikola Jokic", "player_id": 203999,
                   "team": "DEN", "is_starter": True, "min": 18.0,
                   "pts": 15, "reb": 6, "ast": 5, "fg3m": 1, "stl": 1,
                   "blk": 0, "tov": 2, "pf": 2},
        "snapshot": {"home_team": "LAL", "away_team": "DEN", "period": 2,
                     "clock": "6:00", "home_score": 50, "away_score": 50,
                     "game_status": "LIVE"},
        "path": "fake",
    }
    monkeypatch.setattr(lp, "find_player_snapshot", lambda *a: fake)
    monkeypatch.setattr(lp, "load_pre_game_for_player", lambda *a, **k: {})
    monkeypatch.setattr(lp, "load_bets_for_player", lambda *a, **k: [])
    out = lp.render("Nikola Jokic", None, "2026-05-24")
    assert "Nikola Jokic" in out
    assert "Q2" in out
    assert "6:00" in out
    # Q2 with 6:00 left = 18/48 min played = 0.375 share -> 15 PTS projects to
    # 15 + (15/0.375)*0.625 = 15 + 25 = 40
    assert "40.0" in out or "40 " in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
