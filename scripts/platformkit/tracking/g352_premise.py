"""G352 premise: does G334's argmax lose under the WHOLE-template denominator?

Usage:
    python -m scripts.platformkit.tracking.g352_premise <render.jpg> <evidence_dir>

The comparison is between two fits on the SAME image and the SAME support field:
  * the SURVIVOR argmax -- what `g334_court_line_calibration.fit_frame` maximises, taken WITHOUT
    its output gate. `fit_frame` returns no matrix when its gate rejects the winner, so calling it
    here would silently drop the very fit the premise is about; the search below is its own search
    with the gate omitted, and nothing else changed.
  * the WHOLE-template argmax -- `g352_whole_template_objective.fit_whole_template`.
Both are then scored with the whole-template denominator: the mean over ALL 398 template points of
`max(0, 1 - d / tau)`, where a point projected out of the image contributes 0. Per-point records
are archived so the counts are never prose only (carry-over (e)).
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking import g334_court_line_calibration as gc
from scripts.platformkit.tracking import g334_court_template as gt
from scripts.platformkit.tracking import g352_cells as cells
from scripts.platformkit.tracking import g352_whole_template_objective as g352


def survivor_argmax(image, segments, field, cfg):
    """G334's soft-chamfer maximiser with its OUTPUT GATE omitted; the search is unchanged."""
    family_a, family_b = gc.split_families(segments, cfg)
    groups_a = gc.family_groups(family_a, cfg)
    groups_b = gc.family_groups(family_b, cfg)
    bound, best, total = 8.0 * max(image.shape[:2]), None, 0
    for first, second in ((groups_a, groups_b), (groups_b, groups_a)):
        for image_quad, court_quad in gc.enumerate_hypotheses(first, second, cfg, bound):
            total += 1
            matrix = cv2.getPerspectiveTransform(court_quad, image_quad)
            score, _n_scored = gc.score_image_matrix(matrix, field, cfg)
            if best is None or score > best[0]:
                best = (score, matrix)
    return (best[1] if best else None), (best[0] if best else float("nan")), total


def whole_score(matrix, field, cfg) -> tuple:
    """The whole-template soft-chamfer score and its in-frame count, plus the per-point records."""
    if matrix is None:
        return float("nan"), 0, []
    records = cells.template_records(matrix, field)
    values = [max(0.0, 1.0 - value / cfg.tau) if in_frame else 0.0
              for _i, value, in_frame in records]
    return (float(np.mean(values)) if values else float("nan"),
            sum(1 for _i, _v, in_frame in records if in_frame), records)


def main(argv) -> int:
    render, evidence = Path(argv[1]), Path(argv[2])
    cfg = gc.ARM_A
    image = cv2.imread(str(render))
    segments = gc.detect_segments(image, cfg)
    field = gt.distance_transform(image.shape, segments)
    survivor, survivor_old, n_hyp = survivor_argmax(image, segments, field, cfg)
    whole = g352.fit_whole_template(image, segments, cfg)
    rows, summary = ["point_index,fit,fit_support_px,in_frame"], []
    for label, matrix in (("survivor_argmax", survivor),
                          ("whole_template_argmax", whole.image)):
        score, n_in, records = whole_score(matrix, field, cfg)
        old, _n = gc.score_image_matrix(matrix, field, cfg) if matrix is not None \
            else (float("nan"), 0)
        summary.append((label, old, score, n_in))
        for point, value, in_frame in records:
            rows.append("%06d,%s,%.3f,%d" % (point, label, value, int(in_frame)))
    (evidence / "premise.csv").write_text("\n".join(rows) + "\n", encoding="ascii", newline="\n")
    print("BEFORE_S1_RENDER path=%s bytes=%d shape=%dx%d segments=%d hypotheses=%d "
          "template_points=%d" % (render.as_posix(), render.stat().st_size, image.shape[1],
                                  image.shape[0], len(segments), n_hyp, len(gt.TEMPLATE_POINTS)))
    for label, old, score, n_in in summary:
        print("%s old_score=%.9f whole_score=%.9f in_frame=%06d/%06d" % (
            label.upper(), old, score, n_in, len(gt.TEMPLATE_POINTS)))
    true = summary[0][2] < summary[1][2]
    print("PREMISE %s argmax %s under the whole-template score" % (
        "TRUE" if true else "FALSE", "loses" if true else "wins"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
