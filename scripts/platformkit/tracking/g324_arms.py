"""G324 SCREENING arms: person detection through two stacks, single AND batched.

Split out of g324_apache_arm_rebudget.py to keep both modules inside the 300-line
PlatformKit rail. NO ground truth lives here: these are proxies, not scores. More
boxes can mean more players found OR more false boxes and this module cannot tell
them apart. Nothing here is recall, precision, registration or a pass, and neither
arm may be called better.

The detector-agnostic part is `call(frames) -> [(boxes, scores, classes), ...]`, so
`run_single` / `run_batched` are testable with a synthetic detector and no GPU.

Reads and imports src/ ; never edits it.
"""

from __future__ import annotations

import time

import numpy as np

from scripts.platformkit.tracking.g311_apache_detector_arm import (  # inherited, not copied
    PERSON, WARMUP, allowlist_ckpt_globals,
)

BATCH = 8  # sealed in g324_prereg_2026-09-07.md; not movable


def chunk(seq: list, n: int) -> list[list]:
    """Contiguous chunks of n; the last chunk may be short. Every element kept."""
    if n <= 0:
        raise ValueError("batch size must be positive")
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def run_single(frames: list, call) -> tuple[list, float | None]:
    """One frame per detector call. Mean ms over calls; warm-up is the caller's job."""
    rows, ms = [], []
    for f in frames:
        t = time.perf_counter()
        r = call([f])
        ms.append((time.perf_counter() - t) * 1000.0)
        rows.append(r[0])
    return rows, (sum(ms) / len(ms)) if ms else None


def run_batched(frames: list, call, bs: int = BATCH) -> tuple[list, float | None]:
    """Same call over chunks of bs. ms/frame = TOTAL elapsed / frames, so the figure
    is comparable with run_single's per-frame mean. A zero-box frame still occupies
    its slot in the returned rows and its share of the denominator."""
    rows: list = []
    t = time.perf_counter()
    for c in chunk(frames, bs):
        rows.extend(call(c))
    total = (time.perf_counter() - t) * 1000.0
    if len(rows) != len(frames):
        raise RuntimeError("batched pass returned %d rows for %d frames" % (len(rows), len(frames)))
    return rows, (total / len(frames)) if frames else None


def batch_vs_single(single_rows: list, batch_rows: list) -> dict:
    """Did batching change the boxes, or only the cost? Reported, never assumed."""
    same_counts = all(len(a[0]) == len(b[0]) for a, b in zip(single_rows, batch_rows))
    delta = 0.0
    for a, b in zip(single_rows, batch_rows):
        if len(a[0]) == len(b[0]) and len(a[0]):
            delta = max(delta, float(np.abs(np.asarray(a[0]) - np.asarray(b[0])).max()))
    return {"identical_box_counts": bool(same_counts),
            "max_abs_coord_delta_px": delta if same_counts else None}


def rows_to_csv(rows: list, idxs: list[int], path) -> int:
    """Raw box rows for coordinate-level reproduction (G311-RAW-BOX-DURABILITY).
    Every box behind the reported counts, one line each; returns the row count."""
    n = 0
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("frame_index,x1,y1,x2,y2,score,class\n")
        for i, (boxes, scores, classes) in zip(idxs, rows):
            for b, s, c in zip(np.asarray(boxes).reshape(-1, 4), scores, classes):
                fh.write("%d,%.3f,%.3f,%.3f,%.3f,%.6f,%d\n"
                         % (i, b[0], b[1], b[2], b[3], float(s), int(c)))
                n += 1
    return n


def measure(call, frames: list) -> dict:
    """Warm-up excluded and SAID to be excluded. The single-image pass is the box
    source of record; the batch-8 pass over the SAME frames is a COST measurement."""
    import torch
    for _ in range(WARMUP):
        call([frames[0]])
    torch.cuda.reset_peak_memory_stats()
    rows, ms = run_single(frames, call)
    brows, bms = run_batched(frames, call)
    return {"rows": rows, "ms_per_frame": ms, "ms_per_frame_batch8": bms,
            "batch_size": BATCH, "peak_vram_mb": round(torch.cuda.max_memory_allocated() / 1e6, 1),
            "vram_method": "torch.cuda.max_memory_allocated", "warmup_frames_excluded": WARMUP,
            "batch_vs_single": batch_vs_single(rows, brows)}


def yolo_call(conf: float = 0.3):
    """ARM Y: the gated FeetDetector, imported unedited, its own settings."""
    from src.tracking.player_detection import FeetDetector
    det = FeetDetector([])

    def call(fs: list) -> list:
        res = det.model(fs, classes=[PERSON], conf=conf, verbose=False,
                        imgsz=getattr(det, "_infer_imgsz", 640),
                        half=det._use_half, device=det._device)
        out = []
        for r in res:
            b = r.boxes
            if b is None or not len(b):
                out.append((np.zeros((0, 4)), np.zeros(0), np.zeros(0)))
            else:
                out.append((b.xyxy.cpu().numpy(), b.conf.cpu().numpy(), b.cls.cpu().numpy()))
        return out
    return call, det


def rtmdet_call(config: str, ckpt: str, score: float = 0.3):
    """ARM R: Apache-2.0 RTMDet through mmdet, person class only."""
    from mmdet.apis import inference_detector, init_detector
    allowlist_ckpt_globals()  # weights_only STAYS TRUE; ckpt SHA-256 verified by the caller
    model = init_detector(config, ckpt, device="cuda:0")

    def call(fs: list) -> list:
        res = inference_detector(model, fs)
        if not isinstance(res, list):
            res = [res]
        out = []
        for r in res:
            inst = r.pred_instances
            lab = inst.labels.cpu().numpy()
            sc = inst.scores.cpu().numpy()
            keep = (lab == PERSON) & (sc >= score)
            out.append((inst.bboxes.cpu().numpy()[keep], sc[keep], lab[keep]))
        return out
    return call, model
