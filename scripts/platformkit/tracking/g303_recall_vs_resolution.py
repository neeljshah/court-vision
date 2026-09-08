"""G303 -- player recall at the production route's MEASURED detector input vs native.

`detect` runs on the pod and IMPORTS the unedited human-gated production detector;
`score` is local arithmetic. Rules sealed in `g303_prereg_2026-09-07.md` and, for this fix
pass, `g303_prereg_supplement_2026-09-07b.md`; `src/` is imported and run, never edited.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

from scripts.platformkit.tracking.g298_compare import read_csv, sha256, write_csv

TOLERANCES = (25, 50, 100)  # the three REGISTERED tolerances; the candidate's 40 px is dropped
ARMS = ("P", "P_repeat", "R", "M", "P22")
ARM_IMGSZ = {"P": None, "P_repeat": None, "R": 1920, "M": 1280, "P22": None}  # None = route
REGISTERED_CONF = 0.3
ARM_CONF = {"P": REGISTERED_CONF, "P_repeat": REGISTERED_CONF, "R": REGISTERED_CONF,
            "M": REGISTERED_CONF, "P22": None}  # None = the route's OWN threshold, untouched
PRIMARY = "adjudicated_113"
FIELDS = ["source_frame", "detection_index", "x1", "y1", "x2", "y2", "confidence",
          "foot_x_px", "foot_y_px"]
DEPLOYED = "/workspace/nba-ai-system"  # A11: reuse the deployed weights, never a fresh download
NOTE = "LOWER BOUND: a real person outside the scored basis is a false positive here"


def foot(box, width, height, y_offset):
    """Production bottom-centre in detector coords, mapped back to native pixels."""
    x1, _, x2, y2 = (int(v) for v in box[:4])
    return (max(0, x1) + min(width, x2)) // 2, min(height, y2) + y_offset


def probe(command):
    """Run an operational probe and record its output verbatim."""
    r = subprocess.run(command, capture_output=True, text=True)
    rec = {"command": command, "rc": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
    print(json.dumps(rec), flush=True)
    return rec


class Capture:
    """Transparent proxy that records the production model call, changing nothing."""

    def __init__(self, model, tag, slot):
        self.model, self.tag, self.slot = model, tag, slot
        self.calls, self.tensors, self._hooked = [], [], False

    def __getattr__(self, name):
        return getattr(self.model, name)

    def _hook(self):
        """Wrap the ultralytics predictor preprocess to see the real network input."""
        predictor = getattr(self.model, "predictor", None)
        if self._hooked or predictor is None:
            return
        inner, sink = predictor.preprocess, self.tensors

        def wrapped(im):
            out = inner(im)
            sink.append({"tensor_shape": list(out.shape), "dtype": str(out.dtype)})
            return out

        predictor.preprocess, self._hooked = wrapped, True

    def __call__(self, frame, **kwargs):
        first = frame[0] if isinstance(frame, list) else frame
        self.calls.append({"model": self.tag, "array_shape": list(first.shape),
                           "batch": len(frame) if isinstance(frame, list) else 1,
                           "dtype": str(first.dtype),
                           "kwargs": {k: repr(v) for k, v in kwargs.items()}})
        self._hook()
        out = self.model(frame, **kwargs)
        self.slot["result"], self.slot["served_by"] = out[0], self.tag
        return out


def detect(args):
    """Run every arm on the shipped frames through the unedited production class."""
    import cv2
    import numpy as np
    import torch
    import ultralytics
    from src.tracking.advanced_tracker import AdvancedFeetDetector
    from src.tracking.tracker_config import load_config
    from src.tracking.video_handler import TOPCUT

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    gpu = probe(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader"])
    used, total = (int(s.strip().split()[0]) for s in gpu["stdout"].splitlines()[0].split(","))
    assert total - used >= 8000, "gate: need 8 GB free VRAM"
    dd = ["dd", "if=/dev/zero", f"of={out / 'fsync.bin'}", "bs=1M", "count=8", "conv=fsync"]
    disk = probe(dd)
    assert disk["rc"] == 0, "FAILED dd conv=fsync probe"
    (out / "fsync.bin").unlink()
    order = [int(r["source_frame"]) for r in read_csv(args.frames_csv)]
    paths = sorted(args.frames.glob("frame_*.jpg"))
    assert len(paths) == len(order) == 24, "expect the 24 committed frames"
    images, meta = {}, []
    for frame_id, path in zip(order, paths):
        image = cv2.imread(str(path))
        assert image is not None and image.shape == (1080, 1920, 3), path
        images[frame_id] = image[TOPCUT:]
        meta.append({"source_frame": frame_id, "jpeg": path.name, "topcut": TOPCUT,
                     "sha256": sha256(path), "fed_shape": list(images[frame_id].shape)})
    for stem in ("yolov8n.pt", "yolov8n-pose.pt"):  # A11: the DEPLOYED weights, not a download
        if Path(DEPLOYED, stem).is_file() and not Path(stem).exists():
            shutil.copy(Path(DEPLOYED, stem), stem)
    detector = AdvancedFeetDetector([])
    weights = Path(str(getattr(detector.model, "ckpt_path", "") or "."))
    route = int(detector._infer_imgsz)
    route_conf = float(detector._fill_conf_threshold)
    print(f"BEFORE-CONDITION input_size={route} lt_1920={route < 1920} "
          f"route_conf={route_conf} registered_conf={REGISTERED_CONF}", flush=True)
    step0 = {"route_infer_imgsz": route, "route_yolo_imgsz": int(detector._yolo_imgsz),
             "route_fill_conf_threshold": route_conf, "registered_conf": REGISTERED_CONF,
             "conf_conflict": route_conf != REGISTERED_CONF, "topcut": TOPCUT,
             "before_condition_lt_1920": route < 1920,
             "loaded_tracker_config": load_config(), "pose_active": detector._use_pose,
             "weights": {"path": str(weights), "sha256": sha256(weights)},
             "env": {"python": sys.version.split()[0], "torch": torch.__version__,
                     "ultralytics": ultralytics.__version__, "cv2": cv2.__version__,
                     "gpu": torch.cuda.get_device_name(0), "half": detector._use_half}}
    ARM_IMGSZ["P"] = ARM_IMGSZ["P_repeat"] = ARM_IMGSZ["P22"] = route
    arms, errors = {}, {}
    for arm in ARMS:
        detector = AdvancedFeetDetector([])
        detector._infer_imgsz = ARM_IMGSZ[arm]
        if ARM_CONF[arm] is not None:
            detector._fill_conf_threshold = ARM_CONF[arm]
        conf_used = float(detector._fill_conf_threshold)
        slot = {}
        rec = Capture(detector.model, "det", slot)
        detector.model = rec
        if detector._pose_model is not None:
            detector._pose_model = Capture(detector._pose_model, "pose", slot)
        torch.cuda.reset_peak_memory_stats()
        rows, elapsed, served = [], 0.0, []
        for frame_id in order:
            slot.clear()
            start = time.perf_counter()
            try:
                detector.get_players_pos(np.eye(3), np.eye(3), images[frame_id].copy(),
                                         frame_id, np.zeros((2, 2, 3), dtype=np.uint8))
            except Exception as error:  # downstream tracking logic, not the detection
                errors.setdefault(arm, {})[frame_id] = repr(error)[:160]
            elapsed += time.perf_counter() - start
            served.append(slot.get("served_by", "none"))
            boxes = getattr(slot.get("result"), "boxes", None)
            xyxy = boxes.xyxy.cpu().numpy() if boxes is not None else []
            conf = boxes.conf.cpu().numpy() if boxes is not None else []
            height, width = images[frame_id].shape[:2]
            for i, (box, sc) in enumerate(zip(xyxy, conf)):
                fx, fy = foot(box, width, height, TOPCUT)
                rows.append(dict(zip(FIELDS, [frame_id, i, float(box[0]), float(box[1]),
                                              float(box[2]), float(box[3]), float(sc),
                                              fx, fy])))
        assert any(s != "none" for s in served), f"{arm}: production model never called"
        write_csv(out / f"{arm}.csv", rows, FIELDS)
        arms[arm] = {"imgsz": ARM_IMGSZ[arm], "conf": conf_used,
                     "conf_source": "route" if ARM_CONF[arm] is None else "registered",
                     "total_detections": len(rows),
                     "detections_per_frame": len(rows) / len(order),
                     "ms_per_frame": 1000.0 * elapsed / len(order),
                     "peak_vram_mib": torch.cuda.max_memory_allocated() / 1024 ** 2,
                     "served_by": dict(zip(order, served)), "calls": rec.calls[:3],
                     "pose_served_frames": [f for f, s in zip(order, served) if s == "pose"],
                     "tensors": rec.tensors[:3], "errors": len(errors.get(arm, {}))}
        del detector, rec
        torch.cuda.empty_cache()
    step0["arm_P_calls"], step0["arm_P_tensors"] = arms["P"]["calls"], arms["P"]["tensors"]
    step0["arm_P22_calls"] = arms["P22"]["calls"]
    step0["downstream_error_sample"] = dict(list(errors.get("P", {}).items())[:2])
    same = (out / "P.csv").read_bytes() == (out / "P_repeat.csv").read_bytes()
    (out / "g303_detect.json").write_text(json.dumps(
        {"step0": step0, "frames": meta, "arms": arms, "probes": [gpu, disk],
         "arm_P_byte_identical_repeat": same}, indent=2) + "\n", encoding="ascii")
    print(f"G303 detect done; P_repeat byte-identical={same}", flush=True)


def eligible(rows):
    """Pass-level on-court feet with both coordinates present."""
    return [r for r in rows if r.get("role") == "player_on_court"
            and r.get("feet_visible") == "true" and r.get("foot_x_px")
            and r.get("foot_y_px")]


def assign(truth, dets, tol):
    """One-to-one Hungarian on Euclidean distance; per-point matched flags."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    flags = [False] * len(truth)
    if not truth or not dets:
        return flags
    cost = np.array([[math.hypot(t[0] - d[0], t[1] - d[1]) for d in dets] for t in truth])
    for r, c in zip(*linear_sum_assignment(cost)):
        flags[r] = bool(cost[r, c] <= tol)
    return flags


