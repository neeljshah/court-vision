"""G57 control: same frames, same solver, resolution changed and nothing else.

Every native-resolution clip is resampled on the SAME evenly spaced grid, each
frame is bilinearly resized to 640x360, and the production gate is re-run.  This
separates "the solver fails at 360p" from "the 360p clips happen to be bad
footage".  Read-only; the solver is not touched.
"""
import json
import sys

import cv2
import numpy as np

sys.path.insert(0, "/workspace/nba-ai-system")
cv2.setNumThreads(4)

from domains.tennis.tracking.court_diagnostics import rejection_gate  # noqa: E402


def main(clip, out_json, w, h, n=200):
    cap = cv2.VideoCapture(clip)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idx = np.unique(np.linspace(0, total - 1, n).astype(int))
    rows = []
    for f in idx:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok, frame = cap.read()
        if not ok:
            rows.append([int(f), "read_failed"])
            continue
        small = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
        rows.append([int(f), rejection_gate(small)])
    cap.release()
    acc = sum(1 for _, g in rows if g == "accepted")
    with open(out_json, "w") as fh:
        json.dump({"clip": clip, "resized_to": [w, h], "sampled": len(rows),
                   "accepted": acc, "rows": rows}, fh)
    print("DONE %s -> %dx%d accepted %d / %d" % (clip, w, h, acc, len(rows)), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]),
         int(sys.argv[5]) if len(sys.argv) > 5 else 200)
