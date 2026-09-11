"""Frozen same-detector person comparator replay for the G406 pixel diagnostic.

This is a plain YOLOv8n person inference over the sealed native frames with the
arguments read from the exercised producer route. It is NOT a producer run and
NOT an independent teacher: it shares the producer's detector family and weights.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

FROZEN_ARGS = {"classes": [0], "conf": 0.3, "imgsz": 640, "half": True, "device": 0,
               "verbose": False}
ABSENT_AT_CALL_SITE = ["iou", "max_det", "agnostic_nms", "augment", "rect"]
ROUTE = ("src/tracking/player_detection.py:FeetDetector.get_players_pos "
         "self.model(frame, classes=[0], conf=0.3, verbose=False, imgsz=_infer_imgsz, "
         "half=self._use_half, device=self._device)")
FIELDS = ["det_id", "card_id", "frame_path", "frame_sha256", "det_index", "cls", "confidence",
          "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "image_width", "image_height", "status"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _launch_receipt(weights: Path, deploy: Path, frames: list[Path]) -> dict[str, Any]:
    import torch
    import ultralytics
    from ultralytics.cfg import get_cfg
    defaults = get_cfg()
    smi = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total",
                          "--format=csv,noheader"], capture_output=True, text=True)
    return {"captured_before_load": True,
            "deploy_weights": {"path": str(deploy), "bytes": deploy.stat().st_size,
                               "sha256": sha256(deploy)},
            "scratch_weights": {"path": str(weights), "bytes": weights.stat().st_size,
                                "sha256": sha256(weights)},
            "exercised_route": ROUTE,
            "frozen_args": FROZEN_ARGS,
            "absent_at_call_site": {name: getattr(defaults, name) for name in ABSENT_AT_CALL_SITE},
            "absent_arg_provenance": "INHERITED_LIBRARY_DEFAULT_NOT_EXPLICIT_IN_EXERCISED_ROUTE",
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "torch": torch.__version__, "ultralytics": ultralytics.__version__,
                            "cuda_available": bool(torch.cuda.is_available()),
                            "gpu": smi.stdout.strip(),
                            "env": {name: os.environ.get(name, "")
                                    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
                                                 "OPENBLAS_NUM_THREADS", "CUDA_VISIBLE_DEVICES")}},
            "frames": [{"path": str(item), "sha256": sha256(item)} for item in frames]}


def main(frames_dir: str, weights_path: str, deploy_path: str, out_dir: str) -> None:
    import cv2
    import torch
    torch.set_num_threads(1)
    frames = sorted(Path(frames_dir).glob("*.png"))
    weights, deploy, out = Path(weights_path), Path(deploy_path), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    receipt = _launch_receipt(weights, deploy, frames)
    (out / "launch_receipts.json").write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n",
                                              encoding="utf-8", newline="\n")
    from ultralytics import YOLO
    model = YOLO(str(weights))
    digests = {item["path"]: item["sha256"] for item in receipt["frames"]}
    rows = []
    for frame in frames:
        image = cv2.imread(str(frame))
        result = model(image, **FROZEN_ARGS)[0]
        boxes = result.boxes
        count = 0 if boxes is None else len(boxes)
        for index in range(count):
            box = boxes.xyxy[index].cpu().numpy()
            rows.append({"det_id": "%s_d%02d" % (frame.stem, index), "card_id": frame.stem,
                         "frame_path": str(frame), "frame_sha256": digests[str(frame)],
                         "det_index": index, "cls": int(boxes.cls[index].item()),
                         "confidence": "%.6f" % float(boxes.conf[index].item()),
                         "bbox_x1": "%.3f" % box[0], "bbox_y1": "%.3f" % box[1],
                         "bbox_x2": "%.3f" % box[2], "bbox_y2": "%.3f" % box[3],
                         "image_width": image.shape[1], "image_height": image.shape[0],
                         "status": "DETECTION"})
        if count == 0:
            rows.append({"det_id": "%s_silence" % frame.stem, "card_id": frame.stem,
                         "frame_path": str(frame), "frame_sha256": digests[str(frame)],
                         "det_index": "", "cls": "", "confidence": "", "bbox_x1": "",
                         "bbox_y1": "", "bbox_x2": "", "bbox_y2": "",
                         "image_width": image.shape[1], "image_height": image.shape[0],
                         "status": "COMPARATOR_SILENCE"})
        print(frame.stem, count, flush=True)
    with open(out / "comparator_detections.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"frames": len(frames), "rows": len(rows),
                      "silent_frames": sum(1 for row in rows
                                           if row["status"] == "COMPARATOR_SILENCE")}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
