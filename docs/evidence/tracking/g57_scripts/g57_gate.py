"""G57: tennis court-solver acceptance per clip, on evenly spaced frames.

Read-only.  No solver code, threshold or detection parameter is touched.
The only call into the solver is court_diagnostics.rejection_gate, which is
detect_court(frame)[2] verbatim -- "accepted" is the production accept.
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, "/workspace/nba-ai-system")
cv2.setNumThreads(4)

from domains.tennis.tracking.court_diagnostics import rejection_gate  # noqa: E402


def main(clip, out_json, n=200):
    cap = cv2.VideoCapture(clip)
    if not cap.isOpened():
        raise SystemExit("cannot open %s" % clip)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    idx = np.unique(np.linspace(0, total - 1, n).astype(int))
    rows = []
    for f in idx:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok, frame = cap.read()
        if not ok:
            rows.append([int(f), "read_failed"])
            continue
        rows.append([int(f), rejection_gate(frame)])
        if len(rows) % 25 == 0:
            print("%s %d/%d" % (os.path.basename(clip), len(rows), len(idx)), flush=True)
    cap.release()
    acc = sum(1 for _, g in rows if g == "accepted")
    payload = {"clip": clip, "width": w, "height": h, "total_frames": total,
               "sampled": len(rows), "accepted": acc, "rows": rows}
    with open(out_json, "w") as fh:
        json.dump(payload, fh)
    print("DONE %s %dx%d accepted %d / %d" % (os.path.basename(clip), w, h, acc, len(rows)), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 200)
