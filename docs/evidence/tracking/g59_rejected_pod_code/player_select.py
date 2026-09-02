"""Court-prior player selection for tennis person detections."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Hashable, Optional

import numpy as np


COURT_X_BOUNDS = (-6.0, 84.0)
COURT_Y_BOUNDS = (-4.0, 40.0)
HALF_LENGTH_FT = 39.0
HISTORY_FRAMES = 15
NEAREST_CENTER_PX = 120.0


@dataclass(frozen=True)
class PlayerCandidate:
    """One detector person box after its foot has been projected to court feet."""

    center: np.ndarray
    foot: np.ndarray
    confidence: float
    detector_track_id: Optional[Hashable] = None


def is_on_expanded_court(foot: np.ndarray) -> bool:
    """Return whether a foot point lies inside the permitted expanded court."""
    return bool(COURT_X_BOUNDS[0] <= foot[0] <= COURT_X_BOUNDS[1]
                and COURT_Y_BOUNDS[0] <= foot[1] <= COURT_Y_BOUNDS[1])


class PlayerSelector:
    """Choose at most one on-court person per half using recent persistence."""

    def __init__(self) -> None:
        self._history: deque[tuple[PlayerCandidate, ...]] = deque(maxlen=HISTORY_FRAMES)
        self.last_non_players: list[PlayerCandidate] = []

    def reset(self) -> None:
        """Forget image-space history after a scene/camera epoch boundary."""
        self._history.clear()
        self.last_non_players = []

    def _persistence(self, candidate: PlayerCandidate) -> int:
        count = 0
        for frame in self._history:
            for previous in frame:
                same_id = (candidate.detector_track_id is not None
                           and candidate.detector_track_id == previous.detector_track_id)
                near_center = np.linalg.norm(candidate.center - previous.center) <= NEAREST_CENTER_PX
                if same_id or (candidate.detector_track_id is None and near_center):
                    count += 1
                    break
        return count

    def select(self, candidates: list[PlayerCandidate]) -> dict[int, PlayerCandidate]:
        """Return on-court selections by half; off-court boxes are never selected."""
        in_court: list[PlayerCandidate] = []
        self.last_non_players = []
        for candidate in candidates:
            (in_court if is_on_expanded_court(candidate.foot) else self.last_non_players).append(candidate)
        selected: dict[int, PlayerCandidate] = {}
        for half in (0, 1):
            half_candidates = [candidate for candidate in in_court
                               if (0 if candidate.foot[0] < HALF_LENGTH_FT else 1) == half]
            if half_candidates:
                selected[half] = max(half_candidates, key=lambda candidate: (
                    self._persistence(candidate), candidate.confidence,
                ))
        self._history.append(tuple(selected.values()))
        return selected
