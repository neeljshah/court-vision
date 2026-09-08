"""G334 driver: premise gate, the route baseline arm, the G334 arms, and the two CSV artifacts.

Usage:
    python -m scripts.platformkit.tracking.g334_run <workdir> <evidence_dir> [A|B|A,B] [S1,S2,...]

<workdir> is the pod job root holding the read-only section snapshot, `pano_enhanced.png`,
`Rectify1.npy` and `2d_map.png`. Every section's sha256 is checked against the value sealed in
`docs/evidence/tracking/g334_prereg_2026-09-08.md` before any arm runs. Nothing is written outside
<evidence_dir>; nothing under `src/` is edited and no panorama cache path is written.

ONE sequential decode per section serves every arm: the route's matcher is fed EVERY frame in order
so its own counter, cut gate and EMA tiers decide where a fit happens, and the G334 arms see only
the five-frame shot window around each sealed evaluation index.
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

from scripts.platformkit.tracking import g334_metrics as gm  # noqa: E402
from scripts.platformkit.tracking import g334_court_line_calibration as gc  # noqa: E402
from scripts.platformkit.tracking import g334_court_template as gt  # noqa: E402
from scripts.platformkit.tracking.g330_attempt2 import (  # noqa: E402
    ArmTally, MatchRecorder, eval_indices, make_arm, step_arm,
)
from scripts.platformkit.tracking.g330_panorama_identity import (  # noqa: E402
    feet_from_boxes, frac, pad6, route, sha256_of,
)

# Sealed in the prereg, section 1: stem -> (sha256 of the scored copy, container frame count).
SEALED = {
    "S1": ("basketball__nbl-WTEUwPcy7X8_s90",
           "225ada2044bf0d6b530ddef7d3cdddec38521b8a546771e6736ac659dca763fb", 6527),
    "S2": ("nba__0022500081_s4812",
           "03e66b6b172a494f0df5857a9394bbeec15c65868a6db15bcaae03cf9322b997", 3941),
    "S3": ("nba__0022401198_s2784",
           "444325a05cdb375990b621fc8870ddc774d4f0af4dad456f0b329b03a6552485", 3957),
    "S4": ("nba__RIrGQJ_jsGQ_s6690",
           "5938100b59c2aeebd62e222f7219363f2846a85e79b98516ca0e2161155eb2fd", 3961),
    "S5": ("nba__m7K0J4wzDn4_s2070",
           "7b8f86372e74ae431224c1606d26d9ddb80d30c781c9fdc2af6eb2cd8ba4afbb", 8044),
    "S6": ("nba__4PH6yOSvcs4_s2932",
           "31d1146112322ed3c60596058e45bd2fd349fa0483dc186fc99d49891f9d7214", 7826),
}
PREMISE_SECTIONS = ("S1", "S2", "S3")
PREMISE_MAX_RATIO = 0.30
METRIC_COLS = ("section,stem,arm,n_frames,valid_frames,valid_share,feet_total,feet_evaluated,"
               "feet_inside,feet_inside_share,heldout_forward_px,n_forward_points,"
               "heldout_reverse_px,n_reverse_points,n_heldout_segments,nn_median_ft,n_nn_pairs,"
               "n_hypotheses,bucket_valid,bucket_too_few_groups,bucket_no_valid_h,"
               "bucket_implausible_scale")
FRAME_COLS = ("section,arm,eval_index,reason,score,n_scored,n_hypotheses,n_fit_segments,"
              "n_heldout_segments,forward_px,n_forward,reverse_px,n_reverse,feet,feet_inside,"
              "nn_median_ft")


def _num(value) -> str:
    return "-" if value is None or not np.isfinite(value) else "%.3f" % float(value)


def peak_rss_mb() -> str:
    try:
        import resource
        return "%.1f" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0)
    except Exception:
        return "unknown"


def verify_snapshot(workdir: Path, keys) -> None:
    for key in keys:
        stem, want, _frames = SEALED[key]
        got = sha256_of(workdir / ("%s.mp4" % stem))
        print("SNAPSHOT %s %s sealed=%s got=%s %s" % (
            key, stem, want[:16], got[:16], "MATCH" if got == want else "MISMATCH"))
        if got != want:
            raise SystemExit("snapshot sha256 mismatch for %s" % stem)


def detect_feet(model, frame):
    result = list(model(frame, classes=[0], conf=0.3, verbose=False, imgsz=640,
                        device="cpu", stream=True))[0]
    boxes = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else []
    return feet_from_boxes(boxes, frame.shape)


def _hist(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    values = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten()
    total = values.sum()
    return values / total if total > 0 else values


def shot_run(window, centre_position: int, cut_l1: float):
    """The run of the window containing the centre frame, split at the route's own cut threshold."""
    histograms = [_hist(image) for image in window]
    start, stop = centre_position, centre_position + 1
    while start > 0 and float(np.abs(histograms[start] - histograms[start - 1]).sum()) < cut_l1:
        start -= 1
    while stop < len(window) and float(np.abs(histograms[stop] - histograms[stop - 1]).sum()) < cut_l1:
        stop += 1
    return start, stop


