"""Cheap image-space player-role filtering for future soccer packets."""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from scripts.platformkit.detection.deterministic import build_soccer_packet_detector, read_packet_frame


@dataclass(frozen=True)
class RoleBox:
    """A person box plus its player-role decision."""

    box: tuple[float, float, float, float]
    role: str
    cue: str


def _valid_boxes(boxes: Sequence[Sequence[float]]) -> list[tuple[float, float, float, float]]:
    return [tuple(map(float, box[:4])) for box in boxes
            if len(box) >= 4 and float(box[2]) > float(box[0]) and float(box[3]) > float(box[1])]


def _pitch_mask(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array((35, 45, 0), dtype=np.uint8),
                       np.array((90, 255, 255), dtype=np.uint8))
    kernel = np.ones((5, 5), dtype=np.uint8)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    if count <= 1:
        return np.zeros_like(closed)
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == largest, 255, 0).astype(np.uint8)


def _foot_on_pitch(mask: np.ndarray, box: tuple[float, float, float, float]) -> bool:
    height, width = mask.shape
    x = int(round((box[0] + box[2]) / 2.0))
    # Detector bottoms often sit on a shoe pixel; sample immediately beneath it
    # to ask whether the contact point is on the playing surface.
    y = int(round(min(box[3] + 4.0, height - 1)))
    if not (0 <= x < width and 0 <= y < height):
        return False
    radius = max(2, round(min(height, width) * 0.003))
    patch = mask[max(0, y - radius):min(height, y + radius + 1),
                 max(0, x - radius):min(width, x + radius + 1)]
    if patch.size == 0 or float(np.mean(patch > 0)) < 0.30:
        return False
    distance = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
    band = max(3.0, min(height, width) * 0.004)
    return float(distance[y, x]) > band


