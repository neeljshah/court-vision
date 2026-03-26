"""
label_ball_yolo.py — Auto-label basketball positions from existing clips.

Uses the existing BallDetectTrack (Hough + CSRT) to find high-confidence
ball positions in the video clips and saves them as YOLO-format labels.

Only frames where:
  - BallDetectTrack returns a valid bbox
  - _is_ball_orange() passes (center patch is basketball-orange)
  - CSRT confidence is not in do_detection mode (CSRT is actively tracking)

are saved.  This keeps label quality high.

Output:
    data/ball_yolo/images/   — 640×480 BGR crops of full frame
    data/ball_yolo/labels/   — YOLO format  (class cx cy w h, normalised)
    Targets 2,000+ labeled frames.

Usage:
    conda activate basketball_ai
    python scripts/label_ball_yolo.py
"""

from __future__ import annotations

import os
import sys
import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.tracking.ball_detect_track import BallDetectTrack
from src.tracking.player_detection import FeetDetector
from src.tracking import TOPCUT

VIDEOS_DIR = os.path.join(ROOT, "data", "videos")
OUT_DIR    = os.path.join(ROOT, "data", "ball_yolo")
IMG_DIR    = os.path.join(OUT_DIR, "images")
LBL_DIR    = os.path.join(OUT_DIR, "labels")
os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(LBL_DIR, exist_ok=True)

TARGET_FRAMES = 2000   # stop early if we hit this
IMGSZ         = 640    # output image size for training
FRAME_STRIDE  = 3      # sample every Nth frame (avoid near-duplicate labels)


def _bbox_to_yolo(bbox, frame_w: int, frame_h: int) -> str:
    """Convert (x, y, w, h) bbox to YOLO format string."""
    x, y, w, h = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    cx = (x + w / 2) / frame_w
    cy = (y + h / 2) / frame_h
    nw = w / frame_w
    nh = h / frame_h
    # Clamp to [0, 1]
    cx = max(0.0, min(1.0, cx))
    cy = max(0.0, min(1.0, cy))
    nw = max(0.001, min(1.0, nw))
    nh = max(0.001, min(1.0, nh))
    return f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"


def label_clip(video_path: str, label_count: int) -> int:
    """Extract ball labels from one video clip. Returns number of labels saved."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  Cannot open: {video_path}")
        return 0

    total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    saved   = 0
    stem    = os.path.splitext(os.path.basename(video_path))[0]

    # Minimal player list stub — BallDetectTrack only needs players for possession IoU;
    # detection itself doesn't need players.  Pass an empty list.
    tracker = BallDetectTrack(players=[])

    # Homography stubs — BallDetectTrack uses M and M1 only for 2D projection
    # (which we don't need here).  Pass identity matrices so projection math
    # doesn't crash; last_2d_pos may be None but bbox detection still works.
    M_ident  = np.eye(3, dtype=np.float64)
    M1_ident = np.eye(3, dtype=np.float64)
    map_2d   = np.zeros((500, 940, 3), dtype=np.uint8)
    map_txt  = np.zeros_like(map_2d)

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_idx % FRAME_STRIDE != 0:
            frame_idx += 1
            continue

        frame = frame[TOPCUT:]
        h, w  = frame.shape[:2]

        try:
            frame_out, _ = tracker.ball_tracker(
                M_ident, M1_ident, frame.copy(), map_2d.copy(), map_txt.copy(), frame_idx
            )
        except Exception:
            frame_idx += 1
            continue

        bbox = tracker._last_bbox

        # Only save when CSRT is actively tracking (not in do_detection mode)
        # and the bbox looks valid
        if bbox is not None and not tracker.do_detection:
            x, y, bw, bh = bbox
            cx_int = int(x + bw / 2)
            cy_int = int(y + bh / 2)
            if BallDetectTrack._is_ball_orange(frame, cx_int, cy_int):
                # Resize frame to training size
                frame_resized = cv2.resize(frame, (IMGSZ, IMGSZ))
                scale_x = IMGSZ / w
                scale_y = IMGSZ / h
                bbox_scaled = (x * scale_x, y * scale_y,
                               bw * scale_x, bh * scale_y)

                name = f"{stem}_{frame_idx:06d}"
                cv2.imwrite(os.path.join(IMG_DIR, f"{name}.jpg"), frame_resized,
                            [cv2.IMWRITE_JPEG_QUALITY, 85])
                with open(os.path.join(LBL_DIR, f"{name}.txt"), "w") as f:
                    f.write(_bbox_to_yolo(bbox_scaled, IMGSZ, IMGSZ) + "\n")
                saved += 1

                if (label_count + saved) >= TARGET_FRAMES:
                    break

        frame_idx += 1

    cap.release()
    return saved


def main() -> None:
    # Find all mp4 files
    videos = [
        os.path.join(VIDEOS_DIR, f)
        for f in os.listdir(VIDEOS_DIR)
        if f.lower().endswith(".mp4")
    ]

    if not videos:
        print(f"No .mp4 files found in {VIDEOS_DIR}")
        sys.exit(1)

    print(f"Found {len(videos)} clips. Generating ball labels...")
    total_saved = 0

    for vp in videos:
        if total_saved >= TARGET_FRAMES:
            break
        print(f"  {os.path.basename(vp)} ...", end=" ", flush=True)
        n = label_clip(vp, total_saved)
        total_saved += n
        print(f"{n} labels  (total: {total_saved})")

    print(f"\nDone. {total_saved} labeled frames saved to {OUT_DIR}/")

    # Write dataset.yaml for training
    yaml_path = os.path.join(OUT_DIR, "dataset.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"path: {OUT_DIR}\n")
        f.write(f"train: images\n")
        f.write(f"val: images\n")
        f.write(f"nc: 1\n")
        f.write(f"names: ['ball']\n")
    print(f"Dataset YAML: {yaml_path}")


if __name__ == "__main__":
    main()
