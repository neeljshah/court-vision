"""G304 attempt 2 -- algorithmic landmark PROPOSAL generator (raters verify, never locate).

Frozen by `docs/evidence/tracking/g304_proposal_verify_prereg_2026-09-07.md`; every constant
here is quoted from that seal and none may be re-tuned after a rating is seen.  This module
produces CANDIDATE points and marked crops only.  It rates nothing, fits nothing, projects
nothing and measures no registration, calibration or tracking quality whatsoever.
`domains/` is READ AND IMPORT ONLY.
"""
from __future__ import annotations

import argparse
import csv
import math
import pathlib
from collections import OrderedDict
from itertools import combinations
from typing import Iterable, NamedTuple

import cv2
import numpy as np

from domains.basketball.tracking.keypoints import BasketballKeypointProvider
from domains.basketball.tracking.line_calibration import (
    _covers, _intersection, candidate_line_group_details, detect_lsd_segments,
)

WIDTH, HEIGHT = 1920, 1080
CAP = 12
DEDUPE_PX = 5.0
MIN_CROSS_ANGLE_DEG = 25.0
EXTENT_TOLERANCE_PX = 40.0

# Vocabulary name -> marking structure (the ">= 3 distinct structures" rule counts these).
VOCABULARY = {
    "CORNER_NEAR_L": "court_corner", "CORNER_NEAR_R": "court_corner",
    "CORNER_FAR_L": "court_corner", "CORNER_FAR_R": "court_corner",
    "LANE_BASE_L": "lane_boundary", "LANE_BASE_R": "lane_boundary",
    "FT_LINE_L": "lane_boundary", "FT_LINE_R": "lane_boundary",
    "KEY_TOP": "free_throw_line",
    "THREE_PT_BASE_L": "three_point_arc", "THREE_PT_BASE_R": "three_point_arc",
    "CENTER_SIDELINE_NEAR": "midcourt_line", "CENTER_SIDELINE_FAR": "midcourt_line",
    "CENTER_CIRCLE_TOP": "center_circle", "CENTER_CIRCLE_BOTTOM": "center_circle",
}

BAND_SIDE_NAMES = {
    ("NEAR", "L"): "CORNER_NEAR_L", ("NEAR", "C"): "LANE_BASE_L", ("NEAR", "R"): "CORNER_NEAR_R",
    ("MID", "L"): "THREE_PT_BASE_L", ("MID", "C"): "FT_LINE_L", ("MID", "R"): "THREE_PT_BASE_R",
    ("FAR", "L"): "CORNER_FAR_L", ("FAR", "C"): "KEY_TOP", ("FAR", "R"): "CORNER_FAR_R",
}
CENTER_OVERRIDE = {"NEAR": "CENTER_SIDELINE_NEAR", "FAR": "CENTER_SIDELINE_FAR"}

# The semantic provider's own names; `center_circle` is deliberately unmapped because the
# provider returns a circle CENTRE and the vocabulary names the circle's top and bottom.
SEMANTIC_MAP = {
    "left_paint_bl": "LANE_BASE_L", "left_paint_br": "LANE_BASE_R",
    "left_paint_tl": "FT_LINE_L", "left_paint_tr": "FT_LINE_R",
    "left_ft_circle": "KEY_TOP", "right_ft_circle": "KEY_TOP",
}


class Proposal(NamedTuple):
    """One candidate landmark point in native 1920x1080 pixels."""

    name: str
    source: str
    x: float
    y: float
    score: float


def name_for(x: float, y: float, allow_center: bool) -> str:
    """Return the preregistered positional-table name for a point. A HYPOTHESIS, not truth."""
    bx, by = x / float(WIDTH), y / float(HEIGHT)
    band = "NEAR" if by >= 0.66 else ("MID" if by >= 0.33 else "FAR")
    side = "L" if bx < 0.40 else ("C" if bx < 0.60 else "R")
    if allow_center and side == "C" and band in CENTER_OVERRIDE:
        return CENTER_OVERRIDE[band]
    return BAND_SIDE_NAMES[(band, side)]


