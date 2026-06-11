"""P3.4 — universal_winprob: win% from projected-final + time (never raw live margin).

Proves the probabilistic shape (tie=0.5, monotone, band shrinks to a step) and the routing discipline
(no sim-WP before endQ3; fail-closed league-wide; no Brier-0.183 magic constant).
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ingame import universal_winprob as uwp  # noqa: E402


def test_tie_projection_is_half():
    assert abs(uwp.win_prob_from_projection(0.0, 0.5) - 0.5) < 1e-12


def test_positive_margin_favours_home_and_is_monotone():
    p_small = uwp.win_prob_from_projection(3.0, 0.5)
    p_big = uwp.win_prob_from_projection(10.0, 0.5)
    assert 0.5 < p_small < p_big < 1.0
    # symmetric: a mirror-image away lead
    assert abs(uwp.win_prob_from_projection(-3.0, 0.5) - (1.0 - p_small)) < 1e-9


def test_band_shrinks_as_game_ends():
    # same +4 projected margin is MORE certain late (smaller remaining_frac -> tighter band)
    early = uwp.win_prob_from_projection(4.0, 0.9)
    late = uwp.win_prob_from_projection(4.0, 0.05)
    assert late > early
    # at the buzzer a positive projected margin is ~certain
    assert uwp.win_prob_from_projection(4.0, 0.0) > 0.999


def test_eligibility_no_sim_wp_before_q4():
    assert uwp.universal_eligible(period=2, coverage_class="mc_full") is False  # Q1-Q2 -> sigmoid wins
    assert uwp.universal_eligible(period=3, coverage_class="mc_full") is False  # still before endQ3/Q4
    assert uwp.universal_eligible(period=4, coverage_class="mc_full") is True


def test_eligibility_fails_closed_off_mc_coverage():
    # league-wide (non sim-coverable) -> NOT eligible -> router uses existing inplay_winprob stack
    assert uwp.universal_eligible(period=4, coverage_class="shotzone") is False
    assert uwp.universal_eligible(period=4, coverage_class="league_min") is False


def test_routed_returns_none_when_should_fall_back():
    assert uwp.win_prob_routed(2, "mc_full", 5.0, 0.6) is None         # too early
    assert uwp.win_prob_routed(4, "league_min", 5.0, 0.3) is None      # off-coverage
    assert uwp.win_prob_routed(4, "mc_full", None, 0.3) is None        # no projection
    v = uwp.win_prob_routed(4, "mc_full", 5.0, 0.3)
    assert v is not None and v > 0.5


def test_no_brier_183_numeric_literal():
    import ast
    src = open(os.path.join(ROOT, "src", "ingame", "universal_winprob.py"), encoding="utf-8").read()
    # 0.183 may appear in the docstring (explaining its REMOVAL) but never as a live float literal
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            assert abs(node.value - 0.183) > 1e-9, "0.183 used as a numeric literal (a live threshold)"
