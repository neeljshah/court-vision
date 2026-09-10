"""Sealed G367 orientation cues and rating-only calibration summary."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

RATIO_MARGIN, PAN_MIN = 1.15, 1.5
CUES = ("basket_side", "graphic_side", "crowd_side", "pan_direction")


def _side(left: float, right: float, invert: bool = False) -> str:
    if max(left, right) < 1e-9 or max(left, right) / max(min(left, right), 1e-9) < RATIO_MARGIN:
        return "unknown"
    value = "left" if left > right else "right"
    return {"left": "right", "right": "left"}[value] if invert else value


def basket_side(frame: np.ndarray) -> str:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, w = frame.shape[:2]
    mask = (hsv[:int(h * .55), :, 1] < 55) & (hsv[:int(h * .55), :, 2] > 185)
    return _side(float(mask[:, :w // 3].sum()), float(mask[:, 2 * w // 3:].sum()))


def graphic_side(frame: np.ndarray) -> str:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, w = frame.shape[:2]
    band = hsv[int(h * .78):]
    mask = (band[:, :, 1] < 45) & ((band[:, :, 2] < 55) | (band[:, :, 2] > 205))
    return _side(float(mask[:, :w // 2].sum()), float(mask[:, w // 2:].sum()), invert=True)


def crowd_side(frame: np.ndarray) -> str:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, w = frame.shape[:2]
    floor_hue = int(np.bincount(hsv[h // 2:, :, 0].ravel(), minlength=180).argmax())
    gap = np.abs(hsv[:, :, 0].astype(int) - floor_hue)
    gap = np.minimum(gap, 180 - gap)
    mask = (gap > 15) | (hsv[:, :, 1] < 40)
    return _side(float(mask[:, :w // 3].sum()), float(mask[:, 2 * w // 3:].sum()))


def pan_direction(previous: np.ndarray, frame: np.ndarray) -> str:
    a = cv2.resize(cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY), (128, 72)).astype(np.float32)
    b = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (128, 72)).astype(np.float32)
    shift, _response = cv2.phaseCorrelate(a, b)
    if shift[0] <= -PAN_MIN:
        return "right"
    if shift[0] >= PAN_MIN:
        return "left"
    return "unknown"


def calls(previous: np.ndarray, frame: np.ndarray) -> dict:
    """The four deterministic calls, independent of ratings and one another."""
    return {"basket_side": basket_side(frame), "graphic_side": graphic_side(frame),
            "crowd_side": crowd_side(frame), "pan_direction": pan_direction(previous, frame)}


def _ratings(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result = {}
    for row in rows:
        key, rater, label = row.get("frame_key", ""), row.get("rater", ""), row.get("label", "")
        if key and rater in ("terra", "sol", "ADJUDICATOR") and label in ("left", "right", "unknown"):
            result.setdefault(key, {})[rater] = label
    return result


def _reference(labels: dict[str, str]) -> str:
    first, second = labels.get("terra"), labels.get("sol")
    if first and first == second:
        return first
    return labels.get("ADJUDICATOR", "")


def _wilson(correct: int, total: int) -> list[float | None]:
    if not total:
        return [None, None]
    z, p = 1.959963984540054, correct / total
    denom = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [center - radius, center + radius]


def _kappa(labels: dict[str, dict[str, str]]) -> float | None:
    pairs = [(row["terra"], row["sol"]) for row in labels.values()
             if "terra" in row and "sol" in row]
    if not pairs:
        return None
    values = ("left", "right", "unknown")
    observed = sum(first == second for first, second in pairs) / len(pairs)
    expected = sum((sum(first == value for first, _ in pairs) / len(pairs)) *
                   (sum(second == value for _, second in pairs) / len(pairs)) for value in values)
    return None if abs(1 - expected) < 1e-12 else (observed - expected) / (1 - expected)


def score(ratings: Path, manifest: Path, cache: Path, cues_out: Path, summary: Path) -> int:
    """Join blind adjudication to frame-only cue calls and write the per-frame series."""
    labels = _ratings(ratings)
    with manifest.open(newline="", encoding="ascii") as handle:
        frames = list(csv.DictReader(handle))
    rows, totals = [], {name: {"correct": 0, "predicted": 0} for name in CUES}
    references = {"left": 0, "right": 0, "unknown": 0, "unadjudicated_frames": 0}
    for item in frames:
        key, row_labels = item["frame_key"], labels.get(item["frame_key"], {})
        reference = _reference(row_labels)
        if not reference:
            references["unadjudicated_frames"] += 1
        else:
            references[reference] += 1
        frame = cv2.imread(str(cache / item["cache"]), cv2.IMREAD_COLOR)
        previous = cv2.imread(str(cache / item["prev1_cache"]), cv2.IMREAD_COLOR)
        if frame is None or previous is None:
            raise ValueError("missing cached frame for %s" % key)
        result = calls(previous, frame)
        for name, value in result.items():
            if reference in ("left", "right") and value in ("left", "right"):
                totals[name]["predicted"] += 1
                totals[name]["correct"] += int(value == reference)
        rows.append({"frame_key": key, "reference": reference or "UNADJUDICATED",
                     "terra": row_labels.get("terra", ""), "sol": row_labels.get("sol", ""),
                     "adjudicator": row_labels.get("ADJUDICATOR", ""), **result})
    cues_out.parent.mkdir(parents=True, exist_ok=True)
    with cues_out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=("frame_key,reference,terra,sol,adjudicator," + ",".join(CUES)).split(","))
        writer.writeheader(); writer.writerows(rows)
    labelled = references["left"] + references["right"]
    report = {name: {"correct": item["correct"], "predicted": item["predicted"],
                     "precision": (item["correct"] / item["predicted"] if item["predicted"] else None),
                     "wilson_95": _wilson(item["correct"], item["predicted"]),
                     "abstention": (1 - item["predicted"] / labelled if labelled else None)}
              for name, item in totals.items()}
    payload = json.loads(summary.read_text(encoding="ascii")) if summary.exists() else {}
    payload["orientation"] = {"n_frames": len(rows), "n_labelled": labelled, **references,
                              "kappa": _kappa(labels), "cues": report}
    summary.write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("ORIENTATION labelled=%d frames=%d" % (labelled, len(rows)))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    item = sub.add_parser("score")
    for name in ("ratings", "manifest", "cache", "cues-out", "summary"):
        item.add_argument("--" + name, required=True)
    args = parser.parse_args(argv[1:])
    return score(Path(args.ratings), Path(args.manifest), Path(args.cache), Path(args.cues_out), Path(args.summary))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
