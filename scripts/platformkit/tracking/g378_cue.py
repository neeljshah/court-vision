"""The ONE sealed G378 cue: ANCHOR_SIDE_OCR, read through the DEPLOYED character route.

Every constant that belongs to the deployed route is IMPORTED from it and never restated:
the confidence floor and the top overlay fraction come from ``src.tracking.scoreboard_ocr``,
which is read only. ``RATIO_MARGIN`` comes from the landed G367 cue module. Missing evidence of
any kind emits UNKNOWN and is passed on, never quarantined (contract B3).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g367_cues import RATIO_MARGIN

BOTTOM_FRAC, MASS_FLOOR, MASK_VALUE = 0.82, 2000.0, 128
LEFT, RIGHT, UNKNOWN = "LEFT", "RIGHT", "UNKNOWN"
CUE_COLUMNS = ("frame_key,section,game,call,confidence,left_mass,right_mass,total_mass,"
               "n_detections,unknown_reason").split(",")
_ROUTE = {}


def constants() -> dict:
    """The deployed route's own two constants, imported and never restated. No reader is built."""
    if "conf_min" not in _ROUTE:
        from src.tracking import scoreboard_ocr
        _ROUTE["module"] = scoreboard_ocr
        _ROUTE["module_file"] = scoreboard_ocr.__file__
        _ROUTE["conf_min"] = float(scoreboard_ocr._OCR_CONF_MIN)
        _ROUTE["top_frac"] = float(scoreboard_ocr._TOP_FRAC)
    return _ROUTE


def route() -> dict:
    """The deployed reader factory. Built once, on first use, never edited."""
    if "reader" not in _ROUTE:
        module = constants()["module"]
        _ROUTE["reader"] = module._get_reader()
        _ROUTE["engine"] = "paddleocr" if getattr(module, "_sb_use_paddle", False) else "easyocr"
    return _ROUTE


def band_bounds(height: int) -> tuple:
    """The sealed anchor band: the deployed top overlay strip and the bottom apron removed."""
    return int(constants()["top_frac"] * height), int(BOTTOM_FRAC * height)


def _polygon_area(points) -> float:
    array = np.asarray(points, dtype=float).reshape(-1, 2)
    if array.shape[0] < 3 or not np.isfinite(array).all():
        return 0.0
    shift = np.roll(array, -1, axis=0)
    return float(abs(np.sum(array[:, 0] * shift[:, 1] - shift[:, 0] * array[:, 1])) / 2.0)


def _detections(frame: np.ndarray) -> list:
    """Raw kept detections as (centroid_x, weight); a reader failure yields an empty list."""
    top, bottom = band_bounds(frame.shape[0])
    band = frame[top:bottom, :]
    if band.size == 0:
        return []
    reader, conf_min = route()["reader"], constants()["conf_min"]
    try:
        if route()["engine"] == "paddleocr":
            raw = reader.ocr(band, cls=False)
            lines = (raw[0] or []) if raw else []
            results = [(line[0], line[1][0], float(line[1][1])) for line in lines if line]
        else:
            results = reader.readtext(band, detail=1, paragraph=False)
    except Exception:
        return []
    kept = []
    for box, _text, confidence in results:
        if float(confidence) < conf_min:
            continue
        area = _polygon_area(box)
        if area <= 0.0:
            continue
        centroid = float(np.asarray(box, dtype=float).reshape(-1, 2)[:, 0].mean())
        kept.append((centroid, area * float(confidence)))
    return kept


def call(frame) -> dict:
    """The sealed decision rule on ONE frame. Any missing evidence is UNKNOWN."""
    blank = {"call": UNKNOWN, "confidence": 0.0, "left_mass": 0.0, "right_mass": 0.0,
             "total_mass": 0.0, "n_detections": 0, "unknown_reason": ""}
    if frame is None or getattr(frame, "size", 0) == 0:
        return {**blank, "unknown_reason": "no_frame"}
    kept = _detections(frame)
    if not kept:
        return {**blank, "unknown_reason": "no_detection"}
    middle = frame.shape[1] / 2.0
    left = sum(weight for centroid, weight in kept if centroid < middle)
    right = sum(weight for centroid, weight in kept if centroid >= middle)
    total, high, low = left + right, max(left, right), min(left, right)
    out = {"call": UNKNOWN, "confidence": round(high / total, 6) if total else 0.0,
           "left_mass": round(left, 4), "right_mass": round(right, 4),
           "total_mass": round(total, 4), "n_detections": len(kept), "unknown_reason": ""}
    if total < MASS_FLOOR:
        return {**out, "unknown_reason": "mass_below_floor"}
    if high / max(low, 1e-9) < RATIO_MARGIN:
        return {**out, "unknown_reason": "ratio_below_margin"}
    return {**out, "call": LEFT if left > right else RIGHT}


def mirrored(frame):
    return cv2.flip(frame, 1)


def masked(frame):
    """The cue's OWN evidence band overwritten with a constant, so no evidence remains."""
    out = frame.copy()
    top, bottom = band_bounds(out.shape[0])
    out[top:bottom, :] = MASK_VALUE
    return out


def _frames(path: Path) -> list:
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def run(frames: Path, cache: Path, out: Path, summary: Path) -> int:
    """The sealed cue over EVERY decoded frame; nothing is dropped from the denominator."""
    rows = []
    for item in _frames(frames):
        frame = cv2.imread(str(cache / item["cache"]), cv2.IMREAD_COLOR)
        result = call(frame)
        if frame is None:
            result["unknown_reason"] = "cache_unreadable"
        rows.append({"frame_key": item["frame_key"], "section": item["section"],
                     "game": item["game"], **result})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=CUE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    counts = {name: sum(row["call"] == name for row in rows) for name in (LEFT, RIGHT, UNKNOWN)}
    payload = json.loads(summary.read_text(encoding="ascii")) if summary.exists() else {"row": "G378"}
    payload["cue"] = {"name": "ANCHOR_SIDE_OCR", "engine": route()["engine"],
                      "route_file": constants()["module_file"],
                      "conf_min": constants()["conf_min"], "top_frac": constants()["top_frac"],
                      "bottom_frac": BOTTOM_FRAC, "mass_floor": MASS_FLOOR,
                      "ratio_margin": RATIO_MARGIN, "n_frames": len(rows), "calls": counts,
                      "resolved_over_decoded": round((counts[LEFT] + counts[RIGHT]) / len(rows), 6) if rows else None,
                      "unknown_share": round(counts[UNKNOWN] / len(rows), 6) if rows else None}
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("CUE frames=%d left=%d right=%d unknown=%d engine=%s"
          % (len(rows), counts[LEFT], counts[RIGHT], counts[UNKNOWN], route()["engine"]))
    return 0


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frames", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args(argv[1:])
    return run(Path(args.frames), Path(args.cache), Path(args.out), Path(args.summary))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
