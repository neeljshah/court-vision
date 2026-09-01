"""Near-ball pressing proxy over 105x68 metre soccer tracking rows.

Consumes the schema written by ``domains.soccer.tracking.adapter``:
``frame, track_id, cls, x, y`` with ``x``/``y`` in pitch metres. Ball rows
(``cls == "ball"``) are OPTIONAL -- the adapter ball detector is still a stub,
so most real inputs have none.

WHAT THIS IS
------------
A style / conditioning covariate ONLY. It measures how many opposition-side
players sit near the likely ball carrier and how fast they are closing on him,
on the frames the tracker actually emitted. It is in-frame by construction: the
adapter only emits rows for calibrated pitch views, so this is a within-broadcast
sample of pressing, NOT a match-level PPDA and NOT comparable across matches with
different broadcast cuts.

WHAT THIS IS NOT
----------------
Never a win-probability input or claim. The published pressing-to-points
evidence (PPDA and friends) is xG-mediated: pressing shifts shot quality and
location, and the points relationship runs through that mediator with wide
uncertainty. Nothing here is validated against match outcomes, and no outcome
claim may be built on it without a separate leak-free gate.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

PLAYER_CLS = "player"
BALL_CLS = "ball"
DEFAULT_RADIUS_M = 15.0
DEFAULT_FPS = 25.0
DEFAULT_MAX_BALL_DIST_M = 5.0

CARRIER_COLUMNS = ("frame", "track_id", "x", "y", "ball_dist")
PRESSURE_COLUMNS = ("frame", "track_id", "n_opponents", "pressure")
WINDOW_COLUMNS = ("window", "n_frames", "mean", "std", "p10", "p50", "p90", "max")


def _players(rows: pd.DataFrame) -> pd.DataFrame:
    return rows[rows["cls"] == PLAYER_CLS]


def _empty(columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame({name: pd.Series(dtype="float64") for name in columns})


def team_sides(rows: pd.DataFrame) -> pd.Series:
    """Return a track_id -> side label Series.

    Uses a ``team`` column when the caller supplied one. Otherwise falls back to
    splitting tracks at the median of their mean x-position.

    PROXY, NOT IDENTITY: the x-median split only says "these tracks spent the
    observed frames on opposite halves", which is weakly correlated with team
    membership -- it fails on a compressed block, on a phase played inside one
    third, and on any keeper-inclusive sample. Treat a side label as noise, never
    as a roster fact. Upgrade path: kit-colour or re-ID team labels passed in as a
    ``team`` column.
    """
    players = _players(rows)
    if "team" in players.columns:
        return players.groupby("track_id")["team"].first()
    mean_x = players.groupby("track_id")["x"].mean()
    if mean_x.empty:
        return pd.Series(dtype="int64")
    return (mean_x >= mean_x.median()).astype(int).rename("side")


def _nearest(group: pd.DataFrame, point: tuple[float, float]) -> tuple[int, float, float, float]:
    distance = np.hypot(group["x"].to_numpy() - point[0], group["y"].to_numpy() - point[1])
    index = int(np.argmin(distance))
    row = group.iloc[index]
    return int(row["track_id"]), float(row["x"]), float(row["y"]), float(distance[index])


def _proxy_carriers(players: pd.DataFrame, sides: pd.Series) -> pd.DataFrame:
    """Ball-free fallback: nearest player to the midpoint of the two side centroids.

    HONEST CEILING: with no ball rows there is no carrier evidence at all. This
    heuristic assumes the contested point sits between the two side centroids,
    which is false on a switch of play, a counter, and any dead-ball phase, and it
    inherits every error of the x-median side proxy. It is opt-in and unvalidated
    -- this repo has no ground-truth possession label to score it against.
    Upgrade path: a real ball detector in the adapter, then delete this branch.
    """
    if sides.empty or sides.nunique() < 2:
        return _empty(CARRIER_COLUMNS)
    labels = sorted(sides.unique())[:2]
    records: list[dict[str, float]] = []
    for frame, group in players.groupby("frame"):
        side_of = group["track_id"].map(sides)
        left = group[side_of == labels[0]]
        right = group[side_of == labels[1]]
        if left.empty or right.empty:
            continue
        point = (
            float((left["x"].mean() + right["x"].mean()) / 2.0),
            float((left["y"].mean() + right["y"].mean()) / 2.0),
        )
        track_id, x, y, distance = _nearest(group, point)
        records.append(
            {"frame": float(frame), "track_id": float(track_id), "x": x, "y": y, "ball_dist": distance}
        )
    return pd.DataFrame(records, columns=list(CARRIER_COLUMNS)) if records else _empty(CARRIER_COLUMNS)


def carrier_frames(
    rows: pd.DataFrame,
    ball_proxy: bool = False,
    max_ball_dist: float = DEFAULT_MAX_BALL_DIST_M,
) -> pd.DataFrame:
    """Return the likely ball carrier per frame: ``frame, track_id, x, y, ball_dist``.

    With ball rows present the carrier is the nearest player to the ball, dropped
    when that distance exceeds ``max_ball_dist`` (a loose ball belongs to nobody).
    With no ball rows the result is EMPTY unless ``ball_proxy=True`` selects the
    documented, unvalidated fallback in ``_proxy_carriers``.
    """
    players = _players(rows)
    if players.empty:
        return _empty(CARRIER_COLUMNS)
    balls = rows[rows["cls"] == BALL_CLS]
    if balls.empty:
        return _proxy_carriers(players, team_sides(rows)) if ball_proxy else _empty(CARRIER_COLUMNS)
    ball_xy = balls.groupby("frame")[["x", "y"]].mean()
    records: list[dict[str, float]] = []
    for frame, group in players.groupby("frame"):
        if frame not in ball_xy.index:
            continue
        point = (float(ball_xy.at[frame, "x"]), float(ball_xy.at[frame, "y"]))
        track_id, x, y, distance = _nearest(group, point)
        if distance > max_ball_dist:
            continue
        records.append(
            {"frame": float(frame), "track_id": float(track_id), "x": x, "y": y, "ball_dist": distance}
        )
    return pd.DataFrame(records, columns=list(CARRIER_COLUMNS)) if records else _empty(CARRIER_COLUMNS)


def pressure_index(
    rows: pd.DataFrame,
    radius: float = DEFAULT_RADIUS_M,
    fps: float = DEFAULT_FPS,
    ball_proxy: bool = False,
    carriers: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Per carrier frame: opposition players within ``radius``, weighted by closing speed.

    For each opposition-side player within ``radius`` metres of the carrier the
    contribution is ``(1 - distance / radius) * (1 + closing_speed_mps)``, where
    closing speed is the positive part of the frame-over-frame shrink in
    carrier-to-defender distance divided by elapsed seconds. A parked defender
    inside the radius still counts (it is a count, weighted); one sprinting at the
    carrier counts more. The first carrier frame has no predecessor, so its
    closing speed is zero by construction, not by measurement.

    Returns ``frame, track_id, n_opponents, pressure`` -- empty when there are no
    carrier frames.
    """
    if radius <= 0 or fps <= 0:
        raise ValueError("radius and fps must be positive")
    frames = carrier_frames(rows, ball_proxy=ball_proxy) if carriers is None else carriers
    if frames.empty:
        return _empty(PRESSURE_COLUMNS)
    players = _players(rows)
    sides = team_sides(rows)
    by_frame = {int(frame): group for frame, group in players.groupby("frame")}
    previous_positions: dict[int, tuple[float, float]] = {}
    previous_carrier: Optional[tuple[float, float]] = None
    previous_frame: Optional[int] = None
    records: list[dict[str, float]] = []
    for carrier in frames.sort_values("frame").itertuples(index=False):
        frame = int(carrier.frame)
        group = by_frame.get(frame)
        if group is None:
            continue
        carrier_id = int(carrier.track_id)
        carrier_side = sides.get(carrier_id)
        elapsed = None if previous_frame is None else (frame - previous_frame) / fps
        total = 0.0
        count = 0
        for player in group.itertuples(index=False):
            track_id = int(player.track_id)
            if track_id == carrier_id or sides.get(track_id) == carrier_side:
                continue
            distance = float(np.hypot(player.x - carrier.x, player.y - carrier.y))
            if distance > radius:
                continue
            count += 1
            closing = 0.0
            before = previous_positions.get(track_id)
            if elapsed and elapsed > 0 and before is not None and previous_carrier is not None:
                was = float(np.hypot(before[0] - previous_carrier[0], before[1] - previous_carrier[1]))
                closing = max(0.0, (was - distance) / elapsed)
            total += (1.0 - distance / radius) * (1.0 + closing)
        records.append(
            {
                "frame": float(frame),
                "track_id": float(carrier_id),
                "n_opponents": float(count),
                "pressure": float(total),
            }
        )
        previous_positions = {
            int(player.track_id): (float(player.x), float(player.y))
            for player in group.itertuples(index=False)
        }
        previous_carrier = (float(carrier.x), float(carrier.y))
        previous_frame = frame
    return pd.DataFrame(records, columns=list(PRESSURE_COLUMNS)) if records else _empty(PRESSURE_COLUMNS)


