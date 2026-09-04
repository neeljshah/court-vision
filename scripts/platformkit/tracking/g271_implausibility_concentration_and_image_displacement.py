"""Describe where G267's retained on-court implausible steps occur."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.platformkit.tracking import g267_court_space_physical_plausibility as g267
from scripts.platformkit.tracking import g270_implausibility_conditioned_on_position as g270


SEED_FRAME, END_FRAME = 19599, 23399
EXPECTED_BASELINE = {"finite_boxes": 30071, "steps": 29973, "implausible": 4090}
MIN_REQUIRED_IMAGE_PX, MAX_REQUIRED_IMAGE_PX = 17.0, 83.0


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
    return ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _summary(values: list[float]) -> dict[str, float | int | None]:
    return {"n": len(values), "median": _quantile(values, .5), "p90": _quantile(values, .9), "max": max(values) if values else None}


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2 + 1
        for index in order[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean, right_mean = sum(left) / len(left), sum(right) / len(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(sum(value * value for value in left_delta) * sum(value * value for value in right_delta))
    return None if denominator == 0.0 else sum(a * b for a, b in zip(left_delta, right_delta)) / denominator


def _spearman(left: list[float], right: list[float]) -> float | None:
    return _pearson(_rank(left), _rank(right))


def _movement_class(image_displacement_px: float, speed_ft_per_s: float) -> str:
    if speed_ft_per_s <= 40.0:
        return "plausible"
    if image_displacement_px < MIN_REQUIRED_IMAGE_PX:
        return "projection_amplified"
    if image_displacement_px > MAX_REQUIRED_IMAGE_PX:
        return "box_jump"
    return "indeterminate"


def _image_bin(image_displacement_px: float) -> str:
    if image_displacement_px < MIN_REQUIRED_IMAGE_PX:
        return "below_17_px"
    if image_displacement_px > MAX_REQUIRED_IMAGE_PX:
        return "above_83_px"
    return "17_to_83_px_inclusive"


def _enrich_on_court_steps(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for frame in frames:
        for row in frame["detections"]:
            if row["finite"]:
                key = (int(row["track_id"]), int(row["source_frame"]))
                if key in rows_by_key:
                    raise ValueError("retained artifact repeats an emitted ID within a frame")
                rows_by_key[key] = row
    steps = []
    for step in g270._steps(frames, g267.PUBLISHED_H):
        if not (step["prior_inside_court"] and step["current_inside_court"]):
            continue
        prior = rows_by_key[(step["track_id"], step["prior_source_frame"])]
        current = rows_by_key[(step["track_id"], step["source_frame"])]
        image_displacement = math.hypot(current["foot_x_px"] - prior["foot_x_px"], current["foot_y_px"] - prior["foot_y_px"])
        steps.append({
            "track_id": step["track_id"], "prior_source_frame": step["prior_source_frame"],
            "source_frame": step["source_frame"], "frame_gap": step["frame_gap"],
            "speed_ft_per_s": step["speed_ft_per_s"], "image_bottom_centre_displacement_px": image_displacement,
            "strictly_over_40_ft_per_s": step["speed_ft_per_s"] > 40.0,
            "movement_description": _movement_class(image_displacement, step["speed_ft_per_s"]),
        })
    return steps


def _per_track(steps: list[dict[str, Any]], emitted_ids: list[int]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for step in steps:
        grouped[int(step["track_id"])].append(step)
    result = []
    for track_id in emitted_ids:
        track_steps = grouped[track_id]
        impossible = sum(step["strictly_over_40_ft_per_s"] for step in track_steps)
        result.append({"emitted_track_id": track_id, "on_court_same_id_steps": len(track_steps),
                       "on_court_impossible_steps": impossible,
                       "on_court_impossible_fraction": impossible / len(track_steps) if track_steps else None})
    return result


def _length_relation(per_track: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in per_track if row["on_court_same_id_steps"]]
    lengths = [float(row["on_court_same_id_steps"]) for row in usable]
    fractions = [float(row["on_court_impossible_fraction"]) for row in usable]
    ordered = sorted(usable, key=lambda row: row["on_court_same_id_steps"])
    quartiles = []
    for index in range(4):
        start, end = round(index * len(ordered) / 4), round((index + 1) * len(ordered) / 4)
        group = ordered[start:end]
        steps = sum(row["on_court_same_id_steps"] for row in group)
        impossible = sum(row["on_court_impossible_steps"] for row in group)
        quartiles.append({"length_rank_quartile": index + 1, "emitted_ids": len(group),
                          "step_count": steps, "impossible_steps": impossible,
                          "impossible_fraction": impossible / steps if steps else None,
                          "step_count_range": [group[0]["on_court_same_id_steps"], group[-1]["on_court_same_id_steps"]] if group else None})
    return {"ids_with_at_least_one_on_court_step": len(usable),
            "spearman_on_court_step_count_vs_impossible_fraction": _spearman(lengths, fractions),
            "length_rank_quartiles": quartiles}


def analyze(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Reproduce G267/G270 and add complete on-court box-displacement pairs."""
    baseline = g267.analyze(frames)
    observed = {"finite_boxes": baseline["denominator"]["all_finite_detector_box_feet"],
                "steps": baseline["denominator"]["same_track_consecutive_observation_steps"],
                "implausible": baseline["speed_ft_per_s"]["implausible_steps"]}
    if observed != EXPECTED_BASELINE:
        raise RuntimeError("G267 baseline mismatch: " + json.dumps(observed, sort_keys=True))
    on_court = _enrich_on_court_steps(frames)
    impossible = [step for step in on_court if step["strictly_over_40_ft_per_s"]]
    if len(on_court) != 23783 or len(impossible) != 2507:
        raise RuntimeError("G270 on-court baseline mismatch")
    emitted_ids = sorted({int(row["track_id"]) for frame in frames for row in frame["detections"] if row["finite"]})
    per_track = _per_track(on_court, emitted_ids)
    ranked = sorted(per_track, key=lambda row: (-row["on_court_impossible_steps"], row["emitted_track_id"]))
    joint = {"plausible": [step for step in on_court if not step["strictly_over_40_ft_per_s"]], "impossible": impossible}
    distributions = {}
    for name, rows in joint.items():
        image = [step["image_bottom_centre_displacement_px"] for step in rows]
        speed = [step["speed_ft_per_s"] for step in rows]
        distributions[name] = {"paired_step_count": len(rows), "image_bottom_centre_displacement_px": _summary(image),
                               "court_speed_ft_per_s": _summary(speed), "spearman_image_px_vs_court_speed": _spearman(image, speed),
                               "image_displacement_bins": {label: sum(_image_bin(value) == label for value in image) for label in ("below_17_px", "17_to_83_px_inclusive", "above_83_px")}}
    all_impossible = len(impossible)
    split = {label: sum(step["movement_description"] == label for step in impossible) for label in ("box_jump", "projection_amplified", "indeterminate")}
    return {"reproduced_baselines": {"g267_all_same_id": {"steps": observed["steps"], "impossible_steps": observed["implausible"], "fraction": observed["implausible"] / observed["steps"]},
                                       "g270_both_endpoints_on_court": {"steps": len(on_court), "impossible_steps": all_impossible, "fraction": all_impossible / len(on_court)}},
            "population": "retained finite detector-box footpoints and emitted association IDs, not authenticated players",
            "on_court_per_emitted_id": per_track,
            "concentration": {"emitted_ids": len(per_track), "ids_with_zero_on_court_impossible_steps": sum(row["on_court_impossible_steps"] == 0 for row in per_track),
                                "worst_5_impossible_step_share": sum(row["on_court_impossible_steps"] for row in ranked[:5]) / all_impossible,
                                "worst_10_impossible_step_share": sum(row["on_court_impossible_steps"] for row in ranked[:10]) / all_impossible,
                                "ranked_by_on_court_impossible_steps": ranked},
            "track_length_against_impossible_fraction": _length_relation(per_track),
            "joint_image_displacement_px_and_court_speed": distributions,
            "below_17_px_impossible_steps": sum(step["movement_description"] == "projection_amplified" for step in impossible),
            "descriptive_movement_split": {"definition": "<17 px projection-amplified; >83 px box-jump; 17--83 px inclusive indeterminate. Indicative sampled-Jacobian bounds, not causal or production thresholds.",
                                            "counts": split, "fractions": {key: value / all_impossible for key, value in split.items()}},
            "on_court_step_records": on_court}


