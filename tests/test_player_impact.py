"""Tests for PlayerImpactModel (ML-04).

TDD RED phase — these tests are written before the implementation exists.
"""

import pandas as pd
import pytest


class TestPlayerImpactModel:
    """Tests for PlayerImpactModel behavior."""

    def test_predict_returns_dict_with_epa_per_100(self):
        """predict() must return a dict containing 'epa_per_100' key."""
        from models.player_impact import PlayerImpactModel

        m = PlayerImpactModel()
        m.fit(pd.DataFrame())
        result = m.predict(
            {
                "track_id": 7,
                "made_rate": 0.48,
                "event_mix": {"cut": 3, "screen": 1, "drift": 2},
                "shots_taken": 10,
            }
        )
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "epa_per_100" in result, f"Missing 'epa_per_100' key: {result}"

    def test_epa_per_100_is_float(self):
        """epa_per_100 value must be a float."""
        from models.player_impact import PlayerImpactModel

        m = PlayerImpactModel()
        m.fit(pd.DataFrame())
        result = m.predict(
            {
                "track_id": 1,
                "made_rate": 0.50,
                "event_mix": {},
                "shots_taken": 8,
            }
        )
        assert isinstance(result["epa_per_100"], float), (
            f"Expected float, got {type(result['epa_per_100'])}"
        )

    def test_higher_made_rate_yields_higher_epa(self):
        """Higher made_rate must produce higher epa_per_100."""
        from models.player_impact import PlayerImpactModel

        m = PlayerImpactModel()
        m.fit(pd.DataFrame())
        base = {"track_id": 1, "event_mix": {}, "shots_taken": 10}
        result_low = m.predict({**base, "made_rate": 0.30})
        result_high = m.predict({**base, "made_rate": 0.65})
        assert result_high["epa_per_100"] > result_low["epa_per_100"], (
            f"Expected higher made_rate -> higher EPA, "
            f"got {result_low['epa_per_100']} (0.30) vs {result_high['epa_per_100']} (0.65)"
        )

    def test_fit_empty_df_uses_synthetic_fallback(self):
        """fit() on empty DataFrame must not raise."""
        from models.player_impact import PlayerImpactModel

        m = PlayerImpactModel()
        m.fit(pd.DataFrame())  # Must not raise
        result = m.predict(
            {"track_id": 1, "made_rate": 0.45, "event_mix": {}, "shots_taken": 5}
        )
        assert "epa_per_100" in result

    def test_fit_sparse_df_uses_synthetic_fallback(self):
        """fit() with fewer than 5 unique track_ids uses synthetic fallback."""
        from models.player_impact import PlayerImpactModel

        # Only 3 unique track_ids — below threshold of 5
        sparse_df = pd.DataFrame(
            {
                "track_id": [1, 1, 2, 2, 3],
                "game_id": ["g1"] * 5,
                "event_type": ["cut", "screen", "drift", "cut", "screen"],
                "confidence": [0.8, 0.7, 0.9, 0.75, 0.85],
                "made": [1, 0, 1, 0, 1],
                "x": [100.0, 200.0, 300.0, 400.0, 500.0],
                "y": [150.0, 200.0, 100.0, 250.0, 180.0],
            }
        )
        m = PlayerImpactModel()
        m.fit(sparse_df)  # Must not raise
        result = m.predict(
            {"track_id": 99, "made_rate": 0.45, "event_mix": {}, "shots_taken": 5}
        )
        assert "epa_per_100" in result

    def test_save_load_round_trip_matches(self, tmp_path, monkeypatch):
        """save/load round-trip must preserve predict() output exactly."""
        from models import base as base_module
        from models.player_impact import PlayerImpactModel

        monkeypatch.setattr(base_module, "ARTIFACTS_DIR", tmp_path)

        m = PlayerImpactModel()
        m.fit(pd.DataFrame())
        features = {
            "track_id": 7,
            "made_rate": 0.55,
            "event_mix": {"cut": 3, "screen": 1, "drift": 2},
            "shots_taken": 12,
        }
        result1 = m.predict(features)
        m.save()

        m2 = PlayerImpactModel.load("player_impact")
        result2 = m2.predict(features)
        assert abs(result1["epa_per_100"] - result2["epa_per_100"]) < 1e-6, (
            f"Save/load mismatch: {result1['epa_per_100']} vs {result2['epa_per_100']}"
        )

    def test_rank_players_returns_list(self):
        """rank_players() must return a list."""
        from models.player_impact import PlayerImpactModel

        m = PlayerImpactModel()
        m.fit(pd.DataFrame())
        rankings = m.rank_players()
        assert isinstance(rankings, list), f"Expected list, got {type(rankings)}"

    def test_rank_players_sorted_by_epa_descending(self):
        """rank_players() list must be sorted by epa_per_100 descending."""
        from models.player_impact import PlayerImpactModel

        m = PlayerImpactModel()
        m.fit(pd.DataFrame())
        rankings = m.rank_players()
        if len(rankings) > 1:
            epas = [r["epa_per_100"] for r in rankings]
            assert epas == sorted(epas, reverse=True), (
                f"Rankings not sorted descending: {epas}"
            )

    def test_rank_players_items_have_required_keys(self):
        """Each item in rank_players() must have track_id and epa_per_100."""
        from models.player_impact import PlayerImpactModel

        m = PlayerImpactModel()
        m.fit(pd.DataFrame())
        rankings = m.rank_players()
        for item in rankings:
            assert "track_id" in item, f"Missing track_id: {item}"
            assert "epa_per_100" in item, f"Missing epa_per_100: {item}"

    def test_synthetic_df_has_10_players(self):
        """_synthetic_df() must return exactly SYNTHETIC_PLAYERS rows."""
        from models.player_impact import PlayerImpactModel

        m = PlayerImpactModel()
        df = m._synthetic_df()
        assert len(df) == PlayerImpactModel.SYNTHETIC_PLAYERS

    def test_model_name(self):
        """model_name must equal 'player_impact'."""
        from models.player_impact import PlayerImpactModel

        assert PlayerImpactModel.model_name == "player_impact"

    def test_aggregate_produces_expected_columns(self):
        """_aggregate() must produce per-player feature DataFrame with expected columns."""
        from models.player_impact import PlayerImpactModel

        m = PlayerImpactModel()
        df = pd.DataFrame(
            {
                "track_id": [1, 1, 2, 2, 2],
                "game_id": ["g1"] * 5,
                "event_type": ["cut", "screen", "cut", "drift", "screen"],
                "confidence": [0.8, 0.7, 0.9, 0.75, 0.85],
                "made": [1, 0, 1, 0, 1],
                "x": [100.0, 200.0, 300.0, 400.0, 500.0],
                "y": [150.0, 200.0, 100.0, 250.0, 180.0],
            }
        )
        agg = m._aggregate(df)
        expected_cols = {
            "track_id", "made_rate", "shots_taken", "cut_rate",
            "screen_rate", "avg_confidence", "x_mean",
        }
        assert expected_cols.issubset(set(agg.columns)), (
            f"Missing columns: {expected_cols - set(agg.columns)}"
        )
        assert len(agg) == 2  # 2 unique track_ids
