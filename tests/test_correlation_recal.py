"""tests/test_correlation_recal.py

Tests for CV_ARCHETYPE_CORR gated correlation recalibration.

(a) Flag OFF  -> _correlation returns byte-identical values to the pre-change
    engine for same-player, teammate, opponent, and mixed OVER/UNDER pairs.
(b) Flag ON   -> returns the recalibrated/archetype values.
(c) _mu (q50 means) and per-leg sigma are UNCHANGED by the flag.
(d) Covariance stays PSD (Cholesky succeeds).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.parlay_engine import (
    _correlation,
    _SAME_PLAYER_RHO,
    _TEAMMATE_RHO,
    _OPPONENT_RHO,
    ParlayEngine,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal bet dicts
# ---------------------------------------------------------------------------
GAME_A = "0022500001"
GAME_B = "0022500002"

# A known SPOT_UP_SHOOTER player_id from the archetype map
SPOT_UP_PID = 1630530  # verified SPOT_UP_SHOOTER in player_archetype_sameplayer.json
OTHER_PID    = 203999   # a player that will likely be OTHER or HIGH_AST_PLAYMAKER
TEAMMATE_PID = 201939   # teammate (different player, same team)


def make_bet(
    player_id, team, stat, side="OVER", game_id=GAME_A
) -> dict:
    return {
        "bet_id": f"{player_id}_{stat}_{side}",
        "player_id": player_id,
        "team": team,
        "prop_stat": stat,
        "side": side,
        "game_id": game_id,
        "q50": 15.0,
        "line": 14.5,
        "best_price": -110,
    }


# ---------------------------------------------------------------------------
# Part (a): Flag OFF -> byte-identical to naive engine
# ---------------------------------------------------------------------------

class TestFlagOffByteIdentical:
    """All _correlation results must be exactly equal to the naive lookup
    when CV_ARCHETYPE_CORR is not set (default)."""

    def setup_method(self):
        os.environ.pop("CV_ARCHETYPE_CORR", None)

    def teardown_method(self):
        os.environ.pop("CV_ARCHETYPE_CORR", None)

    def _naive_same_player(self, sa, sb):
        key = frozenset((sa, sb))
        return _SAME_PLAYER_RHO.get(key, 0.0)

    def _naive_teammate(self, sa, sb):
        key = frozenset((sa, sb))
        return _TEAMMATE_RHO.get(key, 0.0)

    def _naive_opponent(self, sa, sb):
        key = frozenset((sa, sb))
        return _OPPONENT_RHO.get(key, 0.05)

    @pytest.mark.parametrize("stat_a,stat_b", [
        ("pts", "ast"),
        ("pts", "reb"),
        ("pts", "fg3m"),
        ("pts", "tov"),
        ("ast", "tov"),
        ("reb", "blk"),
    ])
    def test_same_player_same_side(self, stat_a, stat_b):
        bet_a = make_bet(OTHER_PID, "LAL", stat_a, "OVER")
        bet_b = make_bet(OTHER_PID, "LAL", stat_b, "OVER")
        expected = max(-0.95, min(0.95, self._naive_same_player(stat_a, stat_b)))
        assert _correlation(bet_a, bet_b) == pytest.approx(expected, abs=1e-9)

    @pytest.mark.parametrize("stat_a,stat_b", [
        ("pts", "ast"),
        ("pts", "reb"),
        ("ast", "tov"),
    ])
    def test_same_player_mixed_side_flag_off_preserves_sign_flip(self, stat_a, stat_b):
        """Flag OFF keeps the existing (buggy) sign flip for mixed sides."""
        bet_a = make_bet(OTHER_PID, "LAL", stat_a, "OVER")
        bet_b = make_bet(OTHER_PID, "LAL", stat_b, "UNDER")
        naive = self._naive_same_player(stat_a, stat_b)
        # sign flip: rho = -naive
        expected = max(-0.95, min(0.95, -naive))
        assert _correlation(bet_a, bet_b) == pytest.approx(expected, abs=1e-9)

    @pytest.mark.parametrize("stat_a,stat_b", [
        ("pts", "pts"),
        ("pts", "ast"),
        ("reb", "reb"),
        ("ast", "ast"),
    ])
    def test_teammate_same_side(self, stat_a, stat_b):
        bet_a = make_bet(OTHER_PID, "LAL", stat_a, "OVER")
        bet_b = make_bet(TEAMMATE_PID, "LAL", stat_b, "OVER")
        expected = max(-0.95, min(0.95, self._naive_teammate(stat_a, stat_b)))
        assert _correlation(bet_a, bet_b) == pytest.approx(expected, abs=1e-9)

    @pytest.mark.parametrize("stat_a,stat_b", [
        ("pts", "pts"),
        ("ast", "ast"),
        ("reb", "reb"),
    ])
    def test_opponent_same_side(self, stat_a, stat_b):
        bet_a = make_bet(OTHER_PID, "LAL", stat_a, "OVER")
        bet_b = make_bet(TEAMMATE_PID, "BOS", stat_b, "OVER")
        expected = max(-0.95, min(0.95, self._naive_opponent(stat_a, stat_b)))
        assert _correlation(bet_a, bet_b) == pytest.approx(expected, abs=1e-9)

    def test_different_games_returns_zero(self):
        bet_a = make_bet(OTHER_PID, "LAL", "pts", game_id=GAME_A)
        bet_b = make_bet(TEAMMATE_PID, "LAL", "pts", game_id=GAME_B)
        assert _correlation(bet_a, bet_b) == pytest.approx(0.0, abs=1e-9)

    def test_teammate_mixed_side_sign_flip_preserved(self):
        bet_a = make_bet(OTHER_PID, "LAL", "pts", "OVER")
        bet_b = make_bet(TEAMMATE_PID, "LAL", "pts", "UNDER")
        naive = _TEAMMATE_RHO.get(frozenset(("pts", "pts")), 0.0)
        expected = max(-0.95, min(0.95, -naive))
        assert _correlation(bet_a, bet_b) == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------------------
# Part (b): Flag ON -> recalibrated/archetype values
# ---------------------------------------------------------------------------

class TestFlagOnRecalibratedValues:

    def setup_method(self):
        os.environ["CV_ARCHETYPE_CORR"] = "1"
        # Clear lru_caches so fresh data is loaded.
        try:
            from src.prediction import correlation_recal
            correlation_recal.clear_caches()
        except Exception:
            pass

    def teardown_method(self):
        os.environ.pop("CV_ARCHETYPE_CORR", None)
        try:
            from src.prediction import correlation_recal
            correlation_recal.clear_caches()
        except Exception:
            pass

    def test_pts_pts_teammate_near_zero_not_minus015(self):
        """Global recalibrated pts-pts teammate should be ~0, not -0.15."""
        bet_a = make_bet(OTHER_PID, "LAL", "pts", "OVER")
        bet_b = make_bet(TEAMMATE_PID, "LAL", "pts", "OVER")
        rho = _correlation(bet_a, bet_b)
        # Should be closer to 0 than to -0.15
        assert abs(rho) < 0.05, f"pts-pts teammate rho={rho} should be near 0"
        # Explicitly NOT the naive -0.15
        assert rho != pytest.approx(-0.15, abs=0.05)

    def test_ast_tov_same_player_recalibrated(self):
        """Global ast-tov same-player should be ~0.11, not 0.40."""
        bet_a = make_bet(OTHER_PID, "LAL", "ast", "OVER")
        bet_b = make_bet(OTHER_PID, "LAL", "tov", "OVER")
        rho = _correlation(bet_a, bet_b)
        # Recalibrated global: ~0.09-0.12 range (n-weighted average)
        assert rho < 0.25, f"ast-tov rho={rho} should be well below naive 0.40"
        assert rho >= 0.0, f"ast-tov rho={rho} should still be positive"

    def test_spot_up_fg3m_pts_higher(self):
        """SPOT_UP_SHOOTER fg3m-pts should be ~0.74 (vs naive 0.55)."""
        bet_a = make_bet(SPOT_UP_PID, "LAL", "fg3m", "OVER")
        bet_b = make_bet(SPOT_UP_PID, "LAL", "pts", "OVER")
        rho = _correlation(bet_a, bet_b)
        # SPOT_UP_SHOOTER refined fg3m_pts = 0.738
        assert rho > 0.65, f"SPOT_UP fg3m-pts rho={rho} should be > 0.65"
        # Should exceed the naive 0.55
        assert rho > 0.55, f"rho={rho} should exceed naive 0.55"

    def test_pts_tov_same_player_recalibrated(self):
        """Global pts-tov same-player should be ~0.12-0.18, not 0.35."""
        bet_a = make_bet(OTHER_PID, "LAL", "pts", "OVER")
        bet_b = make_bet(OTHER_PID, "LAL", "tov", "OVER")
        rho = _correlation(bet_a, bet_b)
        assert rho < 0.25, f"pts-tov rho={rho} should be well below naive 0.35"
        assert rho >= 0.0

    def test_reb_blk_same_player_recalibrated(self):
        """Global reb-blk same-player should be ~0.14-0.16, not 0.35."""
        bet_a = make_bet(OTHER_PID, "LAL", "reb", "OVER")
        bet_b = make_bet(OTHER_PID, "LAL", "blk", "OVER")
        rho = _correlation(bet_a, bet_b)
        assert rho < 0.25, f"reb-blk rho={rho} should be well below naive 0.35"
        assert rho >= 0.0

    def test_opponent_branch_unchanged(self):
        """Opponent branch must NOT be affected by the recal flag."""
        bet_a = make_bet(OTHER_PID, "LAL", "pts", "OVER")
        bet_b = make_bet(TEAMMATE_PID, "BOS", "pts", "OVER")
        rho = _correlation(bet_a, bet_b)
        expected = _OPPONENT_RHO.get(frozenset(("pts", "pts")), 0.05)
        assert rho == pytest.approx(expected, abs=1e-9)

    def test_different_games_still_zero(self):
        os.environ["CV_ARCHETYPE_CORR"] = "1"
        bet_a = make_bet(OTHER_PID, "LAL", "pts", game_id=GAME_A)
        bet_b = make_bet(TEAMMATE_PID, "LAL", "pts", game_id=GAME_B)
        assert _correlation(bet_a, bet_b) == pytest.approx(0.0)

    def test_parlay_fix_mixed_side_still_applies_when_both_flags_on(self):
        """With recal ON and PARLAY_FIX_MIXED_SIDE OFF (default): mixed sides
        still get the sign flip on the recalibrated rho."""
        from src.prediction import parlay_engine
        if parlay_engine._PARLAY_FIX_MIXED_SIDE:
            pytest.skip("CV_PARLAY_FIX_MIXED_SIDE is ON in this environment")
        bet_a = make_bet(OTHER_PID, "LAL", "pts", "OVER")
        bet_b = make_bet(OTHER_PID, "LAL", "ast", "UNDER")
        rho_mixed = _correlation(bet_a, bet_b)
        bet_a2 = make_bet(OTHER_PID, "LAL", "pts", "OVER")
        bet_b2 = make_bet(OTHER_PID, "LAL", "ast", "OVER")
        rho_same = _correlation(bet_a2, bet_b2)
        # Sign should be flipped
        assert rho_mixed == pytest.approx(-rho_same, abs=1e-9)


# ---------------------------------------------------------------------------
# Part (c): mu (q50 means) and per-leg sigma unchanged by flag
# ---------------------------------------------------------------------------

class TestMuAndSigmaUnchanged:
    """AST marginal stays raw: q50 means and sigma are NOT touched by recal."""

    BETS = [
        {
            "bet_id": "a1", "player_id": OTHER_PID, "team": "LAL",
            "prop_stat": "pts", "side": "OVER", "game_id": GAME_A,
            "q50": 25.0, "line": 24.5, "best_price": -110,
        },
        {
            "bet_id": "a2", "player_id": OTHER_PID, "team": "LAL",
            "prop_stat": "ast", "side": "OVER", "game_id": GAME_A,
            "q50": 8.0, "line": 7.5, "best_price": -110,
        },
    ]

    def test_mu_unchanged_flag_off(self):
        os.environ.pop("CV_ARCHETYPE_CORR", None)
        eng = ParlayEngine(self.BETS, rng_seed=42)
        assert eng._mu[0] == pytest.approx(25.0)
        assert eng._mu[1] == pytest.approx(8.0)

    def test_mu_unchanged_flag_on(self):
        os.environ["CV_ARCHETYPE_CORR"] = "1"
        try:
            from src.prediction import correlation_recal
            correlation_recal.clear_caches()
        except Exception:
            pass
        try:
            eng = ParlayEngine(self.BETS, rng_seed=42)
            assert eng._mu[0] == pytest.approx(25.0)
            assert eng._mu[1] == pytest.approx(8.0)
        finally:
            os.environ.pop("CV_ARCHETYPE_CORR", None)

    def test_sigma_unchanged_flag_on(self):
        """Per-leg sigma must not be affected by CV_ARCHETYPE_CORR."""
        os.environ.pop("CV_ARCHETYPE_CORR", None)
        eng_off = ParlayEngine(self.BETS, rng_seed=42)
        sigma_off = eng_off._sigma.copy()

        os.environ["CV_ARCHETYPE_CORR"] = "1"
        try:
            from src.prediction import correlation_recal
            correlation_recal.clear_caches()
            eng_on = ParlayEngine(self.BETS, rng_seed=42)
            np.testing.assert_array_equal(eng_on._sigma, sigma_off)
        finally:
            os.environ.pop("CV_ARCHETYPE_CORR", None)

    def teardown_method(self):
        os.environ.pop("CV_ARCHETYPE_CORR", None)


# ---------------------------------------------------------------------------
# Part (d): Covariance PSD — Cholesky succeeds
# ---------------------------------------------------------------------------

class TestCovariancePSD:
    BETS_5LEG = [
        {
            "bet_id": f"p{i}", "player_id": SPOT_UP_PID, "team": "LAL",
            "prop_stat": stat, "side": "OVER", "game_id": GAME_A,
            "q50": 10.0 + i, "line": 9.5 + i, "best_price": -110,
        }
        for i, stat in enumerate(["pts", "reb", "ast", "fg3m", "tov"])
    ]

    def _run(self, flag_on: bool):
        if flag_on:
            os.environ["CV_ARCHETYPE_CORR"] = "1"
            try:
                from src.prediction import correlation_recal
                correlation_recal.clear_caches()
            except Exception:
                pass
        else:
            os.environ.pop("CV_ARCHETYPE_CORR", None)
        try:
            eng = ParlayEngine(self.BETS_5LEG, rng_seed=0)
            # Cholesky succeeds (PSD) iff this doesn't raise
            L = eng._cholesky_psd(eng._cov)
            assert L.shape == (5, 5)
            # Verify positive diagonal
            assert all(L[i, i] > 0 for i in range(5))
        finally:
            os.environ.pop("CV_ARCHETYPE_CORR", None)

    def test_psd_flag_off(self):
        self._run(flag_on=False)

    def test_psd_flag_on(self):
        self._run(flag_on=True)

    def test_psd_spot_up_with_fg3m_pts_high_rho(self):
        """SPOT_UP_SHOOTER has fg3m_pts=0.738; matrix must still be PSD."""
        os.environ["CV_ARCHETYPE_CORR"] = "1"
        try:
            from src.prediction import correlation_recal
            correlation_recal.clear_caches()
            eng = ParlayEngine(self.BETS_5LEG, rng_seed=1)
            np.linalg.cholesky(eng._cov)  # raises if not PSD
        except np.linalg.LinAlgError:
            pytest.fail("Covariance not PSD after eigen-clip repair for SPOT_UP_SHOOTER")
        finally:
            os.environ.pop("CV_ARCHETYPE_CORR", None)


# ---------------------------------------------------------------------------
# Bonus: correlation_recal module API contract
# ---------------------------------------------------------------------------

class TestCorrelationRecalAPI:

    def setup_method(self):
        from src.prediction import correlation_recal
        correlation_recal.clear_caches()

    def teardown_method(self):
        os.environ.pop("CV_ARCHETYPE_CORR", None)
        try:
            from src.prediction import correlation_recal
            correlation_recal.clear_caches()
        except Exception:
            pass

    def test_recal_enabled_default_false(self):
        os.environ.pop("CV_ARCHETYPE_CORR", None)
        from src.prediction import correlation_recal
        assert not correlation_recal.recal_enabled()

    def test_recal_enabled_when_set(self):
        os.environ["CV_ARCHETYPE_CORR"] = "1"
        from src.prediction import correlation_recal
        assert correlation_recal.recal_enabled()

    def test_same_player_rho_in_range(self):
        from src.prediction import correlation_recal
        for sa, sb in [("pts", "ast"), ("reb", "blk"), ("ast", "tov"), ("fg3m", "pts")]:
            rho = correlation_recal.same_player_rho(sa, sb)
            if rho is not None:
                assert -0.95 <= rho <= 0.95, f"{sa}-{sb} rho={rho} out of range"

    def test_teammate_rho_in_range(self):
        from src.prediction import correlation_recal
        for sa, sb in [("pts", "pts"), ("pts", "ast"), ("reb", "reb"), ("ast", "fg3m")]:
            rho = correlation_recal.teammate_rho(sa, sb)
            if rho is not None:
                assert -0.95 <= rho <= 0.95

    def test_spot_up_fg3m_pts_archetype_override(self):
        """Known SPOT_UP_SHOOTER player should get the archetype-specific rho."""
        from src.prediction import correlation_recal
        rho = correlation_recal.same_player_rho("fg3m", "pts", SPOT_UP_PID)
        assert rho is not None
        # SPOT_UP refined = 0.738
        assert rho > 0.65, f"SPOT_UP fg3m-pts rho={rho} expected ~0.738"

    def test_unknown_player_falls_back_to_global(self):
        """Unknown player_id should still return a global rho (not None)."""
        from src.prediction import correlation_recal
        rho = correlation_recal.same_player_rho("pts", "reb", player_id=999999999)
        # Global rho exists for pts-reb pair
        assert rho is not None
        # Should be the global average, not the naive 0.40
        assert rho < 0.40

    def test_clamp_at_095(self):
        """Any rho returned must be clamped to [-0.95, 0.95]."""
        from src.prediction import correlation_recal
        rho = correlation_recal.same_player_rho("fg3m", "pts", SPOT_UP_PID)
        if rho is not None:
            assert -0.95 <= rho <= 0.95