def _torso_color(frame: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray | None:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = box
    left, right = int(x1 + 0.22 * (x2 - x1)), int(x2 - 0.22 * (x2 - x1))
    top, bottom = int(y1 + 0.24 * (y2 - y1)), int(y1 + 0.58 * (y2 - y1))
    left, right = max(0, left), min(width, right)
    top, bottom = max(0, top), min(height, bottom)
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return None
    color = np.mean(crop.reshape(-1, 3), axis=0).astype(np.float32)
    chroma = color / max(float(np.linalg.norm(color)), 1.0)
    # Retain a small brightness term: normalized chroma alone makes black and
    # white kits identical greys, while the term is too weak to dominate hue.
    return np.append(chroma, float(np.mean(color) / 255.0 * 0.55)).astype(np.float32)


def _team_outliers(colors: list[np.ndarray | None]) -> set[int]:
    usable = [(index, color) for index, color in enumerate(colors) if color is not None]
    if len(usable) < 5:
        return set()
    values = np.vstack([color for _, color in usable]).astype(np.float32)
    clusters = min(3, len(usable))
    cv2.setRNGSeed(20260901)
    _, labels, centers = cv2.kmeans(values, clusters, None,
                                    (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.01),
                                    5, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    counts = np.bincount(labels, minlength=clusters)
    team_ids = set(np.argsort(counts)[-min(2, clusters):].tolist())
    ordered_team_ids = sorted(team_ids)
    team_centers = centers[ordered_team_ids]
    radii = []
    for cluster_id, center in zip(ordered_team_ids, team_centers):
        members = values[labels == cluster_id]
        radii.append(float(np.max(np.linalg.norm(members - center, axis=1))))
    strong_limit = 2.0 * max(radii)
    return {index for index, color in usable
            if bool(np.all(np.linalg.norm(team_centers - color, axis=1) > strong_limit))}


def filter_person_boxes(frame: np.ndarray, boxes: Sequence[Sequence[float]]) -> dict[str, object]:
    """Classify raw person boxes with off-pitch or strong-color evidence only."""
    valid = _valid_boxes(boxes)
    mask = _pitch_mask(frame)
    results: list[RoleBox | None] = [None] * len(valid)
    on_pitch: list[tuple[int, tuple[float, float, float, float]]] = []
    for index, box in enumerate(valid):
        if _foot_on_pitch(mask, box):
            on_pitch.append((index, box))
        else:
            results[index] = RoleBox(box, "non_player", "foot_off_pitch_or_touchline")
    colors = [_torso_color(frame, box) for _, box in on_pitch]
    color_outliers = _team_outliers(colors)
    for local_index, (index, box) in enumerate(on_pitch):
        if local_index in color_outliers:
            results[index] = RoleBox(box, "non_player", "jersey_outlier")
        else:
            results[index] = RoleBox(box, "player", "all_cues_pass")
    final = [result for result in results if result is not None]
    return {"raw_boxes": len(final), "player_boxes": sum(item.role == "player" for item in final),
            "boxes": final}


def render_roles(frame: np.ndarray, result: dict[str, object]) -> np.ndarray:
    """Return a role-colored diagnostic frame without modifying the source image."""
    canvas = frame.copy()
    for item in result["boxes"]:
        assert isinstance(item, RoleBox)
        x1, y1, x2, y2 = map(int, item.box)
        color = (0, 200, 0) if item.role == "player" else (0, 0, 220)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        cv2.putText(canvas, "%s:%s" % (item.role, item.cue), (x1, max(12, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)
    return canvas


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def _mean(values: list[int]) -> float:
    return round(float(np.mean(values)), 3)


def measure_packet(packet_root: Path, output_dir: Path) -> dict[str, object]:
    """Rerun the existing detector and measure future producer-only role output."""
    output_dir.mkdir(parents=True, exist_ok=True)
    label_rows = _csv_rows(packet_root / "blind_labels_2026-09-01.csv")
    label_rows += _csv_rows(packet_root / "ext_2026-09-01" / "blind_labels_ext_2026-09-01.csv")
    old_rows = _csv_rows(packet_root / "detector_counts_separate.csv")
    old_rows += _csv_rows(packet_root / "ext_2026-09-01" / "detector_counts_separate_ext.csv")
    old_counts = {row["frame_id"]: int(row.get("raw_boxes") or row["detector_observed_distinct_player_count"])
                  for row in old_rows}
    detector = build_soccer_packet_detector()
    records: list[dict[str, object]] = []
    for row in label_rows:
        frame_id = row["frame_id"]
        folder = packet_root / ("frames" if int(frame_id[-4:]) <= 36 else "ext_2026-09-01/frames")
        frame = read_packet_frame(folder / (frame_id + ".jpg"))
        raw = list(detector(frame))
        filtered = filter_person_boxes(frame, raw)
        records.append({"frame_id": frame_id, "clip": row["clip"], "manual": int(row["manual_player_count"]),
                        "old_raw": old_counts[frame_id], "rerun_raw": int(filtered["raw_boxes"]),
                        "player_boxes": int(filtered["player_boxes"]), "result": filtered, "frame": frame})
    before = [record["manual"] - record["old_raw"] for record in records]
    after = [record["manual"] - record["player_boxes"] for record in records]
    clips: dict[str, dict[str, object]] = {}
    for clip in sorted({str(record["clip"]) for record in records}):
        group = [record for record in records if record["clip"] == clip]
        clips[clip] = {"n": len(group), "delta_before": _mean([item["manual"] - item["old_raw"] for item in group]),
                       "delta_after": _mean([item["manual"] - item["player_boxes"] for item in group]),
                       "flips": sum((item["old_raw"] >= 14) != (item["player_boxes"] >= 14) for item in group)}
    chosen: list[dict[str, object]] = []
    for clip in clips:
        group = [record for record in records if record["clip"] == clip]
        for index in np.linspace(0, len(group) - 1, 4).round().astype(int):
            chosen.append(group[int(index)])
    for record in chosen:
        frame_id = str(record["frame_id"])
        image = render_roles(record["frame"], record["result"])
        cv2.putText(image, "%s manual=%d old_raw=%d players=%d" %
                    (frame_id, record["manual"], record["old_raw"], record["player_boxes"]),
                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(image, "%s manual=%d old_raw=%d players=%d" %
                    (frame_id, record["manual"], record["old_raw"], record["player_boxes"]),
                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 0, 0), 1, cv2.LINE_AA)
        if not cv2.imwrite(str(output_dir / (frame_id + ".jpg")), image):
            raise RuntimeError("could not write render: %s" % frame_id)
    report = {"n": len(records), "pooled_delta_before": _mean(before), "pooled_delta_after": _mean(after),
              "flips_across_14": sum((item["old_raw"] >= 14) != (item["player_boxes"] >= 14) for item in records),
              "rerun_raw_mismatches": sum(item["old_raw"] != item["rerun_raw"] for item in records),
              "per_clip": clips,
              "rendered_frame_ids": [item["frame_id"] for item in chosen],
              "records": [{key: value for key, value in item.items() if key not in ("frame", "result")} for item in records]}
    (output_dir / "measurement.json").write_text(json.dumps(report, indent=2), encoding="ascii")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure-packet", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.measure_packet is None or args.output_dir is None:
        parser.error("--measure-packet and --output-dir are required")
    print(json.dumps(measure_packet(args.measure_packet, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
