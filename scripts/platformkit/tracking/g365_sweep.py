"""G365 runner: the premise re-run, the noise sweep, and the eight overlays.

`premise` re-runs G362's known-H path UNCHANGED (its strokes, its search, its validator) on the four
sealed geometries and caches each 4-corner winner, so the enumeration runs once per geometry and the
premise is always measured before anything is refined (contract Q8). `sweep` refines each cached
winner over its FIT supports and then runs the sub-pixel endpoint noise draws; `render` writes one
overlay per geometry per arm. The GEOMETRY path is the DETECTED one (painted raster, LSD detection,
whole-stroke grouping, G362's complete enumeration); the NOISE path skips the detector and jitters
the projected endpoints of the nine straight markings, the only way to put a KNOWN sigma on the
quantity G362's diagnostic named as the floor. Every constant here is sealed in
`g365_fitter_refinement_2026-09-09/g365_prereg_2026-09-09.md`; `BAR_PX` is G362's, never moved (Q3).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("OMP_NUM_THREADS", "2")

from pathlib import Path  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from scripts.platformkit.tracking import g334_metrics as gm  # noqa: E402
from scripts.platformkit.tracking import g362_fit_validate as fv  # noqa: E402
from scripts.platformkit.tracking import g362_strokes as st  # noqa: E402
from scripts.platformkit.tracking import g362_synth as synth  # noqa: E402
from scripts.platformkit.tracking import g365_refine as rf  # noqa: E402
from scripts.platformkit.tracking.g334_court_template import (  # noqa: E402
    HALF_COURT_QUAD, TEMPLATE_POINTS,
)

cv2.setNumThreads(1)

BAR_PX = 1.0
SIGMAS = (0.0, 0.25, 0.5, 1.0)
DRAWS = 40
FIT_LINES, VAL_LINES = (0, 1, 2, 3, 4, 5, 8), (6, 7)  # indices into straight_template_lines()
CORNER_PAIRS = ((0, 1), (0, 2), (3, 2), (3, 1))
GEOMETRIES = (
    ("G1_SYNTH_QUAD", ((180.0, 690.0), (1100.0, 690.0), (960.0, 200.0), (320.0, 200.0))),
    ("G2_WIDE", ((120.0, 700.0), (1160.0, 700.0), (1000.0, 240.0), (280.0, 240.0))),
    ("G3_TIGHT", ((260.0, 660.0), (1020.0, 660.0), (900.0, 250.0), (380.0, 250.0))),
    ("G4_OFF_AXIS", ((200.0, 700.0), (1120.0, 660.0), (940.0, 220.0), (300.0, 250.0))),
)
SWEEP_COLS = ("geometry,sigma_px,draw,seed,baseline_gap_px,refined_gap_px,improvement_px,"
              "n_supports,n_assigned,n_fev,status,base_val_px,ref_val_px")
RECOVERY_COLS = ("geometry,state,baseline_gap_px,refined_gap_px,improvement_px,bar_px,n_strokes,"
                 "n_fit_strokes,n_val_strokes,n_val_points,n_supports,n_assigned,n_fev,status,"
                 "base_val_forward_px,base_val_inverse_px,ref_val_forward_px,ref_val_inverse_px")


def geometry_matrix(quad) -> np.ndarray:
    """The feet-to-image homography of a sealed view quad, normalised by its (2, 2) element."""
    matrix = cv2.getPerspectiveTransform(HALF_COURT_QUAD, np.asarray(quad, dtype=np.float32))
    return np.asarray(matrix, dtype=float) / float(matrix[2, 2])


def _write(path: Path, header: str, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write(header + "\n")
        for row in rows:
            handle.write(",".join(str(cell) for cell in row) + "\n")
    print("WROTE %s rows=%d" % (path.as_posix(), len(rows)))


def _gap(truth: np.ndarray, matrix) -> float:
    return (float("inf") if matrix is None else
            synth.reprojection_median(truth, np.asarray(matrix, dtype=float), TEMPLATE_POINTS))


def premise(out: Path) -> int:
    """Re-run G362's known-H path on the four sealed geometries and cache each 4-corner winner."""
    rows = {}
    for name, quad in GEOMETRIES:
        truth = geometry_matrix(quad)
        decision = fv.decide(synth.render_court(truth))
        gap = _gap(truth, decision.image_matrix)
        rows[name] = {
            "quad": [[float(v) for v in point] for point in quad], "state": decision.state,
            "reason": decision.reason, "baseline_gap_px": round(gap, 4), "bar_px": BAR_PX,
            "forward_median_px": round(decision.forward_median, 4), "n_strokes": decision.n_strokes,
            "inverse_median_px": round(decision.inverse_median, 4),
            "n_val_points": decision.n_val_points, "n_hypotheses": decision.n_hypotheses,
            "image_matrix": (decision.image_matrix.tolist()
                             if decision.image_matrix is not None else None)}
        print("PREMISE %s %s gap=%.4f bar=%.1f px" % (name, decision.state, gap, BAR_PX))
    inside = all(row["baseline_gap_px"] <= BAR_PX for row in rows.values())
    payload = {"row": "G365", "bar_px": BAR_PX, "premise": "FALSE" if inside else "TRUE",
               "geometries": rows}
    out.mkdir(parents=True, exist_ok=True)
    (out / "premise.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("PREMISE %s -- FALSE means every geometry already recovers within the bar: STOP"
          % payload["premise"])
    return 2 if inside else 0


