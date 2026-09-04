"""Render blind, fixed-footpoint crop pairs for G272b's frozen box-jump sample."""
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

EXPECTED_BOX_JUMPS = 1454
SAMPLE_SIZE = 48
CROP_WIDTH, CROP_HEIGHT = 512, 640
SAMPLE_SEED, BLIND_SEED = 27220260904, 272200904
VERDICTS = (
    "SAME PERSON, real fast movement",
    "DIFFERENT PERSON",
    "NOT A PERSON in one or both crops",
    "OCCLUDED / CANNOT JUDGE",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def candidates(input_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Reproduce G271's frozen count and return only its >83-px on-court steps."""
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
            speed = math.hypot(current["court_x_ft"] - prior["court_x_ft"], current["court_y_ft"] - prior["court_y_ft"]) * 30.0 / gap
            inside = all(0.0 <= row["court_x_ft"] <= 50.0 and 0.0 <= row["court_y_ft"] <= 94.0 for row in (prior, current))
            displacement = math.hypot(current["foot_x_px"] - prior["foot_x_px"], current["foot_y_px"] - prior["foot_y_px"])
            if gap > 0 and inside and speed > 40.0 and displacement > 83.0:
                steps.append({"track_id": track_id, "prior_source_frame": prior["source_frame"], "source_frame": current["source_frame"], "speed_ft_per_s": speed, "image_bottom_centre_displacement_px": displacement, "prior_foot_x_px": prior["foot_x_px"], "prior_foot_y_px": prior["foot_y_px"], "current_foot_x_px": current["foot_x_px"], "current_foot_y_px": current["foot_y_px"]})
    if len(steps) != EXPECTED_BOX_JUMPS:
        raise RuntimeError("G272b box-jump count mismatch: " + str(len(steps)))
    return source, sorted(steps, key=lambda row: (row["source_frame"], row["track_id"], row["prior_source_frame"]))


def select_evenly(steps: list[dict[str, Any]], sample_size: int = SAMPLE_SIZE) -> list[dict[str, Any]]:
    """Select one seeded candidate per time bin, preferring previously unused emitted IDs."""
    if sample_size > len(steps):
        raise ValueError("sample exceeds candidate set")
    low, high = steps[0]["source_frame"], steps[-1]["source_frame"]
    rng, used_ids, selected = random.Random(SAMPLE_SEED), set(), []
    for bin_index in range(sample_size):
        start = low + (high - low + 1) * bin_index // sample_size
        stop = low + (high - low + 1) * (bin_index + 1) // sample_size - 1
        in_bin = [row for row in steps if start <= row["source_frame"] <= stop]
        if not in_bin:
            raise RuntimeError("empty temporal sample bin")
        unused = [row for row in in_bin if row["track_id"] not in used_ids]
        choice = rng.choice(unused or in_bin)
        selected.append({**choice, "time_bin": bin_index + 1, "time_bin_frames": [start, stop]})
        used_ids.add(choice["track_id"])
    return selected


def blind_order(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign a fixed randomized presentation index without changing the selected rows."""
    indexes = list(range(len(selected)))
    random.Random(BLIND_SEED).shuffle(indexes)
    ordered = []
    for blind_index, original_index in enumerate(indexes, start=1):
        ordered.append({**selected[original_index], "blind_index": blind_index})
    return ordered


def _crop(image: np.ndarray, foot_x: float, foot_y: float) -> np.ndarray:
    center_x, center_y = round(foot_x), round(foot_y)
    left, top = center_x - CROP_WIDTH // 2, center_y - CROP_HEIGHT // 2
    right, bottom = left + CROP_WIDTH, top + CROP_HEIGHT
    padded = cv2.copyMakeBorder(image, CROP_HEIGHT, CROP_HEIGHT, CROP_WIDTH, CROP_WIDTH, cv2.BORDER_CONSTANT)
    left += CROP_WIDTH; right += CROP_WIDTH; top += CROP_HEIGHT; bottom += CROP_HEIGHT
    return padded[top:bottom, left:right].copy()


def _label_crop(crop: np.ndarray, caption: str) -> np.ndarray:
    cv2.circle(crop, (CROP_WIDTH // 2, CROP_HEIGHT // 2), 8, (0, 0, 255), 2, cv2.LINE_AA)
    cv2.drawMarker(crop, (CROP_WIDTH // 2, CROP_HEIGHT // 2), (0, 0, 255), cv2.MARKER_CROSS, 19, 2, cv2.LINE_AA)
    cv2.rectangle(crop, (0, 0), (CROP_WIDTH, 30), (0, 0, 0), -1)
    cv2.putText(crop, caption, (10, 21), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1, cv2.LINE_AA)
    return crop


def _overlap(step: dict[str, Any]) -> float:
    dx = abs(step["image_bottom_centre_displacement_px"])
    # The retained scalar is Euclidean displacement; this is an upper-bound window overlap.
    return max(0.0, 1.0 - dx / min(CROP_WIDTH, CROP_HEIGHT))


def _pair_image(before: np.ndarray, after: np.ndarray, step: dict[str, Any]) -> np.ndarray:
    before = _label_crop(before, "BEFORE: retained footpoint at crop centre")
    after = _label_crop(after, "AFTER: retained footpoint at crop centre")
    panel = np.hstack((before, after))
    footer = np.zeros((76, panel.shape[1], 3), dtype=np.uint8)
    displacement = step["image_bottom_centre_displacement_px"]
    line = "Image displacement %.1f px | Court speed %.1f ft/s" % (displacement, step["speed_ft_per_s"])
    overlap = _overlap(step)
    overlap_text = "Crops overlap heavily (upper-bound window overlap %.0f%%)." % (100 * overlap) if overlap >= .50 else "Crops do not overlap heavily."
    cv2.putText(footer, line, (12, 27), cv2.FONT_HERSHEY_SIMPLEX, .70, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(footer, overlap_text, (12, 58), cv2.FONT_HERSHEY_SIMPLEX, .58, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack((panel, footer))


def _read_frame(capture: cv2.VideoCapture, source_frame: int) -> np.ndarray:
    capture.set(cv2.CAP_PROP_POS_FRAMES, source_frame)
    ok, image = capture.read()
    if not ok:
        raise RuntimeError("could not decode source frame " + str(source_frame))
    return image


def render(video: Path, ordered: list[dict[str, Any]], output: Path) -> None:
    """Decode only sampled frames and write native-resolution crop pairs and blind sheets."""
    render_dir = output / "blind_renders"; render_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not open source video")
    for step in ordered:
        prior = _read_frame(capture, step["prior_source_frame"])
        current = _read_frame(capture, step["source_frame"])
        image = _pair_image(_crop(prior, step["prior_foot_x_px"], step["prior_foot_y_px"]),
                            _crop(current, step["current_foot_x_px"], step["current_foot_y_px"]), step)
        path = render_dir / ("blind_%03d.jpg" % step["blind_index"])
        if not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise RuntimeError("could not write " + str(path))
    capture.release()


def _unblind_rows(source: dict[str, Any], ordered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for step in ordered:
        rows.append({"blind_index": step["blind_index"], "emitted_track_id": step["track_id"], "prior_source_frame": step["prior_source_frame"], "source_frame": step["source_frame"], "time_bin": step["time_bin"], "time_bin_frames": step["time_bin_frames"], "speed_ft_per_s": step["speed_ft_per_s"], "image_bottom_centre_displacement_px": step["image_bottom_centre_displacement_px"], "prior_foot_x_px": step["prior_foot_x_px"], "prior_foot_y_px": step["prior_foot_y_px"], "current_foot_x_px": step["current_foot_x_px"], "current_foot_y_px": step["current_foot_y_px"], "render": "blind_renders/blind_%03d.jpg" % step["blind_index"]})
    return rows


def measure(input_path: Path, video: Path, output: Path) -> dict[str, Any]:
    """Reproduce, select, blind, and render without detector or association calls."""
    source, steps = candidates(input_path)
    selected = select_evenly(steps)
    ordered = blind_order(selected)
    output.mkdir(parents=True, exist_ok=True)
    unblind = _unblind_rows(source, ordered)
    commitment = hashlib.sha256(json.dumps(unblind, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    (output / "blind_order_commitment.json").write_text(json.dumps({"sample_size": len(ordered), "blind_seed": BLIND_SEED, "unblind_map_sha256": commitment, "render_policy": "512x640 full-source-resolution crops centred on retained footpoints; no detector box geometry exists or is inferred"}, indent=2) + "\n", encoding="ascii")
    with (output / "blind_verdicts.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(("blind_index", "verdict"))
        writer.writerows((step["blind_index"], "") for step in ordered)
    with (output / "blind_presentation_order.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(("blind_index", "render"))
        writer.writerows((step["blind_index"], "blind_renders/blind_%03d.jpg" % step["blind_index"]) for step in ordered)
    render_steps = [{**step, **next(row for row in unblind if row["blind_index"] == step["blind_index"])} for step in ordered]
    render(video, render_steps, output)
    (output / "unblind_map.json").write_text(json.dumps(unblind, indent=2, allow_nan=False) + "\n", encoding="ascii")
    (output / "measurement_summary.json").write_text(json.dumps({"input_artifact": str(input_path), "input_sha256": _sha256(input_path), "inherited_source": source["input"], "reproduced_box_jumps": len(steps), "sample_size": len(selected), "distinct_emitted_ids": len({step["track_id"] for step in selected}), "time_bin_count": len({step["time_bin"] for step in selected}), "crop_size_px": [CROP_WIDTH, CROP_HEIGHT]}, indent=2) + "\n", encoding="ascii")
    return {"reproduced_box_jumps": len(steps), "sample_size": len(selected), "distinct_emitted_ids": len({step["track_id"] for step in selected}), "time_bin_count": len({step["time_bin"] for step in selected}), "unblind_map_sha256": commitment}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path); parser.add_argument("--video", required=True, type=Path); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(); report = measure(args.input, args.video, args.output)
    print("G272B_REPRODUCED_BOX_JUMPS=" + str(report["reproduced_box_jumps"]))
    print("G272B_SAMPLE=" + str(report["sample_size"]) + " distinct_ids=" + str(report["distinct_emitted_ids"]))


if __name__ == "__main__":
    main()
