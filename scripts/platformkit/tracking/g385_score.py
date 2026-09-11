"""G385 planned-denominator scoring with UNKNOWN retained in published counts."""

from __future__ import annotations

import math


Z = 1.959964
PLAY = "PLAY"
DEFINITE_NONPLAY = {"NONPLAY", "OTHER_SPORT", "NON_SPORT"}


def wilson(successes: int, total: int) -> tuple[float, float, float]:
    """Return point, lower, and upper Wilson 95 percent values."""
    if total == 0:
        return 0.0, 0.0, 0.0
    point = successes / total
    denom = 1.0 + Z * Z / total
    centre = (point + Z * Z / (2.0 * total)) / denom
    spread = Z * math.sqrt(point * (1.0 - point) / total + Z * Z / (4.0 * total * total)) / denom
    return point, max(0.0, centre - spread), min(1.0, centre + spread)


def score(rows: list[dict[str, str]]) -> dict[str, object]:
    """Score all attempted planned ticks; UNKNOWN rows are never discarded."""
    keys = [row["tick_key"] for row in rows]
    if len(keys) != 360 or len(set(keys)) != 360:
        raise ValueError("all 360 planned unique ticks must be represented")
    masks = [row for row in rows if row["shadow_decision"] == "MASK"]
    play = [row for row in rows if row["reference_label"] == PLAY]
    definite = [row for row in rows if row["reference_label"] in DEFINITE_NONPLAY]
    unknown = [row for row in rows if row["reference_label"] == "UNKNOWN"]
    false_masks = sum(row["shadow_decision"] == "MASK" for row in play)
    captured = sum(row["shadow_decision"] == "MASK" for row in definite)
    correct_masks = captured
    return {
        "planned_frames": len(rows), "reference_play": len(play),
        "reference_definite_nonplay": len(definite), "reference_unknown": len(unknown),
        "masked_frames": len(masks), "false_masks": false_masks, "captured_nonplay": captured,
        "false_mask_rate": wilson(false_masks, len(play)),
        "nonplay_capture": wilson(captured, len(definite)),
        "mask_precision_all_masked": wilson(correct_masks, len(masks)),
        "unknown_all_planned": wilson(len(unknown), len(rows)),
        "bar_false_mask": wilson(false_masks, len(play))[2] <= 0.05,
        "bar_capture": wilson(captured, len(definite))[1] >= 0.50,
        "bar_classes": len(play) >= 30 and len(definite) >= 30,
        "zero_absent_masks": all(not (row["shadow_decision"] == "MASK" and
                                       row.get("evidence_status") != "READABLE") for row in rows),
    }
