"""test_L04_gpp.py — Tests for L04_gpp_optimizer.py (BUILD L4).

Run with:
    conda run -n basketball_ai python -m pytest scripts/execute_loop/tests/test_L04_gpp.py -v

All tests use synthetic slate data — no network calls, no model files required.
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_TESTS_DIR   = Path(__file__).resolve().parent
_EL_DIR      = _TESTS_DIR.parent
_PROJECT_DIR = _EL_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

from scripts.execute_loop.L04_gpp_optimizer import (
    DEFAULT_PAYOUT,
    _SMALL_FIELD_PAYOUT,
    compute_leverage_score,
    optimize_gpp,
    simulate_contest_finish,
)

# ---------------------------------------------------------------------------
# Minimal FPTSDistribution stub (avoids L02 model dependency in tests)
# ---------------------------------------------------------------------------
@dataclass
class _FDist:
    mean: float = 25.0
    std: float = 5.0
    q10: float = 15.0
    q50: float = 25.0
    q90: float = 35.0
    samples: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))


# ---------------------------------------------------------------------------
# Minimal SlateContest stub
# ---------------------------------------------------------------------------
@dataclass
class _Slate:
    salary_cap: int = 50_000
    roster_slots: List[str] = field(
        default_factory=lambda: ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]
    )
    players: List[dict] = field(default_factory=list)
    contest_id: str = "test_slate"
    book: str = "dk"
    sport: str = "NBA"
    slate_type: str = "classic"
    lock_time: str = ""
    game_ids: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_player(
    name: str,
    team: str,
    position: str,
    salary: int,
    game_id: str = "g1",
) -> dict:
    return {
        "name": name,
        "team": team,
        "position": position,
        "salary": salary,
        "status": "",
        "player_id": name.lower().replace(" ", "_"),
        "game_id": game_id,
    }


def _make_slate_and_fpts(
    seed: int = 0,
    n_players: int = 16,
) -> tuple:
    """Build a minimal synthetic slate with two games (4 teams, 4 players/team)."""
    rng = np.random.default_rng(seed)

    # Two games, 4 teams, 4 players each
    rosters = [
        # game g1: LAL vs GSW
        ("LeBron James",    "LAL", "SF",  8800, "g1"),
        ("Anthony Davis",   "LAL", "PF",  9200, "g1"),
        ("Austin Reaves",   "LAL", "SG",  5400, "g1"),
        ("D'Angelo Russell","LAL", "PG",  6200, "g1"),
        ("Stephen Curry",   "GSW", "PG",  9600, "g1"),
        ("Klay Thompson",   "GSW", "SG",  6800, "g1"),
        ("Draymond Green",  "GSW", "PF",  6000, "g1"),
        ("Andrew Wiggins",  "GSW", "SF",  5800, "g1"),
        # game g2: BOS vs MIA
        ("Jayson Tatum",    "BOS", "SF",  9400, "g2"),
        ("Jaylen Brown",    "BOS", "SG",  8200, "g2"),
        ("Al Horford",      "BOS", "C",   5600, "g2"),
        ("Marcus Smart",    "BOS", "PG",  5200, "g2"),
        ("Jimmy Butler",    "MIA", "SF",  8600, "g2"),
        ("Bam Adebayo",     "MIA", "C",   8000, "g2"),
        ("Kyle Lowry",      "MIA", "PG",  5000, "g2"),
        ("Tyler Herro",     "MIA", "SG",  7400, "g2"),
    ]
    # Pad if fewer than n_players
    players = [_make_player(*r) for r in rosters[:n_players]]

    # Give each player a synthetic FPTS distribution
    fpts_data: Dict[str, _FDist] = {}
    ownership: Dict[str, float] = {}
    for p in players:
        mu = rng.uniform(18.0, 45.0)
        sigma = rng.uniform(4.0, 8.0)
        samples = rng.normal(mu, sigma, size=2000).clip(0)
        fpts_data[p["name"]] = _FDist(
            mean=float(mu), std=float(sigma),
            q10=float(np.quantile(samples, 0.10)),
            q50=float(np.quantile(samples, 0.50)),
            q90=float(np.quantile(samples, 0.90)),
            samples=samples,
        )
        ownership[p["name"]] = float(rng.uniform(0.03, 0.35))

    slate = _Slate(players=players, salary_cap=50_000)
    return slate, fpts_data, ownership


# ---------------------------------------------------------------------------
# TEST 1 — optimize_gpp returns 20 lineups with mixed stacking patterns
# ---------------------------------------------------------------------------
def test_optimize_gpp_returns_20_lineups_mixed_stacks():
    """optimize_gpp should return exactly 20 lineups with ≥2 distinct team-stack patterns."""
    slate, fpts_data, ownership = _make_slate_and_fpts(seed=1)
    lineups = optimize_gpp(
        slate, fpts_data, ownership=ownership,
        n_lineups=20, field_size=500, seed=7,
    )
    assert len(lineups) == 20, f"Expected 20 lineups, got {len(lineups)}"

    # Identify stacking patterns: frozenset of team combos per lineup
    patterns = set()
    for lu in lineups:
        teams = tuple(sorted(Counter(p.get("team", "") for p in lu.players).items()))
        patterns.add(teams)

    assert len(patterns) >= 2, (
        f"Expected ≥2 distinct stacking patterns, found {len(patterns)}: {patterns}"
    )


# ---------------------------------------------------------------------------
# TEST 2 — ownership=None uses uniform 0.05 fallback without error
# ---------------------------------------------------------------------------
def test_optimize_gpp_no_ownership_fallback():
    """Passing ownership=None must succeed and use 0.05 uniform fallback."""
    slate, fpts_data, _ = _make_slate_and_fpts(seed=2)
    lineups = optimize_gpp(
        slate, fpts_data, ownership=None,
        n_lineups=5, field_size=200, seed=9,
    )
    assert len(lineups) == 5
    # All projected_fpts must be positive (sanity)
    for lu in lineups:
        assert lu.projected_fpts > 0.0, f"projected_fpts={lu.projected_fpts} should be >0"


# ---------------------------------------------------------------------------
# TEST 3 — compute_leverage_score: contrarian high-proj > chalk high-proj
# ---------------------------------------------------------------------------
def test_compute_leverage_score_contrarian_beats_chalk():
    """A contrarian player (low ownership) should outscore a chalk player at same proj/salary."""
    # Same projection and salary; contrarian has 5% ownership vs chalk 40%
    contrarian = compute_leverage_score(
        player_ownership=0.05,
        player_proj_fpts=40.0,
        salary=8000,
    )
    chalk = compute_leverage_score(
        player_ownership=0.40,
        player_proj_fpts=40.0,
        salary=8000,
    )
    assert contrarian > chalk, (
        f"Contrarian leverage {contrarian:.4f} should exceed chalk {chalk:.4f}"
    )


# ---------------------------------------------------------------------------
# TEST 4 — ≥60% (12/20) lineups have 2+ same-team players
# ---------------------------------------------------------------------------
def test_stack_requirement_60pct():
    """At least 60% of returned lineups must have ≥2 players from the same team."""
    slate, fpts_data, ownership = _make_slate_and_fpts(seed=3)
    lineups = optimize_gpp(
        slate, fpts_data, ownership=ownership,
        n_lineups=20, field_size=300, seed=11,
    )

    def _has_stack(lu) -> bool:
        teams = Counter(p.get("team", "") for p in lu.players)
        return max(teams.values(), default=0) >= 2

    stacked = sum(1 for lu in lineups if _has_stack(lu))
    pct = stacked / max(len(lineups), 1)
    assert pct >= 0.60, (
        f"Expected ≥60% stacked lineups, got {stacked}/{len(lineups)} = {pct:.1%}"
    )


# ---------------------------------------------------------------------------
# TEST 5 — field_size=50 uses small-field payout curve
# ---------------------------------------------------------------------------
def test_small_field_payout_curve():
    """With field_size<100, the payout curve should be the small-field variant."""
    from scripts.execute_loop.L04_gpp_optimizer import _select_payout, _SMALL_FIELD_PAYOUT, DEFAULT_PAYOUT

    small = _select_payout(50)
    large = _select_payout(100)

    assert small == _SMALL_FIELD_PAYOUT, f"Small-field payout mismatch: {small}"
    assert large == DEFAULT_PAYOUT, f"Large-field payout mismatch: {large}"

    # The top-finish payout in small-field curve should be 3× entry
    top_small_multiplier = small[0][1]
    assert top_small_multiplier == 3.0, f"Expected 3.0x top payout, got {top_small_multiplier}"


# ---------------------------------------------------------------------------
# TEST 6 — Planted dominant lineup in small field → E[ROI] > 1.0
# ---------------------------------------------------------------------------
def test_simulate_contest_finish_dominant_lineup():
    """A lineup that always scores 200 FPTS vs a weak field should have E[ROI] > 1.0."""
    from scripts.execute_loop.L04_gpp_optimizer import Lineup

    rng = np.random.default_rng(42)
    n_sims = 2000
    field_size = 50  # small field → top-3-only payout = 3×

    # Dominant lineup: fixed 200 FPTS every sim
    dominant_player = {
        "name": "Super Player",
        "team": "AAA",
        "salary": 5000,
        "position": "PG",
        "proj_fpts": 200.0,
        "samples": np.full(2000, 200.0),
    }
    dominant_lineup = Lineup(
        players=[dominant_player],
        total_salary=5000,
        projected_fpts=200.0,
    )

    # Weak field: lineups averaging ~50 FPTS
    field_lineups = []
    for i in range(field_size):
        p = {
            "name": f"Weak{i}",
            "team": "BBB",
            "salary": 5000,
            "position": "PG",
            "proj_fpts": 50.0,
            "samples": rng.normal(50.0, 5.0, size=2000).clip(0),
        }
        field_lineups.append([p])

    payout_curve = _SMALL_FIELD_PAYOUT
    roi = simulate_contest_finish(
        dominant_lineup,
        field_lineups,
        payout_curve=payout_curve,
        n_sims=n_sims,
        seed=42,
        _pool_players=[dominant_player],
    )
    assert roi > 1.0, f"Dominant lineup should have E[ROI] > 1.0, got {roi:.4f}"


# ---------------------------------------------------------------------------
# TEST 7 — Banned players never appear in any output lineup
# ---------------------------------------------------------------------------
def test_banned_players_never_appear():
    """Players listed in banned set must not appear in any returned lineup."""
    slate, fpts_data, ownership = _make_slate_and_fpts(seed=4)
    banned = {"Stephen Curry", "Jayson Tatum", "LeBron James"}

    lineups = optimize_gpp(
        slate, fpts_data, ownership=ownership,
        n_lineups=10, field_size=200,
        banned=banned, seed=13,
    )

    for i, lu in enumerate(lineups):
        for p in lu.players:
            assert p["name"] not in banned, (
                f"Banned player {p['name']!r} appeared in lineup {i + 1}"
            )


# ---------------------------------------------------------------------------
# TEST 8 — Salary cap is never exceeded
# ---------------------------------------------------------------------------
def test_salary_cap_never_exceeded():
    """No lineup's total salary should exceed the slate salary cap."""
    slate, fpts_data, ownership = _make_slate_and_fpts(seed=5)
    lineups = optimize_gpp(
        slate, fpts_data, ownership=ownership,
        n_lineups=10, field_size=200, seed=17,
    )
    for i, lu in enumerate(lineups):
        assert lu.total_salary <= slate.salary_cap, (
            f"Lineup {i+1} exceeds salary cap: {lu.total_salary} > {slate.salary_cap}"
        )


