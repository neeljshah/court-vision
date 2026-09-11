"""Pure population and native-PTS controls for the G407 census."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

KNOWN_RENDITIONS = ("270", "232", "312", "301", "311", "300")


def _text(row: dict[str, Any], key: str) -> str:
    return str(row.get(key, "")).strip()


def actual_rendition(row: dict[str, Any]) -> str:
    """Return an actual receipt-bound rendition, never a requested one."""
    format_id = _text(row, "actual_format_id")
    digest = _text(row, "source_sha256")
    width = _text(row, "measured_width")
    height = _text(row, "measured_height")
    if not format_id or not digest or not width or not height:
        return "UNRESOLVED"
    return format_id if format_id in KNOWN_RENDITIONS else "GENERIC_FALLBACK"


def earliest_terminal_original(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one earliest terminal ORIGINAL attempt per section identity."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if _text(row, "attempt_kind") != "ORIGINAL" or not row.get("terminal"):
            continue
        identity = _text(row, "section_identity")
        if identity:
            grouped[identity].append(dict(row))
    kept = []
    for identity in sorted(grouped):
        kept.append(min(grouped[identity], key=lambda row: (
            _text(row, "terminal_utc"), _text(row, "attempt_id"))))
    return kept


def join_format_receipts(attempts: list[dict[str, Any]],
                         receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join attempts only when section identity and native source digest agree."""
    by_key = {(_text(row, "section_identity"), _text(row, "source_sha256")): row
              for row in receipts}
    joined = []
    for attempt in earliest_terminal_original(attempts):
        key = (_text(attempt, "section_identity"), _text(attempt, "source_sha256"))
        receipt = by_key.get(key)
        row = dict(attempt)
        if receipt is None:
            row["format_join_status"] = "UNRESOLVED"
        else:
            row.update({key: value for key, value in receipt.items()
                        if key != "requested_format_id"})
            row["format_join_status"] = "BOUND"
        row["actual_rendition"] = actual_rendition(row)
        joined.append(row)
    return joined


def even_draw(rows: list[dict[str, Any]], quota: int = 30,
              total_cap: int = 180) -> dict[str, list[dict[str, Any]]]:
    """Draw an exact-even no-refill sample separately for each rendition."""
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        strata[_text(row, "actual_rendition") or actual_rendition(row)].append(dict(row))
    selected: dict[str, list[dict[str, Any]]] = {}
    for rendition in sorted(set(KNOWN_RENDITIONS) | set(strata)):
        unique = {(_text(row, "section_identity"), _text(row, "source_sha256")): row
                  for row in strata.get(rendition, [])}
        ordered = sorted(unique.values(), key=lambda row: (
            _text(row, "competition"), _text(row, "canonical_game"),
            _text(row, "section_identity"), _text(row, "source_sha256")))
        if len(ordered) < quota:
            selected[rendition] = []
            continue
        selected[rendition] = [ordered[int(j * (len(ordered) - 1) / (quota - 1) + .5)]
                               for j in range(quota)]
    if sum(len(rows) for rows in selected.values()) > total_cap:
        raise ValueError("rendition-draw-over-total-cap")
    return selected


def fps_bucket(rendition: str, value: Any) -> str:
    """Return the preregistered native-rate bin; only itag 232 uses these bins."""
    if rendition != "232":
        return "NOT_232"
    try:
        fps = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if 29.0 <= fps <= 31.0:
        return "29_31"
    if fps == 25.0:
        return "25"
    return "OTHER"


def centered_interval(pts: list[float], seconds: float = 2.0) -> tuple[float, float]:
    """Seal a centered PTS interval, resolving equal-distance ties earlier."""
    if not pts or seconds <= 0:
        raise ValueError("native-pts-required")
    ordered = sorted(float(value) for value in pts)
    middle = (ordered[0] + ordered[-1]) / 2.0
    center = min(ordered, key=lambda value: (abs(value - middle), value))
    return center - seconds / 2.0, center + seconds / 2.0
