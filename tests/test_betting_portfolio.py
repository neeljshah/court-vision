"""
test_betting_portfolio.py — Unit tests for betting_portfolio.py and betting_edge.py.

Covers: kelly_corr (quarter-Kelly, 4% cap, drawdown halt, 20-bet cap, corr matrix),
        detect_arb, backtest_clv, CLV tracker synthetic data, bankroll Monte Carlo.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.prediction.betting_portfolio import (
    ArbOpportunity,
    Bet,
    MAX_BET_PCT,
    MAX_DRAWDOWN_PCT,
    MAX_OPEN_BETS,
    KELLY_FRACTION,
    _american_to_prob,
    _american_to_payout,
    check_drawdown_ok,
    detect_arb,
    kelly_corr,
)


# ── kelly_corr ────────────────────────────────────────────────────────────────

class TestKellyCorr:

    def test_quarter_kelly_applied(self) -> None:
        """Result must be <= full-Kelly * KELLY_FRACTION (quarter-Kelly by default)."""
        edge = 0.06
        odds = -110
        bankroll = 1000.0
        result = kelly_corr(edge, odds, bankroll)
        b = _american_to_payout(odds)
        implied = _american_to_prob(odds)
        win_prob = min(0.95, implied + edge)
        q = 1.0 - win_prob
        full_kelly = (win_prob * b - q) / b
        quarter_kelly_dollars = full_kelly * KELLY_FRACTION * bankroll
        assert result <= quarter_kelly_dollars + 0.01  # float tolerance

    def test_four_pct_cap(self) -> None:
        """No single bet exceeds 4% of bankroll regardless of edge."""
        bankroll = 5000.0
        result = kelly_corr(0.30, +200, bankroll)  # huge edge
        assert result <= bankroll * MAX_BET_PCT + 0.01

    def test_drawdown_halt(self) -> None:
        """Returns 0 when drawdown from bankroll_start exceeds MAX_DRAWDOWN_PCT (15%)."""
        bankroll_start = 1000.0
        bankroll_now = bankroll_start * (1.0 - MAX_DRAWDOWN_PCT - 0.01)  # just over limit
        result = kelly_corr(0.06, -110, bankroll_now, bankroll_start=bankroll_start)
        assert result == 0.0

    def test_no_drawdown_halt_at_safe_level(self) -> None:
        """Returns positive bet when drawdown is well within limit."""
        bankroll_start = 1000.0
        bankroll_now = 920.0  # 8% drawdown — well under 15%
        result = kelly_corr(0.06, -110, bankroll_now, bankroll_start=bankroll_start)
        assert result > 0.0

    def test_negative_edge_returns_zero(self) -> None:
        """Kelly returns 0 for a losing bet (negative edge)."""
        result = kelly_corr(-0.05, -110, 1000.0)
        assert result == 0.0

    def test_correlation_reduction(self) -> None:
        """High correlation penalty reduces bet size."""
        no_corr = kelly_corr(0.06, -110, 1000.0, corr_with_open=0.0, existing_exposure=0.0)
        high_corr = kelly_corr(0.06, -110, 1000.0, corr_with_open=0.9, existing_exposure=500.0)
        assert high_corr <= no_corr

    def test_max_open_bets_constant(self) -> None:
        """MAX_OPEN_BETS is 20 (enforced at portfolio level)."""
        assert MAX_OPEN_BETS == 20


# ── check_drawdown_ok ─────────────────────────────────────────────────────────

class TestDrawdownGuard:

    def test_ok_when_no_loss(self) -> None:
        assert check_drawdown_ok(1000.0, 1000.0) is True

    def test_ok_at_14_pct(self) -> None:
        assert check_drawdown_ok(1000.0, 860.0) is True  # 14% < 15%

    def test_halt_at_15_pct(self) -> None:
        assert check_drawdown_ok(1000.0, 849.0) is False  # 15.1% > 15%

    def test_zero_start_safe(self) -> None:
        assert check_drawdown_ok(0.0, -100.0) is True  # guard: zero start → True


# ── detect_arb ────────────────────────────────────────────────────────────────

class TestDetectArb:

    def test_detects_true_arb(self) -> None:
        """Cross-book arb where over+under implied probs < 1.0."""
        lines = {
            "BookA": {"LeBron_pts": (25.5, +115, -125)},  # over +115
            "BookB": {"LeBron_pts": (25.5, -130, +130)},  # under +130
        }
        arbs = detect_arb(lines)
        assert len(arbs) >= 1
        assert arbs[0].arb_pct > 0

    def test_no_arb_standard_market(self) -> None:
        """Standard -110/-110 market has no arb."""
        lines = {
            "BookA": {"LeBron_pts": (25.5, -110, -110)},
            "BookB": {"LeBron_pts": (25.5, -110, -110)},
        }
        arbs = detect_arb(lines)
        assert len(arbs) == 0

    def test_single_book_no_arb(self) -> None:
        """Can't arb with only one book."""
        lines = {"BookA": {"Curry_pts": (28.5, +110, -120)}}
        arbs = detect_arb(lines)
        assert len(arbs) == 0

    def test_sorted_by_arb_pct_desc(self) -> None:
        """Multiple arbs are sorted by arb_pct descending."""
        lines = {
            "B1": {"A_pts": (20.0, +120, -115), "B_pts": (10.0, +150, -120)},
            "B2": {"A_pts": (20.0, -110, +140), "B_pts": (10.0, -100, +170)},
        }
        arbs = detect_arb(lines)
        if len(arbs) >= 2:
            assert arbs[0].arb_pct >= arbs[1].arb_pct