def _recover(name: str, quad, cached: dict):
    """Refine the CACHED 4-corner winner over the FIT supports of the same painted raster."""
    truth = geometry_matrix(quad)
    frame, _scale = fv.to_base_height(synth.render_court(truth))
    strokes = st.extract_strokes(frame)
    fit_strokes, val_strokes = st.partition(strokes)
    fit_supports, val_supports = st.support_array(fit_strokes), st.support_array(val_strokes)
    if cached["image_matrix"] is None:
        print("SKIP %s: the premise left no 4-corner winner to refine" % name)
        return None, None
    baseline = np.asarray(cached["image_matrix"], dtype=float)
    refined, stats = rf.refine_homography(baseline, fit_supports)
    base_gap, ref_gap = _gap(truth, baseline), _gap(truth, refined)
    base_val = fv.bidirectional(baseline, val_supports, frame.shape)
    ref_val = fv.bidirectional(refined, val_supports, frame.shape)
    row = [name, cached["state"], "%.4f" % base_gap, "%.4f" % ref_gap,
           "%.4f" % (base_gap - ref_gap), BAR_PX, len(strokes), len(fit_strokes),
           len(val_strokes), len(val_supports), stats["n_supports"], stats["n_assigned"],
           stats["n_fev"], stats["status"],
           "%.4f" % float(np.median(base_val[0])), "%.4f" % float(np.median(base_val[1])),
           "%.4f" % float(np.median(ref_val[0])), "%.4f" % float(np.median(ref_val[1]))]
    print("RECOVER %s baseline=%.4f refined=%.4f improvement=%.4f px status=%s"
          % (name, base_gap, ref_gap, base_gap - ref_gap, stats["status"]))
    return row, refined


def seed_of(name: str, sigma: float, draw: int, prefix: str = "G365") -> int:
    """The sealed seed of one draw: content-addressed, so any draw reproduces on its own."""
    key = "%s|%s|%.2f|%03d" % (prefix, name, sigma, draw)
    return int(hashlib.sha256(key.encode("ascii")).hexdigest()[:8], 16)


def draw_lines(truth: np.ndarray, sigma: float, seed: int):
    """Project the nine straight markings and jitter every endpoint by N(0, sigma) pixels."""
    lines = rf.straight_template_lines()
    starts = rf.apply_h(truth, np.asarray([line[0] for line in lines], dtype=float))
    ends = rf.apply_h(truth, np.asarray([line[1] for line in lines], dtype=float))
    if sigma > 0.0:
        rng = np.random.default_rng(seed)
        starts = starts + rng.normal(0.0, sigma, starts.shape)
        ends = ends + rng.normal(0.0, sigma, ends.shape)
    return starts, ends


