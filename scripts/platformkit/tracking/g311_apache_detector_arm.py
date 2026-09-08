"""G311 SCREENING: Apache-2.0 RTMDet arm vs the production AGPL yolov8n arm.

Two person-detection arms on IDENTICAL decoded frames. Image-space proxies only.
NO ground truth: no labels, no renders, no eye check. More boxes can mean more
players found OR more false boxes and this module cannot tell them apart. Nothing
here is recall, precision, registration or a pass, and neither arm may be called
better. G303/G296 are the rows that score recall against labelled frames.

Reads and imports src/ ; never edits it. Writes only under the given --out dir.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking.g311_proxies import (  # re-exported for callers/tests
    IOU_LINK, IOU_MATCH, agreement, frame_indices, greedy_match, iou, link_tracks,
    summarize,
)

PERSON = 0
WARMUP = 3  # frames run before the clock starts, excluded from every ms/frame figure


def probe(path: str) -> dict:
    q = "stream=width,height,avg_frame_rate,nb_frames"
    raw = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", q,
         "-show_entries", "format=duration", "-of", "csv=p=0:s=,", path],
        capture_output=True, text=True, check=True).stdout.strip().splitlines()
    w, h, fps, nbf = raw[0].split(",")[:4]
    return {"path": path, "width": int(w), "height": int(h), "fps": fps,
            "nb_frames": int(nbf), "duration_s": float(raw[-1].split(",")[-1])}


def sha256(path: str) -> str:
    d = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            d.update(chunk)
    return d.hexdigest()


def last_decodable(cap, nb_frames: int) -> int:
    """Highest index cv2 can seek AND read. ffprobe nb_frames overcounts the
    seekable range by up to 132 frames on this corpus, so the frame list's top
    anchor is MEASURED, never trusted."""
    import cv2

    def readable(i: int) -> bool:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        return cap.read()[0]
    lo, hi = 0, nb_frames - 1
    if readable(hi):
        return hi
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if readable(mid) else (lo, mid)
    return lo


def decode(path: str, nb_frames: int, k: int) -> tuple[list[np.ndarray], list[int]]:
    """Decode k evenly spaced frames spanning 0 .. the LAST DECODABLE index. A
    failed read is FATAL, never dropped: both arms must see the same frame list
    and the declared denominator must not shrink unobserved."""
    import cv2
    cap = cv2.VideoCapture(path)
    idxs = frame_indices(last_decodable(cap, nb_frames) + 1, k)
    out, failed = [], []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if ok:
            out.append(frame)
        else:
            failed.append(i)
    cap.release()
    if failed:
        raise RuntimeError(f"{path}: {len(failed)} of {len(idxs)} frames failed to decode: {failed}")
    return out, idxs


def run_yolo(frames: list[np.ndarray]) -> tuple[list[np.ndarray], list[float], float]:
    """ARM Y: the gated FeetDetector, imported unedited, called as line 118 calls it."""
    import torch
    from src.tracking.player_detection import FeetDetector
    det = FeetDetector([])
    call = lambda f: det.model(f, classes=[PERSON], conf=0.3, verbose=False,
                              imgsz=getattr(det, "_infer_imgsz", 640),
                              half=det._use_half, device=det._device)
    for _ in range(WARMUP):  # excluded from ms/frame
        call(frames[0])
    torch.cuda.reset_peak_memory_stats()
    boxes, ms = [], []
    for f in frames:
        t = time.perf_counter()
        r = call(f)
        ms.append((time.perf_counter() - t) * 1000.0)
        b = r[0].boxes
        boxes.append(b.xyxy.cpu().numpy() if b is not None else np.zeros((0, 4)))
    peak = torch.cuda.max_memory_allocated() / 1e6
    del det
    torch.cuda.empty_cache()
    return boxes, ms, peak


# torch 2.6+ defaults torch.load to weights_only=True and mmengine 0.10.7 never
# overrides it. weights_only stays TRUE (no arbitrary code execution); the ckpt is
# SHA-256 pinned before load. numpy 2.x aliases numpy.core -> numpy._core, so the
# (obj, dotted) form is required or these names never match.
CKPT_SAFE_GLOBALS = (
    "mmengine.logging.history_buffer.HistoryBuffer",
    "numpy.core.multiarray._reconstruct",
    "numpy.ndarray",
    "numpy.dtype",
    "numpy.dtypes.Float64DType",
    "numpy.dtypes.Int64DType",
    "numpy.core.multiarray.scalar",
)


def allowlist_ckpt_globals() -> None:
    """Allowlist exactly the globals this pinned checkpoint needs, nothing wider."""
    import importlib

    import torch
    for dotted in CKPT_SAFE_GLOBALS:
        mod, _, name = dotted.rpartition(".")
        obj = getattr(importlib.import_module(mod), name)
        torch.serialization.add_safe_globals([(obj, dotted)])


def run_rtmdet(frames: list[np.ndarray], config: str, ckpt: str, score: float
               ) -> tuple[list[np.ndarray], list[float], float]:
    """ARM R: Apache-2.0 RTMDet through mmdet, person class only."""
    import torch
    from mmdet.apis import inference_detector, init_detector
    allowlist_ckpt_globals()
    model = init_detector(config, ckpt, device="cuda:0")
    for _ in range(WARMUP):  # excluded from ms/frame
        inference_detector(model, frames[0])
    torch.cuda.reset_peak_memory_stats()
    boxes, ms = [], []
    for f in frames:
        t = time.perf_counter()
        res = inference_detector(model, f)
        ms.append((time.perf_counter() - t) * 1000.0)
        inst = res.pred_instances
        keep = (inst.labels.cpu().numpy() == PERSON) & (inst.scores.cpu().numpy() >= score)
        boxes.append(inst.bboxes.cpu().numpy()[keep])
    peak = torch.cuda.max_memory_allocated() / 1e6
    del model
    torch.cuda.empty_cache()
    return boxes, ms, peak


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", nargs="+", required=True)
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--rtmdet-config", required=True)
    ap.add_argument("--rtmdet-ckpt", required=True)
    ap.add_argument("--rtmdet-score", type=float, default=0.3)
    ap.add_argument("--gated-src", default="src/tracking/player_detection.py")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {"screening_only": True, "ground_truth": "NONE",
              "iou_match": IOU_MATCH, "iou_link": IOU_LINK,
              "gated_src_sha256_before": sha256(a.gated_src),
              "rtmdet_ckpt_sha256": sha256(a.rtmdet_ckpt), "games": []}
    print("SCREENING ONLY -- no labels, no renders, no eye check; neither arm is better.")

    for vid in a.videos:
        meta = probe(vid)
        frames, idxs = decode(vid, meta["nb_frames"], a.frames)
        t0 = time.time()
        by, my, vy = run_yolo(frames)
        br, mr, vr = run_rtmdet(frames, a.rtmdet_config, a.rtmdet_ckpt, a.rtmdet_score)
        g = {"game": Path(vid).stem, "source": meta, "frame_indices": idxs,
             "decoded": len(frames), "wall_s": round(time.time() - t0, 1),
             "arm_Y": summarize("Y_yolov8n_AGPL", by, my, round(vy, 1), "torch.cuda.max_memory_allocated"),
             "arm_R": summarize("R_rtmdet_Apache2.0", br, mr, round(vr, 1), "torch.cuda.max_memory_allocated"),
             "agreement": agreement(by, br)}
        report["games"].append(g)
        print(json.dumps(g, default=str))

    report["gated_src_sha256_after"] = sha256(a.gated_src)
    report["gated_src_unchanged"] = report["gated_src_sha256_after"] == report["gated_src_sha256_before"]
    (out / "g311_summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", out / "g311_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
