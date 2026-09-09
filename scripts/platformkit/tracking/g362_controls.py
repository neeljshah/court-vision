"""G362 runner: the known-H build gate, the negative controls, the positives loop, and the writers.

Sealed rules this file implements verbatim from `g362_prereg_2026-09-09.md`:
  * section 2  -- the known-H recovery gate runs FIRST and its failure stops the row at PARTIAL;
  * section 5  -- both negative arms (RAW and CASCADE) on an EVEN interior frame sample;
  * section 6  -- positives, 60 evenly spaced frames per section, per-point residuals archived.

No sampling here is a head slice (contract A3, B7) and no draw is random (prereg section 11). The
module writes ONLY under the evidence directory it is given; it never writes `data/`, the register
or the results ledger, and it never scores anything the caller did not name in `sections.csv`.

sections.csv columns: key,path,role,video_id,start_s,video_sha256,bytes,width,height
  role in {POSITIVE, NEGATIVE, HISTORICAL}. A row whose video_id is empty is UNKNOWN under G361 and
  is skipped with a printed reason: an NBA game id alone is not a source.
"""
from __future__ import annotations

import argparse
import csv
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
from scripts.platformkit.tracking import g362_synth as synth  # noqa: E402
from scripts.platformkit.tracking.g334_court_line_calibration import ARM_A, ARM_B  # noqa: E402
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS  # noqa: E402

cv2.setNumThreads(1)

POSITIVE_FRAMES = 60
NEGATIVE_TARGET = 200
RENDER_COUNT = 30
KNOWN_H_BAR_PX = 1.0
ARMS = {"A": ARM_A, "B": ARM_B}

DECISION_COLS = ("key,role,arm,frame_index,state,reason,n_strokes,n_fit_strokes,n_val_strokes,"
                 "n_val_families,n_val_points,n_inframe,n_penalty,forward_median,inverse_median,"
                 "score,n_hypotheses,scale")
METRIC_COLS = ("key,role,arm,n_frames,n_valid,valid_share,n_refused,n_no_lines,n_no_validation,"
               "feet_total,feet_inside,feet_inside_share,forward_median_px,inverse_median_px,"
               "n_forward_points")
RESIDUAL_COLS = "key,arm,frame_index,direction,point_index,distance_px,in_frame"


def even_indices(total: int, count: int) -> list:
    """floor((k + 0.5) * total / count) -- an interior sample, never a head slice."""
    if total <= 0 or count <= 0:
        return []
    return sorted({min(total - 1, int((k + 0.5) * total / count)) for k in range(count)})


