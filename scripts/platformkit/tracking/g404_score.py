"""G404 raw-rating and outcome rails; no rater, decoder, or gate route is called."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

STATES = ("VISIBLE", "ABSENT", "UNKNOWN")


def usable_box(row: Mapping[str, str]) -> bool:
    """Recognize valid geometry without changing the independently recorded state."""
    if row.get("state") != "VISIBLE":
        return False
    try:
        return float(row["box_w"]) > 0.0 and float(row["box_h"]) > 0.0
    except (KeyError, TypeError, ValueError):
        return False


def cohen_kappa(pairs: Iterable[tuple[str, str]]) -> float | None:
    """Return raw three-state kappa, or None for incomplete/undefined input."""
    values = list(pairs)
    if not values or any(left not in STATES or right not in STATES for left, right in values):
        return None
    total = len(values)
    lefts, rights = Counter(left for left, _ in values), Counter(right for _, right in values)
    observed = sum(left == right for left, right in values) / total
    expected = sum(lefts[state] * rights[state] for state in STATES) / (total * total)
    if expected == 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def reliability_pass(round_pairs: Iterable[Iterable[tuple[str, str]]], pooled: Iterable[tuple[str, str]]) -> bool:
    """Enforce every complete n=30 round plus pooled raw kappa at the fixed bar."""
    rounds = [list(pairs) for pairs in round_pairs]
    if len(rounds) != 10 or any(len(pairs) != 30 for pairs in rounds):
        return False
    round_scores = [cohen_kappa(pairs) for pairs in rounds]
    pooled_values = list(pooled)
    pooled_score = cohen_kappa(pooled_values)
    return (len(pooled_values) == 300 and pooled_score is not None and pooled_score >= 0.60
            and all(score is not None and score >= 0.60 for score in round_scores))


def gate_audit_pass(admitted: Iterable[tuple[str, str]], excluded: Iterable[tuple[str, str]]) -> bool:
    """Apply the sealed joint-label audit bars without counting disagreement."""
    admitted_values, excluded_values = list(admitted), list(excluded)
    return (len(admitted_values) == len(excluded_values) == 30
            and sum(pair == ("PLAY", "PLAY") for pair in admitted_values) >= 27
            and sum(pair == ("NONPLAY", "NONPLAY") for pair in excluded_values) >= 24)


def yield_is_complete(planned_keys: set[str], yield_rows: Iterable[Mapping[str, str]]) -> bool:
    """Require one archived result for every planned key, including non-box states."""
    rows = list(yield_rows)
    keys = [row.get("frame_key", "") for row in rows]
    return len(rows) == len(planned_keys) == 300 and set(keys) == planned_keys and len(set(keys)) == len(keys)


def stage_verdict(prerequisites: bool, gate_passed: bool, controls_passed: bool,
                  reliability_ok: bool, usability_ok: bool, yield_complete: bool,
                  audited_unique_boxes: int | None) -> str:
    """Return only the sealed G404 outcome category for a complete later record."""
    if not prerequisites or not yield_complete:
        return "PARTIAL"
    if not gate_passed:
        return "CLOSED AT LIMIT"
    if not controls_passed or not reliability_ok or not usability_ok:
        return "NOT VALIDATED"
    if audited_unique_boxes is None:
        return "PARTIAL"
    return "DONE" if audited_unique_boxes > 120 else "CLOSED AT LIMIT"
