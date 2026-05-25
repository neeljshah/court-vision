"""
L03_cash_optimizer.py — DraftKings Classic Cash-Game Lineup Optimizer (LP-based).

Uses PuLP (CBC) with scipy greedy fallback.

Public API
----------
    Lineup, InfeasibleError
    optimize_cash(slate, fpts_data, n_lineups, max_exposure) -> list[Lineup]
    solve_single_lineup(slate, fpts_dict, banned_players)    -> Lineup
    enforce_diversity(lineups, max_overlap)                  -> list[Lineup]
"""
from __future__ import annotations

import logging
import math
import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import numpy as np

from scripts.execute_loop.L01_slate_ingester import SlateContest
from scripts.execute_loop.L02_fpts_distribution import FPTSDistribution

log = logging.getLogger(__name__)

# DK Classic: 8 slots — PG, SG, SF, PF, C, G(PG/SG), F(SF/PF), UTIL(any)
_DK_SLOTS = ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]

_SLOT_ELIGIBLE: Dict[str, Set[str]] = {
    "PG":   {"PG"},
    "SG":   {"SG"},
    "SF":   {"SF"},
    "PF":   {"PF"},
    "C":    {"C"},
    "G":    {"PG", "SG"},
    "F":    {"SF", "PF"},
    "UTIL": {"PG", "SG", "SF", "PF", "C"},
}

_SALARY_CAP = 50_000
_ROSTER_SIZE = 8


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------
@dataclass
class Lineup:
    players: List[str]        # player_ids, length 8
    total_salary: int
    expected_fpts: float
    std_fpts: float
    positions: Dict[str, str] # player_id -> assigned slot


