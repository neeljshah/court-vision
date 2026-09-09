"""G352 driver: the premise recomputation, the sealed sections, the arms and the CSV artifacts.

Usage:
    python -m scripts.platformkit.tracking.g352_run section <workdir> <evidence> <A|B|ROUTE>         <key> [shard] [n_shards] [keep_every]

The premise recomputation lives in `g352_premise.py`.

One process per section and arm. The ROUTE arm is scored inside the ARM_A process only, against
the SAME held-out supports the G352 arms see, so G334's finding that a denser held-out set buys a
lower forward error cannot repeat here. The five-frame shot-median smoothing of `g334_run.py` is
NOT applied: this row fits each sealed evaluation frame on its own, which is why its cells are not
byte-comparable to G334's. Nothing outside <evidence_dir> is written.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("COURTV_NO_LOFTR", "1")
os.environ.setdefault("OMP_NUM_THREADS", "2")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from scripts.platformkit.tracking import g334_court_line_calibration as gc  # noqa: E402
from scripts.platformkit.tracking import g334_court_template as gt  # noqa: E402
from scripts.platformkit.tracking import g334_metrics as gm  # noqa: E402
from scripts.platformkit.tracking import g352_cells as cells  # noqa: E402
from scripts.platformkit.tracking import g352_whole_template_objective as g352  # noqa: E402
from scripts.platformkit.tracking.g330_attempt2 import (  # noqa: E402
    ArmTally, MatchRecorder, eval_indices, make_arm, step_arm,
)
from scripts.platformkit.tracking.g330_panorama_identity import (  # noqa: E402
    feet_from_boxes, pad6, route, sha256_of,
)

N_EVAL = 60
ARM_POSITION = {"A": 0, "B": 1, "ROUTE": 2}
FRAME_COLS = ("section,arm,eval_index,reason,loss,margin,n_in_frame,n_hypotheses,n_fit_segments,"
              "n_heldout_segments,heldout_digest,forward_in_px,n_forward_in,forward_all_px,"
              "feet,feet_inside,boot_spread_p95_ft")
RESID_COLS = "section,arm,eval_index,point_index,heldout_px,in_frame"
ROUTE_COLS = "section,frame_index,n_matches,n_fit,n_held,fit_inliers,held_inliers,held_median_px"


def num(value) -> str:
    return "-" if value is None or not np.isfinite(float(value)) else "%.3f" % float(value)


def write_jpg(path: Path, image, max_bytes: int = 200_000) -> bool:
    """A bounded jpg, used for the failure-bucket frames that carry no overlay."""
    for quality in (70, 50, 35, 20):
        ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if ok and buffer.nbytes <= max_bytes:
            path.write_bytes(buffer.tobytes())
            return True
    return False


def load_sections(path: Path) -> dict:
    """The sealed list. Only the eight leading fields are read: a later note column holds commas."""
    rows = {}
    for line in path.read_text(encoding="ascii").strip().split("\n")[1:]:
        field = line.split(",")[:8]
        rows[field[0]] = {"section_key": field[0], "stem": field[1], "sha256": field[3],
                          "bytes": int(field[4]), "frame_count": int(field[7])}
    return rows


def detect_feet(model, image):
    """Feet in MEASUREMENT-image pixels, the units every court matrix here is defined on."""
    result = list(model(image, classes=[0], conf=0.3, verbose=False, imgsz=640,
                        device="cpu", stream=True))[0]
    boxes = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else []
    return feet_from_boxes(boxes, image.shape)


def score_frame(stem, index, image, model, cfg, route_court, tally, mode):
    """One arm on the SHARED held-out set of this frame. Returns that arm's records.

    The held-out supports come from ARM_A's detection whatever the arm is, so the digest below is
    identical in every process and G334's buyable-denominator finding cannot repeat.
    """
    segments = gc.detect_segments(image, gc.ARM_A)
    fit_a, held = g352.reserve_supports(segments, stem, index, gc.ARM_A)
    held_field = gt.distance_transform(image.shape, held)
    digest = cells.held_digest(held)
    fit_input = []
    if mode == "ROUTE":
        matrix = gm.invert(route_court) if route_court is not None else None
        arms = [("ROUTE", matrix, "valid" if matrix is not None else "no_valid_h",
                 None, float("nan"), 0, 0)]
    else:
        fit_input = fit_a if cfg.name == "A" else cells.drop_near_heldout(
            gc.detect_segments(image, cfg), held_field)
        tally.take()
        fit = g352.fit_whole_template(image, fit_input, cfg)
        gates = tally.take()
        arms = [("G352" + cfg.name, fit.image, fit.reason, fit.runner_up_margin, fit.loss,
                 fit.n_in_frame, fit.n_hypotheses)]
    if mode == "ROUTE":
        gates = {}
    feet = detect_feet(model, image)
    rng = cells.frame_rng(stem, index)
    out = {}
    for name, image_matrix, reason, margin, loss, n_in, n_hyp in arms:
        ok = reason == "valid" and image_matrix is not None
        records = cells.template_records(image_matrix, held_field) if ok else []
        court = gm.invert(image_matrix) if ok else None
        _points, inside, spreads = cells.foot_metrics(court, feet, rng)
        in_values = [value for _i, value, in_frame in records if in_frame]
        out[name] = {
            "reason": reason if ok else (reason or "no_valid_h"), "records": records,
            "feet": len(feet), "inside": inside, "spreads": spreads, "margin": margin,
            "loss": loss, "n_in_frame": len(in_values) if name == "ROUTE" else n_in,
            "n_hypotheses": n_hyp, "gates": gates, "n_fit": len(fit_input),
            "n_held": len(held), "digest": digest,
            "forward_in": cells.percentile(in_values, 50.0), "n_forward_in": len(in_values),
            "forward_all": cells.percentile([v for _i, v, _f in records], 50.0),
            "image_matrix": image_matrix if ok else None,
        }
    return out


def render_plan(indices: list, arm_name: str) -> dict:
    """The prereg's sealed even render index per arm; never the first valid frame."""
    position = ARM_POSITION.get(arm_name, ARM_POSITION.get(arm_name[-1], 0))
    return {arm_name: indices[(2 * position + 1) % len(indices)]}


