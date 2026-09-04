"""Run and blind a same-source, two-resolution detector precision control."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from domains.basketball.tracking.adapter import BasketballAdapter


SAMPLE_SIZE = 72
SAMPLE_SEED = 28320260904
BLIND_SEED = 28320904
SPAN_START, SPAN_STOP = 19599, 23399
VERDICTS = ("PLAYER", "PERSON NOT PLAYER IN PLAY", "NOT A PERSON", "CANNOT JUDGE")
ARMS = (("broadcast_1080_abs", "1080p", 512, 640),
        ("broadcast_720_fraction", "720p", 341, 427),
        ("broadcast_720_abs", "720p", 512, 640))


def sha256(path: Path) -> str:
    """Return a file digest without changing the source."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    """Return a whitespace-independent JSON commitment."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def crop(image: np.ndarray, x: float, y: float, width: int, height: int) -> np.ndarray:
    """Return a padded footpoint-centred native-pixel crop, never a detector box."""
    left, top = round(x) - width // 2, round(y) - height // 2
    padded = cv2.copyMakeBorder(image, height, height, width, width, cv2.BORDER_CONSTANT)
    result = padded[top + height:top + 2 * height, left + width:left + 2 * width].copy()
    cv2.drawMarker(result, (width // 2, height // 2), (0, 0, 255), cv2.MARKER_CROSS, 19, 2, cv2.LINE_AA)
    cv2.circle(result, (width // 2, height // 2), 8, (0, 0, 255), 2, cv2.LINE_AA)
    return result


def detect(video: Path, capture_start: int, source_start: int, expected_size: tuple[int, int]) -> dict[str, Any]:
    """Run the unchanged G267 detector and association settings over the fixed span."""
    from src.tracking.player_detection import FeetDetector

    detector = FeetDetector([])
    tracker = BasketballAdapter(detector=lambda _image: [])
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not open " + str(video))
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (width, height) != expected_size:
        raise RuntimeError("unexpected video size %s" % ((width, height),))
    capture.set(cv2.CAP_PROP_POS_FRAMES, capture_start)
    rows: list[dict[str, Any]] = []
    frame_counts: list[int] = []
    for offset in range(SPAN_STOP - SPAN_START + 1):
        ok, image = capture.read()
        if not ok:
            raise RuntimeError("source ended at span offset %d" % offset)
        result = detector.model(image, classes=[0], conf=.3, verbose=False, imgsz=detector._infer_imgsz,
                                half=detector._use_half, device=detector._device)
        boxes = result[0].boxes.xyxy.cpu().numpy() if result[0].boxes is not None else []
        centres = [np.array(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)) for box in boxes]
        ids = tracker._assign_tracks(centres)
        source_frame = source_start + offset
        frame_counts.append(len(boxes))
        rows.extend({"source_frame": source_frame, "track_id": int(track_id),
                     "foot_x_px": float((box[0] + box[2]) / 2), "foot_y_px": float(box[3])}
                    for track_id, box in zip(ids, boxes))
    capture.release()
    return {"input": {"absolute_path": str(video.resolve()), "bytes": video.stat().st_size,
                       "resolution_px": [width, height], "capture_start_frame": capture_start,
                       "source_frame_span_inclusive": [SPAN_START, SPAN_STOP]},
            "settings": {"class": 0, "confidence": .3, "imgsz": detector._infer_imgsz,
                         "half": detector._use_half, "device": str(detector._device),
                         "association": "BasketballAdapter nearest-centre assignment as G267"},
            "rows": rows, "processed_frames": len(frame_counts), "empty_processed_frames": sum(n == 0 for n in frame_counts)}


def select_evenly(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Draw one raw detector box per equal-width time bin with no downstream condition."""
    rng, selected = random.Random(SAMPLE_SEED), []
    for index in range(SAMPLE_SIZE):
        start = SPAN_START + (SPAN_STOP - SPAN_START + 1) * index // SAMPLE_SIZE
        stop = SPAN_START + (SPAN_STOP - SPAN_START + 1) * (index + 1) // SAMPLE_SIZE - 1
        eligible = [row for row in rows if start <= row["source_frame"] <= stop]
        if not eligible:
            raise RuntimeError("empty detector-box time bin %d" % (index + 1))
        selected.append({**rng.choice(eligible), "frame_bin": index + 1, "frame_bin_inclusive": [start, stop]})
    return selected


def sample_summary(rows: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, int]:
    """Name detector-box, frame, and emitted-ID denominators for one arm."""
    return {"retained_detector_box_population": len(rows), "processed_frames": SPAN_STOP - SPAN_START + 1,
            "sample_size": len(selected), "frame_bin_count": len({row["frame_bin"] for row in selected}),
            "distinct_sample_frames": len({row["source_frame"] for row in selected}),
            "distinct_sample_track_ids": len({row["track_id"] for row in selected}),
            "distinct_population_track_ids": len({row["track_id"] for row in rows})}


def render(video: Path, selected: list[dict[str, Any]], arm: tuple[str, str, int, int], output: Path) -> list[dict[str, Any]]:
    """Render one crop geometry from selected locations without showing boxes or arm identity."""
    name, resolution, width, height = arm
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not reopen " + str(video))
    rows = []
    for index, row in enumerate(selected, 1):
        capture.set(cv2.CAP_PROP_POS_FRAMES, row["capture_frame"])
        ok, image = capture.read()
        if not ok:
            raise RuntimeError("could not decode crop frame")
        render_name = "%s_%03d.jpg" % (name, index)
        if not cv2.imwrite(str(output / render_name), crop(image, row["foot_x_px"], row["foot_y_px"], width, height),
                           [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise RuntimeError("could not write crop")
        rows.append({"arm": name, "resolution": resolution, "crop_size_px": [width, height],
                     "source_frame": row["source_frame"], "capture_frame": row["capture_frame"],
                     "track_id": row["track_id"], "frame_bin": row["frame_bin"],
                     "frame_bin_inclusive": row["frame_bin_inclusive"], "foot_x_px": row["foot_x_px"],
                     "foot_y_px": row["foot_y_px"], "render_source": render_name})
    capture.release()
    return rows


def prepare(video_1080: Path, video_720: Path, output: Path) -> dict[str, Any]:
    """Detect both arms, make a single sealed blind packet, and retain the private unblind map."""
    output.mkdir(parents=True, exist_ok=True)
    raw_1080 = detect(video_1080, SPAN_START, SPAN_START, (1920, 1080))
    raw_720 = detect(video_720, 0, SPAN_START, (1280, 720))
    (output / "private_detection_1080.json").write_text(json.dumps(raw_1080, separators=(",", ":")) + "\n", encoding="ascii")
    (output / "private_detection_720.json").write_text(json.dumps(raw_720, separators=(",", ":")) + "\n", encoding="ascii")
    selected_1080 = [{**row, "capture_frame": row["source_frame"]} for row in select_evenly(raw_1080["rows"])]
    selected_720 = [{**row, "capture_frame": row["source_frame"] - SPAN_START} for row in select_evenly(raw_720["rows"])]
    renders = output / "blind_renders"; renders.mkdir(exist_ok=True)
    mapping = render(video_1080, selected_1080, ARMS[0], renders)
    mapping += render(video_720, selected_720, ARMS[1], renders)
    mapping += render(video_720, selected_720, ARMS[2], renders)
    order = list(range(len(mapping))); random.Random(BLIND_SEED).shuffle(order)
    blinded = [{**mapping[source], "blind_index": index + 1, "render": "blind_%03d.jpg" % (index + 1)}
               for index, source in enumerate(order)]
    for row in blinded:
        (renders / row["render_source"]).replace(renders / row["render"])
        del row["render_source"]
    commitment = canonical_hash(blinded)
    public = {"sample_size_per_detection_arm": SAMPLE_SIZE, "pooled_blind_crops": len(blinded),
              "sample_seed": SAMPLE_SEED, "blind_seed": BLIND_SEED, "unblind_map_sha256": commitment,
              "sampling": "one uniformly random retained raw class-0 detector box from each equal-width source-frame bin; no verdict, box geometry, position, or ID condition",
              "crop_geometries": {"broadcast_1080_abs": [512, 640], "broadcast_720_fraction": [341, 427], "broadcast_720_abs": [512, 640]}}
    (output / "blind_order_commitment.json").write_text(json.dumps(public, indent=2) + "\n", encoding="ascii")
    with (output / "blind_presentation_order.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(("blind_index", "render")); writer.writerows((row["blind_index"], row["render"]) for row in blinded)
    with (output / "blind_verdicts.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(("blind_index", "verdict")); writer.writerows((row["blind_index"], "") for row in blinded)
    (output / "unblind_map.json").write_text(json.dumps(blinded, indent=2) + "\n", encoding="ascii")
    root = Path(__file__).resolve().parents[3]
    routes = ("scripts/platformkit/tracking/g283_resolution_control.py", "src/tracking/player_detection.py", "domains/basketball/tracking/adapter.py")
    route_hashes = {route: sha256(root / route) for route in routes}
    summary = {"arms": {"broadcast_1080": sample_summary(raw_1080["rows"], selected_1080),
                        "broadcast_720": sample_summary(raw_720["rows"], selected_720)},
               "inputs": {"broadcast_1080": raw_1080["input"], "broadcast_720": raw_720["input"]},
               "route_sha256_by_detection_arm": {"broadcast_1080": route_hashes,
                                                   "broadcast_720": route_hashes}, "blind_packet": public}
    (output / "prepare_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    return summary


def two_proportion(left: int, right: int) -> dict[str, float]:
    """Compute the requested pooled two-sided test for two equal 72-box samples."""
    pooled = (left + right) / (2 * SAMPLE_SIZE)
    se = math.sqrt(pooled * (1 - pooled) * 2 / SAMPLE_SIZE)
    z = ((left - right) / SAMPLE_SIZE) / se if se else 0.0
    return {"pooled_p": pooled, "se": se, "z": z, "nominal_two_sided_p": math.erfc(abs(z) / math.sqrt(2))}


def summarize(output: Path) -> dict[str, Any]:
    """Unblind only after all pooled verdicts have been committed."""
    mapping = json.loads((output / "unblind_map.json").read_text(encoding="ascii"))
    commitment = json.loads((output / "blind_order_commitment.json").read_text(encoding="ascii"))
    if canonical_hash(mapping) != commitment["unblind_map_sha256"]:
        raise RuntimeError("unblind map does not match sealed blind commitment")
    with (output / "blind_verdicts.csv").open(newline="", encoding="ascii") as handle:
        verdicts = {int(row["blind_index"]): row["verdict"] for row in csv.DictReader(handle)}
    if set(verdicts) != {row["blind_index"] for row in mapping} or any(value not in VERDICTS for value in verdicts.values()):
        raise ValueError("all pooled verdicts must use the four fixed G273 categories")
    grouped: dict[str, Counter[str]] = {arm[0]: Counter() for arm in ARMS}
    for row in mapping:
        grouped[row["arm"]][verdicts[row["blind_index"]]] += 1
    counts = {name: {verdict: grouped[name][verdict] for verdict in VERDICTS} for name in grouped}
    tests = {"matched_frame_fraction": {key: two_proportion(counts["broadcast_1080_abs"][key], counts["broadcast_720_fraction"][key]) for key in ("PLAYER", "NOT A PERSON")},
             "same_absolute_pixels": {key: two_proportion(counts["broadcast_1080_abs"][key], counts["broadcast_720_abs"][key]) for key in ("PLAYER", "NOT A PERSON")}}
    result = {"sample_size_per_render_arm": SAMPLE_SIZE, "counts": counts,
              "fractions": {name: {key: value / SAMPLE_SIZE for key, value in values.items()} for name, values in counts.items()},
              "two_proportion_tests": tests, "resolution_player_drop": (counts["broadcast_1080_abs"]["PLAYER"] - counts["broadcast_720_fraction"]["PLAYER"]) / SAMPLE_SIZE,
              "fraction_of_g280b_player_drop_reproduced": ((counts["broadcast_1080_abs"]["PLAYER"] - counts["broadcast_720_fraction"]["PLAYER"]) / SAMPLE_SIZE) / (.597 - .347),
              "nominal_note": "two-sided nominal p values; no multiplicity correction"}
    (output / "blind_measurement_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "summarize")); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--video-1080", type=Path); parser.add_argument("--video-720", type=Path)
    args = parser.parse_args()
    report = prepare(args.video_1080, args.video_720, args.output) if args.action == "prepare" else summarize(args.output)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
