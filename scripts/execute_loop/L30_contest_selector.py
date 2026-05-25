"""
L30_contest_selector.py — DFS contest scoring, ranking, and budget allocation.

Scores each contest using a model edge + field-quality framework, routes budget
toward cash vs GPP by edge tier, and sizes entry counts per Kelly-inspired logic.

Public API
----------
    ContestEV                  dataclass
    score_contest(contest, model_edge_pct, field_quality) -> ContestEV
    rank_contests(contests, budget, model_edge_pct, field_quality) -> list[ContestEV]
    recommend_entry_split(budget, ranked, max_pct_per_contest) -> dict
"""
from __future__ import annotations

import logging
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_RAKE_PCT = 0.12       # assumed when payout_curve is absent
_DEFAULT_FIELD_SIZE = 10_000   # worst-case GPP when field_size missing

# Contest-type inference regexes (evaluated in order)
_TYPE_PATTERNS: List[tuple[str, str]] = [
    (r"(?i)double[- ]?up|50/50|cash", "cash"),
    (r"(?i)satellite|qualifier|ticket", "satellite"),
    (r"(?i)tournament|gpp|millionaire|maker", "gpp"),
]


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ContestEV:
    contest_id: str
    book: str                  # "DK" | "FD"
    name: str
    entry_fee: float
    field_size: int
    total_payout: float
    contest_type: str          # "cash" | "gpp" | "satellite"
    expected_roi: float        # decimal — 0.08 = +8%
    recommended_lineup_count: int
    leverage_score: float      # 0..1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _infer_contest_type(name: str, field_size: int) -> str:
    """Infer contest type from name first, then fall back to field_size heuristic."""
    for pattern, ctype in _TYPE_PATTERNS:
        if re.search(pattern, name):
            return ctype
    return "cash" if field_size <= 20 else "gpp"


def _compute_rake(contest: dict) -> float:
    """
    Return rake as a decimal fraction.

    If payout_curve is present: rake = (pool - payouts) / pool.
    Otherwise: _DEFAULT_RAKE_PCT.
    """
    entry_fee: float = float(contest.get("entry_fee", 0) or 0)
    field_size: int = int(contest.get("field_size", contest.get("max_entrants", _DEFAULT_FIELD_SIZE)) or _DEFAULT_FIELD_SIZE)
    payout_curve: Optional[List[float]] = contest.get("payout_curve")

    if not payout_curve or not entry_fee or not field_size:
        log.debug("payout_curve missing for contest %s — using default rake %.2f",
                  contest.get("contest_id", "?"), _DEFAULT_RAKE_PCT)
        return _DEFAULT_RAKE_PCT

    pool = entry_fee * field_size
    payouts = sum(payout_curve)
    if pool <= 0:
        return _DEFAULT_RAKE_PCT

    rake_pct = (pool - payouts) / pool
    log.debug("contest %s computed rake=%.4f (pool=%.2f payouts=%.2f)",
              contest.get("contest_id", "?"), rake_pct, pool, payouts)
    return rake_pct


def _compute_leverage_score(field_size: int) -> float:
    """leverage_score = max(0, min(1, sqrt(field_size / 1000)))."""
    return max(0.0, min(1.0, math.sqrt(field_size / 1000.0)))


def _expected_roi_cash(edge: float, field_quality: float, rake_pct: float) -> float:
    """Cash E[ROI] = (edge / sqrt(field_quality)) * 1.8 - rake_pct."""
    denominator = math.sqrt(max(field_quality, 1e-9))
    return (edge / denominator) * 1.8 - rake_pct


def _expected_roi_gpp(edge: float, field_size: int, leverage_score: float, rake_pct: float) -> float:
    """GPP E[ROI] = (edge^1.5) * (1 / field_size^0.3) * (1 + leverage_score) - rake_pct."""
    if field_size <= 0:
        field_size = _DEFAULT_FIELD_SIZE
    leverage_factor = 1.0 + leverage_score
    return (edge ** 1.5) * (1.0 / (field_size ** 0.3)) * leverage_factor - rake_pct


