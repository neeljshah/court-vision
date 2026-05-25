"""
test_L30_contests.py — Tests for L30_contest_selector.

All tests are pure-Python; no network calls, no external fixtures.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
_TESTS_DIR = Path(__file__).resolve().parent
_EL_DIR = _TESTS_DIR.parent
_PROJECT_DIR = _EL_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

from scripts.execute_loop.L30_contest_selector import (  # noqa: E402
    ContestEV,
    _compute_leverage_score,
    _compute_rake,
    _infer_contest_type,
    rank_contests,
    recommend_entry_split,
    score_contest,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _cash_50_50(rake_pct: float = 0.05, field: int = 2, fee: float = 10.0) -> dict:
    """50/50 contest with explicit payout_curve → controlled rake."""
    pool = fee * field
    payouts = [pool * (1 - rake_pct) / field] * field
    return {
        "contest_id": "cash-001",
        "book": "DK",
        "name": "50/50 Main",
        "entry_fee": fee,
        "field_size": field,
        "payout_curve": payouts,
    }


def _gpp_large(rake_pct: float = 0.15, field: int = 10_000, fee: float = 25.0) -> dict:
    """Large GPP with explicit payout_curve."""
    pool = fee * field
    payouts = [pool * (1 - rake_pct) / field] * field
    return {
        "contest_id": "gpp-001",
        "book": "DK",
        "name": "Millionaire Maker GPP",
        "entry_fee": fee,
        "field_size": field,
        "payout_curve": payouts,
    }


def _satellite_contest() -> dict:
    return {
        "contest_id": "sat-001",
        "book": "DK",
        "name": "Satellite Qualifier Ticket",
        "entry_fee": 5.0,
        "field_size": 100,
    }


# ---------------------------------------------------------------------------
# 1. score_contest: 50/50 with rake=5%, edge=5% → roi > 0 AND type=="cash"
# ---------------------------------------------------------------------------

class TestScoreContestCash:
    def test_50_50_positive_roi_with_edge(self):
        contest = _cash_50_50(rake_pct=0.05, field=2, fee=10.0)
        ev = score_contest(contest, model_edge_pct=5.0, field_quality=0.5)
        assert ev.contest_type == "cash"
        assert ev.expected_roi > 0, f"expected positive ROI, got {ev.expected_roi}"

    def test_50_50_name_inference(self):
        contest = _cash_50_50()
        ev = score_contest(contest, model_edge_pct=5.0)
        assert ev.contest_type == "cash"

    def test_double_up_name_inference(self):
        c = {"contest_id": "x", "book": "DK", "name": "Double Up $10", "entry_fee": 10.0, "field_size": 5}
        ev = score_contest(c, model_edge_pct=5.0)
        assert ev.contest_type == "cash"

    def test_cash_contest_lineup_count_is_1(self):
        ev = score_contest(_cash_50_50(), model_edge_pct=5.0)
        assert ev.recommended_lineup_count == 1

    def test_fields_populated(self):
        contest = _cash_50_50(fee=20.0, field=4)
        ev = score_contest(contest, model_edge_pct=5.0)
        assert ev.contest_id == "cash-001"
        assert ev.book == "DK"
        assert ev.entry_fee == 20.0
        assert ev.field_size == 4
        assert isinstance(ev.leverage_score, float)
        assert 0.0 <= ev.leverage_score <= 1.0


# ---------------------------------------------------------------------------
# 2. score_contest: large GPP (10k field, rake 15%, edge 5%) → roi < 0
# ---------------------------------------------------------------------------

class TestScoreContestGPP:
    def test_10k_gpp_negative_roi_at_5pct_edge(self):
        contest = _gpp_large(rake_pct=0.15, field=10_000, fee=25.0)
        ev = score_contest(contest, model_edge_pct=5.0, field_quality=0.5)
        assert ev.contest_type == "gpp"
        assert ev.expected_roi < 0, f"expected negative ROI, got {ev.expected_roi}"

    def test_gpp_name_inference_tournament(self):
        c = {"contest_id": "t", "book": "DK", "name": "NBA Tournament $1M", "entry_fee": 5.0, "field_size": 50_000}
        ev = score_contest(c, model_edge_pct=5.0)
        assert ev.contest_type == "gpp"

    def test_gpp_name_inference_millionaire(self):
        c = {"contest_id": "m", "book": "DK", "name": "Millionaire Maker", "entry_fee": 20.0, "field_size": 150_000}
        ev = score_contest(c, model_edge_pct=5.0)
        assert ev.contest_type == "gpp"

    def test_gpp_lineup_count_capped_at_20(self):
        contest = _gpp_large(fee=1.0, field=10_000)
        ev = score_contest(contest, model_edge_pct=5.0, _budget_hint=10_000.0)
        assert ev.recommended_lineup_count <= 20

    def test_gpp_lineup_count_at_least_1(self):
        contest = _gpp_large(fee=500.0, field=1_000)
        ev = score_contest(contest, model_edge_pct=5.0, _budget_hint=100.0)
        assert ev.recommended_lineup_count >= 1

    def test_large_field_leverage_approaches_1(self):
        c = {"contest_id": "big", "book": "DK", "name": "GPP", "entry_fee": 10.0, "field_size": 1_000_000}
        ev = score_contest(c, model_edge_pct=5.0)
        assert ev.leverage_score == 1.0

    def test_small_field_leverage_below_1(self):
        c = {"contest_id": "small", "book": "DK", "name": "GPP Small", "entry_fee": 10.0, "field_size": 100}
        ev = score_contest(c, model_edge_pct=5.0)
        assert ev.leverage_score < 1.0


# ---------------------------------------------------------------------------
# 3. rank_contests returns list sorted by expected_roi DESC
# ---------------------------------------------------------------------------

class TestRankContests:
    def test_sorted_by_roi_descending(self):
        contests = [
            _cash_50_50(rake_pct=0.05, field=2, fee=10.0),
            _gpp_large(rake_pct=0.15, field=10_000, fee=25.0),
        ]
        ranked = rank_contests(contests, budget=1000.0, model_edge_pct=5.0)
        rois = [ev.expected_roi for ev in ranked]
        assert rois == sorted(rois, reverse=True)

    def test_returns_all_contests(self):
        contests = [
            _cash_50_50(),
            _gpp_large(),
            _satellite_contest(),
        ]
        ranked = rank_contests(contests, budget=1000.0, model_edge_pct=5.0)
        assert len(ranked) == 3

    def test_low_edge_penalises_gpp(self):
        """edge < 5%: GPP ROI must be <= 0."""
        gpp = _gpp_large()
        ranked = rank_contests([gpp], budget=1000.0, model_edge_pct=2.0)
        gpp_ev = next(ev for ev in ranked if ev.contest_type == "gpp")
        assert gpp_ev.expected_roi <= 0

    def test_high_edge_reduces_cash_roi(self):
        """edge > 10%: cash ROI scaled to ~30%; should be lower than raw cash ROI."""
        cash = _cash_50_50(rake_pct=0.05, field=2, fee=10.0)
        raw_ev = score_contest(cash, model_edge_pct=15.0)
        ranked = rank_contests([cash], budget=1000.0, model_edge_pct=15.0)
        scaled_roi = ranked[0].expected_roi
        assert scaled_roi < raw_ev.expected_roi

    def test_balanced_edge_both_types_can_be_positive(self):
        """At ~7% edge, both cash and a small GPP can have positive ROI."""
        cash = _cash_50_50(rake_pct=0.05, field=2, fee=10.0)
        small_gpp = {
            "contest_id": "sgpp", "book": "DK", "name": "GPP",
            "entry_fee": 5.0, "field_size": 50,
        }
        ranked = rank_contests([cash, small_gpp], budget=500.0, model_edge_pct=7.0)
        assert len(ranked) == 2

    def test_empty_input_returns_empty(self):
        ranked = rank_contests([], budget=1000.0)
        assert ranked == []


# ---------------------------------------------------------------------------
# 4. recommend_entry_split: no contest stake > 20% of budget
# ---------------------------------------------------------------------------

class TestRecommendEntrySplitCap:
    def test_no_stake_exceeds_20pct_budget(self):
        budget = 1000.0
        contests = [
            _cash_50_50(rake_pct=0.05, field=2, fee=50.0),   # positive ROI
            {"contest_id": "gpp-a", "book": "DK", "name": "GPP", "entry_fee": 3.0, "field_size": 50},
        ]
        ranked = rank_contests(contests, budget=budget, model_edge_pct=10.0)
        split = recommend_entry_split(budget=budget, ranked=ranked, max_pct_per_contest=0.20)
        max_allowed = 0.20 * budget
        for cid, info in split.items():
            assert info["stake"] <= max_allowed + 1e-6, (
                f"contest {cid} stake={info['stake']:.2f} exceeds cap {max_allowed:.2f}"
            )

    def test_entries_consistent_with_stake(self):
        budget = 500.0
        contests = [_cash_50_50(fee=10.0, field=2, rake_pct=0.05)]
        ranked = rank_contests(contests, budget=budget, model_edge_pct=10.0)
        split = recommend_entry_split(budget=budget, ranked=ranked)
        for cid, info in split.items():
            ev = next(e for e in ranked if e.contest_id == cid)
            expected_stake = info["entries"] * ev.entry_fee
            assert abs(info["stake"] - expected_stake) < 1e-6


# ---------------------------------------------------------------------------
# 5. budget < min entry_fee → returns {}
# ---------------------------------------------------------------------------

class TestRecommendEntrySplitBudgetTooSmall:
    def test_budget_below_min_entry_returns_empty(self):
        contests = [
            {"contest_id": "big", "book": "DK", "name": "50/50", "entry_fee": 50.0, "field_size": 2},
        ]
        ranked = rank_contests(contests, budget=10_000.0, model_edge_pct=10.0)
        split = recommend_entry_split(budget=5.0, ranked=ranked)
        assert split == {}

    def test_zero_budget_returns_empty(self):
        contests = [_cash_50_50()]
        ranked = rank_contests(contests, budget=0.0, model_edge_pct=10.0)
        split = recommend_entry_split(budget=0.0, ranked=ranked)
        assert split == {}


# ---------------------------------------------------------------------------
# 6. edge == 0 → recommend_entry_split returns {}
# ---------------------------------------------------------------------------

class TestZeroEdge:
    def test_zero_edge_all_rois_negative_or_zero(self):
        """With edge=0, every expected_roi should be <= 0 (just -rake)."""
        contests = [_cash_50_50(), _gpp_large()]
        ranked = rank_contests(contests, budget=1000.0, model_edge_pct=0.0)
        for ev in ranked:
            assert ev.expected_roi <= 0, f"{ev.contest_id} roi={ev.expected_roi}"

    def test_zero_edge_entry_split_empty(self):
        contests = [_cash_50_50(), _gpp_large()]
        ranked = rank_contests(contests, budget=1000.0, model_edge_pct=0.0)
        split = recommend_entry_split(budget=1000.0, ranked=ranked)
        assert split == {}

    def test_satellite_zero_edge_excluded(self):
        """Satellite always roi=0 so it won't pass the roi>0 gate."""
        ranked = rank_contests([_satellite_contest()], budget=1000.0, model_edge_pct=0.0)
        split = recommend_entry_split(budget=1000.0, ranked=ranked)
        assert split == {}


