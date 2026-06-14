"""tests/tennis/test_match_engine.py — Fast synthetic tests for the tennis match engine.

NO real corpus loaded; all tests use tiny synthetic data or analytic checks.
Run: PYTHONPATH=. python -m pytest tests/tennis/test_match_engine.py -q
"""
from __future__ import annotations

import math
import pytest
import numpy as np
import pandas as pd

from domains.tennis.match_engine import (
    game_win_prob,
    serve_probs_from_winprob,
    markets_from_engine,
    build_engine_forecast,
    _sim_matches,
)


# ---------------------------------------------------------------------------
# 1. game_win_prob — analytic
# ---------------------------------------------------------------------------

class TestGameWinProb:
    def test_half_point_gives_half_hold(self):
        """At p_serve=0.5, deuce game is fair: server holds with prob 0.5."""
        assert abs(game_win_prob(0.5) - 0.5) < 1e-6

    def test_monotone_increasing(self):
        """Higher serve-win prob -> higher hold probability."""
        probs = [0.3, 0.45, 0.5, 0.6, 0.7, 0.85]
        holds = [game_win_prob(p) for p in probs]
        for i in range(len(holds) - 1):
            assert holds[i] < holds[i + 1], (
                f"monotone violated at p={probs[i]:.2f}: hold={holds[i]:.4f} vs "
                f"p={probs[i+1]:.2f}: hold={holds[i+1]:.4f}"
            )

    def test_high_serve_gives_high_hold(self):
        """Dominant server (p=0.8) holds nearly always."""
        assert game_win_prob(0.8) > 0.9

    def test_low_serve_gives_low_hold(self):
        """Weak server (p=0.3) rarely holds."""
        assert game_win_prob(0.3) < 0.2

    def test_boundary_zero(self):
        """p=0: server never wins a point => never holds."""
        assert game_win_prob(0.0) == pytest.approx(0.0, abs=1e-9)

    def test_boundary_one(self):
        """p=1: server wins every point => always holds."""
        assert game_win_prob(1.0) == pytest.approx(1.0, abs=1e-9)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            game_win_prob(1.5)
        with pytest.raises(ValueError):
            game_win_prob(-0.1)


# ---------------------------------------------------------------------------
# 2. serve_probs_from_winprob — round-trip calibration
# ---------------------------------------------------------------------------

class TestServeProbs:
    def test_symmetric_gives_half_match_win(self):
        """Equal serve probs -> ~0.5 match-win (bo3 and bo5)."""
        for bo in (3, 5):
            ph1, ph2 = serve_probs_from_winprob(0.5, bo, n_sims=2000, seed=0)
            assert abs(ph1 - ph2) < 0.01, f"bo{bo}: ph1={ph1:.4f} ph2={ph2:.4f}"

    def test_roundtrip_bo3(self):
        """serve_probs_from_winprob then markets_from_engine recovers target (bo3)."""
        target = 0.72
        ph1, ph2 = serve_probs_from_winprob(target, 3, n_sims=2000, seed=1)
        mkt = markets_from_engine(ph1, ph2, 3, seed=1, n_sims=3000)
        assert abs(mkt["match_win_p1"] - target) < 0.04, (
            f"round-trip error: target={target}, got={mkt['match_win_p1']:.4f}"
        )

    def test_roundtrip_bo5(self):
        """serve_probs_from_winprob then markets_from_engine recovers target (bo5)."""
        target = 0.65
        ph1, ph2 = serve_probs_from_winprob(target, 5, n_sims=2000, seed=2)
        mkt = markets_from_engine(ph1, ph2, 5, seed=2, n_sims=3000)
        assert abs(mkt["match_win_p1"] - target) < 0.05, (
            f"round-trip error: target={target}, got={mkt['match_win_p1']:.4f}"
        )

    def test_higher_p1_serve_wins_more(self):
        """Stronger p1 serve edge -> p1 match-win > 0.5."""
        ph1, ph2 = serve_probs_from_winprob(0.70, 3, n_sims=2000, seed=3)
        mkt = markets_from_engine(ph1, ph2, 3, seed=3, n_sims=2000)
        assert mkt["match_win_p1"] > 0.55


# ---------------------------------------------------------------------------
# 3. markets_from_engine — coherence checks
# ---------------------------------------------------------------------------

