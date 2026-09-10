"""G371 finisher runner: the step-0 premise, the truth-free selection, and the noise sweep.

Selection never sees the truth homography: `g371_symmetry_margin.select_from_scored` ranks
class representatives by the FIT-only objective alone. The truth enters only in `_evaluate`,
after a winner exists, and only to SCORE it (labelled and modulo gap, contract B8).
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

from scripts.platformkit.tracking import g362_fit_validate as fv  # noqa: E402
from scripts.platformkit.tracking import g362_synth as synth  # noqa: E402
from scripts.platformkit.tracking import g365_sweep as sw  # noqa: E402
from scripts.platformkit.tracking import g367_search as g367  # noqa: E402
from scripts.platformkit.tracking import g367_symmetry as sym  # noqa: E402
from scripts.platformkit.tracking import g371_symmetry_margin as sel  # noqa: E402
from scripts.platformkit.tracking.g334_court_template import project, template_polylines  # noqa: E402

cv2.setNumThreads(1)

SIGMAS = (0.25, 0.50, 1.00)
DRAWS = 30
LINE_PX = 1
FT_TO_M = 0.3048
BUDGET_MEDIAN_M, BUDGET_P95_M = 0.25, 0.50
PROBE_X, PROBE_Y = np.linspace(0.0, 50.0, 11), np.linspace(0.0, 94.0, 17)
PROBES = np.asarray([(x, y) for y in PROBE_Y for x in PROBE_X], dtype=float)
PROBE_COLS = "geometry,sigma_px,draw,probe_index,err_m,err_modulo_m"
CAND_COLS = ("geometry,sigma_px,draw,symmetry_class,objective_j,source_element,enumeration_rank,"
             "candidate_hypotheses_count,deduplicated_symmetry_images_count")
SEL_COLS = ("geometry,sigma_px,draw,seed,n_candidates,n_classes,geometry_status,heldout_status,"
            "orientation_status,winner_objective_j,runner_up_objective_j,margin,labelled_gap_px,"
            "modulo_gap_px,modulo_form,attaining_element,probe_err_m_median,probe_err_m_p95,"
            "probe_err_modulo_m_median,probe_err_modulo_m_p95,n_probes_in_frame,"
            "candidate_hypotheses_count,deduplicated_symmetry_images_count")


def seed_of(name: str, sigma: float, draw: int) -> int:
    """The sealed content-addressed seed: sha256('G371|geometry|sigma|draw') truncated to 16 hex."""
    key = "G371|%s|%.2f|%03d" % (name, sigma, draw)
    return int(hashlib.sha256(key.encode("ascii")).hexdigest()[:16], 16)


def truth_of(name: str) -> np.ndarray:
    return sw.geometry_matrix(dict(sw.GEOMETRIES)[name])


def clean_frame(truth: np.ndarray) -> np.ndarray:
    """The painted synthetic court of G362 / G365 / G367, unchanged."""
    return fv.to_base_height(synth.render_court(truth))[0]


def noisy_frame(truth: np.ndarray, sigma: float, seed: int) -> np.ndarray:
    """`render_court` with G365's sealed jitter on the nine straight markings; arcs unjittered.

    The template, the one-pixel anti-aliased stroke and the sub-pixel shift are `render_court`'s,
    so the only difference from the clean fixture is the sealed endpoint noise itself.
    """
    starts, ends = sw.draw_lines(truth, sigma, seed)
    shape = synth.SYNTH_SHAPE
    canvas = np.full((shape[0], shape[1], 3), synth.FLOOR_VALUE, dtype=np.uint8)
    straight = 0
    for polyline in template_polylines():
        if len(polyline) == 2:
            points = np.vstack((starts[straight], ends[straight]))
            straight += 1
        else:
            points = project(truth, polyline)
        if not np.isfinite(points).all():
            continue
        scaled = np.round(points * 16.0).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [scaled], False, (synth.LINE_VALUE,) * 3, LINE_PX, cv2.LINE_AA,
                      shift=4)
    return fv.to_base_height(canvas)[0]


def probe_errors(truth: np.ndarray, candidate: np.ndarray, shape) -> tuple:
    """Per-probe mapped-foot error in metres; the denominator is the in-frame probe count."""
    image = project(np.asarray(truth, dtype=float), PROBES)
    height, width = shape[:2]
    keep = (np.isfinite(image).all(axis=1) & (image[:, 0] >= 0) & (image[:, 0] < width)
            & (image[:, 1] >= 0) & (image[:, 1] < height))
    index = np.flatnonzero(keep)
    if not len(index):
        return np.zeros(0), index
    try:
        inverse = np.linalg.inv(np.asarray(candidate, dtype=float))
    except np.linalg.LinAlgError:
        return np.full(len(index), np.nan), index
    back = project(inverse / inverse[2, 2], image[keep])
    return np.linalg.norm(back - PROBES[keep], axis=1) * FT_TO_M, index


def _stats(error: np.ndarray) -> tuple:
    finite = error[np.isfinite(error)]
    if not len(finite):
        return float("nan"), float("nan")
    return float(np.median(finite)), float(np.percentile(finite, 95))


def _status(selection, frame: np.ndarray) -> tuple:
    """`select_frame`'s sealed rule, kept separable so both fields are archived."""
    if selection.winner is None:
        return selection.geometry_status, "NO_WINNER"
    heldout = sel.heldout_status(selection.winner.matrix, frame)
    status = selection.geometry_status
    if status == "ACCEPT" and heldout != "VALID":
        status = heldout
    return status, heldout


