"""Measure untruncated global court fitting; labels are scoring and oracle-only."""
from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import CandidateLineGroup
from scripts.platformkit.tracking.g196_homography_from_labelled_corners import court_points_for_sport, full_court_lines
from scripts.platformkit.tracking.g205_zero_shot_corner_probe import score_frame
from scripts.platformkit.tracking.g210_court_model_fit_to_lines import (
    HYPOTHESIS_SEED, PROJECTED_CORNER_MARGIN_MULTIPLIER, SUPPORT_ANGLE_DEG,
    SUPPORT_DISTANCE_PX, TRANSVERSE_NAMES, LONGITUDINAL_NAMES, _court_lines,
    _groups, _sources, _valid_projection, solve_line_pairs,
)


ROOT = Path("docs/evidence/tracking")
TARGETS = ROOT / "g140_corner_targets/corner_pixel_targets.csv"
OUT = ROOT / "g210b_court_fit_untruncated_search_artifact"
HYPOTHESES_PER_FRAME = 16_384
RENDER_INDICES = (0, 4, 8, 12, 16)


@dataclass(frozen=True)
class FitResult:
    """A label-free full-group global fit."""

    homography_image_to_court: list[list[float]]
    support_length_px: float
    supported_groups: int
    group_count: int
    configuration_space: int
    hypotheses_tested: int
    valid_hypotheses: int


def _space(group_count: int) -> int:
    """Count four-group partitions and ordered model-pair assignments."""
    return math.comb(group_count, 4) * 6 * 12 * 12


def _support(homography: np.ndarray, groups: list[CandidateLineGroup], sport: str) -> tuple[float, int]:
    projected = np.asarray([homography.T @ line for line in _court_lines(sport).values()], dtype=float)
    projected /= np.hypot(projected[:, 0], projected[:, 1])[:, None]
    anchors = np.asarray([(*group.anchor, 1.0) for group in groups])
    directions = np.asarray([group.direction for group in groups])
    distances = np.abs(anchors @ projected.T)
    alignment = np.abs(directions @ projected[:, :2].T)
    explained = np.any((distances <= SUPPORT_DISTANCE_PX) & (alignment >= np.cos(np.deg2rad(SUPPORT_ANGLE_DEG))), axis=1)
    lengths = np.asarray([group.length for group in groups])
    return float(lengths[explained].sum()), int(explained.sum())


def fit_image(image: np.ndarray, sport: str) -> FitResult | None:
    """Search all detected groups by a fixed, label-free uniform sampler."""
    groups = _groups(image)
    if len(groups) < 4:
        return None
    height, width = image.shape[:2]
    model, rng, best = _court_lines(sport), random.Random(HYPOTHESIS_SEED), None
    valid = 0
    for _ in range(HYPOTHESES_PER_FRAME):
        group_set = sorted(rng.sample(range(len(groups)), 4))
        first, second, third, fourth = group_set
        partitions = ((first, second, third, fourth), (first, third, second, fourth), (first, fourth, second, third))
        picked = partitions[rng.randrange(len(partitions))]
        if rng.randrange(2):
            picked = (*picked[2:], *picked[:2])
        homography = solve_line_pairs(
            tuple(groups[index].line for index in picked[:2]),
            tuple(groups[index].line for index in picked[2:]),
            tuple(model[name] for name in rng.sample(TRANSVERSE_NAMES, 2)),
            tuple(model[name] for name in rng.sample(LONGITUDINAL_NAMES, 2)),
        )
        if homography is None or not _valid_projection(homography, sport, width, height):
            continue
        valid += 1
        support, count = _support(homography, groups, sport)
        candidate = (support, count, homography)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return None
    return FitResult(best[2].astype(float).tolist(), best[0], best[1], len(groups), _space(len(groups)), HYPOTHESES_PER_FRAME, valid)


def _read_targets() -> dict[str, list[dict[str, str]]]:
    with TARGETS.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["audit_id"], []).append(row)
    if len(rows) != 68 or len(grouped) != 17 or any(len(values) != 4 for values in grouped.values()):
        raise ValueError("G140 construct changed")
    return grouped


def _proposals(homography: np.ndarray | None, sport: str) -> list[tuple[float, float]]:
    if homography is None:
        return []
    inverse = np.linalg.inv(homography)
    points = cv2.perspectiveTransform(court_points_for_sport(sport).reshape(1, -1, 2), inverse)[0]
    return [tuple(map(float, point)) for point in points]


def oracle_fit(image: np.ndarray, sport: str, targets: list[dict[str, str]]) -> tuple[np.ndarray | None, list[int], list[float]]:
    """Label-only control: choose the nearest full-set group to each true paint line."""
    groups = _groups(image)
    target_pairs = ((targets[0], targets[1]), (targets[2], targets[3]),
                    (targets[0], targets[2]), (targets[1], targets[3]))
    picked, distances = [], []
    for first, second in target_pairs:
        points = ((float(first["x_px"]), float(first["y_px"]), 1.0), (float(second["x_px"]), float(second["y_px"]), 1.0))
        values = [float(np.mean([abs(group.line @ point) for point in points])) for group in groups]
        picked.append(int(np.argmin(values)))
        distances.append(float(min(values)))
    model = _court_lines(sport)
    homography = solve_line_pairs(tuple(groups[index].line for index in picked[:2]), tuple(groups[index].line for index in picked[2:]),
                                  (model["near_baseline"], model["near_free_throw"]), (model["lane_left"], model["lane_right"]))
    return homography, picked, distances


