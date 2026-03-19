"""
CourtDetector: NBA court line and zone boundary detection using classical CV.

Uses Canny edge detection + HoughLinesP for line extraction and HSV color-based
masking for zone approximation. This is a heuristic, best-effort implementation
designed to provide usable spatial reference data for Phase 2 feature engineering.

Phase 1 goal: output is "usable as spatial reference" — not pixel-perfect.
Court detection is expected to be called once per game or periodically to
calibrate spatial reference, not on every frame.

HSV color ranges for hardwood floor detection (NBA court):
  - Lower bound: (10, 50, 100)  — hue ~15-30 degrees, moderate saturation/value
  - Upper bound: (30, 255, 255)
  These are starting values and may need tuning per video source/broadcast.
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class CourtLine:
    """A single detected court line, parameterized in both polar and Cartesian forms."""
    rho: float    # Distance from origin in Hough polar form
    theta: float  # Angle in radians in Hough polar form
    x1: int       # Start x coordinate
    y1: int       # Start y coordinate
    x2: int       # End x coordinate
    y2: int       # End y coordinate


@dataclass
class CourtZones:
    """Approximate court zone boundaries detected from a frame."""
    paint_region: Optional[List] = None                 # 4 corner points of the paint rectangle
    three_point_arc_points: Optional[List] = None       # Sampled points along three-point arc
    half_court_line: Optional[Tuple] = None             # Two endpoints of the half-court line


# HSV range for NBA hardwood floor color (yellowish-orange wood)
_HARDWOOD_HSV_LOWER = np.array([10, 50, 100], dtype=np.uint8)
_HARDWOOD_HSV_UPPER = np.array([30, 255, 255], dtype=np.uint8)


class CourtDetector:
    """
    Stateless court line and zone detector.

    Both detect_lines() and detect_zones() are safe to call on any frame,
    including blank or invalid frames — they return empty results rather than
    raising exceptions.
    """

    def detect_lines(self, frame: np.ndarray) -> List[CourtLine]:
        """
        Detect court lines in a frame using Canny + HoughLinesP.

        Pipeline:
          1. Grayscale conversion
          2. Gaussian blur (5x5 kernel)
          3. Canny edge detection (low=50, high=150)
          4. Probabilistic Hough line transform

        Args:
            frame: BGR image (H x W x 3) from cv2.

        Returns:
            List of CourtLine objects. Empty list if no lines detected.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=80,
            minLineLength=100,
            maxLineGap=10,
        )

        if lines is None:
            return []

        result: List[CourtLine] = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            # Compute rho and theta from endpoints for consistent polar form
            dx = x2 - x1
            dy = y2 - y1
            # theta = angle of line normal (perpendicular to line direction)
            theta = math.atan2(dy, dx)
            # rho = perpendicular distance from origin to line
            length = math.sqrt(dx * dx + dy * dy)
            if length > 0:
                rho = float(abs(x1 * dy - y1 * dx) / length)
            else:
                rho = 0.0
            result.append(
                CourtLine(
                    rho=rho,
                    theta=float(theta),
                    x1=int(x1),
                    y1=int(y1),
                    x2=int(x2),
                    y2=int(y2),
                )
            )
        return result

    def detect_zones(self, frame: np.ndarray) -> CourtZones:
        """
        Approximate court zone boundaries using HSV color masking + contour detection.

        Attempts to identify:
          - Paint rectangle (largest rectangular contour in lower 2/3 of frame)
          - Half-court line (roughly horizontal line near vertical center)
          - Three-point arc (curved contour near paint region)

        Returns None for each zone it cannot detect rather than raising.

        Args:
            frame: BGR image (H x W x 3) from cv2.

        Returns:
            CourtZones with detected zone data; None for undetectable zones.
        """
        paint_region = None
        three_point_arc_points = None
        half_court_line = None

        try:
            h, w = frame.shape[:2]
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, _HARDWOOD_HSV_LOWER, _HARDWOOD_HSV_UPPER)

            # Morphological cleanup to close gaps
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            if not contours:
                return CourtZones()

            # Sort contours by area descending
            contours = sorted(contours, key=cv2.contourArea, reverse=True)

            # --- Paint region: largest approximately rectangular contour ---
            # Look in the lower two-thirds of the frame (typical broadcast angle)
            for contour in contours[:5]:
                area = cv2.contourArea(contour)
                if area < 5000:
                    continue
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                bx, by, bw, bh = cv2.boundingRect(contour)
                # Paint is roughly rectangular and in lower 2/3 of frame
                if (
                    len(approx) in (4, 5, 6)  # roughly rectangular
                    and by > h // 3           # in lower 2/3
                    and bw > w * 0.05          # at least 5% width
                    and bh > h * 0.05          # at least 5% height
                ):
                    paint_region = approx.reshape(-1, 2).tolist()
                    break

            # --- Half-court line: detect white horizontal line near vertical center ---
            # Use Canny + HoughLinesP scoped to vertical center band
            center_y_start = h // 3
            center_y_end = 2 * h // 3
            center_band = frame[center_y_start:center_y_end, :]
            gray_band = cv2.cvtColor(center_band, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray_band, 200, 255, cv2.THRESH_BINARY)
            lines = cv2.HoughLinesP(
                thresh,
                rho=1,
                theta=np.pi / 180,
                threshold=50,
                minLineLength=w // 4,
                maxLineGap=20,
            )
            if lines is not None:
                # Find most horizontal line (smallest absolute angle to horizontal)
                best_line = None
                best_angle = float("inf")
                for line in lines:
                    lx1, ly1, lx2, ly2 = line[0]
                    angle = abs(math.atan2(ly2 - ly1, lx2 - lx1))
                    # Near horizontal: angle close to 0 or pi
                    horiz_angle = min(angle, abs(math.pi - angle))
                    if horiz_angle < best_angle:
                        best_angle = horiz_angle
                        best_line = (
                            (lx1, ly1 + center_y_start),
                            (lx2, ly2 + center_y_start),
                        )
                # Only keep if reasonably horizontal (< 15 degrees from horizontal)
                if best_line is not None and best_angle < math.radians(15):
                    half_court_line = best_line

        except Exception:
            # Never crash the caller — return whatever we found so far
            pass

        return CourtZones(
            paint_region=paint_region,
            three_point_arc_points=three_point_arc_points,
            half_court_line=half_court_line,
        )
