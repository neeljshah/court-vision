"""G321 -- parameterised SHADOW of the semantic-line provider's abstention gate.

Frozen by `docs/evidence/tracking/g321_prereg_2026-09-07.md`; every constant below is quoted
from that seal and none may be re-tuned after a number is seen.  `domains/` is READ AND IMPORT
ONLY -- this module re-implements only the two functions whose constants the preregistered grid
moves (`_candidate_quads` and the `_paint` filter chain) and IMPORTS everything else from the
shipped provider, so the R0 cell is the shipped provider by construction.  It measures NO
registration, NO calibration and NO tracking quality, and it names NO landmark as correct.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
from dataclasses import asdict, dataclass
from typing import Iterable

import cv2
import numpy as np

from domains.basketball.tracking.keypoints import (
    BasketballKeypointProvider, PaintQuad, _line_support,
)
from scripts.platformkit.tracking.g304_proposals import SEMANTIC_MAP, VOCABULARY, court_marking_mask

MATCH_RADIUS_PX = 8.0
FRAME_INDICES = tuple(round(i * 174429 / 23) for i in range(24))
STAGES = ("contours", "perimeter", "vertices", "quad_ok", "area", "side", "support")


@dataclass(frozen=True)
class GateParams:
    """Every constant the gate rejects on. R0 holds the values shipped in `keypoints.py`."""

    cell: str = "R0"
    contour_source: str = "canny"      # "canny" (shipped) or "mask" (G304 painted-marking mask)
    perimeter_floor: float = 120.0     # keypoints.py:73
    approx_eps: float = 0.025          # keypoints.py:76
    vertex_max: int = 4                # keypoints.py:77 (len(approx) == 4)
    quad_area_floor: float = 400.0     # keypoints.py:39
    require_convex: bool = True        # keypoints.py:44
    area_frac: float = 0.006           # keypoints.py:82
    side_frac: float = 0.15            # keypoints.py:87
    min_edge_support: float = 0.16     # keypoints.py:62


# The ten preregistered cells. Each differs from R0 in EXACTLY ONE constant.
GRID: tuple[GateParams, ...] = (
    GateParams(),
    GateParams(cell="R1", min_edge_support=0.08),
    GateParams(cell="R2", min_edge_support=0.02),
    GateParams(cell="R3", area_frac=0.002),
    GateParams(cell="R4", side_frac=0.05),
    GateParams(cell="R5", approx_eps=0.050),
    GateParams(cell="R6", vertex_max=6),
    GateParams(cell="R7", perimeter_floor=60.0),
    GateParams(cell="R8", require_convex=False),
    GateParams(cell="R9", contour_source="mask"),
)


def _order_quad(points: np.ndarray, params: GateParams) -> np.ndarray | None:
    """Parameterised `keypoints._ordered_quad`: same order, tunable area floor and convexity."""
    quad = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    if len(quad) != 4:
        return None
    if abs(float(cv2.contourArea(quad.reshape(-1, 1, 2)))) < params.quad_area_floor:
        return None
    center = quad.mean(axis=0)
    ordered = quad[np.argsort(np.arctan2(quad[:, 1] - center[1], quad[:, 0] - center[0]))]
    if params.require_convex and not cv2.isContourConvex(ordered.reshape(-1, 1, 2)):
        return None
    return ordered


def _contour_edges(frame: np.ndarray, gray: np.ndarray, params: GateParams) -> np.ndarray:
    """Return the binary image contours are traced on: shipped Canny, or the G304 marking mask."""
    if params.contour_source == "mask":
        return court_marking_mask(frame)
    return cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)


def run_gate(frame: np.ndarray, params: GateParams) -> tuple[dict, dict]:
    """Run the parameterised gate on one BGR frame; return (named detections, stage counts)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    counts = dict.fromkeys(STAGES, 0)
    contours, _ = cv2.findContours(_contour_edges(frame, gray, params), cv2.RETR_LIST,
                                   cv2.CHAIN_APPROX_SIMPLE)
    counts["contours"] = len(contours)
    candidates: list[PaintQuad] = []
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        if perimeter < params.perimeter_floor:
            continue
        counts["perimeter"] += 1
        approx = cv2.approxPolyDP(contour, params.approx_eps * perimeter, True)
        if not 4 <= len(approx) <= params.vertex_max:
            continue
        counts["vertices"] += 1
        points = approx[:, 0, :]
        if len(points) > 4:                    # R6 only: reduce a 5/6-gon to its min-area box
            points = cv2.boxPoints(cv2.minAreaRect(np.asarray(points, dtype=np.float32)))
        quad = _order_quad(points, params)
        if quad is None:
            continue
        counts["quad_ok"] += 1
        if abs(float(cv2.contourArea(quad.reshape(-1, 1, 2)))) < params.area_frac * width * height:
            continue
        counts["area"] += 1
        sides = np.linalg.norm(quad - np.roll(quad, -1, axis=0), axis=1)
        if float(sides.min()) < params.side_frac * height:
            continue
        counts["side"] += 1
        support = _line_support(gray, quad)
        if support < params.min_edge_support:
            continue
        counts["support"] += 1
        candidates.append(PaintQuad(quad, min(0.99, support)))
    if not candidates:
        return {}, counts
    paint = max(candidates, key=lambda candidate: candidate.confidence)
    named = BasketballKeypointProvider._name_paint(paint)
    named.update(BasketballKeypointProvider._circle_landmarks(gray, named))
    return named, counts


