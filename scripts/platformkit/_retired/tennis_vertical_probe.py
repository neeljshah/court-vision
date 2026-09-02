# RETIRED: Replaced by scripts.platformkit.tennis_camera_lock_measure on the current court_lines and camera_lock path.
"""Where do tennis far-court VERTICAL lines go? Raw-segment premise probe.

For every sampled frame this records, side by side, what the production
brightness-mask HoughLinesP path yields (the gate the frame actually faces),
what the same mask yields with the length filter relaxed, and what a raw LSD
pass over the grayscale frame yields with NO filter at all. Each vertical LSD
segment is also tagged bright/dark by sampling the production mask along it,
so "the mask never saw the line" is separable from "Hough fragmented it".

Run:
  python -m scripts.platformkit.tracking.tennis_vertical_probe VIDEO OUT_DIR \
      --section live1 7200 7350 5 --section dead1 15200 15350 5 [--overlay N]
"""
from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np

from domains.tennis.tracking.adapter import CROSS_RATIO, TennisAdapter
from domains.tennis.tracking.court_diagnostics import rejection_gate

BRIGHT_LO, BRIGHT_HI = np.array((200, 200, 200)), np.array((255, 255, 255))


def _classify(seg: np.ndarray) -> str:
    dx, dy = abs(float(seg[2] - seg[0])), abs(float(seg[3] - seg[1]))
    return "h" if dx >= 1.5 * dy else "v" if dy > dx else "u"


def _length(seg: np.ndarray) -> float:
    return float(np.hypot(seg[2] - seg[0], seg[3] - seg[1]))


def _hough(mask: np.ndarray, threshold: int, min_len: int) -> list[np.ndarray]:
    found = cv2.HoughLinesP(mask, 1, np.pi / 180.0, threshold, minLineLength=min_len, maxLineGap=20)
    return [] if found is None else [seg.astype(float) for seg in found.reshape(-1, found.shape[-1])]


def _lsd(gray: np.ndarray) -> list[np.ndarray]:
    found = cv2.createLineSegmentDetector().detect(gray)[0]
    return [] if found is None else [seg.astype(float) for seg in found[:, 0, :]]


def _mask_fraction(mask: np.ndarray, seg: np.ndarray) -> float:
    """Share of samples along the segment (+-1 px) that are bright in the mask."""
    n = max(2, int(_length(seg)))
    xs = np.linspace(seg[0], seg[2], n); ys = np.linspace(seg[1], seg[3], n)
    hit = 0
    for x, y in zip(xs, ys):
        xi, yi = int(round(x)), int(round(y))
        y0, y1 = max(0, yi - 1), min(mask.shape[0], yi + 2)
        x0, x1 = max(0, xi - 1), min(mask.shape[1], xi + 2)
        hit += int(mask[y0:y1, x0:x1].any())
    return hit / n


def _cross_ratio(across: list[float]) -> float:
    denominator = (across[2] - across[1]) * (across[4] - across[0])
    return float("inf") if abs(denominator) < 1e-6 else (across[2] - across[0]) * (across[4] - across[1]) / denominator


def cluster_census(prod: list[np.ndarray], shape: tuple[int, int]) -> dict[str, object]:
    """Production clustering counts plus: does ANY 5-subset of vertical clusters fit the cross ratio?"""
    horizontal = [s for s in prod if _classify(s) == "h"]
    vertical = [s for s in prod if _classify(s) == "v"]
    h_clusters = TennisAdapter._cluster_lines(horizontal, True, shape) if horizontal else []
    v_clusters = TennisAdapter._cluster_lines(vertical, False, shape) if vertical else []
    across = [TennisAdapter._line_position(TennisAdapter._fit_line(c), False, shape) for c in v_clusters]
    subset_ok = 0
    if 5 <= len(across) <= 14:
        subset_ok = sum(abs(_cross_ratio(list(combo)) - CROSS_RATIO) <= 0.05 for combo in combinations(sorted(across), 5))
    return {"h_clusters": len(h_clusters), "v_clusters": len(v_clusters), "v5_subsets_in_cross_ratio": subset_ok}


