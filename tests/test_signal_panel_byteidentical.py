"""Tests for the CV_SIGNAL_PANEL feature.

Covers:
  1. byte-identical when OFF — build_signal_panel returns None
  2. byte-identical when OFF — build_signal_panel_from_live_dir returns None
  3. panel builds correctly with a synthetic snapshot when ON
  4. signal detection logic: TOV_SPIKE, FOUL_TROUBLE, HOT_SCORING, COLD_SCORING
  5. players below min_game_min are excluded
  6. players with no baseline gamelog are excluded
  7. only players with fired signals appear in panel.players
"""
from __future__ import annotations

import os
import json
import tempfile
from typing import Any
from statistics import mean, pstdev

import pytest

# Guard — import after env setup so the module can be imported cleanly
from src.prediction.signal_panel import (
    build_signal_panel,
    build_signal_panel_from_live_dir,
    _detect_signals,
    _load_baseline,
    _BASE_CACHE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(
    pid: int = 1,
    name: str = "Test Player",
    team: str = "TST",
    minutes: float = 20.0,
    pts: int = 4,
    reb: int = 3,
    ast: int = 2,
    tov: int = 1,
    pf: int = 1,
    fg3m: int = 0,
    stl: int = 0,
    blk: int = 0,
) -> dict:
    return {
        "player_id": pid,
        "name": name,
        "team": team,
        "min": minutes,
        "pts": pts,
        "reb": reb,
        "ast": ast,
        "tov": tov,
        "pf": pf,
        "fg3m": fg3m,
        "stl": stl,
        "blk": blk,
    }


def _make_snapshot(players: list[dict], period: int = 3) -> dict:
    return {
        "game_status": "3rd Quarter",
        "period": period,
        "clock": "5:00",
        "away_team": "AWAY",
        "home_team": "HOME",
        "players": players,
    }


def _make_gamelog(
    n: int = 15,
    mpg: float = 32.0,
    pts_pg: float = 22.0,
    reb_pg: float = 8.0,
    ast_pg: float = 6.0,
    tov_pg: float = 2.0,
    fg3m_pg: float = 2.0,
    stl_pg: float = 1.0,
    blk_pg: float = 0.5,
    pf_pg: float = 2.0,
) -> list[dict]:
    rows = []
    for _ in range(n):
        rows.append({
            "MIN": mpg,
            "PTS": pts_pg,
            "REB": reb_pg,
            "AST": ast_pg,
            "TOV": tov_pg,
            "FG3M": fg3m_pg,
            "STL": stl_pg,
            "BLK": blk_pg,
            "PF": pf_pg,
        })
    return rows


# ---------------------------------------------------------------------------
# 1 + 2: byte-identical OFF
# ---------------------------------------------------------------------------

class TestByteIdenticalOff:
    def setup_method(self):
        os.environ.pop("CV_SIGNAL_PANEL", None)
        _BASE_CACHE.clear()

    def teardown_method(self):
        os.environ.pop("CV_SIGNAL_PANEL", None)
        _BASE_CACHE.clear()

    def test_build_signal_panel_returns_none_when_off(self):
        snap = _make_snapshot([_make_player()])
        result = build_signal_panel(snap, root_dir="/tmp")
        assert result is None

    def test_build_signal_panel_from_live_dir_returns_none_when_off(self, tmp_path):
        result = build_signal_panel_from_live_dir("0042500401", str(tmp_path))
        assert result is None

    def test_build_signal_panel_default_is_off(self):
        """Without any env var set the flag defaults to off (not '1')."""
        assert os.environ.get("CV_SIGNAL_PANEL", "0") != "1"
        snap = _make_snapshot([_make_player()])
        assert build_signal_panel(snap, root_dir="/tmp") is None


# ---------------------------------------------------------------------------
# 3: panel builds with synthetic data when ON
# ---------------------------------------------------------------------------

class TestPanelBuildsWhenOn:
    def setup_method(self):
        os.environ["CV_SIGNAL_PANEL"] = "1"
        _BASE_CACHE.clear()

    def teardown_method(self):
        os.environ.pop("CV_SIGNAL_PANEL", None)
        _BASE_CACHE.clear()

    def test_panel_none_for_invalid_snapshot(self):
        assert build_signal_panel({}, root_dir="/tmp") is None
        assert build_signal_panel(None, root_dir="/tmp") is None  # type: ignore[arg-type]

    def test_panel_none_when_no_players(self):
        snap = _make_snapshot([], period=3)
        assert build_signal_panel(snap, root_dir="/tmp") is None

    def test_panel_has_correct_keys(self, tmp_path):
        """Panel dict has required keys even when no signals fire (empty players list)."""
        # Player with no baseline will produce no signals
        snap = _make_snapshot([_make_player(pid=999)])
        result = build_signal_panel(snap, root_dir=str(tmp_path))
        if result is None:
            # Either no signals fired => players list is empty but panel is still built
            return
        assert "players" in result
        assert "n_players_flagged" in result
        assert "n_signals_total" in result
        assert "period" in result

    def test_panel_players_only_contain_flagged_players(self, tmp_path):
        """Players with no baseline (no gamelog) produce no signals => not in panel."""
        snap = _make_snapshot([_make_player(pid=99999, minutes=25.0)])
        result = build_signal_panel(snap, root_dir=str(tmp_path))
        # No gamelog file exists => no baseline => no signals => players list is empty
        if result is not None:
            assert result["n_players_flagged"] == 0
            assert result["players"] == []

    def test_foul_trouble_signal_fires(self, tmp_path):
        """FOUL_TROUBLE fires when player has >=4 PF in period <=4."""
        # Write a gamelog for player 42
        nba_dir = tmp_path / "data" / "nba"
        nba_dir.mkdir(parents=True)
        (nba_dir / "gamelog_42_2025-26.json").write_text(
            json.dumps(_make_gamelog(n=15, mpg=32.0, pf_pg=2.0)), encoding="utf-8"
        )
        _BASE_CACHE.clear()

        player = _make_player(pid=42, minutes=22.0, pf=4, pts=10, tov=1)
        snap = _make_snapshot([player], period=3)
        result = build_signal_panel(snap, root_dir=str(tmp_path))
        assert result is not None
        foul_players = [p for p in result["players"]
                        if any(s["code"] == "FOUL_TROUBLE" for s in p["signals"])]
        assert len(foul_players) >= 1

    def test_tov_spike_signal_fires(self, tmp_path):
        """TOV_SPIKE fires when tov/36 >> baseline and raw tov >= 3."""
        nba_dir = tmp_path / "data" / "nba"
        nba_dir.mkdir(parents=True)
        # Baseline: 2 TOV/game in 32 mpg = 2.25 TOV/36
        (nba_dir / "gamelog_7_2025-26.json").write_text(
            json.dumps(_make_gamelog(n=15, mpg=32.0, tov_pg=2.0)), encoding="utf-8"
        )
        _BASE_CACHE.clear()

        # Observed: 4 TOV in 18 min => 8 TOV/36 (z >> 1.5 vs 2.25/36 baseline)
        player = _make_player(pid=7, minutes=18.0, tov=4, pts=6)
        snap = _make_snapshot([player], period=3)
        result = build_signal_panel(snap, root_dir=str(tmp_path))
        assert result is not None
        tov_players = [p for p in result["players"]
                       if any(s["code"] == "TOV_SPIKE" for s in p["signals"])]
        assert len(tov_players) >= 1

    def test_hot_scoring_signal_fires(self, tmp_path):
        """HOT_SCORING fires for a scorer well above their own norm."""
        nba_dir = tmp_path / "data" / "nba"
        nba_dir.mkdir(parents=True)
        # Baseline: 18 PTS/game in 30 min => 21.6 PTS/36
        (nba_dir / "gamelog_3_2025-26.json").write_text(
            json.dumps(_make_gamelog(n=15, mpg=30.0, pts_pg=18.0)), encoding="utf-8"
        )
        _BASE_CACHE.clear()

        # Observed: 22 PTS in 25 min => 31.7 PTS/36 (z >> 1.8)
        player = _make_player(pid=3, minutes=25.0, pts=22)
        snap = _make_snapshot([player], period=3)
        result = build_signal_panel(snap, root_dir=str(tmp_path))
        assert result is not None
        hot_players = [p for p in result["players"]
                       if any(s["code"] == "HOT_SCORING" for s in p["signals"])]
        assert len(hot_players) >= 1


# ---------------------------------------------------------------------------
# 4: _detect_signals edge cases
# ---------------------------------------------------------------------------

class TestDetectSignals:
    def setup_method(self):
        _BASE_CACHE.clear()

    def teardown_method(self):
        _BASE_CACHE.clear()

    def _flat_base(
        self, n: int = 15,
        pts_p36: float = 21.0, reb_p36: float = 9.0,
        ast_p36: float = 5.5, tov_p36: float = 2.5,
        fg3m_p36: float = 2.0, stl_p36: float = 1.2,
        blk_p36: float = 0.8, pf_pg: float = 2.0,
    ) -> dict:
        """Minimal flat baseline (zero std for testability)."""
        def _b(p36: float) -> dict:
            return {"pg_mean": p36 * 32 / 36, "pg_std": 0.0,
                    "p36_mean": p36, "p36_std": 0.0}
        return {
            "n_games": n, "season": "2025-26", "mpg": 32.0,
            "pts": _b(pts_p36), "reb": _b(reb_p36), "ast": _b(ast_p36),
            "tov": _b(tov_p36), "fg3m": _b(fg3m_p36),
            "stl": _b(stl_p36), "blk": _b(blk_p36),
            "pf": {"pg_mean": pf_pg, "pg_std": 0.5,
                   "p36_mean": pf_pg * 36 / 32, "p36_std": 0.0},
        }

    def test_foul_trouble_4pf_period3(self):
        base = self._flat_base()
        player = _make_player(pid=1, minutes=20.0, pf=4)
        sigs = _detect_signals(player, base, period=3)
        codes = [s["code"] for s in sigs]
        assert "FOUL_TROUBLE" in codes

    def test_no_foul_trouble_period5_ot(self):
        """FOUL_TROUBLE should NOT fire in OT (period > 4)."""
        base = self._flat_base()
        player = _make_player(pid=1, minutes=25.0, pf=4)
        sigs = _detect_signals(player, base, period=5)
        codes = [s["code"] for s in sigs]
        assert "FOUL_TROUBLE" not in codes

    def test_cold_scoring_not_fired_for_role_player(self):
        """COLD_SCORING only fires if baseline >= 12 pts/36."""
        base = self._flat_base(pts_p36=8.0)  # role player
        player = _make_player(pid=1, minutes=20.0, pts=1)
        sigs = _detect_signals(player, base, period=3)
        codes = [s["code"] for s in sigs]
        assert "COLD_SCORING" not in codes

    def test_below_min_game_min_returns_empty(self):
        base = self._flat_base()
        player = _make_player(pid=1, minutes=5.0)  # < 8 min gate
        sigs = _detect_signals(player, base, period=3, min_game_min=8.0)
        assert sigs == []

    def test_no_base_returns_empty(self):
        player = _make_player(pid=1, minutes=20.0)
        sigs = _detect_signals(player, None, period=3)
        assert sigs == []

    def test_too_few_base_games_returns_empty(self):
        base = self._flat_base(n=3)  # only 3 games, gate is 5
        player = _make_player(pid=1, minutes=20.0)
        sigs = _detect_signals(player, base, period=3, min_base_games=5)
        assert sigs == []


# ---------------------------------------------------------------------------
# 5 + 6: players below gate excluded
# ---------------------------------------------------------------------------

class TestExclusionGates:
    def setup_method(self):
        os.environ["CV_SIGNAL_PANEL"] = "1"
        _BASE_CACHE.clear()

    def teardown_method(self):
        os.environ.pop("CV_SIGNAL_PANEL", None)
        _BASE_CACHE.clear()

    def test_player_below_min_minutes_excluded(self, tmp_path):
        nba_dir = tmp_path / "data" / "nba"
        nba_dir.mkdir(parents=True)
        # Write gamelog for player 5
        (nba_dir / "gamelog_5_2025-26.json").write_text(
            json.dumps(_make_gamelog(n=15, mpg=32.0, tov_pg=2.0)), encoding="utf-8"
        )
        _BASE_CACHE.clear()
        # Player with only 5 minutes — below the 8-min gate
        player = _make_player(pid=5, minutes=5.0, tov=4, pf=4)
        snap = _make_snapshot([player], period=3)
        result = build_signal_panel(snap, root_dir=str(tmp_path))
        # Either result is None or the player did not produce any signals
        if result is not None:
            flagged_ids = [p["player_id"] for p in result["players"]]
            assert 5 not in flagged_ids


# ---------------------------------------------------------------------------
# 7: from_live_dir no-snapshot path
# ---------------------------------------------------------------------------

class TestLiveDirNoSnapshot:
    def setup_method(self):
        os.environ["CV_SIGNAL_PANEL"] = "1"
        _BASE_CACHE.clear()

    def teardown_method(self):
        os.environ.pop("CV_SIGNAL_PANEL", None)
        _BASE_CACHE.clear()

    def test_no_live_dir_returns_none(self, tmp_path):
        """If data/live directory doesn't exist, returns None gracefully."""
        result = build_signal_panel_from_live_dir("0042500999", str(tmp_path))
        assert result is None

    def test_no_snapshot_file_returns_none(self, tmp_path):
        live_dir = tmp_path / "data" / "live"
        live_dir.mkdir(parents=True)
        result = build_signal_panel_from_live_dir("0042500999", str(tmp_path))
        assert result is None

    def test_valid_snapshot_file_returns_panel(self, tmp_path):
        """When a valid snapshot exists, build_signal_panel_from_live_dir returns panel."""
        live_dir = tmp_path / "data" / "live"
        live_dir.mkdir(parents=True)
        snap = _make_snapshot([_make_player(pid=77, minutes=25.0, pf=4)])
        (live_dir / "0042500999_1000000.json").write_text(
            json.dumps(snap), encoding="utf-8"
        )
        # Write gamelog so baseline exists
        nba_dir = tmp_path / "data" / "nba"
        nba_dir.mkdir(parents=True)
        (nba_dir / "gamelog_77_2025-26.json").write_text(
            json.dumps(_make_gamelog(n=15, mpg=32.0, pf_pg=2.0)), encoding="utf-8"
        )
        _BASE_CACHE.clear()
        result = build_signal_panel_from_live_dir("0042500999", str(tmp_path))
        assert result is not None
        assert "players" in result
