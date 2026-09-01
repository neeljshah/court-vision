"""Measure EasyOCR numeral registration on a staged NFL broadcast.

Run: python -m domains.football.tracking.numeral_probe VIDEO --output DIR
The output JSON preserves every denominator; JPEGs retain five highest and five
lowest confidence OCR crops for an honest visual audit.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from domains.football.tracking.field_gates import MIN_FIELD_VIEW_GREEN, field_view_fraction
from domains.football.tracking.geometry import FootballGeometryMixin
from domains.football.tracking.numeral_registration import NumeralRead, _reader_or_load, recognize, solve


@dataclass
class NumeralProbe:
    sampled: int = 0
    field_view: int = 0
    candidate_frames: int = 0
    recognized_frames: int = 0
    recognized_numerals: int = 0
    solve_frames: int = 0
    held_out_errors_ft: list[float] = field(default_factory=list)
    scale_errors_pct: list[float] = field(default_factory=list)

    def report(self) -> dict:
        def summary(values: list[float]) -> dict:
            return {"n": len(values), "median": None if not values else float(np.median(values)),
                    "p95": None if not values else float(np.percentile(values, 95))}
        return {**asdict(self), "recognition_rate_field_view": self.recognized_frames / max(self.field_view, 1),
                "held_out_error_ft": summary(self.held_out_errors_ft),
                "scale_error_pct": summary(self.scale_errors_pct)}


def _lines(frame: np.ndarray, geometry: FootballGeometryMixin) -> list[np.ndarray]:
    segments = geometry._segments(frame, max(30.0, frame.shape[1] / 12.0))
    return geometry.family_from_segments(segments)


def _render(frame: np.ndarray, readings: list[NumeralRead], label: str) -> np.ndarray:
    image = frame.copy()
    for read in readings:
        x, y, width, height = map(int, read.box)
        cv2.rectangle(image, (x, y), (x + width, y + height), (0, 255, 255), 2)
        cv2.putText(image, "%d %.2f" % (read.value, read.confidence), (x, max(20, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 0, 0), 3)
        cv2.putText(image, "%d %.2f" % (read.value, read.confidence), (x, max(20, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 255, 255), 1)
    cv2.putText(image, label, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 0), 3)
    cv2.putText(image, label, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 255), 1)
    return image


def measure(video: Path, output: Path, frames: int = 120) -> dict:
    """Run one digits-only reader against >=60 evenly sampled field-view frames."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("could not open %s" % video)
    output.mkdir(parents=True, exist_ok=True)
    geometry, result = FootballGeometryMixin(field_level="nfl"), NumeralProbe()
    reader = _reader_or_load(None)
    saved: list[tuple[float, np.ndarray]] = []
    count = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
    try:
        for index in np.linspace(0, count - 1, num=frames, dtype=int):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                continue
            result.sampled += 1
            if field_view_fraction(frame) < MIN_FIELD_VIEW_GREEN:
                continue
            result.field_view += 1
            lines = _lines(frame, geometry)
            readings = recognize(frame, lines, reader)
            result.candidate_frames += int(bool(lines))
            result.recognized_frames += int(bool(readings))
            result.recognized_numerals += len(readings)
            confidence = max((read.confidence for read in readings), default=0.0)
            saved.append((confidence, _render(frame, readings, "frame=%d reads=%d" % (index, len(readings)))))
            # A fixed image-side order names the near numeral side; it is not
            # selected from held-out error.  The mirror branch must be supplied
            # only by a separate field-direction observation before production.
            solved = solve(readings, side=-1)
            if solved.homography is not None:
                result.solve_frames += 1
                if solved.held_out_error_ft is not None:
                    result.held_out_errors_ft.append(solved.held_out_error_ft)
                if solved.scale_error_pct is not None:
                    result.scale_errors_pct.append(solved.scale_error_pct)
    finally:
        capture.release()
    for rank, (_, image) in enumerate(sorted(saved, key=lambda item: item[0])[:5], 1):
        cv2.imwrite(str(output / ("worst_%02d.jpg" % rank)), image)
    for rank, (_, image) in enumerate(sorted(saved, key=lambda item: item[0], reverse=True)[:5], 1):
        cv2.imwrite(str(output / ("best_%02d.jpg" % rank)), image)
    report = result.report()
    report["gates"] = {"minimum_field_views": 60, "held_out_n": 30,
                       "held_out_median_ft_max": 6.0, "scale_pct_max": 10.0,
                       "pass": bool(result.field_view >= 60 and len(result.held_out_errors_ft) >= 30
                                    and report["held_out_error_ft"]["median"] <= 6.0
                                    and report["scale_error_pct"]["median"] <= 10.0)}
    (output / "numeral_probe.json").write_text(json.dumps(report, indent=2), encoding="ascii")
    return report


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=120)
    args = parser.parse_args(argv[1:])
    report = measure(args.video, args.output, args.frames)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))
