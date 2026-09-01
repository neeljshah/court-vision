"""Synthetic pre-snap alignment tests for the football formation heuristics.

Run: python -m pytest domains/football/tracking/test_presnap_features.py -q
"""
from __future__ import annotations

from typing import List, Tuple

import pandas as pd

from domains.football.tracking.presnap_features import (
    formation_family,
    formation_features,
    line_of_scrimmage,
    offense_defense_split,
)

Point = Tuple[float, float]


def _rows(points: List[Point]) -> pd.DataFrame:
    """Build one pre-snap frame in the adapter schema from (x, y) feet."""
    return pd.DataFrame(
        [
            {"frame": 0, "track_id": index + 1, "cls": "player", "x": x, "y": y}
            for index, (x, y) in enumerate(points)
        ],
        columns=("frame", "track_id", "cls", "x", "y"),
    )


# LOS at x=100. Offense low-x: five linemen on the ball, four split receivers
# out near the sidelines, one shotgun quarterback 15 ft deep.
SPREAD_OFFENSE: List[Point] = [
    (98.0, 71.0), (98.0, 75.0), (98.0, 80.0), (98.0, 85.0), (98.0, 89.0),
    (99.0, 10.0), (99.0, 30.0), (99.0, 130.0), (99.0, 150.0),
    (85.0, 80.0),
]
SPREAD_DEFENSE: List[Point] = [
    (102.0, 72.0), (102.0, 77.0), (102.0, 83.0), (102.0, 88.0),
    (108.0, 74.0), (108.0, 86.0),
    (125.0, 20.0), (125.0, 140.0), (125.0, 80.0),
    (112.0, 5.0), (112.0, 155.0),
]

# LOS at x=200. Offense low-x: seven bodies tight on the line, quarterback
# under center, fullback and tailback behind him. No split receivers.
HEAVY_OFFENSE: List[Point] = [
    (198.0, 66.0), (198.0, 71.0), (198.0, 75.0), (198.0, 80.0),
    (198.0, 85.0), (198.0, 89.0), (198.0, 94.0),
    (196.0, 80.0), (192.0, 80.0), (188.0, 80.0),
]
HEAVY_DEFENSE: List[Point] = [
    (202.0, 72.0), (202.0, 76.0), (202.0, 80.0), (202.0, 84.0), (202.0, 88.0),
    (212.0, 74.0), (212.0, 80.0), (212.0, 86.0),
    (220.0, 70.0), (220.0, 90.0),
    (205.0, 25.0), (205.0, 135.0),
]


def test_spread_alignment_reads_as_spread_with_exact_box_count() -> None:
    features = formation_features(_rows(SPREAD_OFFENSE + SPREAD_DEFENSE))
    assert formation_family(features) == "SPREAD"
    assert features["n_offense_detected"] == 10.0
    assert features["alignment_width_ft"] == 140.0
    assert features["backfield_count"] == 1.0
    # Four down linemen plus two linebackers; the three deep players and the
    # two wide corners are outside the tackle box.
    assert features["box_count"] == 6.0
    assert features["balance"] == 0.0


def test_heavy_alignment_reads_as_heavy_with_exact_box_count() -> None:
    features = formation_features(_rows(HEAVY_OFFENSE + HEAVY_DEFENSE))
    assert formation_family(features) == "HEAVY"
    assert features["n_offense_detected"] == 10.0
    assert features["alignment_width_ft"] == 28.0
    assert features["backfield_count"] == 2.0
    # Five down linemen plus three linebackers at 4 yards; safeties are 20 ft
    # off the ball and the corners are outside the box laterally.
    assert features["box_count"] == 8.0


def test_line_of_scrimmage_lands_within_a_yard_of_truth() -> None:
    spread = line_of_scrimmage(_rows(SPREAD_OFFENSE + SPREAD_DEFENSE))
    heavy = line_of_scrimmage(_rows(HEAVY_OFFENSE + HEAVY_DEFENSE))
    assert spread is not None and heavy is not None
    assert abs(spread - 100.0) <= 3.0
    assert abs(heavy - 200.0) <= 3.0


def test_split_assigns_the_crowded_line_side_to_the_offense() -> None:
    rows = _rows(HEAVY_OFFENSE + HEAVY_DEFENSE)
    los = line_of_scrimmage(rows)
    assert los is not None
    offense, defense = offense_defense_split(rows, los)
    assert len(offense) == 10 and len(defense) == 12
    assert offense["x"].max() < los <= defense["x"].min()


def test_too_few_detections_returns_unknown() -> None:
    rows = _rows([(98.0, 75.0), (98.0, 85.0), (102.0, 78.0), (102.0, 84.0)])
    assert line_of_scrimmage(rows) is None
    features = formation_features(rows)
    assert features["n_offense_detected"] == 0.0
    assert formation_family(features) == "UNKNOWN"


def test_partial_offense_detection_is_not_labelled() -> None:
    # Six offensive linemen visible, defense fully occluded except the front.
    rows = _rows(SPREAD_OFFENSE[:5] + [(85.0, 80.0)] + SPREAD_DEFENSE[:4])
    features = formation_features(rows)
    assert features["n_offense_detected"] < 7.0
    assert formation_family(features) == "UNKNOWN"