def score_window(section, stem, index, window, centre_position, feet, cfg, route_matrix, rows):
    """Both arms on one evaluation frame: the G334 per-shot median, then the route composition.

    `window` frames are ALREADY TOPCUT-cropped by the caller, so the measurement image only applies
    the width scale here; `resize` in the caller carries the crop, and cropping twice would offset
    the route composition against the image every metric is measured in.
    """
    images = [gt.measurement_image(frame, topcut=0) for frame in window]
    centre = images[centre_position]
    start, stop = shot_run(images, centre_position, cfg.cut_l1)
    splits = [gc.heldout_split(gc.detect_segments(image, cfg), stem, index) for image in images]
    fit_centre, held_centre = splits[centre_position]
    held_field = gt.distance_transform(centre.shape, held_centre)
    fits = [gc.fit_frame(images[i], splits[i][0], cfg) for i in range(start, stop)]
    n_hyp = sum(fit.n_hypotheses for fit in fits)
    reason = fits[centre_position - start].reason
    matrix = gc.shot_median([fit.image for fit in fits])
    if matrix is not None:
        score, n_scored = gc.score_image_matrix(
            matrix, gt.distance_transform(centre.shape, fit_centre), cfg)
        reason = gc.gate(matrix, score, n_scored, centre.shape, cfg)
    else:
        score, n_scored = -1.0, 0
        if reason == "valid":
            reason = "no_valid_h"
    if reason != "valid":
        matrix = None
    out = {}
    for arm, image_matrix in (("G334" + cfg.name, matrix),
                              ("ROUTE", gm.invert(route_matrix))):
        court = gm.invert(image_matrix) if arm.startswith("G334") else route_matrix
        ok = image_matrix is not None and court is not None
        forward, n_forward = gm.forward_error(image_matrix if ok else None, held_field)
        reverse, n_reverse = gm.reverse_error(image_matrix if ok else None, held_centre,
                                              centre.shape)
        points = gm.court_points(court if ok else None, feet)
        inside = gm.inside_count(points)
        neighbours = gm.nearest_neighbour_ft(points)
        arm_reason = reason if arm.startswith("G334") else ("valid" if ok else "no_valid_h")
        out[arm] = (arm_reason, forward, n_forward, reverse, n_reverse, len(held_centre),
                    len(feet), inside, neighbours, n_hyp if arm.startswith("G334") else 0)
        rows.append(",".join([
            section, arm, pad6(index), arm_reason, _num(score if arm.startswith("G334") else None),
            pad6(n_scored if arm.startswith("G334") else 0),
            pad6(n_hyp if arm.startswith("G334") else 0), pad6(len(fit_centre)),
            pad6(len(held_centre)), _num(forward), pad6(n_forward), _num(reverse),
            pad6(n_reverse), pad6(len(feet)), pad6(inside),
            _num(np.median(neighbours) if len(neighbours) else None)]))
    return out, centre, matrix


