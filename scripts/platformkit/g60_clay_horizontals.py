"""Read-only G60 measurement of solver-derived above-court horizontals."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable

import cv2
import numpy as np

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.court_diagnostics import rejection_gate
from domains.tennis.tracking.court_lines import (
    TOPHAT_CONTRASTS,
    _ACROSS_TARGET,
    _match,
    court_line_segments,
    select_court_lines,
    solve_corners,
    split_orientation,
)


@dataclass(frozen=True)
class VerticalGuide:
    """Solver-recovered court horizon proxy and two outside doubles sidelines."""

    top: float
    left: np.ndarray
    right: np.ndarray


def horizontal_midpoint(segment: np.ndarray) -> tuple[float, float]:
    """Return a horizontal Hough segment's midpoint in image coordinates."""
    return ((float(segment[0]) + float(segment[2])) / 2.0,
            (float(segment[1]) + float(segment[3])) / 2.0)


def above_court(segment: np.ndarray, guide: VerticalGuide) -> bool:
    """Classify a segment above the solver-derived court-region horizon."""
    return horizontal_midpoint(segment)[1] < guide.top


def vertical_guide(segments: list[np.ndarray], shape: tuple[int, int]) -> VerticalGuide | None:
    """Recover the horizon proxy from exactly the vertical selection used by the solver."""
    _, vertical = split_orientation(segments)
    if len(vertical) < 2:
        return None
    clusters = TennisAdapter._cluster_lines(vertical, False, shape)
    if len(clusters) < 5:
        return None
    fitted = [TennisAdapter._fit_line(cluster) for cluster in clusters]
    positions = [TennisAdapter._line_position(line, False, shape) for line in fitted]
    chosen = _match(positions, 5, _ACROSS_TARGET)
    if chosen is None:
        return None
    five = [clusters[index] for index in chosen]
    upper_rows = [min(TennisAdapter._endpoint_rows(cluster)) for cluster in five]
    return VerticalGuide(top=float(np.median(upper_rows)), left=fitted[chosen[0]], right=fitted[chosen[4]])


def filtered_segments(segments: list[np.ndarray], guide: VerticalGuide) -> tuple[list[np.ndarray], int, int]:
    """Remove only horizontals above the derived court horizon; retain every other segment."""
    horizontal, _ = split_orientation(segments)
    above_ids = {id(segment) for segment in horizontal if above_court(segment, guide)}
    return [segment for segment in segments if id(segment) not in above_ids], len(above_ids), len(horizontal)


def trace_counterfactual(frame: np.ndarray) -> tuple[bool, bool, str]:
    """Re-run unchanged role assignment and corner solve after only above-court removal."""
    role_ok = False
    final_gate = "no_hough_lines"
    for contrast in TOPHAT_CONTRASTS:
        segments = court_line_segments(frame, contrast=contrast)
        if not segments:
            continue
        guide = vertical_guide(segments, frame.shape[:2])
        kept = segments if guide is None else filtered_segments(segments, guide)[0]
        court, final_gate = select_court_lines(kept, frame.shape[:2])
        if court is None:
            continue
        role_ok = True
        corners, final_gate = solve_corners(court, frame.shape[:2])
        if corners is not None:
            return True, True, "accepted"
    return role_ok, False, final_gate


def horizontal_role_segments(frame: np.ndarray) -> tuple[list[np.ndarray], VerticalGuide, int] | None:
    """Return the richest evidence pass that reaches the named role-assignment gate."""
    candidates: list[tuple[int, list[np.ndarray], VerticalGuide, int]] = []
    for contrast in TOPHAT_CONTRASTS:
        segments = court_line_segments(frame, contrast=contrast)
        if not segments:
            continue
        _, gate = select_court_lines(segments, frame.shape[:2])
        if gate != "horizontal_roles":
            continue
        guide = vertical_guide(segments, frame.shape[:2])
        if guide is not None:
            candidates.append((len(segments), segments, guide, contrast))
    if not candidates:
        return None
    _, segments, guide, contrast = max(candidates, key=lambda item: item[0])
    return segments, guide, contrast


def analyze_frame(frame: np.ndarray, frame_no: int, clip: str) -> dict[str, object] | None:
    """Measure one production `horizontal_roles` rejection without changing the solver."""
    choice = horizontal_role_segments(frame)
    if choice is None:
        return None
    segments, guide, contrast = choice
    _, above, horizontal = filtered_segments(segments, guide)
    role_ok, solver_ok, counterfactual_gate = trace_counterfactual(frame)
    return {
        "clip": clip,
        "frame": frame_no,
        "contrast": contrast,
        "raw_gate": rejection_gate(frame),
        "horizontal": horizontal,
        "above": above,
        "inside": horizontal - above,
        "guide_top": guide.top,
        "counterfactual_role_ok": role_ok,
        "counterfactual_solver_ok": solver_ok,
        "counterfactual_gate": counterfactual_gate,
    }


