"""
test_L03_cash.py — Tests for L03_cash_optimizer (DK Classic LP optimizer).

Tests:
1. solve_single_lineup returns valid 8-player lineup, salary ≤ 50000, all slots filled
2. optimize_cash with n_lineups=3 returns exactly 3 valid Lineups
3. enforce_diversity: 5 lineups, max_overlap=6 → all pairs share ≤ 6 players
4. InfeasibleError when cheapest valid combo exceeds salary cap
5. expected_fpts ≈ sum of player means (within 1e-6)
6. Player in slate missing from fpts_dict → warnings.warn called, player excluded
7. max_exposure=0.4 with n_lineups=10 → no player appears in >4 lineups
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

import numpy as np
import pytest

# Make sure project root is on path
_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

from scripts.execute_loop.L01_slate_ingester import SlateContest
from scripts.execute_loop.L02_fpts_distribution import FPTSDistribution
from scripts.execute_loop.L03_cash_optimizer import (
    InfeasibleError,
    Lineup,
    enforce_diversity,
    optimize_cash,
    solve_single_lineup,
)

# ---------------------------------------------------------------------------
# Helpers: build synthetic slates / fpts dicts
# ---------------------------------------------------------------------------

_DK_SLOTS = ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]

# DK position eligibility for slot assignment checks
_SLOT_ELIGIBLE = {
    "PG":   {"PG"},
    "SG":   {"SG"},
    "SF":   {"SF"},
    "PF":   {"PF"},
    "C":    {"C"},
    "G":    {"PG", "SG"},
    "F":    {"SF", "PF"},
    "UTIL": {"PG", "SG", "SF", "PF", "C"},
}


def _make_dist(mean: float, std: float = 5.0) -> FPTSDistribution:
    """Build a minimal FPTSDistribution."""
    samples = np.random.normal(mean, std, 1000)
    return FPTSDistribution(
        mean=mean,
        std=std,
        q10=float(np.percentile(samples, 10)),
        q50=float(np.percentile(samples, 50)),
        q90=float(np.percentile(samples, 90)),
        samples=samples,
    )


def _make_slate(players: List[dict], salary_cap: int = 50_000) -> SlateContest:
    return SlateContest(
        contest_id="TEST_001",
        book="dk",
        sport="NBA",
        slate_type="classic",
        salary_cap=salary_cap,
        roster_slots=list(_DK_SLOTS),
        lock_time="2026-05-25T23:00:00+00:00",
        game_ids=["G1", "G2"],
        players=players,
    )


def _make_player(pid: str, name: str, pos: str, salary: int) -> dict:
    return {
        "player_id": pid,
        "name": name,
        "team": "LAL",
        "position": pos,
        "salary": salary,
        "status": "",
    }


def _standard_12_players() -> tuple[SlateContest, Dict[str, FPTSDistribution]]:
    """
    12-player slate with all required positions for a DK Classic lineup.
    Positions cover: PG(2), SG(2), SF(2), PF(2), C(2) + 2 more flex-eligible.
    Salary is affordable under $50k cap.
    """
    players = [
        _make_player("p1",  "Player PG1",  "PG", 7000),
        _make_player("p2",  "Player PG2",  "PG", 6500),
        _make_player("p3",  "Player SG1",  "SG", 6800),
        _make_player("p4",  "Player SG2",  "SG", 6200),
        _make_player("p5",  "Player SF1",  "SF", 7200),
        _make_player("p6",  "Player SF2",  "SF", 5800),
        _make_player("p7",  "Player PF1",  "PF", 6600),
        _make_player("p8",  "Player PF2",  "PF", 5500),
        _make_player("p9",  "Player C1",   "C",  7500),
        _make_player("p10", "Player C2",   "C",  5000),
        _make_player("p11", "Player PG3",  "PG", 4800),
        _make_player("p12", "Player SF3",  "SF", 4900),
    ]
    # Total cheapest 8 = ~$47,800 — well within cap
    means = {
        "p1": 42.0, "p2": 38.5, "p3": 41.0, "p4": 35.0,
        "p5": 44.0, "p6": 30.0, "p7": 39.0, "p8": 28.0,
        "p9": 46.0, "p10": 24.0, "p11": 22.0, "p12": 23.0,
    }
    fpts_dict = {pid: _make_dist(m) for pid, m in means.items()}
    slate = _make_slate(players)
    return slate, fpts_dict


# ---------------------------------------------------------------------------
# Validity helpers
# ---------------------------------------------------------------------------

def _assert_lineup_valid(lineup: Lineup, slate: SlateContest) -> None:
    """Assert all structural invariants of a Lineup."""
    assert len(lineup.players) == 8, f"Expected 8 players, got {len(lineup.players)}"
    assert len(set(lineup.players)) == 8, "Duplicate players in lineup"
    assert lineup.total_salary <= slate.salary_cap, (
        f"Salary {lineup.total_salary} > cap {slate.salary_cap}"
    )
    assert lineup.total_salary > 0
    assert lineup.expected_fpts > 0.0
    assert lineup.std_fpts >= 0.0

    # All 8 DK slots must be assigned
    assigned_slots = set(lineup.positions.values())
    assert assigned_slots == set(_DK_SLOTS), (
        f"Slots assigned: {assigned_slots}, expected: {set(_DK_SLOTS)}"
    )

    # Each player assigned to a slot compatible with their position
    player_pos = {
        str(p["player_id"]): str(p["position"])
        for p in slate.players
    }
    for pid, slot in lineup.positions.items():
        pos = player_pos.get(pid)
        assert pos in _SLOT_ELIGIBLE.get(slot, set()), (
            f"Player {pid} (pos={pos}) assigned to incompatible slot {slot}"
        )


# ---------------------------------------------------------------------------
# Test 1: solve_single_lineup basic validity
# ---------------------------------------------------------------------------
class TestSolveSingleLineup:
    def test_valid_lineup_structure(self):
        slate, fpts_dict = _standard_12_players()
        lineup = solve_single_lineup(slate, fpts_dict)

        _assert_lineup_valid(lineup, slate)

    def test_salary_within_cap(self):
        slate, fpts_dict = _standard_12_players()
        lineup = solve_single_lineup(slate, fpts_dict)
        assert lineup.total_salary <= 50_000

    def test_all_slots_filled(self):
        slate, fpts_dict = _standard_12_players()
        lineup = solve_single_lineup(slate, fpts_dict)
        assert set(lineup.positions.values()) == set(_DK_SLOTS)

    def test_banned_players_excluded(self):
        slate, fpts_dict = _standard_12_players()
        # Ban best players; optimizer should still find a valid lineup
        lineup = solve_single_lineup(slate, fpts_dict, banned_players={"p9", "p5"})
        assert "p9" not in lineup.players
        assert "p5" not in lineup.players
        _assert_lineup_valid(lineup, slate)


# ---------------------------------------------------------------------------
# Larger slate for multi-lineup tests (20 players, enough depth)
# ---------------------------------------------------------------------------
def _standard_20_players() -> tuple[SlateContest, Dict[str, FPTSDistribution]]:
    """
    20-player slate to support generating multiple lineups without hitting
    exposure limits with a reasonable max_exposure.
    """
    position_cycle = ["PG", "SG", "SF", "PF", "C"] * 4
    players = []
    fpts_dict: Dict[str, FPTSDistribution] = {}
    for i in range(20):
        pid = f"q{i+1}"
        pos = position_cycle[i]
        salary = 4500 + (i % 10) * 300   # range 4500–7200
        players.append(_make_player(pid, f"Player {pos}{i}", pos, salary))
        fpts_dict[pid] = _make_dist(22.0 + (i % 8) * 2.5)

    slate = _make_slate(players, salary_cap=50_000)
    return slate, fpts_dict


# ---------------------------------------------------------------------------
# Test 2: optimize_cash returns exactly n_lineups
# ---------------------------------------------------------------------------
class TestOptimizeCash:
    def test_returns_n_lineups(self):
        # Use max_exposure=1.0 so no player is ever banned; slate has 20 players,
        # more than enough for 3 lineups with diversity constraints.
        slate, fpts_dict = _standard_20_players()
        lineups = optimize_cash(slate, fpts_dict, n_lineups=3, max_exposure=1.0)
        assert len(lineups) == 3

    def test_all_lineups_valid(self):
        slate, fpts_dict = _standard_20_players()
        lineups = optimize_cash(slate, fpts_dict, n_lineups=3, max_exposure=1.0)
        for lineup in lineups:
            _assert_lineup_valid(lineup, slate)

    def test_single_lineup_fast_path(self):
        slate, fpts_dict = _standard_12_players()
        lineups = optimize_cash(slate, fpts_dict, n_lineups=1)
        assert len(lineups) == 1
        _assert_lineup_valid(lineups[0], slate)

    def test_invalid_max_exposure_raises(self):
        slate, fpts_dict = _standard_12_players()
        with pytest.raises(ValueError, match="max_exposure"):
            optimize_cash(slate, fpts_dict, n_lineups=5, max_exposure=0.1)


# ---------------------------------------------------------------------------
# Test 3: enforce_diversity
# ---------------------------------------------------------------------------
class TestEnforceDiversity:
    def _make_lineup(self, players: List[str]) -> Lineup:
        return Lineup(
            players=players,
            total_salary=45_000,
            expected_fpts=300.0,
            std_fpts=15.0,
            positions={p: "PG" for p in players},
        )

    def test_all_pairs_within_max_overlap(self):
        """5 lineups with varied composition; after enforce_diversity max overlap ≤ 6."""
        # Build 5 lineups with 8 players each — deliberately overlapping
        base = [f"p{i}" for i in range(1, 9)]     # p1-p8
        pool = [f"p{i}" for i in range(1, 21)]    # p1-p20

        lineups = [
            self._make_lineup(base),                        # p1-p8
            self._make_lineup(pool[0:8]),                   # p1-p8 (same → will be filtered)
            self._make_lineup(pool[2:10]),                  # p3-p10
            self._make_lineup(pool[4:12]),                  # p5-p12
            self._make_lineup(pool[10:18]),                 # p11-p18
        ]
        result = enforce_diversity(lineups, max_overlap=6)

        # Verify all accepted pairs satisfy constraint
        from itertools import combinations
        for a, b in combinations(result, 2):
            overlap = len(set(a.players) & set(b.players))
            assert overlap <= 6, f"Pair overlap={overlap} > 6"

    def test_identical_lineups_filtered(self):
        players = [f"p{i}" for i in range(1, 9)]
        l1 = self._make_lineup(players)
        l2 = self._make_lineup(players)  # identical → should be filtered
        result = enforce_diversity([l1, l2], max_overlap=6)
        assert len(result) == 1

    def test_no_overlap_lineups_all_accepted(self):
        # Two lineups with zero overlap
        l1 = self._make_lineup([f"p{i}" for i in range(1, 9)])
        l2 = self._make_lineup([f"p{i}" for i in range(9, 17)])
        result = enforce_diversity([l1, l2], max_overlap=6)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Test 4: InfeasibleError when salary too tight
# ---------------------------------------------------------------------------
class TestInfeasible:
    def test_infeasible_when_cap_too_low(self):
        """Set salary cap extremely low so no 8-player combo can fit."""
        slate, fpts_dict = _standard_12_players()
        # Override salary cap to $1 — impossible
        tight_slate = SlateContest(
            contest_id="TIGHT",
            book="dk",
            sport="NBA",
            slate_type="classic",
            salary_cap=1,
            roster_slots=list(_DK_SLOTS),
            lock_time="2026-05-25T23:00:00+00:00",
            game_ids=[],
            players=slate.players,
        )
        with pytest.raises(InfeasibleError):
            solve_single_lineup(tight_slate, fpts_dict)


# ---------------------------------------------------------------------------
# Test 5: expected_fpts == sum of player means (within 1e-6)
# ---------------------------------------------------------------------------
class TestExpectedFptsAccuracy:
    def test_expected_fpts_equals_sum_of_means(self):
        slate, fpts_dict = _standard_12_players()
        lineup = solve_single_lineup(slate, fpts_dict)

        sum_means = sum(fpts_dict[pid].mean for pid in lineup.players)
        assert abs(lineup.expected_fpts - sum_means) < 1e-6, (
            f"expected_fpts={lineup.expected_fpts:.8f} != sum_means={sum_means:.8f}"
        )


# ---------------------------------------------------------------------------
# Test 6: Missing player in fpts_dict triggers warning + exclusion
# ---------------------------------------------------------------------------
class TestMissingFptsWarning:
    def test_missing_player_warns_and_excludes(self):
        slate, fpts_dict = _standard_12_players()
        # Remove p1 from fpts_dict — it should warn and be excluded
        partial_fpts = {k: v for k, v in fpts_dict.items() if k != "p1"}

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            lineup = solve_single_lineup(slate, partial_fpts)

        # Check that at least one warning was issued about the missing player
        warning_messages = [str(w.message) for w in caught]
        assert any("p1" in msg or "Player PG1" in msg for msg in warning_messages), (
            f"Expected warning about p1. Got: {warning_messages}"
        )

        # Player p1 must not appear in the solved lineup
        assert "p1" not in lineup.players


# ---------------------------------------------------------------------------
# Test 7: max_exposure=0.4, n_lineups=10 → no player in >4 lineups
# ---------------------------------------------------------------------------
class TestExposureCap:
    def _make_large_slate(self) -> tuple[SlateContest, Dict[str, FPTSDistribution]]:
        """30-player slate with enough depth to spread exposure."""
        # 6 PG, 6 SG, 5 SF, 5 PF, 4 C, 4 extra PG/SF for flex
        positions = (
            ["PG"] * 6 + ["SG"] * 6 + ["SF"] * 6 + ["PF"] * 5 + ["C"] * 5
        )
        players = []
        fpts_dict = {}
        for i, pos in enumerate(positions):
            pid = f"ep{i+1}"
            salary = 4500 + (i % 7) * 300   # stagger salaries 4500-6300
            players.append(_make_player(pid, f"Player {pos}{i}", pos, salary))
            fpts_dict[pid] = _make_dist(25.0 + (i % 5) * 2.0)

        slate = _make_slate(players, salary_cap=50_000)
        return slate, fpts_dict

    def test_max_exposure_respected(self):
        slate, fpts_dict = self._make_large_slate()
        lineups = optimize_cash(slate, fpts_dict, n_lineups=10, max_exposure=0.4)

        assert len(lineups) == 10

        # Count usage per player
        usage: Dict[str, int] = {}
        for lu in lineups:
            for pid in lu.players:
                usage[pid] = usage.get(pid, 0) + 1

        max_allowed = int(0.4 * 10)  # floor(4.0) = 4
        for pid, cnt in usage.items():
            assert cnt <= max_allowed, (
                f"Player {pid} appeared in {cnt} lineups (max allowed={max_allowed})"
            )

    def test_max_exposure_too_low_raises(self):
        slate, fpts_dict = self._make_large_slate()
        with pytest.raises(ValueError):
            # 0.05 < 1/10 = 0.1 → invalid
            optimize_cash(slate, fpts_dict, n_lineups=10, max_exposure=0.05)
