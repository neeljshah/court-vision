#!/usr/bin/env python3
"""G316 attempt 2 -- scoreboard game-clock liveness. MEASUREMENT ONLY, additive.

Sealed design: docs/evidence/tracking/g316_preregistration_attempt2_2026-09-07.md
(SHA-256 23a01551e94d1ab3cbd8e0ab7655886547a53f762c5acf0ea688d244b0820fc4).

Reads only. Writes JSON/JSONL/PNG under --out. Never writes data/, never edits
src/, never touches a ledger. Makes NO recall, precision, registration,
tracking-quality or harness-pass claim. All four stages run on the POD (prereg
section 2 names the machine split and the reason): `premise` censuses
scoreboard_game_clock / scoreboard_period; `extract` writes evenly-spaced frames
by timestamp plus a manifest; `score` applies the presence rule then EasyOCR over
R1..R4; `sheet` renders 20 tiles evenly spaced over the FULL sample.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess

# ---- sealed constants (prereg sections 3-6) ---------------------------------
REGIONS = {
    "TOP":      (0.00, 1.00, 0.00, 0.16),
    "BOT":      (0.00, 1.00, 0.78, 1.00),
    "BOTLEFT":  (0.00, 0.55, 0.78, 1.00),
    "BOTRIGHT": (0.45, 1.00, 0.78, 1.00),
}
WHITE_MIN = 200          # min(B,G,R) >= this is "near-white"
EDGE_MIN = 40            # |d(gray)/dy| >= this is a strong horizontal step
PRESENT_WHITE = 0.04     # sealed threshold on white(BOT)
PRESENT_EDGE = 0.07      # sealed threshold on edge(BOT)
CONF_MIN = 0.30          # == _OCR_CONF_MIN in src/tracking/scoreboard_ocr.py
UPSCALE = 4
HANDCHECK_K = 20
RECORD_KEYS = ("clip", "skin", "j", "t_sec", "png", "sha256", "white_bot",
               "edge_bot", "scoreboard_present", "region_set", "ocr_text",
               "parsed_clock", "clock_seconds", "parsed_period", "ocr_confidence",
               "reader")


def crop(frame, box):
    h, w, (x0, x1, y0, y1) = frame.shape[0], frame.shape[1], box
    return frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]


def white_row(reg) -> float:
    """Max over rows of the near-white pixel fraction. Sealed statistic."""
    if reg.size == 0:
        return 0.0
    return float((reg.min(axis=2) >= WHITE_MIN).mean(axis=1).max())


def edge_row(reg) -> float:
    """Max over rows of the strong-vertical-step column fraction. Sealed."""
    import cv2
    import numpy as np
    if reg.size == 0 or reg.shape[0] < 2:
        return 0.0
    g = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY).astype(np.int16)
    d = np.abs(np.diff(g, axis=0)) >= EDGE_MIN
    return float(d.mean(axis=1).max()) if d.size else 0.0


def is_present(white: float, edge: float) -> bool:
    return white >= PRESENT_WHITE and edge >= PRESENT_EDGE


def wilson(k: int, n: int):
    """95 pct Wilson interval. (lo, hi) or (None, None) on an empty n."""
    if n == 0:
        return None, None
    z, p = 1.959963984540054, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)


# ---- stage premise ---------------------------------------------------------
def premise(root: str, clips) -> dict:
    out = {}
    for cid in clips:
        path = os.path.join(root, "data", "tracking", cid, "tracking_data.csv")
        n = c = pf = 0
        per, dur = {}, 0.0
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                n += 1
                if (row.get("scoreboard_game_clock") or "").strip():
                    c += 1
                v = (row.get("scoreboard_period") or "").strip()
                if v:
                    pf, per[v] = pf + 1, per.get(v, 0) + 1
                try:
                    dur = max(dur, float(row.get("source_duration") or 0))
                except (TypeError, ValueError):
                    pass
        out[cid] = {"table": path, "N_rows": n, "scoreboard_game_clock_filled": c,
                    "scoreboard_period_filled": pf, "distinct_periods": sorted(per),
                    "period_value_counts": per, "clip_seconds": round(dur, 2)}
    return out


# ---- stage extract ----------------------------------------------------------
def _ffprobe(path, entries, sel):
    cmd = ["ffprobe", "-v", "error"] + sel + ["-show_entries", entries, "-of",
                                              "csv=p=0", path]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def extract(corpus: str, clip: str, k: int, out_dir: str) -> dict:
    """Sealed sampling rule: t_j = D * (j + 0.5) / k, evenly spaced, no head slice."""
    path = os.path.join(corpus, clip + ".mp4")
    dur = float(_ffprobe(path, "format=duration", []).split("\n")[0])
    wh = _ffprobe(path, "stream=width,height", ["-select_streams", "v:0"])
    w, h = (int(x) for x in wh.split("\n")[0].split(","))
    os.makedirs(out_dir, exist_ok=True)
    recs = []
    for j in range(k):
        t = dur * (j + 0.5) / k
        dst = os.path.join(out_dir, "%s__f%03d.png" % (clip, j))
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", "%.6f" % t,
                        "-i", path, "-frames:v", "1", "-y", dst], check=True)
        with open(dst, "rb") as fh:
            sha = hashlib.sha256(fh.read()).hexdigest()
        recs.append({"clip": clip, "j": j, "t_sec": round(t, 6),
                     "png": os.path.basename(dst), "sha256": sha})
    return {"clip": clip, "path": path, "bytes": os.path.getsize(path),
            "width": w, "height": h, "duration_sec": round(dur, 6),
            "k": k, "frames": recs}


# ---- stage score ------------------------------------------------------------
def production_parser(root=None):
    """`_parse_scoreboard_text` loaded VERBATIM from src/tracking/scoreboard_ocr.py
    by file path: read, never edited, and its package __init__ chain is not run."""
    import importlib.util, sys  # noqa: E401
    root = root or os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..", ".."))
    src = os.path.join(root, "src", "tracking", "scoreboard_ocr.py")
    spec = importlib.util.spec_from_file_location("g316_scoreboard_ocr", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # @dataclass resolves via sys.modules
    spec.loader.exec_module(mod)
    return mod._parse_scoreboard_text


def read_frame(rdr, frame):
    """Union of kept tokens over R1..R4, each upscaled UPSCALE x. Sealed."""
    import cv2
    toks, confs = [], []
    for box in REGIONS.values():
        reg = crop(frame, box)
        if reg.size == 0:
            continue
        big = cv2.resize(reg, None, fx=UPSCALE, fy=UPSCALE,
                         interpolation=cv2.INTER_CUBIC)
        for _, txt, cf in rdr.readtext(big, detail=1, paragraph=False):
            if cf >= CONF_MIN:
                toks.append(str(txt))
                confs.append(float(cf))
    conf = round(sum(confs) / len(confs), 4) if confs else None
    return " ".join(toks), conf


def score(frame_dir: str, manifest: dict, skins: dict, out_dir: str, gpu=False):
    import cv2
    import easyocr
    _parse_scoreboard_text = production_parser()
    rdr = easyocr.Reader(["en"], gpu=gpu, verbose=False)  # prereg s6 + amendment 1
    recs = []
    for clip_man in manifest:
        clip = clip_man["clip"]
        for fr_rec in clip_man["frames"]:
            frame = cv2.imread(os.path.join(frame_dir, fr_rec["png"]))
            bot = crop(frame, REGIONS["BOT"])
            wr, er = white_row(bot), edge_row(bot)
            text, conf = read_frame(rdr, frame)
            st = _parse_scoreboard_text(text)
            sec = st["game_clock_sec"]
            recs.append({
                "clip": clip, "skin": skins.get(clip, clip), "j": fr_rec["j"],
                "t_sec": fr_rec["t_sec"], "png": fr_rec["png"],
                "sha256": fr_rec["sha256"], "white_bot": round(wr, 4),
                "edge_bot": round(er, 4), "ocr_text": text, "ocr_confidence": conf,
                "scoreboard_present": bool(is_present(wr, er)),
                "region_set": {k: list(v) for k, v in REGIONS.items()},
                "parsed_clock": (None if sec <= 0 else
                                 "%d:%02d" % (int(sec) // 60, int(sec) % 60)),
                "clock_seconds": (None if sec <= 0 else float(sec)),
                "parsed_period": (None if st["period"] < 0 else int(st["period"])),
                "reader": "easyocr==1.7.2 " + ("cuda" if gpu else "cpu")})
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "g316_frame_records.jsonl"), "w") as fh:
        fh.writelines(json.dumps(r, sort_keys=True) + "\n" for r in recs)
    return summarise(recs, out_dir)


def summarise(recs, out_dir: str) -> dict:
    per, pooled_k, pooled_n = {}, 0, 0
    for r in recs:
        s = per.setdefault(r["skin"], {"sampled": 0, "present": 0, "rejected": 0,
                                       "parsed": 0, "unique_frames": set()})
        s["sampled"] += 1
        s["unique_frames"].add((r["clip"], r["j"]))
        if r["scoreboard_present"]:
            s["present"] += 1
            if r["clock_seconds"] is not None:
                s["parsed"] += 1
        else:
            s["rejected"] += 1
    for s in per.values():
        s["unique_frames"] = len(s["unique_frames"])
        s["parsed_clock_rate"] = (round(s["parsed"] / s["present"], 4)
                                  if s["present"] else None)
        s["wilson95"] = wilson(s["parsed"], s["present"])
        pooled_k, pooled_n = pooled_k + s["parsed"], pooled_n + s["present"]
    out = {"n_sampled": len(recs), "n_unique": len({(r["clip"], r["j"]) for r in recs}),
           "per_skin": per, "pooled_present": pooled_n, "pooled_parsed": pooled_k,
           "pooled_parsed_clock_rate": (round(pooled_k / pooled_n, 4)
                                        if pooled_n else None),
           "pooled_wilson95": wilson(pooled_k, pooled_n), "bar": 0.90}
    json.dump(out, open(os.path.join(out_dir, "g316_liveness_summary.json"),
                   "w"), indent=1)
    return out


# ---- stage sheet ------------------------------------------------------------
def sheet(frame_dir: str, out_dir: str, cols: int = 4) -> dict:
    """20 renders EVENLY SPACED over the FULL sample -- not over accepted only."""
    import cv2, numpy as np  # noqa: E401
    recs = [json.loads(l) for l in
            open(os.path.join(out_dir, "g316_frame_records.jsonl")) if l.strip()]
    recs.sort(key=lambda r: (r["clip"], r["j"]))
    idx = [round(j * (len(recs) - 1) / (HANDCHECK_K - 1)) for j in range(HANDCHECK_K)]
    tiles, index = [], []
    for tile_no, i in enumerate(idx):
        r = recs[i]
        img = cv2.imread(os.path.join(frame_dir, r["png"]))
        reg = crop(img, REGIONS["BOT"])
        big = cv2.resize(reg, (1200, max(1, int(1200 * reg.shape[0] / reg.shape[1]))),
                         interpolation=cv2.INTER_CUBIC)
        cv2.rectangle(big, (0, 0), (150, 26), (0, 0, 0), -1)
        cv2.putText(big, "t%02d" % tile_no, (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 255), 2)
        tiles.append(big)
        index.append({"tile": tile_no, "sample_index": i, "clip": r["clip"],
                      "skin": r["skin"], "j": r["j"], "png": r["png"],
                      "scoreboard_present": r["scoreboard_present"],
                      "white_bot": r["white_bot"], "edge_bot": r["edge_bot"],
                      "parsed_clock": r["parsed_clock"], "hand_read_clock": None,
                      "parsed_sec": r["clock_seconds"], "hand_read_sec": None,
                      "abs_error_sec": None})
    th = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, th - t.shape[0], 0, 0, cv2.BORDER_CONSTANT,
                                value=(40, 40, 40)) for t in tiles]
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(os.path.join(out_dir, "g316_handcheck_sheet.png"), np.vstack(rows))
    json.dump(index, open(os.path.join(out_dir, "g316_handcheck_index.json"), "w"),
              indent=1)
    return {"tiles": len(index), "sample_indices": idx}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["premise", "extract",
                                                       "score", "sheet"])
    ap.add_argument("--root", default="/workspace/nba-ai-system")
    ap.add_argument("--corpus", default="/workspace/nba-ai-system/data/footage_corpus")
    ap.add_argument("--frames", default="/tmp/g316/score")
    ap.add_argument("--out", default="/tmp/g316/out")
    ap.add_argument("--clips", nargs="*", default=[])
    ap.add_argument("--skins", default="{}")
    ap.add_argument("--k", type=int, default=100)  # frames per clip (prereg s3)
    ap.add_argument("--gpu", action="store_true")  # prereg amendment 1 (device)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    if a.stage == "premise":
        res = premise(a.root, a.clips)
        json.dump(res, open(os.path.join(a.out, "g316_premise.json"), "w"), indent=1)
    elif a.stage == "extract":
        res = [extract(a.corpus, c, a.k, a.frames) for c in a.clips]
        json.dump(res, open(os.path.join(a.frames, "manifest.json"), "w"), indent=1)
        res = {"clips": len(res), "frames": sum(m["k"] for m in res)}
    elif a.stage == "score":
        res = score(a.frames, json.load(open(os.path.join(a.frames,
                    "manifest.json"))), json.loads(a.skins), a.out, a.gpu)
    else:
        res = sheet(a.frames, a.out)
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
