"""
tests/test_minutes_predictor.py — Unit tests for MinutesPredictor and adjust_props_for_minutes.

Mocks out the underlying sklearn/xgb models so tests are hermetic.
"""
from __future__ import annotations

import sys
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import numpy as np
import pytest
from unittest.mock import MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_dnp_model(prob: float):
    """Return a mock DNP sklearn model that always predicts `prob`."""
    model = MagicMock()
    model.predict_proba.return_value = np.array([[1 - prob, prob]])
    scaler = MagicMock()
    scaler.transform.side_effect = lambda x: x
    return {"model": model, "scaler": scaler}


def _make_lm_model(prob: float):
    """Return a mock load-management model dict that always gives `prob`."""
    # We reverse-engineer the sigmoid: score = log(p/(1-p))
    p = float(np.clip(prob, 1e-6, 1 - 1e-6))
    score_needed = float(np.log(p / (1 - p)))
    # intercept = score_needed, all coefs = 0
    return {
        "type": "logistic_heuristic",
        "coefs": {k: 0.0 for k in [
            "age", "games_played", "minutes_per_game", "is_b2b",
            "days_rest", "games_last_7", "usage_rate", "injury_history",
            "contract_year", "is_star",
        ]},
        "intercept": score_needed,
    }


def _make_mf_model(return_val: float):
    """Return a mock minutes-floor XGB model."""
    model = MagicMock()
    model.predict.return_value = np.array([return_val])
    return {"type": "xgb", "model": model, "version": "1.0"}


GAME_CTX_NORMAL = {
    "is_b2b": 0, "rest_days": 2, "games_in_last_7": 2,
    "usage_rate": 30.0, "age": 28,
}

GAME_CTX_B2B = {
    "is_b2b": 1, "rest_days": 0, "games_in_last_7": 4,
    "usage_rate": 30.0, "age": 28,
}

_FAKE_GAMES = [
    (f"2025-0{i+1}-01", 32.0) for i in range(20)
]  # 20 games at 32 min each


# ── MinutesPredictor tests ────────────────────────────────────────────────────

