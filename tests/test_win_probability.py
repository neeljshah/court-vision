"""Tests for WinProbabilityModel (ML-02).

TDD RED phase — these tests are written before the implementation exists.
"""

import pandas as pd
import pytest


class TestWinProbabilityModel:
    """Tests for WinProbabilityModel behavior."""

    def test_predict_returns_float_in_0_1(self):
        """predict() must return a float in [0, 1]."""
        from models.win_probability import WinProbabilityModel

        m = WinProbabilityModel()
        m.fit(pd.DataFrame())
        features = {
            "convex_hull_area": 12000.0,
            "avg_inter_player_dist": 180.0,
            "scoring_run": 4,
            "possession_streak": 2,
            "swing_point": 0,
        }
        p = m.predict(features)
        assert isinstance(p, float), f"Expected float, got {type(p)}"
        assert 0.0 <= p <= 1.0, f"Expected [0,1], got {p}"

    def test_higher_scoring_run_yields_higher_probability(self):
        """Higher scoring_run should produce higher win probability."""
        from models.win_probability import WinProbabilityModel

        m = WinProbabilityModel()
        m.fit(pd.DataFrame())
        base = {
            "convex_hull_area": 12000.0,
            "avg_inter_player_dist": 180.0,
            "possession_streak": 3,
            "swing_point": 0,
        }
        p_low = m.predict({**base, "scoring_run": -5})
        p_high = m.predict({**base, "scoring_run": 10})
        assert p_high > p_low, (
            f"Expected higher scoring_run to yield higher probability, "
            f"got {p_low} (run=-5) vs {p_high} (run=10)"
        )

    def test_fit_empty_df_uses_synthetic_fallback(self):
        """fit() on empty DataFrame must not raise."""
        from models.win_probability import WinProbabilityModel

        m = WinProbabilityModel()
        # Should not raise
        m.fit(pd.DataFrame())
        # Model should be usable after fit on empty df
        p = m.predict(
            {
                "convex_hull_area": 10000.0,
                "avg_inter_player_dist": 200.0,
                "scoring_run": 0,
                "possession_streak": 1,
                "swing_point": 0,
            }
        )
        assert 0.0 <= p <= 1.0

    def test_fit_small_df_uses_synthetic_fallback(self):
        """fit() on fewer than 20 rows uses synthetic data without raising."""
        from models.win_probability import WinProbabilityModel

        small_df = pd.DataFrame(
            {
                "convex_hull_area": [10000.0] * 5,
                "avg_inter_player_dist": [150.0] * 5,
                "scoring_run": [2] * 5,
                "possession_streak": [1] * 5,
                "swing_point": [0] * 5,
                "won": [0] * 5,
            }
        )
        m = WinProbabilityModel()
        m.fit(small_df)  # Must not raise
        p = m.predict(
            {
                "convex_hull_area": 10000.0,
                "avg_inter_player_dist": 200.0,
                "scoring_run": 0,
                "possession_streak": 1,
                "swing_point": 0,
            }
        )
        assert 0.0 <= p <= 1.0

    def test_save_load_round_trip_matches(self, tmp_path, monkeypatch):
        """save/load round-trip must preserve predict() output exactly."""
        import pathlib

        from models import base as base_module
        from models.win_probability import WinProbabilityModel

        # Redirect artifacts dir to tmp_path for isolation
        monkeypatch.setattr(base_module, "ARTIFACTS_DIR", tmp_path)

        m = WinProbabilityModel()
        m.fit(pd.DataFrame())
        features = {
            "convex_hull_area": 12000.0,
            "avg_inter_player_dist": 180.0,
            "scoring_run": 6,
            "possession_streak": 3,
            "swing_point": 0,
        }
        p1 = m.predict(features)
        m.save()

        m2 = WinProbabilityModel.load("win_probability")
        p2 = m2.predict(features)
        assert abs(p1 - p2) < 1e-6, f"Save/load mismatch: {p1} vs {p2}"

    def test_synthetic_label_rule(self):
        """_label() encodes correct synthetic rule: won if scoring_run>0 AND possession_streak>=2,
        OR swing_point=1 AND scoring_run>0."""
        from models.win_probability import WinProbabilityModel

        m = WinProbabilityModel()

        # Positive scoring run + streak >= 2 → won
        df_win = pd.DataFrame(
            {
                "scoring_run": [5],
                "possession_streak": [3],
                "swing_point": [0],
            }
        )
        assert m._label(df_win).iloc[0] == 1

        # Negative scoring run → not won
        df_lose = pd.DataFrame(
            {
                "scoring_run": [-3],
                "possession_streak": [4],
                "swing_point": [0],
            }
        )
        assert m._label(df_lose).iloc[0] == 0

        # swing_point=1 AND scoring_run>0 → won
        df_swing = pd.DataFrame(
            {
                "scoring_run": [2],
                "possession_streak": [1],  # streak < 2
                "swing_point": [1],
            }
        )
        assert m._label(df_swing).iloc[0] == 1

    def test_synthetic_df_has_200_rows(self):
        """_synthetic_df() returns exactly SYNTHETIC_ROWS rows."""
        from models.win_probability import WinProbabilityModel

        m = WinProbabilityModel()
        df = m._synthetic_df()
        assert len(df) == WinProbabilityModel.SYNTHETIC_ROWS

    def test_model_name(self):
        """model_name must equal 'win_probability'."""
        from models.win_probability import WinProbabilityModel

        assert WinProbabilityModel.model_name == "win_probability"