def run_section(workdir: Path, key: str, model, pano, configs, evidence: Path, rows, premise):
    """One sequential decode: the route arm sees every frame, the G334 arms see the windows."""
    stem, _sha, frames = SEALED[key]
    indices = eval_indices(frames)
    window_map = {}
    for index in indices:
        for offset in range(-(gc.ARM_A.window // 2), gc.ARM_A.window // 2 + 1):
            window_map.setdefault(index + offset, []).append(index)
    pipeline = route()
    arm = make_arm(pano)
    resize = None
    cells = {name: gm.Cell(key, name) for name in
             ["G334" + cfg.name for cfg in configs] + ["ROUTE"]}
    tally, held_rows = ArmTally(), []
    pending, feet_at, rendered = {}, {}, set()
    capture = cv2.VideoCapture(str(workdir / ("%s.mp4" % stem)))
    position = 0
    with MatchRecorder() as recorder:
        while True:
            ok, raw = capture.read()
            if not ok:
                break
            frame = raw[pipeline.TOPCUT:]
            if resize is None:
                resize = gt.measurement_matrix(raw.shape[0], raw.shape[1])
            homography = step_arm(arm, frame, recorder, tally, 5.0, rows=held_rows,
                                  tag=(position,))
            if position in window_map:
                for centre_index in window_map[position]:
                    pending.setdefault(centre_index, []).append(frame)
                    if centre_index == position:
                        # The route's M at the EVALUATION frame, not at the end of its window.
                        feet_at[centre_index] = (detect_feet(model, frame), homography)
            ready = [i for i in list(pending) if position >= i + gc.ARM_A.window // 2]
            for centre_index in sorted(ready):
                window = pending.pop(centre_index)
                centre_position = min(gc.ARM_A.window // 2, len(window) - 1)
                feet, centre_h = feet_at.pop(centre_index, ([], None))
                route_matrix = gm.route_court_matrix(centre_h, arm.M1, arm.map_2d.shape[1],
                                                     arm.map_2d.shape[0], resize)
                for cfg in configs:
                    out, centre, matrix = score_window(
                        key, stem, centre_index, window, centre_position, feet, cfg,
                        route_matrix, rows)
                    for name, values in out.items():
                        if name == "ROUTE" and cfg is not configs[0]:
                            continue
                        cells[name].add(*values)
                    if matrix is not None and cfg.name not in rendered:
                        if gm.render_overlay(centre, matrix, evidence / "renders" /
                                             ("%s_%s.jpg" % (key, cfg.name))):
                            rendered.add(cfg.name)
            position += 1
    capture.release()
    print("  %s decoded=%s eval=%s route_fits=%s heldout=%s/%s render=%s" % (
        key, pad6(position), pad6(cells["ROUTE"].n_frames), pad6(tally.fit_frames),
        pad6(tally.held_inliers), pad6(tally.n_held), sorted(rendered)))
    if key in PREMISE_SECTIONS:
        premise[key] = (tally.held_inliers, tally.n_held)
    return cells


def check_premise(premise) -> bool:
    """Binding before-condition: the route's reproduced held-out inlier ratio on S1 to S3."""
    over, covered = 0, [key for key in PREMISE_SECTIONS if key in premise]
    for key in covered:
        inliers, total = premise[key]
        ratio = inliers / total if total else 0.0
        over += ratio > PREMISE_MAX_RATIO
        print("BEFORE %s heldout_inliers=%s ratio=%.4f" % (key, frac(inliers, total), ratio))
    if len(covered) < len(PREMISE_SECTIONS):
        print("PREMISE PARTIAL: %d of 3 sealed sections in this process; the gate is decided over "
              "all three together" % len(covered))
        return True
    print("PREMISE %s (%d of 3 sections above %.2f)" % (
        "FALSE" if over >= 2 else "TRUE", over, PREMISE_MAX_RATIO))
    return over < 2


def main(argv) -> int:
    started = time.time()
    workdir, evidence = Path(argv[1]), Path(argv[2])
    names = (argv[3] if len(argv) > 3 else "A").split(",")
    keys = (argv[4].split(",") if len(argv) > 4 else sorted(SEALED))
    configs = [{"A": gc.ARM_A, "B": gc.ARM_B}[name.strip()] for name in names]
    (evidence / "renders").mkdir(parents=True, exist_ok=True)
    verify_snapshot(workdir, keys)
    pano = cv2.imread(str(workdir / "pano_enhanced.png"))
    print("ARM ROUTE panorama pano_enhanced.png %s" % sha256_of(workdir / "pano_enhanced.png")[:16])
    from ultralytics import YOLO
    model = YOLO(str(workdir / "yolov8n.pt"))
    metric_rows, frame_rows, premise = [METRIC_COLS], [FRAME_COLS], {}
    for key in keys:
        print("SECTION %s %s" % (key, SEALED[key][0]))
        cells = run_section(workdir, key, model, pano, configs, evidence, frame_rows, premise)
        for name in sorted(cells):
            summary = cells[name].summary()
            metric_rows.append(",".join([
                key, SEALED[key][0], name, pad6(summary["n_frames"]),
                pad6(summary["valid_frames"]),
                frac(summary["valid_frames"], summary["n_frames"]), pad6(summary["feet_total"]),
                pad6(summary["feet_evaluated"]), pad6(summary["feet_inside"]),
                frac(summary["feet_inside"], summary["feet_evaluated"]),
                _num(summary["heldout_forward_px"]), pad6(summary["n_forward_points"]),
                _num(summary["heldout_reverse_px"]), pad6(summary["n_reverse_points"]),
                pad6(summary["n_heldout_segments"]), _num(summary["nn_median_ft"]),
                pad6(summary["n_nn_pairs"]), pad6(summary["n_hypotheses"]),
                pad6(summary["bucket_valid"]), pad6(summary["bucket_too_few_groups"]),
                pad6(summary["bucket_no_valid_h"]), pad6(summary["bucket_implausible_scale"])]))
            print("  %s" % metric_rows[-1])
        (evidence / "metrics.csv").write_text("\n".join(metric_rows) + "\n", encoding="ascii")
        (evidence / "perframe.csv").write_text("\n".join(frame_rows) + "\n", encoding="ascii")
    if premise:
        check_premise(premise)
    print("PEAK_RSS_MB %s" % peak_rss_mb())
    print("WALL_SECONDS %s" % pad6(int(time.time() - started)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