def probe_frame(frame: np.ndarray) -> dict[str, object]:
    """Raw detector census for one frame: production, relaxed Hough, raw LSD."""
    height, width = frame.shape[:2]
    prod_min = max(40, width // 12)
    mask = cv2.inRange(frame, BRIGHT_LO, BRIGHT_HI)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    prod = _hough(mask, 45, prod_min)
    clusters = cluster_census(prod, (height, width))
    relaxed = _hough(mask, 20, 30)
    lsd = _lsd(gray)
    lsd_v = [s for s in lsd if _classify(s) == "v"]
    lsd_v_long = [s for s in lsd_v if _length(s) >= prod_min]
    lsd_v_mid = [s for s in lsd_v if 40 <= _length(s) < prod_min]
    bright_long = [s for s in lsd_v_long if _mask_fraction(mask, s) >= 0.5]
    return {
        "gate": rejection_gate(frame), **clusters,
        "prod_h": sum(_classify(s) == "h" for s in prod),
        "prod_v": sum(_classify(s) == "v" for s in prod),
        "relaxed_v": sum(_classify(s) == "v" for s in relaxed),
        "relaxed_v_len_max": max((_length(s) for s in relaxed if _classify(s) == "v"), default=0.0),
        "lsd_total": len(lsd),
        "lsd_v_all": len(lsd_v),
        "lsd_v_ge_prodmin": len(lsd_v_long),
        "lsd_v_40_to_prodmin": len(lsd_v_mid),
        "lsd_v_ge_prodmin_bright": len(bright_long),
        "lsd_v_ge_prodmin_dark": len(lsd_v_long) - len(bright_long),
        "lsd_v_ge_prodmin_upper_half": sum((s[1] + s[3]) / 2.0 < height / 2.0 for s in lsd_v_long),
        "mask_bright_px": int((mask > 0).sum()),
        "_prod": prod, "_lsd_v_long": lsd_v_long, "_lsd_v_mid": lsd_v_mid, "_mask": mask,
    }


def overlay(frame: np.ndarray, census: dict[str, object], label: str) -> np.ndarray:
    """Production Hough (green h / red v) plus raw LSD verticals (cyan long, yellow mid)."""
    image = frame.copy()
    for seg in census["_lsd_v_mid"]:
        cv2.line(image, (int(seg[0]), int(seg[1])), (int(seg[2]), int(seg[3])), (0, 255, 255), 1)
    for seg in census["_lsd_v_long"]:
        cv2.line(image, (int(seg[0]), int(seg[1])), (int(seg[2]), int(seg[3])), (255, 255, 0), 2)
    for seg in census["_prod"]:
        colour = (0, 255, 0) if _classify(seg) == "h" else (0, 0, 255)
        cv2.line(image, (int(seg[0]), int(seg[1])), (int(seg[2]), int(seg[3])), colour, 2)
    text = "%s gate=%s H=%d V=%d hcl=%d vcl=%d v5ok=%d lsdV>=min=%d (bright %d dark %d)" % (
        label, census["gate"], census["prod_h"], census["prod_v"], census["h_clusters"], census["v_clusters"],
        census["v5_subsets_in_cross_ratio"], census["lsd_v_ge_prodmin"],
        census["lsd_v_ge_prodmin_bright"], census["lsd_v_ge_prodmin_dark"])
    cv2.rectangle(image, (0, 0), (image.shape[1], 26), (0, 0, 0), -1)
    cv2.putText(image, text, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    return image


def _median(rows: list[dict[str, object]], key: str) -> float:
    return float(np.median([row[key] for row in rows])) if rows else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--section", nargs=4, action="append", metavar=("NAME", "START", "STOP", "STEP"), required=True)
    parser.add_argument("--overlay", type=int, default=2, help="overlays written per section (first N frames)")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise FileNotFoundError(args.video)
    keys = ("h_clusters", "v_clusters", "v5_subsets_in_cross_ratio", "prod_h", "prod_v", "relaxed_v", "relaxed_v_len_max", "lsd_v_all", "lsd_v_ge_prodmin",
            "lsd_v_40_to_prodmin", "lsd_v_ge_prodmin_bright", "lsd_v_ge_prodmin_dark",
            "lsd_v_ge_prodmin_upper_half", "mask_bright_px")
    report: dict[str, object] = {"video": str(args.video), "sections": {}}
    for name, start, stop, step in args.section:
        rows: list[dict[str, object]] = []
        written = 0
        tiles: list[np.ndarray] = []
        for source_frame in range(int(start), int(stop) + 1, int(step)):
            capture.set(cv2.CAP_PROP_POS_FRAMES, source_frame)
            ok, frame = capture.read()
            if not ok:
                continue
            census = probe_frame(frame)
            tile = cv2.resize(frame, (160, 90))
            cv2.putText(tile, "%d %s" % (source_frame, census["gate"][:8]), (2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                        (0, 255, 0) if census["gate"] == "accepted" else (0, 0, 255), 1)
            tiles.append(tile)
            if written < args.overlay or (census["gate"] == "accepted" and written < args.overlay + 1):
                cv2.imwrite(str(args.out_dir / ("%s_f%06d.png" % (name, source_frame))),
                            overlay(frame, census, "%s f%d" % (name, source_frame)))
                written += 1
            row = {k: v for k, v in census.items() if not k.startswith("_")}
            row["frame"] = source_frame
            rows.append(row)
        while len(tiles) % 8:
            tiles.append(np.zeros((90, 160, 3), dtype=np.uint8))
        cv2.imwrite(str(args.out_dir / ("%s_sheet.png" % name)),
                    np.vstack([np.hstack(tiles[i:i + 8]) for i in range(0, len(tiles), 8)]))
        gates: dict[str, int] = {}
        for row in rows:
            gates[row["gate"]] = gates.get(row["gate"], 0) + 1
        report["sections"][name] = {
            "plan": [int(start), int(stop), int(step)], "n_frames": len(rows), "gates": gates,
            "median": {k: _median(rows, k) for k in keys},
            "frames_prod_v_lt2": sum(row["prod_v"] < 2 for row in rows),
            "frames_prod_v_lt2_but_lsd_v_ge_prodmin_ge2": sum(
                row["prod_v"] < 2 and row["lsd_v_ge_prodmin"] >= 2 for row in rows),
            "frames_prod_v_lt2_but_lsd_v_ge_prodmin_bright_ge2": sum(
                row["prod_v"] < 2 and row["lsd_v_ge_prodmin_bright"] >= 2 for row in rows),
            "frames_v_clusters_ne5": sum(row["v_clusters"] != 5 for row in rows),
            "frames_v_clusters_gt5_with_subset": sum(row["v_clusters"] > 5 and row["v5_subsets_in_cross_ratio"] > 0 for row in rows),
            "frames_v_clusters_lt5": sum(row["v_clusters"] < 5 for row in rows),
            "frames_h_clusters_lt4": sum(row["h_clusters"] < 4 for row in rows),
            "rows": rows,
        }
        sec = report["sections"][name]
        summary = {k: sec["median"][k] for k in ("prod_h", "prod_v", "h_clusters", "v_clusters", "lsd_v_ge_prodmin")}
        summary.update({k: sec[k] for k in ("frames_v_clusters_ne5", "frames_v_clusters_gt5_with_subset",
                                            "frames_v_clusters_lt5", "frames_h_clusters_lt4")})
        print(name, "n=%d" % len(rows), json.dumps(gates, sort_keys=True), json.dumps(summary, sort_keys=True))
    capture.release()
    (args.out_dir / "vertical_probe.json").write_text(json.dumps(report, indent=1, default=lambda o: o.item()) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
