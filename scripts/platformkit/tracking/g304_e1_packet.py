"""Schema checks for the G304 held-out annotation packet."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

TOTAL_ROWS = 60
ELIGIBLE_ROWS = 40
NEGATIVE_ROWS = 20
PER_ARENA_NEGATIVE_SPLIT = {"close_up": 4, "graphics_transition": 3, "replay_alternate": 3}
NEGATIVE_SPLIT = {"close_up": 8, "graphics_transition": 6, "replay_alternate": 6}
MIN_SHOTS_PER_ARENA = 4
LANDMARKS_PER_ELIGIBLE = 6
MIN_MARKING_STRUCTURES = 3
ADJUDICATION_PX = 4
FRAME_GOOD_RULE = "p90 <= 12 px AND max <= 24 px"
SOURCE_FPS = 30
FRAME_INDEX_RULE = "frame_index = ceil(pts_seconds * 30)"


def frame_index_for_pts(pts_seconds: float, fps: int = SOURCE_FPS) -> int:
    """The frame `ffmpeg -ss <pts_seconds>` decodes: the first frame at or after the seek."""
    return math.ceil(pts_seconds * fps)


def validate_completed_packet(manifest: dict[str, Any]) -> list[str]:
    """Return contract violations; an unresolved packet is intentionally invalid."""
    errors: list[str] = []
    rows = manifest.get("rows", [])
    if len(rows) != TOTAL_ROWS:
        errors.append("requires 60 enumerated rows")
    for row in rows:
        if row.get("frame_index") != frame_index_for_pts(row.get("pts_seconds", -1.0)):
            errors.append(f"{row.get('row_id')} breaks {FRAME_INDEX_RULE}")
    selected = [row for row in rows if row.get("selection_status") == "selected"]
    eligible = [row for row in selected if row.get("scope") == "eligible"]
    negatives = [row for row in selected if row.get("scope") == "negative"]
    if len(eligible) != ELIGIBLE_ROWS or len(negatives) != NEGATIVE_ROWS:
        errors.append("requires 40 eligible and 20 negative selected rows")
    if Counter(row.get("negative_type") for row in negatives) != NEGATIVE_SPLIT:
        errors.append("requires the 4/3/3 negative split in each arena")
    for source in manifest.get("source_rows", []):
        arena = source.get("id")
        arena_eligible = [row for row in eligible if row.get("source_id") == arena]
        arena_negatives = [row for row in negatives if row.get("source_id") == arena]
        if Counter(row.get("negative_type") for row in arena_negatives) != PER_ARENA_NEGATIVE_SPLIT:
            errors.append(f"{arena} needs the 4/3/3 negative split")
        if len({row.get("shot_identity") for row in arena_eligible}) < MIN_SHOTS_PER_ARENA:
            errors.append(f"{arena} needs at least four shots")
    for row in eligible:
        landmarks = row.get("landmarks", [])
        if len(landmarks) != LANDMARKS_PER_ELIGIBLE:
            errors.append(f"{row.get('row_id')} needs six landmarks")
            continue
        if len({point.get("marking_structure") for point in landmarks}) < MIN_MARKING_STRUCTURES:
            errors.append(f"{row.get('row_id')} needs three marking structures")
    if manifest.get("frame_good_rule") != FRAME_GOOD_RULE:
        errors.append("frame-good rule differs from the sealed requirement")
    return errors
