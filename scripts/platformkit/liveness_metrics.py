"""Liveness metrics for normalized tracking frames.

Metrics use player rows sorted by track and frame. Positions are rounded to three
decimals for the distinct-position metric. A track is stationary when its summed
step distance is below that sport's floor. `FROZEN` requires both near-universal
zero steps and near-universal stationary tracks; `SUSPECT` is an advisory warning
for weaker evidence. The per-sport zero-step maximum is the harness failure gate.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


_THRESHOLDS: dict[str, dict[str, float]] = {
    "basketball": {"zero_step_share_max": 0.98, "stationary_distance_floor": 0.50},
    "wnba": {"zero_step_share_max": 0.98, "stationary_distance_floor": 0.50},
    "tennis": {"zero_step_share_max": 0.98, "stationary_distance_floor": 0.25},
    "soccer": {"zero_step_share_max": 0.98, "stationary_distance_floor": 0.75},
    "baseball": {"zero_step_share_max": 0.99, "stationary_distance_floor": 0.50},
    "npb": {"zero_step_share_max": 0.99, "stationary_distance_floor": 0.50},
    "kbo": {"zero_step_share_max": 0.99, "stationary_distance_floor": 0.50},
    "football": {"zero_step_share_max": 0.98, "stationary_distance_floor": 0.75},
}
_FROZEN_ZERO_STEP_SHARE = 0.995
_FROZEN_STATIONARY_TRACK_SHARE = 0.98
_SUSPECT_ZERO_STEP_SHARE = 0.95
_SUSPECT_STATIONARY_TRACK_SHARE = 0.90


@dataclass(frozen=True)
class LivenessMetrics:
    zero_step_share: float
    median_step_distance: float
    distinct_position_ratio: float
    stationary_track_share: float
    verdict: str


def thresholds_for(sport: str) -> dict[str, float]:
    """Return immutable-by-convention liveness thresholds for a supported sport."""
    return dict(_THRESHOLDS[sport])


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
    stationary_track_share = (
        float(track_displacement.lt(threshold["stationary_distance_floor"]).mean())
        if not track_displacement.empty else 0.0
    )

    if (zero_step_share >= _FROZEN_ZERO_STEP_SHARE
            and stationary_track_share >= _FROZEN_STATIONARY_TRACK_SHARE):
        verdict = "FROZEN"
    elif (zero_step_share >= _SUSPECT_ZERO_STEP_SHARE
          or stationary_track_share >= _SUSPECT_STATIONARY_TRACK_SHARE):
        verdict = "SUSPECT"
    else:
        verdict = "LIVE"
    return LivenessMetrics(zero_step_share, median_step_distance,
                           distinct_position_ratio, stationary_track_share, verdict)