# ── backtest_clv ──────────────────────────────────────────────────────────────

class TestBacktestClv:

    def test_returns_dict(self) -> None:
        """backtest_clv returns a dict (may have 'error' key if no data)."""
        from src.analytics.betting_edge import backtest_clv
        result = backtest_clv(seasons=["2024-25"])
        assert isinstance(result, dict)

    def test_result_has_expected_keys_or_error(self) -> None:
        """Either full result keys or 'error'/'n_games' sentinel."""
        from src.analytics.betting_edge import backtest_clv
        result = backtest_clv(seasons=["2024-25"])
        full_keys = {"mean_clv", "std_clv", "pct_positive_clv",
                     "pct_correct_winner", "mae_spread", "n_games"}
        has_full = full_keys.issubset(result.keys())
        has_error = "error" in result or result.get("n_games", 0) == 0
        assert has_full or has_error, f"Unexpected result keys: {list(result.keys())}"


# ── CLV tracker with synthetic data ──────────────────────────────────────────

class TestClvTracker:

    def test_clv_tracker_import(self) -> None:
        """scripts/clv_tracker.py is importable and exposes update_clv_log."""
        import importlib
        mod = importlib.import_module("scripts.clv_tracker")
        assert hasattr(mod, "update_clv_log"), "update_clv_log not found in clv_tracker"

    def test_update_clv_log_with_synthetic_data(self, tmp_path: Path) -> None:
        """update_clv_log writes entries to a JSON log and computes realized CLV."""
        import importlib
        mod = importlib.import_module("scripts.clv_tracker")

        log_path = tmp_path / "clv_test.json"
        entries = [
            {"bet_id": "b1", "stat": "pts", "direction": "over",
             "opening_line": 24.5, "closing_line": 25.5, "edge_pct": 0.04},
            {"bet_id": "b2", "stat": "reb", "direction": "under",
             "opening_line": 8.5,  "closing_line": 7.5,  "edge_pct": 0.03},
        ]
        mod.update_clv_log(entries, log_path=str(log_path))
        assert log_path.exists()
        data = json.loads(log_path.read_text())
        assert len(data) == 2
        # Both entries should have computed CLV
        for entry in data:
            assert "clv" in entry
            assert isinstance(entry["clv"], float)

    def test_realized_clv_direction_over(self, tmp_path: Path) -> None:
        """Over bet: positive CLV when closing > opening (line moved in our favour)."""
        import importlib
        mod = importlib.import_module("scripts.clv_tracker")

        log_path = tmp_path / "clv_over.json"
        entries = [{"bet_id": "b_over", "stat": "pts", "direction": "over",
                    "opening_line": 24.5, "closing_line": 26.0, "edge_pct": 0.05}]
        mod.update_clv_log(entries, log_path=str(log_path))
        data = json.loads(log_path.read_text())
        assert data[0]["clv"] > 0, "Over bet should have positive CLV when line moved up"


# ── Bankroll Monte Carlo simulator ───────────────────────────────────────────

class TestBankrollMonteCarlo:

    def test_import(self) -> None:
        """scripts/bankroll_simulator.py is importable."""
        import importlib
        mod = importlib.import_module("scripts.bankroll_simulator")
        assert hasattr(mod, "simulate_bankroll")

    def test_simulate_returns_metrics(self) -> None:
        """simulate_bankroll returns drawdown_pct, ruin_prob, and final_bankroll_median."""
        import importlib
        mod = importlib.import_module("scripts.bankroll_simulator")
        result = mod.simulate_bankroll(
            n_bets=100, edge_mean=0.04, edge_std=0.02,
            kelly_fraction=0.25, bankroll=1000.0, n_simulations=200,
            seed=42,
        )
        assert isinstance(result, dict)
        assert "ruin_prob" in result
        assert "max_drawdown_pct" in result
        assert "final_bankroll_median" in result
        assert 0.0 <= result["ruin_prob"] <= 1.0

    def test_ruin_prob_increases_with_negative_edge(self) -> None:
        """Negative-edge sequences should have higher ruin probability than positive-edge."""
        import importlib
        mod = importlib.import_module("scripts.bankroll_simulator")

        pos = mod.simulate_bankroll(100, edge_mean=0.05, edge_std=0.01,
                                    kelly_fraction=0.25, bankroll=1000.0,
                                    n_simulations=500, seed=0)
        neg = mod.simulate_bankroll(100, edge_mean=-0.03, edge_std=0.01,
                                    kelly_fraction=0.25, bankroll=1000.0,
                                    n_simulations=500, seed=0)
        assert neg["ruin_prob"] >= pos["ruin_prob"]
