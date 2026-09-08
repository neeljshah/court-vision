"""G302 attempt 2: separate source resolution from amateur-ness in detector precision.

Three arms over one bin structure, one stride and one processed-frame count:
  arm1 broadcast native 1920x1080 over G273's own inherited span; arm2 the SAME
  decoded frames downscaled to 1280x720 before the detector sees them; arm3 the
  G280 amateur clip at native 1280x720 over its own frames.
arm1 vs arm2 isolates RESOLUTION on identical content; arm2 vs arm3 isolates
AMATEUR-vs-BROADCAST at matched resolution. Both sources are the ones G273 and
G280 measured, re-acquired and qualified by g302_source_identity.py. Measurement
only: no production change, filter, threshold or gate is proposed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import cv2
import numpy as np

SAMPLE_SIZE = 72
BIN_FRAMES = 16
STRIDE = 3
PROCESSED = SAMPLE_SIZE * BIN_FRAMES
BROADCAST_SPAN_START = 19599  # G273's inherited source-frame span is [19599, 23399]
AMATEUR_SPAN_START = 0        # the G280 clip's own frames; its tracker emitted 0, 3, 6, ...
SAMPLE_SEED = 30220260907
BLIND_SEED = 30220907
CROP_W, CROP_H = 512, 640
VERDICTS = ("PLAYER", "PERSON NOT PLAYER IN PLAY", "NOT A PERSON", "CANNOT JUDGE")
ARMS = ("arm1_broadcast_1080_native", "arm2_broadcast_720_downscaled", "arm3_amateur_720_native")
ARM_SPAN_START = {ARMS[0]: BROADCAST_SPAN_START, ARMS[1]: BROADCAST_SPAN_START,
                  ARMS[2]: AMATEUR_SPAN_START}
DOWNSCALE, PRIOR_PLAYER_GAP = (1280, 720), (43 - 25) / SAMPLE_SIZE  # G273 0.597 -> G280b 0.347
POD_WEIGHTS = Path("/workspace/nba-ai-system/yolov8n.pt")  # the pod's pinned copy, read only


def sha256(path: Path) -> str:
    """Digest a file without modifying it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    """Whitespace-independent JSON commitment."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def frame_indices(span_start: int) -> list[int]:
    """The processed source-frame indices of one arm; identical shape in every arm."""
    return [span_start + STRIDE * i for i in range(PROCESSED)]


def open_capture(video: Path, expected: tuple[int, int]) -> cv2.VideoCapture:
    """Open a source and refuse it if its resolution is not the declared one."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not open " + str(video))
    size = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    if size != expected:
        raise RuntimeError("unexpected video size %s for %s" % (size, video))
    return capture


def scan(capture: cv2.VideoCapture, wanted: list[int]):
    """Yield (source_frame, image) for wanted indices by sequential decode, never a seek."""
    position = 0
    for target in sorted(wanted):
        while position < target:
            if not capture.grab():
                raise RuntimeError("source ended before frame %d" % target)
            position += 1
        ok, image = capture.read()
        if not ok:
            raise RuntimeError("could not decode frame %d" % target)
        position += 1
        yield target, image


def detect_pass(detector, video: Path, expected: tuple[int, int], variants: list[tuple[str, Any]],
                span_start: int) -> dict[str, Any]:
    """Run the imported production detector call over one decode of one arm's span."""
    capture = open_capture(video, expected)
    rows: dict[str, list[dict[str, Any]]] = {name: [] for name, _ in variants}
    counts: dict[str, list[int]] = {name: [] for name, _ in variants}
    for source_frame, image in scan(capture, frame_indices(span_start)):
        for name, resize_to in variants:
            frame = cv2.resize(image, resize_to, interpolation=cv2.INTER_AREA) if resize_to else image
            result = detector.model(frame, classes=[0], conf=0.3, verbose=False, imgsz=detector._infer_imgsz,
                                    half=detector._use_half, device=detector._device)
            boxes = result[0].boxes.xyxy.cpu().numpy() if result[0].boxes is not None else np.zeros((0, 4))
            counts[name].append(len(boxes))
            rows[name].extend({"source_frame": int(source_frame),
                               "foot_x_px": float((box[0] + box[2]) / 2), "foot_y_px": float(box[3])}
                              for box in boxes)
    capture.release()
    return {"rows": rows, "frame_counts": counts}


