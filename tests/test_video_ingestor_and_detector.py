"""
TDD tests for VideoIngestor and ObjectDetector (plan 01-02, task 1).
RED phase: these tests must fail before implementation.
"""
import dataclasses
import numpy as np
import pytest
import tempfile
import os

# --- Import checks ---
from pipelines.video_ingestor import VideoIngestor
from pipelines.detector import ObjectDetector, Detection


class TestDetectionDataclass:
    def test_detection_is_dataclass(self):
        assert dataclasses.is_dataclass(Detection)

    def test_detection_has_required_fields(self):
        fields = {f.name for f in dataclasses.fields(Detection)}
        assert "bbox" in fields
        assert "confidence" in fields
        assert "class_label" in fields
        assert "cx" in fields
        assert "cy" in fields

    def test_detection_instantiation(self):
        d = Detection(
            bbox=(10.0, 20.0, 50.0, 80.0),
            confidence=0.9,
            class_label="player",
            cx=30.0,
            cy=50.0,
        )
        assert d.bbox == (10.0, 20.0, 50.0, 80.0)
        assert d.confidence == 0.9
        assert d.class_label == "player"
        assert d.cx == 30.0
        assert d.cy == 50.0


class TestVideoIngestor:
    def test_raises_file_not_found_for_missing_path(self):
        with pytest.raises(FileNotFoundError):
            VideoIngestor("/nonexistent/video.mp4")

    def test_frames_is_generator(self):
        """frames() must be a generator (not list)."""
        import types
        # Create a tiny synthetic video to test generator behavior
        # We just check the method is a generator function on a temp file
        # by creating a valid path (even though video is empty/invalid,
        # just checking the constructor won't raise on an existing file)
        import cv2
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_path = f.name
        try:
            # Write a minimal video file so VideoCapture can open it
            out = cv2.VideoWriter(
                tmp_path,
                cv2.VideoWriter_fourcc(*"mp4v"),
                30,
                (64, 64),
            )
            for _ in range(5):
                frame = np.zeros((64, 64, 3), dtype=np.uint8)
                out.write(frame)
            out.release()
            vi = VideoIngestor(tmp_path)
            gen = vi.frames()
            assert isinstance(gen, types.GeneratorType)
        finally:
            os.unlink(tmp_path)

    def test_frames_yields_correct_tuple_structure(self):
        """Each yield must be (frame_number: int, frame: np.ndarray, timestamp_ms: float)."""
        import cv2
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_path = f.name
        try:
            out = cv2.VideoWriter(
                tmp_path,
                cv2.VideoWriter_fourcc(*"mp4v"),
                30,
                (64, 64),
            )
            for _ in range(3):
                frame = np.zeros((64, 64, 3), dtype=np.uint8)
                out.write(frame)
            out.release()
            vi = VideoIngestor(tmp_path)
            frames = list(vi.frames())
            assert len(frames) == 3
            for i, (frame_num, frame_arr, ts) in enumerate(frames):
                assert isinstance(frame_num, int)
                assert isinstance(frame_arr, np.ndarray)
                assert isinstance(ts, float)
                assert frame_arr.shape == (64, 64, 3)
        finally:
            os.unlink(tmp_path)

    def test_frame_count_property(self):
        import cv2
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_path = f.name
        try:
            out = cv2.VideoWriter(
                tmp_path,
                cv2.VideoWriter_fourcc(*"mp4v"),
                30,
                (64, 64),
            )
            for _ in range(5):
                out.write(np.zeros((64, 64, 3), dtype=np.uint8))
            out.release()
            vi = VideoIngestor(tmp_path)
            assert vi.frame_count >= 1  # VideoCapture may report differently on tiny vids
        finally:
            os.unlink(tmp_path)

    def test_fps_property(self):
        import cv2
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_path = f.name
        try:
            out = cv2.VideoWriter(
                tmp_path,
                cv2.VideoWriter_fourcc(*"mp4v"),
                30,
                (64, 64),
            )
            for _ in range(3):
                out.write(np.zeros((64, 64, 3), dtype=np.uint8))
            out.release()
            vi = VideoIngestor(tmp_path)
            assert isinstance(vi.fps, float)
            assert vi.fps > 0
        finally:
            os.unlink(tmp_path)


class TestObjectDetector:
    def test_detect_returns_list(self):
        """detect() must return a list (may be empty on blank frame)."""
        od = ObjectDetector(weights_path="/nonexistent/model.pt")
        frame = np.zeros((640, 640, 3), dtype=np.uint8)
        result = od.detect(frame)
        assert isinstance(result, list)

    def test_detect_returns_detections_with_valid_class_labels(self):
        """All Detection objects must have class_label in ['player', 'ball']."""
        od = ObjectDetector(weights_path="/nonexistent/model.pt")
        frame = np.zeros((640, 640, 3), dtype=np.uint8)
        result = od.detect(frame)
        for det in result:
            assert isinstance(det, Detection)
            assert det.class_label in ("player", "ball")
            assert isinstance(det.confidence, float)
            assert 0.0 <= det.confidence <= 1.0
