"""Blind, all-detection footpoint sample for G273 (no detector invocation)."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from statistics import median
from typing import Any

import cv2
import numpy as np

SAMPLE_SIZE = 72
CROP_WIDTH, CROP_HEIGHT = 512, 640
SAMPLE_SEED, BLIND_SEED = 27320260904, 27320904
VERDICTS = ("PLAYER", "PERSON NOT PLAYER IN PLAY", "NOT A PERSON", "CANNOT JUDGE")


def sha256(path: Path) -> str:
    """Return a file SHA-256 without changing it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def records(input_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load every finite retained G267 detection, without any downstream condition."""
    source = json.loads(input_path.read_text(encoding="ascii"))
    rows = [row for frame in source["frame_records"] for row in frame["detections"] if row["finite"]]
    rows.sort(key=lambda row: (row["source_frame"], row["track_id"], row["foot_x_px"], row["foot_y_px"]))
    expected = source["analysis"]["denominator"]["all_finite_detector_box_feet"]
    if len(rows) != expected:
        raise RuntimeError("finite retained detection count mismatch: %s != %s" % (len(rows), expected))
    return source, rows


def select_evenly(rows: list[dict[str, Any]], sample_size: int = SAMPLE_SIZE) -> list[dict[str, Any]]:
    """Draw one uniformly random detection from each equal-width frame bin."""
    if sample_size <= 0:
        raise ValueError("sample size must be positive")
    low, high = rows[0]["source_frame"], rows[-1]["source_frame"]
    rng, selected = random.Random(SAMPLE_SEED), []
    for index in range(sample_size):
        start = low + (high - low + 1) * index // sample_size
        stop = low + (high - low + 1) * (index + 1) // sample_size - 1
        available = [row for row in rows if start <= row["source_frame"] <= stop]
        if not available:
            raise RuntimeError("empty frame bin %s" % (index + 1))
        selected.append({**rng.choice(available), "frame_bin": index + 1, "frame_bin_inclusive": [start, stop]})
    return selected


def blind_order(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Randomize presentation independently of sampling."""
    indexes = list(range(len(selected)))
    random.Random(BLIND_SEED).shuffle(indexes)
    return [{**selected[original], "blind_index": index + 1} for index, original in enumerate(indexes)]


def crop(image: np.ndarray, foot_x: float, foot_y: float) -> np.ndarray:
    """Return a fixed native-pixel crop with the retained footpoint at its centre."""
    left, top = round(foot_x) - CROP_WIDTH // 2, round(foot_y) - CROP_HEIGHT // 2
    padded = cv2.copyMakeBorder(image, CROP_HEIGHT, CROP_HEIGHT, CROP_WIDTH, CROP_WIDTH, cv2.BORDER_CONSTANT)
    return padded[top + CROP_HEIGHT:top + 2 * CROP_HEIGHT, left + CROP_WIDTH:left + 2 * CROP_WIDTH].copy()


def render(video: Path, ordered: list[dict[str, Any]], output: Path) -> None:
    """Decode only selected source frames and create no detector rectangles."""
    render_dir = output / "blind_renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not open source video")
    for row in ordered:
        capture.set(cv2.CAP_PROP_POS_FRAMES, row["source_frame"])
        ok, image = capture.read()
        if not ok:
            raise RuntimeError("could not decode source frame %s" % row["source_frame"])
        image = crop(image, row["foot_x_px"], row["foot_y_px"])
        cv2.drawMarker(image, (CROP_WIDTH // 2, CROP_HEIGHT // 2), (0, 0, 255), cv2.MARKER_CROSS, 19, 2, cv2.LINE_AA)
        cv2.circle(image, (CROP_WIDTH // 2, CROP_HEIGHT // 2), 8, (0, 0, 255), 2, cv2.LINE_AA)
        path = render_dir / ("blind_%03d.jpg" % row["blind_index"])
        if not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise RuntimeError("could not write " + str(path))
    capture.release()


def unblind_map(ordered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep source identity and positions out of the blinded presentation files."""
    return [{"blind_index": row["blind_index"], "emitted_track_id": row["track_id"],
             "source_frame": row["source_frame"], "frame_bin": row["frame_bin"],
             "frame_bin_inclusive": row["frame_bin_inclusive"], "foot_x_px": row["foot_x_px"],
             "foot_y_px": row["foot_y_px"], "court_x_ft": row["court_x_ft"], "court_y_ft": row["court_y_ft"],
             "render": "blind_renders/blind_%03d.jpg" % row["blind_index"]} for row in ordered]


def prepare(input_path: Path, video: Path, output: Path) -> dict[str, int | str]:
    """Sample, blind, and render from frozen records; it never calls detection or association."""
    source, rows = records(input_path)
    ordered = blind_order(select_evenly(rows))
    output.mkdir(parents=True, exist_ok=True)
    mapping = unblind_map(ordered)
    map_bytes = json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode("ascii")
    (output / "blind_order_commitment.json").write_text(json.dumps({"sample_size": len(ordered), "sample_seed": SAMPLE_SEED, "blind_seed": BLIND_SEED, "unblind_map_sha256": hashlib.sha256(map_bytes).hexdigest(), "sampling": "one uniformly random finite retained detection from each equal-width source-frame bin; no speed, jump, association outcome, position, or ID condition", "crop_policy": "512x640 native-pixel crop centred on retained footpoint; no box drawn, reconstructed, or inferred"}, indent=2) + "\n", encoding="ascii")
    with (output / "blind_presentation_order.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(("blind_index", "render"))
        writer.writerows((row["blind_index"], "blind_renders/blind_%03d.jpg" % row["blind_index"]) for row in ordered)
    with (output / "blind_verdicts.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(("blind_index", "verdict"))
        writer.writerows((row["blind_index"], "") for row in ordered)
    render(video, ordered, output)
    (output / "unblind_map.json").write_text(json.dumps(mapping, indent=2, allow_nan=False) + "\n", encoding="ascii")
    (output / "measurement_summary.json").write_text(json.dumps({"input_artifact": str(input_path), "input_sha256": sha256(input_path), "inherited_source": source["input"], "retained_detection_count": len(rows), "sample_size": len(ordered), "frame_bin_count": len({row["frame_bin"] for row in ordered}), "distinct_sample_frames": len({row["source_frame"] for row in ordered}), "distinct_emitted_ids": len({row["track_id"] for row in ordered}), "crop_size_px": [CROP_WIDTH, CROP_HEIGHT]}, indent=2) + "\n", encoding="ascii")
    return {"retained": len(rows), "sample": len(ordered), "map_sha256": hashlib.sha256(map_bytes).hexdigest()}


def summarize(output: Path) -> dict[str, Any]:
    """Unblind committed verdicts and compute category counts and descriptive positions."""
    mapping = {row["blind_index"]: row for row in json.loads((output / "unblind_map.json").read_text(encoding="ascii"))}
    with (output / "blind_verdicts.csv").open(newline="", encoding="ascii") as handle:
        verdicts = {int(row["blind_index"]): row["verdict"] for row in csv.DictReader(handle)}
    if set(verdicts) != set(mapping) or any(value not in VERDICTS for value in verdicts.values()):
        raise RuntimeError("verdict rows must be complete and use only fixed categories")
    grouped: dict[str, list[dict[str, Any]]] = {verdict: [] for verdict in VERDICTS}
    for index, verdict in verdicts.items():
        grouped[verdict].append(mapping[index])
    def position(rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"n": 0}
        result: dict[str, Any] = {"n": len(rows)}
        for name in ("foot_x_px", "foot_y_px", "court_x_ft", "court_y_ft"):
            values = [float(row[name]) for row in rows]
            result[name] = {"min": min(values), "median": median(values), "max": max(values)}
        return result
    counts = {verdict: len(rows) for verdict, rows in grouped.items()}
    prepared = json.loads((output / "measurement_summary.json").read_text(encoding="ascii"))
    summary = {**prepared, "counts": counts,
               "fractions": {verdict: counts[verdict] / len(mapping) for verdict in VERDICTS},
               "useful_player_yield": {"count": counts["PLAYER"], "fraction": counts["PLAYER"] / len(mapping)},
               "person_or_not_person_not_player": {"count": counts["PERSON NOT PLAYER IN PLAY"] + counts["NOT A PERSON"], "fraction": (counts["PERSON NOT PLAYER IN PLAY"] + counts["NOT A PERSON"]) / len(mapping)},
               "positions_by_class": {verdict: position(rows) for verdict, rows in grouped.items()},
               "unblinded_rows": [{**mapping[index], "verdict": verdicts[index]} for index in sorted(mapping)]}
    (output / "measurement_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="ascii")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "summarize"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = prepare(args.input, args.video, args.output) if args.action == "prepare" else summarize(args.output)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