def _recommended_lineup_count(contest_type: str, entry_fee: float, budget: float) -> int:
    """Lineup count recommendation per contest type."""
    if contest_type == "cash":
        return 1
    if contest_type == "satellite":
        return 0
    # GPP: min(20, max(1, int(budget * 0.15 / entry_fee)))
    if entry_fee <= 0:
        return 1
    return min(20, max(1, int(budget * 0.15 / entry_fee)))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_contest(
    contest: dict,
    model_edge_pct: float,
    field_quality: float = 0.5,
    _budget_hint: float = 1000.0,   # internal — used by rank_contests to size GPP lineups
) -> ContestEV:
    """
    Score a single contest and return a ContestEV.

    Args:
        contest:        dict with keys: name, entry_fee, field_size, payout_curve,
                        contest_id, book. Optional: max_entrants (alias for field_size).
        model_edge_pct: model edge expressed as 0..100 (e.g. 5.0 = 5%).
        field_quality:  opponent skill 0..1 (0 = fish pond, 1 = sharps).

    Returns:
        ContestEV with all fields populated.
    """
    edge: float = model_edge_pct / 100.0

    contest_id: str = str(contest.get("contest_id", ""))
    book: str = str(contest.get("book", ""))
    name: str = str(contest.get("name", ""))
    entry_fee: float = float(contest.get("entry_fee", 0) or 0)
    field_size: int = int(
        contest.get("field_size", contest.get("max_entrants", _DEFAULT_FIELD_SIZE)) or _DEFAULT_FIELD_SIZE
    )
    payout_curve: Optional[List[float]] = contest.get("payout_curve")
    total_payout: float = float(sum(payout_curve)) if payout_curve else float(entry_fee * field_size * (1.0 - _DEFAULT_RAKE_PCT))

    contest_type = _infer_contest_type(name, field_size)
    rake_pct = _compute_rake(contest)
    leverage_score = _compute_leverage_score(field_size)

    if contest_type == "cash":
        expected_roi = _expected_roi_cash(edge, field_quality, rake_pct)
    elif contest_type == "gpp":
        expected_roi = _expected_roi_gpp(edge, field_size, leverage_score, rake_pct)
    else:  # satellite
        expected_roi = 0.0

    lineup_count = _recommended_lineup_count(contest_type, entry_fee, _budget_hint)

    log.debug(
        "score_contest id=%s type=%s edge=%.4f rake=%.4f roi=%.4f leverage=%.3f",
        contest_id, contest_type, edge, rake_pct, expected_roi, leverage_score,
    )

    return ContestEV(
        contest_id=contest_id,
        book=book,
        name=name,
        entry_fee=entry_fee,
        field_size=field_size,
        total_payout=total_payout,
        contest_type=contest_type,
        expected_roi=expected_roi,
        recommended_lineup_count=lineup_count,
        leverage_score=leverage_score,
    )


def rank_contests(
    contests: List[dict],
    budget: float,
    model_edge_pct: float = 5.0,
    field_quality: float = 0.5,
) -> List[ContestEV]:
    """
    Score all contests and return sorted by expected_roi DESC.

    ROUTING BY EDGE:
        edge < 5%  → only cash rated positively; GPP ROIs floored to negative
        5–10%      → balanced
        >10%       → GPP-heavy; cash expected_roi scaled down by 0.30

    Args:
        contests:       list of contest dicts (same shape as score_contest input).
        budget:         total available bankroll in dollars (used to size GPP lineups).
        model_edge_pct: 0..100.
        field_quality:  0..1.

    Returns:
        list[ContestEV] sorted by expected_roi descending.
    """
    edge = model_edge_pct / 100.0
    scored: List[ContestEV] = []

    for c in contests:
        ev = score_contest(c, model_edge_pct, field_quality, _budget_hint=budget)

        # Routing adjustment
        if edge < 0.05:
            # Low edge: only cash contests get positive ROI; penalise GPP
            if ev.contest_type == "gpp":
                ev = ContestEV(**{**ev.__dict__, "expected_roi": min(ev.expected_roi, -abs(ev.expected_roi) - 0.001)})
        elif edge > 0.10:
            # High edge: GPP-heavy; scale down cash ROI to ~30% weight
            if ev.contest_type == "cash":
                ev = ContestEV(**{**ev.__dict__, "expected_roi": ev.expected_roi * 0.30})

        scored.append(ev)

    ranked = sorted(scored, key=lambda x: x.expected_roi, reverse=True)
    log.info("rank_contests: scored %d contests, top roi=%.4f",
             len(ranked), ranked[0].expected_roi if ranked else float("nan"))
    return ranked


def recommend_entry_split(
    budget: float,
    ranked: List[ContestEV],
    max_pct_per_contest: float = 0.20,
) -> Dict[str, Dict[str, float]]:
    """
    Allocate budget across contests.

    Rules:
        - Only include contests where expected_roi > 0.
        - Satellite contests are excluded.
        - Per-contest stake capped at max_pct_per_contest * budget.
        - Stake = min(entry_fee * recommended_lineup_count, cap).
        - Return {} if budget < min entry_fee among eligible contests.
        - Return {} if model_edge is effectively 0 (all ROIs <= 0).

    Returns:
        {contest_id: {"entries": int, "stake": float, "expected_profit": float}}
    """
    if budget <= 0:
        return {}

    eligible = [
        ev for ev in ranked
        if ev.expected_roi > 0 and ev.contest_type != "satellite"
    ]

    if not eligible:
        log.info("recommend_entry_split: no eligible contests (edge=0 or all satellite)")
        return {}

    min_fee = min(ev.entry_fee for ev in eligible if ev.entry_fee > 0)
    if budget < min_fee:
        log.info("recommend_entry_split: budget=%.2f < min_fee=%.2f → empty", budget, min_fee)
        return {}

    max_stake = max_pct_per_contest * budget
    result: Dict[str, Dict[str, float]] = {}

    for ev in eligible:
        if ev.entry_fee <= 0:
            continue
        raw_stake = ev.entry_fee * ev.recommended_lineup_count
        stake = min(raw_stake, max_stake)
        entries = max(1, int(stake // ev.entry_fee))
        actual_stake = entries * ev.entry_fee
        expected_profit = actual_stake * ev.expected_roi

        result[ev.contest_id] = {
            "entries": float(entries),
            "stake": round(actual_stake, 2),
            "expected_profit": round(expected_profit, 4),
        }

    log.info(
        "recommend_entry_split: budget=%.2f → %d contests, total_stake=%.2f",
        budget,
        len(result),
        sum(v["stake"] for v in result.values()),
    )
    return result
