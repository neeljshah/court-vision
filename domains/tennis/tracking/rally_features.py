"""Descriptive rally-level features from our own tennis tracking rows.

Input is the canonical schema written by
:mod:`domains.tennis.tracking.adapter` -- ``frame, track_id, cls, x, y`` with
``x`` and ``y`` already rectified into the adapter's 78 by 36 foot court plane.
In that plane the two baselines sit at ``y = 0`` (near) and ``y = 36`` (far),
the net line is ``y = 18``, and detections are kept out to the run-off bounds
``-5 <= x <= 83`` and ``-5 <= y <= 41``.

HONESTY: every number here is DESCRIPTIVE.  Rally windows, baseline depth,
court coverage, distance run and separation summarise what our tracker saw --
nothing more.  None of them has been validated for prediction lift; until the
foundry gates them on held-out matches they support no outcome, edge, market
or profit claim of any kind.  Segmentation quality is itself unmeasured: we
have no hand-labelled rally boundaries to score it against.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np
import pandas as pd


SCHEMA = ("frame", "track_id", "cls", "x", "y")
FAR_BASELINE_Y = 36.0
MID_COURT_Y = 18.0
DEFAULT_FPS = 30.0
# ponytail: one tunable knob instead of a shot detector.  Broadcast rallies run
# roughly a stroke every 1.5 s; recalibrate per tour/surface once we have
# labelled shot counts, or replace it with real ball-bounce detection.
SECONDS_PER_SHOT = 1.5
DEFAULT_MAX_GAP_FRAMES = 20
DEFAULT_MIN_FRAMES = 10
DEFAULT_MOTION_FT_PER_FRAME = 0.2
BUCKETS = ("1-4", "5-8", "9+")


def _require(df: pd.DataFrame) -> None:
    missing = [column for column in SCHEMA if column not in df.columns]
    if missing:
        raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))


def _players(df: pd.DataFrame) -> pd.DataFrame:
    _require(df)
    return df.loc[df["cls"] == "player", list(SCHEMA)]


def _median(values: Sequence[float]) -> float:
    return float(np.median(values)) if len(values) else math.nan


def _split_runs(frames: Sequence[int], max_gap_frames: int) -> list[tuple[int, int]]:
    """Group ascending frame numbers into runs separated by more than the gap."""
    runs: list[list[int]] = []
    for frame in frames:
        if runs and frame - runs[-1][1] <= max_gap_frames:
            runs[-1][1] = frame
        else:
            runs.append([frame, frame])
    return [(start, end) for start, end in runs]


def _motion_windows(
    players: pd.DataFrame, max_gap_frames: int, motion_ft_per_frame: float
) -> list[tuple[int, int]]:
    """Fall back to bursts of player motion when no ball rows were tracked."""
    active: set[int] = set()
    for _, track in players.groupby("track_id"):
        track = track.sort_values("frame")
        frames = track["frame"].to_numpy(dtype=float)
        x = track["x"].to_numpy(dtype=float)
        y = track["y"].to_numpy(dtype=float)
        if frames.size < 2:
            continue
        gap = np.maximum(np.diff(frames), 1.0)
        speed = np.hypot(np.diff(x), np.diff(y)) / gap
        fast = speed >= motion_ft_per_frame
        active.update(frames[:-1][fast].astype(int).tolist())
        active.update(frames[1:][fast].astype(int).tolist())
    return _split_runs(sorted(active), max_gap_frames)


def baseline_depth(y: np.ndarray) -> np.ndarray:
    """Feet behind a player's own baseline; negative means inside the court.

    The player's end is decided once, from the median of ``y``, so a net
    approach across the mid-court line cannot flip the sign mid-rally.
    """
    y = np.asarray(y, dtype=float)
    if float(np.median(y)) < MID_COURT_Y:
        return -y
    return y - FAR_BASELINE_Y


def _max_separation(sub: pd.DataFrame) -> float:
    """Largest player-to-player distance seen on any single tracked frame."""
    best = math.nan
    for _, group in sub.groupby("frame"):
        points = group[["x", "y"]].to_numpy(dtype=float)
        if len(points) < 2:
            continue
        spread = np.hypot(
            points[:, None, 0] - points[None, :, 0],
            points[:, None, 1] - points[None, :, 1],
        ).max()
        best = float(spread) if math.isnan(best) else max(best, float(spread))
    return best


def rally_segments(
    df: pd.DataFrame,
    max_gap_frames: int = DEFAULT_MAX_GAP_FRAMES,
    min_frames: int = DEFAULT_MIN_FRAMES,
    motion_ft_per_frame: float = DEFAULT_MOTION_FT_PER_FRAME,
) -> list[tuple[int, int]]:
    """Split a tracked match into inclusive ``(start_frame, end_frame)`` rallies.

    Ball rows drive the split when the tracker produced any; otherwise windows
    come from bursts of player motion, which is the weaker signal -- warm-up
    hitting and between-point walking can clear the same threshold.
    """
    _require(df)
    ball = df.loc[df["cls"] == "ball", "frame"]
    if not ball.empty:
        windows = _split_runs(sorted({int(frame) for frame in ball}), max_gap_frames)
    else:
        windows = _motion_windows(_players(df), max_gap_frames, motion_ft_per_frame)
    return [(start, end) for start, end in windows if end - start + 1 >= min_frames]


def rally_features(
    df: pd.DataFrame,
    window: Optional[tuple[int, int]] = None,
    fps: float = DEFAULT_FPS,
) -> dict[str, object]:
    """Summarise one rally window: coverage, depth, distance run, separation.

    ``n_frames`` counts distinct frames actually tracked inside the window, so
    it can trail ``duration_s`` (derived from the window span) whenever the
    adapter dropped frames.  Coverage is the axis-aligned bounding-box area of
    a player's court positions.
    """
    players = _players(df)
    if window is None:
        if players.empty:
            raise ValueError("No player rows to summarise")
        window = (int(players["frame"].min()), int(players["frame"].max()))
    start, end = int(window[0]), int(window[1])
    sub = players[(players["frame"] >= start) & (players["frame"] <= end)]
    per_player: dict[int, dict[str, float]] = {}
    for track_id, track in sub.groupby("track_id"):
        track = track.sort_values("frame")
        x = track["x"].to_numpy(dtype=float)
        y = track["y"].to_numpy(dtype=float)
        depth = baseline_depth(y)
        per_player[int(track_id)] = {
            "n_frames": int(x.size),
            "mean_baseline_depth_ft": float(np.mean(depth)),
            "median_baseline_depth_ft": float(np.median(depth)),
            "coverage_area_sqft": float((x.max() - x.min()) * (y.max() - y.min())),
            "distance_run_ft": float(np.hypot(np.diff(x), np.diff(y)).sum()),
        }
    return {
        "start_frame": start,
        "end_frame": end,
        "n_frames": int(sub["frame"].nunique()),
        "duration_s": float((end - start + 1) / fps),
        "max_separation_ft": _max_separation(sub),
        "players": per_player,
    }


def shots_equivalent(duration_s: float) -> int:
    """Duration-implied stroke count for a rally (never below one)."""
    return max(1, int(round(duration_s / SECONDS_PER_SHOT)))


def rally_bucket(shots: int) -> str:
    """Map a stroke count onto the 1-4 / 5-8 / 9+ rally-length buckets."""
    if shots <= 4:
        return BUCKETS[0]
    if shots <= 8:
        return BUCKETS[1]
    return BUCKETS[2]


def match_aggregates(
    df: pd.DataFrame,
    fps: float = DEFAULT_FPS,
    max_gap_frames: int = DEFAULT_MAX_GAP_FRAMES,
    min_frames: int = DEFAULT_MIN_FRAMES,
    motion_ft_per_frame: float = DEFAULT_MOTION_FT_PER_FRAME,
) -> dict[str, object]:
    """Per-player medians across rallies plus the rally-length distribution.

    Medians are taken over rallies (not over frames), so one long rally cannot
    outvote several short ones.  Buckets are duration-derived, not shot-detected
    -- see ``SECONDS_PER_SHOT``.
    """
    windows = rally_segments(df, max_gap_frames, min_frames, motion_ft_per_frame)
    rallies = [rally_features(df, window, fps) for window in windows]
    buckets = {name: 0 for name in BUCKETS}
    collected: dict[int, list[dict[str, float]]] = {}
    for rally in rallies:
        buckets[rally_bucket(shots_equivalent(float(rally["duration_s"])))] += 1
        for track_id, features in rally["players"].items():  # type: ignore[union-attr]
            collected.setdefault(int(track_id), []).append(features)
    players = {
        track_id: {
            "n_rallies": float(len(items)),
            "median_baseline_depth_ft": _median(
                [item["median_baseline_depth_ft"] for item in items]
            ),
            "median_coverage_area_sqft": _median(
                [item["coverage_area_sqft"] for item in items]
            ),
            "median_distance_run_ft": _median(
                [item["distance_run_ft"] for item in items]
            ),
        }
        for track_id, items in sorted(collected.items())
    }
    return {
        "n_rallies": len(rallies),
        "fps": float(fps),
        "median_rally_seconds": _median([float(r["duration_s"]) for r in rallies]),
        "median_separation_ft": _median(
            [float(r["max_separation_ft"]) for r in rallies]
        ),
        "rally_length_buckets": buckets,
        "players": players,
    }
