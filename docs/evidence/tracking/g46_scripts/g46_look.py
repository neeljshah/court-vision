"""G46 render-and-look pass. Draws, per frame:
  - the solver's claimed 78 x 36 ft doubles rectangle (thin green, gapped in the
    middle so the paint underneath stays visible)
  - thin gapped reference lines back-projected at 39 / 60 solver-feet
  - every DETECTED horizontal court-line cluster, at its true image position,
    labelled with the length it projects to in solver feet
Read-only; production solver path, nothing tuned.
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, "/workspace/nba-ai-system")
sys.path.insert(0, "/tmp")

from g46_probe import (COURT_FEET, TennisAdapter, _row_on, cluster_points,  # noqa: E402
                       cluster_top_point, run_solver, split_orientation, to_feet)


def gapped(img, a, b, colour, thick):
    a, b = np.float32(a), np.float32(b)
    for lo, hi in ((0.0, 0.36), (0.64, 1.0)):
        p, q = a + (b - a) * lo, a + (b - a) * hi
        cv2.line(img, (int(p[0]), int(p[1])), (int(q[0]), int(q[1])), colour, thick)


def draw(frame, out_path):
    got = run_solver(frame)
    if got is None:
        return None
    court, corners, segments, _ = got
    img2ft, _ = cv2.findHomography(np.float32(corners), COURT_FEET)
    ft2img, _ = cv2.findHomography(COURT_FEET, np.float32(corners))
    img = frame.copy()

    box = to_feet(ft2img, [(0, 0), (0, 36), (78, 36), (78, 0)])
    for i in range(4):
        gapped(img, box[i], box[(i + 1) % 4], (0, 255, 0), 2)
    for feet, colour in ((39.0, (255, 255, 0)), (60.0, (255, 0, 255))):
        p = to_feet(ft2img, [(feet, 0.0), (feet, 36.0)])
        gapped(img, p[0], p[1], colour, 2)
        cv2.putText(img, "%d ft" % feet, (int(p[0][0]) - 70, int(p[0][1]) + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 2)
    cv2.putText(img, "78 ft (solver far edge)", (int(box[3][0]) - 230, int(box[3][1]) + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

    horizontal, _ = split_orientation(segments)
    rows = [l[1] for cl in court.vertical_clusters for l in cl] + \
           [l[3] for cl in court.vertical_clusters for l in cl]
    top, bottom = min(rows), max(rows)
    margin = 0.1 * (bottom - top)
    detected = []
    for cl in TennisAdapter._cluster_lines(horizontal, True, frame.shape[:2]):
        fitted = TennisAdapter._fit_line(cl)
        row = _row_on(fitted, court.centre)
        ip = TennisAdapter._intersection(fitted, court.centre)
        if row is None or ip is None or not (top - margin <= row <= bottom + margin):
            continue
        lf = float(to_feet(img2ft, [ip])[0][0])
        p = cluster_points(cl)
        lo, hi = p[np.argmin(p[:, 0])], p[np.argmax(p[:, 0])]
        cv2.line(img, (int(lo[0]), int(lo[1])), (int(hi[0]), int(hi[1])), (0, 128, 255), 1)
        cv2.putText(img, "%.0f" % lf, (int(hi[0]) + 4, int(hi[1]) + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 128, 255), 1)
        detected.append(round(lf, 1))

    pt = cluster_top_point(court.vertical_clusters[2], 10.0)
    cv2.circle(img, (int(pt[0]), int(pt[1])), 8, (0, 0, 255), 2)
    cv2.putText(img, "centre-service-line paint ends here = %.1f solver-ft (true 60)"
                % float(to_feet(img2ft, [pt])[0][0]), (10, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    ys = box[:, 1]
    y0, y1 = max(0, int(min(ys)) - 90), min(img.shape[0], int(min(ys) + 0.62 * (max(ys) - min(ys))))
    cv2.imwrite(out_path.replace(".png", "_far.png"),
                cv2.resize(img[y0:y1], None, fx=2.0, fy=2.0))
    cv2.imwrite(out_path, img)
    return detected


def main(clip, frames, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(clip)
    result = {}
    for f in frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok, frame = cap.read()
        if not ok:
            continue
        got = draw(frame, os.path.join(out_dir, "look%06d.png" % f))
        print(f, got, flush=True)
        result[f] = got
    cap.release()
    json.dump(result, open(os.path.join(out_dir, "look.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], [int(x) for x in sys.argv[2].split(",")], sys.argv[3])
