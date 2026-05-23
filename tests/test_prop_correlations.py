"""
tests/test_prop_correlations.py
--------------------------------
Tests for the prop correlation matrix and correlated Kelly portfolio sizing.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CORR_PATH = os.path.join(PROJECT_DIR, "data", "models", "prop_corr_matrix.json")

_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def corr_data():
    """Load saved correlation matrix; skip entire suite if not present."""
    if not os.path.exists(_CORR_PATH):
        pytest.skip(f"prop_corr_matrix.json not found at {_CORR_PATH} — run build script first")
    with open(_CORR_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def mock_bets():
    """Three representative prop bets across different players and stats."""
    from src.prediction.betting_portfolio import Bet
    return [
        Bet(
            bet_id="test-001",
            player_id="2544",
            player_name="LeBron James",
            stat="pts",
            direction="over",
            line=25.5,
            pred=28.3,
            book="DraftKings",
            odds=-110,
            edge_pct=0.11,
            kelly_size=0.0,
            placed_at=time.time(),
        ),
        Bet(
            bet_id="test-002",
            player_id="2544",
            player_name="LeBron James",
            stat="ast",
            direction="over",
            line=7.5,
            pred=8.9,
            book="FanDuel",
            odds=-115,
            edge_pct=0.09,
            kelly_size=0.0,
            placed_at=time.time(),
        ),
        Bet(
            bet_id="test-003",
            player_id="203999",
            player_name="Nikola Jokic",
            stat="reb",
            direction="over",
            line=11.5,
            pred=13.1,
            book="BetMGM",
            odds=-120,
            edge_pct=0.07,
            kelly_size=0.0,
            placed_at=time.time(),
        ),
    ]


# ── Correlation matrix structural tests ───────────────────────────────────────

class TestCorrMatrixStructure:

    def test_schema_keys(self, corr_data):
        """New structured format must have stats, corr, std, n, computed_at."""
        assert "stats" in corr_data, "Missing 'stats' key"
        assert "corr" in corr_data,  "Missing 'corr' key"
        assert "std"  in corr_data,  "Missing 'std' key"
        assert "n"    in corr_data,  "Missing 'n' key"
        assert "computed_at" in corr_data, "Missing 'computed_at' key"

    def test_stats_order(self, corr_data):
        assert corr_data["stats"] == _STATS

    def test_corr_shape_7x7(self, corr_data):
        corr = corr_data["corr"]
        assert len(corr) == 7, f"Expected 7 rows, got {len(corr)}"
        for i, row in enumerate(corr):
            assert len(row) == 7, f"Row {i} has {len(row)} cols, expected 7"

    def test_diagonal_is_one(self, corr_data):
        corr = np.array(corr_data["corr"])
        for i in range(7):
            assert abs(corr[i, i] - 1.0) < 1e-6, f"corr[{i},{i}] = {corr[i,i]:.6f}, expected 1.0"

    def test_symmetric(self, corr_data):
        corr = np.array(corr_data["corr"])
        diff = np.abs(corr - corr.T).max()
        assert diff < 1e-6, f"Matrix not symmetric; max abs diff = {diff}"

    def test_positive_semidefinite(self, corr_data):
        """All eigenvalues must be >= -1e-6 (PSD tolerance for floating-point)."""
        corr = np.array(corr_data["corr"])
        eigenvalues = np.linalg.eigvalsh(corr)
        min_eig = float(eigenvalues.min())
        assert min_eig >= -1e-6, f"Matrix not PSD — min eigenvalue = {min_eig:.4e}"

    def test_values_in_range(self, corr_data):
        corr = np.array(corr_data["corr"])
        assert corr.min() >= -1.0 - 1e-9
        assert corr.max() <=  1.0 + 1e-9

    def test_std_positive(self, corr_data):
        for i, s in enumerate(_STATS):
            assert corr_data["std"][i] > 0, f"std[{s}] = {corr_data['std'][i]} not positive"

    def test_sample_size(self, corr_data):
        assert corr_data["n"] >= 10, f"Only {corr_data['n']} samples — too few"


# ── Kelly portfolio tests ──────────────────────────────────────────────────────

class TestKellyPortfolio:

    def test_returns_correct_length(self, mock_bets):
        from src.prediction.betting_portfolio import kelly_portfolio
        stakes = kelly_portfolio(mock_bets, bankroll=10_000.0)
        assert len(stakes) == len(mock_bets)

    def test_no_nan_or_inf(self, mock_bets):
        from src.prediction.betting_portfolio import kelly_portfolio
        stakes = kelly_portfolio(mock_bets, bankroll=10_000.0)
        for i, s in enumerate(stakes):
            assert not (s != s), f"NaN at index {i}"   # NaN check
            assert abs(s) < 1e9, f"Inf at index {i}"

    def test_individual_cap(self, mock_bets):
        """No single bet should exceed MAX_BET_PCT of bankroll."""
        from src.prediction.betting_portfolio import kelly_portfolio, MAX_BET_PCT
        bankroll = 10_000.0
        stakes = kelly_portfolio(mock_bets, bankroll=bankroll)
        cap = MAX_BET_PCT * bankroll
        for i, s in enumerate(stakes):
            assert s <= cap + 1e-6, f"Stake {s:.2f} > cap {cap:.2f} for bet {i}"

    def test_total_allocation_reasonable(self, mock_bets):
        """Total stakes should be <= 20% of bankroll (portfolio cap)."""
        from src.prediction.betting_portfolio import kelly_portfolio
        bankroll = 10_000.0
        stakes = kelly_portfolio(mock_bets, bankroll=bankroll)
        total = sum(stakes)
        assert total <= bankroll * 0.20 + 1e-2, (
            f"Total stakes {total:.2f} exceed 20% of bankroll {bankroll * 0.20:.2f}"
        )

    def test_non_negative_stakes(self, mock_bets):
        from src.prediction.betting_portfolio import kelly_portfolio
        stakes = kelly_portfolio(mock_bets, bankroll=10_000.0)
        for i, s in enumerate(stakes):
            assert s >= 0.0, f"Negative stake {s} at index {i}"

    def test_drawdown_guard_zeros_all(self, mock_bets):
        """When bankroll is below drawdown threshold, all stakes must be 0."""
        from src.prediction.betting_portfolio import kelly_portfolio
        bankroll_start = 10_000.0
        bankroll_now   = 8_000.0   # 20% drawdown > MAX_DRAWDOWN_PCT (15%)
        stakes = kelly_portfolio(mock_bets, bankroll=bankroll_now,
                                 bankroll_start=bankroll_start)
        assert all(s == 0.0 for s in stakes), "Expected all zeros after drawdown breach"

    def test_empty_bets(self):
        from src.prediction.betting_portfolio import kelly_portfolio
        assert kelly_portfolio([], bankroll=10_000.0) == []


# ── Simulate portfolio tests ───────────────────────────────────────────────────

class TestSimulatePortfolio:

    def test_output_keys(self, mock_bets):
        from src.prediction.betting_portfolio import simulate_portfolio
        result = simulate_portfolio(mock_bets, bankroll=10_000.0, n_sims=1_000)
        expected = {"mean_roi", "median_roi", "var_5pct", "win_pct",
                    "kelly_growth_rate", "n_bets", "n_sims", "total_staked"}
        assert expected == set(result.keys()), f"Keys mismatch: {set(result.keys())}"

    def test_var_5pct_less_than_median(self, mock_bets):
        """5th percentile ROI must be < median ROI by definition."""
        from src.prediction.betting_portfolio import simulate_portfolio
        result = simulate_portfolio(mock_bets, bankroll=10_000.0, n_sims=5_000)
        assert result["var_5pct"] < result["median_roi"], (
            f"VaR-5 {result['var_5pct']} should be < median {result['median_roi']}"
        )

    def test_win_pct_in_range(self, mock_bets):
        from src.prediction.betting_portfolio import simulate_portfolio
        result = simulate_portfolio(mock_bets, bankroll=10_000.0, n_sims=2_000)
        assert 0.0 <= result["win_pct"] <= 1.0

    def test_empty_bets_returns_zeros(self):
        from src.prediction.betting_portfolio import simulate_portfolio
        result = simulate_portfolio([], bankroll=10_000.0)
        assert result["mean_roi"] == 0.0
        assert result["n_bets"] == 0

    def test_n_sims_propagated(self, mock_bets):
        from src.prediction.betting_portfolio import simulate_portfolio
        result = simulate_portfolio(mock_bets, bankroll=10_000.0, n_sims=500)
        assert result["n_sims"] == 500
