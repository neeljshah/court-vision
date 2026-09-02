"""G46: premise test -- does the tennis court solver label the far SERVICE line
as the far BASELINE?  Read-only.  No solver code, threshold or parameter is
touched; every call below is the production path.

Independent quantity used as truth: the CENTRE SERVICE LINE is painted from the
net (18 ft) to the far service line (60 ft) only.  Its topmost painted pixel is
therefore the FAR SERVICE LINE at a true 60 ft.  Push that pixel through the
solver's own homography:
  correct labelling            -> ~60 solver-feet
  far-service-for-baseline     -> ~78 solver-feet (it IS the solver's far edge)
Detection gaps can only SHORTEN the observed extent, i.e. can only pull the
number down toward 60.  The test is therefore conservative against CONFIRMING.

Same for the doubles sidelines, painted 0..78 ft: their topmost painted pixel
reads ~78 when correct and up to ~116 under the mislabel.
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, "/workspace/nba-ai-system")

from domains.tennis.tracking.adapter import TennisAdapter  # noqa: E402
from domains.tennis.tracking.court_lines import (  # noqa: E402
    TOPHAT_CONTRASTS, _row_on, court_line_segments, select_court_lines,
    solve_corners, split_orientation)

COURT_FEET = np.float32(((0, 0), (0, 36), (78, 0), (78, 36)))


def run_solver(frame):
    """Production detect_court, but returning the intermediate CourtLines too."""
    shape = frame.shape[:2]
    for contrast in TOPHAT_CONTRASTS:
        segments = court_line_segments(frame, contrast=contrast)
        if not segments:
            continue
        court, _ = select_court_lines(segments, shape)
        if court is None:
            continue
        corners, _ = solve_corners(court, shape)
        if corners is not None:
            return court, corners, segments, contrast
    return None


def to_feet(homography, points):
    pts = np.float32(points).reshape(1, -1, 2)
    return cv2.perspectiveTransform(pts, homography)[0]


def cluster_points(cluster):
    return np.array([[l[0], l[1]] for l in cluster] + [[l[2], l[3]] for l in cluster],
                    dtype=np.float32)


def cluster_top_point(cluster, pct):
    """Point at the `pct` percentile of the cluster's endpoint rows (topmost = low row)."""
    pts = cluster_points(cluster)
    cut = np.percentile(pts[:, 1], pct)
    keep = pts[pts[:, 1] <= cut]
    return keep[np.argmin(keep[:, 1])]


def projective_1d(s_c):
    """t -> s fixing 0->0, 18->18, 60->s_c; return the true feet T with s(T)=78.

    s = a t / (c t + 1).  18 -> 18 gives a = 18c + 1.
    """
    denom = 1080.0 - 60.0 * s_c
    if abs(denom) < 1e-9:
        return None
    c = (s_c - 60.0) / denom
    a = 18.0 * c + 1.0
    k = a - 78.0 * c
    return None if abs(k) < 1e-9 else 78.0 / k


def analyse_frame(frame):
    out = run_solver(frame)
    if out is None:
        return None
    court, corners, segments, contrast = out
    img2ft, _ = cv2.findHomography(np.float32(corners), COURT_FEET)
    ft2img, _ = cv2.findHomography(COURT_FEET, np.float32(corners))
    if img2ft is None or ft2img is None:
        return None

    clusters = court.vertical_clusters  # image order: left, l-singles, centre, r-singles, right
    rec = {"contrast": contrast, "corners": np.asarray(corners).tolist()}

    # --- independent truth 1: far end of the painted centre service line (true 60 ft)
    for pct in (0.0, 10.0):
        pt = cluster_top_point(clusters[2], pct)
        rec["centre_top_ft_p%d" % int(pct)] = float(to_feet(img2ft, [pt])[0][0])
    # --- independent truth 2: far end of the painted doubles sidelines (true 78 ft)
    for name, idx in (("left", 0), ("right", 4)):
        pt = cluster_top_point(clusters[idx], 10.0)
        rec["%s_sideline_top_ft" % name] = float(to_feet(img2ft, [pt])[0][0])
    # --- sanity: near end of the centre service line (true 18 ft, the net)
    pts = cluster_points(clusters[2])
    rec["centre_bottom_ft"] = float(to_feet(img2ft, [pts[np.argmax(pts[:, 1])]])[0][0])

    # --- every horizontal court-line candidate, in solver feet (the histogram)
    horizontal, _ = split_orientation(segments)
    horizontal_clusters = TennisAdapter._cluster_lines(horizontal, True, frame.shape[:2])
    rows = [l[1] for cl in clusters for l in cl] + [l[3] for cl in clusters for l in cl]
    top, bottom = min(rows), max(rows)
    margin = 0.1 * (bottom - top)
    cand = []
    for cl in horizontal_clusters:
        fitted = TennisAdapter._fit_line(cl)
        row = _row_on(fitted, court.centre)
        if row is None or not (top - margin <= row <= bottom + margin):
            continue
        ip = TennisAdapter._intersection(fitted, court.centre)
        if ip is None:
            continue
        lf, wf = to_feet(img2ft, [ip])[0]
        p = cluster_points(cl)
        span = to_feet(img2ft, [p[np.argmin(p[:, 0])], p[np.argmax(p[:, 0])]])
        cand.append({"len_ft": round(float(lf), 2), "wid_ft": round(float(wf), 2),
                     "span_w_ft": [round(float(span[0][1]), 1), round(float(span[1][1]), 1)]})
    rec["horizontals_ft"] = sorted(cand, key=lambda d: d["len_ft"])

    # --- solver's own role rows, in solver feet (0 / 18 / 78 by construction)
    for name in ("near", "near_service", "far", "far_service"):
        line = getattr(court, name)
        if line is None:
            rec["role_%s_ft" % name] = None
            continue
        ip = TennisAdapter._intersection(line, court.centre)
        rec["role_%s_ft" % name] = None if ip is None else round(float(to_feet(img2ft, [ip])[0][0]), 2)

    s_c = rec["centre_top_ft_p10"]
    span_true = projective_1d(s_c)
    rec["true_span_ft"] = span_true
    rec["length_ratio"] = None if not span_true or span_true <= 0 else 78.0 / span_true
    return rec, ft2img, corners, clusters


