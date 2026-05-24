"""tests/test_recommend_endQ2_bets.py -- cycle 98d (loop 5).

5 tests for the halftime betting recommender:
  1. Single endQ2 snapshot produces non-empty recommendation list.
  2. period=3 mid-Q3 snapshot returns empty (wrong snapshot point).
  3. --threshold filters correctly (high threshold -> empty).
  4. --include-pts-tov toggle adds PTS/TOV.
  5. Empty live dir returns empty without crash.
"""
from __future__ import annotations

import json
import os
import sys
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import recommend_endQ2_bets as rec    # noqa: E402


def _snapshot(period=2, clock="0:00", players=None,
              game_id="0022400123", home_team="OKC", away_team="SAS",
              home_score=58, away_score=55):
    return {
        "game_id": game_id,
        "captured_at": "2026-05-24T20:48:33+00:00",
        "game_status": "LIVE",
        "period": period, "clock": clock,
        "home_team": home_team, "away_team": away_team,
        "home_score": home_score, "away_score": away_score,
        "players": players or [],
    }


def _player(name, team, pid, **stats):
    base = {"name": name, "player_id": pid, "team": team,
            "is_starter": True, "min": 20.0, "pf": 2,
            "pts": 15, "reb": 7, "ast": 5, "fg3m": 2,
            "stl": 1, "blk": 1, "tov": 2}
    base.update(stats)
    return base


def _fake_l5(stat_to_line):
    """Return a callable matching ``rec.l5_line_for_player`` signature."""
    def _fn(pid, on_or_before, project_dir=None):
        return dict(stat_to_line)
    return _fn


# ── test 1: single halftime snapshot -> non-empty recs --------------------------

def test_halftime_snapshot_produces_recommendations(monkeypatch):
    snap = _snapshot(period=2, clock="0:00",
                     players=[_player("Star Player", "OKC", 99,
                                       reb=10, ast=8, fg3m=3, stl=2, blk=1)])
    # L5 line proxy puts the player far BELOW their halftime projection on
    # every viable stat -- guarantees |edge| >= 1.0 and Kelly > 0.
    fake = _fake_l5({"reb": 4.0, "ast": 3.0, "fg3m": 0.5,
                      "stl": 0.4, "blk": 0.2, "pts": 12.0, "tov": 2.0})
    monkeypatch.setattr(rec, "l5_line_for_player", fake)

    recs = rec.build_recommendations(
        snapshots=[("/fake.json", snap)],
        threshold=1.0,
        include_pts_tov=False,
        date_iso="2026-05-24",
    )
    assert recs, "expected at least one recommendation from a halftime snapshot"
    # All recommendations must come from the 5 viable stats.
    for r in recs:
        assert r["stat"] in rec.ENDQ2_VIABLE_STATS
        assert r["kelly_stake"] > 0
        assert r["endQ2_roi_baseline"] > 0


# ── test 2: period=3 (mid-Q3) snapshot is NOT halftime --------------------------

def test_mid_q3_snapshot_is_not_halftime():
    """period=3 with 6:00 left on the clock is mid-Q3, NOT halftime."""
    snap = _snapshot(period=3, clock="6:00",
                     players=[_player("Some Player", "OKC", 1)])
    assert rec.is_halftime_snapshot(snap) is False
    # discover_halftime_snapshots should drop this one too.
    with mock.patch.object(rec, "list_today_snapshots",
                            return_value=["/fake.json"]), \
         mock.patch.object(rec, "load_live_state", return_value=snap):
        snaps = rec.discover_halftime_snapshots("2026-05-24")
    assert snaps == []


# ── test 3: threshold filters correctly -----------------------------------------

def test_threshold_filters_low_edge(monkeypatch):
    snap = _snapshot(period=2, clock="0:00",
                     players=[_player("Edge Case", "OKC", 7,
                                       reb=4, ast=3, fg3m=1, stl=1, blk=0)])
    # L5 line essentially MATCHES the projection on every viable stat ->
    # edge is ~0 -> nothing should clear threshold 1.0.
    # Project a halftime snap so projected_final ~= 2 * current (rough).
    fake = _fake_l5({"reb": 8.0, "ast": 6.0, "fg3m": 2.0,
                      "stl": 2.0, "blk": 0.0, "pts": 30.0, "tov": 2.0})
    monkeypatch.setattr(rec, "l5_line_for_player", fake)

    high_threshold = rec.build_recommendations(
        snapshots=[("/fake.json", snap)],
        threshold=100.0,   # impossibly high -> empty
        include_pts_tov=True,
        date_iso="2026-05-24",
    )
    assert high_threshold == []


# ── test 4: --include-pts-tov toggle adds PTS/TOV -------------------------------

def test_include_pts_tov_adds_those_stats(monkeypatch):
    snap = _snapshot(period=2, clock="0:00",
                     players=[_player("Wide Edge", "OKC", 8,
                                       pts=20, reb=6, ast=4, fg3m=2,
                                       stl=1, blk=1, tov=3)])
    # Force a big edge on EVERY stat so PTS + TOV both clear the gate when
    # they're allowed.
    fake = _fake_l5({"reb": 2.0, "ast": 1.0, "fg3m": 0.2,
                      "stl": 0.2, "blk": 0.2, "pts": 5.0, "tov": 0.5})
    monkeypatch.setattr(rec, "l5_line_for_player", fake)

    without = rec.build_recommendations(
        snapshots=[("/fake.json", snap)],
        threshold=1.0,
        include_pts_tov=False,
        date_iso="2026-05-24",
    )
    with_pts_tov = rec.build_recommendations(
        snapshots=[("/fake.json", snap)],
        threshold=1.0,
        include_pts_tov=True,
        date_iso="2026-05-24",
    )

    stats_without = {r["stat"] for r in without}
    stats_with = {r["stat"] for r in with_pts_tov}

    assert "pts" not in stats_without
    assert "tov" not in stats_without
    # The flag MUST add pts+tov entries when their edge is big enough.
    assert "pts" in stats_with
    assert "tov" in stats_with
    # And it never removes viable-stat entries.
    assert stats_without.issubset(stats_with)


# ── test 5: empty live dir returns empty without crash --------------------------

def test_empty_live_dir_returns_empty(monkeypatch):
    """discover_halftime_snapshots over an empty live dir returns []."""
    monkeypatch.setattr(rec, "list_today_snapshots", lambda *a, **kw: [])

    snaps = rec.discover_halftime_snapshots("2026-05-24")
    assert snaps == []

    # And build_recommendations on an empty snapshot list is also clean.
    recs = rec.build_recommendations(
        snapshots=[],
        threshold=1.0,
        include_pts_tov=False,
        date_iso="2026-05-24",
    )
    assert recs == []
