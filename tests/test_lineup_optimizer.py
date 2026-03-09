"""Tests for LineupOptimizer (ML-05).

TDD RED phase — written before the implementation exists.
"""

import pandas as pd
import pytest


class TestLineupOptimizer:
    """Tests for LineupOptimizer behavior."""

    def test_predict_returns_dict_with_required_keys(self):
        """predict() must return a dict with offensive_gravity, defensive_disruption, lineup_score."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        m.fit(pd.DataFrame())
        result = m.predict({"lineup": [1, 2, 3, 4, 5]})
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "offensive_gravity" in result, f"Missing 'offensive_gravity': {result}"
        assert "defensive_disruption" in result, f"Missing 'defensive_disruption': {result}"
        assert "lineup_score" in result, f"Missing 'lineup_score': {result}"

    def test_predict_values_in_unit_interval(self):
        """All returned float values must be in [0, 1]."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        m.fit(pd.DataFrame())
        result = m.predict({"lineup": [1, 2, 3, 4, 5]})
        for key in ("offensive_gravity", "defensive_disruption", "lineup_score"):
            assert 0.0 <= result[key] <= 1.0, (
                f"{key}={result[key]} not in [0, 1]"
            )

    def test_lineup_score_is_weighted_average(self):
        """lineup_score must equal 0.5 * offensive_gravity + 0.5 * defensive_disruption."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        m.fit(pd.DataFrame())
        result = m.predict({"lineup": [1, 2, 3, 4, 5]})
        expected = 0.5 * result["offensive_gravity"] + 0.5 * result["defensive_disruption"]
        assert abs(result["lineup_score"] - expected) < 1e-9, (
            f"lineup_score={result['lineup_score']} != 0.5*og + 0.5*dd={expected}"
        )

    def test_unknown_track_ids_use_fallback(self):
        """Unknown track_ids must not raise — league-average fallback must be used."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        m.fit(pd.DataFrame())
        # Use IDs very unlikely to be in synthetic data
        result = m.predict({"lineup": [9999, 9998, 9997, 9996, 9995]})
        assert "lineup_score" in result
        assert 0.0 <= result["lineup_score"] <= 1.0

    def test_fit_empty_df_uses_synthetic_fallback(self):
        """fit() on empty DataFrame must not raise and populate _player_stats."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        m.fit(pd.DataFrame())
        assert m._player_stats is not None, "_player_stats must be set after fit()"
        assert len(m._player_stats) > 0, "_player_stats must be non-empty"

    def test_predict_raises_before_fit(self):
        """predict() must raise RuntimeError if called before fit()."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        with pytest.raises(RuntimeError, match="fit"):
            m.predict({"lineup": [1, 2, 3, 4, 5]})

    def test_higher_epa_lineup_scores_higher_offensive_gravity(self):
        """Higher-EPA lineups produce higher offensive_gravity than lower-EPA lineups."""
        from models.lineup_optimizer import LineupOptimizer
        import numpy as np

        m = LineupOptimizer()
        m.fit(pd.DataFrame())

        # Inject controlled player stats so we can compare deterministically
        high_epa_ids = [100, 101, 102, 103, 104]
        low_epa_ids = [200, 201, 202, 203, 204]

        for tid in high_epa_ids:
            m._player_stats[tid] = {
                "epa_per_100": 8.0,
                "avg_def_dist": 150.0,
                "avg_closing_speed": 5.0,
            }
        for tid in low_epa_ids:
            m._player_stats[tid] = {
                "epa_per_100": -4.0,
                "avg_def_dist": 150.0,
                "avg_closing_speed": 5.0,
            }

        high_result = m.predict({"lineup": high_epa_ids})
        low_result = m.predict({"lineup": low_epa_ids})
        assert high_result["offensive_gravity"] > low_result["offensive_gravity"], (
            f"Expected higher EPA lineup to score higher offensive_gravity: "
            f"high={high_result['offensive_gravity']} vs low={low_result['offensive_gravity']}"
        )

    def test_score_lineup_is_wrapper(self):
        """score_lineup(lineup) must return same result as predict({'lineup': lineup})."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        m.fit(pd.DataFrame())
        lineup = [1, 2, 3, 4, 5]
        direct = m.predict({"lineup": lineup})
        via_wrapper = m.score_lineup(lineup)
        assert abs(direct["lineup_score"] - via_wrapper["lineup_score"]) < 1e-9

    def test_compare_lineups_returns_sorted_desc(self):
        """compare_lineups() must return list sorted by lineup_score descending."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        m.fit(pd.DataFrame())
        lineups = [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10], [11, 12, 13, 14, 15]]
        results = m.compare_lineups(lineups)
        assert len(results) == 3, f"Expected 3 results, got {len(results)}"
        scores = [r["lineup_score"] for r in results]
        assert scores == sorted(scores, reverse=True), (
            f"Not sorted descending: {scores}"
        )

    def test_compare_lineups_items_have_lineup_key(self):
        """Each item in compare_lineups() must include the original lineup list."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        m.fit(pd.DataFrame())
        lineups = [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]
        results = m.compare_lineups(lineups)
        for item in results:
            assert "lineup" in item, f"Missing 'lineup' key: {item}"

    def test_save_load_round_trip_matches(self, tmp_path, monkeypatch):
        """save/load round-trip must preserve predict() output exactly."""
        from models import base as base_module
        from models.lineup_optimizer import LineupOptimizer

        monkeypatch.setattr(base_module, "ARTIFACTS_DIR", tmp_path)

        m = LineupOptimizer()
        m.fit(pd.DataFrame())
        features = {"lineup": [1, 2, 3, 4, 5]}
        result1 = m.predict(features)
        m.save()

        m2 = LineupOptimizer.load("lineup_optimizer")
        result2 = m2.predict(features)
        assert abs(result1["lineup_score"] - result2["lineup_score"]) < 1e-6, (
            f"Save/load mismatch: {result1['lineup_score']} vs {result2['lineup_score']}"
        )

    def test_model_name(self):
        """model_name must equal 'lineup_optimizer'."""
        from models.lineup_optimizer import LineupOptimizer

        assert LineupOptimizer.model_name == "lineup_optimizer"

    def test_synthetic_stats_has_expected_players(self):
        """_synthetic_stats() must return dict with SYNTHETIC_PLAYERS entries."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        stats = m._synthetic_stats()
        assert len(stats) == LineupOptimizer.SYNTHETIC_PLAYERS, (
            f"Expected {LineupOptimizer.SYNTHETIC_PLAYERS} players, got {len(stats)}"
        )

    def test_synthetic_stats_keys_are_correct(self):
        """Each player in _synthetic_stats() must have required keys."""
        from models.lineup_optimizer import LineupOptimizer

        m = LineupOptimizer()
        stats = m._synthetic_stats()
        required = {"epa_per_100", "avg_def_dist", "avg_closing_speed"}
        for tid, player_stats in stats.items():
            assert required == set(player_stats.keys()), (
                f"track_id={tid} missing keys: {required - set(player_stats.keys())}"
            )
