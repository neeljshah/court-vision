"""
run_pipeline: End-to-end NBA CV tracking pipeline.

Orchestrates the full pipeline:
  VideoIngestor → ObjectDetector → ObjectTracker → CoordinateWriter

Processes a local video file frame-by-frame, detects players and basketballs
with YOLOv8, assigns persistent track IDs via DeepSORT, computes velocities,
and writes all tracking coordinates to PostgreSQL.

CLI usage::

    python -m pipelines.run_pipeline --video path/to/game.mp4 --game-id UUID
    python -m pipelines.run_pipeline --video path/to/game.mp4 --game-id UUID \
        --weights path/to/yolo.pt --conf 0.4
"""
import argparse
import sys

from pipelines.detector import ObjectDetector
from pipelines.video_ingestor import VideoIngestor
from tracking.coordinate_writer import CoordinateWriter
from tracking.tracker import ObjectTracker


def run_pipeline(
    video_path: str,
    game_id: str,
    weights_path: str = None,
    conf_threshold: float = 0.5,
) -> None:
    """Process a video file end-to-end: detect → track → store coordinates.

    Args:
        video_path: Path to the local video file to process.
        game_id: UUID identifying the game in the database (FK to games table).
        weights_path: Optional path to YOLOv8 weights file. If None or the
                      file does not exist, falls back to yolov8n.pt auto-download.
        conf_threshold: Minimum YOLO detection confidence (0.0–1.0).

    Prints a summary line with frames processed and total tracked objects written.
    """
    # Initialise pipeline components
    ingestor = VideoIngestor(video_path)
    detector = ObjectDetector(
        weights_path=weights_path if weights_path else "yolov8n.pt",
        conf_threshold=conf_threshold,
    )
    tracker = ObjectTracker()
    tracker.set_fps(ingestor.fps)
    writer = CoordinateWriter(game_id=game_id)

    frames_processed = 0
    total_tracked = 0

    for frame_num, frame, ts_ms in ingestor.frames():
        detections = detector.detect(frame)
        tracked = tracker.update(detections, frame, frame_num, ts_ms)
        writer.write_batch(tracked)
        frames_processed += 1
        total_tracked += len(tracked)

    writer.flush()

    print(
        f"Pipeline complete: {frames_processed} frames processed, "
        f"{total_tracked} tracked objects written."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="NBA CV tracking pipeline — detects and tracks players/ball, writes coordinates to DB"
    )
    parser.add_argument(
        "--video",
        required=True,
        help="Path to the input video file",
    )
    parser.add_argument(
        "--game-id",
        required=True,
        help="UUID of the game record in the database",
    )
    parser.add_argument(
        "--weights",
        default=None,
        help="Path to YOLOv8 weights file (default: auto-download yolov8n.pt)",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.5,
        help="Minimum detection confidence threshold (default: 0.5)",
    )
    args = parser.parse_args()
    run_pipeline(args.video, args.game_id, args.weights, args.conf)
