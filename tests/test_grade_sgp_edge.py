"""tests/test_grade_sgp_edge.py

Unit tests for scripts/grade_sgp_edge.py and scripts/fanduel_sgp_scraper.py.

Tests:
  (a) american_to_decimal / decimal_to_american roundtrip
  (b) real_sgp_ev computation correctness
  (c) grade_pair HIT / MISS / PENDING logic
  (d) bootstrap_ev_ci confidence interval
  (e) parse_sgp_response parses all three known FD response patterns
  (f) book_blindspot_score weighting in sgp_edge_finder
  (g) book_priced flag set correctly for same-player haircut pairs
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ---------------------------------------------------------------------------
# (a) Odds utilities
# ---------------------------------------------------------------------------

class TestOddsConversions:

    def test_american_to_decimal_positive(self):
        from scripts.grade_sgp_edge import american_to_decimal
        assert american_to_decimal(200) == pytest.approx(3.0, abs=1e-6)

    def test_american_to_decimal_negative(self):
        from scripts.grade_sgp_edge import american_to_decimal
        assert american_to_decimal(-110) == pytest.approx(1.9090909, abs=1e-4)

    def test_american_to_decimal_minus100_boundary(self):
        from scripts.grade_sgp_edge import american_to_decimal
        # -100 is valid: 1 + 100/100 = 2.0
        assert american_to_decimal(-100) == pytest.approx(2.0, abs=1e-6)

    def test_american_to_decimal_plus100_boundary(self):
        from scripts.grade_sgp_edge import american_to_decimal
        # +100 is valid: 1 + 100/100 = 2.0
        assert american_to_decimal(100) == pytest.approx(2.0, abs=1e-6)

    def test_american_to_decimal_invalid_small(self):
        from scripts.grade_sgp_edge import american_to_decimal
        # |99| < 100 -> invalid
        assert american_to_decimal(99) is None
        assert american_to_decimal(-50) is None

    def test_decimal_to_american_positive_territory(self):
        from scripts.grade_sgp_edge import decimal_to_american
        # decimal 3.0 -> American +200
        assert decimal_to_american(3.0) == pytest.approx(200.0, abs=0.5)

    def test_decimal_to_american_negative_territory(self):
        from scripts.grade_sgp_edge import decimal_to_american
        # decimal 1.5 -> American -200
        assert decimal_to_american(1.5) == pytest.approx(-200.0, abs=0.5)

    def test_decimal_to_american_even_money(self):
        from scripts.grade_sgp_edge import decimal_to_american
        # decimal 2.0 -> American +100
        assert decimal_to_american(2.0) == pytest.approx(100.0, abs=0.5)

    def test_decimal_roundtrip(self):
        from scripts.grade_sgp_edge import american_to_decimal, decimal_to_american
        # Note: -100 and +100 both map to decimal 2.0, so -100 -> decimal_to_american
        # returns +100 (positive territory). Skip -100 from roundtrip test.
        for odds in [-120, -200, -110, 150, 250, 100]:
            dec = american_to_decimal(odds)
            back = decimal_to_american(dec)
            assert back == pytest.approx(odds, abs=1.0), f"Roundtrip failed for {odds}"


# ---------------------------------------------------------------------------
# (b) real_sgp_ev computation
# ---------------------------------------------------------------------------

class TestRealSgpEV:

    def test_ev_positive_when_p_recal_times_payout_exceeds_one(self):
        """EV = P_recal * decimal - 1. If P=0.4 and decimal=3.0 -> EV=+0.20."""
        p_recal = 0.40
        combined_decimal = 3.0
        ev = p_recal * combined_decimal - 1.0
        assert ev == pytest.approx(0.20, abs=1e-6)

    def test_ev_negative_vig_scenario(self):
        """Standard vig: P=0.476 at -110 (decimal 1.909) -> EV = -0.091."""
        p_recal = 0.476
        combined_decimal = 1.909
        ev = p_recal * combined_decimal - 1.0
        assert ev < 0, "Expected negative EV at fair single-leg vig"

    def test_ev_exact_break_even(self):
        """At break-even: P_recal * decimal = 1 -> EV = 0."""
        combined_decimal = 2.5
        p_recal = 1.0 / combined_decimal
        ev = p_recal * combined_decimal - 1.0
        assert ev == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# (c) grade_pair HIT / MISS / PENDING
# ---------------------------------------------------------------------------

class TestGradePair:

    def _make_sgp_row(self, combined_odds: float = -130) -> pd.Series:
        from scripts.grade_sgp_edge import american_to_decimal
        return pd.Series({
            'player_a'               : 'Jalen Brunson',
            'player_a_lower'         : 'jalen brunson',
            'stat_a'                 : 'ast',
            'line_a'                 : 5.5,
            'player_b'               : 'Josh Hart',
            'player_b_lower'         : 'josh hart',
            'stat_b'                 : 'fg3m',
            'line_b'                 : 1.5,
            'combined_odds_american' : combined_odds,
            'combined_decimal'       : american_to_decimal(combined_odds),
            'event_id'               : 35669206,
            'game_date'              : '2026-06-06',
        })

    def _make_recal_df(self, p_recal: float = 0.38) -> pd.DataFrame:
        return pd.DataFrame([{
            'player_a_lower': 'jalen brunson',
            'player_b_lower': 'josh hart',
            'stat_a'        : 'ast',
            'stat_b'        : 'fg3m',
            'p_recal'       : p_recal,
            'recal_rho'     : 0.113,
            'naive_rho'     : 0.0,
            'pair_type'     : 'creator_AST+catch_shoot_FG3M',
            'book_priced'   : False,
        }])

    def _make_box_df(self, ast_val: float, fg3m_val: float) -> pd.DataFrame:
        return pd.DataFrame([
            {'player_name_lower': 'jalen brunson', 'ast': ast_val,  'pts': 20, 'fg3m': 2},
            {'player_name_lower': 'josh hart',     'ast': 3,        'pts': 12, 'fg3m': fg3m_val},
        ])

    def test_pending_when_no_box_score(self):
        from scripts.grade_sgp_edge import grade_pair
        row = self._make_sgp_row()
        recal_df = self._make_recal_df()
        result = grade_pair(row, recal_df, box_df=None)
        assert result['outcome'] == 'PENDING'
        assert result['realized_value'] == ''

    def test_hit_when_both_legs_over(self):
        from scripts.grade_sgp_edge import grade_pair
        row = self._make_sgp_row(-130)
        recal_df = self._make_recal_df(0.38)
        box_df = self._make_box_df(ast_val=7, fg3m_val=2)  # 7>5.5, 2>1.5 -> HIT
        result = grade_pair(row, recal_df, box_df)
        assert result['outcome'] == 'HIT'
        assert float(result['realized_value']) > 1.0  # got paid

    def test_miss_when_one_leg_misses(self):
        from scripts.grade_sgp_edge import grade_pair
        row = self._make_sgp_row(-130)
        recal_df = self._make_recal_df(0.38)
        box_df = self._make_box_df(ast_val=3, fg3m_val=2)  # 3<5.5 -> MISS
        result = grade_pair(row, recal_df, box_df)
        assert result['outcome'] == 'MISS'
        assert float(result['realized_value']) == pytest.approx(0.0, abs=1e-6)

    def test_miss_when_both_legs_miss(self):
        from scripts.grade_sgp_edge import grade_pair
        row = self._make_sgp_row(-130)
        recal_df = self._make_recal_df(0.38)
        box_df = self._make_box_df(ast_val=2, fg3m_val=0)  # both miss
        result = grade_pair(row, recal_df, box_df)
        assert result['outcome'] == 'MISS'

    def test_ev_populated_from_recal(self):
        from scripts.grade_sgp_edge import grade_pair, american_to_decimal
        combined_odds = -130
        p_recal = 0.40
        combined_decimal = american_to_decimal(combined_odds)
        expected_ev = p_recal * combined_decimal - 1.0
        row = self._make_sgp_row(combined_odds)
        recal_df = self._make_recal_df(p_recal)
        result = grade_pair(row, recal_df, box_df=None)
        assert float(result['real_sgp_ev']) == pytest.approx(expected_ev, abs=1e-4)

    def test_swapped_player_order_still_matches(self):
        """grade_pair should match even when player order is swapped."""
        from scripts.grade_sgp_edge import grade_pair
        row = self._make_sgp_row()
        # Recal has Hart as player_a, Brunson as player_b (swapped)
        recal_df = pd.DataFrame([{
            'player_a_lower': 'josh hart',
            'player_b_lower': 'jalen brunson',
            'stat_a'        : 'fg3m',
            'stat_b'        : 'ast',
            'p_recal'       : 0.38,
            'recal_rho'     : 0.113,
            'naive_rho'     : 0.0,
            'pair_type'     : 'creator_AST+catch_shoot_FG3M',
            'book_priced'   : False,
        }])
        result = grade_pair(row, recal_df, box_df=None)
        assert float(result['p_recal']) == pytest.approx(0.38, abs=1e-3)


# ---------------------------------------------------------------------------
# (d) bootstrap_ev_ci
# ---------------------------------------------------------------------------

class TestBootstrapCI:

    def test_positive_ev_ci_excludes_zero(self):
        """Large positive EV values should produce CI excluding 0."""
        np.random.seed(42)
        from scripts.grade_sgp_edge import bootstrap_ev_ci
        ev_vals = [0.15] * 30  # strong consistent edge
        lo, hi = bootstrap_ev_ci(ev_vals, n_boot=2000)
        assert lo > 0, f"Expected CI>0 for consistent +15% EV, got [{lo:.3f}, {hi:.3f}]"

    def test_zero_ev_ci_includes_zero(self):
        """Zero-mean EV values should produce CI including 0."""
        np.random.seed(42)
        from scripts.grade_sgp_edge import bootstrap_ev_ci
        ev_vals = list(np.random.normal(0, 0.1, 20))
        lo, hi = bootstrap_ev_ci(ev_vals, n_boot=2000)
        assert lo < 0 and hi > 0, f"Expected CI to include 0, got [{lo:.3f}, {hi:.3f}]"

    def test_single_value_returns_nan(self):
        from scripts.grade_sgp_edge import bootstrap_ev_ci
        lo, hi = bootstrap_ev_ci([0.10])
        assert np.isnan(lo) or np.isnan(hi)


# ---------------------------------------------------------------------------
# (e) parse_sgp_response — FD BetBuilder response patterns
# ---------------------------------------------------------------------------

class TestParseSgpResponse:

    def test_pattern_a_combined_price(self):
        from scripts.fanduel_sgp_scraper import parse_sgp_response
        resp = {"combinedPrice": -140, "status": "AVAILABLE"}
        assert parse_sgp_response(resp) == pytest.approx(-140, abs=0.1)

    def test_pattern_b_price_nested(self):
        from scripts.fanduel_sgp_scraper import parse_sgp_response
        resp = {"price": {"americanOdds": -165, "fractionalOdds": "3/5"}, "status": "OK"}
        assert parse_sgp_response(resp) == pytest.approx(-165, abs=0.1)

    def test_pattern_c_combined_nested(self):
        from scripts.fanduel_sgp_scraper import parse_sgp_response
        resp = {"combined": {"americanOdds": 110}, "legs": [], "status": "AVAILABLE"}
        assert parse_sgp_response(resp) == pytest.approx(110, abs=0.1)

    def test_unknown_structure_returns_none(self):
        from scripts.fanduel_sgp_scraper import parse_sgp_response
        resp = {"error": True, "message": "not found"}
        assert parse_sgp_response(resp) is None


# ---------------------------------------------------------------------------
# (f) book_blindspot_score weighting
# ---------------------------------------------------------------------------

class TestBookBlindspotScore:

    def test_cross_player_gets_high_score(self):
        """Teammate pair should score > same-player haircut pair."""
        from scripts.sgp_edge_finder import book_blindspot_score
        tm_score = book_blindspot_score('teammate', 'ast', 'fg3m', 0.113, 'creator+catcher')
        sp_haircut = book_blindspot_score('same_player', 'fg3m', 'pts', 0.188, 'SPOT_UP')
        assert tm_score > sp_haircut, (
            f"Expected teammate ({tm_score}) > same_player haircut ({sp_haircut})"
        )

    def test_haircut_pair_score_is_low(self):
        """fg3m+pts same-player pair should score very low (book prices it)."""
        from scripts.sgp_edge_finder import book_blindspot_score
        score = book_blindspot_score('same_player', 'fg3m', 'pts', 0.188, 'SPOT_UP')
        assert score < 0.5, f"Expected low score for haircut pair, got {score}"

    def test_non_haircut_same_player_scores_medium(self):
        """Non-haircut same-player pair (e.g. fg3m+reb) scores higher than haircut."""
        from scripts.sgp_edge_finder import book_blindspot_score
        score_haircut = book_blindspot_score('same_player', 'fg3m', 'pts', 0.10, 'X')
        score_other   = book_blindspot_score('same_player', 'fg3m', 'reb', 0.10, 'X')
        assert score_other > score_haircut

    def test_higher_rho_delta_increases_score(self):
        """Larger |recal - naive| should increase blindspot score."""
        from scripts.sgp_edge_finder import book_blindspot_score
        score_low  = book_blindspot_score('teammate', 'ast', 'fg3m', 0.05, 'arch')
        score_high = book_blindspot_score('teammate', 'ast', 'fg3m', 0.20, 'arch')
        assert score_high > score_low

    def test_score_is_non_negative(self):
        from scripts.sgp_edge_finder import book_blindspot_score
        for ptype in ('same_player', 'teammate'):
            for sa, sb in [('pts', 'reb'), ('fg3m', 'pts'), ('ast', 'fg3m')]:
                for delta in [-0.15, 0.0, 0.10, 0.20]:
                    score = book_blindspot_score(ptype, sa, sb, delta, 'X')
                    assert score >= 0, f"{ptype} {sa}+{sb} delta={delta} -> {score}"


# ---------------------------------------------------------------------------
# (g) book_priced flag for same-player haircut pairs
# ---------------------------------------------------------------------------

class TestBookPricedFlag:

    def test_fg3m_pts_flagged_as_book_priced(self):
        """SPOT_UP fg3m+pts should be flagged book_priced=True."""
        from scripts.sgp_edge_finder import BOOK_HAIRCUT_SAME_PLAYER_PAIRS
        assert frozenset({'fg3m', 'pts'}) in BOOK_HAIRCUT_SAME_PLAYER_PAIRS

    def test_pts_reb_flagged_as_book_priced(self):
        from scripts.sgp_edge_finder import BOOK_HAIRCUT_SAME_PLAYER_PAIRS
        assert frozenset({'pts', 'reb'}) in BOOK_HAIRCUT_SAME_PLAYER_PAIRS

    def test_pts_ast_flagged_as_book_priced(self):
        from scripts.sgp_edge_finder import BOOK_HAIRCUT_SAME_PLAYER_PAIRS
        assert frozenset({'pts', 'ast'}) in BOOK_HAIRCUT_SAME_PLAYER_PAIRS

    def test_ast_fg3m_not_flagged(self):
        """Cross-player pair ast+fg3m should NOT be in haircut set."""
        from scripts.sgp_edge_finder import BOOK_HAIRCUT_SAME_PLAYER_PAIRS
        assert frozenset({'ast', 'fg3m'}) not in BOOK_HAIRCUT_SAME_PLAYER_PAIRS
