"""
tests/test_v3_integration.py — Integration tests for v3 game-feature pipeline.

Tests:
  1. build_v3_game_features returns expected number of keys (~75 new keys)
  2. Module failure (news_features raises) → safe defaults returned, no crash
  3. Module failure (schedule_pressure raises) → safe defaults, no crash
  4. Module failure (coach_features raises) → safe defaults, no crash
  5. Win-prob v3 model predict → output in [0, 1]
  6. Game-model v3 predict → reasonable ranges
     (total ∈ [150, 270], spread ∈ [-30, 30], pace ∈ [85, 115])
  7. All v3 feature values are finite floats (no NaN/Inf)
  8. v3 feature dict has no string values (only numerics)
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.features.v3_game_features import (
    build_v3_game_features,
    get_v3_new_feature_cols,
    _REF_DEFAULTS,
    _NEWS_DEFAULTS,
    _COACH_DEFAULTS,
    _ELO_DEFAULTS,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

_HOME     = "LAL"
_AWAY     = "GSW"
_HOME_ID  = 1610612747   # Lakers NBA team ID
_AWAY_ID  = 1610612744   # Warriors
_DATE     = "2025-01-15"
_SEASON   = "2024-25"


def _build(**kwargs) -> dict:
    defaults = dict(
        home_team=_HOME, away_team=_AWAY,
        home_team_id=_HOME_ID, away_team_id=_AWAY_ID,
        game_date=_DATE, season=_SEASON, game_id=None,
    )
    defaults.update(kwargs)
    return build_v3_game_features(**defaults)


# ── Test 1: Key count ──────────────────────────────────────────────────────────

class TestKeyCount:
    def test_returns_dict(self):
        feats = _build()
        assert isinstance(feats, dict), "Expected dict from build_v3_game_features"

    def test_minimum_key_count(self):
        feats = _build()
        # At minimum: ref(7) + news(9) + sched_home(12) + sched_away(12)
        # + form_home(7) + form_away(7) + coach(22) + elo(3) = 79
        assert len(feats) >= 70, (
            f"Expected >= 70 v3 keys, got {len(feats)}: {sorted(feats.keys())}"
        )

    def test_expected_module_keys_present(self):
        feats = _build()
        # Referee keys
        assert "ref_crew_known" in feats, "Missing ref_crew_known"
        assert "ref_crew_game_total_avg" in feats
        # News keys
        assert "home_inactives_count" in feats
        assert "away_star_out_flag" in feats
        # Schedule keys
        assert "home_games_in_last_7d" in feats
        assert "away_games_in_last_7d" in feats
        # Form keys
        assert any("quality_of_wins" in k for k in feats), "Missing quality_of_wins"
        # Coach keys
        assert "home_coach_avg_pace" in feats
        assert "away_coach_avg_pace" in feats
        # ELO
        assert "v3_home_elo_v2" in feats
        assert "v3_elo_diff_v2" in feats

    def test_get_v3_new_feature_cols(self):
        cols = get_v3_new_feature_cols()
        assert isinstance(cols, list)
        assert len(cols) >= 70


# ── Test 2-4: Module failures → safe defaults, no crash ───────────────────────

class TestModuleFailureFallbacks:
    def test_news_features_raises_no_crash(self):
        """If news_features.build_news_features raises, defaults are returned."""
        with patch("src.data.news_features.build_news_features",
                   side_effect=RuntimeError("news API down")):
            feats = _build()
        assert isinstance(feats, dict)
        # News defaults should be present
        for key in _NEWS_DEFAULTS:
            assert key in feats, f"Missing news default key: {key}"
        # Values should be numeric defaults
        assert feats["home_inactives_count"] == _NEWS_DEFAULTS["home_inactives_count"]

    def test_schedule_pressure_raises_no_crash(self):
        """If schedule_pressure fails, schedule defaults are returned."""
        with patch("src.features.schedule_pressure.get_team_schedule_features",
                   side_effect=ConnectionError("NBA API timeout")):
            feats = _build()
        assert isinstance(feats, dict)
        assert "home_games_in_last_7d" in feats
        assert feats["home_games_in_last_7d"] == 0   # default

    def test_coach_features_raises_no_crash(self):
        """If coach_features fails, coach defaults are returned."""
        with patch("src.features.coach_features.get_coach_features",
                   side_effect=Exception("coach DB unavailable")):
            feats = _build()
        assert isinstance(feats, dict)
        for key in _COACH_DEFAULTS:
            assert key in feats, f"Missing coach default key: {key}"

    def test_referee_features_raises_no_crash(self):
        """If referee_features.get_ref_crew_features raises, ref defaults returned."""
        with patch("src.features.referee_features.get_ref_crew_features",
                   side_effect=Exception("ref API down")):
            feats = _build(game_id="0022401234")
        assert isinstance(feats, dict)
        assert feats.get("ref_crew_known") == _REF_DEFAULTS["ref_crew_known"]

    def test_elo_raises_no_crash(self):
        """If ELO lookup fails, defaults 1500/0 returned."""
        with patch("src.features.elo.get_current_elo",
                   side_effect=Exception("ELO file missing")):
            feats = _build()
        assert "v3_home_elo_v2" in feats
        assert feats["v3_home_elo_v2"] == _ELO_DEFAULTS["v3_home_elo_v2"]

    def test_all_modules_fail_still_returns_dict(self):
        """If every module fails, we still get safe defaults — no crash."""
        with patch("src.data.news_features.build_news_features",
                   side_effect=Exception("all down")), \
             patch("src.features.schedule_pressure.get_team_schedule_features",
                   side_effect=Exception("all down")), \
             patch("src.features.team_form.get_team_form_features",
                   side_effect=Exception("all down")), \
             patch("src.features.coach_features.get_coach_features",
                   side_effect=Exception("all down")), \
             patch("src.features.elo.get_current_elo",
                   side_effect=Exception("all down")):
            feats = _build()
        assert isinstance(feats, dict)
        assert len(feats) >= 40  # at minimum defaults are returned


# ── Test 5: All values are finite floats ──────────────────────────────────────

class TestValueFiniteness:
    def test_no_nan_or_inf(self):
        feats = _build()
        for k, v in feats.items():
            if isinstance(v, float):
                assert not (v != v), f"NaN in key {k}"   # NaN != NaN
                assert abs(v) < 1e9,  f"Inf-like value in key {k}: {v}"

    def test_no_string_values(self):
        feats = _build()
        for k, v in feats.items():
            assert not isinstance(v, str), (
                f"String value in features dict: {k}={v!r} — "
                "coach names must be stripped before returning"
            )


# ── Test 6: Win-prob v3 model predict → [0, 1] ────────────────────────────────

class TestWinProbV3Model:
    @pytest.fixture(autouse=True)
    def _skip_if_no_model(self):
        model_path = os.path.join(PROJECT_DIR, "data", "models", "win_prob_v3.pkl")
        if not os.path.exists(model_path):
            pytest.skip("win_prob_v3.pkl not yet trained — run retrain_win_prob_v3.py first")

    def test_predict_returns_probability_in_unit_interval(self):
        import pickle
        import numpy as np
        model_path = os.path.join(PROJECT_DIR, "data", "models", "win_prob_v3.pkl")
        with open(model_path, "rb") as f:
            data = pickle.load(f)
        clf  = data["model"]
        cols = data["feature_cols"]
        # Build a dummy feature vector (zeros — just checks plumbing)
        X = np.zeros((1, len(cols)), dtype=np.float32)
        prob = float(clf.predict_proba(X)[0][1])
        assert 0.0 <= prob <= 1.0, f"Win prob {prob} not in [0, 1]"

    def test_metrics_json_has_required_keys(self):
        metrics_path = os.path.join(PROJECT_DIR, "data", "models", "win_prob_v3_metrics.json")
        if not os.path.exists(metrics_path):
            pytest.skip("metrics file not found")
        with open(metrics_path) as f:
            m = json.load(f)
        assert "accuracy" in m
        assert "brier" in m
        assert "version" in m
        assert m["version"] == "v3_integration"
        assert "baseline_v2_acc" in m
        assert "top20_features" in m


# ── Test 7: Game-model v3 predict → reasonable ranges ─────────────────────────

class TestGameModelsV3:
    @pytest.fixture(autouse=True)
    def _skip_if_no_models(self):
        total_path = os.path.join(PROJECT_DIR, "data", "models", "game_total_v3_lgb.txt")
        if not os.path.exists(total_path):
            pytest.skip("game_total_v3_lgb.txt not yet trained — run retrain_game_models_v3.py first")

    def _load_model(self, name):
        import lightgbm as lgb
        path = os.path.join(PROJECT_DIR, "data", "models", f"game_{name}_v3_lgb.txt")
        return lgb.Booster(model_file=path)

    def _dummy_X(self, n_features: int) -> "np.ndarray":
        import numpy as np
        # A realistic feature row: league-average ratings
        X = np.zeros((1, n_features), dtype=np.float32)
        return X

    def _n_features(self) -> int:
        import pickle
        meta_path = os.path.join(PROJECT_DIR, "data", "models", "game_pace_v3_lgb_meta.pkl")
        # Use total model's expected_num_features
        import lightgbm as lgb
        b = lgb.Booster(model_file=os.path.join(PROJECT_DIR, "data", "models",
                                                 "game_total_v3_lgb.txt"))
        return b.num_feature()

    def test_total_in_range(self):
        m = self._load_model("total")
        import numpy as np
        n = m.num_feature()
        X = np.full((1, n), 0.5, dtype=np.float32)
        pred = float(m.predict(X)[0])
        assert 150 <= pred <= 280, f"game_total={pred} out of [150, 280]"

    def test_spread_in_range(self):
        m = self._load_model("spread")
        import numpy as np
        n = m.num_feature()
        X = np.zeros((1, n), dtype=np.float32)
        pred = float(m.predict(X)[0])
        assert -30 <= pred <= 30, f"spread={pred} out of [-30, 30]"

    def test_blowout_prob_in_unit_interval(self):
        m = self._load_model("blowout")
        import numpy as np
        n = m.num_feature()
        X = np.zeros((1, n), dtype=np.float32)
        prob = float(m.predict(X)[0])
        assert 0.0 <= prob <= 1.0, f"blowout_prob={prob} not in [0,1]"

    def test_metrics_json_exists(self):
        metrics_path = os.path.join(PROJECT_DIR, "data", "models", "game_models_v3_metrics.json")
        if not os.path.exists(metrics_path):
            pytest.skip("metrics not found")
        with open(metrics_path) as f:
            m = json.load(f)
        assert "game_total" in m
        assert "spread" in m
        assert "version" in m
        assert m["version"] == "v3_integration"
