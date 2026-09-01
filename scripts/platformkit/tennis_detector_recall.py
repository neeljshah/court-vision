"""Reproducible tennis detector recall experiment with inference receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pandas as pd

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.quality_probe import quality_report
from scripts.platformkit.tracking.bridge_infill import bridge_dataframe


@dataclass(frozen=True)
class Arm:
    name: str
    imgsz: int
    conf: float
    tracker_conf: float
    tile_size: int | None = None


ARMS = (
    Arm("default", 640, 0.25, 0.25),
    Arm("high_resolution_low_conf", 1280, 0.15, 0.15),
    Arm("tiling", 640, 0.25, 0.25, 640),
    Arm("low_conf_tracker_rejection", 640, 0.10, 0.25),
)


def _detector(arm: Arm) -> Callable[[np.ndarray], Sequence[Sequence[float]]]:
    from ultralytics import YOLO

    model = YOLO("yolov8n.pt")
    emitted = False

    def detect(image: np.ndarray) -> Sequence[Sequence[float]]:
        nonlocal emitted
        if not emitted:
            tile = "none" if arm.tile_size is None else str(arm.tile_size)
            print("TENNIS_INFERENCE arm=%s imgsz=%d conf=%.3f tile=%s" % (
                arm.name, arm.imgsz, arm.conf, tile))
            emitted = True
        height, width = image.shape[:2]
        size = arm.tile_size
        origins = [(0, 0)] if size is None else [
            (x, y) for y in range(0, height, size) for x in range(0, width, size)
        ]
        detections: list[list[float]] = []
        for x0, y0 in origins:
            tile = image if size is None else image[y0:min(y0 + size, height), x0:min(x0 + size, width)]
            result = model(tile, classes=[0], imgsz=arm.imgsz, conf=arm.conf, verbose=False)[0]
            if result.boxes is None:
                continue
            boxes = result.boxes.xyxy.cpu().numpy().tolist()
            scores = result.boxes.conf.cpu().numpy().tolist()
            detections.extend([[float(x1 + x0), float(y1 + y0), float(x2 + x0),
                                float(y2 + y0), float(score)]
                               for (x1, y1, x2, y2), score in zip(boxes, scores)])
        return detections

    return detect


def _metrics(rows: pd.DataFrame) -> dict[str, object]:
    report = dict(quality_report(rows))
    players = rows.loc[rows["cls"].eq("player")]
    report["player_observation_frames"] = int(players["frame"].nunique())
    report["rows"] = int(len(rows))
    return report


def run_arm(video: Path, arm: Arm, frames: int) -> tuple[pd.DataFrame, dict[str, object]]:
    adapter = TennisAdapter(detector=_detector(arm), imgsz=arm.imgsz, conf=arm.conf,
                            tracker_conf=arm.tracker_conf)
    rows = adapter.process_video(video, max_frames=frames)
    return rows, _metrics(rows)


def run(video: Path, frames: int) -> dict[str, object]:
    receipt: dict[str, object] = {
        "source": str(video), "source_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        "max_frames": frames, "arms": [],
    }
    baseline: pd.DataFrame | None = None
    for arm in ARMS:
        rows, metrics = run_arm(video, arm, frames)
        receipt["arms"].append({"config": asdict(arm), "metrics": metrics})
        if arm.name == "default":
            baseline = rows
    if baseline is None:
        raise RuntimeError("default arm is required")
    inferred, report = bridge_dataframe(baseline, "tennis", {"p99": 6.0})
    receipt["arms"].append({"config": {"name": "short_gap_interpolation"},
                             "metrics": _metrics(inferred),
                             "infill": report.to_dict(),
                             "inferred_rows": int(inferred["provenance"].eq("inferred").sum())})
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.frames <= 0:
        raise ValueError("frames must be positive")
    receipt = run(args.video, args.frames)
    args.output.write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding="ascii")
    print("TENNIS_RECEIPT %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
