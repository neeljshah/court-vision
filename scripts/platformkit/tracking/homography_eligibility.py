"""Frame-level tennis court-calibration diagnosis and controlled replay."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.segmenter import detect_cut, small_gray


@dataclass(frozen=True)
class LineConfig:
    """One independently testable court-line detection configuration."""

    bright_low: int = 200
    hough_threshold: int = 45
    min_line_fraction: int = 12
    max_gap: int = 20
    reprojection_max: float = 2.0


@dataclass(frozen=True)
class FrameDiagnosis:
    """Result and provenance for a single attempted frame."""

    frame: int
    status: str
    cause: str
    horizontal_lines: int
    vertical_lines: int
    blur_variance: float
    reprojection_error: Optional[float]


def _lines(frame: np.ndarray, config: LineConfig) -> tuple[list[np.ndarray], list[np.ndarray]]:
    height, width = frame.shape[:2]
    bright = cv2.inRange(frame, np.full(3, config.bright_low), np.full(3, 255))
    found = cv2.HoughLinesP(bright, 1, np.pi / 180.0, config.hough_threshold,
                             minLineLength=max(40, width // config.min_line_fraction),
                             maxLineGap=config.max_gap)
    horizontal, vertical = [], []
    if found is None:
        return horizontal, vertical
    for item in found.reshape(-1, found.shape[-1]):
        line = item.astype(float)
        dx, dy = abs(line[2] - line[0]), abs(line[3] - line[1])
        if dx >= 1.5 * dy:
            horizontal.append(line)
        elif dy > dx:
            vertical.append(line)
    return horizontal, vertical


def _corners(frame: np.ndarray, config: LineConfig) -> tuple[Optional[np.ndarray], FrameDiagnosis]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    horizontal, vertical = _lines(frame, config)
    empty = not horizontal and not vertical
    if empty:
        return None, FrameDiagnosis(-1, "unavailable", "non_court_scene", 0, 0, blur, None)
    if blur < 20.0:
        return None, FrameDiagnosis(-1, "unavailable", "motion_blur", len(horizontal), len(vertical), blur, None)
    if len(horizontal) < 2 or len(vertical) < 2:
        return None, FrameDiagnosis(-1, "unavailable", "too_few_line_features", len(horizontal), len(vertical), blur, None)
    height, width = frame.shape[:2]
    grouped_h = TennisAdapter._cluster_lines(horizontal, True, (height, width))
    grouped_v = TennisAdapter._cluster_lines(vertical, False, (height, width))
    if len(grouped_h) < 2 or len(grouped_v) < 2:
        return None, FrameDiagnosis(-1, "unavailable", "too_few_line_features", len(horizontal), len(vertical), blur, None)
    far, near = TennisAdapter._fit_line(grouped_h[0]), TennisAdapter._fit_line(grouped_h[-1])
    left, right = TennisAdapter._fit_line(grouped_v[0]), TennisAdapter._fit_line(grouped_v[-1])
    points = [TennisAdapter._intersection(near, left), TennisAdapter._intersection(near, right),
              TennisAdapter._intersection(far, left), TennisAdapter._intersection(far, right)]
    if any(point is None for point in points):
        return None, FrameDiagnosis(-1, "unavailable", "camera_angle_outside_range", len(horizontal), len(vertical), blur, None)
    corners = np.asarray(points, dtype=np.float32)
    if (np.any(corners[:, 0] < -5) or np.any(corners[:, 0] > width + 5)
            or np.any(corners[:, 1] < -5) or np.any(corners[:, 1] > height + 5)):
        return None, FrameDiagnosis(-1, "unavailable", "camera_angle_outside_range", len(horizontal), len(vertical), blur, None)
    homography = TennisAdapter.homography_from_corners(corners)
    expected = np.float32(((0, 0), (0, 36), (78, 0), (78, 36)))
    actual = cv2.perspectiveTransform(corners.reshape(1, -1, 2), homography)[0]
    error = float(np.linalg.norm(actual - expected, axis=1).mean())
    if not np.isfinite(error) or error > config.reprojection_max:
        return None, FrameDiagnosis(-1, "unavailable", "solver_rejection", len(horizontal), len(vertical), blur, error)
    return homography, FrameDiagnosis(-1, "solved", "solved", len(horizontal), len(vertical), blur, error)


class PropagationGate:
    """Bridge only short, uncut, nearly-static calibration gaps."""

    def __init__(self, max_gap: int = 6, static_delta: float = 4.0) -> None:
        self.max_gap, self.static_delta = max_gap, static_delta
        self._last_h: Optional[np.ndarray] = None
        self._last_gray: Optional[np.ndarray] = None
        self._gap = 0

    def update(self, solved: Optional[np.ndarray], frame: np.ndarray) -> tuple[Optional[np.ndarray], str]:
        gray = small_gray(frame)
        if solved is not None:
            self._last_h, self._gap = solved, 0
            self._last_gray = gray
            return solved, "solved"
        if self._last_h is None or self._last_gray is None:
            self._last_gray = gray
            return None, "unavailable"
        delta = float(np.mean(np.abs(gray.astype(float) - self._last_gray.astype(float))))
        cut = detect_cut(self._last_gray, gray)
        self._last_gray = gray
        if cut or delta > self.static_delta or self._gap >= self.max_gap:
            self._last_h = None if cut else self._last_h
            self._gap = 0 if cut else self._gap + 1
            return None, "unavailable"
        self._gap += 1
        return self._last_h, "propagated"


def inspect_video(video: Path, frames: int, config: LineConfig, propagation: bool) -> dict[str, object]:
    """Measure one video, producing frame causes and solved/propagated eligibility."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % video)
    gate = PropagationGate()
    diagnoses: list[FrameDiagnosis] = []
    try:
        for index in range(frames):
            ok, frame = capture.read()
            if not ok:
                break
            solved, diagnosis = _corners(frame, config)
            homography, provenance = gate.update(solved, frame) if propagation else (solved, diagnosis.status)
            status = provenance if homography is not None else "unavailable"
            cause = diagnosis.cause if status == "unavailable" else status
            diagnoses.append(FrameDiagnosis(index, status, cause, diagnosis.horizontal_lines,
                                            diagnosis.vertical_lines, diagnosis.blur_variance,
                                            diagnosis.reprojection_error))
    finally:
        capture.release()
    return {"source": str(video), "frames": len(diagnoses), "config": asdict(config),
            "propagation": propagation, "statuses": dict(Counter(item.status for item in diagnoses)),
            "causes": dict(Counter(item.cause for item in diagnoses)),
            "frame_diagnostics": [asdict(item) for item in diagnoses]}