class InfeasibleError(Exception):
    """Raised when no feasible lineup exists."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _build_fpts_dict(
    fpts_data: List[FPTSDistribution] | Dict[str, FPTSDistribution],
) -> Dict[str, FPTSDistribution]:
    if isinstance(fpts_data, dict):
        return fpts_data
    result: Dict[str, FPTSDistribution] = {}
    for dist in fpts_data:
        key = getattr(dist, "player_id", None) or getattr(dist, "name", None)
        if key:
            result[str(key)] = dist
        else:
            log.warning("FPTSDistribution entry has no player_id or name — skipped")
    return result


def _eligible_players(
    slate: SlateContest,
    fpts_dict: Dict[str, FPTSDistribution],
    banned: Set[str],
) -> List[dict]:
    eligible = []
    for p in slate.players:
        pid = str(p["player_id"])
        if pid in banned:
            continue
        if pid not in fpts_dict:
            warnings.warn(
                f"Player {p['name']!r} (id={pid}) not in fpts_data — excluding",
                stacklevel=4,
            )
            continue
        eligible.append(p)
    return eligible


def _lineup_std(player_ids: List[str], fpts_dict: Dict[str, FPTSDistribution]) -> float:
    variances = [fpts_dict[pid].std ** 2 for pid in player_ids if pid in fpts_dict]
    return float(np.sqrt(sum(variances))) if variances else 0.0


def _build_lineup(
    positions_map: Dict[str, str],
    salary_map: Dict[str, int],
    fpts_dict: Dict[str, FPTSDistribution],
) -> Lineup:
    player_ids = list(positions_map.keys())
    return Lineup(
        players=player_ids,
        total_salary=sum(salary_map[pid] for pid in player_ids),
        expected_fpts=sum(fpts_dict[pid].mean for pid in player_ids),
        std_fpts=_lineup_std(player_ids, fpts_dict),
        positions=positions_map,
    )


# ---------------------------------------------------------------------------
# PuLP solver (primary)
# ---------------------------------------------------------------------------
def _solve_pulp(
    players: List[dict],
    fpts_dict: Dict[str, FPTSDistribution],
    salary_cap: int,
    slots: List[str],
    prev_lineups: List[Lineup],
    max_overlap: int,
) -> Lineup:
    import pulp  # type: ignore

    prob = pulp.LpProblem("dk_cash", pulp.LpMaximize)
    salary_map = {str(p["player_id"]): int(p["salary"]) for p in players}

    # Binary vars: x[pid][slot]
    x: Dict[str, Dict[str, pulp.LpVariable]] = {}
    for p in players:
        pid, pos = str(p["player_id"]), str(p["position"])
        x[pid] = {
            slot: pulp.LpVariable(f"x_{pid}_{slot}", cat="Binary")
            for slot in slots
            if pos in _SLOT_ELIGIBLE.get(slot, set())
        }

    # Objective: maximize expected fpts
    prob += pulp.lpSum(
        fpts_dict[pid].mean * var
        for pid, sd in x.items() for var in sd.values()
    )

    # Each slot filled exactly once
    for slot in slots:
        prob += (
            pulp.lpSum(x[pid][slot] for pid in x if slot in x[pid]) == 1,
            f"slot_{slot}",
        )

    # Each player in ≤1 slot
    for pid, sd in x.items():
        prob += (pulp.lpSum(sd.values()) <= 1, f"player_{pid}")

    # Salary cap
    prob += (
        pulp.lpSum(salary_map[pid] * v for pid, sd in x.items() for v in sd.values())
        <= salary_cap,
        "salary_cap",
    )

    # Diversity vs previous lineups
    for i, prev in enumerate(prev_lineups):
        prev_set = set(prev.players)
        prob += (
            pulp.lpSum(
                v for pid, sd in x.items() if pid in prev_set for v in sd.values()
            )
            <= max_overlap,
            f"diversity_{i}",
        )

    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    if prob.status != 1:
        raise InfeasibleError(
            f"PuLP status={pulp.LpStatus[prob.status]} — "
            f"players={len(players)}, cap={salary_cap}, overlap={max_overlap}"
        )

    positions_map: Dict[str, str] = {
        pid: slot
        for pid, sd in x.items()
        for slot, var in sd.items()
        if pulp.value(var) is not None and pulp.value(var) > 0.5
    }

    if len(positions_map) != _ROSTER_SIZE:
        raise InfeasibleError(f"PuLP returned {len(positions_map)} players != {_ROSTER_SIZE}")

    return _build_lineup(positions_map, salary_map, fpts_dict)


# ---------------------------------------------------------------------------
# scipy greedy fallback
# ---------------------------------------------------------------------------
def _solve_scipy(
    players: List[dict],
    fpts_dict: Dict[str, FPTSDistribution],
    salary_cap: int,
    slots: List[str],
    prev_lineups: List[Lineup],
    max_overlap: int,
) -> Lineup:
    """Greedy slot-filling fallback sorted by mean fpts, respecting cap + diversity."""
    from scipy.optimize import linprog  # noqa: F401 — confirm availability

    salary_map = {str(p["player_id"]): int(p["salary"]) for p in players}
    prev_sets = [set(prev.players) for prev in prev_lineups]
    pool = sorted(players, key=lambda p: fpts_dict[str(p["player_id"])].mean, reverse=True)

    assigned: Dict[str, str] = {}
    salary_used = 0

    for slot in slots:
        pos_ok = _SLOT_ELIGIBLE.get(slot, set())
        best_pid: Optional[str] = None
        best_fpts = -1.0

        for p in pool:
            pid = str(p["player_id"])
            if pid in assigned or str(p["position"]) not in pos_ok:
                continue
            sal = salary_map[pid]
            slots_left = len(slots) - len(assigned) - 1
            if salary_used + sal + slots_left * 3500 > salary_cap:
                continue
            if fpts_dict[pid].mean > best_fpts:
                best_fpts, best_pid = fpts_dict[pid].mean, pid

        if best_pid is None:
            raise InfeasibleError(
                f"scipy greedy: no eligible player for slot {slot!r} "
                f"(players={len(players)}, cap={salary_cap})"
            )
        assigned[best_pid] = slot
        salary_used += salary_map[best_pid]

    # Diversity check
    for ps in prev_sets:
        if sum(1 for pid in assigned if pid in ps) > max_overlap:
            raise InfeasibleError(
                f"scipy greedy: diversity constraint violated (overlap > {max_overlap})"
            )

    return _build_lineup(assigned, salary_map, fpts_dict)


# ---------------------------------------------------------------------------
# Solver dispatch
# ---------------------------------------------------------------------------
def _solve(
    players: List[dict],
    fpts_dict: Dict[str, FPTSDistribution],
    salary_cap: int,
    slots: List[str],
    prev_lineups: List[Lineup],
    max_overlap: int,
) -> Lineup:
    try:
        import pulp  # noqa: F401
        return _solve_pulp(players, fpts_dict, salary_cap, slots, prev_lineups, max_overlap)
    except ImportError:
        log.warning("pulp unavailable — using scipy greedy fallback")
        return _solve_scipy(players, fpts_dict, salary_cap, slots, prev_lineups, max_overlap)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def solve_single_lineup(
    slate: SlateContest,
    fpts_dict: Dict[str, FPTSDistribution],
    banned_players: Optional[Set[str]] = None,
) -> Lineup:
    """Solve one optimal DK Classic lineup. Raises InfeasibleError if unsolvable."""
    banned = set(banned_players) if banned_players else set()
    eligible = _eligible_players(slate, fpts_dict, banned)
    salary_cap = int(getattr(slate, "salary_cap", _SALARY_CAP))
    slots = list(getattr(slate, "roster_slots", _DK_SLOTS))
    if len(slots) != _ROSTER_SIZE:
        slots = list(_DK_SLOTS)
    if len(eligible) < _ROSTER_SIZE:
        raise InfeasibleError(f"Only {len(eligible)} eligible players — need {_ROSTER_SIZE}")
    return _solve(eligible, fpts_dict, salary_cap, slots, [], max_overlap=_ROSTER_SIZE)


def enforce_diversity(lineups: List[Lineup], max_overlap: int = 6) -> List[Lineup]:
    """
    Greedy-filter lineups so every accepted pair shares ≤ max_overlap players.
    Earlier lineups take priority. Returns a (possibly shorter) list.
    """
    accepted: List[Lineup] = []
    for lineup in lineups:
        s = set(lineup.players)
        if all(len(s & set(prev.players)) <= max_overlap for prev in accepted):
            accepted.append(lineup)
    return accepted


def optimize_cash(
    slate: SlateContest,
    fpts_data: List[FPTSDistribution] | Dict[str, FPTSDistribution],
    n_lineups: int = 1,
    max_exposure: float = 0.4,
) -> List[Lineup]:
    """
    Generate n_lineups optimal cash-game lineups with per-player exposure capping.

    Parameters
    ----------
    slate        : SlateContest (DK Classic).
    fpts_data    : {player_id: FPTSDistribution} or list[FPTSDistribution].
    n_lineups    : number of lineups to generate.
    max_exposure : max fraction of lineups a single player may appear in.
                   Raises ValueError if n_lineups > 1 and max_exposure < 1/n_lineups.

    Raises
    ------
    ValueError      if max_exposure is too low for n_lineups > 1.
    InfeasibleError if a lineup cannot be constructed.
    """
    if n_lineups < 1:
        raise ValueError(f"n_lineups must be >= 1, got {n_lineups}")
    if n_lineups > 1 and max_exposure < 1.0 / n_lineups:
        raise ValueError(
            f"max_exposure={max_exposure} < 1/n_lineups={1.0/n_lineups:.4f}"
        )

    fpts_dict = _build_fpts_dict(fpts_data)
    salary_cap = int(getattr(slate, "salary_cap", _SALARY_CAP))
    slots = list(getattr(slate, "roster_slots", _DK_SLOTS))
    if len(slots) != _ROSTER_SIZE:
        slots = list(_DK_SLOTS)

    exposure_limit = math.floor(max_exposure * n_lineups)
    usage: Dict[str, int] = {}
    lineups: List[Lineup] = []

    for i in range(n_lineups):
        banned: Set[str] = {pid for pid, cnt in usage.items() if cnt >= exposure_limit}
        eligible = _eligible_players(slate, fpts_dict, banned)
        if len(eligible) < _ROSTER_SIZE:
            raise InfeasibleError(
                f"Lineup {i+1}/{n_lineups}: {len(eligible)} eligible players "
                f"after exposure bans — need {_ROSTER_SIZE}"
            )
        prev = [] if n_lineups == 1 else lineups
        lineup = _solve(eligible, fpts_dict, salary_cap, slots, prev, max_overlap=6)
        lineups.append(lineup)
        for pid in lineup.players:
            usage[pid] = usage.get(pid, 0) + 1
        log.info("Lineup %d/%d — fpts=%.2f salary=%d", i + 1, n_lineups,
                 lineup.expected_fpts, lineup.total_salary)

    return lineups
