"""G57: render rejected frames and show WHY the solver rejected them.

For each frame the production segment finder is re-run at every TOPHAT_CONTRASTS
value; the pass with the most segments is drawn (horizontal green, vertical
blue) and the frame is annotated with the gate that rejected it and the segment
counts.  That distinguishes "the solver found nothing to work with" from "the
solver found plenty and threw it away".  Read-only; nothing is tuned.
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, "/workspace/nba-ai-system")
cv2.setNumThreads(4)

from domains.tennis.tracking.court_diagnostics import rejection_gate  # noqa: E402
from domains.tennis.tracking.court_lines import (  # noqa: E402
    TOPHAT_CONTRASTS, court_line_segments, split_orientation)


def main(clip, rows_json, out_dir, n_look=12, tag="look"):
    os.makedirs(out_dir, exist_ok=True)
    rows = json.load(open(rows_json))["rows"]
    rejected = [f for f, g in rows if g != "accepted"]
    gate = dict((f, g) for f, g in rows)
    pick = [rejected[i] for i in np.unique(np.linspace(0, len(rejected) - 1, n_look).astype(int))]
    cap = cv2.VideoCapture(clip)
    summary = []
    for f in pick:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok, frame = cap.read()
        if not ok:
            continue
        best = (None, -1, 0, 0)
        for c in TOPHAT_CONTRASTS:
            segs = court_line_segments(frame, contrast=c)
            if not segs:
                continue
            h, v = split_orientation(segs)
            if len(segs) > best[1]:
                best = (segs, len(segs), len(h), len(v))
        img = frame.copy()
        if best[0]:
            h, v = split_orientation(best[0])
            for s in h:
                cv2.line(img, (int(s[0]), int(s[1])), (int(s[2]), int(s[3])), (0, 255, 0), 1)
            for s in v:
                cv2.line(img, (int(s[0]), int(s[1])), (int(s[2]), int(s[3])), (255, 128, 0), 1)
        txt = "f%d gate=%s seg=%d h=%d v=%d" % (f, gate[f], best[1] if best[1] > 0 else 0,
                                                best[2], best[3])
        cv2.putText(img, txt, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        big = cv2.resize(img, None, fx=2.0, fy=2.0) if img.shape[1] < 900 else img
        cv2.imwrite(os.path.join(out_dir, "%s_f%06d.png" % (tag, f)), big)
        summary.append({"frame": int(f), "gate": gate[f], "segments": max(best[1], 0),
                        "horizontal": best[2], "vertical": best[3]})
        print(txt, flush=True)
    cap.release()
    with open(os.path.join(out_dir, "%s_summary.json" % tag), "w") as fh:
        json.dump(summary, fh, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3],
         int(sys.argv[4]) if len(sys.argv) > 4 else 12,
         sys.argv[5] if len(sys.argv) > 5 else "look")
