"""Reproduce the verifier-computed footpoint analyses landed in RESULTS_LEDGER.md on 2026-09-04.

Every number these functions return was quoted in a ledger row that had no committed script.
Measurement only: reads landed artifacts, writes nothing, changes no threshold.

Inputs (both committed):
  g267_court_space_physical_plausibility_artifact/g267_measurement.json
  g285b_locate_then_match_recall_artifact/located_feet.csv

Run:  python -m scripts.platformkit.tracking.verifier_footpoint_analyses
"""
from __future__ import annotations

import csv
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

EVID = Path("docs/evidence/tracking")
G267 = EVID / "g267_court_space_physical_plausibility_artifact" / "g267_measurement.json"
LOCATED = EVID / "g285b_locate_then_match_recall_artifact" / "located_feet.csv"

# G273's crop, used as its acceptance box: 512 wide x 640 tall, centred on the footpoint.
CROP_HALF_W, CROP_HALF_H = 256, 320
IMPLAUSIBLE_FT_PER_S = 40.0  # G267/G270 published bar; never moved here
FPS = 30.0


def load_detections(path: Path = G267):
    """Per-frame finite detections, in source order."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["frame_records"]


def load_located(path: Path = LOCATED):
    """G285b's sealed hand-located player feet, keyed by source frame."""
    out = defaultdict(list)
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            out[int(row["source_frame"])].append(
                (float(row["foot_x_px"]), float(row["foot_y_px"]))
            )
    return out


def steps(records):
    """Consecutive-OBSERVATION same-id steps, the G267/G279 definition.

    Not frame-gap-1: requiring a unit gap gives 26,517 steps and a false 0.111966,
    against the reference 4,090 / 29,973 = 0.136456.
    """
    prev, out = {}, []
    for rec in records:
        frame = rec["source_frame"]
        for det in rec.get("detections") or []:
            if not det.get("finite"):
                continue
            tid = det["track_id"]
            before = prev.get(tid)
            if before is not None and frame > before[0]:
                gap = frame - before[0]
                dist = math.hypot(det["court_x_ft"] - before[1], det["court_y_ft"] - before[2])
                out.append((tid, dist * FPS / gap))
            prev[tid] = (frame, det["court_x_ft"], det["court_y_ft"])
    return out


def implausible_rate(records):
    """Reproduces G279's all-steps figure: 4090 / 29973 = 0.136456."""
    rows = steps(records)
    bad = sum(1 for _, speed in rows if speed > IMPLAUSIBLE_FT_PER_S)
    return bad, len(rows), bad / len(rows)


def concentration(records, tops=(5, 10, 20, 40)):
    """Share of implausible steps held by the top-N ids: 0.211 / 0.356 / 0.586 / 0.849."""
    per = defaultdict(int)
    for tid, speed in steps(records):
        if speed > IMPLAUSIBLE_FT_PER_S:
            per[tid] += 1
    total = sum(per.values())
    order = sorted(per.values(), reverse=True)
    return {n: sum(order[:n]) / total for n in tops}


def footpoint_player_split(records, located):
    """G273's box applied to G285b's coordinates: 0.705 in-box, and median 172.4 px among those."""
    inside, outside = [], 0
    for rec in records:
        pts = located.get(rec["source_frame"])
        if not pts:
            continue
        for det in rec.get("detections") or []:
            if not det.get("finite"):
                continue
            fx, fy = det["foot_x_px"], det["foot_y_px"]
            near = [
                (px, py)
                for px, py in pts
                if abs(px - fx) <= CROP_HALF_W and abs(py - fy) <= CROP_HALF_H
            ]
            if near:
                inside.append(min(math.hypot(px - fx, py - fy) for px, py in near))
            else:
                outside += 1
    total = len(inside) + outside
    return {
        "n": total,
        "in_box": len(inside),
        "in_box_fraction": len(inside) / total,
        "no_player_fraction": outside / total,
        "median_px_when_player_present": st.median(inside),
    }


def axis_null_check(records, located):
    """G290 verifier note: the acceptance box is 512 wide x 640 tall, so it is 1.25:1 TALL.

    Any offset distribution truncated by it is pushed toward vertical dominance before
    any defect exists. A uniform-in-box null already puts 0.6098 of squared offset on
    the vertical axis, so G290's 0.6487 must be read against 0.6098, NOT against 0.5.
    The square 512x512 sub-box removes the geometric preference -- but it also truncates
    exactly the large-|dy| tail that carries the signal, so it is CONSERVATIVE, not
    unbiased. Report both; neither alone settles it.
    """
    pairs = []
    for rec in records:
        pts = located.get(rec["source_frame"])
        if not pts:
            continue
        for det in rec.get("detections") or []:
            if not det.get("finite"):
                continue
            fx, fy = det["foot_x_px"], det["foot_y_px"]
            near = [
                (px, py)
                for px, py in pts
                if abs(px - fx) <= CROP_HALF_W and abs(py - fy) <= CROP_HALF_H
            ]
            if near:
                px, py = min(near, key=lambda q: math.hypot(q[0] - fx, q[1] - fy))
                pairs.append((fx - px, fy - py))

    def share(rows):
        sx = sum(dx * dx for dx, _ in rows)
        sy = sum(dy * dy for _, dy in rows)
        return sy / (sx + sy) if sx + sy else None  # no pairs: the nulls still stand

    half = min(CROP_HALF_W, CROP_HALF_H)
    square = [q for q in pairs if abs(q[0]) <= half and abs(q[1]) <= half]
    return {
        "n_full_box": len(pairs),
        "vertical_share_full_box": share(pairs),
        "uniform_in_box_null": CROP_HALF_H ** 2 / (CROP_HALF_W ** 2 + CROP_HALF_H ** 2),
        "n_square_sub_box": len(square),
        "vertical_share_square": share(square),
        "isotropic_null": 0.5,
        "downward_full_box": (sum(1 for _, dy in pairs if dy > 0), sum(1 for _, dy in pairs if dy)),
        "downward_square": (sum(1 for _, dy in square if dy > 0), sum(1 for _, dy in square if dy)),
    }