def measure(input_path: Path) -> dict[str, Any]:
    """Read G267's retained artifact only and return the additive G271 measurement."""
    source = json.loads(input_path.read_text(encoding="ascii"))
    frames = source["frame_records"]
    if [frame["source_frame"] for frame in frames] != list(range(SEED_FRAME, END_FRAME + 1)):
        raise ValueError("input does not have G267's exact contiguous span")
    root = Path(__file__).resolve().parents[3]
    routes = ("scripts/platformkit/tracking/g271_implausibility_concentration_and_image_displacement.py",
              "scripts/platformkit/tracking/g267_court_space_physical_plausibility.py",
              "scripts/platformkit/tracking/g270_implausibility_conditioned_on_position.py")
    return {"input": {"retained_g267_artifact": str(input_path), "sha256": _sha256(input_path), "opened_video": False,
                       "inherited_source_video": source["input"], "source_frame_span_inclusive": [SEED_FRAME, END_FRAME]},
            "route_sha256": {route: _sha256(root / route) for route in routes}, "analysis": analyze(frames)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = measure(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="ascii")
    baseline = report["analysis"]["reproduced_baselines"]
    print("G271_BASELINE=" + str(baseline["g267_all_same_id"]["impossible_steps"]) + "/" + str(baseline["g267_all_same_id"]["steps"]))
    print("G271_ON_COURT=" + str(baseline["g270_both_endpoints_on_court"]["impossible_steps"]) + "/" + str(baseline["g270_both_endpoints_on_court"]["steps"]))


if __name__ == "__main__":
    main()
