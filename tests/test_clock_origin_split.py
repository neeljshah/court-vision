"""Regression test for the gated clock possession-origin split (CV_CLOCK_ORIGIN_SPLIT, iter-9).

The split refines the clock engine's origin model (game_clock_sim): after-make (dead-ball, set defense) gets a
LOWER PPP than after-miss-DREB, cross-season-measured + MEAN-PRESERVING. Default OFF -> byte-identical (the
board's test_sim_engine.py already asserts the sim is unchanged with the flag unset). These checks lock the
mean-preservation arithmetic + the env-gating.
"""
import os


def test_split_multipliers_are_mean_preserving():
    # measured corpus shares among the clock sim's "half" possessions (after-make + after-miss-DREB)
    dead_mult, half_mult = 0.9713, 1.0353
    share_make = 0.551   # after-make share of the half population (2022-23+2023-24, 549k poss)
    blended = share_make * dead_mult + (1 - share_make) * half_mult
    assert abs(blended - 1.0) < 0.005      # the split preserves the blended "half" level (no PPP-level drift)


def test_dead_below_half_below_trans():
    # the ordering the data showed: dead (set defense) < after-miss half < transition
    dead_mult, half_mult, trans = 0.9713, 1.0353, 1.337
    assert dead_mult < half_mult < trans


def test_split_is_env_gated_and_byte_identical_off():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "src", "sim", "game_clock_sim.py"), encoding="utf-8").read()
    assert 'os.environ.get("CV_CLOCK_ORIGIN_SPLIT") == "1"' in src
    # OFF path must keep the original half/trans/2nd lift (1.0 / 1.337 / 1.29) reachable
    assert '1.0 if origin == "half" else (1.337 if origin == "trans" else 1.29)' in src
    # the "dead" origin PPP value only exists inside the gated branch (the dict entry, not the explanatory comment)
    guard = src.index('os.environ.get("CV_CLOCK_ORIGIN_SPLIT")')
    assert src.index('"dead": 0.9713') > guard
