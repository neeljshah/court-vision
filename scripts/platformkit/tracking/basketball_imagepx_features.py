"""Emit basketball teacher proxies from declared source-image foot points."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

_PAN_SHIFT_SHARE = 0.05
_PAN_COHERENCE_MIN = 0.75
_REVERSAL_HYSTERESIS_SHARE = 0.05


def _number(value: float | int | np.number | None) -> float | int | None:
    """Return JSON-safe numbers, replacing an unavailable statistic with null."""
    if value is None or not np.isfinite(value):
        return None
    return float(value) if isinstance(value, (float, np.floating)) else int(value)


def _median(values: pd.Series | list[float] | np.ndarray) -> float | None:
    array = np.asarray(values, dtype=float)
    return float(np.median(array)) if len(array) else None


def _observed_rows(rows: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    observation = rows.get("observation", pd.Series("observed", index=rows.index))
    observed = observation.astype(str).str.lower().eq("observed")
    valid = rows.loc[observed].copy()
    valid["frame"] = pd.to_numeric(valid["frame"], errors="coerce")
    valid["x"] = pd.to_numeric(valid["x"], errors="coerce")
    valid["y"] = pd.to_numeric(valid["y"], errors="coerce")
    valid = valid.dropna(subset=["frame", "track_id", "x", "y"])
    valid["frame"] = valid["frame"].astype(int)
    coasted_frames = set(rows.loc[~observed, "frame"].dropna().astype(int))
    return valid, int((~observed).sum()), len(coasted_frames)


def _successive_pairs(observed: pd.DataFrame) -> pd.DataFrame:
    ordered = observed.sort_values(["track_id", "frame"])
    prior = ordered.groupby("track_id")[["frame", "x", "y"]].shift()
    pairs = ordered.assign(frame_prior=prior["frame"], x_prior=prior["x"],
                           y_prior=prior["y"]).dropna()
    pairs["frame_gap"] = pairs["frame"] - pairs["frame_prior"]
    return pairs[pairs["frame_gap"] > 0]


def _camera_motion(observed: pd.DataFrame, width: float) -> tuple[set[int], list[float]]:
    pairs = _successive_pairs(observed)
    flags: set[int] = set()
    shifts: list[float] = []
    for frame, group in pairs.groupby("frame", sort=True):
        delta = group["x"] - group["x_prior"]
        median_abs = float(delta.abs().median())
        signed = float(delta.median())
        shifts.append(median_abs / width)
        coherence = abs(signed) / median_abs if median_abs else 0.0
        if (len(group) >= 2 and abs(signed) / width >= _PAN_SHIFT_SHARE
                and coherence >= _PAN_COHERENCE_MIN):
            flags.add(int(frame))
    return flags, shifts


def _movement_pairs(observed: pd.DataFrame, pan_frames: set[int], width: float,
                    fps: float) -> tuple[list[float], int, int]:
    pairs = _successive_pairs(observed)
    before_pan = len(pairs[pairs["frame"].isin(pan_frames)])
    pairs = pairs[~pairs["frame"].isin(pan_frames)]
    values = (np.hypot(pairs["x"] - pairs["x_prior"], pairs["y"] - pairs["y_prior"])
              * fps / pairs["frame_gap"] / width)
    return values.tolist(), before_pan, len(set(pairs["frame"]))


def _reversals(centroids: pd.Series, width: float, pan_frames: set[int]) -> int:
    hysteresis = width * _REVERSAL_HYSTERESIS_SHARE
    direction, reversals = 0, 0
    anchor: float | None = None
    previous: int | None = None
    for frame, value in centroids.items():
        if previous is None or any(previous < flagged <= frame for flagged in pan_frames):
            anchor, direction = float(value), 0
        elif anchor is not None:
            delta = float(value) - anchor
            if abs(delta) >= hysteresis:
                new_direction = 1 if delta > 0 else -1
                reversals += int(direction != 0 and new_direction != direction)
                direction, anchor = new_direction, float(value)
        previous = int(frame)
    return reversals


def extract_features(rows: pd.DataFrame, game_id: str, fps: float = 30.0) -> dict:
    """Return declared image-pixel teacher features for one basketball game."""
    required = {"frame", "track_id", "x", "y", "frame_width", "frame_height"}
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError("tracking rows missing columns: {}".format(", ".join(missing)))
    if "coordinate_space" in rows and set(rows["coordinate_space"].dropna()) != {"image_px"}:
        raise ValueError("only coordinate_space=image_px is accepted")
    if rows.empty or fps <= 0:
        raise ValueError("rows must be nonempty and fps must be positive")
    width_values = pd.to_numeric(rows["frame_width"], errors="coerce").dropna().unique()
    height_values = pd.to_numeric(rows["frame_height"], errors="coerce").dropna().unique()
    if len(width_values) != 1 or len(height_values) != 1 or width_values[0] <= 0 or height_values[0] <= 0:
        raise ValueError("one positive frame_width and frame_height are required per game")
    width, height = float(width_values[0]), float(height_values[0])
    frame_numbers = pd.to_numeric(rows["frame"], errors="coerce").dropna().astype(int)
    decoded_frames = int(frame_numbers.max()) + 1
    observed, coasted_rows, coasted_frames = _observed_rows(rows)
    pan_frames, camera_shifts = _camera_motion(observed, width)
    counts = observed.groupby("frame").size()
    players_per_frame = [int(counts.get(frame, 0)) for frame in range(decoded_frames)]
    pace, pace_pan, pace_frames = _movement_pairs(observed, pan_frames, width, fps)
    usable = observed[~observed["frame"].isin(pan_frames)]
    grouped = usable.groupby("frame")
    spread = grouped["x"].std(ddof=0).dropna() / width
    centroids = grouped["x"].mean()
    reversal_count = _reversals(centroids, width, pan_frames)
    minutes = decoded_frames / fps / 60.0
    exclusions = {
        "n_rows_excluded_coasted": coasted_rows,
        "n_frames_with_coasted_rows": coasted_frames,
        "n_frames_excluded_camera_pan": len(pan_frames),
    }
    return {
        "game_id": game_id,
        "coordinate_space": "image_px",
        "frame_width": int(width),
        "frame_height": int(height),
        "fps_assumed": fps,
        "decoded_frames": decoded_frames,
        "exclusions": exclusions,
        "players_on_floor": {
            "median_observed_rows_per_frame": _number(np.median(players_per_frame)),
            "share_frames_count_8_to_10": _number(
                sum(8 <= count <= 10 for count in players_per_frame) / decoded_frames),
            "n_frames_used": decoded_frames,
            "n_excluded": {"coasted_rows": coasted_rows, "camera_pan_frames": 0},
        },
        "pace_proxy": {
            "median_foot_point_displacement_per_second_per_frame_width": _number(_median(pace)),
            "n_frames_used": pace_frames,
            "n_excluded": {"coasted_rows": coasted_rows, "camera_pan_pairs": pace_pan},
        },
        "possession_change_proxy": {
            "centroid_x_direction_reversals_per_minute": _number(reversal_count / minutes),
            "reversal_hysteresis_frame_width_share": _REVERSAL_HYSTERESIS_SHARE,
            "n_frames_used": int(len(centroids)),
            "n_excluded": {"coasted_rows": coasted_rows, "camera_pan_frames": len(pan_frames)},
        },
        "spread_proxy": {
            "median_x_foot_point_std_per_frame_width": _number(spread.median()),
            "n_frames_used": int(len(spread)),
            "n_excluded": {"coasted_rows": coasted_rows, "camera_pan_frames": len(pan_frames)},
        },
        "camera_motion": {
            "flagged_frame_share": _number(len(pan_frames) / decoded_frames),
            "median_all_track_displacement_per_frame_width": _number(_median(camera_shifts)),
            "global_shift_threshold_frame_width_share": _PAN_SHIFT_SHARE,
            "n_frames_used": len(camera_shifts),
            "n_excluded": {"coasted_rows": coasted_rows, "camera_pan_frames": 0},
        },
    }


def main() -> int:
    """Write one image-pixel feature JSON file per tracking table below --in."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="input_root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fps", default=30.0, type=float)
    args = parser.parse_args()
    paths = sorted(args.input_root.glob("*/tracking_data.csv"))
    if not paths:
        raise FileNotFoundError("no */tracking_data.csv below {}".format(args.input_root))
    for path in paths:
        result = extract_features(pd.read_csv(path, low_memory=False), path.parent.name, args.fps)
        output = args.out / path.parent.name / "imagepx_features.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, allow_nan=False, indent=2) + "\n", encoding="utf-8")
        print("wrote {}".format(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
