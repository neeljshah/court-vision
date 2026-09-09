"""G342 finisher-authored synthetic validation driver, fix 1c (not part of the sealed prereg).

Runs the prereg's Arm A (true H per template; best-of-50 seeded re-fit for the non-true
templates) and Arm B (2 px corner-jittered Arm-A homography) over 200 independent
camera-like frames per template (NBA, WNBA, FIBA, NCAA) and writes confusion.csv,
separation.csv, and archive.csv into the given output directory. Deterministic given the
sealed seed.

Fix 1d (`docs/evidence/tracking/g342_prereg_fix1d_2026-09-08.md`, sealed) uses
real gated calls to `select_template` on held-out VALIDATION-only observations:
  * The 200 renders per template are labelled frame_id 0..199 and grouped into 40
    pseudo-shots of 5 (shot_id = frame_id // 5).
  * A decision pools five frames with at least two shot IDs. There are 40 independent,
    non-overlapping decisions per template per arm. Its VALIDATION-only winner labels its five
    frames, preserving the required n=200 matrix population.
  * Pairwise separation (spec:37-53's frame-level cost-share diagnostic, distinct from the
    gated decision) and the best-of-50 re-fit / arm-B jitter methods are unchanged from the
    rejected candidate (amendment 4).
  * archive.csv records held-out residuals and observed_polylines.csv preserves their
    VALIDATION inputs; decisions.csv preserves FIT costs and bootstrap/group diagnostics.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.court_templates.template_select import _frame_cost, _project, select_template
from scripts.platformkit.court_templates.templates import load_template, segments

_NAMES = ("nba", "wnba", "fiba", "ncaa")
_IMG_W, _IMG_H = 1280, 720
_RECT = np.array([[0, 0], [_IMG_W, 0], [_IMG_W, _IMG_H], [0, _IMG_H]], dtype=np.float32)
_SHOT_SIZE = 5
_FRAMES_PER_DECISION = _SHOT_SIZE


def _corners(length: float, width: float) -> np.ndarray:
    return np.array([[0, 0], [length, 0], [0, width], [length, width]], dtype=np.float32)


def _sample_H(rng: np.random.Generator, length: float, width: float, max_tries: int = 50) -> np.ndarray:
    """Sample one camera-like homography per the sealed prereg ranges; redraw until visible."""
    corners = _corners(length, width)
    for _ in range(max_tries):
        cx, cy = rng.uniform(0.35 * length, 0.65 * length), rng.uniform(0.35 * width, 0.65 * width)
        scale = rng.uniform(900.0, 1600.0) / length
        cos_tilt = float(np.cos(np.radians(rng.uniform(-18.0, 18.0))))
        p1, p2 = rng.uniform(-0.00035, 0.00035, 2)
        H = np.array([[scale, 0.0, _IMG_W / 2 - scale * cx], [0.0, scale * cos_tilt, _IMG_H / 2 - scale * cos_tilt * cy],
                      [p1, p2, 1 - p1 * cx - p2 * cy]], dtype=np.float32)
        pts = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), H).reshape(-1, 2)
        if not np.isfinite(pts).all():
            continue
        hull = cv2.convexHull(pts.astype(np.float32))
        hull_area = cv2.contourArea(hull)
        if hull_area <= 0:
            continue
        inter_area, _ = cv2.intersectConvexConvex(hull, _RECT)
        if inter_area / hull_area >= 2.0 / 3.0:
            return H
    return H  # safety cap: ranges are generous enough that this is not expected to trigger


def _resample(points: np.ndarray, n: int = 25) -> np.ndarray:
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    if d[-1] == 0:
        return np.repeat(points[:1], n, axis=0)
    t = np.linspace(0.0, d[-1], n)
    return np.column_stack((np.interp(t, d, points[:, 0]), np.interp(t, d, points[:, 1])))


def _observe(rng: np.random.Generator, template: dict, H: np.ndarray) -> list[dict]:
    """Render, then add per-stroke Gaussian noise and one 30 pct contiguous occlusion."""
    out = []
    for seg in segments(template):
        pts = cv2.perspectiveTransform(seg["points"].reshape(-1, 1, 2), H).reshape(-1, 2)
        pts = _resample(pts) + rng.normal(0.0, rng.uniform(1.0, 3.0), (25, 2))
        start = rng.uniform(0.0, 0.7)
        frac = np.linspace(0.0, 1.0, len(pts))
        keep = (frac < start) | (frac > start + 0.3)
        if keep.sum() < 2:
            keep[:2] = True
        out.append({"semantic_id": seg["semantic_id"], "family": seg["family"], "points": pts[keep].astype(np.float32)})
    return out


def _fit_validation_markings(observed: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split observations into disjoint whole markings for fit and validation."""
    fit, validation = [], []
    for index, marking in enumerate(observed):
        # Each semantic stroke is an indivisible marking. Alternating by its stable
        # generation order gives both subsets line and arc support without reuse.
        (fit if index % 2 == 0 else validation).append(marking)
    return fit, validation


