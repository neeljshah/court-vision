"""Pure trace-control stamps for the proposed G380 producer fields.

This module is test scaffolding only.  The producer integration is deliberately
left in the PROPOSED diff until a human applies and accepts it.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

POSITION_SOURCES = frozenset(
    {"DETECTION", "PREDICTION", "HELD", "CLAMP", "SUBPIXEL", "UNKNOWN"}
)

_BRANCH_LABELS = {
    "fresh_detection": "DETECTION",
    "coast": "PREDICTION",
    "clamp": "CLAMP",
    "subpixel_hold": "SUBPIXEL",
    "id_merge": "PREDICTION",
    "missing_event": "UNKNOWN",
}


def label_for_branch(branch: str) -> str:
    """Return the closed provenance label for one independently traced branch."""
    try:
        return _BRANCH_LABELS[branch]
    except KeyError as exc:
        raise ValueError("unknown provenance branch: %s" % branch) from exc


def stamp_row(row: dict[str, Any], branch: str, source_branch: str,
              matched_event_id: str | None = None) -> dict[str, Any]:
    """Return an additive provenance stamp without changing existing values."""
    stamped = dict(row)
    stamped["position_source"] = label_for_branch(branch)
    stamped["source_branch"] = source_branch
    stamped["matched_event_id"] = (
        matched_event_id if stamped["position_source"] == "DETECTION" else ""
    )
    return stamped


def trace_rows(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the independent, row-level expected trace for a fixture."""
    return [stamp_row(event.get("row", {}), event["branch"],
                      event["source_branch"], event.get("matched_event_id"))
            for event in events]