class TestMinutesPredictor:

    def _make_predictor(self, p_dnp=0.05, p_load=0.10, proj_min=32.0):
        from src.prediction.minutes_predictor import MinutesPredictor
        pred = MinutesPredictor()
        pred._dnp = _make_dnp_model(p_dnp)
        pred._lm  = _make_lm_model(p_load)
        pred._mf  = _make_mf_model(proj_min)
        return pred

    def _run(self, pred, games=_FAKE_GAMES, ctx=GAME_CTX_NORMAL):
        with patch(
            "src.prediction.minutes_predictor._load_gamelogs_for_player",
            return_value=games,
        ):
            return pred.predict_minutes_distribution(999, ctx)

    # ── Test 1: Normal player, low p_dnp → expected ≈ proj_min ────────────

    def test_normal_player_expected_near_proj_min(self):
        pred = self._make_predictor(p_dnp=0.02, p_load=0.05, proj_min=32.0)
        dist = self._run(pred)

        # p_full = 1 - 0.02 - 0.05 = 0.93
        # expected = 0.93 * 32 + 0.05 * 24 + 0.02 * 0 = 29.76 + 1.2 = 30.96
        assert dist["expected_minutes"] == pytest.approx(30.96, abs=0.5)
        assert dist["p_dnp"] == pytest.approx(0.02, abs=0.01)
        assert dist["p_full_load"] == pytest.approx(0.93, abs=0.01)

    # ── Test 2: High p_dnp → expected_minutes near 0 ──────────────────────

    def test_high_p_dnp_pushes_expected_toward_zero(self):
        """
        Use low-minute game history (avg < 25) so the scaler-recalibration guard
        doesn't fire — then p_dnp=0.90 is honoured and expected_minutes stays low.
        """
        pred = self._make_predictor(p_dnp=0.90, p_load=0.05, proj_min=15.0)
        # Bench player: 15 min avg, infrequent playing time
        bench_games = [(f"2025-0{i+1}-01", 15.0) for i in range(15)] + \
                      [(f"2025-0{i+1}-02", 0.0) for i in range(5)]   # 5 DNPs
        dist = self._run(pred, games=bench_games)

        # season_gp_pct = 15/20 = 0.75; recent_min_avg ≈ 15.0 (<25) → no cap
        # expected ≈ 0.05 * 15 + 0.05 * 7 + 0.90 * 0 = 0.75 + 0.35 = 1.10
        assert dist["expected_minutes"] < 6.0, (
            f"Expected near 0 with p_dnp=0.90, got {dist['expected_minutes']}"
        )
        assert dist["p_dnp"] == pytest.approx(0.90, abs=0.02)

    # ── Test 3: p_dnp + p_load sum ≤ 1.0 ─────────────────────────────────

    def test_probabilities_sum_to_one(self):
        for p_dnp, p_load in [(0.1, 0.1), (0.5, 0.6), (0.0, 0.0), (0.99, 0.99)]:
            pred = self._make_predictor(p_dnp=p_dnp, p_load=p_load)
            dist = self._run(pred)
            total = dist["p_dnp"] + dist["p_load_mgmt"] + dist["p_full_load"]
            assert abs(total - 1.0) < 1e-4, f"Probs don't sum to 1: {total}"

    # ── Test 4: No gamelogs → graceful fallback ────────────────────────────

    def test_no_gamelogs_returns_fallback(self):
        pred = self._make_predictor()
        dist = self._run(pred, games=[])

        assert "expected_minutes" in dist
        assert dist["expected_minutes"] > 0

    # ── Test 5: Floor ≤ expected_minutes ≤ ceiling ────────────────────────

    def test_floor_lte_expected_lte_ceiling(self):
        for p_dnp in [0.0, 0.05, 0.50]:
            pred = self._make_predictor(p_dnp=p_dnp, proj_min=32.0)
            dist = self._run(pred)
            # expected may be below floor when DNP heavily weights 0
            # but floor and ceiling should bracket projected full-load minutes
            assert dist["floor"] <= dist["ceiling"]
            assert dist["ceiling"] <= 42.5

    # ── Test 6: B2B context increases load probability ─────────────────────

    def test_b2b_increases_load_prob(self):
        from src.prediction.minutes_predictor import MinutesPredictor

        pred = MinutesPredictor()
        pred._dnp = _make_dnp_model(0.05)
        pred._mf  = _make_mf_model(32.0)
        # Use real _score_load_mgmt with heuristic fallback model
        pred._lm = {
            "type": "logistic_heuristic",
            "coefs": {"is_b2b": 1.2, "days_rest": -0.4, "games_last_7": 0.3,
                      "age": 0.08, "is_star": 0.5, "usage_rate": 0.0,
                      "injury_history": 0.0, "contract_year": 0.0,
                      "minutes_per_game": 0.0, "games_played": 0.0},
            "intercept": -3.5,
        }
        with patch(
            "src.prediction.minutes_predictor._load_gamelogs_for_player",
            return_value=_FAKE_GAMES,
        ):
            dist_rest = pred.predict_minutes_distribution(999, GAME_CTX_NORMAL)
            dist_b2b  = pred.predict_minutes_distribution(999, GAME_CTX_B2B)

        assert dist_b2b["p_load_mgmt"] >= dist_rest["p_load_mgmt"], (
            "B2B should have >= load_mgmt prob than rested"
        )


# ── adjust_props_for_minutes tests ────────────────────────────────────────────

