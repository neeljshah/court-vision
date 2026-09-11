"""G380 branch controls: force each provenance branch and check the stamped label.

Run from inside the PATCHED scratch tree so `src.tracking.advanced_tracker` is
the patched producer, not the landed one:

  cd /workspace/g380_scratch/armA
  python3 -m scripts.platformkit.tracking.g380_controls --out <dir>/controls.csv

Every one of the five sealed branches is CONSTRUCT: fresh detection, coast, clamp,
subpixel hold and id merge.  The coast control drives the REAL patched
`get_players_pos` with synthetic frames and a stubbed empty YOLO result, so the
producer takes its own YOLO-blackout optical-flow gap-fill path; the label is read
back from the store the producer stamped, never asserted.
"""
from __future__ import annotations

import argparse
import csv
import json
import threading
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking import g380_provenance as prov

FIELDS = ("control", "kind", "branch_forced", "expected_label", "observed_label",
          "observed_branch", "result")
COAST_TICK = 101
COAST_BOXES = {0: (580, 300, 700, 420), 1: (300, 260, 410, 380)}
_FLOW_ANCHOR = (640.0, 419.0)


class _Slot:
    """The attributes the producer reads from a player object on this path."""

    def __init__(self, pid):
        self.ID, self.positions, self.previous_bb = pid, {}, None
        self.has_ball, self.team = False, "green"


class _EmptyYolo:
    """A YOLO result carrying no boxes -- the producer's blackout frame."""

    boxes = None
    keypoints = None


def _detector():
    """Build an AdvancedFeetDetector without its YOLO/OSNet constructor."""
    from src.tracking.advanced_tracker import AdvancedFeetDetector

    players = [_Slot(0), _Slot(1)]
    det = AdvancedFeetDetector.__new__(AdvancedFeetDetector)
    det.players = players
    det._lost_ages = {0: 0, 1: 0}
    det._freeze_age, det._kalmans, det._appearances = {}, {}, {}
    det._stable_frames, det._stable_skip = {}, {}
    det._gallery, det._gallery_ages, det._gallery_last_pos = {}, {}, {}
    det._flow_pts, det._pos_source = {}, {}
    det._jersey_buf = None
    det._update_appearance = lambda *a, **k: None   # appearance is irrelevant to provenance
    return det


def _det_payload(x, y):
    return {"bbox": (10, 20, 40, 90), "homo": (x, y),
            "crop_bgr": np.zeros((8, 8, 3), dtype=np.uint8), "foot_xy": (25, 90)}


def _activate(det, slot, timestamp, x, y):
    det._activate_slot(slot, _det_payload(x, y), timestamp)
    return det._pos_source.get((slot, timestamp), ("MISSING", "", ""))


def scene_image(height: int = 720, width: int = 1280) -> np.ndarray:
    """A deterministic textured frame: flat pixels give optical flow no gradient."""
    rng = np.random.RandomState(380)
    base = np.full((height, width, 3), 46, dtype=np.int16)
    return np.clip(base + rng.randint(-26, 27, base.shape), 0, 255).astype(np.uint8)


def coast_scene():
    """Force the in-run coast branch through the real patched `get_players_pos`.

    Slot 0 was detected, is lost one frame, and holds an optical-flow anchor, so
    the producer gap-fill writes its position this tick -- that IS the coast.
    Slot 1 was stamped on an earlier tick and no branch writes it now, so its row
    carries an older position and must read back HELD, never dropped.
    """
    det = _detector()
    det._gallery_ttl = 300
    det.model = det._pose_model = None
    det._use_pose, det._pose_frame_counter = False, 0
    det._yolo_imgsz = det._infer_imgsz = 640
    det._use_half = False
    det._prefetch_thread, det._prefetch_lock = None, threading.Lock()
    det._yolo_frame_buf = deque()
    det._yolo_result_buf = deque([([_EmptyYolo()], False)])
    det._kf_pred = {}
    det._render = lambda frame, map_2d, timestamp: (frame, map_2d)

    frame = scene_image()
    det._prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    det.players[0].previous_bb = COAST_BOXES[0]
    det._flow_pts[0] = np.array([list(_FLOW_ANCHOR)], dtype=np.float32)
    prov.stamp(det._pos_source, 1, COAST_TICK - 1, "DETECTION",
               "src/tracking/advanced_tracker.py:_activate_slot")
    eye = np.eye(3, dtype=np.float64)
    det.get_players_pos(eye, eye, frame, COAST_TICK, np.zeros((720, 1280, 3), dtype=np.uint8))
    return det, frame