# ---------------------------------------------------------------------------
# TEST 9 — Empty pool raises ValueError
# ---------------------------------------------------------------------------
def test_empty_pool_raises():
    """Banning all players should raise ValueError about pool being too small."""
    slate, fpts_data, ownership = _make_slate_and_fpts(seed=6)
    all_names = {p["name"] for p in slate.players}

    with pytest.raises(ValueError, match="Pool too small"):
        optimize_gpp(
            slate, fpts_data, ownership=ownership,
            n_lineups=1, field_size=50,
            banned=all_names, seed=19,
        )


# ---------------------------------------------------------------------------
# TEST 10 — compute_leverage_score edge cases
# ---------------------------------------------------------------------------
def test_compute_leverage_score_edge_cases():
    """compute_leverage_score should handle zero-salary and zero-ownership gracefully."""
    # Zero salary → clipped to 0.1k
    score_zero_sal = compute_leverage_score(0.10, 30.0, 0)
    assert np.isfinite(score_zero_sal), "Should be finite when salary=0"

    # Zero ownership → clipped to 0.01
    score_zero_own = compute_leverage_score(0.0, 30.0, 8000)
    assert np.isfinite(score_zero_own), "Should be finite when ownership=0"
    assert score_zero_own > 0, "Leverage should be positive"

    # Normal case
    normal = compute_leverage_score(0.15, 40.0, 9000)
    assert normal > 0
