"""Measured liveness gates for normalized tracking frames.

Calibration run 2026-08-31 read all 80 NBA production CSVs in
``C:/Users/neelj/nba-data-backup/tracking``. Basketball fails above the empirical
95th percentile for zero-step share (0.883869) or median step (8.408436), below
the 5th percentile for distinct-position ratio (0.108915), or above the 99th
percentile for stationary-track share (0.149000). The stationary floor is 0.50:
the smallest positive production step was 1.00, so this is a measured half-pixel
resolution boundary, not a liveness acceptance cutoff.

No persisted tracking output exists locally for WNBA, tennis, soccer, baseball,
NPB, KBO, or football. Their acceptance thresholds are therefore ``None`` rather
than guesses; exact fully frozen streams still fail. Recalibrate each sport after
its first labelled trajectory corpus is available. See
``docs/research/liveness_calibration.md`` for distributions and limitations.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


_UNCALIBRATED = {
    "zero_step_share_max": None,
    "median_step_distance_max": None,
    "distinct_position_ratio_min": None,
    "stationary_track_share_max": None,
    "stationary_distance_floor": None,
}
_THRESHOLDS: dict[str, dict[str, float | None]] = {
    "basketball": {
        "zero_step_share_max": 0.883869,
        "median_step_distance_max": 8.408436,
        "distinct_position_ratio_min": 0.108915,
        "stationary_track_share_max": 0.149000,
        "stationary_distance_floor": 0.50,
    },
    "wnba": dict(_UNCALIBRATED),
    "tennis": dict(_UNCALIBRATED),
    "soccer": dict(_UNCALIBRATED),
    "baseball": dict(_UNCALIBRATED),
    "npb": dict(_UNCALIBRATED),
    "kbo": dict(_UNCALIBRATED),
    "football": dict(_UNCALIBRATED),
}


@dataclass(frozen=True)
class LivenessMetrics:
    zero_step_share: float
    median_step_distance: float
    distinct_position_ratio: float
    stationary_track_share: float
    verdict: str


def thresholds_for(sport: str) -> dict[str, float | None]:
    """Return immutable-by-convention liveness thresholds for a supported sport."""
    return dict(_THRESHOLDS[sport])


def liveness_failures(metrics: LivenessMetrics, sport: str) -> tuple[str, ...]:
    """Return calibrated metric failures; uncalibrated sports have none."""
    threshold = _THRESHOLDS[sport]
    checks = (
        ("zero_step_share", metrics.zero_step_share,
         threshold["zero_step_share_max"], "max"),
        ("median_step_distance", metrics.median_step_distance,
         threshold["median_step_distance_max"], "max"),
        ("distinct_position_ratio", metrics.distinct_position_ratio,
         threshold["distinct_position_ratio_min"], "min"),
        ("stationary_track_share", metrics.stationary_track_share,
         threshold["stationary_track_share_max"], "max"),
    )
    failures = []
    for name, value, limit, direction in checks:
        if limit is None:
            continue
        invalid = value > limit if direction == "max" else value < limit
        if invalid:
            sign = ">" if direction == "max" else "<"
            failures.append("{} {:.4f} {} {:.4f}".format(name, value, sign, limit))
    return tuple(failures)


def compute_liveness_metrics(df: pd.DataFrame, sport: str) -> LivenessMetrics:
    """Compute player-track liveness from a normalized tracking frame."""
    threshold = _THRESHOLDS[sport]
    players = df.loc[df["cls"] == "player", ["frame", "track_id", "x", "y"]]
    if players.empty:
        return LivenessMetrics(0.0, 0.0, 0.0, 0.0, "SUSPECT")

    players = players.sort_values(["track_id", "frame"])
    dx = players.groupby("track_id")["x"].diff()
    dy = players.groupby("track_id")["y"].diff()
    steps = (dx.pow(2) + dy.pow(2)).pow(0.5).dropna()
    zero_step_share = float(steps.eq(0).mean()) if not steps.empty else 0.0
    median_step_distance = float(steps.median()) if not steps.empty else 0.0
    rounded_positions = players[["x", "y"]].round(3).drop_duplicates()
    distinct_position_ratio = float(len(rounded_positions) / len(players))
    track_displacement = steps.groupby(players.loc[steps.index, "track_id"]).sum()
    track_displacement = track_displacement.reindex(players["track_id"].unique(), fill_value=0.0)
    floor = threshold["stationary_distance_floor"]
    stationary = (track_displacement.eq(0.0) if floor is None
                  else track_displacement.lt(floor))
    stationary_track_share = float(stationary.mean()) if not stationary.empty else 0.0

    metrics = LivenessMetrics(zero_step_share, median_step_distance,
                              distinct_position_ratio, stationary_track_share, "LIVE")
    if zero_step_share == 1.0 and stationary_track_share == 1.0:
        verdict = "FROZEN"
    elif liveness_failures(metrics, sport):
        verdict = "SUSPECT"
    else:
        verdict = "LIVE"
    return LivenessMetrics(zero_step_share, median_step_distance,
                           distinct_position_ratio, stationary_track_share, verdict)
