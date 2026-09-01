"""Independent evaluator for tennis image-to-court homography traces.

Input is JSONL: frame, image_to_court (3x3), observed ({landmark:[x,y]}), and
solve_landmarks.  A landmark in solve_landmarks is never used for ft/scale gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np

COURT = {"doubles_bl": (0., 0.), "doubles_br": (78., 0.), "doubles_tr": (78., 36.),
         "doubles_tl": (0., 36.), "singles_bl": (0., 4.5), "singles_br": (78., 4.5),
         "singles_tr": (78., 31.5), "singles_tl": (0., 31.5),
         "net_post_bottom": (39., 0.), "net_post_top": (39., 36.),
         "left_service_t": (18., 18.), "right_service_t": (60., 18.)}
SCALE = {"length_ft": (78., (("doubles_bl", "doubles_br"), ("doubles_tl", "doubles_tr"),
                              ("singles_bl", "singles_br"), ("singles_tl", "singles_tr"))),
         "singles_width_ft": (27., (("singles_bl", "singles_tl"), ("singles_br", "singles_tr"))),
         "doubles_width_ft": (36., (("doubles_bl", "doubles_tl"), ("doubles_br", "doubles_tr")))}


def _project(h: np.ndarray, points: Iterable[tuple[float, float]]) -> np.ndarray:
    """Project 2-D points through a homography."""
    xy = np.asarray(list(points), dtype=float).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(xy.astype(np.float32), h.astype(np.float64)).reshape(-1, 2)


def _matrix(row: dict[str, Any]) -> np.ndarray | None:
    raw = row.get("image_to_court", row.get("homography"))
    h = np.asarray(raw, dtype=float) if raw is not None else np.empty((0,))
    if h.shape != (3, 3) or not np.isfinite(h).all() or abs(h[2, 2]) < 1e-12:
        return None
    return h / h[2, 2]


def _band(point: tuple[float, float]) -> str:
    return ("near", "mid", "far")[min(2, int(point[0] / 26.0))]


def evaluate_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Score pixel convention, held-out depth error, and independent court scale."""
    pixel_errors: list[float] = []
    held_out = {name: [] for name in ("near", "mid", "far")}
    scale_errors = {name: [] for name in SCALE}
    valid = 0
    for row in records:
        h = _matrix(row)
        observed = row.get("observed", {})
        if h is None or not isinstance(observed, dict):
            continue
        try:
            inverse = np.linalg.inv(h)
        except np.linalg.LinAlgError:
            continue
        valid += 1
        solved = set(row.get("solve_landmarks", []))
        usable = [(name, tuple(value)) for name, value in observed.items()
                  if name in COURT and isinstance(value, (list, tuple)) and len(value) == 2]
        if usable:
            names, pixels = zip(*usable)
            predicted = _project(inverse, (COURT[name] for name in names))
            pixel_errors.extend(np.linalg.norm(predicted - np.asarray(pixels, dtype=float), axis=1).tolist())
        projected = {name: _project(h, [tuple(value)])[0] for name, value in usable}
        for name, point in projected.items():
            if name not in solved:
                held_out[_band(COURT[name])].append(float(np.linalg.norm(point - COURT[name])))
        for label, (expected, pairs) in SCALE.items():
            for first, second in pairs:
                if first in projected and second in projected and first not in solved and second not in solved:
                    measured = float(np.linalg.norm(projected[first] - projected[second]))
                    scale_errors[label].append(100.0 * (measured / expected - 1.0))
    bands = {name: {"n": len(values), "median_ft": None if not values else round(float(np.median(values)), 4),
                    "p95_ft": None if not values else round(float(np.percentile(values, 95)), 4)}
             for name, values in held_out.items()}
    scale = {}
    for name, values in scale_errors.items():
        scale[name] = {"n": len(values), "median_pct_error": None if not values else round(float(np.median(values)), 4),
                       "max_abs_pct_error": None if not values else round(float(np.max(np.abs(values))), 4),
                       "pass": bool(values) and max(abs(value) for value in values) <= 3.0}
    return {"frames_valid": valid,
            "pixel_convention": {"n": len(pixel_errors), "median_px": None if not pixel_errors else round(float(np.median(pixel_errors)), 4),
                                 "pck_at_7px": None if not pixel_errors else round(float(np.mean(np.asarray(pixel_errors) <= 7.0)), 6)},
            "depth_band_ft_error": bands, "independent_scale": scale,
            "scale_pass": all(item["pass"] for item in scale.values())}


def _court_segments() -> list[tuple[tuple[float, float], tuple[float, float]]]:
    rectangles = ((0., 0., 78., 36.), (0., 4.5, 78., 31.5))
    output = []
    for x0, y0, x1, y1 in rectangles:
        output.extend([((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))])
    output.extend([((39., 0.), (39., 36.)), ((18., 4.5), (18., 31.5)), ((60., 4.5), (60., 31.5))])
    return output


def render_overlays(records: Iterable[dict[str, Any]], video: Path, directory: Path, count: int = 10) -> list[str]:
    """Render solved court lines and observed landmarks for independent visual review."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError("cannot open video: %s" % video)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    try:
        for row in records:
            if len(written) >= count:
                break
            h = _matrix(row)
            if h is None or "frame" not in row:
                continue
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(row["frame"]))
            ok, image = capture.read()
            if not ok:
                continue
            inv = np.linalg.inv(h)
            for first, second in _court_segments():
                points = _project(inv, [first, second]).astype(int)
                cv2.line(image, tuple(points[0]), tuple(points[1]), (0, 255, 0), 2)
            for name, value in row.get("observed", {}).items():
                if name in COURT and len(value) == 2:
                    cv2.circle(image, tuple(np.asarray(value, dtype=int)), 5, (0, 0, 255), -1)
            path = directory / ("tennis_calib_overlay_%03d.jpg" % len(written))
            if cv2.imwrite(str(path), image):
                written.append(str(path))
    finally:
        capture.release()
    return written


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="provider-neutral JSONL trace")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--overlay-dir", type=Path, default=Path("docs/evidence/tracking"))
    parser.add_argument("--min-overlays", type=int, default=10)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.min_overlays < 10:
        parser.error("--min-overlays must be at least 10")
    records = _read_jsonl(args.input)
    report = evaluate_records(records)
    overlays = render_overlays(records, args.video, args.overlay_dir, args.min_overlays)
    report["render_and_look"] = {"required": args.min_overlays, "written": len(overlays), "paths": overlays,
                                  "pass": len(overlays) >= args.min_overlays}
    report["verdict"] = "PASS" if report["scale_pass"] and report["render_and_look"]["pass"] else "REJECT"
    report["reject_reason"] = None if report["verdict"] == "PASS" else "scale_or_overlay_gate_failed"
    text = json.dumps(report, sort_keys=True, allow_nan=False)
    if args.report:
        args.report.write_text(text + "\n", encoding="ascii")
    print(text)
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
