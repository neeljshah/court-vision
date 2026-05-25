"""L31_ownership.py — Ownership Projection Model (v1 heuristic).

Estimates DFS contest ownership percentages for players on a slate using
salary value, position ranking, star premium, and late-news boosts.

Public API
----------
    predict_ownership(slate, fpts_data, *, version) -> dict[str, float]
    load_ownership(date) -> dict[str, float] | None
    compute_value_score(salary, projected_fpts) -> float
    heuristic_ownership_v1(slate, fpts_data) -> dict[str, float]
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from scripts.execute_loop.L01_slate_ingester import SlateContest
from scripts.execute_loop.L02_fpts_distribution import FPTSDistribution

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parent.parent
_OWNERSHIP_DIR = _PROJECT_DIR / "data" / "ownership"

# Heuristic constants
_BASE_OWNERSHIP: float = 0.05
_TOP_N_VALUE_BONUS: float = 0.20
_TOP_N_VALUE_K: int = 5          # top-K per position bucket
_STAR_SALARY_THRESHOLD: int = 9000
_STAR_PREMIUM: float = 0.10
_LATE_NEWS_BOOST: float = 0.15
_CAP_OWNERSHIP: float = 0.70
_TARGET_SUM: float = 8.0
_NORM_MAX_ITERS: int = 3


# ---------------------------------------------------------------------------
# Value score
# ---------------------------------------------------------------------------

def compute_value_score(salary: float, projected_fpts: float) -> float:
    """Return FPTS-per-$1000 value score.

    Parameters
    ----------
    salary         : Player salary in dollars.
    projected_fpts : Projected mean FPTS.

    Returns
    -------
    float — FPTS / (salary / 1000).  0.0 if salary <= 0.
    """
    if salary <= 0:
        return 0.0
    return projected_fpts / (salary / 1000.0)


# ---------------------------------------------------------------------------
# Late-news helper (optional L20 integration)
# ---------------------------------------------------------------------------

def _load_late_news_statuses() -> Dict[str, str]:
    """Try to import L20 late-news status changes; return {} on failure."""
    try:
        from scripts.execute_loop.L20_injury_feed import (  # type: ignore[import]
            load_recent_status_changes,
        )
        result = load_recent_status_changes()
        if isinstance(result, dict):
            return result
        log.debug("L20.load_recent_status_changes returned non-dict: %r", type(result))
        return {}
    except (ImportError, AttributeError) as exc:
        log.debug("L20 late-news integration unavailable (%s) — skipping boost.", exc)
        return {}


# ---------------------------------------------------------------------------
# Core heuristic
# ---------------------------------------------------------------------------

def heuristic_ownership_v1(
    slate: SlateContest,
    fpts_data: Dict[str, FPTSDistribution],
) -> Dict[str, float]:
    """Compute v1 heuristic ownership percentages.

    Algorithm
    ---------
    1. Compute value score (FPTS/salary) for each player.
    2. Rank within each position bucket; top-K receive bonus.
    3. Apply star premium for high-salary players.
    4. Apply late-news boost via L20 (optional).
    5. Cap each player at 0.70.
    6. Normalise so Σ ≈ 8.0 (fixed-point, max 3 iters).

    Parameters
    ----------
    slate     : SlateContest with .players list of dicts.
    fpts_data : {player_id: FPTSDistribution} mapping.

    Returns
    -------
    dict {player_id: float in [0.0, 0.70]} with Σ ≈ 8.0.
    """
    if not slate.players:
        return {}

    late_news: Dict[str, str] = _load_late_news_statuses()

    # ------------------------------------------------------------------
    # Step 1 — collect players, compute value scores
    # ------------------------------------------------------------------
    player_ids: List[str] = []
    salaries: Dict[str, float] = {}
    positions: Dict[str, str] = {}
    fpts_means: Dict[str, float] = {}
    value_scores: Dict[str, float] = {}

    for p in slate.players:
        pid = str(p.get("player_id", ""))
        salary = float(p.get("salary", 0) or 0)
        position = str(p.get("position", "UTIL") or "UTIL")

        if salary <= 0:
            log.warning(
                "Player %r (id=%s) has salary=%.0f — skipping (data error).",
                p.get("name", "?"), pid, salary,
            )
            continue

        player_ids.append(pid)
        salaries[pid] = salary
        positions[pid] = position

        dist = fpts_data.get(pid)
        if dist is None:
            log.debug("Player %s not in fpts_data — ownership set to 0.0.", pid)
            fpts_means[pid] = 0.0
        else:
            mean_val = float(dist.mean) if dist.mean is not None else 0.0
            fpts_means[pid] = max(0.0, mean_val)

        value_scores[pid] = compute_value_score(salary, fpts_means[pid])

    if not player_ids:
        return {}

    # ------------------------------------------------------------------
    # Step 2 — position buckets, rank by value descending
    # ------------------------------------------------------------------
    pos_buckets: Dict[str, List[str]] = {}
    for pid in player_ids:
        pos = positions[pid]
        pos_buckets.setdefault(pos, []).append(pid)

    top_value_set: set = set()
    for pos, bucket in pos_buckets.items():
        ranked = sorted(bucket, key=lambda p: value_scores[p], reverse=True)
        for pid in ranked[:_TOP_N_VALUE_K]:
            top_value_set.add(pid)

    # ------------------------------------------------------------------
    # Steps 3-7 — build raw ownership
    # ------------------------------------------------------------------
    raw: Dict[str, float] = {}
    # Track players with no fpts data — pinned to 0.0, excluded from normalisation
    zero_pids: set = set()

    for pid in player_ids:
        dist = fpts_data.get(pid)
        if dist is None:
            # Missing fpts_data → 0.0, no bonuses, excluded from norm redistribution
            raw[pid] = 0.0
            zero_pids.add(pid)
            continue

        ownership = _BASE_OWNERSHIP

        # Top-value bonus
        if pid in top_value_set:
            ownership += _TOP_N_VALUE_BONUS

        # Star premium
        if salaries[pid] > _STAR_SALARY_THRESHOLD:
            ownership += _STAR_PREMIUM

        # Late-news boost (L20 integration)
        if late_news.get(pid) == "confirmed_starter_late":
            ownership += _LATE_NEWS_BOOST

        # Cap before normalisation
        ownership = min(ownership, _CAP_OWNERSHIP)
        raw[pid] = ownership

    # ------------------------------------------------------------------
    # Step 8 — normalise to Σ ≈ 8.0 (fixed-point, max 3 iters)
    # ------------------------------------------------------------------
    raw_sum = sum(raw.values())

    if raw_sum <= 0.0:
        # All-zero (e.g. every player missing from fpts_data)
        return dict(raw)

    # Scale toward target — only players WITH fpts data participate in normalisation.
    # zero_pids (missing fpts_data) are pinned to 0.0 and excluded from scaling.
    normed_pids = [pid for pid in player_ids if pid not in zero_pids]
    target = _TARGET_SUM
    result = dict(raw)

    if normed_pids:
        for _iter in range(_NORM_MAX_ITERS):
            current_sum = sum(result[pid] for pid in normed_pids)
            if current_sum <= 0.0:
                break
            scale = target / current_sum

            # Apply scale + re-cap (only normed_pids)
            residual = 0.0
            uncapped_pids: List[str] = []
            for pid in normed_pids:
                scaled = result[pid] * scale
                if scaled > _CAP_OWNERSHIP:
                    residual += scaled - _CAP_OWNERSHIP
                    result[pid] = _CAP_OWNERSHIP
                else:
                    result[pid] = scaled
                    uncapped_pids.append(pid)

            # Redistribute residual across uncapped players
            if residual > 1e-9 and uncapped_pids:
                per_player = residual / len(uncapped_pids)
                for pid in uncapped_pids:
                    candidate = result[pid] + per_player
                    if candidate > _CAP_OWNERSHIP:
                        result[pid] = _CAP_OWNERSHIP
                    else:
                        result[pid] = candidate

            # Check convergence
            new_sum = sum(result[pid] for pid in normed_pids)
            if abs(new_sum - target) < 0.05:
                break

    # Final clamp: normed players to [0, CAP], zero players stay 0.0
    for pid in normed_pids:
        result[pid] = max(0.0, min(_CAP_OWNERSHIP, result[pid]))
    for pid in zero_pids:
        result[pid] = 0.0

    return result


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _ownership_path(date: str, ownership_dir: Path = _OWNERSHIP_DIR) -> Path:
    """Return path to ownership JSON for a given date."""
    return ownership_dir / f"{date}.json"


def load_ownership(
    date: Optional[str] = None,
    *,
    ownership_dir: Path = _OWNERSHIP_DIR,
) -> Optional[Dict[str, float]]:
    """Load persisted ownership dict for a date.

    Parameters
    ----------
    date : ISO date string (YYYY-MM-DD). Defaults to today.

    Returns
    -------
    dict {player_id: float} or None if file does not exist.
    """
    if date is None:
        date = datetime.date.today().isoformat()
    path = _ownership_path(date, ownership_dir)
    if not path.exists():
        log.debug("Ownership file not found: %s", path)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in data.items()}
    except Exception as exc:
        log.warning("Failed to read ownership file %s: %s", path, exc)
        return None


def _persist_ownership(
    ownership: Dict[str, float],
    date: str,
    ownership_dir: Path = _OWNERSHIP_DIR,
) -> None:
    """Write ownership dict to data/ownership/<date>.json."""
    ownership_dir.mkdir(parents=True, exist_ok=True)
    path = _ownership_path(date, ownership_dir)
    path.write_text(json.dumps(ownership, indent=2), encoding="utf-8")
    log.info("Persisted ownership (%d players) → %s", len(ownership), path)


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------

def predict_ownership(
    slate: SlateContest,
    fpts_data: Dict[str, FPTSDistribution],
    *,
    version: str = "v1",
    _ownership_dir: Path = _OWNERSHIP_DIR,
) -> Dict[str, float]:
    """Predict contest ownership percentages for a slate.

    Parameters
    ----------
    slate     : SlateContest with player pool.
    fpts_data : {player_id: FPTSDistribution} for players on the slate.
    version   : Algorithm version — "v1" (heuristic) or "v2" (stub).

    Returns
    -------
    dict {player_id: float in [0.0, 0.70]} with Σ ≈ 8.0.
    Persists result to data/ownership/<today>.json (empty slate → no write).
    """
    if version == "v1":
        result = heuristic_ownership_v1(slate, fpts_data)
    elif version == "v2":
        raise NotImplementedError("v2 ownership model not yet implemented.")
    else:
        raise ValueError(f"Unknown ownership version {version!r}. Supported: v1, v2.")

    if result:
        date_str = datetime.date.today().isoformat()
        _persist_ownership(result, date_str, _ownership_dir)

    return result
