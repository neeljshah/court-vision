"""Tests for scripts/live_dashboard.py (cycle 88i)."""
from __future__ import annotations

import csv
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.live_dashboard as ld  # noqa: E402


def _snapshot(period=2, clock="6:00", home_score=50, away_score=50,
              home_team="OKC", away_team="SAS",
              status="LIVE", players=None):
    return {
        "game_id": "0022400123", "captured_at": "2026-05-24T19:42:00",
        "game_status": status, "period": period, "clock": clock,
        "home_score": home_score, "away_score": away_score,
        "home_team": home_team, "away_team": away_team,
        "players": players if players is not None else [],
    }


def _player(name, pts=10, reb=4, ast=2, fg3m=1, stl=1, blk=0, tov=1,
             minutes=12.0, is_starter=True, player_id=1, team="OKC"):
    return {"name": name, "player_id": player_id, "team": team,
            "is_starter": is_starter, "min": minutes,
            "pts": pts, "reb": reb, "ast": ast, "fg3m": fg3m,
            "stl": stl, "blk": blk, "tov": tov, "pf": 1}


# ── project_remaining ────────────────────────────────────────────────────────

def test_project_remaining_doubles_at_half():
    """Q2 with 6:00 means 0.5 share played -> projection is 2x current."""
    assert ld.project_remaining(12.0, 0.5) == pytest.approx(24.0)


def test_project_remaining_returns_current_at_game_end():
    """share_played = 1.0 means current IS final."""
    assert ld.project_remaining(24.0, 1.0) == pytest.approx(24.0)


def test_project_remaining_zero_share_returns_current():
    """Don't divide by zero — return current value when game hasn't started."""
    assert ld.project_remaining(0.0, 0.0) == 0.0
    assert ld.project_remaining(5.0, 0.0) == 5.0


def test_project_remaining_clamps_low_share():
    """A near-zero share would project absurdly large numbers — clamp."""
    # At 0.05 share played, doesn't extrapolate to 200; clamps at 1/0.05 = 20x
    assert ld.project_remaining(5.0, 0.01) == pytest.approx(100.0)
    assert ld.project_remaining(5.0, 0.001) == pytest.approx(100.0)


# ── pre-game ledger loader ───────────────────────────────────────────────────

def test_load_pre_game_returns_empty_when_no_ledger():
    with tempfile.TemporaryDirectory() as tmp:
        out = ld.load_pre_game_predictions("2099-01-01", project_dir=tmp)
        assert out == {}


def test_load_pre_game_parses_cycle80_schema():
    """Cycle 80's CSV schema has lineup_status etc; loader only needs player+stat+pred."""
    with tempfile.TemporaryDirectory() as tmp:
        pred_dir = os.path.join(tmp, "data", "predictions")
        os.makedirs(pred_dir)
        path = os.path.join(pred_dir, "2026-05-24.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "game_id", "player_id", "player",
                        "team", "opp", "venue", "stat", "pred",
                        "lineup_status", "lineup_class", "play_pct", "injury_status"])
            w.writerow(["2026-05-24", "g1", "1", "Nikola Jokic",
                        "DEN", "LAL", "home", "pts", "28.5",
                        "Confirmed", "starter", "100", ""])
            w.writerow(["2026-05-24", "g1", "1", "Nikola Jokic",
                        "DEN", "LAL", "home", "reb", "12.1",
                        "Confirmed", "starter", "100", ""])
        out = ld.load_pre_game_predictions("2026-05-24", project_dir=tmp)
    assert "nikola jokic" in out
    assert out["nikola jokic"]["pts"] == 28.5
    assert out["nikola jokic"]["reb"] == 12.1


def test_load_pre_game_diacritic_insensitive_key():
    """Lookup key is canonicalized (Jokić -> jokic) — so dashboard finds him later."""
    with tempfile.TemporaryDirectory() as tmp:
        pred_dir = os.path.join(tmp, "data", "predictions")
        os.makedirs(pred_dir)
        path = os.path.join(pred_dir, "2026-05-24.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "game_id", "player_id", "player", "team",
                        "opp", "venue", "stat", "pred"])
            w.writerow(["2026-05-24", "g1", "1", "Nikola Jokić",
                        "DEN", "LAL", "home", "pts", "28.5"])
        out = ld.load_pre_game_predictions("2026-05-24", project_dir=tmp)
    assert "nikola jokic" in out
    # Stripped key is what the dashboard uses for lookup with raw name 'Jokic'.


# ── render_game ──────────────────────────────────────────────────────────────

def test_render_game_includes_header_with_scores():
    snap = _snapshot(period=3, clock="2:30", home_score=85, away_score=78,
                      home_team="OKC", away_team="SAS",
                      players=[_player("Shai Gilgeous-Alexander", pts=22, minutes=24)])
    out = ld.render_game(snap, pre_game={})
    assert "OKC" in out
    assert "SAS" in out
    assert "Q3" in out
    assert "2:30" in out
    assert "85" in out
    assert "78" in out


def test_render_game_sorts_players_by_current_pts():
    snap = _snapshot(players=[
        _player("Low Scorer", pts=4),
        _player("High Scorer", pts=24),
        _player("Mid Scorer", pts=12),
    ])
    out = ld.render_game(snap, pre_game={})
    # High scorer's line must appear before low scorer's.
    hi_idx = out.find("High Scorer")
    mid_idx = out.find("Mid Scorer")
    lo_idx = out.find("Low Scorer")
    assert hi_idx > 0 and hi_idx < mid_idx < lo_idx


def test_render_game_starters_only_hides_bench():
    snap = _snapshot(players=[
        _player("Starter A", pts=15, is_starter=True),
        _player("Bench B", pts=8, is_starter=False),
    ])
    full = ld.render_game(snap, pre_game={}, only_starters=False)
    starters = ld.render_game(snap, pre_game={}, only_starters=True)
    assert "Bench B" in full
    assert "Bench B" not in starters
    assert "Starter A" in starters


def test_render_game_shows_pregame_pred_when_available():
    snap = _snapshot(period=2, clock="6:00", players=[
        _player("Nikola Jokic", pts=15, minutes=18),
    ])
    pre = {"nikola jokic": {"pts": 28.5, "reb": 11.0, "ast": 8.0,
                              "fg3m": 1.5, "stl": 1.0, "blk": 1.0, "tov": 3.0}}
    out = ld.render_game(snap, pre_game=pre)
    # Player line should include the pre-game pts value "28.5"
    assert "28.5" in out


def test_render_game_handles_empty_snapshot():
    assert ld.render_game({}, pre_game={}) == "(empty snapshot)"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
