"""Measure G253 withheld court geometry using G252's fixed edge-offset method."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking import g252_projection_accuracy_in_pixels as g252


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = ROOT / "docs/evidence/tracking/g253_line_and_conic_calibration_2026-09-04_artifact"
OUTPUT = ROOT / "docs/evidence/tracking/g255_amateur_gate_independent_check_2026-09-04_artifact"


def _arc(baseline: float, direction: float, radius: float) -> np.ndarray:
    basket = baseline + direction * 4.0
    angle = np.linspace(0.0, np.pi, 121)
    points = np.column_stack((25.0 + radius * np.cos(angle), basket + direction * radius * np.sin(angle)))
    return points.astype(np.float32)


def withheld_geometry() -> dict[str, list[np.ndarray]]:
    """Return only the geometry excluded from each G253 fit."""
    control_arc = _arc(0.0, 1.0, 22.0 + 1.75 / 12.0)
    amateur_arc = _arc(0.0, 1.0, 19.75)
    return {
        "control_arc": [control_arc, np.float32(((control_arc[0, 0], 0.0), control_arc[0])),
                        np.float32(((control_arc[-1, 0], 0.0), control_arc[-1]))],
        "control_sideline": [np.float32(((0.0, 0.0), (0.0, 94.0))), np.float32(((50.0, 0.0), (50.0, 94.0)))],
        "amateur_arc": [amateur_arc, np.float32(((amateur_arc[0, 0], 0.0), amateur_arc[0])),
                         np.float32(((amateur_arc[-1, 0], 0.0), amateur_arc[-1]))],
        "amateur_paint": [np.float32(((0.0, 0.0), (50.0, 0.0))), np.float32(((19.0, 0.0), (19.0, 19.0))),
                           np.float32(((31.0, 0.0), (31.0, 19.0))), np.float32(((19.0, 19.0), (31.0, 19.0)))],
    }


def _clip(first: np.ndarray, last: np.ndarray, width: int, height: int) -> tuple[np.ndarray, np.ndarray] | None:
    delta, low, high = last - first, 0.0, 1.0
    for numerator, value in ((-delta[0], first[0]), (delta[0], width - 1 - first[0]),
                             (-delta[1], first[1]), (delta[1], height - 1 - first[1])):
        if abs(numerator) < 1e-12:
            if value < 0:
                return None
        elif numerator < 0:
            low = max(low, value / numerator)
        else:
            high = min(high, value / numerator)
    return None if low > high else (first + low * delta, first + high * delta)


def _edge_distances(edges: np.ndarray, points: np.ndarray, normals: np.ndarray) -> np.ndarray:
    radii = np.arange(-g252.SEARCH_RADIUS_PX, g252.SEARCH_RADIUS_PX + 1, dtype=np.float64)
    found = np.full(len(points), np.nan, dtype=np.float64)
    for start in range(0, len(points), 12000):
        end = min(len(points), start + 12000)
        coords = points[start:end, None, :] + radii[None, :, None] * normals[start:end, None, :]
        xs, ys = np.rint(coords[:, :, 0]).astype(np.int32), np.rint(coords[:, :, 1]).astype(np.int32)
        keep = (xs >= 0) & (xs < edges.shape[1]) & (ys >= 0) & (ys < edges.shape[0])
        hit = np.zeros(keep.shape, dtype=bool)
        hit[keep] = edges[ys[keep], xs[keep]] > 0
        any_hit = hit.any(axis=1)
        if any_hit.any():
            nearest = np.where(hit, np.abs(radii)[None, :], np.inf).min(axis=1)
            found[start:end][any_hit] = nearest[any_hit]
    return found


def _measure_curve(edges: np.ndarray, curve: np.ndarray) -> tuple[int, list[float]]:
    """Apply G252's unchanged projected-segment normal search to one curve."""
    height, width = edges.shape
    point_parts: list[np.ndarray] = []
    normal_parts: list[np.ndarray] = []
    for first, last in zip(curve[:-1], curve[1:]):
        delta = last - first
        length = float(np.linalg.norm(delta))
        if not np.isfinite(length) or length <= 1e-6:
            continue
        clipped = _clip(first, last, width, height)
        if clipped is None:
            continue
        start, end = clipped
        clipped_length = float(np.linalg.norm(end - start))
        if clipped_length <= 1e-6:
            continue
        count = max(1, int(math.ceil(clipped_length / g252.SAMPLE_SPACING_PX)))
        fraction = (np.arange(count, dtype=np.float64) + 0.5) / count
        point_parts.append(start + fraction[:, None] * (end - start))
        tangent = delta / length
        normal_parts.append(np.repeat(np.array([[-tangent[1], tangent[0]]]), count, axis=0))
    if not point_parts:
        return 0, []
    distances = _edge_distances(edges, np.concatenate(point_parts), np.concatenate(normal_parts))
    return int(len(distances)), [float(value) for value in distances[np.isfinite(distances)]]


