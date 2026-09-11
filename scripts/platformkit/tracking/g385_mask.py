"""G385 SHADOW-only non-play decisions; the pure API never mutates its input."""

from __future__ import annotations

from typing import Mapping


THRESHOLD = 0.95
UNKNOWN = "UNKNOWN"
KEEP = "KEEP"
MASK = "MASK"


def shadow_decision(row: Mapping[str, object], threshold: float = THRESHOLD) -> dict[str, object]:
    """Return an additive proposed decision, never an operational flag or section mutation."""
    output = dict(row)
    value = row.get("p_nonplay")
    if value is None or row.get("evidence_status") not in (None, "READABLE"):
        return {**output, "shadow_decision": UNKNOWN, "shadow_reason": "absent_or_invalid_evidence"}
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return {**output, "shadow_decision": UNKNOWN, "shadow_reason": "absent_or_invalid_evidence"}
    if not 0.0 <= probability <= 1.0:
        return {**output, "shadow_decision": UNKNOWN, "shadow_reason": "absent_or_invalid_evidence"}
    return {**output, "shadow_decision": MASK if probability >= threshold else KEEP,
            "shadow_reason": "threshold"}


def shadow_decisions(rows: list[Mapping[str, object]], threshold: float = THRESHOLD) -> list[dict[str, object]]:
    """Score a read-only batch for evidence only; no input row is changed."""
    return [shadow_decision(row, threshold) for row in rows]