def emit(key, name, index, values, render_at, evidence, rendered, frame_rows, resid_rows):
    """One frame-by-arm record: the CSV rows, the sealed-index overlay, the bucket frame."""
    frame_rows.append(",".join([
        key, name, pad6(index), values["reason"], num(values["loss"]), num(values["margin"]),
        pad6(values["n_in_frame"]), pad6(values["n_hypotheses"]), pad6(values["n_fit"]),
        pad6(values["n_held"]), values["digest"][:16], num(values["forward_in"]),
        pad6(values["n_forward_in"]), num(values["forward_all"]), pad6(values["feet"]),
        pad6(values["inside"]), num(cells.percentile(values["spreads"], 95.0))]))
    for point, value, in_frame in values["records"]:
        resid_rows.append("%s,%s,%s,%s,%s,%d" % (
            key, name, pad6(index), pad6(point), num(value), int(in_frame)))
    if values["image_matrix"] is not None and index == render_at:
        if gm.render_overlay(values["image"], values["image_matrix"],
                             evidence / "renders" / ("%s_%s.jpg" % (key, name))):
            rendered[name] = index
    tag = "%s_%s" % (name, values["reason"])
    if values["reason"] != "valid" and tag not in rendered:
        if write_jpg(evidence / "renders" / ("%s_%s_bucket_%s_f%s.jpg" % (
                key, name, values["reason"], pad6(index))), values["image"]):
            rendered[tag] = index