def _evaluate(row: dict, selection, truth: np.ndarray, frame: np.ndarray) -> tuple:
    """Truth used ONLY here, after the winner is fixed: labelled gap, modulo gap, probe error."""
    row.update(sel.selection_row(selection, truth))
    if selection.winner is None:
        return row, []
    error, index = probe_errors(truth, selection.winner.matrix, frame.shape)
    element = next(item for item in sym.GROUP if item.name == row["attaining_element"])
    aligned = sym.compose(selection.winner.matrix, element)
    modulo, _index = probe_errors(truth, aligned, frame.shape)
    median, p95 = _stats(error)
    mod_median, mod_p95 = _stats(modulo)
    row.update({"probe_err_m_median": median, "probe_err_m_p95": p95,
                "probe_err_modulo_m_median": mod_median, "probe_err_modulo_m_p95": mod_p95,
                "n_probes_in_frame": len(index)})
    probes = [{"geometry": row["geometry"], "sigma_px": row["sigma_px"], "draw": row["draw"],
               "probe_index": int(where), "err_m": "%.6f" % error[position],
               "err_modulo_m": "%.6f" % modulo[position]}
              for position, where in enumerate(index)]
    return row, probes


def one_cell(name: str, sigma: float, draw: int) -> tuple:
    """One geometry/sigma/draw: enumerate, score FIT-only, select truth-free, then evaluate."""
    truth = truth_of(name)
    seed = 0 if sigma == 0.0 else seed_of(name, sigma, draw)
    frame = clean_frame(truth) if sigma == 0.0 else noisy_frame(truth, sigma, seed)
    scored, counts = sel.score_frame(frame)
    selection = sel.select_from_scored(scored)
    status, heldout = _status(selection, frame)
    classes = sel.class_rows(scored)
    row = {"geometry": name, "sigma_px": "%.2f" % sigma, "draw": draw, "seed": seed,
           "n_candidates": len(scored), "heldout_status": heldout, **counts,
           "n_classes": len({item["symmetry_class"] for item in classes})}
    row, probes = _evaluate(row, selection, truth, frame)
    row["geometry_status"] = status
    matrices = {"winner": None if selection.winner is None else selection.winner.matrix.tolist(),
                "runner_up": (None if selection.runner_up is None
                              else selection.runner_up.matrix.tolist()),
                "truth": truth.tolist()}
    if sigma == 0.0:
        matrices["scored"] = [{"objective_j": item.objective, "source_element": item.source_element,
                               "enumeration_rank": item.enumeration_rank,
                               "matrix": item.matrix.tolist()} for item in scored]
    for item in classes:
        item.update({"geometry": name, "sigma_px": "%.2f" % sigma, "draw": draw, **counts})
    return row, classes, matrices, probes


