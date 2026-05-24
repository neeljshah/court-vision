"""tests/test_live_factors.py — cycle 89b (loop 5) unification.

Pins the canonical foul_trouble_factor table to the single source of truth in
``src/prediction/live_factors.py``. Also includes graceful-input regressions
to guarantee live-dashboard callers never crash on malformed snapshots.
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.live_factors import foul_trouble_factor  # noqa: E402


# ─── canonical table pinning ────────────────────────────────────────────────

def test_no_fouls_returns_one():
    """pf=0 anywhere => no adjustment."""
    assert foul_trouble_factor(0, 2, 5.0) == 1.00


def test_five_fouls_q1_returns_040():
    """5+ fouls anywhere => 0.40 (aggressive bench)."""
    assert foul_trouble_factor(5, 1, 10.0) == 0.40


def test_five_fouls_late_q4_returns_040():
    """5+ fouls late Q4 still 0.40 — one away from foul-out, never softens."""
    assert foul_trouble_factor(5, 4, 2.0) == 0.40


def test_four_fouls_q3_returns_055():
    """4 fouls in Q3 — classic 'rest until Q4' benching."""
    assert foul_trouble_factor(4, 3, 5.0) == 0.55


def test_four_fouls_early_q4_returns_065():
    """4 fouls early Q4 (>6 min left) — leash shortened but still plays."""
    assert foul_trouble_factor(4, 4, 7.0) == 0.65


def test_four_fouls_late_q4_returns_090():
    """4 fouls late Q4 (<=6 min) — must-win, coach lets them play."""
    assert foul_trouble_factor(4, 4, 3.0) == 0.90


def test_three_fouls_q2_returns_080():
    """3 fouls in Q2 — 'save him for the half' bench."""
    assert foul_trouble_factor(3, 2, 8.0) == 0.80


def test_three_fouls_q1_returns_one():
    """3 fouls in Q1 does NOT trigger — only Q2 has the 3-foul rule."""
    assert foul_trouble_factor(3, 1, 8.0) == 1.00


# ─── robustness / graceful input handling ────────────────────────────────────

def test_none_pf_returns_one():
    """pf=None must not crash — degrade to 1.00."""
    assert foul_trouble_factor(None, 3, 5.0) == 1.00


def test_four_fouls_overtime_acts_like_late_q4():
    """OT (period >= 5) with 4 fouls acts like late Q4 (must-win) -> 0.90."""
    assert foul_trouble_factor(4, 5, 2.0) == 0.90


# ─── extra robustness (string/garbage inputs that live snapshots can produce) ──

def test_string_pf_returns_one_when_garbage():
    """A non-numeric string falls through to 'no adjustment' rather than raising."""
    assert foul_trouble_factor("garbage", 3, 5.0) == 1.00


def test_string_numeric_pf_is_parsed():
    """A numeric string still works — JSON often gives '4' from upstream."""
    assert foul_trouble_factor("4", 3, 5.0) == 0.55


def test_negative_pf_treated_as_zero():
    """Negative pf is nonsensical — treat as 0, never as 'in trouble'."""
    assert foul_trouble_factor(-1, 4, 2.0) == 1.00
