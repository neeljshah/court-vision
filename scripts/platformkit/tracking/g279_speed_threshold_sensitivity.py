"""Compute G279's fixed speed-threshold curve from G267's committed JSON."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from scripts.platformkit.tracking import g267_court_space_physical_plausibility as g267
from scripts.platformkit.tracking import g270_implausibility_conditioned_on_position as g270


EXPECTED_G267 = {"finite_boxes": 30071, "steps": 29973, "over_40": 4090}
EXPECTED_G270 = {"both_on_court_steps": 23783, "over_40": 2507}
THRESHOLDS_FTPS = (20.0, 25.0, 26.5, 30.0, 35.0, 40.0, 45.0, 50.0, 60.0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _quantile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _distribution(values: list[float]) -> dict[str, float | None]:
    return {
        "median": _quantile(values, 0.5),
        "p90": _quantile(values, 0.9),
        "p99": _quantile(values, 0.99),
        "p99_9": _quantile(values, 0.999),
        "max": max(values) if values else None,
    }


def _curve(steps: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    speeds = [float(step["speed_ft_per_s"]) for step in steps]
    denominator = len(speeds)
    return {
        str(threshold): {
            "strictly_above_threshold_steps": sum(speed > threshold for speed in speeds),
            "denominator_steps": denominator,
            "fraction": sum(speed > threshold for speed in speeds) / denominator,
        }
        for threshold in THRESHOLDS_FTPS
    }


def analyze(frame_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Reproduce G267/G270 and summarize the requested fixed threshold curve."""
    baseline = g267.analyze(frame_records)
    observed_g267 = {
        "finite_boxes": baseline["denominator"]["all_finite_detector_box_feet"],
        "steps": baseline["denominator"]["same_track_consecutive_observation_steps"],
        "over_40": baseline["speed_ft_per_s"]["implausible_steps"],
    }
    if observed_g267 != EXPECTED_G267:
        raise RuntimeError("G267 reproduction mismatch: " + json.dumps(observed_g267, sort_keys=True))

    steps = g270._steps(frame_records, np.array(g267.PUBLISHED_H, dtype=float))
    both_on_court = [
        step for step in steps
        if step["prior_inside_court"] and step["current_inside_court"]
    ]
    observed_g270 = {
        "both_on_court_steps": len(both_on_court),
        "over_40": sum(step["speed_ft_per_s"] > 40.0 for step in both_on_court),
    }
    if len(steps) != EXPECTED_G267["steps"] or observed_g270 != EXPECTED_G270:
        raise RuntimeError("G270 reproduction mismatch: " + json.dumps(observed_g270, sort_keys=True))

    total_detections = sum(len(frame["detections"]) for frame in frame_records)
    nonfinite_detections = sum(
        not detection["finite"]
        for frame in frame_records
        for detection in frame["detections"]
    )
    one_on_court = sum(
        step["prior_inside_court"] != step["current_inside_court"] for step in steps
    )
    neither_on_court = sum(
        not step["prior_inside_court"] and not step["current_inside_court"]
        for step in steps
    )
    return {
        "population": "detector boxes and emitted association IDs, not authenticated players",
        "method": (
            "consecutive retained finite observations within each same track_id; "
            "speed is court distance times 30 fps divided by actual frame gap"
        ),
        "reproduction": {
            "g267_all_steps_strictly_over_40_ft_per_s": {
                "numerator": observed_g267["over_40"],
                "denominator": observed_g267["steps"],
                "fraction": observed_g267["over_40"] / observed_g267["steps"],
            },
            "g270_both_endpoints_on_court_strictly_over_40_ft_per_s": {
                "numerator": observed_g270["over_40"],
                "denominator": observed_g270["both_on_court_steps"],
                "fraction": observed_g270["over_40"] / observed_g270["both_on_court_steps"],
            },
        },
        "thresholds_ft_per_s": list(THRESHOLDS_FTPS),
        "contextual_references_ft_per_s": {
            "26.5": "NBA average top speed",
            "40.0": "published fixed strict-over threshold",
            "40.7": "Bolt peak",
        },
        "all_finite_same_id_steps": {
            "curve": _curve(steps),
            "speed_distribution_ft_per_s": _distribution(
                [float(step["speed_ft_per_s"]) for step in steps]
            ),
        },
        "both_endpoints_on_court_same_id_steps": {
            "court_condition": "both endpoint feet inside inclusive 0 <= x <= 50 and 0 <= y <= 94 ft",
            "curve": _curve(both_on_court),
            "speed_distribution_ft_per_s": _distribution(
                [float(step["speed_ft_per_s"]) for step in both_on_court]
            ),
        },
        "unmeasurable_or_conditionally_excluded_accounting": {
            "all_retained_detection_records": total_detections,
            "finite_detection_records": total_detections - nonfinite_detections,
            "nonfinite_detection_records": nonfinite_detections,
            "same_id_steps_eligible_after_finite_endpoint_requirement": len(steps),
            "steps_excluded_by_both_endpoints_on_court_condition": len(steps) - len(both_on_court),
            "one_endpoint_on_court_steps": one_on_court,
            "neither_endpoint_on_court_steps": neither_on_court,
            "both_endpoints_on_court_steps": len(both_on_court),
        },
    }


def measure(input_path: Path) -> dict[str, Any]:
    """Load only G267's committed artifact and return G279's additive result."""
    source = json.loads(input_path.read_text(encoding="ascii"))
    root = Path(__file__).resolve().parents[3]
    return {
        "input": {
            "retained_g267_artifact": str(input_path),
            "bytes": input_path.stat().st_size,
            "sha256": _sha256(input_path),
            "opened_video": False,
            "inherited_source_video": source["input"],
        },
        "route_sha256": {
            route: _sha256(root / route)
            for route in (
                "scripts/platformkit/tracking/g279_speed_threshold_sensitivity.py",
                "scripts/platformkit/tracking/g267_court_space_physical_plausibility.py",
                "scripts/platformkit/tracking/g270_implausibility_conditioned_on_position.py",
            )
        },
        "analysis": analyze(source["frame_records"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = measure(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="ascii")
    reproduced = report["analysis"]["reproduction"]
    print("G279_ALL_OVER_40=" + str(reproduced["g267_all_steps_strictly_over_40_ft_per_s"]["numerator"]))
    print("G279_ON_COURT_OVER_40=" + str(reproduced["g270_both_endpoints_on_court_strictly_over_40_ft_per_s"]["numerator"]))


if __name__ == "__main__":
    main()
