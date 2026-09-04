"""Shared court-model helpers for basketball tracking adapters."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.tracking.g196_homography_from_labelled_corners import (
    COURT_LENGTH_FT,
    COURT_WIDTH_FT,
    LANE_WIDTH_FT,
    PAINT_DEPTH_FT,
    court_points_for_sport,
)


class BasketballGeometryMixin:
    """Expose the established NBA-family paint model without claiming a solve."""

    @staticmethod
    def court_model(league: str = "ncaa_basketball") -> np.ndarray:
        """Return ordered near-paint corners from the shared G196 court model."""
        if league not in LANE_WIDTH_FT:
            raise ValueError("unsupported basketball league: %s" % league)
        return court_points_for_sport(league).copy()

    @staticmethod
    def point_in_court(point: np.ndarray) -> bool:
        """Return whether a known court-space point lies inside the 94x50 model."""
        return bool(0.0 <= point[0] <= COURT_WIDTH_FT and
                    0.0 <= point[1] <= COURT_LENGTH_FT)
