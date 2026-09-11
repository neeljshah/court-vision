"""Receipt helpers used by G380 trace controls, not by the live producer."""
from __future__ import annotations

from collections.abc import Iterable


def receipt_for_attempts(frame_ids: Iterable[int], attempted_frames_capped: int) -> dict:
    """Create the additive receipt and reject a denominator below observed ticks."""
    ticks = sorted({int(frame) for frame in frame_ids})
    if any(frame < 0 for frame in ticks):
        raise ValueError("evaluated tick ids must be nonnegative")
    if attempted_frames_capped < len(ticks):
        raise ValueError("attempted_frames_capped is below unique evaluated ticks")
    return {
        "evaluated_tick_ids": ticks,
        "attempted_frames_capped": attempted_frames_capped,
        "evaluated_tick_ids_schema": "sorted_source_frame_indices",
    }


def receipt_matches_trace(receipt: dict, traced_frame_ids: Iterable[int]) -> bool:
    """Check exact set equality against independently logged producer attempts."""
    return receipt.get("evaluated_tick_ids") == sorted({int(x) for x in traced_frame_ids})