def _best_refit(rng: np.random.Generator, template: dict, observed: list[dict], n: int = 50) -> np.ndarray:
    best_cost, best_H = None, None
    for _ in range(n):
        H = _sample_H(rng, template["feet"]["length"], template["feet"]["width"])
        cost, _ = _frame_cost(observed, _project(template, H))
        if best_cost is None or cost < best_cost:
            best_cost, best_H = cost, H
    return best_H


def _jitter_H(rng: np.random.Generator, template: dict, H: np.ndarray) -> np.ndarray:
    corners = _corners(template["feet"]["length"], template["feet"]["width"])
    img_pts = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), H).reshape(-1, 2)
    jittered = (img_pts + rng.uniform(-2.0, 2.0, img_pts.shape)).astype(np.float32)
    return cv2.getPerspectiveTransform(corners, jittered)


def _score_template_population(rng: np.random.Generator, templates: dict, true_name: str, n: int) -> tuple[list, list, dict, dict]:
    """Fit candidate H on FIT markings; select and report costs on VALIDATION markings."""
    true_tpl = templates[true_name]
    fit_by_frame, validation_by_frame = [None] * n, [None] * n
    H = {"a": {name: [None] * n for name in _NAMES}, "b": {name: [None] * n for name in _NAMES}}
    cost = {"a": {name: [None] * n for name in _NAMES}, "b": {name: [None] * n for name in _NAMES}}
    for frame_id in range(n):
        H_true = _sample_H(rng, true_tpl["feet"]["length"], true_tpl["feet"]["width"])
        observed = _observe(rng, true_tpl, H_true)
        fit, validation = _fit_validation_markings(observed)
        fit_by_frame[frame_id], validation_by_frame[frame_id] = fit, validation
        H_by_name = {true_name: H_true}
        for wrong_name in _NAMES:
            if wrong_name != true_name:
                H_by_name[wrong_name] = _best_refit(rng, templates[wrong_name], fit)
        for arm in ("a", "b"):
            for name, H_a in H_by_name.items():
                scored_H = H_a if arm == "a" else _jitter_H(rng, templates[name], H_a)
                scored_cost, _ = _frame_cost(validation, _project(templates[name], scored_H))
                H[arm][name][frame_id] = scored_H
                cost[arm][name][frame_id] = scored_cost
    return fit_by_frame, validation_by_frame, H, cost