def run_section(workdir: Path, evidence: Path, cfg, key: str, row: dict, mode: str,
                shard: int = 0, n_shards: int = 1, keep_every: int = 1):
    """One sequential decode. ROUTE steps every frame; an arm shard fits its own sealed frames.

    Sharding splits the SAME sealed evaluation list across processes by position, so no frame,
    held-out set or hypothesis changes -- only how many processes carry them.
    """
    with_route = mode == "ROUTE"
    stem = row["stem"]
    video = workdir / (stem + ".mp4")
    got = sha256_of(video)
    print("SNAPSHOT %s %s sealed=%s got=%s %s" % (
        key, stem, row["sha256"][:16], got[:16],
        "MATCH" if got == row["sha256"] else "MISMATCH"), flush=True)
    if got != row["sha256"]:
        raise SystemExit("snapshot sha256 mismatch for %s" % stem)
    indices = eval_indices(row["frame_count"], N_EVAL)
    arm_name = "ROUTE" if with_route else "G352" + cfg.name
    plan = render_plan(indices, arm_name)
    # The sealed list is the frame SOURCE; `keep_every` thins it evenly when an arm cannot afford
    # all 60 on shared pod CPU. That thinning is a PARTIAL the memo names; it never reorders or
    # reselects, and ROUTE always keeps the full list.
    selected = [index for position, index in enumerate(indices) if position % keep_every == 0]
    want = {index for position, index in enumerate(selected)
            if with_route or position % n_shards == shard}
    after = [index for index in selected if index >= plan[arm_name]]
    render_at = after[0] if after else selected[-1]
    print("SHARD %s %s %d/%d keep_every=%d frames=%d of %d sealed=%d render_at=%d" % (
        key, arm_name, shard, n_shards, keep_every, len(want), len(selected), len(indices),
        render_at), flush=True)
    cell_map = {arm_name: cells.Cell(key, arm_name)}
    pipeline = route()
    arm = make_arm(cv2.imread(str(workdir / "pano_enhanced.png"))) if with_route else None
    from ultralytics import YOLO
    model = YOLO(str(workdir / "yolov8n.pt"))
    frame_rows, resid_rows, route_rows, held_rows = [], [], [], []
    rendered, route_tally, seen, decoded = {}, ArmTally(), [], 0
    capture = cv2.VideoCapture(str(video))
    with MatchRecorder() as recorder, cells.ReasonTally() as tally:
        while True:
            ok, raw = capture.read()
            if not ok:
                break
            frame = raw[pipeline.TOPCUT:]
            homography = step_arm(arm, frame, recorder, route_tally, 5.0, rows=held_rows,
                                  tag=(decoded,)) if with_route else None
            if decoded in want:
                seen.append(decoded)
                image = gt.measurement_image(frame, topcut=0)
                resize = gt.measurement_matrix(frame.shape[0], frame.shape[1], topcut=0)
                route_court = gm.route_court_matrix(
                    homography, arm.M1, arm.map_2d.shape[1], arm.map_2d.shape[0],
                    resize) if with_route else None
                out = score_frame(stem, decoded, image, model, cfg, route_court, tally, mode)
                for name, values in out.items():
                    values["image"] = image
                    cell_map[name].add(values["reason"], values["records"], values["feet"],
                                       values["inside"], values["spreads"], values["margin"],
                                       values["n_hypotheses"], values["n_held"])
                    for gate, count in values["gates"].items():
                        cell_map[name].gate_counts[gate] = \
                            cell_map[name].gate_counts.get(gate, 0) + count
                    emit(key, name, decoded, values, render_at, evidence, rendered,
                         frame_rows, resid_rows)
                print("  FRAME %s %s %s" % (pad6(decoded), arm_name,
                                            out[arm_name]["reason"]), flush=True)
            decoded += 1
    capture.release()
    for position, n_matches, stats in held_rows:
        route_rows.append("%s,%s,%s,%s" % (
            key, pad6(position), pad6(n_matches),
            ",".join([pad6(stats["n_fit"]), pad6(stats["n_held"]), pad6(stats["fit_inliers"]),
                      pad6(stats["held_inliers"]), num(stats["held_median_px"])])
            if stats else "-,-,-,-,-"))
    print("  %s decoded=%s eval_reached=%s/%s renders=%s" % (
        key, pad6(decoded), pad6(len(seen)), pad6(len(indices)), sorted(rendered)), flush=True)
    return cell_map, frame_rows, resid_rows, route_rows, len(seen), len(indices), decoded


def main(argv) -> int:
    started = time.time()
    workdir, evidence, name, key = Path(argv[2]), Path(argv[3]), argv[4], argv[5]
    shard = int(argv[6]) if len(argv) > 6 else 0
    n_shards = int(argv[7]) if len(argv) > 7 else 1
    keep_every = int(argv[8]) if len(argv) > 8 else 1
    cfg = {"A": gc.ARM_A, "B": gc.ARM_B, "ROUTE": gc.ARM_A}[name]
    (evidence / "renders").mkdir(parents=True, exist_ok=True)
    row = load_sections(evidence / "sections_sealed.csv")[key]
    cell_map, frames, resid, route_rows, reached, wanted, decoded = run_section(
        workdir, evidence, cfg, key, row, name, shard, n_shards, keep_every)
    out = evidence / ("part_%s_%s_%02d" % (key, name, shard))
    out.mkdir(parents=True, exist_ok=True)
    (out / "perframe.csv").write_text("\n".join([FRAME_COLS] + frames) + "\n",
                                      encoding="ascii", newline="\n")
    (out / "residuals.csv").write_text("\n".join([RESID_COLS] + resid) + "\n",
                                       encoding="ascii", newline="\n")
    if route_rows:
        (out / "route_correspondences.csv").write_text(
            "\n".join([ROUTE_COLS] + route_rows) + "\n", encoding="ascii", newline="\n")
    lines = []
    for arm in sorted(cell_map):
        summary = cell_map[arm].summary()
        summary.update({"section": key, "arm": arm, "eval_reached": reached,
                        "eval_wanted": wanted, "decoded": decoded})
        lines.append(repr(summary))
    (out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    for line in lines:
        print("SUMMARY %s" % line, flush=True)
    print("WALL_SECONDS %s" % pad6(int(time.time() - started)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
