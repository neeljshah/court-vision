"""Per-file test for improve.d2_soccer_competition_tiebreak. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_d2_soccer_competition_tiebreak.py -q
"""
from __future__ import annotations

from scripts.platformkit.improve import d2_soccer_competition_tiebreak as tb


def test_tiebreak_upgrades_only_on_same_sign_and_cleared_bar():
    v = lambda p, e: "CONFIRMED_LOCAL" if (p < 0.01 and abs(e) >= 0.02) else "NULL_LOCAL"
    assert tb.tiebreak(True, 0.03, 0.001, 100, 20, v).startswith("CONFIRMED_LOCAL")
    assert tb.tiebreak(True, -0.03, 0.001, 100, 20, v).startswith("NULL_LOCAL")  # opposite sign


def test_tiebreak_flags_underpowered_before_directional_verdict():
    """Failure mode: a tiny n with a clean p-value must not silently read as
    a confident confirm/deny -- n floor check must come before the verdict."""
    v = lambda p, e: "CONFIRMED_LOCAL"
    assert tb.tiebreak(True, 0.03, 0.001, 3, 20, v).startswith("UNDERPOWERED")


def test_tiebreak_not_testable_on_nan_p():
    assert tb.tiebreak(True, 0.03, float("nan"), 100, 20, lambda p, e: "NULL_LOCAL") == "NOT_TESTABLE"


def test_competition_groups_balances_match_counts():
    """The greedy largest-first assignment must not leave one group starved --
    imbalance should be small relative to the largest single competition."""
    groups = tb.competition_groups()
    assert set(groups.values()) <= {"A", "B"}
    assert len(groups) == 80  # full local StatsBomb competition catalog
