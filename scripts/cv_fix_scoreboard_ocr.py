"""
cv_fix_scoreboard_ocr.py — Robust score-bug OCR for the NBC/TNT bottom-center bug.

Reads period + game-clock + both team scores per sampled frame from the fixed-position
broadcast score bug, producing the frame<->game-state map that PBP-anchoring needs.
Validated on 0042500315 (WCF G3): period reads at ~1.0 conf; scores/clock high.

Output: data/tracking/<gid>/scoreboard_ocr.csv  (frame, sec, period, clock_sec, okc, sas, *conf)

Usage: python scripts/cv_fix_scoreboard_ocr.py <gid> [--video PATH] [--every 20] [--fps 60]
"""
from __future__ import annotations
import argparse, csv, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2

# Full-frame ROIs (1280x720) for the bottom-center score bug, tuned on 0042500315.
ROIS = {
    "okc":    (505, 600, 620, 666, "0123456789"),
    "sas":    (712, 782, 620, 666, "0123456789"),
    "clock":  (598, 686, 624, 653, "0123456789:"),
    "period": (595, 652, 650, 674, "0123456789STNDRTHO"),
}
_PERIOD_MAP = {"1ST": 1, "2ND": 2, "3RD": 3, "4TH": 4, "OT": 5, "2OT": 6, "3OT": 7}


def parse_clock(txt):
    """'8:18'->498s, '209'->2:09->129s, '1148'->11:48->708s. Returns seconds or None."""
    if not txt:
        return None
    t = txt.replace(" ", "")
    if ":" in t:
        m = re.match(r"^(\d{1,2}):(\d{2})$", t)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        return None
    if t.isdigit():
        if len(t) <= 2:          # ':18' style fragment — ambiguous, skip
            return None
        if len(t) == 3:          # M SS
            return int(t[0]) * 60 + int(t[1:])
        if len(t) == 4:          # MM SS
            return int(t[:2]) * 60 + int(t[2:])
    return None


def parse_period(txt):
    if not txt:
        return None
    t = txt.upper().replace(" ", "")
    if t in _PERIOD_MAP:
        return _PERIOD_MAP.get(t)
    # Fuzzy: EasyOCR reads "1ST" as "TST"/"IST" (the 1 looks like T/I). Match by the
    # ordinal suffix, which is unambiguous (1ST/2ND/3RD/4TH).
    if t.endswith("ST"):
        return 1
    if t.endswith("ND"):
        return 2
    if t.endswith("RD"):
        return 3
    if t.endswith("TH"):
        return 4 if not t.startswith("5") else 5
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gid")
    ap.add_argument("--video", default=None)
    ap.add_argument("--every", type=int, default=20)
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--data-dir", default=None)
    args = ap.parse_args()

    import easyocr
    reader = easyocr.Reader(["en"], gpu=True, verbose=False)

    data_dir = args.data_dir or f"data/tracking/{args.gid}"
    video = args.video or f"data/videos/full_games/{args.gid}.mp4"
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[sb] video={video} frames={total} every={args.every}")

    def ocr_roi(img, x0, x1, y0, y1, allow):
        c = img[y0:y1, x0:x1]
        if c.size == 0:
            return None, 0.0
        c = cv2.resize(c, (c.shape[1] * 4, c.shape[0] * 4), interpolation=cv2.INTER_CUBIC)
        r = reader.readtext(c, allowlist=allow, detail=1, paragraph=False)
        if not r:
            return None, 0.0
        # take highest-confidence token
        best = max(r, key=lambda z: z[2])
        return best[1].strip(), float(best[2])

    rows = []
    import time
    t0 = time.time()
    for fr in range(0, total, args.every):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fr)
        ok, img = cap.read()
        if not ok:
            continue
        vals = {}
        for name, (x0, x1, y0, y1, al) in ROIS.items():
            txt, conf = ocr_roi(img, x0, x1, y0, y1, al)
            vals[name] = (txt, conf)
        per = parse_period(vals["period"][0])
        clk = parse_clock(vals["clock"][0])
        okc = vals["okc"][0] if (vals["okc"][0] or "").isdigit() else None
        sas = vals["sas"][0] if (vals["sas"][0] or "").isdigit() else None
        rows.append({
            "frame": fr, "sec": round(fr / args.fps, 2),
            "period": per, "clock_sec": clk,
            "okc": int(okc) if okc else None, "sas": int(sas) if sas else None,
            "period_conf": vals["period"][1], "clock_conf": vals["clock"][1],
            "okc_conf": vals["okc"][1], "sas_conf": vals["sas"][1],
            "period_raw": vals["period"][0], "clock_raw": vals["clock"][0],
        })
        if len(rows) % 300 == 0:
            print(f"[sb] {len(rows)} sampled, frame {fr}, {time.time()-t0:.0f}s")
    cap.release()

    out = os.path.join(data_dir, "scoreboard_ocr.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    # coverage report
    np_ = sum(1 for r in rows if r["period"])
    nc = sum(1 for r in rows if r["clock_sec"] is not None)
    ns = sum(1 for r in rows if r["okc"] is not None and r["sas"] is not None)
    print(f"[sb] wrote {out}: {len(rows)} rows | period {np_} ({100*np_//max(1,len(rows))}%) "
          f"clock {nc} ({100*nc//max(1,len(rows))}%) scores {ns} ({100*ns//max(1,len(rows))}%)")
    # period histogram
    from collections import Counter
    print("[sb] period hist:", Counter(r["period"] for r in rows if r["period"]))


if __name__ == "__main__":
    main()
