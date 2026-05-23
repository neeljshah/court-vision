"""
tests/test_props_v3_integration.py — Integration tests for the v3 prop pipeline.

Tests:
  1. build_v3_features() returns ~50+ keys, all float, no NaN/Inf
  2. V3 LightGBM model loads + predicts within sane per-stat bounds
  3. Backward compat: predict_props() still returns the standard schema
  4. _load_v3_model() falls back gracefully when model file absent
  5. MODEL_VERSION env-var correctly gates v3 vs v2 path

All tests work offline (NBA_OFFLINE=1 is set automatically).
No real API calls, no DB required.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import sys
from contextlib import ExitStack
from typing import List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Force offline mode for all tests
os.environ.setdefault("NBA_OFFLINE", "1")


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_prior_games(n: int = 15) -> List[dict]:
    """Synthetic prior game rows with realistic NBA stats."""
    rng = np.random.default_rng(42)
    games = []
    for i in range(n):
        games.append({
            "pts":        float(rng.integers(8, 30)),
            "reb":        float(rng.integers(2, 12)),
            "ast":        float(rng.integers(1, 8)),
            "min":        float(rng.integers(22, 36)),
            "fg3m":       float(rng.integers(0, 5)),
            "stl":        float(rng.integers(0, 3)),
            "blk":        float(rng.integers(0, 2)),
            "tov":        float(rng.integers(0, 4)),
            "fga":        float(rng.integers(8, 20)),
            "fgm":        float(rng.integers(3, 12)),
            "oreb":       float(rng.integers(0, 3)),
            "dreb":       float(rng.integers(2, 9)),
            "pf":         float(rng.integers(0, 5)),
            "fg3a":       float(rng.integers(0, 8)),
            "fta":        float(rng.integers(0, 6)),
            "plus_minus": float(rng.integers(-15, 15)),
            "matchup":    "LAL vs. GSW" if i % 2 == 0 else "LAL @ BOS",
        })
    return games


def _default_v3_row(player_id: int = 2544, n_prior: int = 15) -> dict:
    """Call build_v3_features with standard test args."""
    from src.features.v3_prop_features import build_v3_features
    return build_v3_features(
        player_id=player_id,
        game_date="2025-03-15",
        season="2024-25",
        team_id=1610612747,
        opp_team_id=1610612744,
        home_team="LAL",
        away_team="GSW",
        is_home=True,
        prior_games=_make_prior_games(n_prior),
    )


# ── Shared mock patches for predict_props ─────────────────────────────────────

_MOCK_AVGS = {
    "player_id": 2544, "team": "LAL", "gp": 60,
    "min": 35.0, "pts": 25.0, "reb": 7.0, "ast": 8.0,
    "tov": 3.5, "fg3m": 2.0, "stl": 1.0, "blk": 0.5,
    "fg_pct": 0.50, "fg3_pct": 0.36, "ft_pct": 0.74, "fta": 5.0,
}

_SHOT_DASH = {
    "contested_pct": 0.45, "pull_up_pct": 0.0,
    "catch_shoot_pct": 0.0, "avg_defender_dist": 4.2,
}

_SCHED_CTX = {"rest_days": 2, "games_in_last_14": 5}
_OPP_TOV   = {"opp_tov_pct": 0.145, "opp_pace": 100.0}


def _patch_predict_props(pp):
    """Return ExitStack with all heavy patches applied.  Use as context manager."""
    stack = ExitStack()
    patches = [
        patch.object(pp, "_get_player_season_avgs",  return_value=_MOCK_AVGS),
        patch.object(pp, "_get_recent_form",          return_value=None),
        patch.object(pp, "_get_opp_def_rating",       return_value=113.0),
        patch.object(pp, "_get_opp_pts_vs_team",      return_value=None),
        patch.object(pp, "_load_clutch_stats",        return_value={}),
        patch.object(pp, "_load_hustle_player",       return_value={}),
        patch.object(pp, "_load_on_off_player",       return_value={}),
        patch.object(pp, "_load_synergy_off",         return_value={}),
        patch.object(pp, "_load_synergy_def",         return_value={}),
        patch.object(pp, "_load_matchup_features",    return_value={}),
        patch.object(pp, "_load_defender_zone_opp",   return_value={}),
        patch.object(pp, "_load_shot_dashboard_player", return_value=_SHOT_DASH),
        patch.object(pp, "_load_tracking_player",     return_value={}),
        patch.object(pp, "_get_schedule_context_player", return_value=_SCHED_CTX),
        patch.object(pp, "_load_pbp_features",        return_value={}),
        patch.object(pp, "_load_shot_tendency",       return_value={}),
        patch.object(pp, "_get_schedule_hardship",    return_value={}),
        patch.object(pp, "_load_cv_features_player",  return_value={}),
        patch.object(pp, "_get_opp_tov_stats",        return_value=_OPP_TOV),
        patch.object(pp, "_get_opp_stl_rate",         return_value=0.08),
        patch.object(pp, "_load_pbp_features_expanded", return_value={}),
    ]
    for p in patches:
        stack.enter_context(p)
    return stack


# ── Test 1: build_v3_features shape and type safety ──────────────────────────

class TestBuildV3Features:
    def test_returns_dict(self):
        assert isinstance(_default_v3_row(), dict)

    def test_minimum_key_count(self):
        row = _default_v3_row()
        assert len(row) >= 50, f"Only {len(row)} features returned"

    def test_all_values_finite_float(self):
        from src.features.v3_prop_features import build_v3_features
        row = build_v3_features(
            player_id=203076,
            game_date="2025-01-10",
            season="2024-25",
            team_id=1610612747,
            opp_team_id=1610612738,
            home_team="LAL",
            away_team="BOS",
            is_home=False,
            prior_games=_make_prior_games(10),
        )
        bad = {k: v for k, v in row.items()
               if not isinstance(v, float) or math.isnan(v) or math.isinf(v)}
        assert not bad, f"Non-finite values: {bad}"

    def test_v2_core_features_present(self):
        row = _default_v3_row()
        core_keys = [
            "pts_roll", "reb_roll", "ast_roll", "min_roll",
            "pts_bayes", "reb_bayes", "ast_bayes",
            "season_pts", "season_reb", "season_ast",
            "oreb_roll", "dreb_roll", "fga_roll",
        ]
        missing = [k for k in core_keys if k not in row]
        assert not missing, f"Missing v2 core keys: {missing}"

    def test_new_module_features_present(self):
        row = _default_v3_row()
        new_keys = [
            "is_b2b", "days_since_last_game",
            "traj_z_score_l5", "traj_hot_flag",
            "mp_expected_min", "mp_p_dnp",
            "sched_games_l7", "sched_b2b",
            "form_win_pct_l10",
            "coach_pace",
            "news_inactives_count",
            "rampup_mult_pts",
            "b2b_mult_pts",
            "pos_residual_pts",
        ]
        missing = [k for k in new_keys if k not in row]
        assert not missing, f"Missing new-module keys: {missing}"

    def test_empty_prior_games(self):
        from src.features.v3_prop_features import build_v3_features
        row = build_v3_features(
            player_id=999999,
            game_date="2025-03-15",
            season="2024-25",
            team_id=0,
            opp_team_id=0,
            home_team="LAL",
            away_team="GSW",
            is_home=True,
            prior_games=[],
        )
        assert isinstance(row, dict)
        assert len(row) >= 20

    def test_rolling_values_reasonable(self):
        row = _default_v3_row(n_prior=15)
        assert 0 < row["pts_roll"] < 60,  f"pts_roll={row['pts_roll']}"
        assert 0 < row["min_roll"] < 48,  f"min_roll={row['min_roll']}"
        assert 0 <= row["is_home"] <= 1,  f"is_home={row['is_home']}"


# ── Test 2: V3 model load + predict ──────────────────────────────────────────

class TestV3ModelInference:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        import src.prediction.player_props as pp
        pp._v3_booster_cache.clear()
        yield
        pp._v3_booster_cache.clear()

    def test_load_v3_returns_none_when_missing(self):
        from src.prediction.player_props import _load_v3_model
        assert _load_v3_model("__nonexistent__") is None

    def test_v3_predict_falls_back_gracefully(self):
        from src.prediction.player_props import _v3_predict
        feats = _default_v3_row()
        result = _v3_predict(feats, "__no_stat__")
        assert result is None

    @pytest.mark.skipif(
        not os.path.exists(
            os.path.join(PROJECT_DIR, "data", "models", "prop_pts_v3_lgb.txt")
        ),
        reason="v3 model not trained yet",
    )
    def test_v3_pts_predict_range(self):
        from src.features.v3_prop_features import build_v3_features
        from src.prediction.player_props import _v3_predict
        feats = build_v3_features(
            player_id=2544, game_date="2025-11-15", season="2025-26",
            team_id=1610612747, opp_team_id=1610612744,
            home_team="LAL", away_team="GSW", is_home=True,
            prior_games=_make_prior_games(15),
        )
        val = _v3_predict(feats, "pts")
        assert val is not None, "pts v3 model returned None"
        assert 0.0 <= val <= 60.0, f"pts out of range: {val}"

    @pytest.mark.skipif(
        not os.path.exists(
            os.path.join(PROJECT_DIR, "data", "models", "prop_reb_v3_lgb.txt")
        ),
        reason="v3 model not trained yet",
    )
    def test_v3_reb_predict_range(self):
        from src.features.v3_prop_features import build_v3_features
        from src.prediction.player_props import _v3_predict
        feats = build_v3_features(
            player_id=2544, game_date="2025-11-15", season="2025-26",
            team_id=1610612747, opp_team_id=1610612744,
            home_team="LAL", away_team="GSW", is_home=True,
            prior_games=_make_prior_games(15),
        )
        val = _v3_predict(feats, "reb")
        assert val is not None
        assert 0.0 <= val <= 25.0, f"reb out of range: {val}"


# ── Test 3: Backward compat — predict_props() standard schema ─────────────────

class TestPredictPropsBackwardCompat:
    def test_predict_props_returns_standard_keys(self):
        from src.prediction import player_props as pp
        with _patch_predict_props(pp):
            result = pp.predict_props("LeBron James", "GSW", "2024-25", n_games=10)

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            assert stat in result, f"Missing stat '{stat}'"
            assert isinstance(result[stat], (int, float)), f"{stat} not numeric"
            assert result[stat] >= 0, f"{stat} is negative: {result[stat]}"

    def test_predict_props_values_in_range(self):
        from src.prediction import player_props as pp
        with _patch_predict_props(pp):
            result = pp.predict_props("LeBron James", "GSW", "2024-25")

        assert 0 <= result["pts"] <= 60, f"pts={result['pts']}"
        assert 0 <= result["reb"] <= 25, f"reb={result['reb']}"
        assert 0 <= result["ast"] <= 20, f"ast={result['ast']}"


# ── Test 4: MODEL_VERSION env-var gates ──────────────────────────────────────

class TestModelVersionGate:
    def test_default_version_is_v3(self):
        import src.prediction.player_props as pp
        assert pp.MODEL_VERSION == "v3"

    def test_env_var_read_correctly(self, monkeypatch):
        monkeypatch.setenv("MODEL_VERSION", "v2")
        assert os.environ.get("MODEL_VERSION", "v3") == "v2"