def overlay_bands(records):
    """Detection share by image row band.

    The two 90-px edge strips I first tested hold 0.001 each; the bands where a
    lower-third ticker and a score bug actually sit hold 0.318 and 0.036.
    """
    ys = [
        det["foot_y_px"]
        for rec in records
        for det in rec.get("detections") or []
        if det.get("finite")
    ]
    bands = {
        "top_strip_0_89": (0, 89),
        "score_bug_90_300": (90, 300),
        "lower_third_850_980": (850, 980),
        "bottom_strip_990_1079": (990, 1079),
    }
    return {k: sum(1 for y in ys if lo <= y <= hi) / len(ys) for k, (lo, hi) in bands.items()}


def _kmeans2(points, iterations=25):
    a = min(points, key=lambda p: p[0] + p[1])
    b = max(points, key=lambda p: p[0] + p[1])
    for _ in range(iterations):
        ca = [p for p in points if math.dist(p, a) <= math.dist(p, b)]
        cb = [p for p in points if math.dist(p, a) > math.dist(p, b)]
        if not ca or not cb:
            return None
        a = (sum(p[0] for p in ca) / len(ca), sum(p[1] for p in ca) / len(ca))
        b = (sum(p[0] for p in cb) / len(cb), sum(p[1] for p in cb) / len(cb))
    return a, b, ca, cb


def bimodal_tracks(records, min_obs=20, min_sep=200.0, max_spread=80.0, min_side=5):
    """Ids splitting into two tight far-apart clusters: 10 of 84 under these cuts.

    The cuts are chosen, not derived -- two-means always returns two clusters.
    """
    pos = defaultdict(list)
    for rec in records:
        for det in rec.get("detections") or []:
            if det.get("finite"):
                pos[det["track_id"]].append((det["foot_x_px"], det["foot_y_px"]))
    eligible, found = 0, set()
    for tid, pts in pos.items():
        if len(pts) < min_obs:
            continue
        eligible += 1
        split = _kmeans2(pts)
        if not split:
            continue
        a, b, ca, cb = split
        sa = st.pstdev([math.dist(p, a) for p in ca]) if len(ca) > 1 else 0.0
        sb = st.pstdev([math.dist(p, b) for p in cb]) if len(cb) > 1 else 0.0
        if math.dist(a, b) > min_sep and max(sa, sb) < max_spread and min(len(ca), len(cb)) >= min_side:
            found.add(tid)
    return found, eligible


def jump_return_rate(records, jump_px=150.0, back_px=100.0, window=5):
    """Large image jumps that come back: 262 / 2115 = 0.124. Constants are chosen."""
    seq = defaultdict(list)
    for rec in records:
        for det in rec.get("detections") or []:
            if det.get("finite"):
                seq[det["track_id"]].append(
                    (rec["source_frame"], det["foot_x_px"], det["foot_y_px"])
                )
    returned = total = 0
    for points in seq.values():
        points.sort()
        for i in range(1, len(points)):
            f0, x0, y0 = points[i - 1]
            f1, x1, y1 = points[i]
            if f1 <= f0 or math.hypot(x1 - x0, y1 - y0) < jump_px:
                continue
            total += 1
            for j in range(i + 1, len(points)):
                if points[j][0] - f1 > window:
                    break
                if math.hypot(points[j][1] - x0, points[j][2] - y0) < back_px:
                    returned += 1
                    break
    return returned, total, returned / total


def main() -> None:
    records = load_detections()
    bad, total, rate = implausible_rate(records)
    print(f"implausible steps        {bad}/{total} = {rate:.6f}")
    print(f"concentration            {concentration(records)}")
    print(f"overlay bands            {overlay_bands(records)}")
    found, eligible = bimodal_tracks(records)
    print(f"bimodal tracks           {len(found)} of {eligible}")
    ret, tot, frac = jump_return_rate(records)
    print(f"jumps returning          {ret}/{tot} = {frac:.3f}")
    if LOCATED.exists():
        print(f"footpoint/player split   {footpoint_player_split(records, load_located())}")


if __name__ == "__main__":
    main()