def render_partition(frame: np.ndarray) -> np.ndarray:
    """Draw the mandatory eye-check partition without changing measurement inputs."""
    choice = horizontal_role_segments(frame)
    if choice is None:
        raise ValueError("frame does not reach horizontal_roles with a vertical guide")
    segments, guide, _ = choice
    image = frame.copy()
    horizontal, vertical = split_orientation(segments)
    for segment in vertical:
        cv2.line(image, tuple(segment[:2].astype(int)), tuple(segment[2:].astype(int)), (255, 128, 0), 1)
    for segment in horizontal:
        color = (0, 0, 255) if above_court(segment, guide) else (0, 255, 0)
        cv2.line(image, tuple(segment[:2].astype(int)), tuple(segment[2:].astype(int)), color, 1)
    top = int(round(guide.top))
    cv2.line(image, (0, top), (image.shape[1] - 1, top), (0, 255, 255), 2)
    cv2.putText(image, "red=above green=inside yellow=horizon", (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3)
    cv2.putText(image, "red=above green=inside yellow=horizon", (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
    return image


def frame_grid(capture: cv2.VideoCapture, count: int) -> list[int]:
    """Return a de-duplicated full-clip evenly spaced grid."""
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    return [int(value) for value in np.unique(np.linspace(0, total - 1, count).astype(int))]


def scan(video: str, count: int) -> tuple[list[tuple[str, int, float]], dict[str, int]]:
    """Scan an evenly spaced full-clip grid and retain named decision-set frames."""
    capture = cv2.VideoCapture(video)
    if not capture.isOpened():
        raise FileNotFoundError(video)
    grid = frame_grid(capture, count)
    gates: Counter[str] = Counter()
    eligible: list[tuple[str, int, float]] = []
    try:
        for index, frame_no in enumerate(grid):
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ok, frame = capture.read()
            gate = rejection_gate(frame) if ok else "read_failed"
            gates[gate] += 1
            if gate == "horizontal_roles":
                eligible.append((video, frame_no, index / max(1, len(grid) - 1)))
    finally:
        capture.release()
    return eligible, dict(sorted(gates.items()))


def stratified_pick(rows: list[tuple[str, int, float]], count: int, seed: int) -> list[tuple[str, int, float]]:
    """Seeded one-per-stratum selection, evenly covering the named decision set."""
    if len(rows) < count:
        raise ValueError("eligible horizontal_roles frames %d < requested %d" % (len(rows), count))
    ordered = sorted(rows, key=lambda row: (row[2], row[0], row[1]))
    rng = np.random.default_rng(seed)
    picked = []
    for index in range(count):
        low = index * len(ordered) // count
        high = (index + 1) * len(ordered) // count
        picked.append(ordered[int(rng.integers(low, high))])
    return picked


def measure(videos: Iterable[str], scan_count: int, sample_count: int, seed: int) -> dict[str, object]:
    """Measure seeded, evenly distributed horizontal-role failures across source videos."""
    eligible: list[tuple[str, int, float]] = []
    gates: dict[str, dict[str, int]] = {}
    for video in videos:
        found, counts = scan(video, scan_count)
        eligible.extend(found)
        gates[video] = counts
    selected = stratified_pick(eligible, sample_count, seed)
    records = []
    for video, frame_no, _ in selected:
        capture = cv2.VideoCapture(video)
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ok, frame = capture.read()
        capture.release()
        if not ok:
            raise RuntimeError("selected frame unreadable: %s:%d" % (video, frame_no))
        record = analyze_frame(frame, frame_no, video)
        if record is None:
            raise RuntimeError("selected frame lost its named decision gate: %s:%d" % (video, frame_no))
        records.append(record)
    return {"scan_count_per_video": scan_count, "sample_count": sample_count, "seed": seed,
            "gate_counts": gates, "eligible_horizontal_roles": len(eligible), "records": records}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clay", required=True)
    parser.add_argument("--hard", required=True, nargs="+")
    parser.add_argument("--clay-scan-count", type=int, default=400)
    parser.add_argument("--hard-scan-count", type=int, default=1800)
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--seed", type=int, default=60)
    parser.add_argument("--render-video")
    parser.add_argument("--render-frame", type=int)
    args = parser.parse_args()
    if args.render_video is not None and args.render_frame is not None:
        capture = cv2.VideoCapture(args.render_video)
        capture.set(cv2.CAP_PROP_POS_FRAMES, args.render_frame)
        ok, frame = capture.read()
        capture.release()
        if not ok:
            raise RuntimeError("render frame unreadable")
        ok, encoded = cv2.imencode(".jpg", render_partition(frame), [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        sys.stdout.buffer.write(encoded.tobytes())
        return
    print(json.dumps({"clay": measure([args.clay], args.clay_scan_count, args.samples, args.seed),
                      "hard": measure(args.hard, args.hard_scan_count, args.samples, args.seed)}, indent=2))


if __name__ == "__main__":
    main()
