"""G365 attempt-2 runner: the premise re-run, the PAIRED baseline/A/B tables, and the B overlays.

Every constant is sealed in `g365_fitter_refinement_2026-09-09/g365_prereg_att2_2026-09-09.md`. The
four geometries, the sigma set, the bar and the seed formula are attempt 1's, imported from
`g365_sweep` rather than restated, so a bar cannot drift between the two attempts; only the seed
PREFIX changes, to `G365B`, so no attempt-2 draw can be an attempt-1 draw.

On every draw the archived corner solve, candidate A and candidate B run on the SAME noisy lines, so
the A-vs-B comparison is paired rather than two independent samplings. Attempt 1's own committed
medians are re-reported in the memo beside these and are not re-run here.
"""
from __future__ import annotations

import argparse
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
from scripts.platformkit.tracking import g365_refine_b as rb  # noqa: E402
from scripts.platformkit.tracking import g365_sweep as sw  # noqa: E402

cv2.setNumThreads(1)

PREFIX_B = "G365B"
DRAWS_B = 40
RECOVERY_COLS = ("geometry,state,init_fail,baseline_gap_px,a_gap_px,b_gap_px,a_improvement_px,"
                 "b_improvement_px,bar_px,n_strokes,n_fit_strokes,n_val_strokes,n_supports,n_kept,"
                 "rounds_run,n_fev,status,base_val_forward_px,base_val_inverse_px,"
                 "b_val_forward_px,b_val_inverse_px")
SWEEP_COLS = ("geometry,sigma_px,draw,seed,baseline_gap_px,a_gap_px,b_gap_px,a_improvement_px,"
              "b_improvement_px,n_supports,n_kept,rounds_run,n_fev,status")


def support_lengths(strokes: list) -> np.ndarray:
    """One parent-stroke pixel length per support point, in `support_array` order."""
    if not strokes:
        return np.zeros(0, dtype=float)
    return np.concatenate([np.full(len(s.supports), float(s.length), dtype=float)
                           for s in strokes])


def premise(out: Path) -> int:
    """Re-run G362's known-H path on the four sealed geometries and compare with attempt 1."""
    prior = {}
    path = out / "premise.json"
    if path.exists():
        prior = json.loads(path.read_text(encoding="ascii"))["geometries"]
    rows, reproduces = {}, {}
    for name, quad in sw.GEOMETRIES:
        truth = sw.geometry_matrix(quad)
        decision = fv.decide(synth.render_court(truth))
        gap = sw._gap(truth, decision.image_matrix)
        flag = rb.init_fail(decision.state, gap)
        rows[name] = {
            "quad": [[float(v) for v in point] for point in quad], "state": decision.state,
            "reason": decision.reason, "baseline_gap_px": round(gap, 4), "bar_px": sw.BAR_PX,
            "init_fail": bool(flag), "forward_median_px": round(decision.forward_median, 4),
            "inverse_median_px": round(decision.inverse_median, 4), "n_strokes": decision.n_strokes,
            "n_val_points": decision.n_val_points, "n_hypotheses": decision.n_hypotheses,
            "image_matrix": (decision.image_matrix.tolist()
                             if decision.image_matrix is not None else None)}
        if name in prior:
            reproduces[name] = {
                "attempt1_gap_px": prior[name]["baseline_gap_px"],
                "attempt2_gap_px": round(gap, 4),
                "delta_px": round(gap - float(prior[name]["baseline_gap_px"]), 6),
                "state_matches": prior[name]["state"] == decision.state}
            print("REPRODUCE %s attempt1=%.4f attempt2=%.4f delta=%.6f px state_matches=%s"
                  % (name, prior[name]["baseline_gap_px"], gap, reproduces[name]["delta_px"],
                     reproduces[name]["state_matches"]))
        print("PREMISE %s %s gap=%.4f bar=%.1f px init_fail=%s"
              % (name, decision.state, gap, sw.BAR_PX, flag))
    inside = all(row["baseline_gap_px"] <= sw.BAR_PX for row in rows.values())
    payload = {"row": "G365", "attempt": 2, "bar_px": sw.BAR_PX,
               "init_fail_px": rb.INIT_FAIL_PX, "premise": "FALSE" if inside else "TRUE",
               "reproduces_attempt1": reproduces, "geometries": rows}
    out.mkdir(parents=True, exist_ok=True)
    (out / "premise_b.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("PREMISE %s -- FALSE means every geometry already recovers within the bar: STOP"
          % payload["premise"])
    return 2 if inside else 0


