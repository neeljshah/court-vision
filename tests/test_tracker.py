"""
Tests for tracking/tracker.py — ObjectTracker and TrackedObject.

TDD RED phase: All tests written before implementation exists.
Tests cover TrackedObject dataclass structure, ObjectTracker initialization,
velocity computation, and update() return type guarantees.
"""
import dataclasses
import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# TrackedObject dataclass structure
# ---------------------------------------------------------------------------

class TestTrackedObjectDataclass:
    """TrackedObject must be a dataclass with all required fields."""

    def test_is_dataclass(self):
        from tracking.tracker import TrackedObject
        assert dataclasses.is_dataclass(TrackedObject)

    def test_has_track_id(self):
        from tracking.tracker import TrackedObject
        fields = {f.name for f in dataclasses.fields(TrackedObject)}
        assert "track_id" in fields

    def test_has_object_type(self):
        from tracking.tracker import TrackedObject
        fields = {f.name for f in dataclasses.fields(TrackedObject)}
        assert "object_type" in fields

    def test_has_cx_cy(self):
        from tracking.tracker import TrackedObject
        fields = {f.name for f in dataclasses.fields(TrackedObject)}
        assert "cx" in fields
        assert "cy" in fields

    def test_has_bbox(self):
        from tracking.tracker import TrackedObject
        fields = {f.name for f in dataclasses.fields(TrackedObject)}
        assert "bbox" in fields

    def test_has_confidence(self):
        from tracking.tracker import TrackedObject
        fields = {f.name for f in dataclasses.fields(TrackedObject)}
        assert "confidence" in fields

    def test_has_frame_number(self):
        from tracking.tracker import TrackedObject
        fields = {f.name for f in dataclasses.fields(TrackedObject)}
        assert "frame_number" in fields

    def test_has_timestamp_ms(self):
        from tracking.tracker import TrackedObject
        fields = {f.name for f in dataclasses.fields(TrackedObject)}
        assert "timestamp_ms" in fields

    def test_has_velocity_fields(self):
        from tracking.tracker import TrackedObject
        fields = {f.name for f in dataclasses.fields(TrackedObject)}
        assert "velocity_x" in fields
        assert "velocity_y" in fields

    def test_has_speed(self):
        from tracking.tracker import TrackedObject
        fields = {f.name for f in dataclasses.fields(TrackedObject)}
        assert "speed" in fields

    def test_has_direction_degrees(self):
        from tracking.tracker import TrackedObject
        fields = {f.name for f in dataclasses.fields(TrackedObject)}
        assert "direction_degrees" in fields

    def test_instantiation_with_all_fields(self):
        from tracking.tracker import TrackedObject
        obj = TrackedObject(
            track_id=1,
            object_type="player",
            cx=100.0,
            cy=200.0,
            bbox=(90.0, 190.0, 110.0, 210.0),
            confidence=0.9,
            frame_number=0,
            timestamp_ms=0.0,
            velocity_x=0.0,
            velocity_y=0.0,
            speed=0.0,
            direction_degrees=0.0,
        )
        assert obj.track_id == 1
        assert obj.object_type == "player"
        assert obj.cx == 100.0
        assert obj.cy == 200.0


# ---------------------------------------------------------------------------
# ObjectTracker initialization
# ---------------------------------------------------------------------------

class TestObjectTrackerInit:
    """ObjectTracker must initialize correctly with required attributes."""

    def test_instantiation_default_params(self):
        from tracking.tracker import ObjectTracker
        tracker = ObjectTracker()
        assert tracker is not None

    def test_has_previous_positions(self):
        from tracking.tracker import ObjectTracker
        tracker = ObjectTracker()
        assert hasattr(tracker, "previous_positions")
        assert isinstance(tracker.previous_positions, dict)

    def test_previous_positions_initially_empty(self):
        from tracking.tracker import ObjectTracker
        tracker = ObjectTracker()
        assert len(tracker.previous_positions) == 0

    def test_has_update_method(self):
        from tracking.tracker import ObjectTracker
        tracker = ObjectTracker()
        assert hasattr(tracker, "update")
        assert callable(tracker.update)

    def test_has_set_fps_method(self):
        from tracking.tracker import ObjectTracker
        tracker = ObjectTracker()
        assert hasattr(tracker, "set_fps")
        assert callable(tracker.set_fps)

    def test_set_fps_updates_fps(self):
        from tracking.tracker import ObjectTracker
        tracker = ObjectTracker()
        tracker.set_fps(25.0)
        assert tracker.fps == 25.0

    def test_custom_max_age_n_init(self):
        from tracking.tracker import ObjectTracker
        tracker = ObjectTracker(max_age=60, n_init=5)
        assert tracker is not None  # Just verifies no error on construction


# ---------------------------------------------------------------------------
# ObjectTracker.update() return type
# ---------------------------------------------------------------------------

