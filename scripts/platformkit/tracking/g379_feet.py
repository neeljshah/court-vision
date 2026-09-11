"""G379 feet: the DEPLOYED detector, unchanged, mapped through the selected matrix.

Sealed in the G379 prereg section 7. `src/` is imported READ-ONLY from the deploy tree; nothing
here writes to it, and no detector threshold is changed. A foot on a frame with no selected matrix
stays in the denominator and is not inside (contract B1).
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

COURT_LENGTH_FT = 94.0
COURT_WIDTH_FT = 50.0
HALF_LENGTH_FT = 47.0
CONF = 0.3
IMGSZ = 640
FIELDS = ("frame_key", "section_id", "game_id", "frame_index", "validation_status", "has_matrix",
          "foot_x_px", "foot_y_px", "court_x_ft", "court_y_ft", "finite", "inside_full_court",
          "inside_near_half")


def detector():
    """The deployed route, constructed exactly as the landed callers construct it."""
    from src.tracking.player_detection import FeetDetector

    return FeetDetector([])


def feet_of(model, image: np.ndarray) -> list[tuple[float, float]]:
    """One foot point per detected person box: the bottom-centre pixel, as the route defines it."""
    result = model.model(image, classes=[0], conf=CONF, verbose=False, imgsz=model._infer_imgsz,
                         half=model._use_half, device=model._device)
    boxes = result[0].boxes.xyxy.cpu().numpy() if result[0].boxes is not None else []
    return [(float((x1 + x2) / 2.0), float(y2)) for x1, _y1, x2, y2 in boxes]


def map_feet(court_matrix, feet: list) -> list[tuple[float, float]]:
    if court_matrix is None or not feet:
        return []
    points = np.asarray(feet, dtype=np.float32).reshape(1, -1, 2)
    return [tuple(float(value) for value in point)
            for point in cv2.perspectiveTransform(points, np.asarray(court_matrix,
                                                                     dtype=np.float32))[0]]


def run(frames: Path, matrices: Path, rows_path: Path, out: Path) -> None:
    """Detect on every scheduled decoded frame and map with that frame's selected matrix."""
    with frames.open("r", encoding="utf-8", newline="") as handle:
        decoded = [row for row in csv.DictReader(handle) if row["state"] == "DECODED"]
    with rows_path.open("r", encoding="utf-8", newline="") as handle:
        status = {row["frame_key"]: row["validation_status"] for row in csv.DictReader(handle)}
    selected = json.loads(matrices.read_text(encoding="ascii"))
    model = detector()
    out_rows = []
    for entry in decoded:
        key = entry["frame_key"]
        image = cv2.imread(entry["path"])
        if image is None:
            continue
        points = feet_of(model, image)
        matrix = selected.get(key, {}).get("court_matrix")
        mapped = map_feet(matrix, points)
        for index, (foot_x, foot_y) in enumerate(points):
            court = mapped[index] if mapped else (float("nan"), float("nan"))
            finite = bool(np.isfinite(court[0]) and np.isfinite(court[1]))
            inside = bool(finite and 0.0 <= court[0] <= COURT_WIDTH_FT
                          and 0.0 <= court[1] <= COURT_LENGTH_FT)
            near = bool(finite and 0.0 <= court[0] <= COURT_WIDTH_FT
                        and 0.0 <= court[1] <= HALF_LENGTH_FT)
            out_rows.append({
                "frame_key": key, "section_id": entry["section_id"], "game_id": entry["game_id"],
                "frame_index": entry["frame_index"],
                "validation_status": status.get(key, ""), "has_matrix": int(matrix is not None),
                "foot_x_px": round(foot_x, 3), "foot_y_px": round(foot_y, 3),
                "court_x_ft": "" if not finite else round(court[0], 4),
                "court_y_ft": "" if not finite else round(court[1], 4),
                "finite": int(finite), "inside_full_court": int(inside),
                "inside_near_half": int(near)})
        print("%s feet=%d matrix=%d" % (key, len(points), int(matrix is not None)), flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)
    inside = sum(row["inside_full_court"] for row in out_rows)
    print("FEET n=%d inside=%d frames=%d" % (len(out_rows), inside, len(decoded)))


def main() -> None:
    parser = argparse.ArgumentParser(description="G379 deployed-route feet, mapped and counted")
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--matrices", type=Path, required=True)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.frames, args.matrices, args.rows, args.out)


if __name__ == "__main__":
    main()