def _recover(name: str, quad, cached: dict):
    """Both candidates on the SAME cached 4-corner winner and the same FIT supports."""
    truth = sw.geometry_matrix(quad)
    frame, _scale = fv.to_base_height(synth.render_court(truth))
    strokes = st.extract_strokes(frame)
    fit_strokes, val_strokes = st.partition(strokes)
    fit_supports = st.support_array(fit_strokes)
    val_supports = st.support_array(val_strokes)
    if cached["image_matrix"] is None:
        print("SKIP %s: the premise left no 4-corner winner to refine" % name)
        return None, None
    baseline = np.asarray(cached["image_matrix"], dtype=float)
    a_matrix, _a_stats = rf.refine_homography(baseline, fit_supports)
    b_matrix, b_stats = rb.refine_b(baseline, fit_supports, support_lengths(fit_strokes))
    base_gap = sw._gap(truth, baseline)
    a_gap, b_gap = sw._gap(truth, a_matrix), sw._gap(truth, b_matrix)
    flag = rb.init_fail(cached["state"], base_gap)
    base_val = fv.bidirectional(baseline, val_supports, frame.shape)
    b_val = fv.bidirectional(b_matrix, val_supports, frame.shape)
    row = [name, "INIT_FAIL" if flag else cached["state"], int(flag), "%.4f" % base_gap,
           "%.4f" % a_gap, "%.4f" % b_gap, "%.4f" % (base_gap - a_gap), "%.4f" % (base_gap - b_gap),
           sw.BAR_PX, len(strokes), len(fit_strokes), len(val_strokes), b_stats["n_supports"],
           b_stats["n_kept"], b_stats["rounds_run"], b_stats["n_fev"], b_stats["status"],
           "%.4f" % float(np.median(base_val[0])), "%.4f" % float(np.median(base_val[1])),
           "%.4f" % float(np.median(b_val[0])), "%.4f" % float(np.median(b_val[1]))]
    print("RECOVER %s baseline=%.4f A=%.4f B=%.4f px rounds=%d kept=%d status=%s init_fail=%s"
          % (name, base_gap, a_gap, b_gap, b_stats["rounds_run"], b_stats["n_kept"],
             b_stats["status"], flag))
    return row, b_matrix


def one_draw(truth: np.ndarray, name: str, sigma: float, draw: int, prefix: str = PREFIX_B):
    """One noise draw: the archived corner solve, then candidate A and candidate B on it."""
    seed = sw.seed_of(name, sigma, draw, prefix)
    starts, ends = sw.draw_lines(truth, sigma, seed)
    baseline = sw.corner_solve(starts, ends)
    if baseline is None:
        return ([name, "%.2f" % sigma, draw, seed] + ["inf"] * 5 + [0, 0, 0, 0, "no_corner_solve"],
                float("inf"), float("inf"), float("inf"))
    chunks = [sw.supports_along(starts[i], ends[i]) for i in sw.FIT_LINES]
    supports = np.concatenate(chunks, axis=0)
    lengths = np.concatenate([np.full(len(chunk), float(np.linalg.norm(ends[i] - starts[i])))
                              for i, chunk in zip(sw.FIT_LINES, chunks)])
    a_matrix, _a_stats = rf.refine_homography(baseline, supports)
    b_matrix, b_stats = rb.refine_b(baseline, supports, lengths)
    base_gap = sw._gap(truth, baseline)
    a_gap, b_gap = sw._gap(truth, a_matrix), sw._gap(truth, b_matrix)
    row = [name, "%.2f" % sigma, draw, seed, "%.6f" % base_gap, "%.6f" % a_gap, "%.6f" % b_gap,
           "%.6f" % (base_gap - a_gap), "%.6f" % (base_gap - b_gap), b_stats["n_supports"],
           b_stats["n_kept"], b_stats["rounds_run"], b_stats["n_fev"], b_stats["status"]]
    return row, base_gap, a_gap, b_gap


