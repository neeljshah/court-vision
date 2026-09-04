"""Condition G267 retained same-ID speeds on court and horizon position."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from scripts.platformkit.tracking import g267_court_space_physical_plausibility as g267


FPS = 30.0
SEED_FRAME, END_FRAME = 19599, 23399
EXPECTED_BASELINE = {"finite_boxes": 30071, "steps": 29973, "implausible": 4090}
HORIZON_BANDS_PX = (1200.0, 1400.0, 1600.0, 1800.0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _quantile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values); position = (len(ordered) - 1) * percentile
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _inside(row: dict[str, Any]) -> bool:
    return 0.0 <= row["court_x_ft"] <= 50.0 and 0.0 <= row["court_y_ft"] <= 94.0


def horizon_distance_px(homography: np.ndarray, row: dict[str, Any]) -> float:
    """Return perpendicular image-footpoint distance to the projective horizon."""
    a, b, c = homography[2]
    return abs(a * row["foot_x_px"] + b * row["foot_y_px"] + c) / math.hypot(a, b)


def local_scale_at_foot(homography: np.ndarray, row: dict[str, Any]) -> tuple[float, float]:
    """Return image-to-court Jacobian singular values at one retained footpoint."""
    x, y = row["foot_x_px"], row["foot_y_px"]
    q = homography @ np.array((x, y, 1.0))
    denominator = q[2]
    if denominator == 0.0:
        return math.inf, math.inf
    dx = (homography[:2, 0] * denominator - q[:2] * homography[2, 0]) / denominator**2
    dy = (homography[:2, 1] * denominator - q[:2] * homography[2, 1]) / denominator**2
    singular = np.linalg.svd(np.column_stack((dx, dy)), compute_uv=False)
    return float(singular[-1]), float(singular[0])


def _steps(frames: list[dict[str, Any]], homography: np.ndarray) -> list[dict[str, Any]]:
    tracks: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for frame in frames:
        for row in frame["detections"]:
            if row["finite"]:
                tracks[int(row["track_id"])].append(row)
    output = []
    for track_id, rows in tracks.items():
        rows.sort(key=lambda row: row["source_frame"])
        for prior, current in zip(rows, rows[1:]):
            gap = current["source_frame"] - prior["source_frame"]
            if gap <= 0:
                raise ValueError("G267 artifact has a nonpositive same-ID frame gap")
            speed = math.hypot(current["court_x_ft"] - prior["court_x_ft"], current["court_y_ft"] - prior["court_y_ft"]) * FPS / gap
            prior_horizon, current_horizon = horizon_distance_px(homography, prior), horizon_distance_px(homography, current)
            scale_row = prior if prior_horizon <= current_horizon else current
            scale_min, scale_max = local_scale_at_foot(homography, scale_row)
            output.append({
                "track_id": track_id, "prior_source_frame": prior["source_frame"], "source_frame": current["source_frame"],
                "frame_gap": gap, "speed_ft_per_s": speed, "prior_inside_court": _inside(prior),
                "current_inside_court": _inside(current), "prior_horizon_distance_px": prior_horizon,
                "current_horizon_distance_px": current_horizon, "minimum_endpoint_horizon_distance_px": min(prior_horizon, current_horizon),
                "local_ft_per_px_min_at_nearest_endpoint": scale_min, "local_ft_per_px_max_at_nearest_endpoint": scale_max,
            })
    return output


def _partition(step: dict[str, Any]) -> str:
    inside_count = int(step["prior_inside_court"]) + int(step["current_inside_court"])
    return ("both_endpoints_inside_court", "one_endpoint_inside_court", "both_endpoints_outside_court")[2 - inside_count]


def _horizon_band(distance: float) -> str:
    lower = 0.0
    for upper in HORIZON_BANDS_PX:
        if distance < upper:
            return f"{int(lower)}_to_{int(upper)}_px"
        lower = upper
    return f"{int(lower)}_px_or_more"


def _summary(steps: list[dict[str, Any]]) -> dict[str, Any]:
    speeds = [step["speed_ft_per_s"] for step in steps]
    scale_min = [step["local_ft_per_px_min_at_nearest_endpoint"] for step in steps]
    scale_max = [step["local_ft_per_px_max_at_nearest_endpoint"] for step in steps]
    count = sum(speed > 40.0 for speed in speeds)
    return {
        "step_count": len(steps), "strictly_over_40_ft_per_s_steps": count,
        "strictly_over_40_ft_per_s_fraction": count / len(steps) if steps else None,
        "speed_ft_per_s_p99": _quantile(speeds, .99), "speed_ft_per_s_max": max(speeds) if speeds else None,
        "local_ft_per_px_at_nearest_horizon_endpoint": {
            "median_principal_scale_min": _quantile(scale_min, .5),
            "median_principal_scale_max": _quantile(scale_max, .5),
            "p99_principal_scale_max": _quantile(scale_max, .99),
        },
    }


def analyze(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Reproduce G267 and return additive position-conditioned step summaries."""
    baseline = g267.analyze(frames)
    observed = {
        "finite_boxes": baseline["denominator"]["all_finite_detector_box_feet"],
        "steps": baseline["denominator"]["same_track_consecutive_observation_steps"],
        "implausible": baseline["speed_ft_per_s"]["implausible_steps"],
    }
    if observed != EXPECTED_BASELINE:
        raise RuntimeError("G267 baseline mismatch: " + json.dumps(observed, sort_keys=True))
    homography = np.array(g267.PUBLISHED_H, dtype=float)
    steps = _steps(frames, homography)
    if len(steps) != observed["steps"] or sum(step["speed_ft_per_s"] > 40.0 for step in steps) != observed["implausible"]:
        raise RuntimeError("position-conditioned step construction changed G267 baseline")
    partitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    bands: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for step in steps:
        partitions[_partition(step)].append(step)
        bands[_horizon_band(step["minimum_endpoint_horizon_distance_px"])].append(step)
    return {
        "reproduced_g267_baseline": {"strictly_over_40_ft_per_s_steps": observed["implausible"], "same_id_steps": observed["steps"], "fraction": observed["implausible"] / observed["steps"]},
        "partition_definition": "both endpoints inside 50 x 94 ft court; one inside/one outside; or both outside",
        "court_position_partitions": {name: _summary(partitions[name]) for name in ("both_endpoints_inside_court", "one_endpoint_inside_court", "both_endpoints_outside_court")},
        "horizon_definition": "image line h31*x + h32*y + h33 = 0 from G267's retained published seed image-to-court homography; band uses the smaller of the two endpoint distances",
        "horizon_distance_bands_px": {name: _summary(bands[name]) for name in ["0_to_1200_px", "1200_to_1400_px", "1400_to_1600_px", "1600_to_1800_px", "1800_px_or_more"]},
        "step_records": steps,
    }


def measure(input_path: Path) -> dict[str, Any]:
    """Load only G267's retained artifact and write an additive G270 artifact."""
    source = json.loads(input_path.read_text(encoding="ascii"))
    frames = source["frame_records"]
    indices = [frame["source_frame"] for frame in frames]
    if indices != list(range(SEED_FRAME, END_FRAME + 1)):
        raise ValueError("input does not have G267's exact contiguous span")
    root = Path(__file__).resolve().parents[3]
    return {
        "input": {"retained_g267_artifact": str(input_path), "sha256": _sha256(input_path), "opened_video": False,
                  "inherited_source_video": source["input"], "population": "finite detector-box footpoints, not authenticated players"},
        "route_sha256": {route: _sha256(root / route) for route in ("scripts/platformkit/tracking/g270_implausibility_conditioned_on_position.py", "scripts/platformkit/tracking/g267_court_space_physical_plausibility.py")},
        "analysis": analyze(frames),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(); report = measure(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="ascii")
    baseline = report["analysis"]["reproduced_g267_baseline"]
    print("G270_BASELINE=" + str(baseline["strictly_over_40_ft_per_s_steps"]) + "/" + str(baseline["same_id_steps"]))


if __name__ == "__main__":
    main()