def measure(image_path: Path, image_to_court: np.ndarray, groups: dict[str, list[np.ndarray]]) -> dict[str, object]:
    """Measure all named withheld groups on one fixed frame."""
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, g252.CANNY_LOW, g252.CANNY_HIGH, apertureSize=3, L2gradient=True)
    inverse = np.linalg.inv(image_to_court)
    result: dict[str, object] = {}
    for name, curves in groups.items():
        samples, distances = 0, []
        for raw in curves:
            projected = cv2.perspectiveTransform(raw.reshape(1, -1, 2), inverse)[0]
            count, found = _measure_curve(edges, projected)
            samples += count
            distances.extend(found)
        result[name] = {"sample_points": samples, "found": len(distances), "no_candidate": samples - len(distances),
                        "distances_px": distances}
    return result


def _summary(item: dict[str, object]) -> dict[str, float | int | None]:
    values = sorted(float(value) for value in item["distances_px"])
    if not values:
        return {"sample_points": int(item["sample_points"]), "found": 0, "no_candidate": int(item["no_candidate"]),
                "median_px": None, "p90_px": None, "max_px": None}
    return {"sample_points": int(item["sample_points"]), "found": len(values), "no_candidate": int(item["no_candidate"]),
            "median_px": float(statistics.median(values)), "p90_px": float(np.quantile(values, 0.9)), "max_px": values[-1]}


def run(output: Path = OUTPUT) -> dict[str, object]:
    """Measure G253's persisted maps without refitting or modifying their inputs."""
    amateur_meta = json.loads((ARTIFACT / "amateur_fit_measurement.json").read_text(encoding="ascii"))
    control_meta = json.loads((ARTIFACT / "control_measurement.json").read_text(encoding="ascii"))
    geometry = withheld_geometry()
    records = {
        "amateur_line_plus_conic": measure(ARTIFACT / "amateur_frame_0540.jpg", np.asarray(amateur_meta["homography_image_to_court"]),
                                            {"arc": geometry["amateur_arc"], "painted_end": geometry["amateur_paint"]}),
        "wnba_lines_only_control": measure(ARTIFACT / "control_seed_frame_19599.jpg", np.asarray(control_meta["line_fit_homography_image_to_court"]),
                                             {"arc": geometry["control_arc"], "sideline": geometry["control_sideline"]}),
    }
    for record in records.values():
        pooled = {"sample_points": sum(int(item["sample_points"]) for item in record.values()),
                  "no_candidate": sum(int(item["no_candidate"]) for item in record.values()),
                  "distances_px": [value for item in record.values() for value in item["distances_px"]]}
        pooled["found"] = len(pooled["distances_px"])
        record["pooled"] = pooled
    report = {"method": {"reused_from": "scripts/platformkit/tracking/g252_projection_accuracy_in_pixels.py",
                           "g252_route_sha256": hashlib.sha256((ROOT / "scripts/platformkit/tracking/g252_projection_accuracy_in_pixels.py").read_bytes()).hexdigest(),
                           "candidate": "Canny strong edge along projected-line local normal", "canny": {"low": g252.CANNY_LOW, "high": g252.CANNY_HIGH, "aperture_size": 3, "L2gradient": True},
                           "sample_spacing_px": g252.SAMPLE_SPACING_PX, "search_radius_px": g252.SEARCH_RADIUS_PX,
                           "censoring": "No candidate is retained and counted. Found distance 24 px is right-censored; offsets beyond 24 px are not measured."},
              "inputs": {"amateur_frame": str(ARTIFACT / "amateur_frame_0540.jpg"), "control_frame": str(ARTIFACT / "control_seed_frame_19599.jpg"),
                         "amateur_fit_measurement": str(ARTIFACT / "amateur_fit_measurement.json"), "control_measurement": str(ARTIFACT / "control_measurement.json")},
              "withheld_geometry": {"amateur": "left-end three-point curve and corner legs; baseline, lane boundaries, and free-throw line at y=0", "control": "near three-point curve and corner legs; both sidelines"},
              "records": records, "summary": {name: {group: _summary(item) for group, item in record.items()} for name, record in records.items()}}
    output.mkdir(parents=True, exist_ok=True)
    (output / "g255_measurement.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.output_dir)
    print("G255_AMATEUR_FOUND=" + str(report["summary"]["amateur_line_plus_conic"]["pooled"]["found"]))


if __name__ == "__main__":
    main()
