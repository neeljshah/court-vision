"""
run_pipeline: End-to-end NBA CV tracking pipeline.

Features:
- Batched GPU inference (BATCH_SIZE frames per YOLO forward pass)
- Court homography calibrated from first CALIB_FRAMES frames
- Camera cut detection: recalibrates homography after scene changes
- Resumable: skips already-processed frames on restart
- Frame-skip for speed (--skip N processes every Nth frame)
- Progress reporting every REPORT_INTERVAL frames

Usage:
    python -m pipelines.run_pipeline --video game.mp4 --game-id UUID
    python -m pipelines.run_pipeline --video game.mp4 --game-id UUID --skip 2
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from pipelines.detector import ObjectDetector
from pipelines.video_ingestor import VideoIngestor
from tracking.coordinate_writer import CoordinateWriter
from tracking.database import get_connection
from tracking.homography import CourtHomography, detect_court_corners, detect_court_lines
from tracking.tracker import ObjectTracker

BATCH_SIZE      = 8    # frames per YOLO forward pass
CALIB_FRAMES    = 30   # frames sampled for initial homography calibration
REPORT_INTERVAL = 300  # print progress every N processed frames

# Scene-cut detection: mean pixel difference above this → camera switch
_SCENE_CUT_THRESHOLD = 35.0


def _get_resume_frame(game_id: str) -> int:
    """Return the last processed frame_number for this game, or -1 if none."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(frame_number) FROM tracking_coordinates WHERE game_id = %s",
                    (game_id,),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
    except Exception:
        pass
    return -1


def _calibrate_homography(video_path: str, n_frames: int = CALIB_FRAMES) -> CourtHomography:
    """
    Sample up to n_frames from the video and compute court homography
    from the best corner detection result.
    """
    cap   = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step  = max(1, total // n_frames)

    hg = CourtHomography()
    best_corners = None

    for i in range(n_frames):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i * step)
        ret, frame = cap.read()
        if not ret:
            break
        src, dst = detect_court_lines(frame)
        if src is not None and hg.calibrate_from_points(src, dst):
            break  # line-based succeeded
        corners = detect_court_corners(frame)
        if corners is not None:
            best_corners = corners

    cap.release()

    if not hg.is_calibrated and best_corners is not None:
        hg.calibrate(best_corners)

    if hg.is_calibrated:
        print("[Homography] Court calibration successful.", flush=True)
    else:
        print("[Homography] Could not detect court corners — using pixel coordinates.", flush=True)

    return hg


def _detect_scene_cut(prev_gray: np.ndarray, curr_gray: np.ndarray) -> bool:
    """Return True if mean absolute pixel difference indicates a camera cut."""
    diff = cv2.absdiff(prev_gray, curr_gray)
    return float(diff.mean()) > _SCENE_CUT_THRESHOLD


def _try_recalibrate(frame: np.ndarray, homography: CourtHomography) -> bool:
    """
    Attempt to recalibrate homography from a single frame after a camera cut.
    Returns True if calibration succeeded.
    """
    corners = detect_court_corners(frame)
    if corners is None:
        return False
    return homography.calibrate(corners)


def run_pipeline(
    video_path: str,
    game_id:    str,
    weights_path: str = "yolov8x.pt",
    frame_skip: int   = 1,
    conf_threshold: float = 0.25,
) -> None:
    """
    Process a video end-to-end: calibrate → detect (batched) → track → store.

    Args:
        video_path:      Path to input video.
        game_id:         UUID of the game in the database.
        weights_path:    YOLOv8 weights file.
        frame_skip:      Process every Nth frame (1 = every frame).
        conf_threshold:  Minimum detection confidence to keep.
    """
    # ── Resume check ──────────────────────────────────────────────────────────
    resume_from = _get_resume_frame(game_id)
    if resume_from >= 0:
        print(f"[Resume] Resuming from frame {resume_from + 1}", flush=True)

    # ── Court homography ──────────────────────────────────────────────────────
    homography = _calibrate_homography(video_path)

    # ── Pipeline components ───────────────────────────────────────────────────
    ingestor = VideoIngestor(video_path)
    detector = ObjectDetector(weights_path=weights_path)
    tracker  = ObjectTracker(homography=homography)
    tracker.set_fps(ingestor.fps)
    writer   = CoordinateWriter(game_id=game_id)

    total_frames     = ingestor.frame_count
    frames_processed = 0
    total_tracked    = 0
    t_start          = time.time()

    # Batch accumulator
    batch: list = []   # (frame_num, frame_bgr, ts_ms)

    # Scene-cut state: grayscale of last batch's final frame
    prev_gray: np.ndarray = None

    def _process_batch(b):
        nonlocal frames_processed, total_tracked, prev_gray, homography

        # ── Scene-cut detection ───────────────────────────────────────────────
        first_gray = cv2.cvtColor(b[0][1], cv2.COLOR_BGR2GRAY)
        if prev_gray is not None and _detect_scene_cut(prev_gray, first_gray):
            # Camera switched — try to recalibrate from the new frame
            if _try_recalibrate(b[0][1], homography):
                tracker.set_homography(homography)
                print(f"[Homography] Recalibrated after camera cut at frame {b[0][0]}.", flush=True)
            else:
                print(f"[Homography] Camera cut at frame {b[0][0]} — corners unclear, keeping previous.", flush=True)

        prev_gray = cv2.cvtColor(b[-1][1], cv2.COLOR_BGR2GRAY)

        # ── Detection + tracking ──────────────────────────────────────────────
        imgs     = [item[1] for item in b]
        all_dets = detector.detect_batch(imgs)

        for (fn, fr, ts), dets in zip(b, all_dets):
            tracked = tracker.update(dets, fr, fn, ts)
            writer.write_batch(tracked)
            frames_processed += 1
            total_tracked    += len(tracked)

    for frame_num, frame, ts_ms in ingestor.frames():
        # Skip already-processed frames on resume
        if frame_num <= resume_from:
            continue

        # Frame skip for throughput
        if frame_skip > 1 and frame_num % frame_skip != 0:
            continue

        batch.append((frame_num, frame, ts_ms))

        if len(batch) >= BATCH_SIZE:
            _process_batch(batch)
            batch = []

        # Progress report
        if frames_processed > 0 and frames_processed % REPORT_INTERVAL == 0:
            elapsed   = time.time() - t_start
            fps       = frames_processed / elapsed
            remaining = (total_frames - frames_processed) / max(fps, 0.01)
            print(
                f"[Progress] {frames_processed}/{total_frames} frames "
                f"| {fps:.1f} fps | ETA {remaining/60:.1f}min",
                flush=True,
            )

    # Flush remaining frames
    if batch:
        _process_batch(batch)

    writer.flush()

    elapsed = time.time() - t_start
    print(
        f"[Done] {frames_processed} frames in {elapsed:.1f}s "
        f"({frames_processed/max(elapsed,1):.1f} fps) | "
        f"{total_tracked} tracked objects written.",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NBA CV tracking pipeline")
    parser.add_argument("--video",   required=True)
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--weights", default="yolov8x.pt")
    parser.add_argument("--skip",    type=int, default=1,
                        help="Process every Nth frame (default 1 = every frame)")
    args = parser.parse_args()
    run_pipeline(args.video, args.game_id, args.weights, args.skip)
