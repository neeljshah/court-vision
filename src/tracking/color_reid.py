"""
color_reid.py — ISSUE-005: HSV re-ID for similar-colored uniforms.

When two teams wear similar jersey colors (e.g., both wearing light kits,
or both wearing dark kits), the standard 96-dim HSV histogram cannot distinguish
between them.  This module provides:

    dominant_team_color()     — k-means (k=2) on a jersey crop → dominant HSV centroid
    hue_distance()            — circular hue distance between two centroids
    similar_team_colors()     — returns True when team centroids are within HUE_SIMILAR_TH
    build_color_signature()   — EMA-updated team color signature per slot

The key difference from jersey_ocr.dominant_hsv_cluster() (which uses k=3 for
*within-player* color description) is that this module computes a *per-team*
dominant color and detects when that team-level color is ambiguous.

Constants
---------
    HUE_SIMILAR_TH  = 20    hue units (out of 180) — teams closer than this are "similar"
    COLOR_ALPHA     = 0.85  EMA weight for team color signature update (stable)
    K_DOMINANT      = 2     number of k-means clusters for dominant color extraction
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import cv2
import numpy as np

HUE_SIMILAR_TH: int = 20     # hue units; teams with |Δhue| < this are "similar"
COLOR_ALPHA: float  = 0.85   # EMA weight for team color signature stability
K_DOMINANT: int     = 2      # k-means clusters for dominant color extraction
_MIN_PIXELS: int    = 200    # below this, fall back to mean color


def dominant_team_color(crop_bgr: np.ndarray) -> np.ndarray:
    """
    Extract the dominant jersey color from a player crop using k-means (k=2).

    Uses only the upper 65% of the crop (jersey zone, not shorts/shoes).
    Falls back to mean HSV when the ROI is too small for k-means.

    Args:
        crop_bgr: BGR image of a player bounding box, any size.

    Returns:
        np.ndarray: shape (3,) float32 in OpenCV HSV scale (H 0-180, S 0-255, V 0-255).
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return np.array([0.0, 0.0, 128.0], dtype=np.float32)

    h = crop_bgr.shape[0]
    roi = crop_bgr[: max(1, int(h * 0.65))]
    roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    pixels = roi_hsv.reshape(-1, 3).astype(np.float32)

    if pixels.shape[0] < _MIN_PIXELS:
        return pixels.mean(axis=0).astype(np.float32)

    try:
        from sklearn.cluster import KMeans
        km = KMeans(n_clusters=K_DOMINANT, n_init=3, max_iter=30, random_state=0)
        labels = km.fit_predict(pixels)
        counts = np.bincount(labels)
        dominant_idx = int(np.argmax(counts))
        return km.cluster_centers_[dominant_idx].astype(np.float32)
    except Exception:
        return pixels.mean(axis=0).astype(np.float32)


def hue_distance(color_a: np.ndarray, color_b: np.ndarray) -> float:
    """
    Circular hue distance between two HSV color vectors.

    OpenCV hue is in [0, 180] so the maximum circular distance is 90.

    Args:
        color_a: shape (3,) HSV vector.
        color_b: shape (3,) HSV vector.

    Returns:
        float: circular hue distance in [0, 90].
    """
    ha, hb = float(color_a[0]), float(color_b[0])
    diff = abs(ha - hb)
    return min(diff, 180.0 - diff)


def similar_team_colors(
    sig_team0: Optional[np.ndarray],
    sig_team1: Optional[np.ndarray],
    threshold: int = HUE_SIMILAR_TH,
) -> bool:
    """
    Return True when two team color signatures are too close to distinguish.

    Uses circular hue distance.  If either signature is None, returns False
    (not enough information — assume teams are distinguishable).

    Args:
        sig_team0: HSV color signature for team 0, shape (3,) or None.
        sig_team1: HSV color signature for team 1, shape (3,) or None.
        threshold: Maximum hue distance to consider "similar" (default HUE_SIMILAR_TH=20).

    Returns:
        bool: True if the two teams' dominant hues are within *threshold* units.
    """
    if sig_team0 is None or sig_team1 is None:
        return False
    return hue_distance(sig_team0, sig_team1) < threshold


class TeamColorTracker:
    """
    Maintains an EMA-updated dominant color signature for each team,
    and exposes the `similar_colors` flag updated every frame.

    Usage (in AdvancedFeetDetector):
        self._color_tracker = TeamColorTracker()
        # each frame, after building detections:
        self._color_tracker.update(slot, crop_bgr, team)
        similar = self._color_tracker.similar_colors
    """

    def __init__(self) -> None:
        """Initialize with empty per-team EMA signatures."""
        self._team_sig: Dict[str, Optional[np.ndarray]] = {}
        self.similar_colors: bool = False  # updated by update()

    def update(self, crop_bgr: np.ndarray, team: str) -> None:
        """
        Update the EMA color signature for *team* using one player crop.

        Should be called once per detection, per frame.  After updating,
        rechecks the `similar_colors` flag.

        Args:
            crop_bgr: Player crop in BGR.
            team:     Team label (e.g. 'green', 'white').
        """
        if team == "referee":
            return  # referees are not counted in team color comparison

        new_color = dominant_team_color(crop_bgr)
        if team in self._team_sig and self._team_sig[team] is not None:
            self._team_sig[team] = (
                COLOR_ALPHA * self._team_sig[team]
                + (1.0 - COLOR_ALPHA) * new_color
            )
        else:
            self._team_sig[team] = new_color

        # Refresh flag whenever we have signatures for both teams
        sigs = [s for k, s in self._team_sig.items() if k != "referee" and s is not None]
        if len(sigs) >= 2:
            self.similar_colors = similar_team_colors(sigs[0], sigs[1])

    def get_signature(self, team: str) -> Optional[np.ndarray]:
        """Return the current EMA color signature for *team*, or None."""
        return self._team_sig.get(team)