def run(seed: int = 34220260908, n: int = 200) -> tuple[dict, dict, list, list, list]:
    templates = {name: load_template(name) for name in _NAMES}
    confusion = {arm: {true: {w: 0 for w in _NAMES + ("unknown",)} for true in _NAMES} for arm in ("a", "b")}
    separation = {arm: {other: {"win": 0, "n": 0} for other in ("wnba", "fiba", "ncaa")} for arm in ("a", "b")}
    archive, observed_archive, decisions = [], [], []
    rng = np.random.default_rng(seed)
    n_decisions = n // _FRAMES_PER_DECISION
    for true_name in _NAMES:
        fit_by_frame, validation_by_frame, H, cost = _score_template_population(rng, templates, true_name, n)
        for frame_id, subsets in enumerate(zip(fit_by_frame, validation_by_frame)):
            for subset_name, markings in zip(("fit", "validation"), subsets):
                for marking_index, marking in enumerate(markings):
                    for point_index, point in enumerate(marking["points"]):
                        observed_archive.append((true_name, frame_id, subset_name, marking_index, marking["semantic_id"], marking["family"], point_index, point))
        for arm in ("a", "b"):
            for name in _NAMES:
                for frame_id in range(n):
                    archive.append((arm, true_name, frame_id, frame_id // _SHOT_SIZE, name, H[arm][name][frame_id], cost[arm][name][frame_id]))
            if true_name == "nba":
                for other in ("wnba", "fiba", "ncaa"):
                    for frame_id in range(n):
                        separation[arm][other]["n"] += 1
                        separation[arm][other]["win"] += cost[arm]["nba"][frame_id] <= 0.8 * cost[arm][other][frame_id]
            for d in range(n_decisions):
                idxs = range(d * _FRAMES_PER_DECISION, (d + 1) * _FRAMES_PER_DECISION)
                frames = [{"shot_id": f"shot-{i // 2}", "segments": validation_by_frame[i]} for i in idxs]
                homographies = {name: [H[arm][name][i] for i in idxs] for name in _NAMES}
                result = select_template(frames, templates, homographies)
                winner = result["winner"]
                validation_cost = {name: float(np.median([cost[arm][name][i] for i in idxs])) for name in _NAMES}
                decisions.append((arm, true_name, d, winner, result, validation_cost))
                # One held-out VALIDATION selector decision labels each of its five original
                # frames, preserving the spec's n=200-frame confusion population.
                confusion[arm][true_name][winner if winner in _NAMES else "unknown"] += _FRAMES_PER_DECISION
    return confusion, separation, archive, observed_archive, decisions


def _write_confusion(confusion: dict, path: Path) -> None:
    with path.open("w", newline="\n", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["arm", "true_template", "NBA", "WNBA", "FIBA", "NCAA", "UNKNOWN", "n"])
        for arm in ("a", "b"):
            for true_name in _NAMES:
                row = confusion[arm][true_name]
                counts = [row[w] for w in _NAMES] + [row["unknown"]]
                writer.writerow([arm, true_name.upper()] + [f"{c:06d}" for c in counts] + [f"{sum(counts):06d}"])


def _write_separation(separation: dict, path: Path) -> None:
    with path.open("w", newline="\n", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["arm", "pair", "nba_outright_wins", "n", "share"])
        for arm in ("a", "b"):
            for other in ("wnba", "fiba", "ncaa"):
                cell = separation[arm][other]
                writer.writerow([arm, f"nba_vs_{other}", f"{cell['win']:06d}", f"{cell['n']:06d}", f"{cell['win'] / cell['n']:.6f}"])


def _write_archive(archive: list, path: Path) -> None:
    with path.open("w", newline="\n", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["arm", "true_template", "frame_id", "shot_id", "scored_template",
                          "h00", "h01", "h02", "h10", "h11", "h12", "h20", "h21", "h22", "cost",
                          "h00_repr", "h01_repr", "h02_repr", "h10_repr", "h11_repr", "h12_repr",
                          "h20_repr", "h21_repr", "h22_repr", "cost_repr"])
        for arm, true_name, frame_id, shot_id, scored_name, H, cost in archive:
            writer.writerow(_archive_row(arm, true_name, frame_id, shot_id, scored_name, H, cost))


def _archive_row(arm: str, true_name: str, frame_id: int, shot_id: int, scored_name: str, H: np.ndarray, cost: float) -> list[str]:
    """Return one additive archive row, retaining both six-decimal and full precision fields."""
    h_values = np.asarray(H).reshape(-1)
    h_flat = [f"{v:.6f}" for v in h_values]
    h_repr = [repr(float(v)) for v in h_values]
    return [arm, true_name.upper(), f"{frame_id:06d}", f"{shot_id:06d}", scored_name.upper()] + h_flat + [f"{cost:.6f}"] + h_repr + [repr(float(cost))]


def _write_observed_polylines(rows: list, path: Path) -> None:
    with path.open("w", newline="\n", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["true_template", "frame_id", "subset", "marking_index", "semantic_id", "family", "point_index", "x", "y", "x_repr", "y_repr"])
        for true_name, frame_id, subset, marking_index, semantic_id, family, point_index, point in rows:
            writer.writerow([true_name.upper(), f"{frame_id:06d}", subset, f"{marking_index:06d}", semantic_id, family, f"{point_index:06d}", f"{point[0]:.6f}", f"{point[1]:.6f}", repr(float(point[0])), repr(float(point[1]))])


def _write_decisions(rows: list, path: Path) -> None:
    with path.open("w", newline="\n", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["arm", "true_template", "decision_id", "frame_start", "frame_end", "selection_subset", "scoring_subset", "winner", "bootstrap_wins", "distinctive_groups", "fit_group_wins", "selection_cost_nba", "selection_cost_wnba", "selection_cost_fiba", "selection_cost_ncaa", "fit_cost_nba", "fit_cost_wnba", "fit_cost_fiba", "fit_cost_ncaa", "validation_cost_nba", "validation_cost_wnba", "validation_cost_fiba", "validation_cost_ncaa"])
        for arm, true_name, decision_id, winner, result, validation_cost in rows:
            group_values = ";".join(f"{name}:{','.join(f'{group}={value}' for group, value in sorted(result['group_wins'][name].items()))}" for name in _NAMES)
            selection_costs = [f"{result['costs'][name]:.6f}" for name in _NAMES]
            writer.writerow([arm, true_name.upper(), f"{decision_id:06d}", f"{decision_id * _FRAMES_PER_DECISION:06d}", f"{(decision_id + 1) * _FRAMES_PER_DECISION - 1:06d}", "validation", "validation", winner, f"{result['bootstrap_wins']:06d}", f"{result['distinctive_groups']:06d}", group_values] + selection_costs + selection_costs + [f"{validation_cost[name]:.6f}" for name in _NAMES])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=34220260908)
    parser.add_argument("--n", type=int, default=200)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    confusion, separation, archive, observed_archive, decisions = run(args.seed, args.n)
    _write_confusion(confusion, args.out / "confusion.csv")
    _write_separation(separation, args.out / "separation.csv")
    _write_archive(archive, args.out / "archive.csv")
    _write_observed_polylines(observed_archive, args.out / "observed_polylines.csv")
    _write_decisions(decisions, args.out / "decisions.csv")
    for true_name in _NAMES:
        row = confusion["a"][true_name]
        n_decisions = sum(row[w] for w in _NAMES + ("unknown",))
        wrong = sum(row[w] for w in _NAMES if w != true_name)
        print(f"{true_name} true_win_rate={row[true_name] / n_decisions:.4f} wrong_winner_share={wrong / n_decisions:.4f} unknown={row['unknown']} n_decisions={n_decisions}")


if __name__ == "__main__":
    main()