def select_evenly(rows: list[dict[str, Any]], span_start: int) -> list[dict[str, Any]]:
    """One detection per equal-width frame bin, conditioned on nothing downstream."""
    order = frame_indices(span_start)
    rank = {frame: index for index, frame in enumerate(order)}
    rng, selected = random.Random(SAMPLE_SEED), []
    for index in range(SAMPLE_SIZE):
        lo, hi = index * BIN_FRAMES, (index + 1) * BIN_FRAMES - 1
        eligible = [row for row in rows if lo <= rank[row["source_frame"]] <= hi]
        if not eligible:
            raise RuntimeError("empty detector-box bin %d" % (index + 1))
        selected.append({**rng.choice(eligible), "frame_bin": index + 1,
                         "frame_bin_source_frames": [order[lo], order[hi]]})
    return selected


def crop(image: np.ndarray, x: float, y: float) -> np.ndarray:
    """Padded footpoint-centred crop in the arm's own source pixels; never a detector box."""
    left, top = round(x) - CROP_W // 2, round(y) - CROP_H // 2
    padded = cv2.copyMakeBorder(image, CROP_H, CROP_H, CROP_W, CROP_W, cv2.BORDER_CONSTANT)
    out = padded[top + CROP_H:top + 2 * CROP_H, left + CROP_W:left + 2 * CROP_W].copy()
    cv2.drawMarker(out, (CROP_W // 2, CROP_H // 2), (0, 0, 255), cv2.MARKER_CROSS, 19, 2, cv2.LINE_AA)
    cv2.circle(out, (CROP_W // 2, CROP_H // 2), 8, (0, 0, 255), 2, cv2.LINE_AA)
    return out


def render_pass(video: Path, expected: tuple[int, int], picks: dict[str, list[dict[str, Any]]],
                resize: dict[str, Any], output: Path) -> list[dict[str, Any]]:
    """Render every selected location for the arms served by one source."""
    by_frame: dict[int, list[tuple[str, dict[str, Any]]]] = {}
    for arm, rows in picks.items():
        for row in rows:
            by_frame.setdefault(row["source_frame"], []).append((arm, row))
    capture = open_capture(video, expected)
    mapping = []
    for source_frame, image in scan(capture, sorted(by_frame)):
        for arm, row in by_frame[source_frame]:
            target = resize[arm]
            frame = cv2.resize(image, target, interpolation=cv2.INTER_AREA) if target else image
            name = "%s_%03d.jpg" % (arm, row["frame_bin"])
            if not cv2.imwrite(str(output / name), crop(frame, row["foot_x_px"], row["foot_y_px"]),
                               [cv2.IMWRITE_JPEG_QUALITY, 88]):
                raise RuntimeError("could not write crop " + name)
            mapping.append({"arm": arm, "frame_bin": row["frame_bin"],
                            "frame_bin_source_frames": row["frame_bin_source_frames"],
                            "source_frame": source_frame, "foot_x_px": row["foot_x_px"],
                            "foot_y_px": row["foot_y_px"], "crop_size_px": [CROP_W, CROP_H],
                            "render_source": name})
    capture.release()
    return mapping


def source_facts(video: Path) -> dict[str, Any]:
    """A9: full path, byte size and resolution of every input opened."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not open " + str(video))
    facts = {"absolute_path": str(video.resolve()), "bytes": video.stat().st_size,
             "resolution_px": [int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                               int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))],
             "fps": float(capture.get(cv2.CAP_PROP_FPS)), "sha256": sha256(video)}
    capture.release()
    return facts


def _write_packet(packet: Path, blinded: list[dict[str, Any]], commitment: dict[str, Any],
                  counts: dict[str, list[int]]) -> None:
    """Seal the pool: commitment, presentation order, blank verdict sheet, per-frame counts."""
    (packet / "blind_order_commitment.json").write_text(json.dumps(commitment, indent=2) + "\n", encoding="ascii")
    with (packet / "blind_presentation_order.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(("blind_index", "render"))
        writer.writerows((row["blind_index"], row["render"]) for row in blinded)
    with (packet / "blind_verdicts.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(("blind_index", "verdict"))
        writer.writerows((row["blind_index"], "") for row in blinded)
    grids = {arm: frame_indices(ARM_SPAN_START[arm]) for arm in ARMS}
    with (packet / "arm_frame_detection_counts.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(("processed_index",) + tuple("%s_source_frame" % a for a in ARMS)
                        + tuple("%s_boxes" % a for a in ARMS))
        writer.writerows((i,) + tuple(grids[a][i] for a in ARMS) + tuple(counts[a][i] for a in ARMS)
                         for i in range(PROCESSED))


def _write_detection_rows(packet: Path, draws: list[tuple[str, list[dict[str, Any]]]]) -> None:
    """Retain both ARM 1 determinism draws as files a verifier can rehash without the pod."""
    for name, draw in draws:
        with (packet / name).open("w", newline="", encoding="ascii") as handle:
            writer = csv.writer(handle)
            writer.writerow(("source_frame", "foot_x_px", "foot_y_px"))
            writer.writerows((r["source_frame"], r["foot_x_px"], r["foot_y_px"]) for r in draw)


def pin_weights() -> dict[str, Any]:
    """Point ultralytics at the pod's existing yolov8n.pt instead of letting it download one.

    `YOLO("yolov8n.pt")` resolves relative to the working directory and silently fetches an
    unpinned copy when nothing is there, which would make the route unnameable under A11.
    """
    local = Path("yolov8n.pt")
    if not local.exists():
        if not POD_WEIGHTS.exists():
            raise RuntimeError("no pinned yolov8n.pt at " + str(POD_WEIGHTS))
        local.symlink_to(POD_WEIGHTS)
    return {"path": str(local.resolve()), "sha256": sha256(local), "linked_from": str(POD_WEIGHTS)}


def prepare(broadcast: Path, amateur: Path, output: Path) -> dict[str, Any]:
    """Detect all three arms, seal one interleaved blind pool, keep the map private."""
    weights = pin_weights()
    from src.tracking.player_detection import FeetDetector

    packet, private = output / "blind_packet", output / "private"
    renders = packet / "blind_renders"
    for path in (renders, private):
        path.mkdir(parents=True, exist_ok=True)
    detector = FeetDetector([])
    bcast_facts, amat_facts = source_facts(broadcast), source_facts(amateur)
    bcast_size, amat_size = tuple(bcast_facts["resolution_px"]), tuple(amat_facts["resolution_px"])
    first = detect_pass(detector, broadcast, bcast_size, [(ARMS[0], None), (ARMS[1], DOWNSCALE)],
                        BROADCAST_SPAN_START)
    repeat = detect_pass(detector, broadcast, bcast_size, [("repeat", None)], BROADCAST_SPAN_START)
    third = detect_pass(detector, amateur, amat_size, [(ARMS[2], None)], AMATEUR_SPAN_START)
    rows = {ARMS[0]: first["rows"][ARMS[0]], ARMS[1]: first["rows"][ARMS[1]], ARMS[2]: third["rows"][ARMS[2]]}
    counts = {ARMS[0]: first["frame_counts"][ARMS[0]], ARMS[1]: first["frame_counts"][ARMS[1]],
              ARMS[2]: third["frame_counts"][ARMS[2]]}
    determinism = {"arm1_first_sha256": canonical_hash(rows[ARMS[0]]),
                   "arm1_repeat_sha256": canonical_hash(repeat["rows"]["repeat"]),
                   "arm1_first_detections": len(rows[ARMS[0]]),
                   "arm1_repeat_detections": len(repeat["rows"]["repeat"])}
    determinism["byte_identical"] = determinism["arm1_first_sha256"] == determinism["arm1_repeat_sha256"]
    _write_detection_rows(packet, [("arm1_detection_rows_first.csv", rows[ARMS[0]]),
                                   ("arm1_detection_rows_repeat.csv", repeat["rows"]["repeat"])])
    picks = {arm: select_evenly(rows[arm], ARM_SPAN_START[arm]) for arm in ARMS}
    mapping = render_pass(broadcast, bcast_size, {ARMS[0]: picks[ARMS[0]], ARMS[1]: picks[ARMS[1]]},
                          {ARMS[0]: None, ARMS[1]: DOWNSCALE}, renders)
    mapping += render_pass(amateur, amat_size, {ARMS[2]: picks[ARMS[2]]}, {ARMS[2]: None}, renders)
    shuffled = list(range(len(mapping)))
    random.Random(BLIND_SEED).shuffle(shuffled)
    blinded = [{**mapping[src], "blind_index": i + 1, "render": "blind_%03d.jpg" % (i + 1)}
               for i, src in enumerate(shuffled)]
    for row in blinded:
        (renders / row.pop("render_source")).replace(renders / row["render"])
    commitment = {"sample_size_per_arm": SAMPLE_SIZE, "pooled_blind_crops": len(blinded), "arms": list(ARMS),
                  "sample_seed": SAMPLE_SEED, "blind_seed": BLIND_SEED,
                  "unblind_map_sha256": canonical_hash(blinded),
                  "crop_size_px_all_arms": [CROP_W, CROP_H],
                  "frame_indices": {"stride": STRIDE, "processed_frames": PROCESSED,
                                    "bin_frames": BIN_FRAMES, "identical_grid_shape_across_arms": True,
                                    "span_start_per_arm": dict(ARM_SPAN_START),
                                    "arm1_arm2_share_one_decode": True},
                  "sampling": "one uniformly random class-0 conf>=0.3 detector box from each equal-width "
                              "processed-frame bin; no verdict, geometry, position or identity condition"}
    _write_packet(packet, blinded, commitment, counts)
    root = Path(__file__).resolve().parents[3]
    routes = ("scripts/platformkit/tracking/g302_amateur_resolution_attribution.py",
              "src/tracking/player_detection.py")
    summary = {"arms": {arm: {"detections": len(rows[arm]), "processed_frames": PROCESSED,
                              "detections_per_frame": len(rows[arm]) / PROCESSED,
                              "sample_size": SAMPLE_SIZE, "span_start": ARM_SPAN_START[arm],
                              "span_end": frame_indices(ARM_SPAN_START[arm])[-1],
                              "distinct_sample_frames": len({r["source_frame"] for r in picks[arm]}),
                              "empty_frames": sum(n == 0 for n in counts[arm])} for arm in ARMS},
               "inputs": {"broadcast": bcast_facts, "amateur": amat_facts},
               "downscale": {"arm2_target_px": list(DOWNSCALE), "interpolation": "cv2.INTER_AREA"},
               "detector": {"class": 0, "confidence": 0.3, "imgsz": detector._infer_imgsz,
                            "half": bool(detector._use_half), "device": str(detector._device),
                            "call": "imported src.tracking.player_detection.FeetDetector.model, unedited"},
               "arm1_determinism": determinism, "opencv": cv2.__version__, "weights": weights,
               "route_sha256": {route: sha256(root / route) for route in routes},
               "blind_packet": commitment}
    (packet / "arm_detection_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    (private / "unblind_map.json").write_text(json.dumps(blinded, indent=2) + "\n", encoding="ascii")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="G302 attempt 2: detect three arms and seal one blind pool")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--broadcast", type=Path, required=True)
    parser.add_argument("--amateur", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.broadcast, args.amateur, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