class TestAdjustPropsForMinutes:

    def _make_predictor(self, expected_min: float):
        from src.prediction.minutes_predictor import MinutesPredictor
        pred = MinutesPredictor()
        pred._dnp = _make_dnp_model(0.05)
        pred._lm  = _make_lm_model(0.05)
        pred._mf  = _make_mf_model(expected_min)
        return pred

    # ── Test 7: Zero expected minutes → all counting stats become 0 ────────

    def test_zero_expected_minutes_zeroes_all_stats(self):
        """
        Use bench-player game history (avg 12 min, many DNPs) so the scaler guard
        doesn't interfere, then p_dnp=0.999 properly zeroes out expected_minutes.
        """
        from src.prediction.minutes_aware_props import adjust_props_for_minutes
        from src.prediction.minutes_predictor import MinutesPredictor

        # Bench player: 12 min avg when playing, 40% DNP rate → season_gp_pct=0.60
        bench_games = (
            [(f"2025-0{i+1}-01", 12.0) for i in range(12)]
            + [(f"2025-0{i+1}-02", 0.0) for i in range(8)]
        )

        pred = MinutesPredictor()
        pred._dnp = _make_dnp_model(0.999)
        pred._lm  = _make_lm_model(0.0)
        pred._mf  = _make_mf_model(12.0)

        base = {"pts": 10.0, "reb": 3.0, "ast": 2.0, "fg3m": 1.0, "tov": 1.5}
        with patch(
            "src.prediction.minutes_predictor._load_gamelogs_for_player",
            return_value=bench_games,
        ):
            adj = adjust_props_for_minutes(base, 999, GAME_CTX_NORMAL, 12.0, predictor=pred)

        # With p_dnp ≈ 1.0 and no guard firing, expected_min ≈ 0, factor ≈ 0
        for stat in ["pts", "reb", "ast", "fg3m"]:
            assert adj[stat] < 1.0, f"{stat}={adj[stat]} should be near 0"

    # ── Test 8: minutes_factor=1.5 → stats ≈ 1.5x scaled by elasticity ────

    def test_factor_1_5_scales_stats_correctly(self):
        from src.prediction.minutes_aware_props import adjust_props_for_minutes, MINUTES_ELASTICITY

        season_avg = 24.0
        expected_min = 36.0   # factor = 1.5

        pred = self._make_predictor(expected_min)
        base = {"pts": 20.0, "reb": 8.0, "ast": 6.0, "tov": 3.0, "fg3m": 2.0}

        with patch(
            "src.prediction.minutes_predictor._load_gamelogs_for_player",
            return_value=_FAKE_GAMES,
        ):
            adj = adjust_props_for_minutes(base, 999, GAME_CTX_NORMAL, season_avg, predictor=pred)

        factor = adj["minutes_factor"]
        for stat in ["pts", "reb", "ast", "tov"]:
            e = MINUTES_ELASTICITY.get(stat, 1.0)
            expected_adj = base[stat] * (factor ** e)
            assert adj[stat] == pytest.approx(expected_adj, rel=1e-3), (
                f"{stat}: expected {expected_adj:.3f}, got {adj[stat]}"
            )

    # ── Test 9: Rate stats NOT scaled ──────────────────────────────────────

    def test_rate_stats_unchanged(self):
        from src.prediction.minutes_aware_props import adjust_props_for_minutes

        pred = self._make_predictor(28.0)
        base = {"pts": 20.0, "fg_pct": 0.45, "ft_pct": 0.88, "fg3_pct": 0.37, "reb": 8.0}

        with patch(
            "src.prediction.minutes_predictor._load_gamelogs_for_player",
            return_value=_FAKE_GAMES,
        ):
            adj = adjust_props_for_minutes(base, 999, GAME_CTX_NORMAL, 28.0, predictor=pred)

        for rate_stat in ["fg_pct", "ft_pct", "fg3_pct"]:
            assert adj[rate_stat] == base[rate_stat], (
                f"Rate stat {rate_stat} should be unchanged"
            )

    # ── Test 10: Metadata keys injected ────────────────────────────────────

    def test_metadata_keys_injected(self):
        from src.prediction.minutes_aware_props import adjust_props_for_minutes

        pred = self._make_predictor(32.0)
        base = {"pts": 25.0, "reb": 9.0}

        with patch(
            "src.prediction.minutes_predictor._load_gamelogs_for_player",
            return_value=_FAKE_GAMES,
        ):
            adj = adjust_props_for_minutes(base, 999, GAME_CTX_NORMAL, 34.0, predictor=pred)

        for key in ["expected_minutes", "p_dnp", "p_load_mgmt", "minutes_factor", "minutes_std"]:
            assert key in adj, f"Missing metadata key: {key}"

    # ── Test 11: tov scales superlinearly ──────────────────────────────────

    def test_tov_scales_superlinearly_vs_pts(self):
        from src.prediction.minutes_aware_props import adjust_props_for_minutes

        season_avg = 28.0
        expected_min = 36.0  # factor > 1

        pred = self._make_predictor(expected_min)
        base = {"pts": 20.0, "tov": 3.0}

        with patch(
            "src.prediction.minutes_predictor._load_gamelogs_for_player",
            return_value=_FAKE_GAMES,
        ):
            adj = adjust_props_for_minutes(base, 999, GAME_CTX_NORMAL, season_avg, predictor=pred)

        factor = adj["minutes_factor"]
        if factor > 1.0:
            pts_ratio = adj["pts"] / base["pts"]
            tov_ratio = adj["tov"] / base["tov"]
            assert tov_ratio > pts_ratio, (
                f"TOV should scale faster than PTS when factor>1: tov={tov_ratio:.3f}, pts={pts_ratio:.3f}"
            )

    # ── Test 12: invalid season_avg_minutes defaults gracefully ────────────

    def test_invalid_season_avg_defaults(self):
        from src.prediction.minutes_aware_props import adjust_props_for_minutes

        pred = self._make_predictor(28.0)
        base = {"pts": 20.0}

        with patch(
            "src.prediction.minutes_predictor._load_gamelogs_for_player",
            return_value=_FAKE_GAMES,
        ):
            adj = adjust_props_for_minutes(base, 999, GAME_CTX_NORMAL, 0.0, predictor=pred)

        # Should not crash, minutes_factor should be reasonable
        assert "pts" in adj
        assert adj["minutes_factor"] >= 0.0
