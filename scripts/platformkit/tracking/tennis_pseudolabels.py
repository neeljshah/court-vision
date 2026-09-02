"""Emit drift-checked tennis court keypoint pseudo-labels from broadcast video."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable

import cv2
import numpy as np

from domains.tennis.tracking.adapter import TennisAdapter
from scripts.platformkit.calibration.keypoint_calib import CANONICAL_LANDMARKS

_COURT_CORNERS = np.float32(((0.0, 0.0), (0.0, 36.0), (78.0, 0.0), (78.0, 36.0)))
_ACCEPTED = {"solved": "fresh", "camera_lock_drift_checked": "reuse"}


def canonical_keypoints() -> dict[str, tuple[float, float]]:
    """Return the 14-point learner convention from the shared tennis template.

    The shared mapping currently exposes twelve entries, including two net-line
    crossings named as posts.  The 14-point training convention instead uses
    four service-line/singles-sideline intersections, so this leaves out those
    two crossings and derives the four missing intersections from the same
    surveyed court dimensions.
    """
    source = CANONICAL_LANDMARKS["tennis"]
    result = {name: point for name, point in source.items() if not name.startswith("net_post_")}
    result.update({"left_service_singles_bottom": (18.0, 4.5),
                   "left_service_singles_top": (18.0, 31.5),
                   "right_service_singles_bottom": (60.0, 4.5),
                   "right_service_singles_top": (60.0, 31.5)})
    return result


def load_pass_ranges(path: Path) -> list[dict[str, int | str]]:
    """Read only harness-PASS sequential frame ranges from a G18 plan JSON."""
    plan = json.loads(path.read_text(encoding="utf-8"))
    ranges = []
    for item in plan["ranges"]:
        if item.get("harness_verdict") != "PASS":
            continue
        source = item["source_frame_range"]
        start, stop = int(source["start"]), int(source["stop"])
        ranges.append({"id": "%d-%d" % (start, stop), "start": start, "stop": stop})
    return ranges


def select_holdout(labels: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Select deterministic endpoint-inclusive, evenly spaced label rows."""
    if count <= 0 or not labels:
        return []
    if count >= len(labels):
        return labels[:]
    if count == 1:
        return [labels[0]]
    return [labels[index * (len(labels) - 1) // (count - 1)] for index in range(count)]


def _finite(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _line_residual(adapter: Any, homography: np.ndarray, drift_px: float) -> float | None:
    corners = getattr(adapter, "_last_fresh_corners", None)
    if corners is None:
        return _finite(drift_px)
    inverse = np.linalg.inv(homography)
    projected = cv2.perspectiveTransform(_COURT_CORNERS.reshape(1, -1, 2), inverse)[0]
    observed = np.asarray(corners, dtype=np.float32).reshape(-1, 2)
    if len(observed) != len(projected):
        return _finite(drift_px)
    return float(np.median(np.linalg.norm(projected - observed, axis=1)))


def label_frame(adapter: Any, frame: np.ndarray, video: str, frame_index: int,
                range_id: str) -> dict[str, Any] | None:
    """Return one label row when the adapter accepts a drift-checked solve."""
    homography, provenance, _status, drift_px, evidence_count = adapter._calibrated_homography(frame)
    solve_type = _ACCEPTED.get(provenance)
    if homography is None or solve_type is None:
        return None
    height, width = frame.shape[:2]
    inverse = np.linalg.inv(np.asarray(homography, dtype=float))
    canonical = canonical_keypoints()
    names = list(canonical)
    court = np.float32([canonical[name] for name in names])
    pixels = cv2.perspectiveTransform(court.reshape(1, -1, 2), inverse)[0]
    keypoints = []
    for name, point in zip(names, pixels):
        x, y = float(point[0]), float(point[1])
        keypoints.append({"name": name, "x": x, "y": y,
                          "visible": bool(0.0 <= x < width and 0.0 <= y < height)})
    return {"video": video, "frame": int(frame_index), "width": int(width), "height": int(height),
            "keypoints": keypoints,
            "provenance": {"range_id": range_id, "solve_type": solve_type,
                           "drift_px": _finite(drift_px), "drift_evidence_count": int(evidence_count),
                           "line_reprojection_residual_px": _line_residual(adapter, homography, drift_px)}}


def generate(video: Path, ranges: Iterable[dict[str, int | str]], labels_path: Path,
             manifest_path: Path, adapter_factory: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Label every accepted frame in sequential ``ranges`` and write JSONL plus manifest."""
    adapter_factory = adapter_factory or (lambda: TennisAdapter(detector=lambda _frame: []))
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    range_counts: dict[str, int] = {}
    invisible = 0
    with labels_path.open("w", encoding="ascii", newline="\n") as output:
        for item in ranges:
            adapter = adapter_factory()
            range_id, start, stop = str(item["id"]), int(item["start"]), int(item["stop"])
            capture = cv2.VideoCapture(str(video))
            if not capture.isOpened():
                raise FileNotFoundError("Could not open video: %s" % video)
            capture.set(cv2.CAP_PROP_POS_FRAMES, start)
            accepted = 0
            try:
                for frame_index in range(start, stop + 1):
                    ok, frame = capture.read()
                    if not ok:
                        break
                    row = label_frame(adapter, frame, str(video), frame_index, range_id)
                    if row is None:
                        continue
                    output.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
                    accepted += 1
                    counts[row["provenance"]["solve_type"]] += 1
                    invisible += sum(not point["visible"] for point in row["keypoints"])
            finally:
                capture.release()
            range_counts[range_id] = accepted
    manifest = {"video": str(video), "ranges": range_counts, "labeled_frames": sum(range_counts.values()),
                "solve_type_counts": dict(counts), "invisible_keypoints": invisible,
                "canonical_keypoints_per_frame": len(canonical_keypoints())}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="ascii")
    return manifest


def render_holdout(label_paths: list[Path], count: int, output_dir: Path) -> list[Path]:
    """Draw the deterministic global holdout from JSONL labels without copying source frames."""
    labels = [json.loads(line) for path in label_paths for line in path.read_text(encoding="ascii").splitlines()]
    selected = select_holdout(labels, count)
    output_dir.mkdir(parents=True, exist_ok=True)
    renders = []
    for ordinal, row in enumerate(selected):
        capture = cv2.VideoCapture(row["video"])
        capture.set(cv2.CAP_PROP_POS_FRAMES, row["frame"])
        ok, image = capture.read()
        capture.release()
        if not ok:
            raise RuntimeError("Could not decode holdout frame %s:%d" % (row["video"], row["frame"]))
        for point in row["keypoints"]:
            if point["visible"]:
                cv2.circle(image, (round(point["x"]), round(point["y"])), 5, (0, 0, 255), -1)
                cv2.putText(image, point["name"], (round(point["x"]) + 6, round(point["y"]) - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1, cv2.LINE_AA)
        path = output_dir / ("%02d_f%06d.jpg" % (ordinal, row["frame"]))
        if not cv2.imwrite(str(path), image):
            raise RuntimeError("Could not write %s" % path)
        renders.append(path)
    return renders


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--ranges-json", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--holdout", type=int, default=0)
    parser.add_argument("--render-dir", type=Path)
    parser.add_argument("--holdout-from", type=Path, nargs="+")
    args = parser.parse_args()
    if args.holdout_from:
        if args.render_dir is None or args.holdout <= 0:
            parser.error("--holdout-from requires --holdout and --render-dir")
        render_holdout(args.holdout_from, args.holdout, args.render_dir)
        return
    if None in (args.video, args.ranges_json, args.labels, args.manifest):
        parser.error("generation requires --video --ranges-json --labels --manifest")
    generate(args.video, load_pass_ranges(args.ranges_json), args.labels, args.manifest)


if __name__ == "__main__":
    main()
