"""Leak-safe PBP possession tempo features.

The input is one normalized row per possession, ordered by ``game_date``,
``game_id`` and ``event_order``.  A row must name its possessing team, elapsed
game seconds, possession duration, and a pre-possession score margin.  Every
feature is snapshotted before the row updates its team's history.

The pack is PBP-only and RUNTIME-AVAILABLE: all inputs are present in a live
play-by-play feed.  ``garbage_time_exposure_prior_asof`` is a nuisance control,
not a prediction claim.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from scripts.platformkit.asof_common import AsofSpec, Accumulator, walk_forward_asof


OUTPUT_COLUMNS = (
    "possession_seconds_p25_asof",
    "possession_seconds_p50_asof",
    "possession_seconds_p75_asof",
    "late_clock_share_asof",
    "transition_possession_rate_asof",
    "tempo_by_score_state_asof",
    "garbage_time_exposure_prior_asof",
)
RUNTIME_COLUMNS = OUTPUT_COLUMNS
RUNTIME_TAG = "RUNTIME"
MIN_SCORE_STATE_PRIOR_POSSESSIONS = 5
LATE_CLOCK_REMAINING_SECONDS = 7.0
TRANSITION_POSSESSION_SECONDS = 8.0
GARBAGE_TIME_MARGIN = 20.0
GARBAGE_TIME_START_SECONDS = 2160.0

_REQUIRED = {
    "game_id",
    "game_date",
    "event_order",
    "team_id",
    "elapsed_seconds",
    "possession_seconds",
    "score_margin",
}


class QuantileAccumulator:
    """Prior-only empirical quantile accumulator used by the common as-of walker."""

    def __init__(self, quantile: float, min_prior: int = 1) -> None:
        self.n = 0
        self._quantile = float(quantile)
        self._min_prior = int(min_prior)
        self._values: list[float] = []

    def snapshot(self) -> float:
        if self.n < self._min_prior:
            return float("nan")
        return float(np.quantile(self._values, self._quantile))

    def update(self, obs: float) -> None:
        if obs is None or pd.isna(obs):
            return
        self._values.append(float(obs))
        self.n += 1


def _require_columns(possessions: pd.DataFrame) -> None:
    missing = sorted(_REQUIRED.difference(possessions.columns))
    if missing:
        raise ValueError("PBP possessions missing required columns: %s" % ", ".join(missing))


def _score_state(margin: float) -> str:
    if margin <= -10.0:
        return "trailing_10_plus"
    if margin >= 10.0:
        return "leading_10_plus"
    return "competitive"


def _asof_metric(
    events: pd.DataFrame,
    values: pd.Series,
    prefix: str,
    factory: Callable[[], Accumulator],
    state_ids: pd.Series | None = None,
) -> np.ndarray:
    """Run one metric through the shared snapshot-before-update primitive."""
    metric = events[["_tempo_event_id", "game_date", "game_id", "event_order", "team_id"]].copy()
    metric["_state_id"] = events["team_id"] if state_ids is None else state_ids
    metric["_observation"] = values.to_numpy()
    result = walk_forward_asof(
        metric,
        AsofSpec(
            sort_keys=("game_date", "game_id", "event_order"),
            slots=(("_state_id", "_observation", prefix),),
            id_col="_tempo_event_id",
        ),
        factory,
    )
    if not result["_tempo_event_id"].equals(events["_tempo_event_id"]):
        raise AssertionError("PBP as-of result lost chronological event alignment.")
    return result["%s_asof" % prefix].to_numpy(dtype="float64")


def _expanding_mean_factory(min_prior: int = 1) -> Callable[[], Accumulator]:
    class _Mean:
        def __init__(self) -> None:
            self.n = 0
            self._sum = 0.0

        def snapshot(self) -> float:
            return float("nan") if self.n < min_prior else self._sum / self.n

        def update(self, obs: float) -> None:
            if obs is None or pd.isna(obs):
                return
            self._sum += float(obs)
            self.n += 1

    return _Mean


def build_tempo_pbp_asof(possessions: pd.DataFrame) -> pd.DataFrame:
    """Build T1-T4 and S2 as-of features from normalized possession PBP rows.

    ``score_margin`` is the possessing team's score minus its opponent's score
    immediately before the possession.  "Late clock" means a possession ending
    with at most seven seconds left on a 24-second clock, inferred as a duration
    of at least 17 seconds.  Garbage time is a margin of at least 20 points in
    the final 12 regulation minutes.
    """
    _require_columns(possessions)
    events = possessions.copy()
    events["game_date"] = pd.to_datetime(events["game_date"], errors="coerce")
    for column in ("event_order", "elapsed_seconds", "possession_seconds", "score_margin"):
        events[column] = pd.to_numeric(events[column], errors="coerce")
    if events[["game_date", "event_order", "elapsed_seconds", "possession_seconds", "score_margin"]].isna().any().any():
        raise ValueError("PBP possessions contain invalid time, duration, or score-margin values.")
    if (events["possession_seconds"] < 0).any():
        raise ValueError("PBP possession_seconds must be non-negative.")
    events["_tempo_event_id"] = np.arange(len(events), dtype="int64")
    events = events.sort_values(["game_date", "game_id", "event_order"], kind="mergesort").reset_index(drop=True)

    duration = events["possession_seconds"]
    late_clock = (duration >= 24.0 - LATE_CLOCK_REMAINING_SECONDS).astype("float64")
    transition = (duration < TRANSITION_POSSESSION_SECONDS).astype("float64")
    pace = 60.0 / duration.where(duration > 0, np.nan)
    score_state_ids = events["team_id"].astype(str) + "|" + events["score_margin"].map(_score_state)
    garbage = (
        (events["score_margin"].abs() >= GARBAGE_TIME_MARGIN)
        & (events["elapsed_seconds"] >= GARBAGE_TIME_START_SECONDS)
    ).astype("float64")

    output = events[["game_id", "game_date", "event_order", "team_id", "elapsed_seconds"]].copy()
    output["possession_seconds_p25_asof"] = _asof_metric(
        events, duration, "possession_seconds_p25", lambda: QuantileAccumulator(0.25)
    )
    output["possession_seconds_p50_asof"] = _asof_metric(
        events, duration, "possession_seconds_p50", lambda: QuantileAccumulator(0.50)
    )
    output["possession_seconds_p75_asof"] = _asof_metric(
        events, duration, "possession_seconds_p75", lambda: QuantileAccumulator(0.75)
    )
    output["late_clock_share_asof"] = _asof_metric(
        events, late_clock, "late_clock_share", _expanding_mean_factory()
    )
    output["transition_possession_rate_asof"] = _asof_metric(
        events, transition, "transition_possession_rate", _expanding_mean_factory()
    )
    output["tempo_by_score_state_asof"] = _asof_metric(
        events,
        pace,
        "tempo_by_score_state",
        _expanding_mean_factory(MIN_SCORE_STATE_PRIOR_POSSESSIONS),
        score_state_ids,
    )
    output["garbage_time_exposure_prior_asof"] = _asof_metric(
        events, garbage, "garbage_time_exposure_prior", _expanding_mean_factory()
    )
    output["game_date"] = output["game_date"].dt.strftime("%Y-%m-%d")
    return output