def sweep(out: Path) -> int:
    """The four-geometry paired recovery and the sigma draws. `premise` must have run first."""
    path = out / "premise_b.json"
    if not path.exists():
        print("ABSENT %s: run `premise` first (Q8)" % path.as_posix())
        return 2
    cached = json.loads(path.read_text(encoding="ascii"))["geometries"]
    recovery, refined_h = [], {}
    for name, quad in sw.GEOMETRIES:
        row, matrix = _recover(name, quad, cached[name])
        refined_h[name] = matrix.tolist() if matrix is not None else None
        if row is not None:
            recovery.append(row)
    rows, medians = [], {}
    for name, quad in sw.GEOMETRIES:
        truth = sw.geometry_matrix(quad)
        for sigma in sw.SIGMAS:
            cells = [one_draw(truth, name, sigma, draw) for draw in range(DRAWS_B)]
            rows.extend(cell[0] for cell in cells)
            base = sw._median([cell[1] for cell in cells])
            a_med = sw._median([cell[2] for cell in cells])
            b_med = sw._median([cell[3] for cell in cells])
            medians["%s|%.2f" % (name, sigma)] = {
                "baseline_median_px": base, "a_median_px": a_med, "b_median_px": b_med,
                "b_improvement_median_px": base - b_med, "draws": DRAWS_B}
            print("SWEEP %s sigma=%.2f baseline=%.6f A=%.6f B=%.6f px"
                  % (name, sigma, base, a_med, b_med))
    sw._write(out / "recovery_b.csv", RECOVERY_COLS, recovery)
    sw._write(out / "sweep_b.csv", SWEEP_COLS, rows)
    (out / "refined_h_b.json").write_text(json.dumps(refined_h, indent=1) + "\n", encoding="ascii")
    _summary(out, cached, recovery, medians)
    return 0


def _summary(out: Path, cached: dict, recovery: list, medians: dict) -> None:
    """Every sealed constant, the paired tables, and each bar clause evaluated separately.

    Fix 1d correction: the amendment INIT_FAIL carve-out is sealed but not applied to any bar --
    all four bar clauses are evaluated over all four geometries (`names`), G2_WIDE included.
    """
    names = [name for name, _quad in sw.GEOMETRIES]
    flagged = {row[0] for row in recovery if int(row[2]) == 1}
    base_gaps = {row[0]: float(row[3]) for row in recovery}
    b_gaps = {row[0]: float(row[5]) for row in recovery}
    payload = {
        "row": "G365", "attempt": 2, "candidate": "B", "bar_px": sw.BAR_PX,
        "sigmas": list(sw.SIGMAS), "draws": DRAWS_B, "seed_prefix": PREFIX_B,
        "optimiser": rb.OPTIMISER_B, "huber_delta_px": rb.HUBER_DELTA_B_PX,
        "band_px": rb.BAND_B_PX, "rounds": rb.ROUNDS_B, "conv_px": rb.CONV_B_PX,
        "weight_clip": list(rb.WEIGHT_CLIP), "init_fail_px": rb.INIT_FAIL_PX,
        "max_iter": rf.MAX_ITER, "tol": rf.TOL, "assign_max_px": rf.ASSIGN_MAX_PX,
        "min_assigned": rf.MIN_ASSIGNED, "support_spacing_px": st.SUPPORT_SPACING_PX,
        "versions": rf.VERSIONS,
        "premise": {name: cached[name]["baseline_gap_px"] for name in names},
        "init_fail": sorted(flagged),
        "recovery": {row[0]: {"baseline_gap_px": float(row[3]), "a_gap_px": float(row[4]),
                              "b_gap_px": float(row[5]), "init_fail": bool(int(row[2]))}
                     for row in recovery},
        "sweep_median_px": medians,
        "bar": {
            "b_within_bar_all_four": all(b_gaps[n] <= sw.BAR_PX for n in names),
            "sigma_050_median_within_bar": all(medians["%s|0.50" % n]["b_median_px"] <= sw.BAR_PX
                                               for n in names),
            "exact_stays_zero": all(medians["%s|0.00" % n]["b_median_px"] < 1e-6 for n in names),
            "no_geometry_worsens": all(b_gaps[n] <= base_gaps[n] for n in names)},
        "verdict": "FINISHER WRITES THIS"}
    (out / "summary_b.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("WROTE %s" % (out / "summary_b.json").as_posix())


def render(out: Path) -> int:
    """Overlays: per geometry, the cached 4-corner winner and candidate B's matrix."""
    cached = json.loads((out / "premise_b.json").read_text(encoding="ascii"))["geometries"]
    refined = json.loads((out / "refined_h_b.json").read_text(encoding="ascii"))
    target = out / "renders_b"
    target.mkdir(parents=True, exist_ok=True)
    written = 0
    for name, quad in sw.GEOMETRIES:
        frame, _scale = fv.to_base_height(synth.render_court(sw.geometry_matrix(quad)))
        for label, matrix in (("baseline", cached[name]["image_matrix"]),
                              ("candidate_b", refined.get(name))):
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
