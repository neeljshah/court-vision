"""Native PTS and retained-source receipts for a future G402 measurement."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = ["retained_supply", "select_pts_window"]


def _float(value: Any, error: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(error) from exc


def retained_supply(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count uniquely retained sources with bytes and a usable ten-second span."""
    seen: set[str] = set()
    retained = 0
    for source in rows:
        section = str(source.get("section_id", ""))
        if not section or section in seen:
            raise ValueError("source-section-not-unique")
        seen.add(section)
        present = str(source.get("source_status", "")) == "PRESENT"
        bytes_ok = _float(source.get("source_bytes"), "source-bytes-invalid") > 0
        span_ok = _float(source.get("usable_span_s"), "usable-span-invalid") >= 10.0
        if present and bytes_ok and span_ok:
            retained += 1
    return {"selected_sections": len(seen), "retained_sections": retained}


def select_pts_window(decoded: Iterable[Mapping[str, Any]], start_s: float,
                      duration_s: float = 10.0) -> list[dict[str, Any]]:
    """Select exact decoded PTS rows, preserving their source frame identifiers."""
    if duration_s <= 0:
        raise ValueError("window-duration-invalid")
    lower, upper = float(start_s), float(start_s) + float(duration_s)
    rows = [dict(row) for row in decoded]
    prior = float("-inf")
    frame_ids: set[str] = set()
    for row in rows:
        frame = str(row.get("source_frame", ""))
        pts = _float(row.get("pts_s"), "decoded-pts-invalid")
        if not frame or frame in frame_ids:
            raise ValueError("source-frame-mapping-invalid")
        if pts < prior:
            raise ValueError("decoded-pts-not-monotonic")
        frame_ids.add(frame)
        prior = pts
    selected = [row for row in rows if lower <= _float(row["pts_s"], "decoded-pts-invalid") < upper]
    if not selected:
        raise ValueError("window-pts-empty")
    return selected