def court_marking_mask(frame: np.ndarray) -> np.ndarray:
    """Return the painted-marking mask: HSV value > 170 AND saturation < 60, closed 3x3."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 2] > 170) & (hsv[:, :, 1] < 60)).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def lsd_proposals(frame: np.ndarray, allow_center: bool) -> list[Proposal]:
    """Intersect grouped LSD lines that actually cross, keeping only supported points."""
    groups = candidate_line_group_details(detect_lsd_segments(frame))
    cosine_limit = float(np.cos(np.deg2rad(MIN_CROSS_ANGLE_DEG)))
    out: list[Proposal] = []
    for first, second in combinations(groups, 2):
        aligned = abs(first.direction[0] * second.direction[0]
                      + first.direction[1] * second.direction[1])
        if aligned > cosine_limit:
            continue
        point = _intersection(first.line, second.line)
        if point is None or not (0.0 <= point[0] < WIDTH and 0.0 <= point[1] < HEIGHT):
            continue
        if not (_covers(first, point, EXTENT_TOLERANCE_PX)
                and _covers(second, point, EXTENT_TOLERANCE_PX)):
            continue
        score = min(1.0, min(first.length, second.length) / float(WIDTH))
        out.append(Proposal(name_for(point[0], point[1], allow_center),
                            "lsd_intersect", point[0], point[1], score))
    return out


def semantic_proposals(frame: np.ndarray) -> list[Proposal]:
    """Read the in-repo semantic provider; abstention yields an empty list, not a failure."""
    detected = BasketballKeypointProvider().detect(frame)
    return [Proposal(SEMANTIC_MAP[key], "semantic", float(value[0]), float(value[1]),
                     float(value[2]))
            for key, value in sorted(detected.items()) if key in SEMANTIC_MAP]


def shitomasi_proposals(frame: np.ndarray, allow_center: bool) -> list[Proposal]:
    """Shi-Tomasi corners on the marking mask -- the third preregistered proposal family."""
    corners = cv2.goodFeaturesToTrack(court_marking_mask(frame), 80, 0.01, 25)
    if corners is None:
        return []
    out = []
    for rank, (x, y) in enumerate(corners.reshape(-1, 2)):
        out.append(Proposal(name_for(float(x), float(y), allow_center), "shitomasi",
                            float(x), float(y), 1.0 - rank / 80.0))
    return out


def _round_robin(items: list[Proposal], key) -> list[Proposal]:
    """Interleave items by `key` so no single key value monopolises the head of the list."""
    buckets: "OrderedDict[str, list[Proposal]]" = OrderedDict()
    for item in items:
        buckets.setdefault(key(item), []).append(item)
    out: list[Proposal] = []
    while any(buckets.values()):
        for value in list(buckets):
            if buckets[value]:
                out.append(buckets[value].pop(0))
    return out


def select(proposals: Iterable[Proposal], cap: int = CAP) -> list[Proposal]:
    """Dedupe same-name neighbours, then interleave families, then names (AMENDMENT 1).

    Family interleaving comes first because the families' scores are NOT on a comparable
    scale; without it the coarser family takes the head of nearly every name bucket.
    """
    ordered = sorted(proposals, key=lambda p: (-p.score, p.name, p.source, p.x, p.y))
    kept: list[Proposal] = []
    for item in ordered:
        if any(other.name == item.name
               and math.hypot(other.x - item.x, other.y - item.y) < DEDUPE_PX
               for other in kept):
            continue
        kept.append(item)
    families: "OrderedDict[str, list[Proposal]]" = OrderedDict()
    for item in kept:
        families.setdefault(item.source, []).append(item)
    queues = OrderedDict((source, _round_robin(items, lambda p: p.name))
                         for source, items in families.items())
    out: list[Proposal] = []
    while len(out) < cap and any(queues.values()):
        for source in list(queues):
            if not queues[source]:
                continue
            out.append(queues[source].pop(0))
            if len(out) >= cap:
                break
    return out


def frame_proposals(frame: np.ndarray, allow_center: bool, cap: int = CAP) -> list[Proposal]:
    """Run all three preregistered families over one native frame and apply the cap."""
    return select(lsd_proposals(frame, allow_center)
                  + semantic_proposals(frame)
                  + shitomasi_proposals(frame, allow_center), cap)


def _crop(frame: np.ndarray, x: float, y: float, size: int) -> tuple[np.ndarray, int, int]:
    height, width = frame.shape[:2]
    x0 = min(max(0, int(round(x)) - size // 2), max(0, width - size))
    y0 = min(max(0, int(round(y)) - size // 2), max(0, height - size))
    return frame[y0:y0 + size, x0:x0 + size].copy(), x0, y0


def render(frame: np.ndarray, item: Proposal, proposal_id: str, path: pathlib.Path) -> None:
    """Write the marked crop: native 160 px panel plus a 400 px context panel, 1-px marker."""
    near, near_x, near_y = _crop(frame, item.x, item.y, 160)
    context, ctx_x, ctx_y = _crop(frame, item.x, item.y, 400)
    for panel, off_x, off_y in ((near, near_x, near_y), (context, ctx_x, ctx_y)):
        px, py = int(round(item.x - off_x)), int(round(item.y - off_y))
        cv2.line(panel, (px - 6, py), (px + 6, py), (0, 0, 255), 1)
        cv2.line(panel, (px, py - 6), (px, py + 6), (0, 0, 255), 1)
    canvas = np.zeros((424, 568, 3), np.uint8)
    canvas[144:144 + near.shape[0], 4:4 + near.shape[1]] = near
    canvas[24:24 + context.shape[0], 168:168 + context.shape[1]] = context
    cv2.putText(canvas, "%s  %s" % (proposal_id, item.name), (4, 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 85])


def eligible_rows(pairs: list[tuple[str, str]]) -> list[dict]:
    """Read the sealed eligibility CSVs and pair each ELIGIBLE row with its render path."""
    rows = []
    for csv_path, render_dir in pairs:
        with open(csv_path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["classification"] != "ELIGIBLE":
                    continue
                structures = row.get("visible_structures", "").lower()
                rows.append({
                    "row_id": row["row_id"], "arena": row["arena"],
                    "render": pathlib.Path(render_dir) / (row["row_id"] + ".jpg"),
                    "allow_center": "midcourt" in structures or "center-circle" in structures,
                })
    return rows


def generate(pairs: list[tuple[str, str]], crop_root: pathlib.Path, out_csv: pathlib.Path,
             cap: int = CAP, limit: int | None = None) -> list[dict]:
    """Generate, render and tabulate proposals for every ELIGIBLE row. Rates nothing."""
    records = []
    rows = eligible_rows(pairs)[:limit]
    for row in rows:
        frame = cv2.imread(str(row["render"]))
        if frame is None:
            raise FileNotFoundError("missing render: %s" % row["render"])
        items = frame_proposals(frame, row["allow_center"], cap)
        for index, item in enumerate(items, start=1):
            proposal_id = "%s_p%02d" % (row["row_id"], index)
            render(frame, item, proposal_id, crop_root / row["row_id"] / (proposal_id + ".jpg"))
            records.append({"row_id": row["row_id"], "proposal_id": proposal_id,
                            "landmark_name": item.name, "source": item.source,
                            "x": round(item.x, 2), "y": round(item.y, 2),
                            "score": round(item.score, 4)})
        print("%s %s proposals=%d" % (row["row_id"], row["arena"], len(items)))
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["row_id", "proposal_id", "landmark_name",
                                                    "source", "x", "y", "score"])
        writer.writeheader()
        writer.writerows(records)
    print("rows=%d proposals=%d csv=%s" % (len(rows), len(records), out_csv))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="G304 attempt 2 proposal generator")
    parser.add_argument("--pair", nargs=2, action="append", metavar=("CSV", "RENDER_DIR"),
                        required=True, help="eligibility CSV and its native render directory")
    parser.add_argument("--crop-root", default="g304_proposal_crops")
    parser.add_argument("--out-csv", default="docs/evidence/tracking/g304_proposals_2026-09-07.csv")
    parser.add_argument("--cap", type=int, default=CAP)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    generate([(a, b) for a, b in args.pair], pathlib.Path(args.crop_root),
             pathlib.Path(args.out_csv), args.cap, args.limit)


if __name__ == "__main__":
    main()