def render(frame, ft2img, corners, clusters, rec, path):
    img = frame.copy()
    order = [(0, 0), (0, 36), (78, 36), (78, 0)]
    poly = np.int32(to_feet(ft2img, order)).reshape(-1, 1, 2)
    cv2.polylines(img, [poly], True, (0, 255, 0), 2)
    for feet, colour, label in ((18.0, (255, 128, 0), "18"),
                                (39.0, (255, 255, 0), "39 net"),
                                (60.0, (255, 0, 255), "60 far-svc")):
        pair = to_feet(ft2img, [(feet, 0.0), (feet, 36.0)])
        a = (int(pair[0][0]), int(pair[0][1]))
        b = (int(pair[1][0]), int(pair[1][1]))
        cv2.line(img, a, b, colour, 2)
        cv2.putText(img, label, a, cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 2)
    pt = cluster_top_point(clusters[2], 10.0)
    cv2.circle(img, (int(pt[0]), int(pt[1])), 8, (0, 0, 255), 2)
    cv2.putText(img, "centre-svc top = %.1f solver-ft (true 60)" % rec["centre_top_ft_p10"],
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.putText(img, "green = solver 78ft far edge   ratio %.3f" % (rec["length_ratio"] or 0.0),
                (10, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imwrite(path, img)
    ys = poly.reshape(-1, 2)[:, 1]
    y0 = max(0, int(min(ys)) - 70)
    y1 = min(img.shape[0], int(min(ys)) + int(0.6 * (max(ys) - min(ys))))
    crop = img[y0:y1]
    if crop.size:
        cv2.imwrite(path.replace(".png", "_far.png"), cv2.resize(crop, None, fx=1.7, fy=1.7))


def main(clip, out_dir, n_target=40, grid=160):
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(clip)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idx = np.unique(np.linspace(0, total - 1, grid).astype(int))
    hits = []
    for f in idx:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok, frame = cap.read()
        if not ok:
            continue
        got = analyse_frame(frame)
        if got is None:
            continue
        rec, ft2img, corners, clusters = got
        rec["frame"] = int(f)
        hits.append((rec, frame, ft2img, corners, clusters))
        print("hit %d ratio %s centre_top %.2f" % (f, rec["length_ratio"], rec["centre_top_ft_p10"]),
              flush=True)
    cap.release()
    print("accepted %d of %d sampled" % (len(hits), len(idx)), flush=True)
    if len(hits) > n_target:
        pick = np.unique(np.linspace(0, len(hits) - 1, n_target).astype(int))
        hits = [hits[i] for i in pick]
    recs = []
    for rec, frame, ft2img, corners, clusters in hits:
        render(frame, ft2img, corners, clusters, rec,
               os.path.join(out_dir, "f%06d.png" % rec["frame"]))
        recs.append(rec)
    with open(os.path.join(out_dir, "records.json"), "w") as fh:
        json.dump({"clip": clip, "grid": len(idx), "accepted": len(recs), "records": recs}, fh, indent=1)
    ratios = np.array([x["length_ratio"] for x in recs if x["length_ratio"]])
    if ratios.size:
        print("RATIO n=%d median=%.4f mean=%.4f p10=%.4f p90=%.4f min=%.4f max=%.4f"
              % (ratios.size, np.median(ratios), ratios.mean(), np.percentile(ratios, 10),
                 np.percentile(ratios, 90), ratios.min(), ratios.max()), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2],
         int(sys.argv[3]) if len(sys.argv) > 3 else 40,
         int(sys.argv[4]) if len(sys.argv) > 4 else 160)