def score_arm(by_frame, dbf, keys):
    """Per-point one-to-one flags per tolerance, plus the G298 nearest rule."""
    near = [min((math.hypot(t[0] - d[0], t[1] - d[1]) for d in dbf.get(f, [])),
                default=math.inf) for f in keys for t in by_frame[f]]
    flags = {t: {f: assign(by_frame[f], dbf.get(f, []), t) for f in keys} for t in TOLERANCES}
    return {"hits": {t: {f: sum(flags[t][f]) for f in keys} for t in TOLERANCES},
            "one_to_one": {t: [v for f in keys for v in flags[t][f]] for t in TOLERANCES},
            "nearest_rule": {t: [d <= t for d in near] for t in TOLERANCES},
            "median_nearest_px": statistics.median(near) if near else None}


def main():
    # Lazy: g303_report imports constants/eligible/score_arm back from this module, so this
    # module must finish loading (all defs above already bound) before that import runs.
    from scripts.platformkit.tracking.g303_report import score
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode, func, flags in (("detect", detect, ("frames", "frames-csv", "output")),
                              ("score", score, ("ground-truth", "pass-a", "pass-b", "output"))):
        p = sub.add_parser(mode)
        for flag in flags:
            p.add_argument("--" + flag, type=Path, required=flag != "ground-truth")
        p.set_defaults(func=func)
    args = parser.parse_args()
    args.func(args)


def __getattr__(name):
    """Lazy re-export (fix 1d, NEW GAP): `score`/`score_basis`/`bootstrap_ci` moved to
    g303_report in fix 1c with no tracked reader left importing them from here. PEP 562
    module __getattr__ resolves them ON ACCESS instead of at module-load time, so
    `from g303_recall_vs_resolution import score` keeps working without creating a
    load-time circular import (g303_report already imports FROM this module at its top)."""
    if name in ("score", "score_basis", "bootstrap_ci"):
        from scripts.platformkit.tracking import g303_report
        return getattr(g303_report, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    main()
