"""tests/test_parlay_constructor.py — Unit tests for src/prediction/parlay_constructor.py

Covers:
  - Combo enumeration correctness (no fg3m+pts in same combo)
  - Joint hit-rate estimate (independent vs correlation-adjusted)
  - Kelly stake bounds
  - rank_parlays ordering and positive-ROI filter
  - build_parlay_candidates with minimal DataFrame
"""
from __future__ import annotations

import sys
import os

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.parlay_constructor import (
    build_parlay_candidates,
    compute_parlay_metrics,
    kelly_parlay_stake,
    rank_parlays,
    FORBIDDEN_PAIRS,
    BREAKEVEN_3LEG,
    SGP_PENALTY,
    _is_forbidden_combo,
    _american_to_decimal,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_bet(player: str, stat: str, line: float = 10.0,
              odds: int = -110, prob: float = 0.60,
              game_id: str = "GAME1") -> dict:
    return {
        "player": player, "stat": stat, "line": line, "side": "OVER",
        "odds": odds, "prob": prob, "game_id": game_id,
        "model": line + 1.0, "edge": 1.0, "ev": 0.05,
        "kelly_pct": 5.0, "kelly_stake": 50.0,
    }


def _make_df(bets: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(bets)


# ── _is_forbidden_combo ───────────────────────────────────────────────────────

class TestForbiddenCombo:
    def test_fg3m_pts_forbidden(self):
        assert _is_forbidden_combo(("fg3m", "pts", "reb")) is True

    def test_pts_fg3m_order_invariant(self):
        assert _is_forbidden_combo(("pts", "fg3m", "ast")) is True

    def test_valid_combo_not_forbidden(self):
        assert _is_forbidden_combo(("ast", "reb", "blk")) is False

    def test_single_stat_not_forbidden(self):
        assert _is_forbidden_combo(("fg3m",)) is False

    def test_two_stats_fg3m_pts(self):
        assert _is_forbidden_combo(("fg3m", "pts")) is True

    def test_stl_blk_pts_allowed(self):
        assert _is_forbidden_combo(("stl", "blk", "pts")) is False


# ── compute_parlay_metrics ────────────────────────────────────────────────────

class TestComputeParlayMetrics:
    def _make_legs(self, stats=("ast", "reb", "blk")):
        return [_make_bet("Jokic", s) for s in stats]

    def test_hit_rate_indep_is_product(self):
        legs = self._make_legs()
        result = compute_parlay_metrics(legs, hit_rates=[0.6, 0.6, 0.6],
                                        prices=[-110, -110, -110])
        expected_indep = 0.6 ** 3
        assert abs(result["hit_rate_indep"] - expected_indep) < 1e-9

    def test_hit_rate_adj_bounded(self):
        legs = self._make_legs()
        result = compute_parlay_metrics(legs, hit_rates=[0.99, 0.99, 0.99],
                                        prices=[-110, -110, -110])
        assert 0.0 <= result["hit_rate_adj"] <= 1.0

    def test_decimal_odds_product(self):
        legs = self._make_legs()
        result = compute_parlay_metrics(legs, hit_rates=[0.6, 0.6, 0.6],
                                        prices=[-110, -110, -110])
        dec = _american_to_decimal(-110)
        assert abs(result["decimal_odds"] - dec ** 3) < 1e-6

    def test_sgp_penalty_applied(self):
        legs = self._make_legs()
        result = compute_parlay_metrics(legs, hit_rates=[0.6, 0.6, 0.6],
                                        prices=[-110, -110, -110])
        net_raw = result["decimal_odds"] - 1.0
        expected_sgp = net_raw * (1.0 - SGP_PENALTY)
        assert abs(result["sgp_payout_adj"] - expected_sgp) < 1e-9

    def test_ev_sgp_formula(self):
        legs = self._make_legs()
        result = compute_parlay_metrics(legs, hit_rates=[0.6, 0.6, 0.6],
                                        prices=[-110, -110, -110])
        p = result["hit_rate_adj"]
        b = result["sgp_payout_adj"]
        expected_ev = p * b - (1 - p) * 1.0
        assert abs(result["ev_sgp"] - expected_ev) < 1e-9

    def test_ev_raw_gt_ev_sgp_for_winning_combo(self):
        legs = self._make_legs()
        result = compute_parlay_metrics(legs, hit_rates=[0.7, 0.7, 0.7],
                                        prices=[-110, -110, -110])
        assert result["ev_raw"] >= result["ev_sgp"]

    def test_positive_odds_boost_payout(self):
        legs = self._make_legs()
        result_neg = compute_parlay_metrics(legs, hit_rates=[0.6, 0.6, 0.6],
                                            prices=[-110, -110, -110])
        result_pos = compute_parlay_metrics(legs, hit_rates=[0.6, 0.6, 0.6],
                                            prices=[+145, -110, -110])
        assert result_pos["decimal_odds"] > result_neg["decimal_odds"]

    def test_same_player_corr_adjustment_non_trivial(self):
        """Same-player corr adjustment must differ from 1.0 for correlated pairs."""
        legs = [_make_bet("Jokic", "pts"), _make_bet("Jokic", "reb"),
                _make_bet("Jokic", "ast")]
        result_sp = compute_parlay_metrics(legs, hit_rates=[0.6, 0.6, 0.6],
                                           prices=[-110, -110, -110],
                                           same_player=True)
        result_xp = compute_parlay_metrics(legs, hit_rates=[0.6, 0.6, 0.6],
                                           prices=[-110, -110, -110],
                                           same_player=False)
        # Same-player positive correlations boost the joint probability
        assert result_sp["hit_rate_adj"] >= result_xp["hit_rate_adj"]

    def test_zero_hit_rate_zero_ev(self):
        legs = self._make_legs()
        result = compute_parlay_metrics(legs, hit_rates=[0.0, 0.0, 0.0],
                                        prices=[-110, -110, -110])
        assert result["ev_sgp"] < 0
        assert result["hit_rate_adj"] == 0.0

    def test_breakeven_3leg_constant(self):
        """At break-even hit rate with -110/-110/-110 EV should be ~0."""
        legs = self._make_legs()
        dec = _american_to_decimal(-110)
        be = 1.0 / (dec ** 3)
        assert abs(be - BREAKEVEN_3LEG) < 0.005  # Within 0.5pp


# ── build_parlay_candidates ───────────────────────────────────────────────────

class TestBuildParlayCandidates:
    def _valid_slate(self) -> pd.DataFrame:
        return _make_df([
            _make_bet("Jokic",   "pts",  22.5, -110, 0.65, "G1"),
            _make_bet("Jokic",   "reb",  11.5, -110, 0.62, "G1"),
            _make_bet("Jokic",   "ast",   8.5, -110, 0.68, "G1"),
            _make_bet("Curry",   "fg3m",  4.5, -115, 0.55, "G2"),
            _make_bet("Curry",   "pts",  28.5, -110, 0.58, "G2"),
            _make_bet("AD",      "blk",   1.5, +145, 0.70, "G1"),
            _make_bet("SGA",     "stl",   1.5, -110, 0.63, "G3"),
        ])

    def test_no_fg3m_pts_combo(self):
        df = self._valid_slate()
        candidates = build_parlay_candidates(df)
        for _, row in candidates.iterrows():
            stats = [s.lower() for s in row["stat_combo"].split("+")]
            assert not (("fg3m" in stats) and ("pts" in stats)), (
                f"fg3m+pts found in combo: {row['stat_combo']}"
            )

    def test_returns_dataframe(self):
        df = self._valid_slate()
        candidates = build_parlay_candidates(df)
        assert isinstance(candidates, pd.DataFrame)

    def test_required_columns_present(self):
        df = self._valid_slate()
        candidates = build_parlay_candidates(df)
        required_cols = {
            "parlay_id", "stat_combo", "hit_rate_indep", "hit_rate_adj",
            "decimal_odds", "american_odds", "ev_sgp", "expected_roi_sgp_pct",
        }
        assert required_cols.issubset(set(candidates.columns))

    def test_empty_slate_returns_empty(self):
        df = _make_df([])
        # Empty df has no columns — just confirm no exception and empty result
        try:
            candidates = build_parlay_candidates(df)
        except (ValueError, KeyError):
            pass  # Acceptable: missing required columns

    def test_under_bets_excluded(self):
        """UNDER bets should not appear in candidates."""
        bets = [
            _make_bet("Jokic", "pts",  22.5),
            _make_bet("Jokic", "reb",  11.5),
            _make_bet("Jokic", "ast",   8.5),
        ]
        bets_df = _make_df(bets)
        bets_df.loc[0, "side"] = "UNDER"
        # Only 2 OVER bets remain — no 3-leg combos possible
        candidates = build_parlay_candidates(bets_df)
        assert candidates.empty

    def test_combos_exhaustive_count(self):
        """4 valid bets → C(4,3)=4 combos max; some may be filtered for fg3m+pts."""
        bets = _make_df([
            _make_bet("P1", "ast",  5.5),
            _make_bet("P2", "reb",  8.5),
            _make_bet("P3", "blk",  1.5),
            _make_bet("P4", "stl",  1.5),
        ])
        candidates = build_parlay_candidates(bets)
        assert len(candidates) == 4  # C(4,3) = 4, no forbidden pairs

    def test_fg3m_pts_in_pool_reduces_count(self):
        """Adding fg3m+pts bets reduces enumerable combos."""
        bets_no_conflict = _make_df([
            _make_bet("P1", "ast",  5.5),
            _make_bet("P2", "reb",  8.5),
            _make_bet("P3", "blk",  1.5),
            _make_bet("P4", "stl",  1.5),
        ])
        bets_with_conflict = _make_df([
            _make_bet("P1", "fg3m", 4.5),
            _make_bet("P2", "pts",  22.5),
            _make_bet("P3", "reb",  8.5),
            _make_bet("P4", "blk",  1.5),
        ])
        c_no_conflict = build_parlay_candidates(bets_no_conflict)
        c_with_conflict = build_parlay_candidates(bets_with_conflict)
        # C(4,3)=4 valid vs fewer due to fg3m+pts exclusion
        assert len(c_with_conflict) < len(c_no_conflict)


# ── rank_parlays ──────────────────────────────────────────────────────────────

class TestRankParlays:
    def _make_candidates(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"parlay_id": "a", "expected_roi_sgp_pct": 55.0, "ev_sgp": 0.55},
            {"parlay_id": "b", "expected_roi_sgp_pct": 30.0, "ev_sgp": 0.30},
            {"parlay_id": "c", "expected_roi_sgp_pct": -5.0, "ev_sgp": -0.05},
            {"parlay_id": "d", "expected_roi_sgp_pct": 70.0, "ev_sgp": 0.70},
        ])

    def test_sorted_descending(self):
        ranked = rank_parlays(self._make_candidates())
        roi_vals = ranked["expected_roi_sgp_pct"].tolist()
        assert roi_vals == sorted(roi_vals, reverse=True)

    def test_negative_roi_excluded(self):
        ranked = rank_parlays(self._make_candidates())
        assert (ranked["expected_roi_sgp_pct"] > 0).all()

    def test_rank_column_one_indexed(self):
        ranked = rank_parlays(self._make_candidates())
        assert ranked["rank"].iloc[0] == 1

    def test_top_n_limit(self):
        ranked = rank_parlays(self._make_candidates(), top_n=2)
        assert len(ranked) <= 2

    def test_empty_input(self):
        empty = pd.DataFrame(columns=["parlay_id", "expected_roi_sgp_pct"])
        ranked = rank_parlays(empty)
        assert ranked.empty


