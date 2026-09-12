"""Preparation-only guards for the G409 coordinate trace."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

SEAL_PATTERN = re.compile(r"(?:^|\n)SEAL sha256 ([0-9a-f]{64})\n?$")


def prereg_seal_valid(path: Path) -> bool:
    """Validate the preregistration seal after CRLF-to-LF normalization."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = SEAL_PATTERN.search(text)
    if match is None:
        return False
    start = match.start() + (1 if text[match.start():match.start() + 1] == "\n" else 0)
    actual = hashlib.sha256(text[:start].encode("utf-8")).hexdigest()
    return actual == match.group(1)


def require_absolute_window(frame: int, start_frame: int, frame_cap: int) -> int:
    """Return an absolute frame index only when it is inside the sealed window."""
    if frame_cap <= start_frame:
        raise ValueError("invalid-window-cap")
    if frame < start_frame or frame >= frame_cap:
        raise ValueError("absolute-frame-outside-window")
    return frame


def retain_silence(
    selected: Iterable[Mapping[str, Any]], rows: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Account for every selected tick, including ticks with no producer row."""
    grouped: dict[tuple[str, str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (str(row["source_sha256"]), str(row["window_id"]), int(row["frame"]))
        grouped[key].append(row)
    retained = []
    for tick in selected:
        key = (str(tick["source_sha256"]), str(tick["window_id"]), int(tick["frame"]))
        retained.append(dict(tick, producer_row_count=len(grouped[key]), silence=int(not grouped[key])))
    return retained


def strict_event_join(
    events: Iterable[Mapping[str, Any]], parents: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Join frozen events to one parent each and reject absent or duplicate keys."""
    indexed: dict[str, Mapping[str, Any]] = {}
    for parent in parents:
        key = str(parent["event_key"])
        if key in indexed:
            raise ValueError("duplicate-event-join")
        indexed[key] = parent
    joined = []
    seen_events = set()
    for event in events:
        key = str(event["event_key"])
        if key in seen_events:
            raise ValueError("duplicate-event-join")
        seen_events.add(key)
        if key not in indexed:
            raise ValueError("absent-event-join")
        joined.append(dict(event, parent=dict(indexed[key])))
    return joined


def cache_frame_identity(native_frame: int, model_frame: int, cache_frame: int) -> dict[str, Any]:
    """Describe cache identity without masking a stale prefetched frame."""
    same = native_frame == model_frame == cache_frame
    return {
        "native_frame": native_frame,
        "model_frame": model_frame,
        "cache_frame": cache_frame,
        "identity_status": "MATCH" if same else "STALE_CACHE_FRAME",
        "matches": same,
    }
