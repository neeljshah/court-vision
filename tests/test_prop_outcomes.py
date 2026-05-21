"""
tests/test_prop_outcomes.py — Unit tests for prop_outcomes derive logic.

Covers:
  - over hits (single stat)
  - under hits (single stat)
  - push (exact match)
  - void (DNP — box_score is None)
  - void (minutes == 0)
  - compound stats: pra, pr, pa, ra
  - all single-stat markets: pts, reb, ast, stl, blk, threes_made, fg_made, ft_made
  - unknown market raises ValueError
  - missing column yields void
"""
from __future__ import annotations

import pytest

from src.data.derive.prop_outcomes import compute_outcome, resolve_result


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _box(
    pts: int = 20, reb: int = 5, ast: int = 4,
    stl: int = 1, blk: int = 1,
    fg3: int = 2, fg: int = 7, ft: int = 4,
    minutes: float = 32.0,
) -> dict:
    """Build a minimal box_scores-like dict."""
    return {
        "minutes": minutes,
        "points": pts,
        "rebounds": reb,
        "assists": ast,
        "steals": stl,
        "blocks": blk,
        "fg3_made": fg3,
        "fg_made": fg,
        "ft_made": ft,
    }


# ── Basic result outcomes ─────────────────────────────────────────────────────

def test_over_hits():
    box = _box(pts=25)
    actual, result = compute_outcome({"market": "pts", "line": 24.5}, box)
    assert result == "over"
    assert actual == 25.0


def test_under_hits():
    box = _box(pts=18)
    actual, result = compute_outcome({"market": "pts", "line": 24.5}, box)
    assert result == "under"
    assert actual == 18.0


def test_push_exact():
    box = _box(pts=25)
    actual, result = compute_outcome({"market": "pts", "line": 25.0}, box)
    assert result == "push"
    assert actual == 25.0


def test_void_no_box_score():
    actual, result = compute_outcome({"market": "pts", "line": 24.5}, None)
    assert result == "void"
    assert actual is None


def test_void_zero_minutes():
    box = _box(minutes=0.0)
    actual, result = compute_outcome({"market": "pts", "line": 24.5}, box)
    assert result == "void"
    assert actual is None


def test_void_none_minutes():
    box = _box()
    box["minutes"] = None
    actual, result = compute_outcome({"market": "pts", "line": 24.5}, box)
    assert result == "void"


# ── All single-stat markets ───────────────────────────────────────────────────

@pytest.mark.parametrize("market,box_key,value,line,expected_result", [
    ("pts",         "points",    30, 24.5, "over"),
    ("reb",         "rebounds",  4,  5.5,  "under"),
    ("ast",         "assists",   8,  7.5,  "over"),
    ("stl",         "steals",    1,  1.5,  "under"),
    ("blk",         "blocks",    2,  1.5,  "over"),
    ("threes_made", "fg3_made",  3,  2.5,  "over"),
    ("fg_made",     "fg_made",   6,  6.5,  "under"),
    ("ft_made",     "ft_made",   4,  4.0,  "push"),
])
def test_single_stat_markets(market, box_key, value, line, expected_result):
    base = _box()
    base[box_key] = value
    _, result = compute_outcome({"market": market, "line": line}, base)
    assert result == expected_result


# ── Compound markets ──────────────────────────────────────────────────────────

def test_pra_over():
    # pts=20, reb=5, ast=4 → total=29
    box = _box(pts=20, reb=5, ast=4)
    actual, result = compute_outcome({"market": "pra", "line": 28.5}, box)
    assert result == "over"
    assert actual == 29.0


def test_pr_under():
    # pts=20, reb=5 → total=25
    box = _box(pts=20, reb=5)
    actual, result = compute_outcome({"market": "pr", "line": 26.5}, box)
    assert result == "under"
    assert actual == 25.0


def test_pa_over():
    # pts=20, ast=8 → total=28
    box = _box(pts=20, ast=8)
    actual, result = compute_outcome({"market": "pa", "line": 27.5}, box)
    assert result == "over"
    assert actual == 28.0


def test_ra_push():
    # reb=5, ast=5 → total=10
    box = _box(reb=5, ast=5)
    actual, result = compute_outcome({"market": "ra", "line": 10.0}, box)
    assert result == "push"
    assert actual == 10.0


# ── resolve_result convenience wrapper ───────────────────────────────────────

def test_resolve_result_wrapper():
    box = _box(pts=30)
    actual, result = resolve_result("pts", 24.5, box)
    assert result == "over"
    assert actual == 30.0


# ── Error cases ───────────────────────────────────────────────────────────────

def test_unknown_market_raises():
    with pytest.raises(ValueError, match="Unknown market"):
        compute_outcome({"market": "rushing_yards", "line": 50.0}, _box())


def test_missing_column_voids():
    """If a required column is None in the box score, result should be void."""
    box = _box()
    box["points"] = None
    _, result = compute_outcome({"market": "pts", "line": 20.0}, box)
    assert result == "void"


def test_pra_missing_column_voids():
    box = _box()
    box["assists"] = None
    _, result = compute_outcome({"market": "pra", "line": 25.0}, box)
    assert result == "void"
