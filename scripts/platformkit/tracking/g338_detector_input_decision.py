"""G338 pure plausibility arithmetic and preregistered input-size decision rule."""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict

COURT_LENGTH_FT = 94.0
PLAUSIBILITY_FIELDS = (
    "band_share", "height_share", "wholly_in_frame_share", "court_share", "persistence_share",
)


def intersects_frame(box, width: int, height: int) -> bool:
    """G325 frame-containment gate: the unpadded rectangle intersects the decoded frame."""
    x1, y1, x2, y2 = map(float, box[:4])
    return x2 > 0 and y2 > 0 and x1 < width and y1 < height


def wholly_in_frame(box, width: int, height: int) -> bool:
    """True only when the full unpadded rectangle lies in the decoded frame."""
    x1, y1, x2, y2 = map(float, box[:4])
    return x1 >= 0 and y1 >= 0 and x2 <= width and y2 <= height


def iou(a, b) -> float:
    """Intersection-over-union for two xyxy boxes."""
    ax1, ay1, ax2, ay2 = map(float, a[:4])
    bx1, by1, bx2, by2 = map(float, b[:4])
    w, h = max(0.0, min(ax2, bx2) - max(ax1, bx1)), max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = w * h
    union = max(0.0, (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter)
    return inter / union if union else 0.0


def percentile(values, q: float):
    """Nearest-rank percentile, or None for an empty denominator."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def height_ft(box, homography, map_width: int):
    """Fallback-homography proxy for box height, in court-map long-axis feet."""
    if homography is None or not map_width:
        return None
    x1, y1, x2, y2 = map(float, box[:4])
    cx = (x1 + x2) / 2.0

    def project(x, y):
        a, b, c = homography[0]
        d, e, f = homography[1]
        g, h, i = homography[2]
        den = g * x + h * y + i
        return None if abs(den) < 1e-12 else ((a * x + b * y + c) / den, (d * x + e * y + f) / den)

    top, bottom = project(cx, y1), project(cx, y2)
    if top is None or bottom is None:
        return None
    return math.dist(top, bottom) * COURT_LENGTH_FT / float(map_width)


def court_hit(box, homography, map_width: int, map_height: int) -> bool | None:
    """Whether the bottom centre projects into the fallback court map."""
    if homography is None:
        return None
    x1, _, x2, y2 = map(float, box[:4])
    x, y = (x1 + x2) / 2.0, y2
    a, b, c = homography[0]
    d, e, f = homography[1]
    g, h, i = homography[2]
    den = g * x + h * y + i
    if abs(den) < 1e-12:
        return None
    px, py = (a * x + b * y + c) / den, (d * x + e * y + f) / den
    return 0 <= px < map_width and 0 <= py < map_height


def persistence_share(frames: list[list]) -> tuple[int, int]:
    """Return numerator/denominator for boxes in chains of three sampled frames at IoU >= .5."""
    total = sum(len(frame) for frame in frames)
    persistent = set()
    for idx in range(1, len(frames) - 1):
        for mid_idx, box in enumerate(frames[idx]):
            left = next((j for j, other in enumerate(frames[idx - 1]) if iou(box, other) >= 0.5), None)
            right = next((j for j, other in enumerate(frames[idx + 1]) if iou(box, other) >= 0.5), None)
            if left is not None and right is not None:
                persistent.update(((idx - 1, left), (idx, mid_idx), (idx + 1, right)))
    return len(persistent), total


def summarize(records: list[dict]) -> dict:
    """Summarize one arm x section raw-record set without silently dropping empty frames."""
    ordered = sorted(records, key=lambda r: int(r["frame_index"]))
    if not ordered:
        return {"n_frames": 0, "n_boxes": 0}
    per_frame, all_boxes, heights, court = [], [], [], []
    wholly = 0
    for row in ordered:
        boxes = [b for b in row.get("boxes", []) if intersects_frame(b, row["frame_w"], row["frame_h"])]
        per_frame.append(len(boxes))
        all_boxes.extend(boxes)
        wholly += sum(wholly_in_frame(b, row["frame_w"], row["frame_h"]) for b in boxes)
        for box in boxes:
            h = height_ft(box, row.get("homography"), row.get("map_w", 0))
            if h is not None:
                heights.append(h)
            hit = court_hit(box, row.get("homography"), row.get("map_w", 0), row.get("map_h", 0))
            if hit is not None:
                court.append(hit)
    persistent, pden = persistence_share([[b for b in r.get("boxes", [])
                                           if intersects_frame(b, r["frame_w"], r["frame_h"])]
                                          for r in ordered])
    n_boxes = len(all_boxes)
    ms = [float(r["ms"]) for r in ordered]
    return {
        "n_frames": len(ordered), "n_boxes": n_boxes,
        "players_median": percentile(per_frame, 0.5), "players_p10": percentile(per_frame, 0.1),
        "players_p90": percentile(per_frame, 0.9),
        "band_share": sum(8 <= n <= 13 for n in per_frame) / len(per_frame),
        "height_n": len(heights), "height_share": (sum(5.5 <= h <= 7.5 for h in heights) / len(heights)
                                                   if heights else None),
        "wholly_in_frame_share": wholly / n_boxes if n_boxes else None,
        "court_n": len(court), "court_share": sum(court) / len(court) if court else None,
        "persistence_n": pden, "persistence_share": persistent / pden if pden else None,
        "ball_per_frame": sum(int(r.get("ball_count", 0)) for r in ordered) / len(ordered),
        "ms_per_frame": sum(ms) / len(ms), "gpu_mib": max(int(r.get("gpu_mib", 0)) for r in ordered),
    }


def decide(by_section: dict[str, dict[int, dict]]) -> dict:
    """Apply G338's sealed smallest-within-5-percent and throughput decision exactly."""
    sizes = sorted({size for arms in by_section.values() for size in arms})
    qualified = defaultdict(int)
    for _, arms in by_section.items():
        if 640 not in arms:
            continue
        best = {field: max((row.get(field) for row in arms.values() if row.get(field) is not None), default=None)
                for field in PLAUSIBILITY_FIELDS}
        for size, row in arms.items():
            close = all(best[field] is not None and row.get(field) is not None and row[field] >= .95 * best[field]
                        for field in PLAUSIBILITY_FIELDS)
            throughput = arms[640]["ms_per_frame"] / row["ms_per_frame"] >= .8
            if close and throughput:
                qualified[size] += 1
    eligible = [size for size in sizes if qualified[size] >= 4]
    return {"recommended_imgsz": min(eligible) if eligible else None,
            "sections_qualified": {size: qualified[size] for size in sizes}}


def verify_seal(path) -> str:
    """Hash prereg bytes above its seal after CRLF-to-LF normalization (landing-safe)."""
    raw = open(path, "rb").read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    above, seal = raw.rsplit(b"SEAL sha256 ", 1)
    actual, declared = hashlib.sha256(above).hexdigest(), seal.strip().decode("ascii")
    if actual != declared:
        raise ValueError("G338 preregistration seal mismatch")
    return actual
