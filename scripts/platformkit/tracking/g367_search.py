"""G367 premise, finite symmetry search, candidate-B refinement, and overlays."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("OMP_NUM_THREADS", "2")

import cv2
import numpy as np

from scripts.platformkit.tracking import g334_metrics as gm
from scripts.platformkit.tracking import g362_fit_validate as fv
from scripts.platformkit.tracking import g362_strokes as st
from scripts.platformkit.tracking import g362_synth as synth
from scripts.platformkit.tracking import g365_refine_b as rb
from scripts.platformkit.tracking import g365_sweep as sw
from scripts.platformkit.tracking import g365_sweep_b as sb
from scripts.platformkit.tracking import g367_symmetry as sym
from scripts.platformkit.tracking.g334_court_line_calibration import (
    ARM_A, enumerate_hypotheses, family_groups, gate, split_families,
)
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS, distance_transform

cv2.setNumThreads(1)
K, M, SYM_EQ_PX, AMBIG_BAND = 7, 8, 2.0, 0.005
RECOVERY_HEADER = ("geometry,arm,state,labelled_gap_px,identity_gap_px,mirror_x_gap_px,"
                   "rot180_gap_px,mirror_y_gap_px,modulo_gap_px,attaining_element")
SEARCH_HEADER = ("geometry,rank,source_element,score,refined_score,labelled_gap_px,"
                 "modulo_gap_px,attaining_element,sym_class,reachability,selectability,margin")


def _write(path: Path, header: str, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=header.split(","))
        writer.writeheader()
        writer.writerows(rows)


def _lengths(strokes: list) -> np.ndarray:
    return sb.support_lengths(strokes)


def _record(name: str, arm: str, state: str, truth, matrix) -> dict:
    value = sym.recovery_modulo_symmetry(truth, matrix, TEMPLATE_POINTS)
    return {"geometry": name, "arm": arm, "state": state,
            "labelled_gap_px": "%.6f" % value["labelled_gap_px"],
            **{"%s_gap_px" % key: "%.6f" % gap for key, gap in value["element_gaps_px"].items()},
            "modulo_gap_px": "%.6f" % value["modulo_gap_px"],
            "attaining_element": value["attaining_element"]}


def _recover(name: str, quad) -> tuple[list[dict], dict]:
    truth = sw.geometry_matrix(quad)
    frame, _scale = fv.to_base_height(synth.render_court(truth))
    decision = fv.decide(frame)
    rows, item = [], {"truth": truth, "frame": frame, "state": decision.state}
    if decision.image_matrix is None:
        return rows, item
    baseline = np.asarray(decision.image_matrix, dtype=float)
    rows.append(_record(name, "corner4", decision.state, truth, baseline))
    strokes = st.extract_strokes(frame)
    fit_strokes, _val_strokes = st.partition(strokes)
    refined, stats = rb.refine_b(baseline, st.support_array(fit_strokes), _lengths(fit_strokes))
    rows.append(_record(name, "candidate_b", decision.state, truth, refined))
    item.update({"baseline": baseline, "candidate_b": refined, "candidate_b_stats": stats})
    return rows, item


def premise(out: Path) -> int:
    """Re-measure the stated four-geometry premise before the search is allowed."""
    rows, cached = [], {}
    for name, quad in sw.GEOMETRIES:
        current, item = _recover(name, quad)
        rows.extend(current)
        cached[name] = item
        for row in current:
            print("PREMISE %s %s modulo=%s px element=%s" %
                  (name, row["arm"], row["modulo_gap_px"], row["attaining_element"]))
    _write(out / "recovery.csv", RECOVERY_HEADER, rows)
    false = len(rows) == 8 and all(float(row["modulo_gap_px"]) <= sw.BAR_PX
                                   for row in rows if row["arm"] == "candidate_b")
    payload = {"premise": "FALSE" if false else "TRUE", "bar_px": sw.BAR_PX,
               "recovery": rows, "candidate_b": {name: (item.get("candidate_b").tolist()
               if item.get("candidate_b") is not None else None) for name, item in cached.items()}}
    (out / "g367_premise.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("PREMISE %s" % payload["premise"])
    return 2 if false else 0


def _candidates(frame: np.ndarray) -> tuple[list[tuple[float, str, np.ndarray]], int, int, list, np.ndarray]:
    strokes = st.extract_strokes(frame)
    fit_strokes, _val_strokes = st.partition(strokes)
    segments = st.segments_of(fit_strokes)
    field = distance_transform(frame.shape, segments)
    first, second = split_families(segments, ARM_A)
    groups_a, groups_b = family_groups(first, ARM_A)[:K], family_groups(second, ARM_A)[:K]
    unique, total, valid = {}, 0, 0
    for groups_w, groups_l in ((groups_a, groups_b), (groups_b, groups_a)):
        for image_quad, court_quad in enumerate_hypotheses(groups_w, groups_l, ARM_A,
                                                           8.0 * max(frame.shape[:2])):
            total += 1
            base = cv2.getPerspectiveTransform(court_quad, image_quad)
            for element in sym.GROUP:
                matrix = sym.compose(base, element)
                key = tuple(np.round(matrix.ravel(), 6))
                if key in unique:
                    continue
                score, n_scored = fv.whole_template_score(matrix, field, ARM_A)
                if gate(matrix, score, n_scored, frame.shape, ARM_A) != "valid":
                    unique[key] = None
                    continue
                valid += 1
                unique[key] = (score, element.name, matrix)
    ranked = sorted((item for item in unique.values() if item is not None),
                    key=lambda item: (-item[0], item[1], tuple(np.round(item[2].ravel(), 6))))
    return ranked[:M], total, valid, fit_strokes, field


def _classes(matrices: list[np.ndarray]) -> list[int]:
    labels = []
    for matrix in matrices:
        same = next((index for index, prior in enumerate(matrices[:len(labels)])
                     if sym.equivalent(matrix, prior, TEMPLATE_POINTS, SYM_EQ_PX)), None)
        labels.append(len(labels) if same is None else labels[same])
    return labels


def selectability(margin: float | None) -> str:
    """Apply the sealed runner-up rule without moving the ambiguity band."""
    return "SELECTABLE" if margin is not None and margin > AMBIG_BAND else "AMBIGUOUS"


def search(out: Path) -> int:
    """Enumerate, rank, refine the sealed top M, and retain both selection questions."""
    premise_path = out / "g367_premise.json"
    if not premise_path.exists():
        print("ABSENT %s: run premise first" % premise_path.as_posix())
        return 2
    if json.loads(premise_path.read_text(encoding="ascii"))["premise"] == "FALSE":
        print("PREMISE FALSE: geometry search stops")
        return 2
    rows, winners, report = [], {}, {}
    for name, quad in sw.GEOMETRIES:
        truth = sw.geometry_matrix(quad)
        frame, _scale = fv.to_base_height(synth.render_court(truth))
        ranked, total, valid, fit_strokes, field = _candidates(frame)
        refined = []
        for score, source, matrix in ranked:
            value, _stats = rb.refine_b(matrix, st.support_array(fit_strokes), _lengths(fit_strokes))
            rescore, _n = fv.whole_template_score(value, field, ARM_A)
            refined.append((score, source, value, rescore, sym.recovery_modulo_symmetry(truth, value, TEMPLATE_POINTS)))
        classes = _classes([item[2] for item in refined])
        by_gap = sorted(range(len(refined)), key=lambda i: (refined[i][4]["modulo_gap_px"], -refined[i][3], i))
        winner = by_gap[0] if by_gap else None
        by_score = sorted(range(len(refined)), key=lambda i: (-refined[i][3], i))
        top = by_score[0] if by_score else None
        other = next((i for i in by_score if classes[i] != classes[top]), None) if top is not None else None
        margin = None if other is None else refined[top][3] - refined[other][3]
        selection = selectability(margin)
        reachability = "REACHED" if winner is not None and refined[winner][4]["modulo_gap_px"] <= sw.BAR_PX else "NOT_REACHED"
        for rank, (score, source, matrix, rescore, value) in enumerate(refined, start=1):
            rows.append({"geometry": name, "rank": rank, "source_element": source, "score": "%.9f" % score,
                         "refined_score": "%.9f" % rescore, "labelled_gap_px": "%.6f" % value["labelled_gap_px"],
                         "modulo_gap_px": "%.6f" % value["modulo_gap_px"], "attaining_element": value["attaining_element"],
                         "sym_class": classes[rank - 1], "reachability": reachability,
                         "selectability": selection, "margin": "" if margin is None else "%.9f" % margin})
        winners[name] = None if winner is None else refined[winner][2].tolist()
        report[name] = {"candidates": total, "gate_valid": valid, "refined": len(refined),
                        "reachability": reachability, "selectability": selection, "margin": margin}
        print("SEARCH %s candidates=%d valid=%d refined=%d %s/%s" %
              (name, total, valid, len(refined), reachability, selection))
    _write(out / "search.csv", SEARCH_HEADER, rows)
    (out / "g367_search.json").write_text(json.dumps({"winners": winners, "report": report}, indent=1) + "\n", encoding="ascii")
    recovery = json.loads((out / "g367_premise.json").read_text(encoding="ascii"))["recovery"]
    prior = {row["geometry"]: float(row["modulo_gap_px"]) for row in recovery
             if row["arm"] == "candidate_b"}
    winner_gap = {name: min((float(row["modulo_gap_px"]) for row in rows if row["geometry"] == name),
                            default=float("inf")) for name, _quad in sw.GEOMETRIES}
    payload = {"geometry": {"bar_px": sw.BAR_PX, "k": K, "m": M, "sym_eq_px": SYM_EQ_PX,
                            "ambiguity_band": AMBIG_BAND, "report": report,
                            "bar_all_within": all(value <= sw.BAR_PX for value in winner_gap.values()),
                            "no_worsening_vs_candidate_b": all(winner_gap[name] <= prior[name]
                                                                  for name in winner_gap)}}
    (out / "summary.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    return 0


def render(out: Path) -> int:
    """Write the required labelled and modulo overlays only after a completed search."""
    values = json.loads((out / "g367_search.json").read_text(encoding="ascii"))["winners"]
    target, written = out / "renders", 0
    target.mkdir(parents=True, exist_ok=True)
    for name, quad in sw.GEOMETRIES:
        winner = values.get(name)
        if winner is None:
            continue
        truth = sw.geometry_matrix(quad)
        frame, _scale = fv.to_base_height(synth.render_court(truth))
        matrix = np.asarray(winner, dtype=float)
        element = sym.recovery_modulo_symmetry(truth, matrix, TEMPLATE_POINTS)["attaining_element"]
        written += int(gm.render_overlay(frame, matrix, target / (name + "_labelled.jpg")))
        written += int(gm.render_overlay(frame, sym.compose(truth, next(x for x in sym.GROUP if x.name == element)),
                                        target / (name + "_modulo.jpg")))
    print("RENDERS %s n=%d" % (target.as_posix(), written))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("premise", "search", "render"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])
    return {"premise": premise, "search": search, "render": render}[args.action](Path(args.out))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
