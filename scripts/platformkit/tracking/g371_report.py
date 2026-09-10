"""G371 controls, sensitivity, overlays and summary over the sweep the runner produced.

Every control is truth-free where the selector is: the planted, permutation and clone cases call
`select_from_scored` alone, and the truth appears only in the exact-line control.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("OMP_NUM_THREADS", "2")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from scripts.platformkit.tracking import g334_metrics as gm  # noqa: E402
from scripts.platformkit.tracking import g362_synth as synth  # noqa: E402
from scripts.platformkit.tracking import g365_sweep as sw  # noqa: E402
from scripts.platformkit.tracking import g371_run as run  # noqa: E402
from scripts.platformkit.tracking import g371_symmetry_margin as sel  # noqa: E402
from scripts.platformkit.tracking.g334_court_template import (  # noqa: E402
    TEMPLATE_POINTS, project, template_polylines,
)

cv2.setNumThreads(1)

PLANT_SEEDS = tuple(range(3710909, 3710939))
PLANT_SHIFT_PX = (10.0, 60.0)
PLANT_MARGIN_MAX = 0.099
EXACT_TOL_PX = 1e-6
RENDERS = 30
CONTROL_COLS = "control,geometry,seed,detail,expected,observed,outcome"
SENS_COLS = ("geometry,sigma_px,n_cells,n_probe_rows,probe_err_m_median,probe_err_m_p95,"
             "probe_err_modulo_m_median,probe_err_modulo_m_p95,budget_median_m,budget_p95_m,"
             "median_within_budget,p95_within_budget,aggregation")


def _read(path: Path) -> list:
    with path.open(encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def _scored(cell: dict) -> list:
    return [sel.ScoredCandidate(np.asarray(item["matrix"], dtype=float), item["objective_j"],
                                item["source_element"], item["enumeration_rank"])
            for item in cell["scored"]]


def _signature(selection) -> tuple:
    winner = None if selection.winner is None else tuple(
        np.round(selection.winner.matrix.ravel(), 9))
    return (selection.geometry_status, selection.margin,
            None if selection.winner is None else selection.winner.objective,
            None if selection.runner_up is None else selection.runner_up.objective, winner)


def _exact_rows() -> list:
    """Exact-line input recovers 0.000 px, and the sealed group arithmetic is exact."""
    rows = []
    for name, _quad in sw.GEOMETRIES:
        truth = run.truth_of(name)
        starts, ends = sw.draw_lines(truth, 0.0, 0)
        baseline = sw.corner_solve(starts, ends)
        gap = (float("inf") if baseline is None
               else synth.reprojection_median(truth, baseline, TEMPLATE_POINTS))
        rows.append({"control": "exact_line_input", "geometry": name, "seed": 0,
                     "detail": "sigma=0 projected endpoints, archived corner solve",
                     "expected": "0.000000", "observed": "%.6f" % gap,
                     "outcome": "PASS" if gap <= EXACT_TOL_PX else "FAIL"})
    value = sel.exact_modulo_gap(synth.known_matrix())
    rows.append({"control": "exact_group_arithmetic", "geometry": "KNOWN_H", "seed": 0,
                 "detail": "mirror_x image of the known homography, modulo gap",
                 "expected": "0.000000", "observed": "%.6f" % value,
                 "outcome": "PASS" if abs(value) <= EXACT_TOL_PX else "FAIL"})
    return rows


def _invariance_rows(clean: dict) -> list:
    """Shuffled candidate order and cloned candidates change nothing at all."""
    rows = []
    for name, _quad in sw.GEOMETRIES:
        items = _scored(clean["%s|0.00|000" % name])
        base = _signature(sel.select_from_scored(items))
        order = np.random.default_rng(PLANT_SEEDS[0]).permutation(len(items))
        shuffled = _signature(sel.select_from_scored([items[i] for i in order]))
        cloned = _signature(sel.select_from_scored(
            items + [sel.ScoredCandidate(item.matrix.copy(), item.objective, item.source_element,
                                         item.enumeration_rank + 100) for item in items]))
        for label, value in (("permutation_invariance", shuffled), ("clone_invariance", cloned)):
            rows.append({"control": label, "geometry": name, "seed": PLANT_SEEDS[0],
                         "detail": "n=%d candidates" % len(items), "expected": str(base),
                         "observed": str(value), "outcome": "PASS" if value == base else "FAIL"})
    return rows


def _plant_rows(clean: dict) -> list:
    """>= 30 planted distinct-class cases whose second class sits inside the sealed band."""
    rows, names = [], [name for name, _quad in sw.GEOMETRIES]
    for index, seed in enumerate(PLANT_SEEDS):
        name = names[index % len(names)]
        items = _scored(clean["%s|0.00|000" % name])
        winner = max(items, key=lambda item: item.objective)
        rng = np.random.default_rng(seed)
        planted = winner.matrix.copy()
        shift = rng.uniform(*PLANT_SHIFT_PX, size=2) * rng.choice([-1.0, 1.0], size=2)
        planted[0, 2] += shift[0]
        planted[1, 2] += shift[1]
        distinct = not sel.equivalent(planted, winner.matrix, TEMPLATE_POINTS, sel.SYM_EQ_PX)
        gap = float(rng.uniform(0.0, PLANT_MARGIN_MAX))
        second = sel.ScoredCandidate(planted, winner.objective - gap * abs(winner.objective),
                                     "planted", winner.enumeration_rank + 1)
        outcome = sel.select_from_scored([winner, second])
        refused = outcome.geometry_status == "REFUSED_MARGIN" and distinct
        rows.append({"control": "planted_ambiguity", "geometry": name, "seed": seed,
                     "detail": "distinct_class=%s planted_margin=%.6f" % (distinct, gap),
                     "expected": "REFUSED_MARGIN", "observed": "%s margin=%s"
                     % (outcome.geometry_status, outcome.margin),
                     "outcome": "PASS" if refused else "FAIL"})
    return rows


def _swap_rows(clean: dict) -> list:
    """The truth-swap test: selection is identical when the truth homography is replaced."""
    rows = []
    for name, _quad in sw.GEOMETRIES:
        items = _scored(clean["%s|0.00|000" % name])
        before = _signature(sel.select_from_scored(items))
        swapped = run.truth_of("G2_WIDE" if name != "G2_WIDE" else "G1_SYNTH_QUAD")
        evaluated = sel.selection_row(sel.select_from_scored(items), swapped)
        after = _signature(sel.select_from_scored(items))
        rows.append({"control": "truth_swap", "geometry": name, "seed": 0, "expected": str(before),
                     "detail": "swapped-truth modulo=%s" % evaluated["modulo_gap_px"],
                     "observed": str(after), "outcome": "PASS" if after == before else "FAIL"})
    return rows


def _sensitivity(out: Path, probes: list) -> list:
    """Pooled per-probe error per geometry and per geometry x sigma, in metres."""
    rows = []
    for name, _quad in sw.GEOMETRIES:
        for sigma in ("0.25", "0.50", "1.00", "ALL"):
            cells = [row for row in probes if row["geometry"] == name
                     and (row["sigma_px"] != "0.00" if sigma == "ALL"
                          else row["sigma_px"] == sigma)]
            if not cells:
                continue
            error = np.asarray([float(row["err_m"]) for row in cells])
            modulo = np.asarray([float(row["err_modulo_m"]) for row in cells])
            median, p95 = run._stats(error)
            mod_median, mod_p95 = run._stats(modulo)
            keys = {(row["sigma_px"], row["draw"]) for row in cells}
            rows.append({"geometry": name, "sigma_px": sigma, "n_cells": len(keys),
                         "n_probe_rows": len(cells), "probe_err_m_median": "%.6f" % median,
                         "probe_err_m_p95": "%.6f" % p95,
                         "probe_err_modulo_m_median": "%.6f" % mod_median,
                         "probe_err_modulo_m_p95": "%.6f" % mod_p95,
                         "budget_median_m": run.BUDGET_MEDIAN_M, "budget_p95_m": run.BUDGET_P95_M,
                         "median_within_budget": median <= run.BUDGET_MEDIAN_M,
                         "p95_within_budget": p95 <= run.BUDGET_P95_M,
                         "aggregation": "pooled_probe_rows"})
    run.write_csv(out / "sensitivity.csv", SENS_COLS, rows)
    return rows


def _overlay(frame: np.ndarray, cell: dict, path: Path) -> bool:
    """Truth in green, runner-up class in red, then the winner in the sealed yellow."""
    canvas = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame.copy()
    for key, colour in (("truth", (0, 255, 0)), ("runner_up", (0, 0, 255))):
        matrix = cell.get(key)
        if matrix is None:
            continue
        for polyline in template_polylines():
            points = project(np.asarray(matrix, dtype=float), polyline)
            if not np.isfinite(points).all() or np.abs(points).max() > 1e6:
                continue
            cv2.polylines(canvas, [np.round(points).astype(np.int32)], False, colour, 1,
                          cv2.LINE_AA)
    return gm.render_overlay(canvas, None if cell["winner"] is None
                             else np.asarray(cell["winner"], dtype=float), path)


def _renders(out: Path, sweep: list, matrices: dict) -> int:
    """Thirty overlays spaced EVENLY over the whole decision set, never a head slice (A3)."""
    keys = ["%s|%s|%03d" % (row["geometry"], row["sigma_px"], int(row["draw"])) for row in sweep]
    keys = sorted(set(keys))
    picks = [keys[int(round(i * (len(keys) - 1) / (RENDERS - 1)))] for i in range(RENDERS)]
    target = out / "renders"
    target.mkdir(parents=True, exist_ok=True)
    written = 0
    for key in sorted(set(picks)):
        name, sigma, draw = key.split("|")
        truth = run.truth_of(name)
        frame = run.noisy_frame(truth, float(sigma), run.seed_of(name, float(sigma), int(draw)))
        written += int(_overlay(frame, matrices[key],
                                target / ("%s_s%s_d%s.jpg" % (name, sigma, draw))))
    total = sum(path.stat().st_size for path in target.glob("*.jpg"))
    print("RENDERS n=%d bytes=%d dir=%s" % (written, total, target.as_posix()))
    return written


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report(out: Path) -> int:
    """Merge the shards, run every control, aggregate the sensitivity, render and summarise."""
    sweep = [row for path in sorted(out.glob("sweep_shard*.csv")) for row in _read(path)]
    run.write_csv(out / "sweep.csv", run.SEL_COLS, sweep)
    classes = [row for path in sorted(out.glob("sweep_classes_shard*.csv")) for row in _read(path)]
    classes = _read(out / "candidates.csv") + classes
    run.write_csv(out / "candidates.csv", run.CAND_COLS, classes)
    probes = [row for path in sorted(out.glob("probe_errors_shard*.csv")) for row in _read(path)]
    probes = _read(out / "probe_errors_clean.csv") + probes
    run.write_csv(out / "probe_errors.csv", run.PROBE_COLS, probes)
    matrices = {}
    for path in sorted(out.glob("matrices_shard*.json")) + [out / "matrices_clean.json"]:
        matrices.update(json.loads(path.read_text(encoding="ascii")))
    clean = json.loads((out / "matrices_clean.json").read_text(encoding="ascii"))
    controls = _exact_rows() + _swap_rows(clean) + _invariance_rows(clean) + _plant_rows(clean)
    run.write_csv(out / "ambiguity_controls.csv", CONTROL_COLS, controls)
    sensitivity = _sensitivity(out, probes)
    written = _renders(out, sweep, matrices)
    plants = [row for row in controls if row["control"] == "planted_ambiguity"]
    refused = sum(row["outcome"] == "PASS" for row in plants)
    statuses = sorted({row["geometry_status"] for row in sweep})
    passed = {kind: all(row["outcome"] == "PASS" for row in controls if row["control"] == kind)
              for kind in ("exact_line_input", "exact_group_arithmetic", "truth_swap",
                           "permutation_invariance", "clone_invariance")}
    payload = {
        "row": "G371", "modulo_form": sel.MODULO_FORM, "selected": _read(out / "selected.csv"),
        "sweep": {"n_cells": len(sweep), "n_cells_multi_class":
                  sum(int(row["n_classes"]) > 1 for row in sweep),
                  "status_counts": {status: sum(row["geometry_status"] == status for row in sweep)
                                    for status in statuses}},
        "controls": {**passed, "planted_total": len(plants), "planted_refused": refused,
                     "planted_refusal_share": refused / max(len(plants), 1)},
        "sensitivity": sensitivity, "renders_written": written,
        "budgets_m": {"median": run.BUDGET_MEDIAN_M, "p95": run.BUDGET_P95_M},
        "orientation_status": sel.ORIENTATION_UNKNOWN,
    }
    (out / "summary.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("SUMMARY %s" % json.dumps(payload["controls"]))
    return 0


def fixtures(out: Path) -> int:
    """The sealed fixture record: geometries, constants, seed rule, probes and budgets."""
    payload = {"row": "G371", "shape": list(synth.SYNTH_SHAPE), "line_px": run.LINE_PX,
               "sigmas": list(run.SIGMAS), "draws": run.DRAWS,
               "seed_rule": "int(sha256('G371|<geometry>|%.2f<sigma>|%03d<draw>')[:16], 16)",
               "sym_eq_px": sel.SYM_EQ_PX, "accept_margin": sel.ACCEPT_MARGIN,
               "margin_epsilon": sel.MARGIN_EPSILON, "modulo_form": sel.MODULO_FORM,
               "plant_seeds": [PLANT_SEEDS[0], PLANT_SEEDS[-1]],
               "probe_grid": {"x_ft": run.PROBE_X.tolist(), "y_ft": run.PROBE_Y.tolist(),
                              "n_probes": len(run.PROBES), "ft_to_m": run.FT_TO_M},
               "budgets_m": {"median": run.BUDGET_MEDIAN_M, "p95": run.BUDGET_P95_M},
               "geometries": {name: {"quad": [list(point) for point in quad],
                                     "truth": run.truth_of(name).tolist()}
                              for name, quad in sw.GEOMETRIES}}
    (out / "fixtures.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("WROTE %s" % (out / "fixtures.json").as_posix())
    return 0


def hashes(out: Path) -> int:
    """A11: the SHA-256 of every module exercised and of every artifact written."""
    here = Path(__file__).parent
    for name in ("g371_symmetry_margin.py g371_run.py g371_report.py g367_search.py g367_symmetry.py"
                 " g365_refine_b.py g365_sweep.py g362_fit_validate.py g362_strokes.py"
                 " g362_synth.py").split():
        print("SHA256 %s %s" % (name, _digest(here / name)[:16]))
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.suffix != ".jpg":
            print("SHA256 %s %s" % (path.name, _digest(path)[:16]))
    return 0


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("fixtures", "report", "hashes"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.command == "fixtures":
        return fixtures(out)
    if args.command == "hashes":
        return hashes(out)
    return report(out)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
