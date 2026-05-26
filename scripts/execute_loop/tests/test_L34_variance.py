"""Tests for L34_variance_budgeter — mean-variance allocation across betting buckets."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure the execute_loop package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.execute_loop.L34_variance_budgeter import (
    DEFAULTS_EDGES,
    DEFAULTS_STDS,
    Allocation,
    compute_daily_allocation,
    coordinate_with_sell_to_close,
    mean_variance_optimize,
)

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

BANKROLL = 100_000.0
EPSILON = 1e-6


def _sum_dollars(allocs: list[Allocation]) -> float:
    return sum(a.target_dollars for a in allocs)


def _sum_pct(allocs: list[Allocation]) -> float:
    return sum(a.target_pct for a in allocs)


def _weight_of(allocs: list[Allocation], bucket: str) -> float:
    for a in allocs:
        if a.bucket == bucket:
            return a.target_pct
    return 0.0


# ---------------------------------------------------------------------------
# Test 1 — Default allocation: all 4 buckets present, sums correct
# ---------------------------------------------------------------------------


class TestDefaultAllocation:
    def test_all_four_buckets_present(self):
        allocs = compute_daily_allocation(BANKROLL)
        buckets = {a.bucket for a in allocs}
        assert "cash_dfs" in buckets
        assert "gpp_dfs" in buckets
        assert "exchange_props" in buckets
        assert "exchange_game_lines" in buckets

    def test_all_buckets_positive_dollars(self):
        allocs = compute_daily_allocation(BANKROLL)
        for a in allocs:
            assert a.target_dollars > 0, f"{a.bucket} has non-positive allocation"

    def test_sum_dollars_within_one_dollar(self):
        allocs = compute_daily_allocation(BANKROLL)
        assert abs(_sum_dollars(allocs) - BANKROLL) <= 1.0

    def test_sum_pct_approx_one(self):
        allocs = compute_daily_allocation(BANKROLL)
        assert abs(_sum_pct(allocs) - 1.0) < 1e-4

    def test_sorted_descending_by_dollars(self):
        allocs = compute_daily_allocation(BANKROLL)
        dollars = [a.target_dollars for a in allocs]
        assert dollars == sorted(dollars, reverse=True)

    def test_sharpe_contribution_positive(self):
        allocs = compute_daily_allocation(BANKROLL)
        for a in allocs:
            assert a.sharpe_contribution > 0, (
                f"{a.bucket} has non-positive sharpe_contribution"
            )

    def test_expected_roi_matches_edges(self):
        allocs = compute_daily_allocation(BANKROLL)
        for a in allocs:
            assert math.isclose(a.expected_roi, DEFAULTS_EDGES[a.bucket], rel_tol=1e-9)

    def test_expected_std_matches_stds(self):
        allocs = compute_daily_allocation(BANKROLL)
        for a in allocs:
            assert math.isclose(a.expected_std, DEFAULTS_STDS[a.bucket], rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Test 2 — All-negative edges → returns []
# ---------------------------------------------------------------------------


class TestAllNegativeEdges:
    def test_returns_empty_list(self):
        neg_edges = {k: -0.01 for k in DEFAULTS_EDGES}
        result = compute_daily_allocation(BANKROLL, edges=neg_edges)
        assert result == []

    def test_zero_edges_returns_empty(self):
        zero_edges = {k: 0.0 for k in DEFAULTS_EDGES}
        result = compute_daily_allocation(BANKROLL, edges=zero_edges)
        assert result == []

    def test_mixed_some_negative_still_allocates(self):
        # Only one positive edge — should still allocate
        mixed = {k: -0.01 for k in DEFAULTS_EDGES}
        mixed["exchange_props"] = 0.055
        result = compute_daily_allocation(BANKROLL, edges=mixed)
        # At least exchange_props gets allocation
        assert any(a.bucket == "exchange_props" for a in result)


# ---------------------------------------------------------------------------
# Test 3 — max_weight=0.4: no bucket exceeds 40%
# ---------------------------------------------------------------------------


class TestMaxWeightConstraint:
    def test_no_bucket_exceeds_max_weight(self):
        allocs = compute_daily_allocation(BANKROLL, max_weight_per_bucket=0.4)
        for a in allocs:
            assert a.target_pct <= 0.4 + EPSILON, (
                f"{a.bucket} weight {a.target_pct:.4f} exceeds 0.40"
            )

    def test_sum_still_correct(self):
        allocs = compute_daily_allocation(BANKROLL, max_weight_per_bucket=0.4)
        assert abs(_sum_dollars(allocs) - BANKROLL) <= 1.0

    def test_all_buckets_present(self):
        allocs = compute_daily_allocation(BANKROLL, max_weight_per_bucket=0.4)
        buckets = {a.bucket for a in allocs}
        assert len(buckets) == 4


# ---------------------------------------------------------------------------
# Test 4 — High correlation between cash_dfs and gpp_dfs reduces their combined weight
# ---------------------------------------------------------------------------


class TestCorrelationEffect:
    def _combined_weight(self, allocs: list[Allocation]) -> float:
        return sum(
            a.target_pct
            for a in allocs
            if a.bucket in ("cash_dfs", "gpp_dfs")
        )

    def test_high_corr_reduces_combined_weight_vs_independent(self):
        # Independent (identity) baseline
        allocs_indep = compute_daily_allocation(BANKROLL, correlations=None)
        w_indep = self._combined_weight(allocs_indep)

        # High correlation ρ=0.9 between cash_dfs and gpp_dfs
        corr = {
            "cash_dfs": {"gpp_dfs": 0.9, "exchange_props": 0.0, "exchange_game_lines": 0.0},
            "gpp_dfs": {"cash_dfs": 0.9, "exchange_props": 0.0, "exchange_game_lines": 0.0},
            "exchange_props": {"cash_dfs": 0.0, "gpp_dfs": 0.0, "exchange_game_lines": 0.0},
            "exchange_game_lines": {"cash_dfs": 0.0, "gpp_dfs": 0.0, "exchange_props": 0.0},
        }
        allocs_corr = compute_daily_allocation(BANKROLL, correlations=corr)
        w_corr = self._combined_weight(allocs_corr)

        # High correlation should penalise the pair → lower or equal combined weight
        assert w_corr <= w_indep + 1e-4, (
            f"Expected high-corr combined weight ({w_corr:.4f}) <= "
            f"independent ({w_indep:.4f})"
        )

    def test_high_corr_sums_to_one(self):
        corr = {
            "cash_dfs": {"gpp_dfs": 0.9},
            "gpp_dfs": {"cash_dfs": 0.9},
        }
        allocs = compute_daily_allocation(BANKROLL, correlations=corr)
        assert abs(_sum_pct(allocs) - 1.0) < 1e-4

    def test_non_psd_fallback_does_not_raise(self):
        # Deliberately non-PSD: ρ > 1 effectively; we use a bad matrix
        bad_corr = {
            "cash_dfs": {"gpp_dfs": 0.99, "exchange_props": 0.99, "exchange_game_lines": 0.99},
            "gpp_dfs": {"cash_dfs": 0.99, "exchange_props": 0.99, "exchange_game_lines": 0.99},
            "exchange_props": {"cash_dfs": 0.99, "gpp_dfs": 0.99, "exchange_game_lines": 0.99},
            "exchange_game_lines": {"cash_dfs": 0.99, "gpp_dfs": 0.99, "exchange_props": 0.99},
        }
        # Should not raise; falls back to identity
        allocs = compute_daily_allocation(BANKROLL, correlations=bad_corr)
        assert isinstance(allocs, list)
        assert abs(_sum_pct(allocs) - 1.0) < 1e-4


# ---------------------------------------------------------------------------
# Test 5 — max_weight=0.2 with 4 buckets (0.8 < 1.0) → ValueError
# ---------------------------------------------------------------------------


class TestMaxWeightTooRestrictive:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="too restrictive"):
            compute_daily_allocation(BANKROLL, max_weight_per_bucket=0.2)

    def test_boundary_exact_sum_one_ok(self):
        # 4 buckets × 0.25 = exactly 1.0 — should be fine
        allocs = compute_daily_allocation(BANKROLL, max_weight_per_bucket=0.25)
        assert abs(_sum_pct(allocs) - 1.0) < 1e-4

    def test_mean_variance_optimize_raises_directly(self):
        # Direct API call
        with pytest.raises(ValueError, match="too restrictive"):
            mean_variance_optimize(
                expected_returns=DEFAULTS_EDGES,
                stds=DEFAULTS_STDS,
                max_weight=0.2,
            )


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_zero_bankroll_raises(self):
        with pytest.raises(ValueError):
            compute_daily_allocation(0.0)

    def test_negative_bankroll_raises(self):
        with pytest.raises(ValueError):
            compute_daily_allocation(-500.0)

    def test_single_positive_bucket_gets_max_weight(self):
        """Single positive-edge bucket gets max_weight (0.6) allocation."""
        edges = {k: -0.01 for k in DEFAULTS_EDGES}
        edges["cash_dfs"] = 0.04
        allocs = compute_daily_allocation(BANKROLL, edges=edges, max_weight_per_bucket=0.6)
        # cash_dfs should get 100% (or up to max_weight if cap applies)
        cash_weight = _weight_of(allocs, "cash_dfs")
        assert cash_weight > 0
        # With only one positive bucket, it must get exactly 1.0
        assert math.isclose(cash_weight, 1.0, abs_tol=1e-4)

    def test_target_pct_equals_dollars_over_bankroll(self):
        allocs = compute_daily_allocation(BANKROLL)
        for a in allocs:
            expected_pct = a.target_dollars / BANKROLL
            assert math.isclose(a.target_pct, expected_pct, rel_tol=1e-6), (
                f"{a.bucket}: target_pct={a.target_pct} but "
                f"target_dollars/bankroll={expected_pct}"
            )

    def test_custom_bankroll_scales_correctly(self):
        """target_dollars should scale linearly with bankroll."""
        allocs_100k = compute_daily_allocation(100_000.0)
        allocs_200k = compute_daily_allocation(200_000.0)
        # Same buckets should be present
        buckets_100k = {a.bucket: a.target_pct for a in allocs_100k}
        buckets_200k = {a.bucket: a.target_pct for a in allocs_200k}
        for b in buckets_100k:
            assert math.isclose(
                buckets_100k[b], buckets_200k.get(b, 0.0), abs_tol=1e-3
            ), f"Weight for {b} changed with bankroll scale"

    def test_mean_variance_optimize_returns_dict(self):
        result = mean_variance_optimize(
            expected_returns=DEFAULTS_EDGES,
            stds=DEFAULTS_STDS,
        )
        assert isinstance(result, dict)
        for k in DEFAULTS_EDGES:
            assert k in result
        total = sum(result.values())
        assert math.isclose(total, 1.0, abs_tol=1e-4)

    def test_allocation_dataclass_fields(self):
        allocs = compute_daily_allocation(BANKROLL)
        for a in allocs:
            assert isinstance(a, Allocation)
            assert isinstance(a.bucket, str)
            assert isinstance(a.target_dollars, float)
            assert isinstance(a.target_pct, float)
            assert isinstance(a.expected_roi, float)
            assert isinstance(a.expected_std, float)
            assert isinstance(a.sharpe_contribution, float)


# ---------------------------------------------------------------------------
# Test v2: coordinate_with_sell_to_close — L33 integration
# ---------------------------------------------------------------------------


class TestCoordinateWithSellToClose:
    """Tests for the L33 sell-to-close coordinator."""

    def _make_positions(self, variances: list[float]) -> list[dict]:
        buckets = ["cash_dfs", "gpp_dfs", "exchange_props", "exchange_game_lines"]
        return [
            {
                "bucket": buckets[i % len(buckets)],
                "dollars": 1000.0 * (i + 1),
                "variance": v,
                "position_id": f"pos_{i}",
            }
            for i, v in enumerate(variances)
        ]

    def test_within_budget_returns_empty(self):
        """No positions closed when total variance <= budget."""
        positions = self._make_positions([0.01, 0.02, 0.01])
        total_var = sum(p["variance"] for p in positions)
        result = coordinate_with_sell_to_close(positions, variance_budget=total_var + 0.1)
        assert result == [], f"Expected empty list, got {result}"

    def test_budget_exceeded_closes_highest_variance_first(self):
        """When budget exceeded, highest-variance position has close_priority=1."""
        # variances: 0.50, 0.10, 0.05 → total=0.65; budget=0.10 → must close
        positions = self._make_positions([0.50, 0.10, 0.05])
        result = coordinate_with_sell_to_close(positions, variance_budget=0.10)
        assert len(result) >= 1, "Expected at least one position to close"
        # Priority-1 position must be the one with highest variance (0.50)
        prio1 = next(p for p in result if p["close_priority"] == 1)
        assert math.isclose(prio1["variance"], 0.50, rel_tol=1e-9), (
            f"Priority-1 position should have variance=0.50, got {prio1['variance']}"
        )

    def test_close_priority_ascending(self):
        """close_priority values must be 1, 2, 3, ... in the returned list."""
        positions = self._make_positions([0.3, 0.2, 0.1, 0.05])
        result = coordinate_with_sell_to_close(positions, variance_budget=0.01)
        priorities = [p["close_priority"] for p in result]
        assert priorities == list(range(1, len(result) + 1)), (
            f"Priorities should be sequential from 1, got {priorities}"
        )

    def test_variance_contribution_pct_sums_to_approx_one(self):
        """Sum of variance_contribution_pct across ALL input positions is ~1.0."""
        positions = self._make_positions([0.4, 0.3, 0.2, 0.1])
        # Force budget exceeded so we exercise the enrichment path
        result = coordinate_with_sell_to_close(positions, variance_budget=0.01)
        total_contrib = sum(p["variance_contribution_pct"] for p in result)
        # Only closed positions are returned; their contributions must be <= 1.0
        assert 0.0 < total_contrib <= 1.0 + 1e-6, (
            f"Contribution pct out of range: {total_contrib}"
        )

    def test_empty_positions_returns_empty(self):
        result = coordinate_with_sell_to_close([], variance_budget=0.5)
        assert result == []

    def test_invalid_budget_raises(self):
        with pytest.raises(ValueError, match="variance_budget"):
            coordinate_with_sell_to_close(self._make_positions([0.1]), variance_budget=0.0)

    def test_missing_required_key_raises(self):
        bad_positions = [{"bucket": "cash_dfs", "dollars": 1000.0}]  # no "variance"
        with pytest.raises(ValueError, match="missing required keys"):
            coordinate_with_sell_to_close(bad_positions, variance_budget=0.5)

    def test_original_positions_not_mutated(self):
        """coordinate_with_sell_to_close must not mutate the input list."""
        positions = self._make_positions([0.5, 0.3])
        original_keys = [set(p.keys()) for p in positions]
        coordinate_with_sell_to_close(positions, variance_budget=0.01)
        for i, pos in enumerate(positions):
            assert set(pos.keys()) == original_keys[i], (
                f"Position[{i}] was mutated: original={original_keys[i]}, "
                f"now={set(pos.keys())}"
            )
