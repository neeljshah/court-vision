"""
VideoIngestor: frame generator from a local video file.

Yields (frame_number, frame_array, timestamp_ms) tuples using cv2.VideoCapture.
Used as the entry point for all downstream pipeline components (detector, tracker).
"""
import os
from typing import Generator, Tuple

import cv2
import numpy as np


class VideoIngestor:
    """Reads a local video file and yields frames one at a time."""

    def __init__(self, video_path: str) -> None:
        """
        Initialize with a path to a local video file.

        Args:
            video_path: Absolute or relative path to the video file.

        Raises:
            FileNotFoundError: If the file does not exist at video_path.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(
                f"Video file not found: {video_path}"
            )
        self._video_path = video_path

    @property
    def frame_count(self) -> int:
        """Total number of frames reported by VideoCapture."""
        cap = cv2.VideoCapture(self._video_path)
        try:
            return int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        finally:
            cap.release()

    @property
    def fps(self) -> float:
        """Frames per second of the video."""
        cap = cv2.VideoCapture(self._video_path)
        try:
            return float(cap.get(cv2.CAP_PROP_FPS))
        finally:
            cap.release()

    def frames(self) -> Generator[Tuple[int, np.ndarray, float], None, None]:
        """
        Generator that yields one frame at a time from the video.

        Yields:
            Tuple of (frame_number: int, frame: np.ndarray, timestamp_ms: float)
            where timestamp_ms is the position in milliseconds of the current frame.
        """
        cap = cv2.VideoCapture(self._video_path)
        try:
            frame_number = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                timestamp_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC))
                yield (frame_number, frame, timestamp_ms)
                frame_number += 1
        finally:
            cap.release()