def write_csv(path: Path, header: str, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=header.split(","), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print("WROTE %s rows=%d" % (path.as_posix(), len(rows)))


def premise(out: Path) -> int:
    """Step 0: re-run G367's own search and print how ITS winner is chosen (Q8)."""
    target = out / "premise_g367"
    if g367.premise(target) != 0 or g367.search(target) != 0:
        print("PREMISE ABORTED: the G367 route refused")
        return 2
    source = Path(__file__).with_name("g367_search.py").read_text(encoding="ascii").splitlines()
    for number in (158, 160, 161, 167):
        print("TRUTH_CONSULT g367_search.py:%d %s" % (number, source[number - 1].strip()))
    rows = list(csv.DictReader((target / "search.csv").open(encoding="ascii")))
    distinct = 0
    for name, _quad in sw.GEOMETRIES:
        cells = [row for row in rows if row["geometry"] == name]
        classes = sorted({int(row["sym_class"]) for row in cells})
        margins = sorted({row["margin"] for row in cells})
        distinct += int(len(classes) > 1)
        print("PREMISE %s refined=%d sym_classes=%s margin=%s selectability=%s"
              % (name, len(cells), classes, margins,
                 cells[0]["selectability"] if cells else "NONE"))
    verdict = "FALSE" if distinct >= 3 else "TRUE"
    payload = {"truth_free_selection": False, "geometries_with_distinct_classes": distinct,
               "premise": verdict, "cited": "g367_search.py:158,160,161,167"}
    (out / "premise.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("PREMISE %s (selection consults the truth; distinct-class geometries=%d of 4)"
          % (verdict, distinct))
    return 2 if verdict == "FALSE" else 0


def select(out: Path) -> int:
    """The four clean geometries: the headline truth-free selection."""
    rows, classes, matrices, probes = [], [], {}, []
    for name, _quad in sw.GEOMETRIES:
        row, class_rows, cell, probe_rows = one_cell(name, 0.0, 0)
        rows.append(row)
        classes.extend(class_rows)
        probes.extend(probe_rows)
        matrices["%s|0.00|000" % name] = cell
        print("SELECT %s status=%s margin=%s labelled=%s modulo=%s (%s) classes=%d"
              % (name, row["geometry_status"], row["margin"], row["labelled_gap_px"],
                 row["modulo_gap_px"], row["attaining_element"], row["n_classes"]))
        sys.stdout.flush()
    write_csv(out / "selected.csv", SEL_COLS, rows)
    write_csv(out / "candidates.csv", CAND_COLS, classes)
    write_csv(out / "probe_errors_clean.csv", PROBE_COLS, probes)
    (out / "matrices_clean.json").write_text(json.dumps(matrices, indent=1) + "\n",
                                             encoding="ascii")
    return 0


def sweep(out: Path, shard: int, shards: int) -> int:
    """The sealed 4 x 3 x 30 noise sweep, sharded so the whole set finishes in one pass."""
    cells = [(name, sigma, draw) for name, _quad in sw.GEOMETRIES
             for sigma in SIGMAS for draw in range(DRAWS)]
    mine = [cell for index, cell in enumerate(cells) if index % shards == shard]
    rows, classes, matrices, probes = [], [], {}, []
    for name, sigma, draw in mine:
        row, class_rows, cell, probe_rows = one_cell(name, sigma, draw)
        rows.append(row)
        classes.extend(class_rows)
        probes.extend(probe_rows)
        matrices["%s|%.2f|%03d" % (name, sigma, draw)] = cell
        print("CELL %s sigma=%.2f draw=%d status=%s classes=%d modulo=%s"
              % (name, sigma, draw, row["geometry_status"], row["n_classes"],
                 row["modulo_gap_px"]))
        sys.stdout.flush()
    write_csv(out / ("sweep_shard%d.csv" % shard), SEL_COLS, rows)
    write_csv(out / ("sweep_classes_shard%d.csv" % shard), CAND_COLS, classes)
    write_csv(out / ("probe_errors_shard%d.csv" % shard), PROBE_COLS, probes)
    (out / ("matrices_shard%d.json" % shard)).write_text(json.dumps(matrices) + "\n",
                                                         encoding="ascii")
    return 0


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("premise", "select", "sweep"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.command == "premise":
        return premise(out)
    if args.command == "select":
        return select(out)
    return sweep(out, args.shard, args.shards)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
