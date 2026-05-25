"""L04_gpp_optimizer.py — GPP DFS Lineup Optimizer (BUILD L4).

Monte Carlo simulated-annealing optimizer for GPP (tournament) contests.
Uses ownership leverage, correlated FPTS distributions, and field simulation
to maximize expected ROI against a sampled field.

Public API
----------
    Lineup                       — dataclass (imported from L03 or defined locally)
    optimize_gpp(...)           -> list[Lineup]
    simulate_contest_finish(...) -> float          (E[ROI])
    compute_leverage_score(...)  -> float
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lineup dataclass — GPP-aware.
# Try to import from L03; if L03's Lineup schema is incompatible (it stores
# player_ids as strings, not dicts), define a local GPP variant that mirrors
# the same public contract the spec requests.
# ---------------------------------------------------------------------------
try:
    from scripts.execute_loop.L03_cash_optimizer import Lineup as _L03Lineup  # noqa: F401
    _L03_FIELDS = {f.name for f in _L03Lineup.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    _L03_HAS_GPP_FIELDS = "projected_fpts" in _L03_FIELDS and "meta" in _L03_FIELDS
except (ImportError, AttributeError):
    _L03_HAS_GPP_FIELDS = False

if _L03_HAS_GPP_FIELDS:
    from scripts.execute_loop.L03_cash_optimizer import Lineup  # type: ignore[assignment]
    log.debug("Lineup imported from L03_cash_optimizer (GPP-compatible)")
else:
    # L03 exists but has a cash-game schema; define GPP Lineup locally.
    @dataclass
    class Lineup:  # type: ignore[no-redef]
        """GPP DFS lineup.  Returned by optimize_gpp; mirrors L03 field contract."""
        players: List[dict] = field(default_factory=list)   # enriched player dicts
        total_salary: int = 0
        projected_fpts: float = 0.0
        slots: List[str] = field(default_factory=list)
        contest_id: str = ""
        meta: dict = field(default_factory=dict)

    log.debug("Using local GPP Lineup definition (L03 schema incompatible or absent).")

# ---------------------------------------------------------------------------
# Soft-import L01 / L02 (type hints only; not required at runtime for tests)
# ---------------------------------------------------------------------------
try:
    from scripts.execute_loop.L01_slate_ingester import SlateContest  # noqa: F401
except ImportError:
    SlateContest = None  # type: ignore[assignment,misc]

try:
    from scripts.execute_loop.L02_fpts_distribution import FPTSDistribution  # noqa: F401
except ImportError:
    @dataclass
    class FPTSDistribution:  # type: ignore[no-redef]
        """Minimal FPTSDistribution fallback (L02 unavailable)."""
        mean: float = 0.0
        std: float = 1.0
        q10: float = 0.0
        q50: float = 0.0
        q90: float = 0.0
        samples: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))

# ---------------------------------------------------------------------------
# Constants — DK Classic
# ---------------------------------------------------------------------------
_DK_SALARY_CAP = 50_000
_DK_SLOTS = ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]
_POSITION_COMPAT: Dict[str, Set[str]] = {
    "PG":   {"PG"},
    "SG":   {"SG"},
    "SF":   {"SF"},
    "PF":   {"PF"},
    "C":    {"C"},
    "G":    {"PG", "SG"},
    "F":    {"SF", "PF"},
    "UTIL": {"PG", "SG", "SF", "PF", "C"},
}
_MIN_DISTINCT_GAMES = 2
_MIN_PLAYERS_POOL   = 8
_SA_ITERS           = 500
_SA_T_START         = 1.0
_SA_T_END           = 0.05
_FIELD_SAMPLE_CAP   = 5000
_DEFAULT_OWNERSHIP  = 0.05

# Default GPP payout curve: (finish_pct_threshold, multiplier)
# Finish in top X% → multiplier × entry_fee returned.
DEFAULT_PAYOUT: List[Tuple[float, float]] = [
    (0.005, 5.0),
    (0.05,  1.5),
    (0.20,  0.5),
    (1.0,   0.0),
]
_SMALL_FIELD_PAYOUT: List[Tuple[float, float]] = [
    (0.03, 3.0),
    (1.0,  0.0),
]

# ---------------------------------------------------------------------------
# Leverage score
# ---------------------------------------------------------------------------

def compute_leverage_score(
    player_ownership: float,
    player_proj_fpts: float,
    salary: int,
) -> float:
    """Compute GPP leverage: value-per-dollar divided by ownership.

    High proj FPTS + low ownership + low salary = high leverage.

    Parameters
    ----------
    player_ownership : Projected ownership fraction in (0, 1].
    player_proj_fpts : Projected fantasy points (distribution mean).
    salary           : DK salary in dollars.

    Returns
    -------
    float leverage score (higher = more contrarian-valuable).
    """
    salary_k = max(salary / 1000.0, 0.1)
    ownership = max(player_ownership, 0.01)
    return (player_proj_fpts / salary_k) / ownership


# ---------------------------------------------------------------------------
# Payout helpers
# ---------------------------------------------------------------------------

def _select_payout(field_size: int) -> List[Tuple[float, float]]:
    return _SMALL_FIELD_PAYOUT if field_size < 100 else DEFAULT_PAYOUT


def _lookup_multiplier(
    finish_pct: float,
    payout_curve: List[Tuple[float, float]],
) -> float:
    for threshold, multiplier in payout_curve:
        if finish_pct <= threshold:
            return multiplier
    return 0.0


# ---------------------------------------------------------------------------
# Player pool helpers
# ---------------------------------------------------------------------------

def _build_player_pool(
    slate,
    fpts_data: Dict[str, object],
    ownership: Dict[str, float],
    banned: Optional[Set[str]],
    rng: np.random.Generator,
) -> List[dict]:
    """Attach FPTS distribution + ownership to each slate player.

    Returns enriched player dicts; banned players excluded.
    Logs one warning when ownership data is absent.
    """
    banned = banned or set()
    pool: List[dict] = []
    missing_ownership_warned = False

    for p in slate.players:
        name = p["name"]
        if name in banned:
            continue

        dist = fpts_data.get(name)
        if dist is None:
            dist_samples = rng.normal(20.0, 5.0, size=2000).clip(0)
            dist_mean = 20.0
            dist_std = 5.0
        else:
            dist_mean = float(getattr(dist, "mean", 20.0))
            dist_std  = float(getattr(dist, "std",  5.0))
            raw_samples = getattr(dist, "samples", np.array([]))
            if len(raw_samples) == 0:
                dist_samples = rng.normal(dist_mean, max(dist_std, 0.01), size=2000).clip(0)
            else:
                idx = rng.integers(0, len(raw_samples), size=2000)
                dist_samples = np.asarray(raw_samples)[idx]

        own = ownership.get(name)
        if own is None:
            if not missing_ownership_warned:
                log.warning(
                    "No ownership data for one or more players — "
                    "using uniform %.2f fallback.", _DEFAULT_OWNERSHIP
                )
                missing_ownership_warned = True
            own = _DEFAULT_OWNERSHIP

        lev = compute_leverage_score(own, dist_mean, int(p.get("salary", 5000)))

        pool.append({
            **p,
            "dist_mean":   dist_mean,
            "dist_std":    dist_std,
            "samples":     dist_samples,      # np.ndarray (2000,)
            "ownership":   float(own),
            "leverage":    lev,
            "proj_fpts":   dist_mean,
        })

    if len(pool) < _MIN_PLAYERS_POOL:
        raise ValueError(
            f"Pool too small for valid lineup: {len(pool)} players after filtering "
            f"(need ≥ {_MIN_PLAYERS_POOL}). Check slate players and banned set."
        )
    return pool


# ---------------------------------------------------------------------------
# Position / lineup validity helpers
# ---------------------------------------------------------------------------

def _slot_accepts(slot: str, position: str) -> bool:
    eligible = _POSITION_COMPAT.get(slot, set())
    pos_parts = {p.strip() for p in position.split("/")}
    return bool(eligible & pos_parts)


def _assign_slots(players: List[dict], slots: List[str]) -> Optional[List[dict]]:
    """Greedy slot assignment; returns player-list in slot order or None."""
    remaining = list(players)
    assigned: List[Optional[dict]] = [None] * len(slots)

    for i, slot in enumerate(slots):
        if slot in ("G", "F", "UTIL"):
            continue
        for j, p in enumerate(remaining):
            if _slot_accepts(slot, p["position"]):
                assigned[i] = p
                remaining.pop(j)
                break
        if assigned[i] is None:
            return None

    for i, slot in enumerate(slots):
        if slot not in ("G", "F", "UTIL"):
            continue
        for j, p in enumerate(remaining):
            if _slot_accepts(slot, p["position"]):
                assigned[i] = p
                remaining.pop(j)
                break
        if assigned[i] is None:
            return None

    return assigned if None not in assigned else None


def _try_build_random_lineup(
    pool: List[dict],
    salary_cap: int,
    slots: List[str],
    weights: np.ndarray,
    rng: np.random.Generator,
    max_attempts: int = 200,
) -> Optional[List[dict]]:
    n_need = len(slots)
    probs = weights / weights.sum()

    for _ in range(max_attempts):
        indices = rng.choice(
            len(pool),
            size=min(n_need * 2, len(pool)),
            replace=False,
            p=probs,
        )
        candidates = [pool[i] for i in indices]
        for start in range(max(1, len(candidates) - n_need + 1)):
            sub = candidates[start: start + n_need]
            if len(sub) < n_need:
                continue
            if sum(p["salary"] for p in sub) > salary_cap:
                continue
            ordered = _assign_slots(sub, slots)
            if ordered is None:
                continue
            games = {p.get("game_id", p.get("team", "")) for p in ordered}
            if len(games) < _MIN_DISTINCT_GAMES:
                continue
            return ordered
    return None


# ---------------------------------------------------------------------------
# Field generation
# ---------------------------------------------------------------------------

def _generate_field(
    pool: List[dict],
    salary_cap: int,
    slots: List[str],
    field_size: int,
    rng: np.random.Generator,
) -> List[List[dict]]:
    n_field = min(field_size, _FIELD_SAMPLE_CAP)
    ownership_weights = np.array([p["ownership"] for p in pool], dtype=float)

    field_lineups: List[List[dict]] = []
    attempts = 0
    max_total = n_field * 20

    while len(field_lineups) < n_field and attempts < max_total:
        lu = _try_build_random_lineup(pool, salary_cap, slots, ownership_weights, rng)
        attempts += 1
        if lu is not None:
            field_lineups.append(lu)

    if len(field_lineups) < 10:
        log.warning(
            "Field generation produced only %d lineups (target %d). "
            "Slate may be too small.", len(field_lineups), n_field
        )
    return field_lineups


# ---------------------------------------------------------------------------
# FPTS simulation helpers
# ---------------------------------------------------------------------------

def _lineup_fpts_samples(
    players: List[dict],
    rng: np.random.Generator,
    n_sims: int,
) -> np.ndarray:
    """Sum resampled FPTS draws for all players → shape (n_sims,)."""
    total = np.zeros(n_sims, dtype=float)
    for p in players:
        arr = p["samples"]
        idx = rng.integers(0, len(arr), size=n_sims)
        total += arr[idx]
    return total


def _field_fpts_matrix(
    field_lineups: List[List[dict]],
    rng: np.random.Generator,
    n_sims: int,
) -> np.ndarray:
    """Build (n_field, n_sims) matrix of FPTS draws for all field lineups."""
    n_field = len(field_lineups)
    mat = np.zeros((n_field, n_sims), dtype=float)
    for i, lu in enumerate(field_lineups):
        mat[i] = _lineup_fpts_samples(lu, rng, n_sims)
    return mat


# ---------------------------------------------------------------------------
# simulate_contest_finish
# ---------------------------------------------------------------------------

def simulate_contest_finish(
    lineup: "Lineup",
    field_lineups: List,
    payout_curve: Optional[List[Tuple[float, float]]] = None,
    n_sims: int = 2000,
    *,
    seed: int = 0,
    _pool_players: Optional[List[dict]] = None,
) -> float:
    """Simulate E[ROI] for a Lineup against a pre-sampled field.

    Parameters
    ----------
    lineup        : Lineup dataclass (projected_fpts used as fallback mean).
    field_lineups : List of field entries.  Each may be a List[dict] of enriched
                    player dicts (with 'samples' key) or a Lineup dataclass.
    payout_curve  : Payout structure.  Defaults to DEFAULT_PAYOUT.
    n_sims        : Monte Carlo iterations.
    seed          : RNG seed for reproducibility.
    _pool_players : Internal — pre-enriched player dicts for our lineup.

    Returns
    -------
    float  E[ROI] = mean(multiplier − 1) over n_sims.
    """
    rng = np.random.default_rng(seed)
    payout_curve = payout_curve or DEFAULT_PAYOUT
    n_field = max(len(field_lineups), 1)

    # --- Our lineup FPTS samples
    if _pool_players is not None:
        our_fpts = _lineup_fpts_samples(_pool_players, rng, n_sims)
    else:
        proj = float(getattr(lineup, "projected_fpts", 0.0) or 0.0)
        our_fpts = rng.normal(proj, max(proj * 0.15, 1.0), size=n_sims)

    # --- Field FPTS matrix
    if (
        field_lineups
        and isinstance(field_lineups[0], list)
        and field_lineups[0]
        and "samples" in field_lineups[0][0]
    ):
        field_mat = _field_fpts_matrix(field_lineups, rng, n_sims)
    else:
        rows = []
        for fl in field_lineups:
            proj = float(getattr(fl, "projected_fpts", 20.0) or 20.0)
            rows.append(rng.normal(proj, max(proj * 0.15, 1.0), size=n_sims))
        field_mat = np.vstack(rows) if rows else np.zeros((1, n_sims))

    # --- Rank: count how many field lineups we beat in each sim
    beats = np.sum(our_fpts[np.newaxis, :] > field_mat, axis=0)   # (n_sims,)
    finish_pct = 1.0 - (beats / n_field)                           # 0 = top, 1 = bottom

    multipliers = np.vectorize(
        lambda pct: _lookup_multiplier(pct, payout_curve)
    )(finish_pct)

    return float(np.mean(multipliers - 1.0))


# ---------------------------------------------------------------------------
# Stacking utilities
# ---------------------------------------------------------------------------

def _count_stack(players: List[dict]) -> int:
    from collections import Counter
    teams = Counter(p.get("team", "") for p in players)
    return max(teams.values()) if teams else 0


def _has_stack(players: List[dict]) -> bool:
    return _count_stack(players) >= 2


def _swap_for_stack(
    lineup: List[dict],
    pool: List[dict],
    salary_cap: int,
    slots: List[str],
    rng: np.random.Generator,
    attempts: int = 100,
) -> Optional[List[dict]]:
    """Try swapping players to create a ≥2-player team stack."""
    from collections import Counter
    teams = list({p.get("team", "") for p in pool if p.get("team")})
    if len(teams) < 1:
        return None

    for _ in range(attempts):
        target_team = teams[int(rng.integers(0, len(teams)))]
        team_pool = [p for p in pool if p.get("team") == target_team]
        if len(team_pool) < 2:
            continue

        picks = rng.choice(team_pool, size=2, replace=False).tolist()  # type: ignore[arg-type]
        # Replace last 2 players in the lineup
        new_lu = list(lineup[:-2]) + picks
        if sum(p["salary"] for p in new_lu) > salary_cap:
            continue
        ordered = _assign_slots(new_lu, slots)
        if ordered is None:
            continue
        games = {p.get("game_id", p.get("team", "")) for p in ordered}
        if len(games) < _MIN_DISTINCT_GAMES:
            continue
        return ordered
    return None


# ---------------------------------------------------------------------------
# Greedy seed lineup
# ---------------------------------------------------------------------------

def _greedy_seed_lineup(
    pool: List[dict],
    salary_cap: int,
    slots: List[str],
    rng: np.random.Generator,
) -> Optional[List[dict]]:
    """Top-leverage greedy seed."""
    sorted_pool = sorted(pool, key=lambda p: p["leverage"], reverse=True)
    n_top = min(30, len(sorted_pool))

    for _ in range(50):
        lu = _try_build_random_lineup(
            sorted_pool[:n_top], salary_cap, slots,
            np.ones(n_top, dtype=float), rng,
        )
        if lu is not None:
            return lu

    # Fall back to ownership-weighted random
    weights = np.array([p["ownership"] for p in pool], dtype=float)
    return _try_build_random_lineup(pool, salary_cap, slots, weights, rng)


# ---------------------------------------------------------------------------
# Reuse penalty
# ---------------------------------------------------------------------------

def _reuse_penalty(players: List[dict], used_counts: Dict[str, int]) -> float:
    return sum(used_counts.get(p["name"], 0) for p in players) * 0.5


# ---------------------------------------------------------------------------
# Simulated annealing — single lineup
# ---------------------------------------------------------------------------

def _optimize_one_lineup(
    pool: List[dict],
    salary_cap: int,
    slots: List[str],
    field_lineups: List[List[dict]],
    payout_curve: List[Tuple[float, float]],
    n_sims: int,
    rng: np.random.Generator,
    used_counts: Dict[str, int],
    sim_seed_base: int,
) -> Optional[List[dict]]:
    """Simulated annealing search for one high-ROI lineup."""
    current = _greedy_seed_lineup(pool, salary_cap, slots, rng)
    if current is None:
        return None

    ownership_weights = np.array([p["ownership"] for p in pool], dtype=float)

    def _score(lu: List[dict], sim_seed: int) -> float:
        stub = Lineup(
            players=lu,
            total_salary=sum(p["salary"] for p in lu),
            projected_fpts=sum(p["proj_fpts"] for p in lu),
        )
        roi = simulate_contest_finish(
            stub, field_lineups, payout_curve,
            n_sims=n_sims, seed=sim_seed,
            _pool_players=lu,
        )
        return roi - _reuse_penalty(lu, used_counts) * 0.05

    current_score = _score(current, sim_seed_base)

    for step in range(_SA_ITERS):
        T = _SA_T_START * (_SA_T_END / _SA_T_START) ** (step / max(_SA_ITERS - 1, 1))

        swap_idx = int(rng.integers(0, len(current)))
        slot = slots[swap_idx]
        current_names = {x["name"] for x in current}
        eligible = [
            p for p in pool
            if _slot_accepts(slot, p["position"]) and p["name"] not in current_names
        ]
        if not eligible:
            continue

        new_player = eligible[int(rng.integers(0, len(eligible)))]
        proposed = list(current)
        proposed[swap_idx] = new_player

        if sum(p["salary"] for p in proposed) > salary_cap:
            continue
        games = {p.get("game_id", p.get("team", "")) for p in proposed}
        if len(games) < _MIN_DISTINCT_GAMES:
            continue

        proposed_score = _score(proposed, sim_seed_base + step)
        delta = proposed_score - current_score

        if delta > 0 or rng.random() < math.exp(delta / max(T, 1e-9)):
            current = proposed
            current_score = proposed_score

    return current


# ---------------------------------------------------------------------------
# Main optimizer
# ---------------------------------------------------------------------------

def optimize_gpp(
    slate,
    fpts_data: Dict[str, object],
    ownership: Optional[Dict[str, float]] = None,
    n_lineups: int = 20,
    field_size: int = 100_000,
    banned: Optional[Set[str]] = None,
    seed: int = 42,
) -> List["Lineup"]:
    """Build n_lineups optimal GPP lineups via simulated annealing + MC field sim.

    Parameters
    ----------
    slate       : SlateContest (players, salary_cap, roster_slots).
    fpts_data   : Dict mapping player name → FPTSDistribution from L02.
    ownership   : Projected ownership per player (fraction 0–1).
                  None → uniform 0.05 fallback (one warning logged).
    n_lineups   : Number of distinct lineups to return.
    field_size  : GPP field size for payout percentile calculations.
    banned      : Set of player names to exclude entirely.
    seed        : Master RNG seed for reproducibility.

    Returns
    -------
    List[Lineup] of length n_lineups.  ≥60% will contain a ≥2-player stack.

    Raises
    ------
    ValueError  if the post-filter pool is too small to build even one lineup.
    """
    rng = np.random.default_rng(seed)
    ownership = ownership or {}
    banned = banned or set()

    salary_cap = int(getattr(slate, "salary_cap", _DK_SALARY_CAP) or _DK_SALARY_CAP)
    slots = list(getattr(slate, "roster_slots", _DK_SLOTS) or _DK_SLOTS)

    log.info("Game stack (top-game) constraint skipped — no team_totals in slate v1.")

    # 1. Build enriched player pool
    pool = _build_player_pool(slate, fpts_data, ownership, banned, rng)

    # 2. Choose payout curve
    payout_curve = _select_payout(field_size)

    # 3. Pre-sample field
    log.info("Generating field (%d lineups target)...", min(field_size, _FIELD_SAMPLE_CAP))
    field_lineups = _generate_field(pool, salary_cap, slots, field_size, rng)

    if not field_lineups:
        log.warning("Field generation failed — ROI scores will be unconstrained.")

    # 4. Simulated annealing — build n_lineups one at a time
    used_counts: Dict[str, int] = {}
    result_lineups: List[Lineup] = []
    _n_sims_sa = 100  # fast SA evaluations; final scoring uses 500

    for i in range(n_lineups):
        best_lu: Optional[List[dict]] = None
        best_roi = float("-inf")

        for attempt in range(5):
            lu = _optimize_one_lineup(
                pool, salary_cap, slots,
                field_lineups, payout_curve,
                _n_sims_sa, rng, used_counts,
                sim_seed_base=seed + i * 1000 + attempt * 100,
            )
            if lu is None:
                continue
            roi = simulate_contest_finish(
                Lineup(
                    players=lu,
                    total_salary=sum(p["salary"] for p in lu),
                    projected_fpts=sum(p["proj_fpts"] for p in lu),
                ),
                field_lineups, payout_curve,
                n_sims=500, seed=seed + i,
                _pool_players=lu,
            )
            if roi > best_roi:
                best_roi = roi
                best_lu = lu

        if best_lu is None:
            log.warning("Could not build lineup %d/%d — skipping.", i + 1, n_lineups)
            continue

        for p in best_lu:
            used_counts[p["name"]] = used_counts.get(p["name"], 0) + 1

        result_lineups.append(Lineup(
            players=best_lu,
            total_salary=sum(p["salary"] for p in best_lu),
            projected_fpts=sum(p["proj_fpts"] for p in best_lu),
            slots=slots,
            meta={"expected_roi": best_roi, "has_stack": _has_stack(best_lu)},
        ))

    # 5. Enforce ≥60% stacking constraint
    n_stacked = sum(1 for lu in result_lineups if lu.meta.get("has_stack", False))
    target_stacked = math.ceil(0.60 * len(result_lineups))

    if n_stacked < target_stacked:
        log.info(
            "Stack enforcement: %d/%d stacked, target %d — patching.",
            n_stacked, len(result_lineups), target_stacked,
        )
        for i, lu in enumerate(result_lineups):
            if n_stacked >= target_stacked:
                break
            if lu.meta.get("has_stack", False):
                continue
            patched = _swap_for_stack(lu.players, pool, salary_cap, slots, rng)
            if patched is None:
                continue
            result_lineups[i] = Lineup(
                players=patched,
                total_salary=sum(p["salary"] for p in patched),
                projected_fpts=sum(p["proj_fpts"] for p in patched),
                slots=slots,
                meta={
                    "expected_roi": lu.meta.get("expected_roi", 0.0),
                    "has_stack": _has_stack(patched),
                },
            )
            n_stacked += 1

    pct_stacked = (
        sum(1 for lu in result_lineups if lu.meta.get("has_stack", False))
        / max(len(result_lineups), 1)
    )
    log.info(
        "optimize_gpp complete: %d lineups, %.0f%% stacked.",
        len(result_lineups), 100 * pct_stacked,
    )
    return result_lineups