def mapped(named: dict) -> list[tuple[str, float, float]]:
    """Project the provider's raw keys through the G304 SEMANTIC_MAP. Unmapped keys are dropped."""
    return [(SEMANTIC_MAP[key], float(value[0]), float(value[1]))
            for key, value in sorted(named.items()) if key in SEMANTIC_MAP]


def on_player(points: list[tuple[str, float, float]],
              truth: list[tuple[float, float]]) -> int:
    """One-to-one count of emitted points within MATCH_RADIUS_PX of an adjudicated foot point.

    Under premise P2 the truth points are PLAYER FOOT positions, so this is a DEFECT count --
    a court-landmark proposal sitting on a player -- and never a landmark hit.
    """
    if not points or not truth:
        return 0
    cost = np.array([[math.hypot(x - tx, y - ty) for tx, ty in truth] for _, x, y in points])
    from scipy.optimize import linear_sum_assignment          # local: only this path needs it
    rows, cols = linear_sum_assignment(cost)
    return int(sum(1 for r, c in zip(rows, cols) if cost[r, c] <= MATCH_RADIUS_PX))


def load_truth(csv_path: pathlib.Path) -> dict[int, list[tuple[float, float]]]:
    """Read the 113 non-dropped adjudicated G296 points, keyed by source frame index."""
    truth: dict[int, list[tuple[float, float]]] = {}
    with open(csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["source"] == "dropped":
                continue
            truth.setdefault(int(row["frame_id"]), []).append((float(row["x"]), float(row["y"])))
    return truth


def frame_row(frame: np.ndarray, index: int, params: GateParams,
              truth: dict[int, list[tuple[float, float]]]) -> dict:
    """Measure one cell on one frame: stage counts plus the six preregistered quantities."""
    named, counts = run_gate(frame, params)
    points = mapped(named)
    names = sorted({name for name, _, _ in points})
    structures = sorted({VOCABULARY[name] for name in names})
    row = {"cell": params.cell, "source_frame": index, "n_raw_keys": len(named),
           "n_mapped_names": len(names), "n_structures": len(structures),
           "n_named_landmarks": len(names),
           "n_on_player": on_player(points, truth.get(index, [])),
           "n_false_proposals": len(points),
           "raw_keys": "|".join(sorted(named)), "names": "|".join(names),
           "structures": "|".join(structures)}
    row.update({"stage_" + stage: counts[stage] for stage in STAGES})
    return row


READY_FRAMES_BAR = 12          # PROVIDER REPAIRABLE needs a cell ready on >= 12 of the 24 frames
MIN_NAMES, MIN_STRUCTURES, MAX_FALSE = 6, 3, 12


def frame_ready(row: dict) -> bool:
    """The sealed E1 frame rule: >= 6 distinct names over >= 3 structures, <= 12 unconfirmed."""
    return (row["n_named_landmarks"] >= MIN_NAMES and row["n_structures"] >= MIN_STRUCTURES
            and row["n_false_proposals"] <= MAX_FALSE)


def fidelity(frames: Iterable[tuple[int, np.ndarray]]) -> list[dict]:
    """R0 must equal the SHIPPED provider exactly, or the shadow is not the provider."""
    provider = BasketballKeypointProvider()
    out = []
    for index, frame in frames:
        shipped, shadow = provider.detect(frame), run_gate(frame, GRID[0])[0]
        equal = sorted(shipped) == sorted(shadow) and all(
            all(abs(a - b) <= 1e-6 for a, b in zip(shipped[key], shadow[key])) for key in shipped)
        out.append({"source_frame": index, "shipped_keys": len(shipped),
                    "shadow_keys": len(shadow), "equal": equal})
    return out


EYE_CHECK_I = (0, 4, 9, 13, 18, 23)          # EVENLY SPACED over the 24 frames, never a head slice


def overlay(frame: np.ndarray, index: int, best: GateParams, path: pathlib.Path) -> None:
    """Draw the R0 emission (red) and the best cell's emission (green) on one frame."""
    canvas = cv2.resize(frame, (1280, 720))
    caption = ["frame %d" % index]
    for params, colour in ((GRID[0], (0, 0, 255)), (best, (0, 220, 0))):
        points = mapped(run_gate(frame, params)[0])
        for name, x, y in points:
            spot = (int(round(x * 1280 / 1920)), int(round(y * 720 / 1080)))
            cv2.drawMarker(canvas, spot, colour, cv2.MARKER_CROSS, 18, 2)
            cv2.putText(canvas, name, (spot[0] + 8, spot[1] - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, colour, 1)
        caption.append("%s=%d names" % (params.cell, len(points)))
    cv2.putText(canvas, "  ".join(caption), (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 80])


def _frames(frame_dir: pathlib.Path) -> list[tuple[int, np.ndarray]]:
    paths = sorted(frame_dir.glob("frame_*.jpg"))
    if len(paths) != len(FRAME_INDICES):
        raise RuntimeError("expected %d frames, found %d" % (len(FRAME_INDICES), len(paths)))
    return [(index, cv2.imread(str(path))) for index, path in zip(FRAME_INDICES, paths)]


def main() -> None:
    parser = argparse.ArgumentParser(description="G321 semantic-gate funnel and relaxation grid")
    parser.add_argument("--frame-dir", default="g321_frames")
    parser.add_argument("--truth", default="docs/evidence/tracking/g296_ground_truth_2026-09-07.csv")
    parser.add_argument("--out-dir", default="docs/evidence/tracking/g321_artifact")
    args = parser.parse_args()
    frames = _frames(pathlib.Path(args.frame_dir))
    truth = load_truth(pathlib.Path(args.truth))
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    checks = fidelity(frames)
    (out_dir / "fidelity.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="ascii")
    print("FIDELITY equal=%d/%d" % (sum(c["equal"] for c in checks), len(checks)))
    if not all(check["equal"] for check in checks):
        raise SystemExit("SHADOW IS NOT THE PROVIDER -- row stops, no relaxation number is quoted")

    rows = [frame_row(frame, index, params, truth)
            for params in GRID for index, frame in frames]
    fields = list(rows[0])
    with open(out_dir / "cells.csv", "w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "grid.json").write_text(
        json.dumps([asdict(params) for params in GRID], indent=2) + "\n", encoding="ascii")

    for params in GRID:
        cell = [row for row in rows if row["cell"] == params.cell]
        ready = sum(1 for row in cell if frame_ready(row))
        print("%s raw=%d names=%d struct=%d on_player=%d ready=%d/24" % (
            params.cell, sum(r["n_raw_keys"] for r in cell),
            sum(r["n_mapped_names"] for r in cell), max(r["n_structures"] for r in cell),
            sum(r["n_on_player"] for r in cell), ready))
    zeroed = {stage: sum(1 for row in rows if row["cell"] == "R0" and row["stage_" + stage] == 0)
              for stage in STAGES}
    print("R0 STAGE ZEROES /24: " + " ".join("%s=%d" % item for item in zeroed.items()))

    best = max(GRID[1:], key=lambda p: sum(row["n_mapped_names"] for row in rows
                                           if row["cell"] == p.cell))
    for i in EYE_CHECK_I:
        overlay(frames[i][1], frames[i][0], best,
                out_dir / "overlays" / ("g321_i%02d_f%06d.jpg" % (i, frames[i][0])))
    print("overlays=%d best_cell=%s rows=%d out=%s" % (len(EYE_CHECK_I), best.cell, len(rows), out_dir))


if __name__ == "__main__":
    main()
