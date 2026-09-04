"""Measure fixed 40-ft/s post-hoc reassociation headroom from G267 records."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

from scripts.platformkit.tracking import g267_court_space_physical_plausibility as g267


FPS = 30.0
MAX_SPEED_FTPS = 40.0
SEED_FRAME, END_FRAME = 19599, 23399
EXPECTED_BASELINE = {
    "finite_boxes": 30071,
    "track_ids": 98,
    "steps": 29973,
    "implausible_steps": 4090,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_preregistration(path: Path) -> str:
    """Verify and return the pre-scoring LF-payload seal."""
    content = path.read_bytes().replace(b"\r\n", b"\n")
    marker = b"SHA256 (LF bytes above this line): "
    if content.count(marker) != 1:
        raise ValueError("preregistration has no unique seal line")
    payload, seal = content.split(marker)
    actual = hashlib.sha256(payload).hexdigest()
    if seal.strip().decode("ascii") != actual:
        raise ValueError("preregistration seal mismatch")
    if b"strictly greater than 40.0 ft/s" not in payload:
        raise ValueError("sealed preregistration does not declare 40 ft/s")
    return actual


def _quantile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _track_lengths(frame_records: list[dict[str, Any]]) -> dict[str, float | int | None]:
    counts = Counter(
        int(row["track_id"])
        for frame in frame_records
        for row in frame["detections"]
        if row["finite"]
    )
    lengths = list(counts.values())
    return {
        "track_ids": len(counts),
        "median": _quantile(lengths, 0.5),
        "p90": _quantile(lengths, 0.9),
        "max": max(lengths) if lengths else None,
    }


def _summary(frame_records: list[dict[str, Any]]) -> dict[str, Any]:
    analysis = g267.analyze(frame_records)
    speed = analysis["speed_ft_per_s"]
    return {
        "finite_detector_boxes": analysis["denominator"]["all_finite_detector_box_feet"],
        "track_length_distribution_observations": _track_lengths(frame_records),
        "same_id_steps": analysis["denominator"]["same_track_consecutive_observation_steps"],
        "implausible_steps_strictly_over_40_ft_per_s": speed["implausible_steps"],
        "implausible_step_fraction_strictly_over_40_ft_per_s": speed["implausible_fraction"],
        "unassociated_detector_boxes": 0,
    }


def reproduce_baseline(frame_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Recompute and enforce G267's named retained-artifact baseline."""
    summary = _summary(frame_records)
    checks = {
        "finite_boxes": summary["finite_detector_boxes"],
        "track_ids": summary["track_length_distribution_observations"]["track_ids"],
        "steps": summary["same_id_steps"],
        "implausible_steps": summary["implausible_steps_strictly_over_40_ft_per_s"],
    }
    if checks != EXPECTED_BASELINE:
        raise RuntimeError("G267 baseline mismatch: " + json.dumps(checks, sort_keys=True))
    return summary


def _assignment_cost(
    current: list[dict[str, Any]], last_by_track: dict[int, dict[str, Any]]
) -> tuple[np.ndarray, list[int]]:
    track_ids = sorted(last_by_track)
    rows, tracks = len(current), len(track_ids)
    costs = np.full((rows, tracks + rows), 3.0, dtype=float)
    costs[:, tracks:] = 2.0
    for row_index, row in enumerate(current):
        for column, track_id in enumerate(track_ids):
            prior = last_by_track[track_id]
            gap = int(row["source_frame"]) - int(prior["source_frame"])
            if gap <= 0:
                continue
            distance = math.hypot(
                row["court_x_ft"] - prior["court_x_ft"],
                row["court_y_ft"] - prior["court_y_ft"],
            )
            permitted = MAX_SPEED_FTPS * gap / FPS
            if distance <= permitted:
                # The tiny rank term makes equal-distance choices reproducible.
                rank = (column + 1) / ((tracks + 1) ** (row_index + 1))
                costs[row_index, column] = distance / permitted + 1e-9 * rank
    return costs, track_ids


def reassociate(frame_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply the sealed maximum-cardinality, minimum-normalized-distance rule."""
    last_by_track: dict[int, dict[str, Any]] = {}
    next_track_id = 0
    output: list[dict[str, Any]] = []
    for source in sorted(frame_records, key=lambda item: int(item["source_frame"])):
        finite = [dict(row) for row in source["detections"] if row["finite"]]
        assignments: dict[int, int] = {}
        if finite and last_by_track:
            costs, track_ids = _assignment_cost(finite, last_by_track)
            matched_rows, matched_columns = linear_sum_assignment(costs)
            for row_index, column in zip(matched_rows.tolist(), matched_columns.tolist()):
                if column < len(track_ids) and costs[row_index, column] < 2.0:
                    assignments[row_index] = track_ids[column]
        for row_index, row in enumerate(finite):
            track_id = assignments.get(row_index)
            if track_id is None:
                track_id = next_track_id
                next_track_id += 1
            row["emitted_track_id"] = row["track_id"]
            row["track_id"] = track_id
            row["reassociated_track_id"] = track_id
            last_by_track[track_id] = row
        nonfinite = [dict(row) for row in source["detections"] if not row["finite"]]
        output.append({**source, "detections": finite + nonfinite})
    return output


def load_frame_records(path: Path) -> list[dict[str, Any]]:
    """Load the fixed G267 retained records and enforce its declared span."""
    report = json.loads(path.read_text(encoding="ascii"))
    frames = report["frame_records"]
    indices = [int(frame["source_frame"]) for frame in frames]
    if len(frames) != END_FRAME - SEED_FRAME + 1 or indices != list(range(SEED_FRAME, END_FRAME + 1)):
        raise ValueError("input does not have G267's exact contiguous frame span")
    return frames


def measure(input_path: Path, preregistration: Path, preregistration_commit: str) -> dict[str, Any]:
    """Reproduce G267 then score only the sealed reassociation measurement."""
    prereg_seal = verify_preregistration(preregistration)
    before_frames = load_frame_records(input_path)
    before = reproduce_baseline(before_frames)
    after_frames = reassociate(before_frames)
    after = _summary(after_frames)
    if after["finite_detector_boxes"] != before["finite_detector_boxes"]:
        raise RuntimeError("reassociation lost a detector box")
    return {
        "input": {
            "path": str(input_path), "sha256": _sha256(input_path),
            "source_frame_span_inclusive": [SEED_FRAME, END_FRAME],
            "population": "retained finite detector-box footpoints, not authenticated players",
        },
        "sealed_constraint": {
            "strictly_over_ft_per_s": MAX_SPEED_FTPS,
            "preregistration_path": str(preregistration),
            "preregistration_lf_payload_sha256": prereg_seal,
            "preregistration_commit": preregistration_commit,
        },
        "algorithm": "ascending-frame maximum-cardinality one-to-one court-space matching, then minimum normalized distance; unmatched boxes start IDs; no dropped boxes or extra retirement limit",
        "before": before,
        "after": after,
        "reassociated_frame_records": after_frames,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = measure(args.input, args.preregistration, args.preregistration_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="ascii")
    print("G269_BASELINE_IMPLAUSIBLE=" + str(report["before"]["implausible_steps_strictly_over_40_ft_per_s"]))
    print("G269_AFTER_IMPLAUSIBLE=" + str(report["after"]["implausible_steps_strictly_over_40_ft_per_s"]))


if __name__ == "__main__":
    main()