def aggregate_pressing(
    rows: pd.DataFrame,
    window_s: float = 60.0,
    fps: float = DEFAULT_FPS,
    radius: float = DEFAULT_RADIUS_M,
    ball_proxy: bool = False,
) -> pd.DataFrame:
    """Mean pressure index and its distribution per fixed time window.

    Windows are indexed from frame 0 in ``window_s`` seconds at ``fps``. A window
    with no carrier frame is absent, not zero -- an unobserved window is missing
    data, and averaging only over emitted frames is the in-frame caveat the module
    docstring names.
    """
    if window_s <= 0:
        raise ValueError("window_s must be positive")
    index = pressure_index(rows, radius=radius, fps=fps, ball_proxy=ball_proxy)
    if index.empty:
        return _empty(WINDOW_COLUMNS)
    per_window = max(1, int(round(window_s * fps)))  # whole frames: float seconds drift on boundaries
    window = (index["frame"] // per_window).astype(int)
    grouped = index.groupby(window)["pressure"]
    return pd.DataFrame(
        {
            "window": grouped.size().index.to_numpy().astype(int),
            "n_frames": grouped.size().to_numpy().astype(float),
            "mean": grouped.mean().to_numpy(),
            "std": grouped.std(ddof=0).to_numpy(),
            "p10": grouped.quantile(0.10).to_numpy(),
            "p50": grouped.quantile(0.50).to_numpy(),
            "p90": grouped.quantile(0.90).to_numpy(),
            "max": grouped.max().to_numpy(),
        }
    )
