"""
test_position_priors.py — Unit tests for src/features/position_priors.py

Tests fit on a synthetic 3-player × 10-game dataset — no NBA API calls,
no disk writes that interfere with existing models.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import List
from unittest.mock import patch

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import src.features.position_priors as _pp


# ── Synthetic fixtures ─────────────────────────────────────────────────────────

def _make_gamelog(player_id: int, position: str, n_games: int,
                  pts_mean: float, reb_mean: float, blk_mean: float) -> List[dict]:
    """Return n_games synthetic game-log rows for one player."""
    rows = []
    import random
    rng = random.Random(player_id)
    for i in range(n_games):
        rows.append({
            "player_id": player_id,
            "position": position,
            "game_date": f"2024-01-{i+1:02d}",
            "min": 30.0,
            "pts": max(0, pts_mean + rng.gauss(0, 3)),
            "reb": max(0, reb_mean + rng.gauss(0, 2)),
            "ast": max(0, 3.0   + rng.gauss(0, 1)),
            "fg3m": 1.2,
            "stl": 0.9,
            "blk": max(0, blk_mean + rng.gauss(0, 0.3)),
            "tov": 1.8,
            "age": 27,
        })
    return rows


_SYNTHETIC_DATA = {
    "2544":  _make_gamelog(2544,  "G",  10, pts_mean=22.0, reb_mean=4.0, blk_mean=0.3),
    "203999": _make_gamelog(203999, "F",  10, pts_mean=14.0, reb_mean=6.5, blk_mean=0.7),
    "76003":  _make_gamelog(76003,  "C",  10, pts_mean=11.0, reb_mean=9.0, blk_mean=1.6),
}


@pytest.fixture()
def tmp_dirs(tmp_path, monkeypatch):
    """Redirect all data paths to temp dirs."""
    nba_dir   = tmp_path / "nba"
    model_dir = tmp_path / "models"
    cache_dir = tmp_path / "cache"
    nba_dir.mkdir()
    model_dir.mkdir()
    cache_dir.mkdir()

    # Write synthetic gamelogs
    gamelog_path = nba_dir / "gamelog_full_synthetic_2024-25.json"
    gamelog_path.write_text(json.dumps(_SYNTHETIC_DATA))

    monkeypatch.setattr(_pp, "_NBA_CACHE",   str(nba_dir))
    monkeypatch.setattr(_pp, "_MODEL_DIR",   str(model_dir))
    monkeypatch.setattr(_pp, "_CACHE_DIR",   str(cache_dir))
    monkeypatch.setattr(_pp, "_PRIORS_PATH", str(model_dir / "position_priors.json"))
    monkeypatch.setattr(_pp, "_POS_CACHE",   str(cache_dir / "positions.json"))
    monkeypatch.setattr(_pp, "_priors_cache", None)
    monkeypatch.setattr(_pp, "_position_cache", None)
    # Block real NBA API calls
    monkeypatch.setenv("NBA_OFFLINE", "1")

    return tmp_path


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestBuildPositionPriors:
    def test_build_returns_dict_with_all_stats(self, tmp_dirs):
        priors = _pp.build_position_priors(seasons=["2024-25"])
        assert isinstance(priors, dict)
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            assert stat in priors, f"stat {stat!r} missing from priors"

    def test_positions_assigned_from_gamelog(self, tmp_dirs):
        priors = _pp.build_position_priors(seasons=["2024-25"])
        # G player should have higher pts prior than C
        g_pts  = priors["pts"]["G"]["mean"]
        c_pts  = priors["pts"]["C"]["mean"]
        assert g_pts > c_pts, f"Expected G pts > C pts, got {g_pts:.2f} vs {c_pts:.2f}"

    def test_blk_prior_differentiated_by_position(self, tmp_dirs):
        priors = _pp.build_position_priors(seasons=["2024-25"])
        c_blk  = priors["blk"]["C"]["mean"]
        g_blk  = priors["blk"]["G"]["mean"]
        assert c_blk > g_blk, f"Expected C blk > G blk, got {c_blk:.2f} vs {g_blk:.2f}"

    def test_reb_prior_differentiated_by_position(self, tmp_dirs):
        priors = _pp.build_position_priors(seasons=["2024-25"])
        c_reb = priors["reb"]["C"]["mean"]
        g_reb = priors["reb"]["G"]["mean"]
        assert c_reb > g_reb, f"Expected C reb > G reb, got {c_reb:.2f} vs {g_reb:.2f}"

    def test_priors_persisted_to_json(self, tmp_dirs):
        priors = _pp.build_position_priors(seasons=["2024-25"])
        path = os.path.join(str(tmp_dirs), "models", "position_priors.json")
        assert os.path.exists(path), "position_priors.json not written"
        with open(path) as f:
            loaded = json.load(f)
        assert "pts" in loaded

    def test_shrinkage_k_correct(self, tmp_dirs):
        priors = _pp.build_position_priors(seasons=["2024-25"])
        # High-volume stats: K=15
        assert priors["pts"]["G"]["K"] == 15
        assert priors["reb"]["G"]["K"] == 15
        # Tail stats: K=30
        assert priors["blk"]["G"]["K"] == 30
        assert priors["stl"]["G"]["K"] == 30
        assert priors["fg3m"]["G"]["K"] == 30


class TestGetPositionPrior:
    def test_returns_tuple_mean_k(self, tmp_dirs):
        _pp.build_position_priors(seasons=["2024-25"])
        mean, K = _pp.get_position_prior("pts", "G", "2024-25")
        assert isinstance(mean, float)
        assert isinstance(K, int)
        assert mean > 0
        assert K > 0

    def test_fallback_for_unknown_stat(self, tmp_dirs):
        _pp.build_position_priors(seasons=["2024-25"])
        mean, K = _pp.get_position_prior("unknown_stat", "G", "2024-25")
        assert isinstance(mean, float)
        assert isinstance(K, int)

    def test_unknown_position_defaults_to_f(self, tmp_dirs):
        _pp.build_position_priors(seasons=["2024-25"])
        mean_f, K_f   = _pp.get_position_prior("pts", "F",  "2024-25")
        mean_unk, K_unk = _pp.get_position_prior("pts", "XYZ", "2024-25")
        # XYZ → "F"
        assert mean_unk == mean_f


class TestGetPositionPriors:
    def test_returns_series_indexed_by_player_id(self, tmp_dirs):
        import pandas as pd
        _pp.build_position_priors(seasons=["2024-25"])

        # Pre-populate position cache with synthetic positions
        _pp._position_cache = {"2544": "G", "203999": "F", "76003": "C"}

        result = _pp.get_position_priors([2544, 203999, 76003], "pts", "2024-25")
        assert isinstance(result, pd.Series)
        assert set(result.index) == {2544, 203999, 76003}
        assert result[2544] > result[76003], "G pts prior should exceed C"


class TestGetPosition:
    def test_cached_position_returned(self, tmp_dirs):
        _pp._position_cache = {"99999": "C"}
        pos = _pp.get_position(99999)
        assert pos == "C"

    def test_missing_defaults_to_f(self, tmp_dirs):
        _pp._position_cache = {}
        pos = _pp.get_position(12345678)
        assert pos == "F"
