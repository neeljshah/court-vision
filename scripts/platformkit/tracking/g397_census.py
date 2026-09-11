"""Pure G397 census and draw rules; callers perform all store I/O explicitly."""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

FORMAT_1080P30 = "1080p30"
FORMAT_720P60 = "720p60"
FORMAT_OTHER = "OTHER"
FORMAT_UNKNOWN = "UNKNOWN"
WORKTREE_PREFIX = re.compile(r"^/c/Users/neelj/nba-track-a\d+/(.*)$", re.IGNORECASE)
TERMINAL_STATUSES = frozenset({"COMPLETE", "COMPLETED", "DONE", "FAILED", "FAILURE",
                               "ERROR", "CANCELLED", "CLOSED", "TERMINAL"})

__all__ = ["FORMAT_1080P30", "FORMAT_720P60", "FORMAT_OTHER", "FORMAT_UNKNOWN",
           "classify_format", "even_draw", "earliest_terminal_original", "sha256_file",
           "resolve_worktree_path", "section_sort_key", "cap_duration_seconds"]


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of one caller-selected file without opening any store."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def classify_format(probe: Mapping[str, Any]) -> str:
    """Classify only measured width, height, and fps; never infer from labels."""
    width, height, fps = _number(probe.get("width")), _number(probe.get("height")), _number(probe.get("fps"))
    if width is None or height is None or fps is None:
        return FORMAT_UNKNOWN
    if width == 1920 and height == 1080 and 29 <= fps <= 31:
        return FORMAT_1080P30
    if width == 1280 and height == 720 and 59 <= fps <= 61:
        return FORMAT_720P60
    return FORMAT_OTHER


def cap_duration_seconds(frame_cap: int, fps: float) -> float:
    """Return the native-time duration implied by a source-frame cap."""
    if frame_cap <= 0 or fps <= 0:
        raise ValueError("positive-cap-and-fps-required")
    return frame_cap / fps


def section_sort_key(record: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the sealed stable ordering key for one unique section."""
    return tuple(str(record.get(name, "")) for name in
                 ("competition", "video", "source_start", "section_id", "source_sha256"))


def even_draw(records: Iterable[Mapping[str, Any]], count: int = 30) -> list[dict[str, Any]]:
    """Select the sealed rounded-even positions with no replacement."""
    ordered = sorted((dict(row) for row in records), key=section_sort_key)
    if len(ordered) < count:
        raise ValueError("insufficient-unique-sections:%d" % len(ordered))
    if len({row.get("section_id") for row in ordered}) != len(ordered):
        raise ValueError("duplicate-section-id")
    indices = [math.floor(index * (len(ordered) - 1) / (count - 1) + 0.5)
               for index in range(count)]
    return [ordered[index] for index in indices]


def _terminal(record: Mapping[str, Any]) -> bool:
    explicit = record.get("terminal")
    if isinstance(explicit, bool):
        return explicit
    return str(record.get("status", "")).strip().upper() in TERMINAL_STATUSES


def earliest_terminal_original(attempts: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Return the frozen earliest terminal ORIGINAL attempt, else an explicit absence."""
    candidates = [dict(row) for row in attempts if _terminal(row)
                  and str(row.get("route_identity", "")).upper() == "ORIGINAL"]
    if not candidates:
        return None
    return min(candidates, key=lambda row: (str(row.get("started_at", "")),
                                             str(row.get("attempt_id", ""))))


def resolve_worktree_path(cited: str | Path, root: Path) -> Path:
    """Resolve a cited sibling worktree prefix beneath this lane's root."""
    text = str(cited).replace("\\", "/")
    match = WORKTREE_PREFIX.match(text)
    return Path(root) / match.group(1) if match else Path(text)