def controls() -> list:
    rows, det = [], _detector()

    label, branch, event = _activate(det, 0, 1, 100, 100)
    rows.append({"control": "fresh_detection", "kind": "CONSTRUCT",
                 "branch_forced": "advanced_tracker.py:_activate_slot fresh",
                 "expected_label": "DETECTION", "observed_label": label,
                 "observed_branch": branch})
    rows.append({"control": "fresh_detection_names_its_event", "kind": "CONSTRUCT",
                 "branch_forced": "advanced_tracker.py:_activate_slot matched detection",
                 "expected_label": "1_10_20_40_90", "observed_label": event,
                 "observed_branch": branch})

    label, branch, _ = _activate(det, 0, 2, 100000, 100000)
    rows.append({"control": "clamp", "kind": "CONSTRUCT",
                 "branch_forced": "advanced_tracker.py:_activate_slot velocity clamp",
                 "expected_label": "CLAMP", "observed_label": label,
                 "observed_branch": branch})

    label, branch = prov.resolve_emitted("DETECTION", "x", (7, 9), (7, 9))
    rows.append({"control": "subpixel_hold", "kind": "CONSTRUCT",
                 "branch_forced": "unified_pipeline.py:subpixel_hold",
                 "expected_label": "SUBPIXEL", "observed_label": label,
                 "observed_branch": branch})

    store = {}
    prov.stamp(store, 3, 10, "DETECTION", "b")
    label, branch, _ = prov.label_for(store, 3, 11)
    rows.append({"control": "carried_position", "kind": "CONSTRUCT",
                 "branch_forced": "no branch wrote this tick",
                 "expected_label": "HELD", "observed_label": label,
                 "observed_branch": branch})

    label, branch, _ = prov.label_for({}, 4, 12)
    rows.append({"control": "missing_event", "kind": "CONSTRUCT",
                 "branch_forced": "no provenance for the slot",
                 "expected_label": "UNKNOWN", "observed_label": label,
                 "observed_branch": branch})

    merge = {}
    prov.stamp(merge, 0, 5, "DETECTION", "b")
    prov.drop(merge, 0, 5)
    prov.stamp(merge, 1, 5, "PREDICTION", "src/tracking/advanced_tracker.py:id_merge")
    label, branch, _ = prov.label_for(merge, 1, 5)
    rows.append({"control": "id_merge_stamp", "kind": "CONSTRUCT",
                 "branch_forced": "advanced_tracker.py:id_merge survivor",
                 "expected_label": "PREDICTION", "observed_label": label,
                 "observed_branch": branch})
    rows.append({"control": "id_merge_loser_dropped", "kind": "CONSTRUCT",
                 "branch_forced": "advanced_tracker.py:id_merge removed row",
                 "expected_label": "HELD", "observed_label": prov.label_for(merge, 0, 5)[0],
                 "observed_branch": ""})

    coast, _frame = coast_scene()
    label, branch, _ = prov.label_for(coast._pos_source, 0, COAST_TICK)
    rows.append({"control": "coast", "kind": "CONSTRUCT",
                 "branch_forced": "advanced_tracker.py:flow_gapfill_render in-run blackout frame",
                 "expected_label": "PREDICTION", "observed_label": label,
                 "observed_branch": branch})
    held, held_branch, _ = prov.label_for(coast._pos_source, 1, COAST_TICK)
    rows.append({"control": "coast_scene_unwritten_slot", "kind": "CONSTRUCT",
                 "branch_forced": "in-run tick no branch wrote",
                 "expected_label": "HELD", "observed_label": held,
                 "observed_branch": held_branch})

    for row in rows:
        row["result"] = "PASS" if row["observed_label"] == row["expected_label"] else "FAIL"
    return rows


