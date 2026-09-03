"""Bounded raw-detector versus emitted-player diagnostic for G188.

This is evidence tooling.  It never changes a detector, selection rule, or
production output.  Its raw stage uses the detector shim; the caller supplies
the sport's existing survivor callback so the retained records make that delta
auditable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable

import cv2
import numpy as np

from scripts.platformkit.detection.shim import Detection, get_detector

Box = dict[str, float | str]


def evenly_spaced_frames(eligible_frames: Iterable[int], count: int) -> list[int]:
    """Choose inclusive, unique positions evenly across a declared frame set."""
    frames = list(eligible_frames)
    if count < 2 or len(frames) < count:
        raise ValueError("need at least count >= 2 eligible frames")
    positions = [round(index * (len(frames) - 1) / (count - 1)) for index in range(count)]
    selected = [frames[position] for position in positions]
    if len(set(selected)) != count:
        raise ValueError("rounded even positions were not unique")
    return selected


def person_boxes(detector: Callable[[np.ndarray], list[Detection]], frame: np.ndarray) -> list[Box]:
    """Return every shim-detected COCO person box, retaining detector confidence."""
    return [
        {"x1": round(item.x1, 2), "y1": round(item.y1, 2),
         "x2": round(item.x2, 2), "y2": round(item.y2, 2),
         "confidence": round(item.conf, 4), "class": item.cls_name}
        for item in detector(frame) if item.cls_name == "person"
    ]


def draw_dual_boxes(frame: np.ndarray, raw: list[Box], survivors: list[Box], label: str) -> np.ndarray:
    """Draw raw boxes red and survivor boxes green without altering either list."""
    image = frame.copy()
    for index, box in enumerate(raw):
        cv2.rectangle(image, (int(float(box["x1"])), int(float(box["y1"]))),
                      (int(float(box["x2"])), int(float(box["y2"]))), (0, 0, 255), 2)
        cv2.putText(image, "R%d %.2f" % (index + 1, float(box["confidence"])),
                    (int(float(box["x1"])), max(15, int(float(box["y1"])) - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 255), 1, cv2.LINE_AA)
    for index, box in enumerate(survivors):
        cv2.rectangle(image, (int(float(box["x1"])), int(float(box["y1"]))),
                      (int(float(box["x2"])), int(float(box["y2"]))), (0, 255, 0), 3)
        cv2.putText(image, "S%d" % (index + 1),
                    (int(float(box["x1"])), min(image.shape[0] - 4, int(float(box["y2"])) + 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.putText(image, label + " | raw=red survivor=green", (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
    return image


def read_frame(capture: cv2.VideoCapture, frame_index: int) -> np.ndarray:
    """Read one absolute source frame or fail rather than silently substituting."""
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    if not ok or frame is None:
        raise RuntimeError("could not decode frame %d" % frame_index)
    return frame


def run_raw_measurement(
    video: Path, frames: list[int], crop_top: int = 0, model_path: str | None = None,
) -> tuple[dict[int, np.ndarray], dict[int, list[Box]]]:
    """Run the configured shim once per declared source frame, with no selection."""
    detector = get_detector(model_path=model_path)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError(str(video))
    images: dict[int, np.ndarray] = {}
    raw: dict[int, list[Box]] = {}
    try:
        for frame_index in frames:
            image = read_frame(capture, frame_index)
            if crop_top:
                image = image[crop_top:]
            images[frame_index] = image
            raw[frame_index] = person_boxes(detector.detect, image)
    finally:
        capture.release()
    return images, raw


def write_records(path: Path, records: list[dict[str, Any]]) -> None:
    """Write inspectable per-frame records; aggregate-only evidence is forbidden."""
    path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    raise SystemExit("G188 is invoked by its bounded evidence runner, not as a generic CLI")


if __name__ == "__main__":
    main()
