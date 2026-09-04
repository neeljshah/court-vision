"""Line and conic homography primitives for the G253 evidence-only measurement."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares


@dataclass(frozen=True)
class LineCorrespondence:
    """One named image-line to court-line correspondence with endpoints."""

    name: str
    image_endpoints: np.ndarray
    court_endpoints: np.ndarray


def homogeneous_line(endpoints: np.ndarray) -> np.ndarray:
    """Return a unit-normal homogeneous line through two Euclidean endpoints."""
    first, second = np.asarray(endpoints, dtype=float)
    line = np.cross(np.r_[first, 1.0], np.r_[second, 1.0])
    scale = float(np.hypot(line[0], line[1]))
    if scale <= 1e-12:
        raise ValueError("line endpoints must be distinct")
    return line / scale


def ellipse_conic(center: tuple[float, float], axes: tuple[float, float], angle_deg: float) -> np.ndarray:
    """Return the homogeneous conic matrix of an ellipse in the supplied pixels."""
    major, minor = axes
    if major <= 0 or minor <= 0:
        raise ValueError("ellipse axes must be positive")
    radians = np.deg2rad(angle_deg)
    rotation = np.array(((np.cos(radians), -np.sin(radians)), (np.sin(radians), np.cos(radians))))
    quadratic = rotation @ np.diag((1.0 / major**2, 1.0 / minor**2)) @ rotation.T
    centre = np.asarray(center, dtype=float)
    linear = -quadratic @ centre
    constant = float(centre @ quadratic @ centre - 1.0)
    return np.block([[quadratic, linear[:, None]], [linear[None, :], np.array([[constant]])]]).astype(float)


def circle_conic(center: tuple[float, float], radius: float) -> np.ndarray:
    """Return the homogeneous conic matrix of a court-coordinate circle."""
    return ellipse_conic(center, (radius, radius), 0.0)


def _similarity(points: np.ndarray) -> np.ndarray:
    centre = np.mean(points, axis=0)
    mean_distance = float(np.mean(np.linalg.norm(points - centre, axis=1)))
    if mean_distance <= 1e-12:
        raise ValueError("normalisation points have zero spread")
    scale = np.sqrt(2.0) / mean_distance
    return np.array(((scale, 0.0, -scale * centre[0]), (0.0, scale, -scale * centre[1]), (0.0, 0.0, 1.0)))


def _line_in_coordinates(line: np.ndarray, point_transform: np.ndarray) -> np.ndarray:
    transformed = np.linalg.inv(point_transform).T @ line
    return transformed / float(np.hypot(transformed[0], transformed[1]))


def _conic_in_coordinates(conic: np.ndarray, point_transform: np.ndarray) -> np.ndarray:
    inverse = np.linalg.inv(point_transform)
    return inverse.T @ conic @ inverse


def _line_rows(image_line: np.ndarray, court_line: np.ndarray) -> np.ndarray:
    map_to_line = np.zeros((3, 9), dtype=float)
    for column in range(3):
        map_to_line[column, column::3] = court_line
    cross = np.array(((0.0, -image_line[2], image_line[1]), (image_line[2], 0.0, -image_line[0]), (-image_line[1], image_line[0], 0.0)))
    return cross @ map_to_line


def fit_lines(correspondences: list[LineCorrespondence]) -> tuple[np.ndarray, float, np.ndarray]:
    """Fit image-to-court H from named lines and return H, design condition, singular values."""
    if len(correspondences) < 4:
        raise ValueError("at least four line correspondences are required")
    image_points = np.vstack([item.image_endpoints for item in correspondences])
    court_points = np.vstack([item.court_endpoints for item in correspondences])
    image_transform, court_transform = _similarity(image_points), _similarity(court_points)
    rows = []
    for item in correspondences:
        image_line = _line_in_coordinates(homogeneous_line(item.image_endpoints), image_transform)
        court_line = _line_in_coordinates(homogeneous_line(item.court_endpoints), court_transform)
        rows.append(_line_rows(image_line, court_line))
    design = np.vstack(rows)
    _unused, singular_values, vectors = np.linalg.svd(design)
    if singular_values[-2] <= 1e-12:
        raise ValueError("rank-deficient line system")
    h_normalised = vectors[-1].reshape(3, 3)
    homography = np.linalg.inv(court_transform) @ h_normalised @ image_transform
    homography /= homography[2, 2]
    return homography, float(singular_values[0] / singular_values[-2]), singular_values


def render_court(image: np.ndarray, homography: np.ndarray, sport: str, colour: tuple[int, int, int]) -> np.ndarray:
    """Return the source image with the declared court model inverse-projected."""
    from scripts.platformkit.tracking.g196_homography_from_labelled_corners import full_court_lines

    rendered, inverse = image.copy(), np.linalg.inv(homography)
    for court_line in full_court_lines(sport):
        projected = cv2.perspectiveTransform(court_line.reshape(1, -1, 2), inverse)[0]
        if np.isfinite(projected).all() and np.abs(projected).max() < 1_000_000:
            cv2.polylines(rendered, [np.round(projected).astype(np.int32)], False, colour, 2, cv2.LINE_AA)
    return rendered


def render_high_school_court(image: np.ndarray, homography: np.ndarray, colour: tuple[int, int, int]) -> np.ndarray:
    """Inverse-project the row-local assumed 84x50-ft high-school model."""
    lane_left, lane_right, length, depth = 19.0, 31.0, 84.0, 19.0
    lines = [np.float32(((0, 0), (50, 0), (50, length), (0, length), (0, 0))),
             np.float32(((0, 42), (50, 42))),
             np.float32(((lane_left, 0), (lane_right, 0), (lane_right, depth), (lane_left, depth), (lane_left, 0))),
             np.float32(((lane_left, length), (lane_right, length), (lane_right, length - depth), (lane_left, length - depth), (lane_left, length))),
             np.float32(np.column_stack((25 + 6 * np.cos(np.linspace(0, 2 * np.pi, 121)), 42 + 6 * np.sin(np.linspace(0, 2 * np.pi, 121)))))]
    for baseline, direction in ((0.0, 1.0), (length, -1.0)):
        basket = baseline + direction * 4.0
        angle = np.linspace(0, np.pi, 121)
        arc = np.column_stack((25 + 19.75 * np.cos(angle), basket + direction * 19.75 * np.sin(angle)))
        lines.extend((arc.astype(np.float32), np.float32(((arc[0, 0], baseline), arc[0])), np.float32(((arc[-1, 0], baseline), arc[-1]))))
    rendered, inverse = image.copy(), np.linalg.inv(homography)
    for line in lines:
        projected = cv2.perspectiveTransform(line.reshape(1, -1, 2), inverse)[0]
        if np.isfinite(projected).all() and np.abs(projected).max() < 1_000_000:
            cv2.polylines(rendered, [np.round(projected).astype(np.int32)], False, colour, 2, cv2.LINE_AA)
    return rendered


def projected_discrepancy_px(first: np.ndarray, second: np.ndarray, sport: str, image_shape: tuple[int, int]) -> dict[str, float]:
    """Measure all and shared-in-frame image-pixel separation of two court models."""
    from scripts.platformkit.tracking.g196_homography_from_labelled_corners import full_court_lines

    inverse_first, inverse_second = np.linalg.inv(first), np.linalg.inv(second)
    distances, visible_distances = [], []
    height, width = image_shape
    for court_line in full_court_lines(sport):
        one = cv2.perspectiveTransform(court_line.reshape(1, -1, 2), inverse_first)[0]
        two = cv2.perspectiveTransform(court_line.reshape(1, -1, 2), inverse_second)[0]
        finite = np.isfinite(one).all(axis=1) & np.isfinite(two).all(axis=1)
        distance = np.linalg.norm(one[finite] - two[finite], axis=1)
        one, two = one[finite], two[finite]
        shared_visible = ((one[:, 0] >= 0) & (one[:, 0] < width) & (one[:, 1] >= 0) & (one[:, 1] < height) &
                          (two[:, 0] >= 0) & (two[:, 0] < width) & (two[:, 1] >= 0) & (two[:, 1] < height))
        distances.extend(distance)
        visible_distances.extend(distance[shared_visible])
    values = np.asarray(distances)
    visible = np.asarray(visible_distances)
    return {"all_sample_points": float(values.size), "all_median_px": float(np.median(values)),
            "all_p90_px": float(np.percentile(values, 90)), "all_max_px": float(np.max(values)),
            "shared_in_frame_sample_points": float(visible.size), "shared_in_frame_median_px": float(np.median(visible)),
            "shared_in_frame_p90_px": float(np.percentile(visible, 90)), "shared_in_frame_max_px": float(np.max(visible))}


def image_line_angle_deg(first: np.ndarray, second: np.ndarray) -> float:
    """Return the acute image-space angle between two named line correspondences."""
    one, two = homogeneous_line(first), homogeneous_line(second)
    cosine = min(1.0, abs(float(np.dot(one[:2], two[:2]))))
    return float(np.rad2deg(np.arccos(cosine)))


def fit_line_conic(
    lines: list[LineCorrespondence],
    image_conic: np.ndarray,
    court_conic: np.ndarray,
    starts: int = 64,
    seed: int = 253,
) -> tuple[np.ndarray, float, float]:
    """Fit the line-plus-conic objective from fixed random starts, returning H and diagnostics."""
    if len(lines) != 2:
        raise ValueError("G253 amateur hypothesis is exactly two lines plus one conic")
    image_points, court_points = np.vstack([item.image_endpoints for item in lines]), np.vstack([item.court_endpoints for item in lines])
    image_transform, court_transform = _similarity(image_points), _similarity(court_points)
    normalised_lines = [(_line_in_coordinates(homogeneous_line(item.image_endpoints), image_transform), _line_in_coordinates(homogeneous_line(item.court_endpoints), court_transform)) for item in lines]
    target_conic = _conic_in_coordinates(image_conic, image_transform)
    target_conic /= np.linalg.norm(target_conic)
    model_conic = _conic_in_coordinates(court_conic, court_transform)

    def residual(parameters: np.ndarray) -> np.ndarray:
        homography = np.r_[parameters, 1.0].reshape(3, 3)
        values = []
        for image_line, court_line in normalised_lines:
            projected = homography.T @ court_line
            projected /= np.hypot(projected[0], projected[1])
            values.extend(np.cross(image_line, projected))
        predicted = homography.T @ model_conic @ homography
        predicted /= np.linalg.norm(predicted)
        if float(np.sum(predicted * target_conic)) < 0:
            predicted *= -1.0
        values.extend((predicted - target_conic).ravel())
        return np.asarray(values)

    rng, best = np.random.default_rng(seed), None
    for start in range(starts):
        initial = np.array((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0))
        if start:
            initial += rng.normal(0.0, 0.35, 8)
        result = least_squares(residual, initial, max_nfev=4000, method="trf")
        if best is None or float(np.dot(result.fun, result.fun)) < float(np.dot(best.fun, best.fun)):
            best = result
    assert best is not None
    homography = np.r_[best.x, 1.0].reshape(3, 3)
    homography = np.linalg.inv(court_transform) @ homography @ image_transform
    homography /= homography[2, 2]
    singular_values = np.linalg.svd(best.jac, compute_uv=False)
    condition = float(singular_values[0] / singular_values[-1]) if singular_values[-1] > 1e-12 else float("inf")
    return homography, float(np.linalg.norm(best.fun)), condition


def run_control(image_path: Path, lines_path: Path, output_dir: Path) -> dict[str, object]:
    """Fit pre-recorded line labels and emit the two required WNBA control renders."""
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    payload = json.loads(lines_path.read_text(encoding="ascii"))
    lines = [LineCorrespondence(item["name"], np.asarray(item["image_endpoints"], dtype=float),
                                np.asarray(item["court_endpoints"], dtype=float)) for item in payload["lines"]]
    published = np.asarray(payload["published_homography_image_to_court"], dtype=float)
    fitted, condition, singular_values = fit_lines(lines)
    output_dir.mkdir(parents=True, exist_ok=True)
    line_render = output_dir / "control_lines_only_render.jpg"
    published_render = output_dir / "control_published_render.jpg"
    if not cv2.imwrite(str(line_render), render_court(image, fitted, "wnba", (0, 255, 255))):
        raise OSError(line_render)
    if not cv2.imwrite(str(published_render), render_court(image, published, "wnba", (255, 0, 255))):
        raise OSError(published_render)
    discrepancy = projected_discrepancy_px(fitted, published, "wnba", image.shape[:2])
    result = {
        "input_image": str(image_path), "native_resolution_px": [int(image.shape[1]), int(image.shape[0])],
        "line_names": [line.name for line in lines], "line_fit_homography_image_to_court": fitted.tolist(),
        "published_homography_image_to_court": published.tolist(), "line_design_condition_number": condition,
        "line_design_singular_values": singular_values.tolist(), "projected_court_discrepancy_px": discrepancy,
        "line_render": str(line_render), "published_render": str(published_render),
    }
    (output_dir / "control_measurement.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-image", type=Path, required=True)
    parser.add_argument("--control-lines", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run_control(args.control_image, args.control_lines, args.output_dir)
    print("G253_CONTROL_VISIBLE_P90_PX=" + format(result["projected_court_discrepancy_px"]["shared_in_frame_p90_px"], ".6f"))


if __name__ == "__main__":
    main()
