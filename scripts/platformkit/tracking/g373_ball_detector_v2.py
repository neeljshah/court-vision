"""Small, corpus-free rails for the G373 ball-detector v2 protocol."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Sequence


MIN_MATCH_PX = 3.0
SEAL_PREFIX = b"SEAL sha256 "


def centre_match(
    references: Sequence[tuple[float, float, float]],
    predictions: Sequence[tuple[float, float]],
    scale_to_720p: float,
) -> set[int]:
    """Return reference indices matched once by the sealed centre-only rule."""
    candidates: list[tuple[float, int, int]] = []
    for prediction_index, (px, py) in enumerate(predictions):
        for reference_index, (rx, ry, diameter_native) in enumerate(references):
            distance = math.hypot(px - rx, py - ry) * scale_to_720p
            tolerance = max(MIN_MATCH_PX, diameter_native * scale_to_720p / 2.0)
            if distance <= tolerance:
                candidates.append((distance, prediction_index, reference_index))
    used_predictions: set[int] = set()
    used_references: set[int] = set()
    for _, prediction_index, reference_index in sorted(candidates):
        if prediction_index not in used_predictions and reference_index not in used_references:
            used_predictions.add(prediction_index)
            used_references.add(reference_index)
    return used_references


def frame_counts(
    label: str,
    references: Sequence[tuple[float, float, float]],
    predictions: Sequence[tuple[float, float]],
    scale_to_720p: float,
) -> tuple[int, int]:
    """Return TP and FP for one frame; UNKNOWN predictions are false positives."""
    targets = references if label == "VISIBLE" else ()
    matched = centre_match(targets, predictions, scale_to_720p)
    true_positives = len(matched)
    return true_positives, len(predictions) - true_positives


def even_indices(total: int, count: int, stable_key: str) -> list[int]:
    """Select evenly distributed, deterministic indices across the complete set."""
    if not stable_key:
        raise ValueError("stable_key is required")
    if total < count or count < 2:
        raise ValueError("total must be at least count and count must be at least two")
    hashlib.sha256(stable_key.encode("ascii")).digest()
    return [round(index * (total - 1) / (count - 1)) for index in range(count)]


def a10_available(a8_has_boxes: bool) -> bool:
    """A10 is available only when its A8 dependency supplies boxes."""
    return a8_has_boxes


def prereg_seal_matches(path: Path) -> bool:
    """Verify a prereg seal from file bytes, normalising only CRLF line endings."""
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    body, separator, recorded = raw.rpartition(b"\n" + SEAL_PREFIX)
    if not separator or not recorded.endswith(b"\n"):
        return False
    digest = hashlib.sha256(body + b"\n").hexdigest().encode("ascii")
    return recorded.strip() == digest
