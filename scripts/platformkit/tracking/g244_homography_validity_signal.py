"""Recompute G244 validity and G241b abrupt-drop evidence from committed data."""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
LABELS = ROOT / "docs/evidence/tracking/g244_blind_validity_labels_2026-09-04.csv"
G242_TABLE = ROOT / "docs/evidence/tracking/g242_seed_reacquisition_whole_game_artifact/per_sample_table.csv"
G242_MEASUREMENT = ROOT / "docs/evidence/tracking/g242_seed_reacquisition_whole_game_artifact/g242_measurement.json"
G241B_MEASUREMENT = ROOT / "docs/evidence/tracking/g241b_seed_horizon_to_failure_artifact/extended_10000/g241b_measurement.json"
VALIDITY_CLASSES = ("VALID", "INVALID", "CANNOT_JUDGE")
DIAGNOSTICS = ("matches", "inliers", "inlier_ratio", "rms_reprojection_px")
CUT_DISTANCES = (3933, 9823)
G242_SCENE_COUNTS = {
    "normal_court": 52,
    "tight_player_bench_crowd": 29,
    "replay_overhead": 6,
    "graphic_partial": 2,
}


def _summary(values: list[float]) -> dict[str, float | int]:
    """Return the required distribution summary for a nonempty numeric class."""
    if not values:
        raise ValueError("cannot summarize an empty class")
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "p90": float(np.quantile(ordered, 0.9)),
        "max": ordered[-1],
    }


def _read_labels(path: Path) -> dict[int, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labels = {int(row["frame"]): row for row in rows}
    if len(rows) != 89 or len(labels) != 89:
        raise ValueError("G244 requires exactly 89 unique blind labels")
    if {row["validity"] for row in rows} - set(VALIDITY_CLASSES):
        raise ValueError("unexpected validity class")
    return labels


def _read_g242(path: Path) -> dict[int, dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    values = {
        int(row["source_frame"]): {name: float(row[name]) for name in DIAGNOSTICS}
        for row in rows
    }
    if len(rows) != 89 or len(values) != 89:
        raise ValueError("G242 diagnostic denominator is not 89 unique frames")
    return values


def _range_overlap(valid: list[float], invalid: list[float]) -> dict[str, int | float]:
    """Report inclusive cross-class range overlap without fitting a threshold."""
    invalid_min, invalid_max = min(invalid), max(invalid)
    valid_min, valid_max = min(valid), max(valid)
    return {
        "valid_in_invalid_range": sum(invalid_min <= value <= invalid_max for value in valid),
        "invalid_in_valid_range": sum(valid_min <= value <= valid_max for value in invalid),
        "invalid_range_min": invalid_min,
        "invalid_range_max": invalid_max,
        "valid_range_min": valid_min,
        "valid_range_max": valid_max,
    }


def _g242_analysis(labels: dict[int, dict[str, str]], diagnostics: dict[int, dict[str, float]]) -> dict[str, object]:
    if set(labels) != set(diagnostics):
        raise ValueError("blind-label and G242 diagnostic frame sets differ")
    by_class: dict[str, dict[str, list[float]]] = {
        kind: {metric: [] for metric in DIAGNOSTICS} for kind in VALIDITY_CLASSES
    }
    cross_tab: dict[str, dict[str, int]] = {}
    for frame, label in labels.items():
        scene = label["scene_type"]
        cross_tab.setdefault(scene, {kind: 0 for kind in VALIDITY_CLASSES})[label["validity"]] += 1
        for metric, value in diagnostics[frame].items():
            by_class[label["validity"]][metric].append(value)
    distributions = {
        metric: {kind: _summary(by_class[kind][metric]) for kind in VALIDITY_CLASSES}
        for metric in DIAGNOSTICS
    }
    return {
        "validity_counts": {kind: sum(row["validity"] == kind for row in labels.values()) for kind in VALIDITY_CLASSES},
        "scene_validity_cross_tab": cross_tab,
        "g242_scene_inventory_marginals": {
            "blind": {scene: sum(row["scene_type"] == scene for row in labels.values()) for scene in G242_SCENE_COUNTS},
            "g242_reported": G242_SCENE_COUNTS,
        },
        "diagnostics": distributions,
        "valid_invalid_range_overlap": {
            metric: _range_overlap(by_class["VALID"][metric], by_class["INVALID"][metric])
            for metric in DIAGNOSTICS
        },
    }


def _matrix_availability(path: Path) -> dict[str, object]:
    """Audit whether G242 persisted data needed for matrix-shape sanity checks."""
    records = json.loads(path.read_text(encoding="utf-8"))["records"]
    with_matrix = sum("homography" in record or "image_to_court" in record for record in records)
    with_ordered_corners = sum("projected_corners" in record or "corners" in record for record in records)
    return {
        "records": len(records),
        "records_with_matrix": with_matrix,
        "records_with_ordered_projected_corners": with_ordered_corners,
        "status": "NOT_REPRODUCIBLE_FROM_COMMITTED_G242_DATA" if not (with_matrix or with_ordered_corners) else "AVAILABLE",
    }


def _g241b_drops(path: Path) -> dict[str, object]:
    records = json.loads(path.read_text(encoding="utf-8"))["direct_geometry_records"]
    matches = {int(row["distance_frames"]): float(row["direct_seed"]["matches"]) for row in records}
    if sorted(matches) != list(range(1, 10001)):
        raise ValueError("G241b does not contain the required contiguous 1..10000 series")
    drops = {distance: matches[distance - 1] - matches[distance] for distance in range(2, 10001)}
    cut_drops = {str(distance): drops[distance] for distance in CUT_DISTANCES}
    ordinary = [value for distance, value in drops.items() if distance not in CUT_DISTANCES]
    lower, upper = min(cut_drops.values()), max(cut_drops.values())
    ordinary_min, ordinary_max = min(ordinary), max(ordinary)
    return {
        "drop_definition": "matches(distance-1) - matches(distance); positive values are declines",
        "all_single_frame_drops": _summary(list(drops.values())),
        "ordinary_single_frame_drops_excluding_named_cuts": _summary(ordinary),
        "cut_drops": cut_drops,
        "overlap": {
            "named_cuts_inside_ordinary_range": sum(ordinary_min <= value <= ordinary_max for value in cut_drops.values()),
            "ordinary_drops_inside_named_cut_range": sum(lower <= value <= upper for value in ordinary),
            "ordinary_range_min": ordinary_min,
            "ordinary_range_max": ordinary_max,
            "named_cut_range_min": lower,
            "named_cut_range_max": upper,
            "ordinary_drops_at_least_each_cut": {
                str(distance): sum(value >= drop for value in ordinary) for distance, drop in cut_drops.items()
            },
        },
    }


def analyze() -> dict[str, object]:
    """Recompute all G244 result tables from committed inputs."""
    labels = _read_labels(LABELS)
    g242 = _g242_analysis(labels, _read_g242(G242_TABLE))
    return {"g242": g242, "matrix_sanity_availability": _matrix_availability(G242_MEASUREMENT), "g241b": _g241b_drops(G241B_MEASUREMENT)}


def main() -> None:
    print(json.dumps(analyze(), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
