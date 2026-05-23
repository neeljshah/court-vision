"""
tests/test_referee_features.py — Unit tests for src/features/referee_features.py

Fixtures create fake boxscores + officials cache; no NBA API calls are made.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest import mock

import pandas as pd
import pytest

# ── path setup ────────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_boxscore(
    game_id: str,
    home_team: str,
    away_team: str,
    home_pts: int,
    away_pts: int,
    home_fta: int = 20,
    away_fta: int = 18,
    home_pf:  int = 16,
    away_pf:  int = 14,
) -> dict:
    players = []
    # 5 players per team, distribute stats evenly
    for i in range(5):
        players.append({
            "player_id": 1000 + i,
            "player_name": f"{home_team}_P{i}",
            "team_abbreviation": home_team,
            "jersey_num": str(i),
            "starter": True,
            "min": 24.0,
            "pts": home_pts // 5,
            "reb": 4, "oreb": 1, "dreb": 3, "ast": 3, "stl": 1, "blk": 0,
            "tov": 1,
            "fgm": 5, "fga": 12, "fg3m": 2, "fg3a": 5,
            "ftm": home_fta // 5,
            "fta": home_fta // 5,
            "pf": home_pf // 5,
            "plus_minus": 5,
        })
    for i in range(5):
        players.append({
            "player_id": 2000 + i,
            "player_name": f"{away_team}_P{i}",
            "team_abbreviation": away_team,
            "jersey_num": str(10 + i),
            "starter": True,
            "min": 24.0,
            "pts": away_pts // 5,
            "reb": 4, "oreb": 1, "dreb": 3, "ast": 3, "stl": 1, "blk": 0,
            "tov": 1,
            "fgm": 5, "fga": 12, "fg3m": 2, "fg3a": 5,
            "ftm": away_fta // 5,
            "fta": away_fta // 5,
            "pf": away_pf // 5,
            "plus_minus": -5,
        })
    return {
        "game_id": game_id,
        "game_status": 3,
        "home_team": home_team,
        "away_team": away_team,
        "home_score": home_pts,
        "away_score": away_pts,
        "players": players,
        "total_players": 10,
        "total_fga": 90,
    }


def _make_officials(ref_list: list[dict]) -> list[dict]:
    return [{"id": r["id"], "name": r["name"], "jersey_num": r.get("jersey_num", "00")}
            for r in ref_list]


# ── fixtures ──────────────────────────────────────────────────────────────────

REFS = [
    {"id": 101, "name": "Alice Foster",   "jersey_num": "1"},
    {"id": 102, "name": "Bob Brothers",   "jersey_num": "2"},
    {"id": 103, "name": "Charlie Capers", "jersey_num": "3"},
]

GAMES = [
    ("0022400001", "BOS", "NYK", 130, 110, 22, 20, 18, 16),  # crew A+B+C, high total
    ("0022400002", "LAL", "GSW", 105, 100, 15, 14, 12, 11),  # crew A+B+C, lower total
    ("0022400003", "MIL", "PHX", 120, 118, 25, 24, 20, 19),  # crew A+B+C
]


@pytest.fixture()
def tmp_dirs(tmp_path):
    """Patch module-level path constants to tmp_path."""
    nba_cache     = tmp_path / "data" / "nba"
    officials_dir = tmp_path / "data" / "cache" / "officials"
    model_dir     = tmp_path / "data" / "models"
    nba_cache.mkdir(parents=True)
    officials_dir.mkdir(parents=True)
    model_dir.mkdir(parents=True)

    import src.features.referee_features as rf
    with mock.patch.multiple(
        rf,
        _NBA_CACHE      = str(nba_cache),
        _OFFICIALS_DIR  = str(officials_dir),
        _MODEL_DIR      = str(model_dir),
        _HISTORY_PATH   = str(model_dir / "ref_history.json"),
        _HISTORY_CACHE  = None,
    ):
        yield {
            "nba_cache":     nba_cache,
            "officials_dir": officials_dir,
            "model_dir":     model_dir,
            "module":        rf,
        }


@pytest.fixture()
def populated_dirs(tmp_dirs):
    """Write 3 fake boxscores + officials cache files."""
    nba_cache     = tmp_dirs["nba_cache"]
    officials_dir = tmp_dirs["officials_dir"]

    for (gid, ht, at, hp, ap, hfta, afta, hpf, apf) in GAMES:
        bs = _make_boxscore(gid, ht, at, hp, ap, hfta, afta, hpf, apf)
        (nba_cache / f"boxscore_{gid}.json").write_text(
            json.dumps(bs), encoding="utf-8"
        )
        (officials_dir / f"{gid}.json").write_text(
            json.dumps(_make_officials(REFS)), encoding="utf-8"
        )

    return tmp_dirs


# ── tests ─────────────────────────────────────────────────────────────────────

class TestGetReferees:
    def test_reads_from_officials_cache(self, populated_dirs):
        """get_referees returns cached officials without API call."""
        rf = populated_dirs["module"]
        result = rf.get_referees("0022400001")
        assert len(result) == 3
        names = {r["name"] for r in result}
        assert "Alice Foster" in names

    def test_reads_from_boxscore_officials_key(self, tmp_dirs):
        """get_referees falls back to embedded 'officials' key in boxscore."""
        rf = tmp_dirs["module"]
        nba_cache = tmp_dirs["nba_cache"]
        bs = _make_boxscore("0022400099", "BOS", "MIA", 110, 105)
        bs["officials"] = _make_officials(REFS[:2])
        (nba_cache / "boxscore_0022400099.json").write_text(
            json.dumps(bs), encoding="utf-8"
        )
        result = rf.get_referees("0022400099")
        assert len(result) == 2
        assert result[0]["name"] in {"Alice Foster", "Bob Brothers"}

    def test_returns_empty_when_no_data(self, tmp_dirs):
        """get_referees returns [] when no cache and API unavailable."""
        rf = tmp_dirs["module"]
        with mock.patch.object(rf, "_API_THROTTLE", 0), \
             mock.patch("time.sleep"), \
             mock.patch.dict("sys.modules", {"nba_api": None,
                                              "nba_api.stats": None,
                                              "nba_api.stats.endpoints": None,
                                              "nba_api.stats.endpoints.boxscoresummaryv2": None}):
            result = rf.get_referees("0099999999")
        assert result == []


class TestBuildRefHistory:
    def test_basic_aggregates(self, populated_dirs):
        """build_ref_history computes correct per-ref aggregates."""
        rf  = populated_dirs["module"]
        df  = rf.build_ref_history()

        assert len(df) == 3  # 3 refs
        assert set(df.columns) >= {
            "ref_id", "ref_name", "games_officiated",
            "avg_game_total", "avg_pace", "avg_fta_per_team",
            "avg_pf_per_team", "home_win_pct",
        }

        # Each ref officiated all 3 games
        assert (df["games_officiated"] == 3).all()

        # Verify avg_game_total:  (240 + 205 + 238) / 3 = 227.67
        expected_total = (240 + 205 + 238) / 3
        assert abs(df["avg_game_total"].iloc[0] - expected_total) < 0.5

    def test_home_win_pct(self, populated_dirs):
        """home_win_pct reflects actual game outcomes."""
        rf  = populated_dirs["module"]
        df  = rf.build_ref_history()

        # All 3 games: home won (130>110, 105>100, 120>118) → 1.0
        assert (df["home_win_pct"] == 1.0).all()

    def test_saves_to_disk(self, populated_dirs):
        """build_ref_history writes ref_history.json."""
        rf   = populated_dirs["module"]
        path = populated_dirs["model_dir"] / "ref_history.json"
        rf.build_ref_history()
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 3

    def test_empty_when_no_boxscores(self, tmp_dirs):
        """Returns empty DataFrame if no boxscores are present."""
        rf = tmp_dirs["module"]
        df = rf.build_ref_history()
        assert df.empty


class TestGetRefCrewFeatures:
    def test_known_crew_returns_means(self, populated_dirs):
        """Crew of 3 known refs returns mean of their profiles."""
        rf = populated_dirs["module"]
        # Ensure history is built
        rf.build_ref_history()
        # Invalidate module-level cache so the patched path is used
        populated_dirs["module"]._HISTORY_CACHE = None

        features = rf.get_ref_crew_features("0022400001", "2024-10-30")

        assert features["ref_crew_known"] == 1
        assert features["ref_crew_games_avg"] == 3.0  # each ref has 3 games

        expected_total = (240 + 205 + 238) / 3
        assert abs(features["ref_crew_game_total_avg"] - expected_total) < 0.5

    def test_unknown_game_returns_zeros(self, populated_dirs):
        """Unknown game_id (no officials) returns zeros + crew_known=0."""
        rf = populated_dirs["module"]
        rf.build_ref_history()
        rf._HISTORY_CACHE = None

        features = rf.get_ref_crew_features("0099999999", "2025-01-01")

        assert features["ref_crew_known"] == 0
        assert features["ref_crew_game_total_avg"] == 0.0
        assert features["ref_crew_pace_avg"]       == 0.0
        assert features["ref_crew_fta_avg"]        == 0.0
        assert features["ref_crew_pf_avg"]         == 0.0
        assert features["ref_crew_home_win_pct"]   == 0.0
        assert features["ref_crew_games_avg"]      == 0.0

    def test_unknown_ref_id_not_in_history(self, populated_dirs):
        """If crew refs have no history entry, returns zeros."""
        rf = populated_dirs["module"]
        rf.build_ref_history()
        rf._HISTORY_CACHE = None

        # Write officials with IDs not in history
        officials_dir = populated_dirs["officials_dir"]
        unknown = [{"id": 9999, "name": "Ghost Ref", "jersey_num": "99"}]
        (officials_dir / "0022400777.json").write_text(
            json.dumps(unknown), encoding="utf-8"
        )

        features = rf.get_ref_crew_features("0022400777")
        assert features["ref_crew_known"] == 0

    def test_feature_dict_has_all_keys(self, populated_dirs):
        """Feature dict always contains all expected keys."""
        rf = populated_dirs["module"]
        features = rf.get_ref_crew_features("0099999998")

        expected_keys = {
            "ref_crew_game_total_avg",
            "ref_crew_pace_avg",
            "ref_crew_fta_avg",
            "ref_crew_pf_avg",
            "ref_crew_home_win_pct",
            "ref_crew_games_avg",
            "ref_crew_known",
        }
        assert expected_keys == set(features.keys())
