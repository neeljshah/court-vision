"""tests/test_predict_in_game_schema.py — cycle 89a (loop 5).

Schema-unification tests for predict_in_game. Cycle 88l integration test
caught that predict_in_game read nested {home: {abbrev, score}, ...} while
src/data/live.py + live_game_poll + save_live_predictions all use the
canonical top-level {home_team, home_score, away_team, away_score}.

These tests pin the contract:
  1. canonical snapshot projects correctly
  2. legacy nested snapshot is auto-lifted to canonical and yields the
     SAME projection rows as the canonical equivalent
  3. empty snapshot returns []
  4. partial snapshot (only one side populated) projects without crash
  5. Q4 blowout still triggers blow_factor < 1.0 under top-level keys
"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig  # noqa: E402


STAR_PLAYER = {
    "player_id": 999, "name": "Big Star", "team": "HOM",
    "min": 32.0, "pts": 28, "reb": 5, "ast": 7,
    "fg3m": 4, "stl": 1, "blk": 0, "tov": 3, "pf": 2,
    "is_starter": True,
}


# ── 1. canonical top-level snapshot projects correctly ──────────────────────

def test_canonical_snapshot_projects_rows():
    """Top-level home_team/away_team/home_score/away_score → non-empty rows."""
    snap = {
        "game_id": "0022400777",
        "period": 2,
        "clock": "6:00",
        "home_team": "HOM",
        "away_team": "AWA",
        "home_score": 56,
        "away_score": 48,
        "players": [dict(STAR_PLAYER)],
    }
    rows = pig.project_snapshot(snap)
    # 1 player × 7 stats = 7 rows.
    assert len(rows) == 7
    # Each row has a non-negative projection >= current.
    for r in rows:
        assert r["projected_final"] >= r["current"] - 1e-6
    # In a competitive Q2 game (margin=8, not Q4) blow_factor must be 1.0.
    assert all(r["blow_factor"] == 1.0 for r in rows)


# ── 2. nested snapshot lifts to canonical, yields identical rows ────────────

def test_nested_snapshot_normalizes_and_matches_canonical():
    """Legacy {home: {abbrev, score}} form → identical output to canonical."""
    canonical = {
        "game_id": "0022400777",
        "period": 3,
        "clock": "5:30",
        "home_team": "HOM",
        "away_team": "AWA",
        "home_score": 72,
        "away_score": 70,
        "players": [dict(STAR_PLAYER)],
    }
    nested = {
        "game_id": "0022400777",
        "period": 3,
        "clock": "5:30",
        "home": {"abbrev": "HOM", "score": 72},
        "away": {"abbrev": "AWA", "score": 70},
        "players": [dict(STAR_PLAYER)],
    }
    # _normalize_snapshot lifts top-level keys.
    lifted = pig._normalize_snapshot(dict(nested))
    assert lifted["home_team"] == "HOM"
    assert lifted["home_score"] == 72
    assert lifted["away_team"] == "AWA"
    assert lifted["away_score"] == 70

    rows_canonical = pig.project_snapshot(canonical)
    rows_nested = pig.project_snapshot(nested)
    assert len(rows_canonical) == len(rows_nested)
    # Compare numeric projections row-for-row.
    for rc, rn in zip(rows_canonical, rows_nested):
        assert rc["stat"] == rn["stat"]
        assert rc["projected_final"] == pytest.approx(rn["projected_final"])
        assert rc["foul_factor"] == pytest.approx(rn["foul_factor"])
        assert rc["blow_factor"] == pytest.approx(rn["blow_factor"])


# ── 3. empty snapshot returns no rows ───────────────────────────────────────

def test_empty_snapshot_returns_empty_rows():
    """No players in snapshot → project_snapshot returns []."""
    snap = {
        "game_id": "0022400000",
        "period": 1,
        "clock": "12:00",
        "home_team": "HOM",
        "away_team": "AWA",
        "home_score": 0,
        "away_score": 0,
        "players": [],
    }
    assert pig.project_snapshot(snap) == []
    # Also: snapshot with no "players" key at all.
    snap2 = {"period": 1, "clock": "12:00"}
    assert pig.project_snapshot(snap2) == []


# ── 4. partial snapshot — only one side populated — graceful default ────────

def test_partial_snapshot_only_home_team():
    """Snapshot with only home_team and no away_team must not crash."""
    snap = {
        "game_id": "0022400001",
        "period": 2,
        "clock": "5:00",
        "home_team": "HOM",
        # No away_team, no scores.
        "players": [dict(STAR_PLAYER)],
    }
    rows = pig.project_snapshot(snap)
    assert len(rows) == 7
    for r in rows:
        assert r["projected_final"] >= r["current"] - 1e-6
        # Margin=0 → blow_factor stays 1.0 even in absence of opposing side.
        assert r["blow_factor"] == 1.0

    # Nested form with only home populated also works.
    snap_nested = {
        "game_id": "0022400001",
        "period": 2,
        "clock": "5:00",
        "home": {"abbrev": "HOM", "score": 40},
        # No away key.
        "players": [dict(STAR_PLAYER)],
    }
    rows_n = pig.project_snapshot(snap_nested)
    assert len(rows_n) == 7


# ── 5. blowout factor fires on Q4 30-pt margin with top-level keys ──────────

def test_blowout_factor_fires_on_top_level_keys():
    """Q4, home_score=110 vs away_score=80 (margin=30), home star → bf<1.0.

    Star player on the LEADING side in a Q4 blowout: predict_in_game's
    internal blowout_factor table for margin>=30 in Q4 returns 0.30.
    """
    snap = {
        "game_id": "0022400123",
        "period": 4,
        "clock": "8:00",
        "home_team": "HOM",
        "away_team": "AWA",
        "home_score": 110,
        "away_score": 80,
        "players": [dict(STAR_PLAYER)],  # team="HOM", min=32 → proj ~38min star
    }
    rows = pig.project_snapshot(snap)
    pts_row = next(r for r in rows if r["stat"] == "pts")
    # margin=30, Q4, is_star=True, team_is_leading=True (HOM leads, team==HOM)
    # blowout_factor(30, 4, is_star=True) -> 0.30.
    assert pts_row["blow_factor"] == pytest.approx(0.30)
    # Projection should be dramatically below pure pace (which would be
    # 28 * 48/40 = 33.6 at Q4 8:00 left).
    no_blow_pace = 28.0 * (48.0 / 40.0)
    assert pts_row["projected_final"] < no_blow_pace

    # Sanity: away team (TRAILING) star in the same blowout gets NO penalty
    # because the leading-side rule guards (a trailing star isn't pulled).
    snap2 = dict(snap)
    snap2["players"] = [{**STAR_PLAYER, "team": "AWA"}]
    rows2 = pig.project_snapshot(snap2)
    pts2 = next(r for r in rows2 if r["stat"] == "pts")
    assert pts2["blow_factor"] == 1.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