def corner_solve(starts: np.ndarray, ends: np.ndarray):
    """The ARCHIVED path: two W and two L image lines, four intersections, one 4-point solve."""
    coef = rf.line_coefficients(starts, ends)
    corners = []
    for w, l in CORNER_PAIRS:
        point = np.cross(coef[w], coef[l])
        if not np.isfinite(point).all() or abs(float(point[2])) < 1e-12:
            return None
        corners.append((point[0] / point[2], point[1] / point[2]))
    quad = np.asarray(corners, dtype=np.float32)
    if not np.isfinite(quad).all() or float(np.abs(quad).max()) > 1e6:
        return None
    matrix = cv2.getPerspectiveTransform(HALF_COURT_QUAD, quad)
    return (None if abs(float(matrix[2, 2])) < 1e-12
            else np.asarray(matrix, dtype=float) / float(matrix[2, 2]))


def supports_along(start: np.ndarray, end: np.ndarray, spacing: float = st.SUPPORT_SPACING_PX):
    """Points at the G362 support spacing along one noisy image line, endpoints included."""
    steps = max(1, int(float(np.linalg.norm(end - start)) // spacing))
    return start + (end - start) * np.linspace(0.0, 1.0, steps + 1)[:, None]


def val_median_px(matrix, starts: np.ndarray, ends: np.ndarray) -> float:
    """The HELD-OUT lines' supports against their projection under a matrix that never saw them."""
    if matrix is None:
        return float("nan")
    lines = rf.straight_template_lines()
    distances = []
    for i in VAL_LINES:
        supports = supports_along(starts[i], ends[i])
        pair = rf.apply_h(matrix, np.vstack((lines[i][0], lines[i][1])))
        coef = rf.line_coefficients(pair[:1], pair[1:])
        distances.append(np.abs(supports @ coef[0, :2] + coef[0, 2]))
    values = np.concatenate(distances)
    values = values[np.isfinite(values)]
    return float(np.median(values)) if len(values) else float("nan")


def one_draw(truth: np.ndarray, name: str, sigma: float, draw: int, prefix: str = "G365"):
    """One noise draw: the archived corner solve, then the refinement of that same solve."""
    seed = seed_of(name, sigma, draw, prefix)
    starts, ends = draw_lines(truth, sigma, seed)
    baseline = corner_solve(starts, ends)
    if baseline is None:
        return ([name, "%.2f" % sigma, draw, seed] + ["inf", "inf", "nan"] + [0, 0, 0]
                + ["no_corner_solve", "nan", "nan"], float("inf"), float("inf"))
    # The FIT lines only: no VALIDATION line ever reaches the refinement (contract B8).
    supports = np.concatenate([supports_along(starts[i], ends[i]) for i in FIT_LINES], axis=0)
    refined, stats = rf.refine_homography(baseline, supports)
    base_gap, ref_gap = _gap(truth, baseline), _gap(truth, refined)
    row = [name, "%.2f" % sigma, draw, seed, "%.6f" % base_gap, "%.6f" % ref_gap,
           "%.6f" % (base_gap - ref_gap), stats["n_supports"], stats["n_assigned"],
           stats["n_fev"], stats["status"],
           "%.6f" % val_median_px(baseline, starts, ends),
           "%.6f" % val_median_px(refined, starts, ends)]
    return row, base_gap, ref_gap


def _median(values: list) -> float:
    return float(np.median([v for v in values if np.isfinite(v)] or [float("inf")]))


def sweep(out: Path) -> int:
    """The four-geometry recovery and the sigma draws. `premise` must have run first."""
    path = out / "premise.json"
    if not path.exists():
        print("ABSENT %s: run `premise` first (Q8)" % path.as_posix())
        return 2
    cached = json.loads(path.read_text(encoding="ascii"))["geometries"]
    recovery, refined_h = [], {}
    for name, quad in GEOMETRIES:
        row, matrix = _recover(name, quad, cached[name])
        refined_h[name] = matrix.tolist() if matrix is not None else None
        if row is not None:
            recovery.append(row)
    rows, medians = [], {}
    for name, quad in GEOMETRIES:
        truth = geometry_matrix(quad)
        for sigma in SIGMAS:
            cells = [one_draw(truth, name, sigma, draw) for draw in range(DRAWS)]
            rows.extend(cell[0] for cell in cells)
            base = _median([cell[1] for cell in cells])
            refined = _median([cell[2] for cell in cells])
            medians["%s|%.2f" % (name, sigma)] = {
                "baseline_median_px": base, "refined_median_px": refined,
                "improvement_median_px": base - refined, "draws": DRAWS}
            print("SWEEP %s sigma=%.2f baseline_median=%.6f refined_median=%.6f px"
                  % (name, sigma, base, refined))
    _write(out / "recovery.csv", RECOVERY_COLS, recovery)
    _write(out / "sweep.csv", SWEEP_COLS, rows)
    (out / "refined_h.json").write_text(json.dumps(refined_h, indent=1) + "\n", encoding="ascii")
    _summary(out, cached, recovery, medians)
    return 0


def _summary(out: Path, cached: dict, recovery: list, medians: dict) -> None:
    """Every sealed constant, the two tables, and each bar clause evaluated separately."""
    refined_gaps = {row[0]: float(row[3]) for row in recovery}
    baseline_gaps = {row[0]: float(row[2]) for row in recovery}
    names = [name for name, _quad in GEOMETRIES]
    payload = {
        "row": "G365", "bar_px": BAR_PX, "sigmas": list(SIGMAS), "draws": DRAWS,
        "optimiser": rf.OPTIMISER, "huber_delta_px": rf.HUBER_DELTA_PX, "max_iter": rf.MAX_ITER,
        "tol": rf.TOL, "assign_max_px": rf.ASSIGN_MAX_PX, "min_assigned": rf.MIN_ASSIGNED,
        "support_spacing_px": st.SUPPORT_SPACING_PX,
        "versions": rf.VERSIONS,
        "premise": {name: cached[name]["baseline_gap_px"] for name in names},
        "recovery": {name: {"baseline_gap_px": baseline_gaps[name],
                            "refined_gap_px": refined_gaps[name]} for name in refined_gaps},
        "sweep_median_px": medians,
        "bar": {
            "refined_within_bar_all_geometries": (len(refined_gaps) == len(names)
                                                  and all(v <= BAR_PX
                                                          for v in refined_gaps.values())),
            "sigma_050_median_within_bar": all(medians["%s|0.50" % n]["refined_median_px"] <= BAR_PX
                                               for n in names),
            "exact_stays_zero": all(medians["%s|0.00" % n]["refined_median_px"] < 1e-6
                                    for n in names),
            "no_geometry_worsens": all(refined_gaps[n] <= baseline_gaps[n] for n in refined_gaps)},
        "verdict": "FINISHER WRITES THIS"}
    (out / "summary.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("WROTE %s" % (out / "summary.json").as_posix())


def render(out: Path) -> int:
    """Eight overlays: per geometry, the cached 4-corner winner and the refined matrix."""
    cached = json.loads((out / "premise.json").read_text(encoding="ascii"))["geometries"]
    refined = json.loads((out / "refined_h.json").read_text(encoding="ascii"))
    target = out / "renders"
    target.mkdir(parents=True, exist_ok=True)
    written = 0
    for name, quad in GEOMETRIES:
        frame, _scale = fv.to_base_height(synth.render_court(geometry_matrix(quad)))
        for label, matrix in (("baseline", cached[name]["image_matrix"]),
                              ("refined", refined.get(name))):
            if matrix is not None:
                written += int(gm.render_overlay(frame, np.asarray(matrix, dtype=float),
                                                 target / ("%s_%s.jpg" % (name, label))))
    print("RENDERS %s n=%d" % (target.as_posix(), written))
    return 0


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("premise", "sweep", "render"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])
    return {"premise": premise, "sweep": sweep, "render": render}[args.action](Path(args.out))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
