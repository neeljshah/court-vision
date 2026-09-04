"""Blind endpoint-crop measurement for G276b, using only retained G267 records."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np


ELIGIBLE_STEPS = 23783
SAMPLE_SIZE = 60
CROP_WIDTH, CROP_HEIGHT = 512, 640
SAMPLE_SEED, BLIND_SEED = 27620260904, 27620904
VERDICTS = ("PLAYER", "PERSON NOT PLAYER IN PLAY", "NOT A PERSON", "CANNOT JUDGE")


def sha256(path: Path) -> str:
    """Return a file SHA-256 without modifying the file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def commitment(rows: list[dict[str, Any]]) -> str:
    """Hash the canonical, withheld step-endpoint map."""
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def eligible_steps(input_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return G272b's structural population with only its speed condition removed."""
    source = json.loads(input_path.read_text(encoding="ascii"))
    tracks: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for frame in source["frame_records"]:
        for row in frame["detections"]:
            if row["finite"]:
                tracks[int(row["track_id"])].append(row)
    steps = []
    for track_id, rows in tracks.items():
        rows.sort(key=lambda row: row["source_frame"])
        for prior, current in zip(rows, rows[1:]):
            gap = current["source_frame"] - prior["source_frame"]
            inside = all(0.0 <= row["court_x_ft"] <= 50.0 and 0.0 <= row["court_y_ft"] <= 94.0
                         for row in (prior, current))
            if gap > 0 and inside:
                steps.append({"emitted_track_id": track_id, "prior_source_frame": prior["source_frame"],
                              "source_frame": current["source_frame"], "prior_foot_x_px": prior["foot_x_px"],
                              "prior_foot_y_px": prior["foot_y_px"], "current_foot_x_px": current["foot_x_px"],
                              "current_foot_y_px": current["foot_y_px"]})
    steps.sort(key=lambda row: (row["source_frame"], row["emitted_track_id"], row["prior_source_frame"]))
    if len(steps) != ELIGIBLE_STEPS:
        raise RuntimeError("eligible step count mismatch: %s != %s" % (len(steps), ELIGIBLE_STEPS))
    return source, steps


def select_evenly(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select one unconditioned retained step per equal-width time bin."""
    low, high = steps[0]["source_frame"], steps[-1]["source_frame"]
    rng, used_ids, selected = random.Random(SAMPLE_SEED), set(), []
    for index in range(SAMPLE_SIZE):
        start = low + (high - low + 1) * index // SAMPLE_SIZE
        stop = low + (high - low + 1) * (index + 1) // SAMPLE_SIZE - 1
        members = [row for row in steps if start <= row["source_frame"] <= stop]
        if not members:
            raise RuntimeError("empty temporal bin %s" % (index + 1))
        unused = [row for row in members if row["emitted_track_id"] not in used_ids]
        chosen = rng.choice(unused or members)
        selected.append({**chosen, "time_bin": index + 1, "time_bin_inclusive": [start, stop]})
        used_ids.add(chosen["emitted_track_id"])
    return selected


def blind_mapping(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pool both endpoints, then randomize them as unrelated presentation items."""
    endpoints = []
    for step_index, step in enumerate(selected, start=1):
        for endpoint in ("prior", "current"):
            endpoints.append({"step_index": step_index, "endpoint": endpoint, "emitted_track_id": step["emitted_track_id"],
                              "source_frame": step["prior_source_frame"] if endpoint == "prior" else step["source_frame"],
                              "foot_x_px": step[endpoint + "_foot_x_px"], "foot_y_px": step[endpoint + "_foot_y_px"],
                              "time_bin": step["time_bin"], "time_bin_inclusive": step["time_bin_inclusive"]})
    random.Random(BLIND_SEED).shuffle(endpoints)
    return [{**row, "blind_index": index} for index, row in enumerate(endpoints, start=1)]


def crop(image: np.ndarray, foot_x: float, foot_y: float) -> np.ndarray:
    """Return a fixed native-pixel crop centred at a retained footpoint."""
    left, top = round(foot_x) - CROP_WIDTH // 2, round(foot_y) - CROP_HEIGHT // 2
    padded = cv2.copyMakeBorder(image, CROP_HEIGHT, CROP_HEIGHT, CROP_WIDTH, CROP_WIDTH, cv2.BORDER_CONSTANT)
    return padded[top + CROP_HEIGHT:top + 2 * CROP_HEIGHT, left + CROP_WIDTH:left + 2 * CROP_WIDTH].copy()


def prepare(input_path: Path, output: Path) -> dict[str, Any]:
    """Create a sealed blind order locally; this action never opens source video."""
    source, steps = eligible_steps(input_path)
    selected = select_evenly(steps)
    mapping = blind_mapping(selected)
    output.mkdir(parents=True, exist_ok=True)
    (output / "blind_order_commitment.json").write_text(json.dumps({
        "sample_size_steps": SAMPLE_SIZE, "sample_size_endpoint_crops": len(mapping),
        "sample_seed": SAMPLE_SEED, "blind_seed": BLIND_SEED, "unblind_map_sha256": commitment(mapping),
        "population": "finite, consecutive same-emitted-ID steps with both retained footpoints inside the declared court; no speed, displacement, jump, or downstream condition",
        "crop_policy": "512x640 native-pixel footpoint-centred crops; no detector box drawn, reconstructed, or inferred",
        "presentation": "both endpoints pooled then shuffled into one order; the presentation CSV has no step, endpoint, ID, frame, or pair field"
    }, indent=2) + "\n", encoding="ascii")
    with (output / "blind_presentation_order.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(("blind_index", "render"))
        writer.writerows((row["blind_index"], "blind_renders/blind_%03d.jpg" % row["blind_index"]) for row in mapping)
    with (output / "blind_verdicts.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(("blind_index", "verdict"))
        writer.writerows((row["blind_index"], "") for row in mapping)
    (output / "unblind_map.json").write_text(json.dumps(mapping, indent=2, allow_nan=False) + "\n", encoding="ascii")
    (output / "measurement_summary.json").write_text(json.dumps({
        "input_artifact": str(input_path), "input_sha256": sha256(input_path), "inherited_source": source["input"],
        "eligible_step_count": len(steps), "sample_size_steps": len(selected),
        "sample_endpoint_crops": len(mapping), "time_bin_count": len({row["time_bin"] for row in selected}),
        "distinct_emitted_ids": len({row["emitted_track_id"] for row in selected}),
        "sample_current_frame_range": [min(row["source_frame"] for row in selected), max(row["source_frame"] for row in selected)],
        "crop_size_px": [CROP_WIDTH, CROP_HEIGHT]
    }, indent=2) + "\n", encoding="ascii")
    return {"eligible_steps": len(steps), "sample_steps": len(selected), "endpoint_crops": len(mapping)}


def render(video: Path, output: Path) -> None:
    """Render sealed blind endpoint crops from the source video on the pod only."""
    mapping = json.loads((output / "unblind_map.json").read_text(encoding="ascii"))
    render_dir = output / "blind_renders"; render_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not open source video")
    for row in mapping:
        capture.set(cv2.CAP_PROP_POS_FRAMES, row["source_frame"])
        ok, image = capture.read()
        if not ok:
            raise RuntimeError("could not decode source frame %s" % row["source_frame"])
        image = crop(image, row["foot_x_px"], row["foot_y_px"])
        cv2.drawMarker(image, (CROP_WIDTH // 2, CROP_HEIGHT // 2), (0, 0, 255), cv2.MARKER_CROSS, 19, 2, cv2.LINE_AA)
        cv2.circle(image, (CROP_WIDTH // 2, CROP_HEIGHT // 2), 8, (0, 0, 255), 2, cv2.LINE_AA)
        if not cv2.imwrite(str(render_dir / ("blind_%03d.jpg" % row["blind_index"])), image, [cv2.IMWRITE_JPEG_QUALITY, 86]):
            raise RuntimeError("could not write crop")
    capture.release()


def _binary_summary(rows: list[dict[str, str]], include_cannot_judge: bool) -> dict[str, Any]:
    grouped: dict[int, dict[str, str]] = defaultdict(dict)
    for row in rows:
        grouped[int(row["step_index"])][row["endpoint"]] = row["verdict"]
    if not include_cannot_judge:
        grouped = {key: value for key, value in grouped.items() if "CANNOT JUDGE" not in value.values()}
    table = {(left, right): 0 for left in (0, 1) for right in (0, 1)}
    for value in grouped.values():
        left = int(value["prior"] == "NOT A PERSON")
        right = int(value["current"] == "NOT A PERSON")
        table[left, right] += 1
    n = sum(table.values()); positives = sum(right * count for (_, right), count in table.items()) + sum(left * count for (left, _), count in table.items())
    rate = positives / (2 * n) if n else 0.0
    either = (table[0, 1] + table[1, 0] + table[1, 1]) / n if n else 0.0
    p1 = (table[1, 0] + table[1, 1]) / n if n else 0.0; p2 = (table[0, 1] + table[1, 1]) / n if n else 0.0
    covariance = table[1, 1] / n - p1 * p2 if n else 0.0
    correlation = covariance / math.sqrt(p1 * (1 - p1) * p2 * (1 - p2)) if 0 < p1 < 1 and 0 < p2 < 1 else None
    return {"steps": n, "table_prior_by_current": {"00": table[0, 0], "01": table[0, 1], "10": table[1, 0], "11": table[1, 1]},
            "per_crop_non_person_rate": rate, "one_or_both_rate": either, "endpoint_phi": correlation,
            "correlation_bracket": [rate, 1 - (1 - rate) ** 2]}


def summarize(output: Path) -> dict[str, Any]:
    """Unblind completed verdicts and calculate joint endpoint results."""
    mapping = {int(row["blind_index"]): row for row in json.loads((output / "unblind_map.json").read_text(encoding="ascii"))}
    sealed = json.loads((output / "blind_order_commitment.json").read_text(encoding="ascii"))
    if commitment([mapping[index] for index in sorted(mapping)]) != sealed["unblind_map_sha256"]:
        raise RuntimeError("unblind map does not match sealed commitment")
    with (output / "blind_verdicts.csv").open(newline="", encoding="ascii") as handle:
        verdicts = {int(row["blind_index"]): row["verdict"] for row in csv.DictReader(handle)}
    if set(verdicts) != set(mapping) or any(value not in VERDICTS for value in verdicts.values()):
        raise RuntimeError("verdict rows must be complete and use fixed categories")
    rows = [{**mapping[index], "verdict": verdicts[index]} for index in sorted(mapping)]
    counts = {verdict: sum(row["verdict"] == verdict for row in rows) for verdict in VERDICTS}
    prepared = json.loads((output / "measurement_summary.json").read_text(encoding="ascii"))
    summary = {**prepared, "counts": counts, "cannot_judge_crops": counts["CANNOT JUDGE"],
               "cannot_judge_steps": len({row["step_index"] for row in rows if row["verdict"] == "CANNOT JUDGE"}),
               "including_cannot_judge": _binary_summary(rows, True), "excluding_cannot_judge": _binary_summary(rows, False),
               "unblinded_rows": rows}
    (output / "measurement_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="ascii")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "render", "summarize")); parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--input", type=Path); parser.add_argument("--video", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        if args.input is None: parser.error("prepare requires --input")
        report: Any = prepare(args.input, args.output)
    elif args.action == "render":
        if args.video is None: parser.error("render requires --video")
        render(args.video, args.output); report = {"rendered": len(list((args.output / "blind_renders").glob("*.jpg")))}
    else:
        report = summarize(args.output)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