# ---------------------------------------------------------------------------
# 7. satellite excluded from recommend_entry_split
# ---------------------------------------------------------------------------

class TestSatelliteExclusion:
    def test_satellite_excluded_even_with_edge(self):
        """Satellite expected_roi = 0.0 always, so roi > 0 gate excludes it."""
        sat = _satellite_contest()
        cash = _cash_50_50(rake_pct=0.05)
        ranked = rank_contests([sat, cash], budget=1000.0, model_edge_pct=10.0)
        split = recommend_entry_split(budget=1000.0, ranked=ranked)
        assert "sat-001" not in split

    def test_satellite_lineup_count_is_0(self):
        ev = score_contest(_satellite_contest(), model_edge_pct=10.0)
        assert ev.contest_type == "satellite"
        assert ev.recommended_lineup_count == 0

    def test_satellite_roi_always_zero(self):
        ev = score_contest(_satellite_contest(), model_edge_pct=50.0)
        assert ev.expected_roi == 0.0


# ---------------------------------------------------------------------------
# Rake helpers
# ---------------------------------------------------------------------------

class TestComputeRake:
    def test_explicit_payout_curve(self):
        contest = {"contest_id": "r", "entry_fee": 10.0, "field_size": 4, "payout_curve": [9.0, 9.0, 9.0, 9.0]}
        rake = _compute_rake(contest)
        # pool=40, payouts=36, rake=4/40=0.10
        assert abs(rake - 0.10) < 1e-9

    def test_missing_payout_curve_uses_default(self):
        contest = {"contest_id": "r2", "entry_fee": 10.0, "field_size": 100}
        rake = _compute_rake(contest)
        assert rake == 0.12

    def test_missing_field_size_uses_default(self):
        contest = {"contest_id": "r3", "entry_fee": 10.0}
        rake = _compute_rake(contest)
        assert rake == 0.12