def _write(path: Path, fields: tuple, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(rows)


TRACE_FIELDS = ("slot", "tick", "traced_label", "expected_from_stamps", "agree")


def trace_diff(trace_path: Path) -> tuple:
    """Diff the independent import-time trace against the stamps it also saw.

    The hook logs every `stamp` (S) and every `label_for` (L) without the producer
    knowing.  A read must return the branch that stamped that (slot, tick), or
    HELD once the slot has been stamped at all, or UNKNOWN.  Nothing here reads
    controls.csv, so the check is independent of what the controls recorded.
    """
    stamps, seen, rows = {}, set(), []
    for line in trace_path.read_text(encoding="ascii").splitlines():
        parts = line.split(",")
        if parts[0] == "S" and len(parts) >= 5:
            stamps[(parts[1], parts[2])] = parts[3]
            seen.add(parts[1])
        elif parts[0] == "D" and len(parts) >= 3:
            stamps.pop((parts[1], parts[2]), None)
        elif parts[0] == "L" and len(parts) >= 5:
            key = (parts[1], parts[2])
            expected = stamps.get(key, "HELD" if parts[1] in seen else "UNKNOWN")
            rows.append({"slot": parts[1], "tick": parts[2], "traced_label": parts[3],
                         "expected_from_stamps": expected,
                         "agree": parts[3] == expected})
    agree = sum(1 for row in rows if row["agree"])
    return rows, {"trace_reads": len(rows), "agree": agree, "stamps": len(stamps),
                  "agreement": round(agree / len(rows), 6) if rows else None}


def renders(out_dir: Path) -> dict:
    """CONSTRUCT overlays for the branch live output never emits.

    These do NOT replace the 30 even live overlays; they stand beside them and are
    named CONSTRUCT so no reader can mistake a forced frame for a measured one.
    """
    from scripts.platformkit.tracking import g380_overlays

    det, frame = coast_scene()
    rows, index = [], []
    for slot, box in sorted(COAST_BOXES.items()):
        label = prov.label_for(det._pos_source, slot, COAST_TICK)[0]
        rows.append({"bbox_x1": box[0], "bbox_y1": box[1], "bbox_x2": box[2],
                     "bbox_y2": box[3], "position_source": label})
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, keep in (("construct_coast_held_%06d.jpg" % COAST_TICK, rows),
                       ("construct_held_only_%06d.jpg" % COAST_TICK,
                        [r for r in rows if r["position_source"] == "HELD"])):
        image = g380_overlays._draw(frame.copy(), keep)
        cv2.putText(image, "CONSTRUCT (not live output)", (16, 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        scale = 640.0 / image.shape[1]
        cv2.imwrite(str(out_dir / name),
                    cv2.resize(image, (640, int(image.shape[0] * scale))),
                    [int(cv2.IMWRITE_JPEG_QUALITY), 55])
        index.append({"file": name, "frame": COAST_TICK, "kind": "CONSTRUCT",
                      "labels": json.dumps({r["position_source"]: 1 for r in keep},
                                           sort_keys=True)})
    idx_path = out_dir / "overlays_index.csv"
    fresh = not idx_path.exists()
    with idx_path.open("a", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(g380_overlays.FIELDS))
        if fresh:
            writer.writeheader()
        writer.writerows(index)
    return {"construct_overlays": [item["file"] for item in index],
            "labels": sorted({r["position_source"] for r in rows})}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--trace-diff")
    parser.add_argument("--trace-out")
    parser.add_argument("--renders")
    args = parser.parse_args()
    if args.trace_diff:
        rows, summary = trace_diff(Path(args.trace_diff))
        _write(Path(args.trace_out or args.out), TRACE_FIELDS, rows)
        print(json.dumps(summary, sort_keys=True))
        return 0
    rows = controls()
    _write(Path(args.out), FIELDS, rows)
    failed = [row["control"] for row in rows if row["result"] == "FAIL"]
    print("controls n=%d construct=%d pass=%d fail=%s"
          % (len(rows), sum(1 for r in rows if r["kind"] == "CONSTRUCT"),
             sum(1 for r in rows if r["result"] == "PASS"), failed or "none"))
    if args.renders:
        print(json.dumps(renders(Path(args.renders)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
