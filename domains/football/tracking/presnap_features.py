"""Coarse pre-snap formation geometry from football tracking rows.

Honest scope: these are geometric heuristics over the pre-snap rows emitted by
`domains.football.tracking.adapter` (x in feet along the field, y across the
160 ft width). There is NO personnel identification here -- no jersey numbers,
no position labels, no eligibility. Separating a tight end from a sixth
lineman, or a nickel back from a safety, needs the jersey/position CV the atlas
calls for and this module does not have. Every label below is therefore a shape
family, not a personnel grouping.

Known biases, stated up front:
  * The line of scrimmage is estimated as the densest one-yard band of players.
    The offense normally puts more bodies on the line than the defense, so the
    estimate is pulled toward the offensive side by roughly a foot.
  * Offense/defense identity is inferred from that same crowding (more players
    within a yard of the LOS = offense). An unbalanced offensive line against a
    heavy defensive front can invert it.
  * `balance` is field-relative, not offense-relative: play direction is not
    recoverable from a single pre-snap frame without the yard numbers, which
    the adapter deliberately leaves as an OCR stub.

Too few detections returns UNKNOWN rather than a guess.

Run: python -m pytest domains/football/tracking/test_presnap_features.py -q
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

FIELD_WIDTH_FT = 160.0
LOS_BAND_FT = 3.0
BOX_HALF_WIDTH_FT = 9.0
BOX_DEPTH_FT = 15.0
BACKFIELD_DEPTH_FT = 5.0
MIN_PLAYERS_FOR_LOS = 6
MIN_OFFENSE_FOR_FAMILY = 7
SPREAD_WIDTH_FT = 85.0
HEAVY_WIDTH_FT = 50.0
SPREAD_MAX_BACKFIELD = 1

FEATURE_KEYS = (
    "n_offense_detected",
    "alignment_width_ft",
    "backfield_count",
    "box_count",
    "balance",
)


def _players(frame_rows: pd.DataFrame) -> pd.DataFrame:
    """Return the player rows of one frame, dropping ball or other classes."""
    if "cls" in frame_rows.columns:
        return frame_rows.loc[frame_rows["cls"] == "player"]
    return frame_rows


def _densest_center(values: np.ndarray, band: float) -> Optional[float]:
    """Return the mean of the members of the densest +/- band window."""
    if values.size == 0:
        return None
    # ponytail: 1 ft grid scan, O(field_ft * n) with n <= ~30 per frame. Swap in
    # a sorted sliding window only if a frame ever carries hundreds of rows.
    grid = np.arange(np.floor(values.min()), np.ceil(values.max()) + 1.0, 1.0)
    center = max(grid, key=lambda point: int(np.count_nonzero(np.abs(values - point) <= band)))
    return float(np.mean(values[np.abs(values - center) <= band]))


def line_of_scrimmage(frame_rows: pd.DataFrame, band_ft: float = LOS_BAND_FT) -> Optional[float]:
    """Estimate the LOS as the x of the densest one-yard cluster of players.

    Returns None when fewer than MIN_PLAYERS_FOR_LOS players were detected, so
    a partially occluded frame does not produce a confident wrong answer.
    """
    players = _players(frame_rows)
    if len(players) < MIN_PLAYERS_FOR_LOS:
        return None
    return _densest_center(players["x"].to_numpy(dtype=float), band_ft)


def _on_the_line(side: pd.DataFrame, los: float) -> int:
    return int(np.count_nonzero(np.abs(side["x"].to_numpy(dtype=float) - los) <= LOS_BAND_FT))


def offense_defense_split(
    frame_rows: pd.DataFrame, los: float
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split players by side of the LOS and return (offense, defense).

    The side with more players within one yard of the LOS is called the
    offense: five linemen plus attached ends outnumber a three or four man
    defensive front. Ties go to the low-x side. This is a shape argument, not
    an identification -- see the module docstring.
    """
    players = _players(frame_rows)
    x = players["x"].to_numpy(dtype=float)
    low, high = players.loc[x < los], players.loc[x >= los]
    if _on_the_line(low, los) >= _on_the_line(high, los):
        return low, high
    return high, low


def _empty_features() -> Dict[str, float]:
    return {key: 0.0 for key in FEATURE_KEYS}


def formation_features(frame_rows: pd.DataFrame) -> Dict[str, float]:
    """Return coarse geometric formation features for one pre-snap frame.

    Keys: n_offense_detected, alignment_width_ft (offense lateral spread),
    backfield_count (offense players more than 5 ft behind the LOS), box_count
    (defenders inside the tackle box), balance (field-left minus field-right
    offensive count about the box center). All zeros when the LOS cannot be
    estimated.
    """
    los = line_of_scrimmage(frame_rows)
    if los is None:
        return _empty_features()
    offense, defense = offense_defense_split(frame_rows, los)
    if offense.empty:
        return _empty_features()

    offense_y = offense["y"].to_numpy(dtype=float)
    offense_x = offense["x"].to_numpy(dtype=float)
    center = _densest_center(offense_y, BOX_HALF_WIDTH_FT)
    if center is None:
        center = FIELD_WIDTH_FT / 2.0

    # Positive depth means further from the defense, i.e. behind the LOS.
    sign = 1.0 if float(offense_x.mean()) < los else -1.0
    depth = sign * (los - offense_x)

    defense_x = defense["x"].to_numpy(dtype=float)
    defense_y = defense["y"].to_numpy(dtype=float)
    in_box = (np.abs(defense_y - center) < BOX_HALF_WIDTH_FT) & (
        np.abs(defense_x - los) <= BOX_DEPTH_FT
    )

    return {
        "n_offense_detected": float(len(offense)),
        "alignment_width_ft": float(offense_y.max() - offense_y.min()),
        "backfield_count": float(np.count_nonzero(depth > BACKFIELD_DEPTH_FT)),
        "box_count": float(np.count_nonzero(in_box)),
        "balance": float(
            np.count_nonzero(offense_y < center) - np.count_nonzero(offense_y > center)
        ),
    }


def formation_family(features: Dict[str, float]) -> str:
    """Map formation features to SPREAD / BALANCED / HEAVY / UNKNOWN.

    Documented thresholds, chosen from alignment geometry rather than fitted:
      UNKNOWN  fewer than 7 offensive players detected -- the width of a
               partially detected offense is meaningless.
      HEAVY    alignment_width_ft <= 50. Tackle to tackle is roughly 22 ft, so
               a 50 ft span means every extra body is attached tight to the
               line: no split receivers to speak of.
      SPREAD   alignment_width_ft >= 85 (offense covers more than half the
               160 ft width, i.e. receivers out near the numbers) AND at most
               one player in the backfield.
      BALANCED everything in between, including wide sets that still keep two
               or more backs.
    """
    if features.get("n_offense_detected", 0.0) < MIN_OFFENSE_FOR_FAMILY:
        return "UNKNOWN"
    width = features.get("alignment_width_ft", 0.0)
    if width <= HEAVY_WIDTH_FT:
        return "HEAVY"
    if width >= SPREAD_WIDTH_FT and features.get("backfield_count", 0.0) <= SPREAD_MAX_BACKFIELD:
        return "SPREAD"
    return "BALANCED"
