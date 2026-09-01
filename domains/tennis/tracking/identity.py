"""Tennis player-track identity epochs."""
from __future__ import annotations

import numpy as np


def end_epoch(centroids: dict[int, np.ndarray], base: int) -> tuple[int, dict[int, np.ndarray]]:
    """Return a new identity epoch after a cut or long emission gap."""
    return base + (2 if centroids else 0), {}


def assign_epoch(candidates: list[tuple[np.ndarray, np.ndarray]],
                 centroids: dict[int, np.ndarray], base: int
                 ) -> tuple[list[tuple[int, np.ndarray]], dict[int, np.ndarray]]:
    """Assign the two current candidates while preserving within-epoch continuity."""
    centers = [candidate[0] for candidate in candidates]
    if len(centroids) != 2:
        order = sorted(range(2), key=lambda index: (-centers[index][1], centers[index][0]))
    else:
        previous = [centroids[key] for key in sorted(centroids)]
        direct = np.linalg.norm(centers[0] - previous[0]) + np.linalg.norm(centers[1] - previous[1])
        crossed = np.linalg.norm(centers[1] - previous[0]) + np.linalg.norm(centers[0] - previous[1])
        order = [0, 1] if direct <= crossed else [1, 0]
    tracked = [(base + track_id, candidates[index][1]) for track_id, index in enumerate(order, start=1)]
    return tracked, {base + track_id: centers[index] for track_id, index in enumerate(order, start=1)}