def read_sections(path: Path, role: str) -> list:
    rows = []
    with path.open("r", encoding="ascii", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("role", "").strip().upper() != role:
                continue
            if not row.get("video_id", "").strip():
                print("SKIP %s UNKNOWN source: no video id (a game id alone is not a source)"
                      % row.get("key", "?"))
                continue
            rows.append(row)
    return rows


def decode(path: Path, indices: list):
    """Yield (index, frame) for the named indices in one forward pass."""
    capture = cv2.VideoCapture(str(path))
    wanted, index = set(indices), 0
    try:
        while wanted:
            ok, frame = capture.read()
            if not ok:
                break
            if index in wanted:
                wanted.discard(index)
                yield index, frame
            index += 1
    finally:
        capture.release()


def frame_count(path: Path) -> int:
    capture = cv2.VideoCapture(str(path))
    try:
        return int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        capture.release()


def _row(key: str, role: str, arm: str, index: int, decision) -> list:
    return [key, role, arm, "%06d" % index, decision.state, decision.reason,
            "%06d" % decision.n_strokes, "%06d" % decision.n_fit_strokes,
            "%06d" % decision.n_val_strokes, "%06d" % decision.n_val_families,
            "%06d" % decision.n_val_points, "%06d" % decision.n_inframe,
            "%06d" % decision.n_penalty, "%.3f" % decision.forward_median,
            "%.3f" % decision.inverse_median, "%.6f" % decision.score,
            "%06d" % decision.n_hypotheses, "%.4f" % decision.scale]


def _write(path: Path, header: str, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write(header + "\n")
        for row in rows:
            handle.write(",".join(str(cell) for cell in row) + "\n")
    print("WROTE %s rows=%06d" % (path.as_posix(), len(rows)))


def _residual_rows(key: str, arm: str, index: int, decision) -> list:
    rows = []
    for i, distance in enumerate(decision.forward):
        in_frame = 1 if distance < fv.PENALTY_PX else 0
        rows.append([key, arm, "%06d" % index, "forward", "%06d" % i, "%.3f" % distance, in_frame])
    for i, distance in enumerate(decision.inverse):
        rows.append([key, arm, "%06d" % index, "inverse", "%06d" % i, "%.3f" % distance, 1])
    return rows


def known_h(out: Path) -> int:
    """BUILD GATE: recover the fixture's known H through the DETECTED-line path. Runs FIRST."""
    truth = synth.known_matrix()
    image = synth.render_court(truth)
    decision = fv.decide(image)
    gap = (synth.reprojection_median(truth, decision.image_matrix, TEMPLATE_POINTS)
           if decision.image_matrix is not None else float("inf"))
    passed = decision.state == fv.STATE_VALID and gap <= KNOWN_H_BAR_PX
    payload = {"state": decision.state, "reason": decision.reason,
               "reprojection_median_px": round(gap, 4), "bar_px": KNOWN_H_BAR_PX,
               "n_strokes": decision.n_strokes, "n_val_strokes": decision.n_val_strokes,
               "n_val_points": decision.n_val_points, "n_hypotheses": decision.n_hypotheses,
               "forward_median_px": round(decision.forward_median, 4),
               "inverse_median_px": round(decision.inverse_median, 4),
               "verdict": "PASS" if passed else "PARTIAL"}
    out.mkdir(parents=True, exist_ok=True)
    (out / "known_h.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("KNOWN_H %s gap=%.4f px bar=%.1f px -> %s"
          % (decision.state, gap, KNOWN_H_BAR_PX, payload["verdict"]))
    return 0 if passed else 1


def _load_feet(model, frame):
    if model is None:
        return []
    from scripts.platformkit.tracking.g330_panorama_identity import feet_from_boxes
    result = list(model(frame, classes=[0], conf=0.3, verbose=False, imgsz=640,
                        device="cpu", stream=True))[0]
    boxes = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else []
    return feet_from_boxes(boxes, frame.shape)


def _model(path: str | None):
    if not path:
        print("NOTE no detector given: feet cells are NOT VERIFIED in this run")
        return None
    from ultralytics import YOLO
    return YOLO(path)


def negatives(sections: list, out: Path, role: str) -> int:
    """Both arms on an even interior sample. RAW is reported for contrast, CASCADE carries the bar."""
    per_section = max(1, -(-NEGATIVE_TARGET // max(1, len(sections))))
    rows, accepts, raw_accepts, total = [], 0, 0, 0
    for section in sections:
        path = Path(section["path"])
        indices = even_indices(frame_count(path), per_section)
        for index, frame in decode(path, indices):
            decision = fv.decide(frame)
            rows.append(_row(section["key"], role, "CASCADE", index, decision))
            accepts += int(decision.accepted)
            matrix, n_hyp, score, scale = fv.raw_argmax(frame)
            rows.append([section["key"], role, "RAW", "%06d" % index,
                         fv.STATE_VALID if matrix is not None else fv.STATE_REFUSED,
                         "argmax_ungated", "%06d" % decision.n_strokes, "000000", "000000",
                         "000000", "000000", "000000", "000000", "nan", "nan",
                         "%.6f" % score, "%06d" % n_hyp, "%.4f" % scale])
            raw_accepts += int(matrix is not None)
            total += 1
    name = "negative_decisions.csv" if role == "NEGATIVE" else "premise_decisions.csv"
    _write(out / name, DECISION_COLS, rows)
    print("NEGATIVES role=%s frames=%06d cascade_accepts=%06d raw_accepts=%06d sections=%06d"
          % (role, total, accepts, raw_accepts, len(sections)))
    return accepts


def positives(sections: list, out: Path, model_path: str | None) -> None:
    """Six-plus court sections, 60 evenly spaced frames each, every per-point residual archived."""
    model = _model(model_path)
    decisions, residuals, metrics, homographies, renders = [], [], [], {}, []
    for section in sections:
        path = Path(section["path"])
        indices = even_indices(frame_count(path), POSITIVE_FRAMES)
        tally = {"n": 0, "valid": 0, "refused": 0, "no_lines": 0, "no_validation": 0,
                 "feet": 0, "inside": 0}
        forward, inverse = [], []
        for index, frame in decode(path, indices):
            decision = fv.decide(frame)
            tally["n"] += 1
            tally[{"VALID": "valid", "REFUSED": "refused", "NO_LINES": "no_lines",
                   "NO_VALIDATION": "no_validation"}[decision.state]] += 1
            decisions.append(_row(section["key"], "POSITIVE", "CASCADE", index, decision))
            if decision.state in (fv.STATE_VALID, fv.STATE_REFUSED) and len(decision.forward):
                residuals.extend(_residual_rows(section["key"], "CASCADE", index, decision))
                forward.extend(decision.forward.tolist())
                inverse.extend(decision.inverse.tolist())
            if decision.accepted:
                feet = _load_feet(model, frame)
                tally["feet"] += len(feet)
                points = gm.court_points(decision.court_matrix, feet)
                tally["inside"] += gm.inside_count(points) if len(points) else 0
                key = "%s|%06d" % (section["key"], index)
                homographies[key] = {
                    "image": decision.image_matrix.tolist(),
                    "court": decision.court_matrix.tolist(),
                    "n_penalty": decision.n_penalty, "n_inframe": decision.n_inframe,
                    "foot_spread_p95_ft": fv.foot_spread_p95_ft(decision.court_matrix, feet, key)}
                renders.append((key, frame, decision.image_matrix))
        metrics.append([
            section["key"], "POSITIVE", "CASCADE", "%06d" % tally["n"], "%06d" % tally["valid"],
            "%.4f" % (tally["valid"] / tally["n"] if tally["n"] else float("nan")),
            "%06d" % tally["refused"], "%06d" % tally["no_lines"], "%06d" % tally["no_validation"],
            "%06d" % tally["feet"], "%06d" % tally["inside"],
            "%.4f" % (tally["inside"] / tally["feet"] if tally["feet"] else float("nan")),
            "%.3f" % (float(np.median(forward)) if forward else float("nan")),
            "%.3f" % (float(np.median(inverse)) if inverse else float("nan")),
            "%06d" % len(forward)])
    _write(out / "metrics.csv", METRIC_COLS, metrics)
    _write(out / "residuals.csv", RESIDUAL_COLS, residuals)
    _write(out / "decisions.csv", DECISION_COLS, decisions)
    (out / "H.json").write_text(json.dumps(homographies, indent=1) + "\n", encoding="ascii")
    _renders(renders, out / "renders")


def _renders(items: list, out: Path) -> None:
    """RENDER_COUNT evenly spaced over the decision set -- never the first frames (A3, B7)."""
    if not items:
        return
    out.mkdir(parents=True, exist_ok=True)
    for position in even_indices(len(items), RENDER_COUNT):
        key, frame, matrix = items[position]
        gm.render_overlay(frame, matrix, out / ("%s.jpg" % key.replace("|", "_")))
    print("RENDERS %s n=%06d" % (out.as_posix(), min(len(items), RENDER_COUNT)))


def summary(out: Path, payload: dict) -> None:
    (out / "summary.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("WROTE %s" % (out / "summary.json").as_posix())


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("known-h", "premise", "negatives", "positives"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--sections")
    parser.add_argument("--model")
    args = parser.parse_args(argv[1:])
    out = Path(args.out)
    if args.action == "known-h":
        return known_h(out)
    if not args.sections:
        parser.error("--sections is required for %s" % args.action)
    role = {"premise": "HISTORICAL", "negatives": "NEGATIVE", "positives": "POSITIVE"}[args.action]
    sections = read_sections(Path(args.sections), role)
    if not sections:
        print("ABSENT no %s section is readable: reporting NOT VERIFIED, not a stop" % role)
        summary(out, {"action": args.action, "role": role, "verdict": "NOT VERIFIED",
                      "reason": "no readable section"})
        return 0
    if args.action == "positives":
        positives(sections, out, args.model)
        summary(out, {"action": args.action, "role": role, "sections": len(sections),
                      "frames_per_section": POSITIVE_FRAMES})
    else:
        accepts = negatives(sections, out, role)
        summary(out, {"action": args.action, "role": role, "sections": len(sections),
                      "cascade_accepts": accepts})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