class TestMarketsCoherence:
    @pytest.fixture(scope="class")
    def surface_bo3(self):
        ph1, ph2 = serve_probs_from_winprob(0.65, 3, n_sims=2000, seed=10)
        return markets_from_engine(ph1, ph2, 3, seed=10, n_sims=3000)

    @pytest.fixture(scope="class")
    def surface_bo5(self):
        ph1, ph2 = serve_probs_from_winprob(0.60, 5, n_sims=2000, seed=11)
        return markets_from_engine(ph1, ph2, 5, seed=11, n_sims=3000)

    def test_match_win_sums_to_one_bo3(self, surface_bo3):
        total = surface_bo3["match_win_p1"] + surface_bo3["match_win_p2"]
        assert total == pytest.approx(1.0, abs=1e-6), f"match_win sum={total:.8f}"

    def test_match_win_sums_to_one_bo5(self, surface_bo5):
        total = surface_bo5["match_win_p1"] + surface_bo5["match_win_p2"]
        assert total == pytest.approx(1.0, abs=1e-6), f"match_win sum={total:.8f}"

    def test_ou_pairs_sum_to_one_bo3(self, surface_bo3):
        """Each over/under pair sums to 1.0."""
        keys = [k for k in surface_bo3 if k.startswith("over_")]
        assert len(keys) > 0, "No O/U markets generated"
        for k in keys:
            line = k[len("over_"):]
            p_over = surface_bo3[k]
            p_under = surface_bo3[f"under_{line}"]
            total = p_over + p_under
            assert total == pytest.approx(1.0, abs=1e-6), f"{k}: {p_over}+{p_under}={total}"

    def test_set_scores_sum_to_one_bo3(self, surface_bo3):
        """All set-score probabilities sum to ~1.0."""
        set_keys = [k for k in surface_bo3 if k.startswith("sets_")]
        assert len(set_keys) > 0, "No set-score markets generated"
        total = sum(surface_bo3[k] for k in set_keys)
        assert total == pytest.approx(1.0, abs=0.02), f"set scores sum={total:.6f}"

    def test_straight_sets_le_match_win(self, surface_bo3):
        """Straight-sets prob <= match-win prob for that player."""
        assert surface_bo3["straight_sets_p1"] <= surface_bo3["match_win_p1"] + 1e-6
        assert surface_bo3["straight_sets_p2"] <= surface_bo3["match_win_p2"] + 1e-6

    def test_symmetric_serve_approx_half(self):
        """Equal serve probs -> match_win ~0.5 for both bo3 and bo5."""
        for bo in (3, 5):
            ph1, ph2 = serve_probs_from_winprob(0.5, bo, n_sims=1500, seed=20 + bo)
            mkt = markets_from_engine(ph1, ph2, bo, seed=20 + bo, n_sims=2000)
            assert abs(mkt["match_win_p1"] - 0.5) < 0.05, (
                f"bo{bo}: symmetric match_win_p1={mkt['match_win_p1']:.4f}"
            )

    def test_total_games_positive(self, surface_bo3):
        """Total games mean and median are positive integers."""
        assert surface_bo3["total_games_mean"] > 0
        assert surface_bo3["total_games_q50"] > 0

    def test_bo5_more_games_than_bo3(self):
        """Best-of-5 matches have more total games on average than best-of-3."""
        ph1, ph2 = 0.63, 0.61
        mkt3 = markets_from_engine(ph1, ph2, 3, seed=30, n_sims=2000)
        mkt5 = markets_from_engine(ph1, ph2, 5, seed=30, n_sims=2000)
        assert mkt5["total_games_mean"] > mkt3["total_games_mean"], (
            f"bo5 mean={mkt5['total_games_mean']:.1f}, bo3 mean={mkt3['total_games_mean']:.1f}"
        )


# ---------------------------------------------------------------------------
# 4. build_engine_forecast — mock tiny corpus (no real file I/O in unit test)
# ---------------------------------------------------------------------------

class TestBuildEngineForecast:
    """Mock a tiny 30-match corpus and verify the returned dict shape."""

    @pytest.fixture(scope="class")
    def tiny_result(self):
        """Build a tiny synthetic corpus and run build_engine_forecast on it."""
        rng = np.random.default_rng(99)
        n = 30
        dates = pd.date_range("2020-01-01", periods=n, freq="7D")
        p1_ids = rng.integers(1000, 1010, size=n)
        p2_ids = rng.integers(2000, 2010, size=n)
        winners = rng.integers(1, 3, size=n)
        surfaces = rng.choice(["Hard", "Clay", "Grass"], size=n)
        best_ofs = rng.choice([3, 5], size=n, p=[0.8, 0.2])
        scores = ["6-3 6-4"] * n

        matches_df = pd.DataFrame({
            "event_id": [f"evt_{i}" for i in range(n)],
            "date": dates,
            "p1_id": p1_ids,
            "p2_id": p2_ids,
            "winner": winners,
            "surface": surfaces,
            "best_of": best_ofs,
            "score": scores,
            "tour": ["atp"] * n,
            "tourney_id": ["t1"] * n,
            "tourney_name": ["Test"] * n,
            "tourney_level": ["G"] * n,
            "round": ["R32"] * n,
            "match_num": list(range(n)),
            "p1_name": ["Alice"] * n,
            "p2_name": ["Bob"] * n,
            "p1_rank": [50] * n,
            "p2_rank": [60] * n,
            "retirement": [0] * n,
            "minutes": [90] * n,
        })

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp_path = tmp.name
        matches_df.to_parquet(tmp_path, index=False)
        result = build_engine_forecast(matches_path=tmp_path, n_sims=500, seed=42)
        os.unlink(tmp_path)
        return result

    def test_returns_dict_with_required_keys(self, tiny_result):
        required = {"n", "baseline", "engine", "dBrier", "dECE", "note", "sample_surface"}
        assert required.issubset(set(tiny_result.keys()))

    def test_baseline_engine_have_metrics(self, tiny_result):
        for key in ("baseline", "engine"):
            assert "brier" in tiny_result[key]
            assert "ece" in tiny_result[key]
            assert "log_loss" in tiny_result[key]

    def test_n_positive(self, tiny_result):
        assert tiny_result["n"] > 0

    def test_sample_surface_has_match_win(self, tiny_result):
        ss = tiny_result["sample_surface"]
        assert ss is not None
        assert "match_win_p1" in ss
        assert "match_win_p2" in ss
        assert ss["match_win_p1"] + ss["match_win_p2"] == pytest.approx(1.0, abs=1e-6)

    def test_note_contains_honest(self, tiny_result):
        assert "HONEST" in tiny_result["note"]
        assert "NO edge" in tiny_result["note"]
