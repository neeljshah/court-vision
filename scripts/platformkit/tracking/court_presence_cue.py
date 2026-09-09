"""Deterministic G360 court-presence cue; no production consumer."""

from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np

from scripts.platformkit.footage_content_gate import _surface_fraction


def _orientation_bins(gray: np.ndarray) -> tuple[int, float]:
    """Return occupied 15-degree long-line bins and the longest segment."""
    width = gray.shape[1]
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=32,
                            minLineLength=max(1, int(np.ceil(width * 0.08))),
                            maxLineGap=12)
    if lines is None:
        return 0, 0.0
    bins: set[int] = set()
    longest = 0.0
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length < width * 0.08:
            continue
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180.0)
        bins.add(int(angle // 15.0))
        longest = max(longest, length)
    return len(bins), longest


def court_presence(frame: np.ndarray) -> tuple[float, int, float, float]:
    """Return composite score, line families, longest pixels, and surface share."""
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("court_presence needs a BGR frame")
    families, longest = _orientation_bins(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    surface = _surface_fraction(frame, "basketball")
    score = 0.5 * min(surface / 0.12, 1.0) + 0.5 * min(families / 2.0, 1.0)
    return float(score), families, longest, surface


def auc(values: Iterable[float], positives: Iterable[bool]) -> float:
    """Compute rank AUC, assigning average ranks to tied cue values."""
    pairs = sorted(zip(values, positives), key=lambda pair: pair[0])
    n_pos = sum(bool(flag) for _, flag in pairs)
    n_neg = len(pairs) - n_pos
    if not n_pos or not n_neg:
        raise ValueError("AUC needs both positive and negative references")
    rank_sum = 0.0
    index = 0
    while index < len(pairs):
        stop = index + 1
        while stop < len(pairs) and pairs[stop][0] == pairs[index][0]:
            stop += 1
        average_rank = (index + 1 + stop) / 2.0
        rank_sum += average_rank * sum(bool(flag) for _, flag in pairs[index:stop])
        index = stop
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def choose_rule(rows: list[dict[str, float | int | bool]]) -> tuple[int, float]:
    """Select the preregistered premise-only AND rule with stable tie breaks."""
    families = sorted({int(row["families"]) for row in rows})
    surfaces = sorted({float(row["surface"]) for row in rows})
    candidates: list[tuple[tuple[float, float, float, int, float], int, float]] = []
    for family_floor in families:
        for surface_floor in surfaces:
            flags = [int(row["families"]) >= family_floor and
                     float(row["surface"]) >= surface_floor for row in rows]
            if all(flags) or not any(flags):
                continue
            positive = [bool(row["positive"]) for row in rows]
            tp = sum(flag and truth for flag, truth in zip(flags, positive))
            fp = sum(flag and not truth for flag, truth in zip(flags, positive))
            fn = sum(not flag and truth for flag, truth in zip(flags, positive))
            tn = sum(not flag and not truth for flag, truth in zip(flags, positive))
            recall = tp / (tp + fn) if tp + fn else 0.0
            precision = tp / (tp + fp) if tp + fp else 0.0
            youden = recall + (tn / (tn + fp) if tn + fp else 0.0) - 1.0
            candidates.append(((youden, precision, recall, family_floor, surface_floor),
                               family_floor, surface_floor))
    if not candidates:
        raise ValueError("premise rule has no nonconstant threshold")
    return max(candidates, key=lambda item: item[0])[1:]


def predict(families: int, surface: float, family_floor: int,
            surface_floor: float) -> str:
    """Apply the sealed court rule, retaining an explicit abstention band."""
    if families >= family_floor and surface >= surface_floor:
        return "COURT"
    if families < family_floor and surface < surface_floor:
        return "NON_COURT"
    return "ABSTAIN"
