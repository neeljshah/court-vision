"""tests/test_sgp_joint_backtest.py

Unit tests for reusable functions in scripts/sgp_joint_hitrate_backtest.py
and scripts/sgp_edge_finder.py.

Tests:
  (a) bvn_joint_prob_sheppard: Sheppard formula at equal marginals.
  (b) bvn_joint_over_prob: correctness at rho=0 (independence) and rho extremes.
  (c) bvn_joint_over_prob: asymmetric marginals correctness.
  (d) american_to_decimal / american_to_devig_prob: odds conversion.
  (e) devig_two_way: vig removal.
  (f) bvn_joint_over_prob: ordering invariance (pa, pb, rho).
  (g) recal rho table building: refined cells are loaded.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ---------------------------------------------------------------------------
# Part (a) + (b): Sheppard formula and BVN correctness
# ---------------------------------------------------------------------------

class TestBVNJointProb:

    def test_sheppard_independence_zero_rho(self):
        """At rho=0 and equal marginals 0.5, P(both over) = 0.25."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_prob_sheppard
        assert bvn_joint_prob_sheppard(0.0) == pytest.approx(0.25, abs=1e-6)

    def test_sheppard_perfect_positive_correlation(self):
        """At rho=1, P(both over | equal marginals) = P(over) = 0.5."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_prob_sheppard
        assert bvn_joint_prob_sheppard(1.0) == pytest.approx(0.5, abs=1e-6)

    def test_sheppard_perfect_negative_correlation(self):
        """At rho=-1, P(both over | equal marginals) = 0."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_prob_sheppard
        assert bvn_joint_prob_sheppard(-1.0) == pytest.approx(0.0, abs=1e-6)

    def test_sheppard_midpoint_rho(self):
        """Sheppard formula: 0.25 + arcsin(rho) / (2*pi)."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_prob_sheppard
        rho = 0.5
        expected = 0.25 + np.arcsin(rho) / (2.0 * np.pi)
        assert bvn_joint_prob_sheppard(rho) == pytest.approx(expected, abs=1e-9)

    def test_bvn_independence_equal_marginals(self):
        """At rho=0, bvn_joint_over_prob(0.5, 0.5, 0) = 0.25 = 0.5*0.5."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_over_prob
        p = bvn_joint_over_prob(0.5, 0.5, 0.0)
        assert p == pytest.approx(0.25, abs=1e-4)

    def test_bvn_independence_unequal_marginals(self):
        """At rho=0, P(both) = pa * pb regardless of marginals."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_over_prob
        pa, pb = 0.6, 0.4
        p = bvn_joint_over_prob(pa, pb, 0.0)
        assert p == pytest.approx(pa * pb, abs=1e-3)

    def test_bvn_positive_rho_exceeds_independence(self):
        """Positive rho -> P(both over) > pa * pb."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_over_prob
        p = bvn_joint_over_prob(0.5, 0.5, 0.7)
        assert p > 0.25
        assert p < 0.5  # can't exceed min(pa, pb)

    def test_bvn_negative_rho_below_independence(self):
        """Negative rho -> P(both over) < pa * pb."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_over_prob
        p = bvn_joint_over_prob(0.5, 0.5, -0.5)
        assert p < 0.25

    def test_bvn_ordering_invariance(self):
        """P(A>a, B>b) = P(B>b, A>a) — swap (pa, pb) gives same result."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_over_prob
        p1 = bvn_joint_over_prob(0.4, 0.6, 0.3)
        p2 = bvn_joint_over_prob(0.6, 0.4, 0.3)
        assert p1 == pytest.approx(p2, abs=1e-4)

    def test_bvn_at_spot_up_rho(self):
        """At rho=0.738 (SPOT_UP fg3m_pts recal), P(both) significantly > independence."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_over_prob
        pa, pb = 0.45, 0.50   # typical marginals for spot-up players
        p_indep = pa * pb
        p_recal = bvn_joint_over_prob(pa, pb, 0.738)
        # With rho=0.738, P(both) should be substantially higher
        assert p_recal > p_indep * 1.5, f"Expected recal>>indep: {p_recal} vs {p_indep}"

    def test_bvn_result_in_bounds(self):
        """BVN prob must be in [0, 1]."""
        from scripts.sgp_joint_hitrate_backtest import bvn_joint_over_prob
        for pa in [0.1, 0.3, 0.5, 0.7, 0.9]:
            for pb in [0.1, 0.3, 0.5, 0.7, 0.9]:
                for rho in [-0.8, -0.3, 0.0, 0.3, 0.7, 0.9]:
                    p = bvn_joint_over_prob(pa, pb, rho)
                    assert 0.0 <= p <= 1.0, (
                        f"P({pa},{pb},{rho}) = {p} out of [0,1]"
                    )


# ---------------------------------------------------------------------------
# Part (d) + (e): Odds conversion and devig
# ---------------------------------------------------------------------------

class TestOddsConversion:

    def test_american_to_decimal_positive(self):
        """American +200 -> decimal 3.0."""
        from scripts.sgp_edge_finder import american_to_decimal
        assert american_to_decimal(200) == pytest.approx(3.0, abs=1e-9)

    def test_american_to_decimal_negative(self):
        """American -110 -> decimal 1.909..."""
        from scripts.sgp_edge_finder import american_to_decimal
        assert american_to_decimal(-110) == pytest.approx(1.0 + 100 / 110, abs=1e-6)

    def test_american_to_decimal_even_money(self):
        """American +100 -> decimal 2.0."""
        from scripts.sgp_edge_finder import american_to_decimal
        assert american_to_decimal(100) == pytest.approx(2.0, abs=1e-9)

    def test_american_invalid_odds_returns_none(self):
        """Odds |x| < 100 are invalid, return None."""
        from scripts.sgp_edge_finder import american_to_decimal
        assert american_to_decimal(50) is None
        assert american_to_decimal(-50) is None
        assert american_to_decimal(0) is None

    def test_devig_two_way_balanced(self):
        """Perfectly balanced +100/-100 market devigged to 50/50."""
        from scripts.sgp_edge_finder import devig_two_way
        result = devig_two_way(100, -100)
        assert result is not None
        p_over, p_under = result
        assert p_over == pytest.approx(0.5, abs=1e-6)
        assert p_under == pytest.approx(0.5, abs=1e-6)
        assert p_over + p_under == pytest.approx(1.0, abs=1e-9)

    def test_devig_two_way_viggy(self):
        """Standard -110/-110 vig: devigged to 50/50."""
        from scripts.sgp_edge_finder import devig_two_way
        result = devig_two_way(-110, -110)
        assert result is not None
        p_over, p_under = result
        assert p_over == pytest.approx(0.5, abs=1e-4)
        assert p_under == pytest.approx(0.5, abs=1e-4)
        assert p_over + p_under == pytest.approx(1.0, abs=1e-6)

    def test_devig_two_way_asymmetric(self):
        """Asymmetric market: devigged probs sum to 1."""
        from scripts.sgp_edge_finder import devig_two_way
        result = devig_two_way(-150, +130)
        assert result is not None
        p_over, p_under = result
        assert p_over + p_under == pytest.approx(1.0, abs=1e-6)
        # Favorite should have higher devig prob
        assert p_over > p_under

    def test_devig_two_way_invalid_returns_none(self):
        """One side has invalid odds (|x| < 100) -> returns None."""
        from scripts.sgp_edge_finder import devig_two_way
        assert devig_two_way(50, -110) is None
        assert devig_two_way(-110, 50) is None


# ---------------------------------------------------------------------------
# Part (f): recal rho table building
# ---------------------------------------------------------------------------

class TestRecalRhoTableBuilding:

    def test_sameplayer_rho_table_has_spot_up_fg3m_pts(self):
        """SPOT_UP_SHOOTER fg3m+pts should be in the refined table."""
        from scripts.sgp_edge_finder import (load_corr_tables, build_sameplayer_rho_table)
        sp_corr, _ = load_corr_tables()
        table = build_sameplayer_rho_table(sp_corr)
        key = ('SPOT_UP_SHOOTER', tuple(sorted(['fg3m', 'pts'])))
        assert key in table, f"Expected SPOT_UP fg3m+pts in table, keys: {list(table.keys())[:5]}"
        recal_rho, naive_rho = table[key]
        assert recal_rho > 0.65, f"SPOT_UP fg3m+pts recal_rho={recal_rho} expected ~0.738"
        assert naive_rho == pytest.approx(0.55, abs=0.01)

    def test_sameplayer_rho_table_has_high_ast_ast_tov(self):
        """HIGH_AST_PLAYMAKER ast+tov should be refined (large delta)."""
        from scripts.sgp_edge_finder import (load_corr_tables, build_sameplayer_rho_table)
        sp_corr, _ = load_corr_tables()
        table = build_sameplayer_rho_table(sp_corr)
        key = ('HIGH_AST_PLAYMAKER', tuple(sorted(['ast', 'tov'])))
        assert key in table
        recal_rho, naive_rho = table[key]
        assert recal_rho < 0.20, f"HIGH_AST ast+tov recal_rho={recal_rho} expected ~0.10"
        assert naive_rho == pytest.approx(0.40, abs=0.01)

    def test_teammate_rho_table_has_creator_catch_shoot(self):
        """primary_creator AST + catch_shoot FG3M should be in surviving cells."""
        from scripts.sgp_edge_finder import (load_corr_tables, build_teammate_rho_table)
        _, tm_corr = load_corr_tables()
        table = build_teammate_rho_table(tm_corr)
        key = ('primary_creator', 'catch_shoot', tuple(sorted(['ast', 'fg3m'])))
        assert key in table, f"Expected creator+catch_shoot in table"
        recal_rho, naive_rho = table[key]
        assert recal_rho > 0.05, f"recal_rho={recal_rho} expected ~0.113"
        assert naive_rho == pytest.approx(0.0, abs=0.01)

    def test_teammate_rho_table_has_pts_pts_near_zero(self):
        """primary+secondary creator PTS+PTS: recal ~0, not -0.15."""
        from scripts.sgp_edge_finder import (load_corr_tables, build_teammate_rho_table)
        _, tm_corr = load_corr_tables()
        table = build_teammate_rho_table(tm_corr)
        key = ('primary_creator', 'secondary_creator', ('pts', 'pts'))
        assert key in table
        recal_rho, naive_rho = table[key]
        assert abs(recal_rho) < 0.05, f"pts+pts recal_rho={recal_rho} expected ~0"
        assert naive_rho == pytest.approx(-0.15, abs=0.01)
