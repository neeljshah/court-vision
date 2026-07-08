"""Shot-zone classification from x/y court position alone -- the single
source of truth for BOTH concession_profiles.py and shot_features.py.

WHY GEOMETRY, NOT THE PBP `area` FIELD: verified on-disk that `area` is
populated on only ~12% of shot actions across the 1192-game 2025-26 PBP
corpus -- CDN-native files carry it, but the majority of files here are
ESPN-derived (a different schema: text `description`, no `area`/
`areaDetail`/`qualifiers`/`assistPersonId`) and carry `area=None`. Reading
`area` directly (the original v1 of this module) silently dropped ~88% of
shots. Both x and y ARE present on every shot in both source shapes (the
2-ended CDN percent convention, per the lane brief), so geometry is the one
feature that actually covers 100% of the corpus.

FORMULA (derived + verified exactly against shotDistance on CDN-native
shots, e.g. actionNumber 7 in 0022500003.json: x=81.82,y=50.98 ->
11.85 ft, matching that action's own `shotDistance` field to 2 decimals):
    x_end_pct = min(x_pct, 100 - x_pct)      # fold both court ends onto one
    x_ft = x_end_pct / 100 * COURT_LENGTH_FT # distance along length from baseline
    y_ft = y_pct / 100 * COURT_WIDTH_FT - COURT_WIDTH_FT / 2  # 0 = center
    distance_ft = sqrt((x_ft - BASKET_X_FT)**2 + y_ft**2)

ZONE THRESHOLDS: grid-searched against the ~34.7k CDN-native shots that DO
carry a ground-truth `area` label (this corpus's only labeled subset) --
96.7% agreement at rim<=4.5ft, |paint width|<=8ft AND depth<=14ft,
|corner y|>=22ft, else mid (2pt) / above_break_3 (3pt). Not exact (NBA zone
boundaries are polygons, not circles/bands) but the best available
calibration on this corpus, and the only classifier that covers all shots.
"""
from __future__ import annotations

import math

COURT_LENGTH_FT = 94.0
COURT_WIDTH_FT = 50.0
BASKET_X_FT = 5.25

RIM_DIST_FT = 4.5
PAINT_WIDTH_FT = 8.0
PAINT_DEPTH_FT = 14.0
CORNER_Y_FT = 22.0

ZONES = ["rim", "paint", "mid", "corner3", "above_break_3"]


def shot_geometry_ft(x_pct: float, y_pct: float) -> tuple[float, float]:
    """Returns (distance_from_basket_ft, y_ft) where y_ft=0 is court center."""
    x_end_pct = min(x_pct, 100.0 - x_pct)
    x_ft = x_end_pct / 100.0 * COURT_LENGTH_FT
    y_ft = y_pct / 100.0 * COURT_WIDTH_FT - COURT_WIDTH_FT / 2.0
    distance = math.sqrt((x_ft - BASKET_X_FT) ** 2 + y_ft ** 2)
    return distance, y_ft


def classify_zone(x_pct: float, y_pct: float, is_3: bool) -> str:
    distance, y_ft = shot_geometry_ft(x_pct, y_pct)
    if is_3:
        return "corner3" if abs(y_ft) >= CORNER_Y_FT else "above_break_3"
    if distance <= RIM_DIST_FT:
        return "rim"
    if abs(y_ft) <= PAINT_WIDTH_FT and distance <= PAINT_DEPTH_FT:
        return "paint"
    return "mid"