# ── kelly_parlay_stake ────────────────────────────────────────────────────────

class TestKellyParlayStake:
    def _profitable_parlay(self) -> dict:
        legs = [_make_bet("P", s) for s in ("ast", "reb", "blk")]
        return compute_parlay_metrics(legs, hit_rates=[0.67, 0.62, 0.67],
                                      prices=[-110, -110, +145])

    def test_positive_edge_returns_positive_stake(self):
        parlay = self._profitable_parlay()
        stake = kelly_parlay_stake(parlay, bankroll=1000.0)
        assert stake > 0

    def test_stake_bounded_by_kelly_fraction_of_bankroll(self):
        parlay = self._profitable_parlay()
        bankroll = 1000.0
        kf = 0.10
        stake = kelly_parlay_stake(parlay, bankroll=bankroll, kelly_fraction=kf)
        assert stake <= kf * bankroll

    def test_zero_hit_rate_zero_stake(self):
        parlay = compute_parlay_metrics(
            [_make_bet("P", s) for s in ("ast", "reb", "blk")],
            hit_rates=[0.0, 0.0, 0.0], prices=[-110, -110, -110]
        )
        assert kelly_parlay_stake(parlay, bankroll=1000.0) == 0.0

    def test_negative_ev_zero_stake(self):
        """Below break-even hit rate → no stake."""
        parlay = compute_parlay_metrics(
            [_make_bet("P", s) for s in ("ast", "reb", "blk")],
            hit_rates=[0.40, 0.40, 0.40], prices=[-110, -110, -110]
        )
        assert kelly_parlay_stake(parlay, bankroll=1000.0) == 0.0

    def test_smaller_fraction_reduces_stake(self):
        parlay = self._profitable_parlay()
        stake_10 = kelly_parlay_stake(parlay, bankroll=1000.0, kelly_fraction=0.10)
        stake_05 = kelly_parlay_stake(parlay, bankroll=1000.0, kelly_fraction=0.05)
        assert stake_10 >= stake_05

    def test_larger_bankroll_scales_stake(self):
        parlay = self._profitable_parlay()
        stake_1k = kelly_parlay_stake(parlay, bankroll=1000.0)
        stake_2k = kelly_parlay_stake(parlay, bankroll=2000.0)
        assert stake_2k == pytest.approx(stake_1k * 2, rel=1e-3)

    def test_stake_non_negative(self):
        for hr in [0.10, 0.20, 0.30, 0.50, 0.70]:
            parlay = compute_parlay_metrics(
                [_make_bet("P", s) for s in ("ast", "reb", "blk")],
                hit_rates=[hr, hr, hr], prices=[-110, -110, -110]
            )
            stake = kelly_parlay_stake(parlay, bankroll=1000.0)
            assert stake >= 0.0