class TestObjectTrackerUpdate:
    """update() must return a list; items must be TrackedObject instances."""

    def _make_frame(self):
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def test_update_returns_list(self):
        from tracking.tracker import ObjectTracker
        tracker = ObjectTracker()
        result = tracker.update([], self._make_frame(), 0, 0.0)
        assert isinstance(result, list)

    def test_update_with_empty_detections_returns_list(self):
        from tracking.tracker import ObjectTracker
        tracker = ObjectTracker()
        result = tracker.update([], self._make_frame(), 0, 0.0)
        assert result == []

    def test_update_items_are_tracked_objects(self):
        """Run enough frames for DeepSORT to confirm a track (n_init=1 for speed)."""
        from tracking.tracker import ObjectTracker, TrackedObject
        from pipelines.detector import Detection

        tracker = ObjectTracker(n_init=1)  # confirm immediately
        frame = self._make_frame()
        det = Detection(
            bbox=(100.0, 100.0, 150.0, 160.0),
            confidence=0.9,
            class_label="player",
            cx=125.0,
            cy=130.0,
        )
        result = tracker.update([det], frame, 0, 33.3)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, TrackedObject)

    def test_tracked_object_has_correct_frame_number(self):
        from tracking.tracker import ObjectTracker, TrackedObject
        from pipelines.detector import Detection

        tracker = ObjectTracker(n_init=1)
        frame = self._make_frame()
        det = Detection(
            bbox=(100.0, 100.0, 150.0, 160.0),
            confidence=0.9,
            class_label="player",
            cx=125.0,
            cy=130.0,
        )
        result = tracker.update([det], frame, 5, 166.5)
        for item in result:
            assert item.frame_number == 5
            assert item.timestamp_ms == 166.5


# ---------------------------------------------------------------------------
# Velocity and physics computation
# ---------------------------------------------------------------------------

class TestVelocityComputation:
    """Velocity must be (delta_cx * fps) and derived quantities must be correct."""

    def _make_frame(self):
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def _make_det(self, cx, cy, label="player"):
        from pipelines.detector import Detection
        w, h = 50.0, 60.0
        return Detection(
            bbox=(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2),
            confidence=0.9,
            class_label=label,
            cx=cx,
            cy=cy,
        )

    def test_first_frame_velocity_is_zero(self):
        """Velocity is 0 the first time a track_id appears in confirmed results.

        With n_init=1, DeepSORT confirms a track on the second call (frame 1),
        because the first call produces a tentative track. The first confirmed
        result (frame 1) has no prior position, so velocity must be 0.
        """
        from tracking.tracker import ObjectTracker

        tracker = ObjectTracker(n_init=1)
        tracker.set_fps(30.0)
        frame = self._make_frame()
        det = self._make_det(100.0, 200.0)
        # First call: tentative track, no confirmed results
        tracker.update([det], frame, 0, 0.0)
        # Second call: track confirmed for the first time — velocity should be 0
        result = tracker.update([det], frame, 1, 33.3)
        assert len(result) >= 1
        obj = result[0]
        assert obj.velocity_x == 0.0
        assert obj.velocity_y == 0.0
        assert obj.speed == 0.0
        assert obj.direction_degrees == 0.0

    def test_speed_is_sqrt_of_vx_vy(self):
        """speed = sqrt(vx^2 + vy^2)."""
        from tracking.tracker import ObjectTracker

        tracker = ObjectTracker(n_init=1)
        tracker.set_fps(30.0)
        frame = self._make_frame()

        # Frame 1
        tracker.update([self._make_det(100.0, 100.0)], frame, 0, 0.0)
        # Frame 2 — move right 10 pixels, down 10 pixels
        result = tracker.update([self._make_det(110.0, 110.0)], frame, 1, 33.3)
        assert len(result) >= 1
        obj = result[0]
        expected_speed = math.sqrt(obj.velocity_x ** 2 + obj.velocity_y ** 2)
        assert abs(obj.speed - expected_speed) < 1e-6

    def test_direction_normalized_to_0_360(self):
        """direction_degrees must be in [0, 360)."""
        from tracking.tracker import ObjectTracker

        tracker = ObjectTracker(n_init=1)
        tracker.set_fps(30.0)
        frame = self._make_frame()

        tracker.update([self._make_det(100.0, 100.0)], frame, 0, 0.0)
        result = tracker.update([self._make_det(110.0, 90.0)], frame, 1, 33.3)
        for obj in result:
            assert 0.0 <= obj.direction_degrees < 360.0

    def test_previous_positions_updated_after_each_frame(self):
        """previous_positions is populated after a track becomes confirmed.

        With n_init=1, confirmed tracks first appear on the second update call.
        After that call, previous_positions must contain at least one entry.
        """
        from tracking.tracker import ObjectTracker

        tracker = ObjectTracker(n_init=1)
        frame = self._make_frame()
        # First call: tentative — previous_positions stays empty
        tracker.update([self._make_det(100.0, 200.0)], frame, 0, 0.0)
        assert len(tracker.previous_positions) == 0
        # Second call: track confirmed — previous_positions now has an entry
        tracker.update([self._make_det(100.0, 200.0)], frame, 1, 33.3)
        assert len(tracker.previous_positions) >= 1
