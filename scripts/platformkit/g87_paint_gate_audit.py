"""Render and replay the G87 hand-marked paint geometry audit."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import (
    CandidateLineGroup,
    ObservedSegment,
    assign_paint_roles,
    candidate_line_group_details,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "docs/evidence/tracking/g87_paint_gate"
HAND_MARKS_PATH = EVIDENCE_DIR / "hand_marks.json"
LINE_ORDER = ("baseline", "free_throw", "lane_low", "lane_high")
LINE_COLOURS = {
    "baseline": (0, 0, 255), "free_throw": (0, 200, 0),
    "lane_low": (255, 0, 0), "lane_high": (0, 255, 255),
}


def load_hand_marks(path: Path = HAND_MARKS_PATH) -> list[dict[str, Any]]:
    """Load the committed, manual endpoint declarations."""
    return json.loads(path.read_text(encoding="utf-8"))


def _groups(mark: dict[str, Any]) -> dict[str, CandidateLineGroup]:
    segments = [ObservedSegment(tuple(mark["lines"][role])) for role in LINE_ORDER]
    details = candidate_line_group_details(segments, angle_deg=0.1, offset_px=1.0)
    by_endpoints = {group.segments[0].endpoints: group for group in details}
    return {role: by_endpoints[tuple(mark["lines"][role])] for role in LINE_ORDER}


def _score(first: CandidateLineGroup, second: CandidateLineGroup) -> float:
    return abs(float(np.dot(first.direction, second.direction)))


def evaluate_mark(mark: dict[str, Any]) -> dict[str, Any]:
    """Replay exactly the four declared lines through the existing role gate."""
    groups = _groups(mark)
    parallel = _score(groups["baseline"], groups["free_throw"]) + _score(
        groups["lane_low"], groups["lane_high"])
    orthogonal = (1.0 - _score(groups["baseline"], groups["lane_low"])) + (
        1.0 - _score(groups["free_throw"], groups["lane_low"]))
    angle = math.degrees(math.acos(min(1.0, _score(groups["baseline"], groups["lane_low"]))))
    roles = assign_paint_roles(
        list(groups.values()), mark["league"], mark["lane_low_image_side"])
    if roles is not None:
        verdict, gate = "PASS", "PASS"
    elif parallel < 1.8:
        verdict, gate = "REJECT", "parallel"
    elif orthogonal < 1.6:
        verdict, gate = "REJECT", "orthogonal"
    else:
        verdict, gate = "REJECT", "post_angle"
    return {
        "clip": mark["clip"], "frame_index": mark["frame_index"],
        "league": mark["league"], "baseline_to_lane_angle_deg": angle,
        "parallel_score": parallel, "orthogonal_score": orthogonal,
        "verdict": verdict, "gate": gate,
    }


def evaluate_all(path: Path = HAND_MARKS_PATH) -> list[dict[str, Any]]:
    """Evaluate every committed manual mark in file order."""
    return [evaluate_mark(mark) for mark in load_hand_marks(path)]


def _source_tile(mark: dict[str, Any], source_root: Path) -> np.ndarray:
    image = cv2.imread(str(source_root / mark["clip"] / mark["source_sheet"]))
    if image is None:
        raise FileNotFoundError(f"missing source board for {mark['clip']} frame {mark['frame_index']}")
    index = int(mark["tile_index"])
    return image[(index // 5) * 384:(index // 5 + 1) * 384, (index % 5) * 640:(index % 5 + 1) * 640].copy()


def render(source_root: Path, output_dir: Path = EVIDENCE_DIR / "renders") -> list[Path]:
    """Create durable visual checks of the manually declared true lines."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for mark, result in zip(load_hand_marks(), evaluate_all()):
        tile = _source_tile(mark, source_root)
        for role in LINE_ORDER:
            x1, y1, x2, y2 = (int(value) for value in mark["lines"][role])
            cv2.line(tile, (x1, y1), (x2, y2), LINE_COLOURS[role], 3, cv2.LINE_AA)
            cv2.putText(tile, role, (x1 + 4, max(18, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.42, LINE_COLOURS[role], 1, cv2.LINE_AA)
        caption = f"{mark['frame_index']} {result['verdict']} {result['gate']} angle={result['baseline_to_lane_angle_deg']:.1f}"
        cv2.rectangle(tile, (0, 0), (min(630, 12 * len(caption)), 24), (0, 0, 0), -1)
        cv2.putText(tile, caption, (5, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        path = output_dir / f"{mark['clip']}__f{mark['frame_index']}.jpg"
        cv2.imwrite(str(path), tile)
        paths.append(path)
    return paths


def write_measurements(output_path: Path = EVIDENCE_DIR / "measurements.csv") -> None:
    """Write the replay results used by the evidence memo."""
    rows = evaluate_all()
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    write_measurements()
    render(args.source_root)


if __name__ == "__main__":
    main()