def _render(image: np.ndarray, homography: np.ndarray, sport: str, destination: Path) -> None:
    panel, inverse = image.copy(), np.linalg.inv(homography)
    for court_line in full_court_lines(sport):
        projected = cv2.perspectiveTransform(court_line.reshape(1, -1, 2), inverse)[0]
        if np.isfinite(projected).all() and np.abs(projected).max() < 1_000_000:
            cv2.polylines(panel, [np.round(projected).astype(np.int32)], False, (0, 255, 255), 2, cv2.LINE_AA)
    if not cv2.imwrite(str(destination), panel, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(destination)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run() -> dict[str, Any]:
    """Freeze real fits before loading labels for scoring and the oracle control."""
    OUT.mkdir(exist_ok=True)
    (OUT / "renders").mkdir(exist_ok=True)
    sources, fits, images = _sources(), {}, {}
    for source in sources:
        image = cv2.imread(str(source.source_path), cv2.IMREAD_COLOR)
        if image is None or image.shape[1::-1] != (source.width, source.height):
            raise ValueError(f"bad source decode: {source.audit_id}")
        images[source.audit_id], fits[source.audit_id] = image, fit_image(image, source.sport)
    (OUT / "fit_records.json").write_text(json.dumps({key: None if value is None else asdict(value) for key, value in fits.items()}, indent=2) + "\n", encoding="ascii")
    targets, real_rows, oracle_rows, frame_rows = _read_targets(), [], [], []
    for index, source in enumerate(sources):
        fit = fits[source.audit_id]
        real, _, real_all = score_frame(targets[source.audit_id], _proposals(None if fit is None else np.asarray(fit.homography_image_to_court), source.sport))
        oracle_h, picked, distances = oracle_fit(images[source.audit_id], source.sport, targets[source.audit_id])
        oracle, _, oracle_all = score_frame(targets[source.audit_id], _proposals(oracle_h, source.sport))
        real_rows.extend(real)
        oracle_rows.extend(oracle)
        frame_rows.append({"audit_id": source.audit_id, "sport": source.sport, "fit": fit is not None,
                           "group_count": "" if fit is None else fit.group_count, "configuration_space": "" if fit is None else fit.configuration_space,
                           "hypotheses_tested": "" if fit is None else fit.hypotheses_tested, "valid_hypotheses": "" if fit is None else fit.valid_hypotheses,
                           "sampled_fraction": "" if fit is None else f"{fit.hypotheses_tested / fit.configuration_space:.12g}",
                           "line_support_px": "" if fit is None else f"{fit.support_length_px:.3f}", "supported_groups": "" if fit is None else fit.supported_groups,
                           "all_four_within_12px": real_all, "oracle_all_four_within_12px": oracle_all,
                           "oracle_group_indices": ";".join(map(str, picked)), "oracle_line_distances_px": ";".join(f"{value:.3f}" for value in distances)})
        if fit is not None and index in RENDER_INDICES:
            _render(images[source.audit_id], np.asarray(fit.homography_image_to_court), source.sport, OUT / "renders" / f"{index:02d}_{source.audit_id}.jpg")
    _write_csv(OUT / "target_scores.csv", real_rows)
    _write_csv(OUT / "oracle_target_scores.csv", oracle_rows)
    _write_csv(OUT / "per_frame.csv", frame_rows)
    errors = [float(row["nearest_proposal_distance_px"]) for row in real_rows]
    oracle_errors = [float(row["nearest_proposal_distance_px"]) for row in oracle_rows]
    maxima = [max(float(row["nearest_proposal_distance_px"]) for row in oracle_rows[index:index + 4]) for index in range(0, len(oracle_rows), 4)]
    summary = {"frames_all_four": sum(bool(row["all_four_within_12px"]) for row in frame_rows), "frames_total": len(frame_rows),
               "corner_errors_px": {"min": min(errors), "median": float(np.median(errors)), "p90": float(np.percentile(errors, 90)), "max": max(errors)},
               "oracle_frames_all_four": sum(bool(row["oracle_all_four_within_12px"]) for row in frame_rows),
               "oracle_median_max_corner_error_px": float(np.median(maxima)),
               "oracle_corner_errors_px": {"min": min(oracle_errors), "median": float(np.median(oracle_errors)), "p90": float(np.percentile(oracle_errors, 90)), "max": max(oracle_errors)},
               "hypotheses_per_frame": HYPOTHESES_PER_FRAME, "render_indices": list(RENDER_INDICES)}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    print(f"all_four={summary['frames_all_four']}/{summary['frames_total']} oracle={summary['oracle_frames_all_four']}/{summary['frames_total']}")
    return summary


if __name__ == "__main__":
    run()