def eligibility_summary(report: dict[str, object], skip_non_court: bool = False) -> dict[str, object]:
    """Derive an explicit denominator and eligibility count from a frame report."""
    diagnostics = report["frame_diagnostics"]
    denominator = len(diagnostics) - sum(item["cause"] == "non_court_scene" for item in diagnostics) if skip_non_court else len(diagnostics)
    eligible = sum(item["status"] in ("solved", "propagated") for item in diagnostics)
    return {"eligible_frames": eligible, "denominator_frames": denominator,
            "eligibility_pct": 0.0 if not denominator else 100.0 * eligible / denominator,
            "non_court_skipped": len(diagnostics) - denominator}


def run_arms(videos: Sequence[Path], frames: int) -> dict[str, object]:
    """Run independent calibration levers; each arm changes one setting only."""
    arms = (("baseline", LineConfig(), False, False),
            ("temporal_propagation", LineConfig(), True, False),
            ("relaxed_reprojection", LineConfig(reprojection_max=4.0), False, False),
            ("line_tuning", LineConfig(bright_low=175, hough_threshold=30), False, False),
            ("skip_non_court", LineConfig(), False, True))
    output: dict[str, object] = {"frames_requested_per_game": frames, "arms": {}}
    for name, config, propagation, skip in arms:
        games = [inspect_video(video, frames, config, propagation) for video in videos]
        output["arms"][name] = [{"game": game, "eligibility": eligibility_summary(game, skip)} for game in games]
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("--frames", type=int, default=500)
    parser.add_argument("--propagation", action="store_true")
    parser.add_argument("--all-arms", action="store_true")
    parser.add_argument("--bright-low", type=int, default=200)
    parser.add_argument("--hough-threshold", type=int, default=45)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.frames < 1:
        raise ValueError("frames must be positive")
    config = LineConfig(bright_low=args.bright_low, hough_threshold=args.hough_threshold)
    report = run_arms(args.videos, args.frames) if args.all_arms else [inspect_video(path, args.frames, config, args.propagation) for path in args.videos]
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="ascii")
    print("HOMOGRAPHY_ELIGIBILITY %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