# ---------------------------------------------------------------------------
# Leverage score helper
# ---------------------------------------------------------------------------

class TestLeverageScore:
    def test_1000_field_equals_1(self):
        assert abs(_compute_leverage_score(1000) - 1.0) < 1e-9

    def test_100_field(self):
        expected = (100 / 1000) ** 0.5
        assert abs(_compute_leverage_score(100) - expected) < 1e-9

    def test_capped_at_1(self):
        assert _compute_leverage_score(1_000_000) == 1.0

    def test_zero_field_returns_0(self):
        assert _compute_leverage_score(0) == 0.0


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

class TestInferContestType:
    @pytest.mark.parametrize("name,expected", [
        ("50/50 Main", "cash"),
        ("Double-Up $5", "cash"),
        ("DoubleUp Special", "cash"),
        ("Satellite Qualifier", "satellite"),
        ("Ticket To Riches", "satellite"),
        ("NBA Qualifier Finals", "satellite"),
        ("Millionaire Maker", "gpp"),
        ("GPP $50K", "gpp"),
        ("NBA Tournament 100K", "gpp"),
    ])
    def test_name_patterns(self, name, expected):
        assert _infer_contest_type(name, field_size=500) == expected

    def test_small_field_fallback_to_cash(self):
        assert _infer_contest_type("Mystery Contest", field_size=10) == "cash"

    def test_large_field_fallback_to_gpp(self):
        assert _infer_contest_type("Mystery Contest", field_size=21) == "gpp"

    def test_boundary_field_20_is_cash(self):
        assert _infer_contest_type("Unknown", field_size=20) == "cash"

    def test_boundary_field_21_is_gpp(self):
        assert _infer_contest_type("Unknown", field_size=21) == "gpp"


# ---------------------------------------------------------------------------
# ContestEV dataclass
# ---------------------------------------------------------------------------

class TestContestEVDataclass:
    def test_all_fields_accessible(self):
        ev = ContestEV(
            contest_id="c1", book="DK", name="Test", entry_fee=10.0,
            field_size=100, total_payout=880.0, contest_type="cash",
            expected_roi=0.05, recommended_lineup_count=1, leverage_score=0.3,
        )
        assert ev.contest_id == "c1"
        assert ev.book == "DK"
        assert ev.contest_type == "cash"
        assert ev.expected_roi == 0.05

    def test_expected_profit_calculation_in_split(self):
        """expected_profit in split should equal stake * expected_roi."""
        contests = [_cash_50_50(rake_pct=0.01, field=2, fee=10.0)]  # very low rake → big ROI
        ranked = rank_contests(contests, budget=200.0, model_edge_pct=10.0)
        split = recommend_entry_split(budget=200.0, ranked=ranked)
        for cid, info in split.items():
            ev = next(e for e in ranked if e.contest_id == cid)
            expected = round(info["stake"] * ev.expected_roi, 4)
            assert abs(info["expected_profit"] - expected) < 1e-3
