"""
TDD tests for CourtDetector (plan 01-02, task 2).
RED phase: these tests must fail before implementation.
"""
import dataclasses
import numpy as np
import pytest

from pipelines.court_detector import CourtDetector, CourtLine, CourtZones


class TestCourtLineDataclass:
    def test_court_line_is_dataclass(self):
        assert dataclasses.is_dataclass(CourtLine)

    def test_court_line_has_required_fields(self):
        fields = {f.name for f in dataclasses.fields(CourtLine)}
        assert "rho" in fields
        assert "theta" in fields
        assert "x1" in fields
        assert "y1" in fields
        assert "x2" in fields
        assert "y2" in fields

    def test_court_line_instantiation(self):
        line = CourtLine(rho=1.0, theta=0.5, x1=0, y1=0, x2=100, y2=0)
        assert line.rho == 1.0
        assert line.theta == 0.5
        assert line.x1 == 0
        assert line.y1 == 0
        assert line.x2 == 100
        assert line.y2 == 0


class TestCourtZonesDataclass:
    def test_court_zones_is_dataclass(self):
        assert dataclasses.is_dataclass(CourtZones)

    def test_court_zones_has_required_fields(self):
        fields = {f.name for f in dataclasses.fields(CourtZones)}
        assert "paint_region" in fields
        assert "three_point_arc_points" in fields
        assert "half_court_line" in fields

    def test_court_zones_allows_none_fields(self):
        zones = CourtZones(
            paint_region=None,
            three_point_arc_points=None,
            half_court_line=None,
        )
        assert zones.paint_region is None
        assert zones.three_point_arc_points is None
        assert zones.half_court_line is None


class TestCourtDetectorDetectLines:
    def setup_method(self):
        self.cd = CourtDetector()
        self.blank_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    def test_detect_lines_returns_list_on_blank_frame(self):
        result = self.cd.detect_lines(self.blank_frame)
        assert isinstance(result, list)

    def test_detect_lines_returns_empty_list_on_blank_frame(self):
        """Blank black frame should produce no lines."""
        result = self.cd.detect_lines(self.blank_frame)
        assert result == []

    def test_detect_lines_returns_court_line_objects(self):
        """Any detected lines must be CourtLine instances."""
        frame_with_lines = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Draw white horizontal and vertical lines
        import cv2
        cv2.line(frame_with_lines, (100, 360), (1180, 360), (255, 255, 255), 3)
        cv2.line(frame_with_lines, (640, 100), (640, 620), (255, 255, 255), 3)
        result = self.cd.detect_lines(frame_with_lines)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, CourtLine)

    def test_detect_lines_handles_none_hough_result(self):
        """Should return [] and not raise if HoughLinesP returns None."""
        # A completely uniform frame produces no edges -> HoughLinesP returns None
        uniform_frame = np.full((720, 1280, 3), 128, dtype=np.uint8)
        result = self.cd.detect_lines(uniform_frame)
        assert isinstance(result, list)

    def test_court_line_has_numeric_rho_theta(self):
        """Lines detected from a real frame must have numeric rho and theta."""
        import cv2
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.line(frame, (0, 360), (1280, 360), (255, 255, 255), 5)
        result = self.cd.detect_lines(frame)
        for line in result:
            assert isinstance(line.rho, float)
            assert isinstance(line.theta, float)


class TestCourtDetectorDetectZones:
    def setup_method(self):
        self.cd = CourtDetector()

    def test_detect_zones_returns_court_zones_on_blank(self):
        blank = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = self.cd.detect_zones(blank)
        assert isinstance(result, CourtZones)

    def test_detect_zones_returns_none_fields_on_blank_frame(self):
        """Blank frame should produce no detectable zones."""
        blank = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = self.cd.detect_zones(blank)
        assert result.paint_region is None
        assert result.three_point_arc_points is None
        assert result.half_court_line is None

    def test_detect_zones_does_not_crash_on_varied_frames(self):
        """Must not raise on any valid image input."""
        import cv2
        # Random noise frame
        noisy = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        result = self.cd.detect_zones(noisy)
        assert isinstance(result, CourtZones)

    def test_detect_zones_returns_valid_paint_region_type_if_detected(self):
        """If paint_region is not None, it must be a list."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = self.cd.detect_zones(frame)
        if result.paint_region is not None:
            assert isinstance(result.paint_region, list)

    def test_detect_zones_returns_valid_half_court_type_if_detected(self):
        """If half_court_line is not None, it must be a tuple."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = self.cd.detect_zones(frame)
        if result.half_court_line is not None:
            assert isinstance(result.half_court_line, tuple)
