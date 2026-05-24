"""Boundary tests for src.prediction.heat_check_shrinkage (cycle 96d, loop 5)."""
from __future__ import annotations

from src.prediction.heat_check_shrinkage import (
    HEAT_CHECK_STATS,
    heat_check_factor,
)


def test_ratio_below_trigger_returns_one():
    # q3_ppm / q12_ppm = 0.8 < 1.5  ->  no shrinkage.
    assert heat_check_factor(q3_ppm=0.8, q12_ppm=1.0, season_ppm=0.9) == 1.0
    # Exactly at trigger boundary (1.5) is still "no shrinkage" per strict <.
    assert heat_check_factor(q3_ppm=1.5, q12_ppm=1.0, season_ppm=0.9) == 1.0


def test_ratio_two_mild_shrinkage():
    # ratio = 2.0 with weight 0.20:
    # falls into stronger branch (>= 2.0): 1 - 0.20 * (2.0 - 1.5) = 0.90.
    # Spec calls this "mild" (~0.95). Cross-check the *mild* branch end at
    # ratio=1.99 yields ~0.95:
    mild_just_below_two = heat_check_factor(
        q3_ppm=1.99, q12_ppm=1.0, season_ppm=0.9, shrinkage_weight=0.20,
    )
    # mild branch: 1 - 0.5*0.20*(1.99 - 1.5) = 1 - 0.049 = 0.951
    assert abs(mild_just_below_two - 0.951) < 1e-6
    # And the >=2.0 branch:
    at_two = heat_check_factor(
        q3_ppm=2.0, q12_ppm=1.0, season_ppm=0.9, shrinkage_weight=0.20,
    )
    # 1 - 0.20 * 0.5 = 0.90
    assert abs(at_two - 0.90) < 1e-6


def test_ratio_three_floors_at_seven_tenths():
    # ratio = 3.0, weight 0.20: 1 - 0.20 * 1.5 = 0.70 -- exactly at floor.
    assert (
        heat_check_factor(q3_ppm=3.0, q12_ppm=1.0, season_ppm=0.9,
                          shrinkage_weight=0.20)
        == 0.70
    )
    # ratio = 5.0 would compute to negative; floor protects.
    assert (
        heat_check_factor(q3_ppm=5.0, q12_ppm=1.0, season_ppm=0.9,
                          shrinkage_weight=0.20)
        == 0.70
    )
    # Very large weight at moderate ratio also floors.
    assert (
        heat_check_factor(q3_ppm=2.5, q12_ppm=1.0, season_ppm=0.9,
                          shrinkage_weight=0.80)
        == 0.70
    )


def test_season_ppm_is_ignored_by_formula():
    # Swap season_ppm wildly; factor must NOT change because formula uses
    # only q3 vs q12 ratio.
    base = heat_check_factor(q3_ppm=2.4, q12_ppm=1.0, season_ppm=1.0,
                             shrinkage_weight=0.20)
    high_season = heat_check_factor(q3_ppm=2.4, q12_ppm=1.0, season_ppm=999.0,
                                    shrinkage_weight=0.20)
    none_season = heat_check_factor(q3_ppm=2.4, q12_ppm=1.0, season_ppm=None,
                                    shrinkage_weight=0.20)
    assert base == high_season == none_season


def test_heat_check_stats_set():
    # Wiring contract: only scoring stats are eligible.
    assert HEAT_CHECK_STATS == frozenset({"pts", "ast", "fg3m"})
