"""G311 SCREENING proxies: pure image-space arithmetic, no I/O and no model.

Split out of g311_apache_detector_arm.py to keep both modules inside the 300-line
PlatformKit rail. NO ground truth lives here: these are proxies, not scores. More
boxes can mean more players found OR more false boxes and this module cannot tell
them apart. Nothing here is recall, precision, registration or a pass.
"""

from __future__ import annotations

import statistics

import numpy as np

IOU_MATCH = 0.5
IOU_LINK = 0.3
PERSON = 0
WARMUP = 3  # frames run before the clock starts, excluded from every ms/frame figure


def iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pairwise IoU between xyxy box arrays a (n,4) and b (m,4) -> (n,m)."""
    if not len(a) or not len(b):
        return np.zeros((len(a), len(b)), dtype=np.float64)
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(area_a[:, None] + area_b[None, :] - inter, 1e-12)


def greedy_match(a: np.ndarray, b: np.ndarray, thr: float = IOU_MATCH) -> list[tuple[int, int]]:
    """Greedy one-to-one pairing by descending IoU; each box consumed at most once."""
    m = iou(a, b)
    pairs: list[tuple[int, int]] = []
    used_a: set[int] = set()
    used_b: set[int] = set()
    order = np.argsort(m, axis=None)[::-1]
    for flat in order:
        i, j = int(flat // max(m.shape[1], 1)), int(flat % max(m.shape[1], 1))
        if m[i, j] < thr:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append((i, j))
    return pairs


def agreement(frames_a: list[np.ndarray], frames_b: list[np.ndarray], thr: float = IOU_MATCH) -> dict:
    """Both-way agreement over a frame-aligned pair of box lists. Denominator is
    every frame: a zero-box frame is NOT dropped, it contributes 0 boxes and 0
    matches. The shares differ when the arms emit different counts; both reported."""
    if len(frames_a) != len(frames_b):
        raise ValueError("arms must be frame-aligned: %d vs %d" % (len(frames_a), len(frames_b)))
    n_a = n_b = matched = 0
    zero_a = zero_b = 0
    for a, b in zip(frames_a, frames_b):
        n_a += len(a)
        n_b += len(b)
        zero_a += int(len(a) == 0)
        zero_b += int(len(b) == 0)
        matched += len(greedy_match(a, b, thr))
    return {
        "frames": len(frames_a),
        "boxes_a": n_a,
        "boxes_b": n_b,
        "matched": matched,
        "agree_a_in_b": (matched / n_a) if n_a else None,
        "agree_b_in_a": (matched / n_b) if n_b else None,
        "zero_box_frames_a": zero_a,
        "zero_box_frames_b": zero_b,
    }


def link_tracks(frames: list[np.ndarray], thr: float = IOU_LINK) -> dict:
    """Greedy IoU-linking tracker, identical parameters for both arms."""
    lengths: dict[int, int] = {}
    live: list[tuple[int, np.ndarray]] = []
    next_id = 0
    for boxes in frames:
        cur = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
        prev = np.array([b for _, b in live], dtype=np.float64).reshape(-1, 4)
        pairs = dict((j, live[i][0]) for i, j in greedy_match(prev, cur, thr))
        new_live = []
        for j in range(len(cur)):
            tid = pairs.get(j)
            if tid is None:
                tid, next_id = next_id, next_id + 1
            lengths[tid] = lengths.get(tid, 0) + 1
            new_live.append((tid, cur[j]))
        live = new_live
    return {
        "distinct_ids": len(lengths),
        "median_track_length": statistics.median(lengths.values()) if lengths else None,
    }


def summarize(name: str, frames: list[np.ndarray], ms: list[float], vram_mb, vram_how: str) -> dict:
    n = len(frames)
    total = sum(len(f) for f in frames)
    out = {
        "arm": name,
        "decoded_frames": n,
        "boxes_total": total,
        "boxes_per_frame": (total / n) if n else None,
        "zero_box_frames": sum(1 for f in frames if not len(f)),
        "ms_per_frame": (sum(ms) / len(ms)) if ms else None,
        "peak_vram_mb": vram_mb,
        "vram_method": vram_how,
    }
    out.update(link_tracks(frames))
    return out


def frame_indices(nb_frames: int, k: int) -> list[int]:
    """k evenly spaced indices across the whole clip, no head slice."""
    if nb_frames <= 0 or k <= 0:
        return []
    if nb_frames <= k:
        return list(range(nb_frames))
    return [round(i * (nb_frames - 1) / (k - 1)) for i in range(k)]
