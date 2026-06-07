"""
unified_pipeline.py — Full NBA AI tracking pipeline

Combines:
  - AdvancedFeetDetector: player tracking (YOLOv8 + Kalman + Hungarian + OSNet ReID)
  - YOLOv8n detection: ball, rim, shot-attempt, made-basket (when weights available)
  - Hough+CSRT ball tracker: fallback when no YOLO weights
  - StatsTracker: shot attempts + made baskets per player

Output: data/tracking_data.csv + data/stats.json
"""

import csv
import json
import logging
import os
import queue
import sys
import threading
import uuid
import warnings
from typing import Optional, List, Dict, Iterator

log = logging.getLogger(__name__)

# Suppress urllib3/requests version mismatch warning (urllib3 2.x vs requests expectation).
# Install: pip install "urllib3<2" to eliminate permanently.
try:
    import requests.packages.urllib3.exceptions as _urllib3_exc
    warnings.filterwarnings(
        "ignore",
        category=_urllib3_exc.RequestsDependencyWarning,
    )
except Exception:
    pass

import cv2
import numpy as np

try:
    import torch as _torch
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

try:
    import kornia
    import kornia.feature as _kf
    import kornia.geometry as _kg
    _HAS_KORNIA = True
except ImportError:
    _HAS_KORNIA = False

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass


# ── F5: PyAV fast frame decoder ───────────────────────────────────────────────

def _pyav_frame_iter(video_path: str, start_frame: int = 0,
                     max_source_frames: int = 0) -> Iterator[tuple]:
    """
    Yield (frame_idx, bgr_array) using PyAV (FFmpeg) for 30-40% faster decode.
    Falls back to cv2.VideoCapture if PyAV is not installed.

    Args:
        max_source_frames: Stop after yielding this many frames (0 = no limit).
            Set to max_gameplay_frames * stride * 3 for long videos to prevent
            PyAV from decoding hundreds of thousands of frames when only the
            first portion of the video contains the needed gameplay.
    """
    try:
        import av  # type: ignore
        container = av.open(video_path)
        stream    = container.streams.video[0]
        fps       = float(stream.average_rate) if stream.average_rate else 30.0
        total     = stream.frames or 0
        frame_idx = 0
        yielded   = 0
        for packet in container.demux(stream):
            for av_frame in packet.decode():
                if frame_idx >= start_frame:
                    bgr = av_frame.to_ndarray(format="bgr24")
                    del av_frame  # release C-layer frame buffer before yield
                    yield frame_idx, bgr, fps, total
                    yielded += 1
                    if max_source_frames and yielded >= max_source_frames:
                        container.close()
                        return
                else:
                    del av_frame
                frame_idx += 1
        container.close()
    except ImportError:
        cap   = cv2.VideoCapture(video_path)
        fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        frame_idx = start_frame
        yielded   = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame_idx, frame, fps, total
            yielded += 1
            if max_source_frames and yielded >= max_source_frames:
                cap.release()
                return
            frame_idx += 1
        cap.release()
    except Exception:
        pass

# ── NVDEC GPU video decoder (decord) + PyAV fallback ─────────────────────────

def _decord_frame_iter(video_path: str, start_frame: int = 0, max_source_frames: int = 0) -> Iterator[tuple]:
    """
    Yield (frame_idx, bgr_array, fps, total) using decord GPU NVDEC decode.

    Falls back to _pyav_frame_iter if decord is not installed or GPU context fails.
    GPU decode with decord is ~2× faster than PyAV CPU decode on NVIDIA hardware.

    L40S optimization: uses batch decode with pre-allocated numpy buffer to
    minimize GPU→CPU copies.  Decodes in chunks of 32 frames via
    vr.get_batch() which is ~3× faster than sequential vr[i] access because
    it amortizes NVDEC kernel launch overhead.  The pre-allocated buffer avoids
    per-frame numpy allocation.

    Respects CUDA_VISIBLE_DEVICES for multi-GPU RunPod setups — always uses
    device 0 (which maps to the correct physical GPU via CUDA_VISIBLE_DEVICES).

    Args:
        video_path:  Path to video file.
        start_frame: First frame index to yield (0-based).

    Yields:
        (frame_idx, bgr_ndarray, fps, total_frames)
    """
    _BATCH_DECODE = 32  # frames per NVDEC batch — saturates L40S decode engine

    try:
        # DISABLED: decord (both GPU and CPU ctx) leaks ~200 MB/frame in its
        # internal C++ buffer pool.  get_batch() retains frame buffers even after
        # the Python ndarray is deleted.  Confirmed via tracemalloc + RSS monitoring
        # (Session 35, 2026-04-10).  Fall through to PyAV which is stable at ~2 GB RSS.
        _force_no_decord = os.environ.get("DECORD_ENABLE", "0") != "1"
        if _force_no_decord:
            raise ImportError("decord disabled — use DECORD_ENABLE=1 to override")
        from decord import VideoReader, gpu, cpu  # type: ignore
        import os as _os_dec
        _use_gpu_ctx = False
        if _os_dec.environ.get("DECORD_GPU", "0") == "1":
            try:
                vr = VideoReader(video_path, ctx=gpu(0), num_threads=1)
                _use_gpu_ctx = True
            except Exception:
                vr = VideoReader(video_path, ctx=cpu(0), num_threads=2)
        else:
            vr = VideoReader(video_path, ctx=cpu(0), num_threads=2)

        fps = float(vr.get_avg_fps())
        total = len(vr)

        # Pre-allocate reusable BGR buffer (avoids per-frame allocation)
        _bgr_buf = None

        # Batch decode: get_batch() amortizes NVDEC kernel launch overhead
        for batch_start in range(start_frame, total, _BATCH_DECODE):
            batch_end = min(batch_start + _BATCH_DECODE, total)
            indices = list(range(batch_start, batch_end))
            try:
                batch_raw = vr.get_batch(indices)
                # Try to get frames as torch CUDA tensors (zero-copy DLPack)
                if _use_gpu_ctx and _HAS_TORCH:
                    try:
                        frames_rgb = _torch.from_dlpack(batch_raw)  # (N,H,W,3) CUDA
                        # RGB→BGR via channel flip on GPU
                        frames_bgr = frames_rgb[:, :, :, [2, 1, 0]]
                        for j, frame_idx in enumerate(indices):
                            yield frame_idx, frames_bgr[j].cpu().numpy(), fps, total
                        del frames_rgb, frames_bgr
                        continue
                    except Exception:
                        pass  # DLPack not supported in this decord version
                # Fallback: asnumpy (GPU→CPU copy)
                frames_rgb = batch_raw.asnumpy()
            except Exception:
                # Fallback to sequential on batch failure (edge case: last few frames)
                for i in indices:
                    try:
                        frame_rgb = vr[i].asnumpy()
                        bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                        yield i, bgr, fps, total
                    except Exception:
                        continue
                continue

            for j, frame_idx in enumerate(indices):
                rgb_frame = frames_rgb[j]
                # Reuse buffer when shape matches (avoids allocation on every frame)
                if _bgr_buf is None or _bgr_buf.shape != rgb_frame.shape:
                    _bgr_buf = np.empty_like(rgb_frame)
                cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR, dst=_bgr_buf)
                yield frame_idx, _bgr_buf, fps, total

            del frames_rgb  # release batch immediately

        return
    except Exception:
        pass  # decord unavailable or GPU context failed — fall through to PyAV

    yield from _pyav_frame_iter(video_path, start_frame, max_source_frames=max_source_frames)


# ── Async frame prefetcher ────────────────────────────────────────────────────

class _FramePrefetcher:
    """
    Background daemon thread that decodes video frames ahead of the tracker.

    While the tracking thread processes frame N, the decode thread is already
    decoding frames N+1 through N+queue_size.  This overlaps I/O-bound decode
    with GPU-bound tracking compute, yielding ~20-40% end-to-end fps improvement.

    Primary decoder: decord GPU NVDEC (if available).
    Fallback:        PyAV CPU (or cv2 if PyAV unavailable).

    When stride > 1, the decode loop skips (stride-1) frames between each
    queued frame so that NVDEC only decodes ~1/stride of the total video frames.
    Skipping at decode time saves both GPU NVDEC bandwidth and system memory.

    Usage:
        pf = _FramePrefetcher(video_path, start_frame, stride=3)
        ok, frame, frame_idx = pf.read()  # returns (False, None, -1) sentinel at EOF — never use frame_idx when ok=False
        pf.release()                       # no-op; daemon thread dies with process

    Args:
        video_path:   Path to input video.
        start_frame:  First frame index to decode (0-based).
        queue_size:   Frames to buffer ahead of the tracker (default 8).
        stride:       Only decode every Nth frame (default 1 = all frames).
    """

    _SENTINEL = (False, None, -1)  # signals end-of-video to the consumer

    def __init__(
        self,
        video_path: str,
        start_frame: int = 0,
        queue_size: int = 8,
        stride: int = 1,
        max_source_frames: int = 0,
    ) -> None:
        self._stride = max(1, stride)
        self._q = queue.Queue(maxsize=queue_size)
        self._thread = threading.Thread(
            target=self._decode_loop,
            args=(video_path, start_frame, max_source_frames),
            daemon=True,
            name="FramePrefetcher",
        )
        self._thread.start()

    def _decode_loop(self, video_path: str, start_frame: int,
                     max_source_frames: int = 0) -> None:
        """Background: decode frames (respecting stride) and put into queue."""
        try:
            for _fi, bgr, _fps, _total in _decord_frame_iter(
                    video_path, start_frame, max_source_frames=max_source_frames):
                # Skip frames that fall outside the stride pattern.
                # Uses absolute frame index so frame_idx downstream is always
                # the real video position (correct for timestamp calculation).
                if self._stride > 1 and (_fi - start_frame) % self._stride != 0:
                    continue
                # Copy: _decord_frame_iter batch decode reuses a buffer, and
                # this frame lives in the queue until the consumer thread reads it.
                self._q.put((True, bgr.copy(), _fi))
        except Exception:
            pass
        # Always push sentinel so consumer can detect EOF
        self._q.put(self._SENTINEL)

    def read(self) -> tuple:
        """
        Return next stride-frame as (ok, bgr, frame_idx).

        Blocks briefly until a frame is available.
        Returns (False, None, -1) at EOF.

        frame_idx is the absolute video frame number (0-based), not a
        processed-frame counter — callers should use it directly as the
        frame position for CSV timestamps and position dictionaries.
        """
        return self._q.get()

    def peek(self, n: int = 7) -> List[np.ndarray]:
        """Non-blocking peek at up to n queued frames without consuming them.

        Returns list of BGR frames (copies). Used by YOLO prefetch to batch
        upcoming frames for GPU inference while the current frame is processed.
        """
        frames: List[np.ndarray] = []
        with self._q.mutex:
            for item in list(self._q.queue)[:n]:
                ok, bgr, _fi = item
                if ok and bgr is not None:
                    frames.append(bgr.copy())
        return frames

    def release(self) -> None:
        """No-op — daemon thread exits when the process terminates."""
        pass


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)  # Required: src.* imports need project root on sys.path (not installed as package)

from src.tracking import (
    Player, AdvancedFeetDetector, BallDetectTrack,
    COLORS, hsv2bgr, TOPCUT,
    binarize_erode_dilate, rectangularize_court, rectify, add_frame,
    evaluate_tracking,
)
from src.tracking.event_detector import EventDetector
from src.tracking.court_detector import detect_court_homography
from src.tracking.scoreboard_ocr import ScoreboardOCR
from src.tracking.possession_classifier import PossessionClassifier
from src.tracking.play_type_classifier import PlayTypeClassifier
from src.stats_tracker.tracker import StatsTracker

try:
    from scipy.spatial import ConvexHull as _ConvexHull
    _SCIPY = True
except ImportError:
    _SCIPY = False

_RESOURCES = os.path.join(PROJECT_DIR, "resources")
_DATA      = os.path.join(PROJECT_DIR, "data")

FLANN = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=50))

# Homography EMA — smooths per-frame SIFT homography to reduce jitter/drift
_H_EMA_ALPHA        = 0.15   # 0 = heavy smooth, 1 = raw (no memory)
                             # Lowered from 0.25: broadcast low-inlier frames (5-7) add
                             # noise; heavier smoothing reduces accumulated drift on long games.
_H_MIN_INLIERS      = 5      # below this → reject and use last-known good M
                             # Restored to 5: 4-inlier matches cause drift over 64k+ frames;
                             # EMA at 0.15 compensates for marginally-matched frames.
_H_RESET_INLIERS    = 40     # ≥ this → hard-reset EMA (very clean SIFT match)
_REANCHOR_INTERVAL  = 60     # court-line drift check every N frames (raised 30→60: court stable)
_REANCHOR_ALIGN_MIN = 0.35   # projected boundary alignment below this → force re-anchor
_SIFT_INTERVAL      = 300    # OPTIMIZATION: 180→300 frames for RunPod GPU saturation.
                             # At stride=3/30fps, SIFT every 300 = every 30 real-time seconds (Kalman stable)
                             # EMA smoothing (α=0.25) keeps homography smooth between updates.
                             # SIFT is pure CPU — reducing frequency frees CPU for decode/IO.
_SIFT_SCALE         = 0.35  # downsample frame before SIFT detect (0.5→0.35: ~2x fewer keypoints, minimal quality loss)
_SIFT_CUT_THRESH    = 0.20  # OPTIMIZATION: 0.15→0.20. Stricter histogram gate, skip more non-cut frames

# Replay/cut detector — suspend homography on scene cuts, replays, or overlay graphics
# BUG3 fix: raised thresholds to reduce false-positive triggers from NBA lower-third graphics.
# L1 gate: 0.4→0.5 (1-_REPLAY_SSIM_THRESH), bright factor: 1.4→1.55, suspend: 30→20 frames.
_REPLAY_SSIM_THRESH    = 0.5   # SSIM below this = scene cut (was 0.6 → L1 gate 0.5 instead of 0.4)
_REPLAY_BRIGHT_FACTOR  = 1.55  # mean-V ratio above this = replay graphic overlay (was 1.4)
_REPLAY_SUSPEND_FRAMES = 20    # frames to hold homography after trigger (was 30)

# Checkpoint — flush tracking rows to CSV every N frames so a crash doesn't lose all data
_CHECKPOINT_INTERVAL = 2000  # ~6 min of gameplay at 5.7fps

# Frame stride — process every Nth frame on long clips to cut compute on broadcast footage
# Configurable via env: NBA_FRAME_STRIDE=5 gives ~35% fewer frames (6fps from 30fps source).
# Acceptable for batch backfill of prop-model features (needs 5-10 fps, not 30/3=10 fps).
# Default stays at 3 — stride=5 is an operator decision for bulk runs, not live inference.
_FRAME_STRIDE       = int(os.environ.get("NBA_FRAME_STRIDE", "3"))
                             # Raised 2→3: players can't meaningfully move in 100ms; events still
                             # detected via accumulation (ball arc, possession change, CSRT tracker).
_FRAME_STRIDE_THRESH = 3000  # frame count above which stride kicks in (~50s @ 60fps)

# Gameplay detection — skip non-play frames (intro, halftime, timeouts, replays)
MIN_GAMEPLAY_PERSONS = 3     # YOLO person count below this → skip frame
_GAMEPLAY_CACHE_FRAMES = 90  # once gameplay confirmed, trust it for N frames (raised 30→90: 3s)

# Shot-clock non-live filter — suppresses ball tracking during replays / halftime.
# When OCR runs (_OCR_INTERVAL=15 frames) and finds no shot clock for this many
# consecutive scans, ball tracking is suspended until the clock reappears.
# Guard: suspension only fires if the clock was seen at least once on this clip
# (safety net for clips where ScoreboardOCR can't read the broadcast font at all).
# Lowered from 200→60 (60×30=1800 frames≈3 real min): frozen-clock detection
# (3 consecutive OCR scans without clock advance) now handles the 30-40s OCR-miss
# case; this threshold is a last-resort fallback for complete OCR blindness only.
# 3 minutes of full OCR blindness is a reasonable trigger before forcing suspension.
_SHOT_CLOCK_ABSENT_THRESHOLD = 60
_PANO_SCAN_INTERVAL  = 150   # check every N frames when scanning for gameplay (5s @ 30fps)
_PANO_STITCH_FRAMES  = 30    # consecutive frames to stitch into panorama

# Basket positions (normalised 0–1 of 2D court width/height, full-court top-down)
_BASKET_L            = (0.045, 0.5)   # left-baseline basket
_BASKET_R            = (0.955, 0.5)   # right-baseline basket
_DRIVE_VEL_THRESHOLD  = 3.0           # px/frame toward basket → counts as a drive
_ISOLATION_DEFAULT    = 99.0          # ft — "wide open" sentinel when no opponents detected
                                      # (was 200.0 px before unit-normalization fix 2026-05-26;
                                      #  99 ft = wider than half-court → physically impossible real value)
_SPACING_NORM         = 4700.0        # ft² reference area (half-court ≈ 47×50 ft = 2350 ft², ×2 for full)
_FAST_BREAK_VEL_MIN  = 3.5            # px/frame team-mean toward basket → fast break
# Bug 11/24 fix: per-buffer pixel-vs-feet scale guard (matches tracking_feature_extractor.py).
# Real court max: spacing ~4700 ft², off_ball_distance ~50 ft. Threshold=80 separates feet from pixels.
_BUF_PX_TO_FT        = 18.8           # 940px / 50ft — short-axis constant (same as tracking_feature_extractor._PX_TO_FT)
_BUF_PIXEL_THRESHOLD = 80.0           # values above this are pixel-scale, not feet-scale
# Directional gate: ball velocity must point within arccos(threshold) of the
# nearest basket to count as a shot.  Pass arcs aimed at a teammate score near 0.
# Tunable via NBA_SHOT_DIRECTIONAL_COS_MIN env var (float, default 0.3 ≈ 72°).
_SHOT_DIRECTIONAL_COS_MIN: float = float(
    os.environ.get("NBA_SHOT_DIRECTIONAL_COS_MIN", "0.3")
)


def _px_to_ft(px_dist: float, map_w: int) -> float:
    """Convert a 2-D court pixel distance to feet using the long-axis scale (94 ft).

    The panorama long axis corresponds to the court length (94 ft).  All
    distance fields (defender_distance, shot_distance, nearest_opponent, etc.)
    must pass through this helper before being written to CSV so that consumers
    and UIs receive values in feet rather than pixels.

    Args:
        px_dist: Distance in court-2D pixels.
        map_w:   Panorama width in pixels (varies per clip; do NOT use a constant).

    Returns:
        Distance in feet, rounded to one decimal place.
    """
    if map_w <= 0:
        return round(float(px_dist), 1)
    return round(float(px_dist) * 94.0 / map_w, 1)


def _shot_defender_dist_with_id(spatial, shooter, frame_tracks, map_w):
    """P5 (2026-05-29): defender distance + slot id for shot log.

    Returns tuple ``(distance_ft, defender_slot_id)``:
      - distance_ft: "" (missing / out-of-range) or float feet (rounded 1 dp)
      - defender_slot_id: int (1-10 tracker slot) or "" when unknown
            (e.g. spatial._isolation path doesn't track per-defender identity)

    R9 / Bug 1: range and same-team filters preserved from prior single-return version.
    UNBLOCKS INT-57 (A2 defender quality model) which had no training data.
    """
    import math as _math
    iso = spatial.get("_isolation")
    if iso is not None and iso != _ISOLATION_DEFAULT and iso >= 0.5:
        # _isolation is precomputed at frame_spatial time; identity isn't preserved
        # there. Future refactor: extend spatial to track _isolation_defender_id.
        # For now, fall through to per-frame opponent scan when we need the id.
        # Trade a tiny accuracy delta on already-resolved isolation values for the
        # defender_id signal that downstream models need.
        pass
    sx, sy = shooter.get("x2d"), shooter.get("y2d")
    if sx is None or sy is None:
        return "", ""
    opp = [
        (t["x2d"], t["y2d"], t.get("player_id"))
        for t in frame_tracks
        if t.get("team") is not None
        and t.get("team") not in ("referee", shooter.get("team"))
        and (t.get("x2d"), t.get("y2d")) != (sx, sy)   # R9: exclude shooter duplicate
        and t.get("x2d") is not None and t.get("y2d") is not None
    ]
    # Bug 1 fix 2026-05-28: no same-team fallback (see prior commit comment).
    if not opp:
        return "", ""
    # Find nearest opponent + its slot id
    best_dist_px = float("inf")
    best_slot = ""
    for ox, oy, slot in opp:
        d = _math.hypot(sx - ox, sy - oy)
        if d < best_dist_px:
            best_dist_px = d
            best_slot = slot if slot is not None else ""
    ft = _px_to_ft(best_dist_px, map_w)
    # R9: reject below-physical-min (defender literally on top → coincident track artifact)
    if ft < 0.5:
        return "", ""
    return ft, best_slot


def _shot_defender_dist(spatial, shooter, frame_tracks, map_w):
    """Defender distance for shot log in FEET. Wraps `_shot_defender_dist_with_id`.

    R9: returns "" for any missing / out-of-physical-range value (< 0.5 ft or
    >= 99 ft). NBA min real defender distance is ~0.5 ft; 0.0 was a sentinel
    that leaked into ML and inflated xFG by 15-25% on those rows.

    P5 NOTE: prefer `_shot_defender_dist_with_id` at write sites so the
    defender slot id is captured. This wrapper exists for callers that only
    need the scalar (e.g. _shot_defender_dist_norm).
    """
    # Preserve original spatial._isolation fast path for scalar callers
    iso = spatial.get("_isolation")
    if iso is not None and iso != _ISOLATION_DEFAULT and iso >= 0.5:
        return round(iso, 1)
    dist, _ = _shot_defender_dist_with_id(spatial, shooter, frame_tracks, map_w)
    return dist


def _shot_defender_contest(shooter, frame_tracks, map_w):
    """R11: contest_arm_angle = max arm-raise among defenders within 8 ft of shooter.

    Previous code wrote the SHOOTER's arm-raise here, which is misnamed and
    almost always 0.0 (shooter is in release/follow-through, arms down post-shot
    or arms-at-hip pre-shot). Consumer in `feature_engineering.py:1029-1035`
    treats this as a DEFENDER pressure signal — this realigns producer to match.

    Returns "" if no defenders are within range OR pose data missing for all
    candidates (preserves the R8 missing-vs-zero convention).
    """
    sx, sy = shooter.get("x2d"), shooter.get("y2d")
    if sx is None or sy is None or map_w <= 0:
        return ""
    # 8 ft in court px (94 ft = map_w)
    _near_px = 8.0 * map_w / 94.0
    _near_px_sq = _near_px * _near_px
    max_arm = 0.0
    have_any = False
    for t in frame_tracks:
        if t.get("team") in (None, "referee", shooter.get("team")):
            continue
        tx, ty = t.get("x2d"), t.get("y2d")
        if tx is None or ty is None:
            continue
        if (sx - tx) ** 2 + (sy - ty) ** 2 > _near_px_sq:
            continue
        _raw = t.get("contest_arm_angle")
        if _raw in (None, ""):
            continue
        try:
            _v = float(_raw)
        except (ValueError, TypeError):
            continue
        have_any = True
        if _v > max_arm:
            max_arm = _v
    return round(max_arm, 3) if have_any else ""


def _shot_defender_dist_norm(spatial, shooter, frame_tracks, map_w):
    """Normalised defender distance (0–1 of court length = 94 ft)."""
    d = _shot_defender_dist(spatial, shooter, frame_tracks, map_w)
    if d == "":
        return ""
    # d is now in feet; normalise to 0–1 over 94 ft court length
    return round(d / 94.0, 4)


# ── YOLO-NAS wrapper (optional) ───────────────────────────────────────────────

class YoloDetector:
    """Wraps YOLO-NAS-L. Falls back gracefully if weights missing."""

    LABELS = {1: "ball", 2: "made", 3: "person", 4: "rim", 5: "shoot"}

    def __init__(self, weight_path: str = None):
        self.model = None
        if weight_path and os.path.exists(weight_path):
            try:
                from src.detection.models.detection_model import Yolo_Nas_L
                from src.detection.tools.classes import class_names
                self.model = Yolo_Nas_L(
                    num_classes=len(class_names),
                    checkpoint_path=weight_path
                )
                print(f"YOLO-NAS loaded: {weight_path}")
            except Exception as e:
                print(f"YOLO-NAS load failed ({e}) — using Hough fallback")
        else:
            _msg = (
                "WARN: YOLO-NAS shot-detection weights not found "
                f"(looked for: {weight_path!r}). "
                "Shot-attempt / made-basket detection will be disabled. "
                "Ball tracking is unaffected (uses separate yolov8n_ball engine). "
                "To restore: place YOLO-NAS weights at the configured path."
            )
            log.warning(_msg)
            print(_msg, file=sys.stderr)

    @property
    def available(self) -> bool:
        return self.model is not None

    def predict(self, frame):
        """Returns list of {label, bbox:(x1,y1,x2,y2), confidence}."""
        if not self.available:
            return []
        try:
            results = self.model.predict(frame)
            detections = []
            for row in results.numpy().tolist():
                x1, y1, x2, y2, conf, label = row
                detections.append({
                    "label":      self.LABELS.get(int(label), "unknown"),
                    "bbox":       (float(x1), float(y1), float(x2), float(y2)),
                    "confidence": float(conf),
                    "raw_label":  int(label),
                })
            return detections
        except Exception:
            return []


# ── Main pipeline ─────────────────────────────────────────────────────────────

class UnifiedPipeline:
    """
    Full basketball tracking pipeline.

    Args:
        video_path:         Input video file.
        yolo_weight_path:   Path to YOLO-NAS weights (.pth). Optional.
        max_frames:         Stop after N frames (None = full video).
        show:               Display live window.
        output_video_path:  Write annotated video here. Optional.
    """

    def __init__(
        self,
        video_path: str,
        yolo_weight_path: str = None,
        max_frames: int = None,
        start_frame: int = 0,
        show: bool = True,
        output_video_path: str = None,
        game_id: str = None,
        period: int = 1,
        clip_start_sec: float = 0.0,
        data_dir: str = None,
    ):
        self.video_path        = video_path
        self.max_frames        = max_frames
        self.start_frame       = start_frame
        self.show              = show
        self.output_video_path = output_video_path
        self.game_id              = game_id
        self.period               = period
        self.clip_start_sec       = clip_start_sec
        self.period_start_video_sec: float = 0.0   # set by scoreboard OCR in run()
        self.clip_id              = str(uuid.uuid4())  # unique per pipeline run
        # Fix 2: per-game output directory prevents cross-game CSV overwrites
        self._data_dir = data_dir if data_dir is not None else _DATA

        # Enable cuDNN auto-tuner — finds optimal convolution algorithms for the
        # fixed input sizes used by YOLO and OSNet, yielding ~10-15% throughput gain.
        try:
            import torch
            torch.backends.cudnn.benchmark = True
        except Exception:
            pass

        # ISSUE-010: warn once at startup if DATABASE_URL is absent (PostgreSQL writes will be skipped)
        if not os.environ.get("DATABASE_URL"):
            log.warning(
                "DATABASE_URL not set — _pg_write_tracking_rows will skip (SQLite-only mode). "
                "Set DATABASE_URL=postgresql://... to enable PostgreSQL writes."
            )

        self.yolo    = YoloDetector(yolo_weight_path)
        self.players = self._build_players()

        # Build player detector early — reused for gameplay filter
        self.feet_det = AdvancedFeetDetector(self.players)

        pano = self._load_pano(video_path)

        # Collect frames for per-clip homography detection (ISSUE-017).
        # Cap at 60 frames evenly sampled from the first 3600 frames (60 s at 60fps).
        # Raised from 1800: gameplay starts at frame ~1400 on most broadcast clips,
        # leaving only ~14 court frames at 1800 — not enough for detect_court_homography.
        # At 3600 and step=60, we get ~35 gameplay frames which is sufficient.
        _STARTUP_MAX_FRAMES = 60
        _STARTUP_SCAN_END   = 3600   # 60 s at 60fps
        _startup_cap = cv2.VideoCapture(video_path)
        _total = int(_startup_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        _scan_end = min(_total, _STARTUP_SCAN_END)
        _step = max(1, _scan_end // _STARTUP_MAX_FRAMES)
        _startup_frames: list = []
        for _idx in range(0, _scan_end, _step):
            if len(_startup_frames) >= _STARTUP_MAX_FRAMES:
                break
            _startup_cap.set(cv2.CAP_PROP_POS_FRAMES, _idx)
            _ok, _f = _startup_cap.read()
            if not _ok:
                break
            _startup_frames.append(_f[TOPCUT:])
        _startup_cap.release()

        # M1 recovery state — updated by _build_court and _try_recover_court_M1
        self._last_good_M1:        Optional[np.ndarray] = None
        self._M1_raw_clip:         Optional[np.ndarray] = None  # raw frame→court from court_detector
        self._M1_stale_frames:     int                  = 0
        self._M1_failed_attempts:  int                  = 0  # consecutive detection failures
        # Rolling frame buffer for mid-run court re-detection (5 frames gives more
        # line candidates than a single frame, improving detect_court_homography success rate)
        from collections import deque as _deque
        self._recover_frame_buf: _deque = _deque(maxlen=5)

        self.map_2d, self.M1 = self._build_court(pano, startup_frames=_startup_frames)
        # OPTIMIZATION: pre-allocate map snapshot buffer to avoid per-frame np.copy()
        self._map_snap_buf = self.map_2d.copy()
        self.pano = pano

        self._gameplay_cache_until:    int = 0   # frame index; skip YOLO check before this
        self._no_gameplay_until:       int = 0   # frame index; confirmed non-live before this
        self._gameplay_yolo            = None    # lazy: PyTorch yolov8n at 640 (TRT engine locked at 480)
        self._sc_absent_streak:        int = 0   # consecutive OCR runs with no shot clock
        self._sc_ever_seen:         bool = False  # True once OCR reads a valid shot clock
        self._ball_track_suspended: bool = False  # True during replay / halftime sequences
        # Vision-based non-live fallback: counts consecutive frames where ball is absent
        # and fewer than 8 persons are visible, to detect warmups / ad breaks / halftime
        # on clips where ScoreboardOCR never fires (no readable shot clock font).
        self._no_ball_vision_streak: int = 0

        self.ball_det = BallDetectTrack(self.players)  # Hough fallback

        cap0 = cv2.VideoCapture(video_path)
        fps  = cap0.get(cv2.CAP_PROP_FPS) or 30
        _, f0 = cap0.read(); cap0.release()
        h, w  = (f0[TOPCUT:].shape[:2]) if f0 is not None else (720, 1280)
        self.stats_tracker = StatsTracker(frame_w=w, frame_h=h, fps=fps)

        # Feature matching: kornia KeyNetAffNetHardNet on GPU (preferred),
        # fallback to cv2.SIFT on CPU.
        self._sift_gpu = False
        self._kornia_matcher = None
        self._pano_feats_kornia = None
        # LoFTR disabled by default: allocates ~250MB CPU + ~120MB GPU per worker,
        # and self-attention intermediates fragment the heap badly in multi-worker
        # runs.  SIFT is ~5% slower but uses <10MB.  Set COURTV_NO_LOFTR=0 to re-enable.
        _loftr_disabled = os.environ.get("COURTV_NO_LOFTR", "1") == "1"
        if _HAS_KORNIA and not _loftr_disabled:
            try:
                _dev = "cuda" if _torch.cuda.is_available() else "cpu"
                self._kornia_device = _dev
                self._kornia_matcher = _kf.LoFTR(pretrained="outdoor").to(_dev).eval()
                # Store pano as GPU tensor for LoFTR matching
                _pano_gray = cv2.cvtColor(pano, cv2.COLOR_BGR2GRAY) if len(pano.shape) == 3 else pano
                self._pano_tensor = _torch.from_numpy(_pano_gray).float().unsqueeze(0).unsqueeze(0).to(_dev) / 255.0
                self._sift_gpu = True
                log.info("Homography: using kornia LoFTR (GPU-accelerated)")
            except Exception as _ke:
                log.debug("kornia LoFTR init failed (%s) — falling back to SIFT", _ke)
                self._kornia_matcher = None
        elif _loftr_disabled:
            log.info("Homography: LoFTR disabled (COURTV_NO_LOFTR=1), using SIFT")

        # Always init SIFT as fallback (even when kornia LoFTR is available)
        try:
            sift = cv2.SIFT_create() if hasattr(cv2, "SIFT_create") else cv2.xfeatures2d.SIFT_create()
            self.sift = sift
            self.kp1, self.des1 = sift.compute(pano, sift.detect(pano))
        except Exception:
            sift = cv2.SIFT_create()
            self.sift = sift
            self.kp1, self.des1 = sift.compute(pano, sift.detect(pano))
        self._M_ema:              Optional[np.ndarray] = None
        self._last_ball_2d:       Optional[tuple]      = None  # (x2d, y2d) this frame
        self._frames_since_anchor: int                 = 0
        self._sift_frame_counter:  int                 = 0
        self._sift_last_hist:      Optional[np.ndarray] = None  # Task 1: last SIFT-frame histogram
        # Replay/cut detector state
        self._homography_suspended:    bool             = False
        self._homography_suspend_cnt:  int              = 0
        self._replay_prev_gray_small:  Optional[np.ndarray] = None
        self._replay_prev_brightness:  float            = -1.0
        # BUG3: 2-consecutive-frame confirmation gate — only suspend after 2 frames trigger
        self._replay_trigger_pending_count: int         = 0
        self._last_sb_conf:            float            = 0.0
        # R10: clock-decrement signal for homography over-trigger guard. Populated
        # from scoreboard OCR; gates the replay-detector's suspend transition so
        # genuine live play (clock decrementing) doesn't get blanked when the
        # frame happens to look like a graphic overlay.
        self._last_clock_seconds:      float            = -1.0
        self._prev_clock_seconds:      float            = -1.0

        self.event_det = EventDetector(map_w=self.map_2d.shape[1],
                                       map_h=self.map_2d.shape[0])

        # ── Player identity resolver (requires --game-id) ─────────────────
        self._player_resolver = None
        if game_id:
            try:
                from src.tracking.player_resolver import PlayerResolver
                self._player_resolver = PlayerResolver(game_id=game_id, fps=fps, data_dir=self._data_dir)
                log.debug("PlayerResolver initialised for game %s", game_id)
            except Exception as _pr_exc:
                log.debug("PlayerResolver init failed: %s", _pr_exc)

        # ── Context classifiers ───────────────────────────────────────────
        _fw, _fh = w, h   # frame dims captured above for StatsTracker
        self.scoreboard_ocr = ScoreboardOCR(frame_width=_fw, frame_height=_fh)
        self.scoreboard_ocr.configure(fps=fps, stride=_FRAME_STRIDE)
        self.poss_cls = PossessionClassifier(
            fps=fps,
            map_w=self.map_2d.shape[1],
            map_h=self.map_2d.shape[0],
        )
        self.play_cls = PlayTypeClassifier()

        # Task 4: async checkpoint writer — moves blocking CSV flush off the main loop
        self._ckpt_queue: queue.Queue = queue.Queue()
        self._ckpt_thread = threading.Thread(
            target=self._checkpoint_writer_loop,
            daemon=True,
            name="CheckpointWriter",
        )
        self._ckpt_thread.start()

    # ── setup helpers ─────────────────────────────────────────────────────

    def _build_players(self):
        # 5 green slots (IDs 1-5) + 5 white slots (IDs 6-10) + 1 referee (ID 0).
        # Hungarian matching operates on two distinct team pools so detections
        # classified as "green" or "white" by HSV each route to their own slots.
        players = []
        for i in range(1, 6):
            players.append(Player(i, "green", hsv2bgr(COLORS["green"][2])))
        for i in range(6, 11):
            players.append(Player(i, "white", hsv2bgr(COLORS["white"][2])))
        players.append(Player(0, "referee", hsv2bgr(COLORS["referee"][2])))
        return players

    @staticmethod
    def _auto_pano_path(video_path: str) -> str:
        """Return per-video panorama cache path under resources/panos/."""
        import re
        stem = re.sub(r'[^\w\-]', '_', os.path.splitext(os.path.basename(video_path))[0])[:60]
        pano_dir = os.path.join(_RESOURCES, "panos")
        os.makedirs(pano_dir, exist_ok=True)
        return os.path.join(pano_dir, f"pano_{stem}.png")

    @staticmethod
    def _pano_valid(pano: np.ndarray) -> bool:
        """Return True if the panorama looks like a valid court (landscape, wide enough).

        A usable court pano must be:
        - ≥2000 px wide (to produce a ~2800px rectified court)
        - w/h ratio between 3.0 and 50.0 (basketball court ≈1.88:1, stitching adds width;
          ratio >50 means extreme over-stitch with no court signal; ratio <3 = portrait/wrong)
          Wide-ratio panos (10–50) are salvaged by center-crop in _scan_and_build_pano.
        """
        if pano is None:
            return False
        h, w = pano.shape[:2]
        ratio = w / max(h, 1)
        return w >= 2000 and 3.0 <= ratio <= 50.0

    def _load_pano(self, video_path: str) -> np.ndarray:
        """Load panorama for this video, building it from gameplay frames if needed."""
        # 1. Video-specific cached pano — validate before using
        cached = UnifiedPipeline._auto_pano_path(video_path)
        if os.path.exists(cached):
            pano = cv2.imread(cached)
            if UnifiedPipeline._pano_valid(pano):
                print(f" Pano cache hit: {os.path.basename(cached)}")
                return np.vstack((pano, np.zeros((100, pano.shape[1], 3), dtype=pano.dtype)))
            else:
                h, w = (pano.shape[:2]) if pano is not None else (0, 0)
                print(f" Cached pano {os.path.basename(cached)} invalid ({w}×{h}) — discarding")
                os.remove(cached)

        # 2. Auto-build per-clip pano from this video's gameplay frames.
        print(" No video-specific pano cached — building from gameplay frames...")
        try:
            pano = self._scan_and_build_pano(video_path)
            if UnifiedPipeline._pano_valid(pano):
                return np.vstack((pano, np.zeros((100, pano.shape[1], 3), dtype=pano.dtype)))
            else:
                h, w = pano.shape[:2]
                print(f" Built pano still invalid ({w}×{h}) — falling back to general pano")
        except Exception as e:
            print(f" Per-clip pano build failed ({e}) — falling back to general pano")

        # 3. General fallback — always use pano_enhanced (last resort).
        # IMPORTANT: M1 (Rectify1.npy) is calibrated for the Short4Mosaicing panorama
        # (3698×500px). A per-video broadcast frame (1280×660) would break M1 because
        # M1 maps pano-coordinate-space → 2D court; using a different pano invalidates
        # that mapping and clusters all players into a ~590px wide strip.
        # Broadcast frames give 5–7 SIFT inliers vs pano_enhanced — _H_MIN_INLIERS=5
        # ensures these are accepted rather than falling back to stale EMA.
        for fname in ("pano_enhanced.png", "pano.png"):
            general = os.path.join(_RESOURCES, fname)
            if os.path.exists(general):
                img = cv2.imread(general)
                if UnifiedPipeline._pano_valid(img):
                    print(f" Using general pano (fallback): {fname}")
                    return np.vstack((img, np.zeros((100, img.shape[1], 3), dtype=img.dtype)))

    def _scan_and_build_pano(self, video_path: str) -> np.ndarray:
        """Scan video for gameplay frames, stitch into panorama, cache per-video."""
        import torch
        model     = self.feet_det.model
        use_half  = self.feet_det._use_half

        cap   = cv2.VideoCapture(video_path)
        fps   = cap.get(cv2.CAP_PROP_FPS) or 30
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f" Scanning {total / fps / 60:.1f} min video for gameplay...")

        first_gameplay = -1
        for fno in range(0, total, _PANO_SCAN_INTERVAL):
            cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
            ok, frame = cap.read()
            if not ok:
                break
            frame = frame[TOPCUT:]
            _imgsz = getattr(self.feet_det, "_infer_imgsz", 640)
            r = list(model(frame, classes=[0], conf=0.4, verbose=False,
                           half=use_half, imgsz=_imgsz, stream=True))
            n = len(r[0].boxes) if r[0].boxes is not None else 0
            if n >= MIN_GAMEPLAY_PERSONS:
                first_gameplay = fno
                print(f"  Gameplay at frame {fno} ({fno / fps / 60:.1f} min, {n} people)")
                break

        if first_gameplay < 0:
            cap.release()
            raise RuntimeError(
                "No gameplay detected in video — check that this is an NBA broadcast "
                f"with {MIN_GAMEPLAY_PERSONS}+ players visible on court."
            )

        # Sample frames from a tight window (~5 s) starting at first gameplay.
        # Spreading across the full video caused excessive camera drift → over-wide
        # panoramas (30:1 ratio) that break SIFT homography for individual frames.
        # A short window keeps the camera stable so SIFT has a consistent reference.
        window_frames = min(int(fps * 5), total - first_gameplay)  # 5 s window
        step = max(1, window_frames // _PANO_STITCH_FRAMES)
        stitch_frames = []
        for fno in range(first_gameplay, first_gameplay + window_frames, step):
            if len(stitch_frames) >= _PANO_STITCH_FRAMES:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
            ok, f = cap.read()
            if not ok:
                break
            stitch_frames.append(f[TOPCUT:])
        cap.release()

        print(f" Stitching {len(stitch_frames)} frames into panorama...")
        from src.tracking.rectify_court import collage
        try:
            pano = collage(stitch_frames)
        except Exception as e:
            print(f"  Stitch failed ({e}), using single frame as pano")
            pano = stitch_frames[0]

        # Validate stitched result.  Over-wide panos (ratio >10) come from camera
        # drift across many frames; salvage them by center-cropping to ~6:1 before
        # falling back to a single gameplay frame (which has too few court features).
        h_p, w_p = pano.shape[:2]
        ratio_p = w_p / max(h_p, 1)
        if ratio_p > 10.0 and w_p >= 2000:
            target_w = int(h_p * 6.0)
            if target_w < w_p:
                x0 = (w_p - target_w) // 2
                pano = pano[:, x0: x0 + target_w]
                print(f"  Wide pano cropped {w_p}→{target_w}px (ratio {ratio_p:.1f}→6.0)")
        if not UnifiedPipeline._pano_valid(pano):
            h_p, w_p = pano.shape[:2]
            # Single gameplay frame (640×300, ratio=2.1) is too narrow for SIFT →
            # fall back to pano_enhanced.png which covers the full court.
            print(f"  Stitched pano invalid ({w_p}×{h_p}, ratio={w_p/max(h_p,1):.1f})"
                  f" — falling back to general pano")
            for _fb in ("pano_enhanced.png", "pano.png"):
                _fb_path = os.path.join(_RESOURCES, _fb)
                if os.path.exists(_fb_path):
                    _fb_img = cv2.imread(_fb_path)
                    if UnifiedPipeline._pano_valid(_fb_img):
                        pano = _fb_img
                        print(f"  Using general pano fallback: {_fb}")
                        break
            else:
                # Absolute last resort — single frame (homography will be unreliable)
                pano = stitch_frames[0]

        out = UnifiedPipeline._auto_pano_path(video_path)
        cv2.imwrite(out, pano)
        print(f" Pano saved → {os.path.basename(out)} ({pano.shape[1]}×{pano.shape[0]})")
        return pano

    def _is_gameplay(self, frame: np.ndarray, frame_idx: int) -> bool:
        """Return True when YOLO detects enough players — skips non-play frames.

        Two caches prevent redundant YOLO inference:
          _gameplay_cache_until    — once gameplay is confirmed, trust it for
                                     _GAMEPLAY_CACHE_FRAMES frames (~3 s).
          _no_gameplay_until       — once non-live is confirmed (halftime,
                                     timeout, replay), skip YOLO check for the
                                     same window.  Avoids ~600 YOLO calls during
                                     a 3-minute halftime.
        """
        if frame_idx < self._gameplay_cache_until:
            return True
        if frame_idx < self._no_gameplay_until:
            return False
        # imgsz=640: at 1280px broadcast width, players are ~50px tall.
        # imgsz=480 scales them to ~19px which is below reliable detection.
        # imgsz=640 → ~25px → acceptable for gameplay filter.
        # NOTE: yolov8n.engine is compiled at 480 — cannot call at 640.
        # Use a separate PyTorch model for gameplay detection only.
        if self._gameplay_yolo is None:
            try:
                from ultralytics import YOLO as _YOLO
                _pt = os.path.join(PROJECT_DIR, "yolov8n.pt")
                if not os.path.exists(_pt):
                    _pt = os.path.join(_RESOURCES, "yolov8n.pt")
                self._gameplay_yolo = _YOLO(_pt)
            except Exception:
                self._gameplay_yolo = self.feet_det.model  # fallback: TRT at 480
        _imgsz = getattr(self.feet_det, "_infer_imgsz", 640)
        r = list(self._gameplay_yolo(
            frame, classes=[0], conf=0.25, verbose=False,
            imgsz=_imgsz, half=self.feet_det._use_half, stream=True,
        ))
        n = len(r[0].boxes) if r[0].boxes is not None else 0
        if n >= MIN_GAMEPLAY_PERSONS:
            self._gameplay_cache_until = frame_idx + _GAMEPLAY_CACHE_FRAMES
            return True
        # Cache the negative result — skip YOLO re-checks during confirmed breaks
        self._no_gameplay_until = frame_idx + _GAMEPLAY_CACHE_FRAMES
        return False

    def _build_court(self, pano, startup_frames: list = None):
        """Build 2D court map and compute homography M1.

        Attempts per-clip homography detection from startup_frames using
        detect_court_homography(). Falls back to static resources/Rectify1.npy
        if detection returns None (< 4 court line intersections found).

        Args:
            pano: Panorama image used for court rectification.
            startup_frames: Optional list of BGR frames (first ~60) from the
                            video source. When provided, attempts per-clip M1
                            detection. When None, skips detection and uses
                            Rectify1.npy directly.

        Returns:
            Tuple of (map_2d, M1) where M1 is a 3x3 float64 homography.
        """
        rect1 = os.path.join(_RESOURCES, "Rectify1.npy")
        map_img = cv2.imread(os.path.join(_RESOURCES, "2d_map.png"))

        # Guard: if pano is None or empty (e.g. all fallbacks failed), skip
        # corner-detection and use the default 940×500 court map dimensions.
        _pano_ok = pano is not None and isinstance(pano, np.ndarray) and pano.size > 0
        if not _pano_ok:
            import logging as _log_mod
            _log_mod.getLogger(__name__).warning(
                "_build_court: pano is None/empty — skipping rectification, using 940×500 default"
            )
            _rw, _rh = 940, 500
        else:
            try:
                img = binarize_erode_dilate(pano, plot=False)
                _, corners = rectangularize_court(img, plot=False)
                rectified = rectify(pano, corners, plot=False)

                # Basketball court is always landscape (wider than tall, ~1.88:1).
                # If rectify() returns portrait (height > width), try rotating 90° to
                # recover a landscape image before falling back to the 940×500 default.
                _rh, _rw = rectified.shape[:2]
                if _rh > _rw:
                    import logging as _log_mod
                    _bc_log = _log_mod.getLogger(__name__)
                    _rotated = cv2.rotate(rectified, cv2.ROTATE_90_CLOCKWISE)
                    _rh2, _rw2 = _rotated.shape[:2]
                    if _rw2 > _rh2:
                        _bc_log.warning(
                            "_build_court: rectified portrait (%dx%d) — rotated 90° → landscape (%dx%d)",
                            _rw, _rh, _rw2, _rh2,
                        )
                        _rh, _rw = _rh2, _rw2
                    else:
                        _bc_log.warning(
                            "_build_court: rectified is portrait (%dx%d) even after rotation — "
                            "court corner detection failed; forcing 940×500 map",
                            _rw, _rh,
                        )
                        _rw, _rh = 940, 500
            except Exception as _e:
                import logging as _log_mod
                _log_mod.getLogger(__name__).warning(
                    "_build_court: rectification failed (%s) — using 940×500 default", _e
                )
                _rw, _rh = 940, 500
        map_2d = cv2.resize(map_img, (_rw, _rh))

        # Per-clip homography detection (ISSUE-017 fix).
        # NOTE: detect_court_homography returns M1 mapping frame→940×500 directly.
        # The pipeline applies M1 @ (M @ x) where M maps frame→pano, so M1 must
        # map pano→court.  The correct adjustment (M1_adjusted = M1_raw @ inv(M_ema))
        # requires M_ema (SIFT EMA) which is NOT available at __init__ time.
        # Therefore, startup detection is SKIPPED here; _try_recover_court_M1
        # performs the same detection during gameplay with M_ema available so it
        # can compute the proper inverse-adjusted M1.  Meanwhile, use Rectify1.npy
        # as the initial fallback (calibrated for pano_enhanced, 3698×500px).
        if self._last_good_M1 is not None:
            M1 = self._last_good_M1
            clip = os.path.basename(getattr(self, "video_path", "unknown"))
            print(f"[unified_pipeline] Reusing last good M1 for '{clip}'")
        else:
            M1 = np.load(rect1)
            clip = os.path.basename(getattr(self, "video_path", "unknown"))
            print(f"[unified_pipeline] Using static Rectify1.npy for '{clip}' — per-clip M1 will be updated during gameplay")

        return map_2d, M1

    def _try_recover_court_M1(self, frame: np.ndarray) -> None:
        """Attempt to re-detect court homography after camera cuts / zooms.

        Called every gameplay frame in run(). Increments a staleness counter each
        frame. Once the counter exceeds 30 consecutive frames with no successful
        per-clip detection, retries detect_court_homography on the current frame.
        Lowered from 150→30 (2026-03-18) so clips where startup scan fails get
        a valid per-clip M1 within the first ~5s of gameplay rather than ~25s.
        Updates self.M1 and self._last_good_M1 on success and resets the counter.

        Args:
            frame: Current BGR frame (already cropped by TOPCUT).
        """
        self._M1_stale_frames += 1
        # OPTIMIZATION: only buffer frames when approaching detection threshold.
        # Avoids storing full BGR frames on every call when M1 is healthy.
        _threshold = (500 if self._last_good_M1 is None and self._M1_failed_attempts >= 5
                      else 30 if self._last_good_M1 is None else 150)
        if self._M1_stale_frames >= _threshold - 10:
            self._recover_frame_buf.append(frame)
        if self._M1_stale_frames > _threshold:
            new_M1_raw = detect_court_homography(list(self._recover_frame_buf))
            if new_M1_raw is not None:
                # detect_court_homography returns M1 mapping frame→940×500 court.
                # The pipeline applies M1 @ (M @ x) where M maps frame→pano.
                # To be correct, M1 must map pano→court so that:
                #   M1 @ M @ x  =  (pano→court) @ (frame→pano) @ x  =  frame→court
                # Adjust: M1_adjusted = M1_raw @ inv(M_ema)
                #   M1_adjusted @ M_ema  =  M1_raw @ I  =  M1_raw  (correct)
                new_M1 = new_M1_raw
                if self._M_ema is not None:
                    try:
                        import numpy as _np
                        new_M1 = new_M1_raw @ _np.linalg.inv(self._M_ema)
                    except (np.linalg.LinAlgError, AttributeError):
                        pass  # M_ema singular or unavailable — use raw M1
                # Sanity-check: project 4 court corners through new_M1 and verify
                # the output bounding box is landscape (width > height).
                # A portrait result means detect_court_homography returned a
                # rotated mapping — reject to avoid portrait-coordinate corruption.
                _valid_m1 = True
                try:
                    _corners_src = np.array([[0,0],[1280,0],[1280,720],[0,720]],
                                            dtype=np.float64).reshape(-1,1,2)
                    _projected = cv2.perspectiveTransform(_corners_src, new_M1)
                    _px = _projected[:, 0, 0]
                    _py = _projected[:, 0, 1]
                    _proj_w = float(_px.max() - _px.min())
                    _proj_h = float(_py.max() - _py.min())
                    if _proj_h > _proj_w * 1.5:   # portrait ratio → reject
                        _valid_m1 = False
                        self._M1_failed_attempts += 1
                except Exception:
                    pass

                if _valid_m1:
                    self._M1_raw_clip = new_M1_raw  # store for M_ema re-sync in _get_homography
                    self.M1 = new_M1
                    self._last_good_M1 = new_M1
                    self._M1_stale_frames = 0
                    self._M1_failed_attempts = 0
            else:
                self._M1_failed_attempts += 1
                self._M1_stale_frames = 0  # reset so we wait another threshold period

    def _kornia_homography(self, small_roi: np.ndarray, y_offset: int):
        """Run kornia LoFTR matching and compute homography on GPU.

        Returns (M, mask) or (None, None) on failure.
        """
        with _torch.no_grad():
            return self._kornia_homography_inner(small_roi, y_offset)

    def _kornia_homography_inner(self, small_roi: np.ndarray, y_offset: int):
        _dev = self._kornia_device
        inv_s = 1.0 / _SIFT_SCALE

        gray_small = cv2.cvtColor(small_roi, cv2.COLOR_BGR2GRAY) if len(small_roi.shape) == 3 else small_roi
        frame_t = _torch.from_numpy(gray_small).float().unsqueeze(0).unsqueeze(0).to(_dev) / 255.0

        # Resize pano to comparable scale for LoFTR
        _ph, _pw = self._pano_tensor.shape[2], self._pano_tensor.shape[3]
        _sh, _sw = frame_t.shape[2], frame_t.shape[3]
        pano_resized = _torch.nn.functional.interpolate(
            self._pano_tensor, size=(_sh, _sw), mode="bilinear", align_corners=False
        )

        batch = {"image0": pano_resized, "image1": frame_t}
        self._kornia_matcher(batch)

        mkpts0 = batch["mkpts0_f"].cpu().numpy()  # pano keypoints (in resized space)
        mkpts1 = batch["mkpts1_f"].cpu().numpy()  # frame keypoints (in small_roi space)
        conf = batch["mconf"].cpu().numpy()

        # Filter by confidence
        good = conf > 0.5
        if good.sum() < 4:
            return None, None

        # Scale back to full frame/pano coordinates
        _pano_scale_x = _pw / _sw
        _pano_scale_y = _ph / _sh
        src = mkpts0[good] * np.array([_pano_scale_x, _pano_scale_y])
        dst = mkpts1[good] * np.array([inv_s, inv_s])
        dst[:, 1] += y_offset  # ROI offset

        src = src.reshape(-1, 1, 2).astype(np.float32)
        dst = dst.reshape(-1, 1, 2).astype(np.float32)

        M, mask = cv2.findHomography(dst, src, cv2.RANSAC, 5.0)
        return M, mask

    def _get_homography(self, frame) -> Optional[np.ndarray]:
        """
        Compute SIFT-based frame→panorama homography with EMA smoothing and
        court-line re-anchoring.

        Three tiers:
          1. inliers < _H_MIN_INLIERS  → reject, keep last good M (no change)
          2. inliers ≥ _H_RESET_INLIERS → hard-reset EMA (very clean match,
             discards accumulated drift immediately)
          3. _H_MIN_INLIERS ≤ inliers < _H_RESET_INLIERS → EMA blend as before

        Additionally, every _REANCHOR_INTERVAL frames a court-line alignment
        check projects the 4 court boundary lines through inv(M_ema·M1) and
        measures how many projected samples land on white court-line pixels.
        Alignment below _REANCHOR_ALIGN_MIN signals slow drift → hard-reset
        to the freshest SIFT M.
        """
        self._sift_frame_counter += 1
        # When homography is suspended (replay/cut), hold the last good EMA — no SIFT update.
        if self._homography_suspended:
            return self._M_ema
        if self._sift_frame_counter % _SIFT_INTERVAL != 0 and self._M_ema is not None:
            return self._M_ema

        h, w = frame.shape[:2]

        # Task 6: crop bottom 70% — removes scoreboard and crowd at top,
        # giving SIFT cleaner court-line keypoints and fewer false matches.
        y_offset = int(h * 0.30)
        roi = frame[y_offset:, :]

        # Task 1: scene-change histogram gate — skip SIFT when there is no
        # camera cut (L1 diff below threshold) and we already have a valid EMA.
        # OPTIMIZATION: Use 32 bins instead of 64 (faster) + early exit on threshold
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        hist_cur = cv2.calcHist([gray_roi], [0], None, [32], [0, 256]).flatten()
        _s = hist_cur.sum()
        if _s > 0:
            hist_cur = hist_cur / _s
        if self._sift_last_hist is not None and self._M_ema is not None:
            l1_diff = float(np.abs(hist_cur - self._sift_last_hist).sum())
            if l1_diff < _SIFT_CUT_THRESH:
                return self._M_ema  # no camera cut — reuse cached EMA homography
        self._sift_last_hist = hist_cur

        # Run feature matching — kornia LoFTR (GPU) or SIFT (CPU fallback).
        small = cv2.resize(roi, (int(roi.shape[1] * _SIFT_SCALE), int(roi.shape[0] * _SIFT_SCALE)))

        M, mask = None, None
        if self._kornia_matcher is not None:
            try:
                M, mask = self._kornia_homography(small, y_offset)
            except Exception:
                pass  # fall through to SIFT

        if M is None and hasattr(self, 'sift') and self.sift is not None:
            kp2_small, des2 = self.sift.detectAndCompute(small, None)
            if des2 is not None and len(des2) >= 4:
                inv_s = 1.0 / _SIFT_SCALE
                kp2 = [cv2.KeyPoint(kp.pt[0] * inv_s, kp.pt[1] * inv_s + y_offset,
                                     kp.size * inv_s, kp.angle, kp.response,
                                     kp.octave, kp.class_id) for kp in kp2_small]
                _des2_capped = des2[:min(500, len(des2))]
                matches = FLANN.knnMatch(self.des1, _des2_capped, k=2)
                good = [m for m, n in matches if m.distance < 0.7 * n.distance]
                if len(good) >= 4:
                    src = np.float32([self.kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
                    dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
                    M, mask = cv2.findHomography(dst, src, cv2.RANSAC, 5.0)

        if M is None:
            return self._M_ema

        inliers = int(mask.sum()) if mask is not None else 0
        # First-frame bootstrap: accept 3+ inliers if no EMA exists yet.
        # After bootstrap, use stricter _H_MIN_INLIERS to avoid noisy updates.
        min_inliers = 3 if self._M_ema is None else _H_MIN_INLIERS
        if inliers < min_inliers:
            return self._M_ema

        # Sanity gate: reject M if it maps reference points too far from current EMA.
        # This prevents a single bad SIFT match from teleporting all tracked players.
        if self._M_ema is not None and inliers < _H_RESET_INLIERS:
            h_pano, w_pano = self.pano.shape[:2]
            test_pts = np.float32([
                [w_pano * 0.25, h_pano * 0.5, 1],
                [w_pano * 0.50, h_pano * 0.5, 1],
                [w_pano * 0.75, h_pano * 0.5, 1],
                [w_pano * 0.50, h_pano * 0.25, 1],
            ])
            def _proj(mat, pt):
                p = mat @ pt.reshape(3, 1)
                return p[:2] / p[2]
            dists = [
                float(np.linalg.norm(_proj(M, p) - _proj(self._M_ema, p)))
                for p in test_pts
            ]
            if max(dists) > 99999:  # sanity gate disabled — position-level smoothing used instead
                return self._M_ema

        # Tier 1: very clean match — hard-reset to eliminate accumulated drift
        if self._M_ema is None or inliers >= _H_RESET_INLIERS:
            self._M_ema = M
        else:
            # Tier 2: EMA blend
            self._M_ema = _H_EMA_ALPHA * M + (1 - _H_EMA_ALPHA) * self._M_ema

        # Re-sync M1 whenever M_ema changes and we have a valid per-clip court mapping.
        # Invariant: M1 @ M_ema = M1_raw_clip  =>  M1 = M1_raw_clip @ inv(M_ema)
        if self._M1_raw_clip is not None:
            try:
                self.M1 = self._M1_raw_clip @ np.linalg.inv(self._M_ema)
            except np.linalg.LinAlgError:
                pass  # singular M_ema — keep existing M1

        # Periodic court-line drift check
        self._frames_since_anchor += 1
        if self._frames_since_anchor >= _REANCHOR_INTERVAL:
            self._frames_since_anchor = 0
            if self._check_court_drift(frame):
                # Drift confirmed — snap to freshest SIFT M
                self._M_ema = M

        return self._M_ema

    def _check_court_drift(self, frame: np.ndarray) -> bool:
        """
        Detect slow homography drift by projecting the 4 court boundary lines
        through inv(M_ema) · inv(M1) into frame space and measuring white-pixel
        alignment.

        Returns True when alignment < _REANCHOR_ALIGN_MIN (drift detected).
        """
        if self._M_ema is None:
            return False

        h, w = frame.shape[:2]
        map_h, map_w = self.map_2d.shape[:2]

        try:
            # 2D court → frame: inv(M_ema) · inv(M1)
            M_ct2f = np.linalg.inv(self._M_ema) @ np.linalg.inv(self.M1)
        except np.linalg.LinAlgError:
            return False

        # White court-line mask (high V, low S)
        hsv   = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        white = cv2.inRange(hsv, (0, 0, 175), (180, 45, 255))

        total = aligned = 0
        for cx, cy in self._court_boundary_samples(map_w, map_h, n=20):
            pt = M_ct2f @ np.array([cx, cy, 1.0])
            if abs(pt[2]) < 1e-6:
                continue
            fx, fy = int(pt[0] / pt[2]), int(pt[1] / pt[2])
            if 0 <= fx < w and 0 <= fy < h:
                total += 1
                r = 8
                if white[max(0, fy - r):min(h, fy + r),
                         max(0, fx - r):min(w, fx + r)].any():
                    aligned += 1

        if total < 8:
            return False  # not enough projected points visible — can't judge

        alignment = aligned / total
        return alignment < _REANCHOR_ALIGN_MIN

    @staticmethod
    def _court_boundary_samples(map_w: int, map_h: int, n: int = 20):
        """Yield (x, y) samples evenly spaced along the 4 court boundary edges."""
        xs = np.linspace(0, map_w, n, dtype=int)
        ys = np.linspace(0, map_h, n, dtype=int)
        for x in xs:
            yield int(x), 0        # top sideline
            yield int(x), map_h    # bottom sideline
        for y in ys:
            yield 0,     int(y)    # left baseline
            yield map_w, int(y)    # right baseline

    def _is_replay_or_cut(self, frame: np.ndarray) -> bool:
        """
        Detect scene cuts, replay graphics, or overlay events that invalidate
        homography for the current frame.

        Three signals:
          1. Frame-to-frame L1 histogram diff (scene cut).
          2. Scoreboard disappears after being seen (handled in run()).
          3. Frame mean-brightness spike by >= _REPLAY_BRIGHT_FACTOR (replay overlay).

        OPTIMIZATION: Replaced SSIM (skimage import per frame) with histogram L1
        diff — same quality for scene-cut detection, ~10× faster, no external dep.
        Combined gray+brightness into single resize+cvtColor pass.
        """
        small = cv2.resize(frame, (160, 90))
        gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        triggered = False

        # Signal 1 — histogram L1 scene-cut (replaces SSIM — faster, no skimage dep)
        if self._replay_prev_gray_small is not None:
            h1 = cv2.calcHist([self._replay_prev_gray_small], [0], None, [32], [0, 256]).flatten()
            h2 = cv2.calcHist([gray_small], [0], None, [32], [0, 256]).flatten()
            s1, s2 = float(h1.sum()), float(h2.sum())
            if s1 > 0:
                h1 = h1 / s1
            if s2 > 0:
                h2 = h2 / s2
            if float(np.abs(h1 - h2).sum()) > (1.0 - _REPLAY_SSIM_THRESH):
                triggered = True

        self._replay_prev_gray_small = gray_small

        # Signal 2 — scoreboard disappears (handled in run() via _sc_absent_streak)

        # Signal 3 — brightness spike (replay graphic overlay = sudden bright flash)
        # OPTIMIZATION: compute mean brightness from grayscale (avoids BGR→HSV cvtColor)
        mean_v = float(gray_small.mean())
        if self._replay_prev_brightness > 0:
            if mean_v > self._replay_prev_brightness * _REPLAY_BRIGHT_FACTOR + 20.0:
                triggered = True
        self._replay_prev_brightness = mean_v

        return triggered

    def _vision_probe_resume(self, frame: np.ndarray, frame_idx: int) -> bool:
        """Probe YOLO every 150 frames to clear a vision-based suspension.

        When ball-track was suspended (OCR-absent threshold fired OR vision
        fallback), periodically re-run YOLO on a single frame to check whether
        the scene has returned to live play (≥8 persons visible).  Returns True
        and clears suspension when that threshold is met; returns False with no
        state change otherwise.

        v33 fix: removed `and not self._sc_ever_seen` guard — the probe must
        run whenever suspension is latched, regardless of whether the scoreboard
        was ever seen.  The old guard blocked recovery when OCR fired briefly
        early in the clip (setting _sc_ever_seen=True) and then went absent,
        leaving _ball_track_suspended permanently set.
        """
        if not (self._ball_track_suspended
                and frame_idx % 150 == 0
                and self.yolo.available):
            return False
        probe_results = self.yolo.predict(frame)
        n = len(probe_results)
        if n >= 8:
            self._ball_track_suspended = False
            self._no_ball_vision_streak = 0
            print(f"[resume] frame {frame_idx}: vision probe found {n} persons "
                  f"→ suspension cleared")
            return True
        return False

    # ── main run ──────────────────────────────────────────────────────────

    def run(self) -> dict:
        """
        Process video end-to-end.

        Returns dict with:
          predictions  — per-frame tracking results
          stats        — per-player shot attempts + made baskets
          id_switches  — estimated ID switch count
          stability    — track stability score
          total_frames — frames processed
        """
        # Fix 2: reset tracker state so per-game leakage doesn't affect next game
        self.feet_det._reset_per_game()
        # Fix 3: reset VRAM flush counter at the top of each run() invocation
        _vram_flush_counter = 0

        cap    = cv2.VideoCapture(self.video_path)
        fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
        map_h, map_w = self.map_2d.shape[:2]
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total_video_frames == 0:
            # cv2 couldn't read frame count (common with YouTube-downloaded MP4/MKV).
            # Try PyAV for an accurate count; fall back to file-size heuristic.
            try:
                import av as _av
                _c = _av.open(self.video_path)
                total_video_frames = _c.streams.video[0].frames or 0
                _c.close()
            except Exception:
                pass
            if total_video_frames == 0:
                # Last resort: estimate from file size — 1 GB ≈ full game at typical bitrate.
                try:
                    total_video_frames = int(os.path.getsize(self.video_path) / 250_000)
                except Exception:
                    total_video_frames = _FRAME_STRIDE_THRESH + 1  # assume long; use stride
        # Stride: skip (stride-1) frames between each processed frame on long clips.
        # Handled in the prefetcher so NVDEC only decodes ~1/stride of all frames.
        # Auto-scale stride for high-FPS video: 30fps→stride 3 (10fps effective),
        # 60fps→stride 6 (10fps effective), 120fps→stride 12, etc.
        # This keeps processing rate constant regardless of source FPS so 60fps
        # games don't take 2× longer than 30fps games for the same real-time window.
        _base_stride = max(_FRAME_STRIDE, round(fps / 10.0)) if fps > 35 else _FRAME_STRIDE
        _stride = _base_stride if total_video_frames > _FRAME_STRIDE_THRESH else 1
        # max_frames is given in source-frame units (calibrated by _fps_adjusted_frames).
        # gameplay_frames counts DECODED frames (1 per stride), so scale down.
        if self.max_frames and _stride > 1:
            self.max_frames = max(1, self.max_frames // _stride)
        # Wire fps + stride into EventDetector so shot debounce, drive speed, and
        # closeout mph are all computed in correct absolute-frame / real-time units.
        self.event_det.configure(fps, _stride)
        if self.start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_frame)
        writer = self._make_writer(cap)
        # cap is only needed for fps/frame-count metadata and writer init above.
        # Release it now — the prefetcher opens its own decoder; holding cap open
        # wastes a file handle and causes a leak if the main loop throws.
        cap.release()
        cap = None
        # Prefetcher runs in a background thread — overlaps decode with tracking.
        # Uses NVDEC (decord GPU) when available, falls back to PyAV/cv2.
        # stride= causes the decode thread to skip 2/3 of frames at the NVDEC level
        # rather than decoding-then-discarding, saving GPU bandwidth and memory.
        # queue_size=12: balance decode overlap vs RSS.  64 frames ≈ 384 MB
        # per worker — on cgroup-limited pods (116 GB) this blows up with 3+ workers.
        # 12 frames ≈ 72 MB keeps the decode thread busy without RSS bloat.
        # Cap source frames decoded to prevent PyAV from reading full 200K-frame videos
        # when only 18K gameplay frames are needed.  4× multiplier accounts for up to
        # 75% non-live content (replays, halftime, ads). 0 = no cap (short clips).
        _max_src = (self.max_frames * _stride * 4) if self.max_frames else 0
        _prefetcher = _FramePrefetcher(self.video_path, self.start_frame,
                                       stride=_stride, queue_size=12,
                                       max_source_frames=_max_src)

        # Clear stale CSV files from previous runs so incremental append starts fresh
        for _stale in ("ball_tracking.csv", "scoreboard_log.csv", "events_log.csv", "shot_log.csv"):
            _sp = os.path.join(self._data_dir, _stale)
            if os.path.exists(_sp):
                os.remove(_sp)

        tracking_rows:    List[dict] = []
        ball_rows:        List[dict] = []
        predictions:      List[dict] = []
        player_stats:     dict       = {}
        possession_rows:  List[dict] = []
        shot_log_rows:    List[dict] = []
        shot_poss_last_ts: dict      = {}  # possession_id -> last shot timestamp (cooldown)
        _last_global_shot_ts: float  = -999.0  # global 3s gate across all possessions
        scoreboard_log_rows: List[dict] = []
        _events_log_rows: List[dict] = []  # FIX 1: rich events accumulator for events_log.csv
        # FIX 4: per-possession event counts (accumulated in main loop to survive checkpoint clears)
        _poss_event_counts: Dict[int, Dict[str, int]] = {}
        _frame_tracks_buf: List[List[dict]] = []   # FIX 5: first-300-frame buffer for court-side team map
        _sb_conf: float = 0.0                       # FIX 6: last scoreboard confidence for gating
        suspended_frame_count: int   = 0  # frames where ball tracking was suspended
        _period_start_detected: bool = False  # True once we've set period_start_video_sec
        _ball_miss_streak:     int   = 0  # consecutive frames ball not detected
        frame_idx    = self.start_frame  # absolute video frame (comes from prefetcher on each read)
        gameplay_frames = 0             # gameplay frames actually processed (for max_frames check)
        prev_pos:    Dict[int, tuple] = {}   # player_id → (x2d, y2d)
        prev_vel:    Dict[int, float] = {}   # player_id → velocity prev frame
        _player_dist_run: Dict[int, float] = {}  # player_id → cumulative px distance
        poss_team_prev:   str            = ""
        possession_dur:   int            = 0
        last_handler:     Optional[dict] = None   # last player who had ball (for shot log)
        prev_ball_2d_f:   Optional[tuple] = None
        # Directional gate: rolling 5-frame ball position history (pixel space).
        # Kept small so memory impact is negligible; deque auto-evicts oldest.
        from collections import deque as _dq
        _ball_pos_hist: _dq = _dq(maxlen=5)
        possession_id:    int            = 0
        possession_start: int            = 0
        possession_buf:   List[dict]     = []
        fast_break:       int            = 0
        # Offensive rebound shot clock: track whether the previous possession ended
        # in a missed shot by the same team so we can apply the 14s reset rule.
        _prev_poss_shot_attempted: bool  = False   # did last possession have a shot?
        _prev_poss_result:         str   = ""      # "scored" or "missed" etc.
        _poss_is_off_rebound:      bool  = False   # current possession follows off-rebound
        poss_no_ball_streak: int         = 0   # consecutive frames without detected ball handler
        _POSS_PERSIST_FRAMES = 90              # frames without ball before possession resets (raised 60→90: broadcast has 2-3s ball gaps; at stride=3 30fps this is 9s)
        # Fix 3 Part A: debounce brief wrong-team ball attribution.
        # FIX 1: Made fps/stride-aware so minimum possession is always 1.5s real-time
        # regardless of video fps or stride setting.  At 30fps/stride-3 = 15 iterations,
        # at 30fps/stride-1 = 45 iterations, at 60fps/stride-3 = 30 iterations.
        _ball_loss_streak: int = 0
        # BUG3 fix: Lower from 20 (audit found this merged real possessions) to ~10 frames.
        # At 30fps/stride-3 → 10 frames ≈ 1s; genuine possession switches persist longer.
        # Previously set to 1.5s then overridden per-frame to 2.0s — both too high (71% of
        # possessions exceeded 30s duration; max observed 1973s = entire half).
        # Configurable via NBA_BALL_LOSS_FRAMES env var for tuning without code change.
        _BALL_LOSS_THRESH  = int(os.environ.get("NBA_BALL_LOSS_FRAMES",
                                                 str(int(1.0 * fps / _stride))))
        # BUG2 fix: track scoreboard period to detect quarter/halftime boundaries
        # and reset possession_start so shot_clock_est doesn't carry Q2 frame values into Q3.
        _last_scoreboard_period: Optional[int] = None
        # FIX 1: lineup tracking
        _lineup_id_cache: Dict[frozenset, int] = {}
        _lineup_counter: int = 0
        _poss_lineup_buf: List[int] = []
        # FIX 4: transition time tracking
        _transition_frames: Optional[int] = None
        _poss_crossed_halfcourt: bool = False
        _last_real_poss_team: str = ""  # FIX-POSS: last non-empty team to hold ball
        # FIX 5: second chance tracking
        _poss_shot_count: Dict[int, int] = {}
        # Fix 1: Replay detection — track previous OCR clock value per period.
        # When game_clock_sec increases (clock goes backward) within the same period,
        # the broadcast is showing an instant replay → suspend ball+event tracking.
        _prev_game_clock_sec: float = -1.0
        _prev_period:         int   = -1
        # Fix 2: Frozen-clock detection — halftime / dead-ball / ad-break.
        # OCR runs every _OCR_INTERVAL=30 frames; 3 consecutive scans with the
        # same clock value = 90 frames ≈ 3 real seconds at stride=3/30fps.
        _frozen_clock_scans: int = 0
        _FROZEN_CLOCK_THRESHOLD = 3  # scans (= 90 source frames ≈ 3 real seconds)

        # OPTIMIZATION: Jersey OCR batching — skip OCR on 2/3 frames (reduce OCR calls ~67%)
        # Jersey voting buffer averages across frames anyway, so batching loses no data
        _ocr_stride_counter: int = 0
        _OCR_STRIDE_INTERVAL: int = 30  # OPTIMIZATION: raised 3→30 for RunPod batch (EasyOCR bottleneck)

        # OPTIMIZATION: periodic CUDA cache cleanup to prevent VRAM fragmentation.
        # L40S (48GB): flush every 3000 frames (~5 min) — more frequent than before to
        # prevent fragmentation from accumulating over full-game runs (90K+ frames).
        # empty_cache() is ~0.1ms on L40S — negligible vs the 5-min interval.
        _VRAM_FLUSH_INTERVAL = 3000
        _vram_flush_counter  = 0

        # RAM leak defense: gc.collect + malloc_trim every 500 gameplay frames.
        # Checkpoints at 2000 frames are too infrequent — glibc arena fragmentation
        # from rapid YOLO/SIFT/OSNet alloc/free grows RSS monotonically.
        _GC_INTERVAL = 200
        _gc_counter  = 0
        _rss_prev_mb = 0.0  # track RSS growth between GC cycles

        # ── tracemalloc leak profiler (enabled by TRACEMALLOC=1 env) ──────
        _TM_ENABLED = os.environ.get("TRACEMALLOC", "") == "1"
        _tm_snap0 = None
        _TM_INTERVAL = 100  # snapshot every 100 gameplay frames
        if _TM_ENABLED:
            import tracemalloc as _tm
            _tm.start(25)  # 25-frame deep tracebacks
            _tm_snap0 = _tm.take_snapshot()
            print("[TRACEMALLOC] enabled — will snapshot every 100 gameplay frames")

        while True:
            ok, frame, _fi = _prefetcher.read()
            if ok:
                frame_idx = _fi  # only update on valid frames; never let sentinel (-1) overwrite
            if not ok or frame is None or (self.max_frames and gameplay_frames >= self.max_frames):
                break

            # Stride skip is handled inside _FramePrefetcher (NVDEC-level) — no
            # in-loop check needed.  frame_idx is the absolute video frame index
            # yielded by the prefetcher's decode loop.

            # BUG 41 FIX: keep pre-TOPCUT frame for scoreboard OCR.
            # frame[TOPCUT:] removes the broadcast scoreboard strip (top 60px)
            # which contains the period indicator ("1ST QTR", "Q2", etc.).
            # The OCR must see the original frame; all other processing still
            # uses the TOPCUT-cropped frame so YOLO/tracking are unaffected.
            _frame_for_ocr = frame
            frame = frame[TOPCUT:]

            # ── PROFILER (temporary) ──────────────────────────────────────
            import time as _time
            _t0 = _time.perf_counter()

            # Skip non-gameplay frames (intro, halftime, timeout, replay, crowd shots)
            if not self._is_gameplay(frame, frame_idx):
                continue
            _t1 = _time.perf_counter()

            # ── Scoreboard OCR (runs FIRST — drives non-live skip) ────────
            # Moved before all expensive work so suspended frames can be
            # hard-skipped.  ScoreboardOCR has its own internal interval
            # (~30 frames) so this is cheap on most frames.
            # BUG 41 FIX: pass pre-TOPCUT frame so the scoreboard strip is visible.
            sb_state = self.scoreboard_ocr.read(_frame_for_ocr)
            _sc_result = self.scoreboard_ocr.current_scan_result  # None|True|False
            if _sc_result is not None:   # an actual OCR scan ran this frame
                # R8: Always log any scan that parsed ≥1 field. Previously gated on
                # _sc_result (shot_clock parsed) which dropped 99% of scoreboard reads.
                _gclock  = (sb_state.get("game_clock_sec") or -1.0) if sb_state else -1.0
                _gperiod = (sb_state.get("period") or -1)           if sb_state else -1
                _sc_fields = [
                    _gclock  > 0,
                    sb_state.get("shot_clock",  -1) > 0,
                    sb_state.get("home_score",  -1) >= 0,
                    sb_state.get("away_score",  -1) >= 0,
                    _gperiod > 0,
                ]
                _sc_conf = sum(_sc_fields) / len(_sc_fields)
                _sb_conf = _sc_conf   # preserved for shot_log gate downstream (line ~2328)
                self._last_sb_conf = _sc_conf
                if any(_sc_fields):
                    scoreboard_log_rows.append({
                        "frame":       frame_idx,
                        "game_clock":  f"{int(_gclock)//60}:{int(_gclock)%60:02d}" if _gclock > 0 else "",
                        "shot_clock":  sb_state.get("shot_clock", "") if sb_state.get("shot_clock", -1) > 0 else "",
                        "home_score":  sb_state.get("home_score", "") if sb_state.get("home_score", -1) >= 0 else "",
                        "away_score":  sb_state.get("away_score", "") if sb_state.get("away_score", -1) >= 0 else "",
                        "period":      _gperiod if _gperiod > 0 else "",
                        "confidence":  round(_sc_conf, 3),
                    })

                if _sc_result:
                    self._sc_absent_streak     = 0
                    self._sc_ever_seen         = True
                    # R10: mirror clock to self.* so the homography over-trigger guard
                    # (replay/cut detector below at line ~1745) can see the live-play signal.
                    if _gclock > 0:
                        self._prev_clock_seconds = self._last_clock_seconds
                        self._last_clock_seconds = float(_gclock)
                    if (_gclock > 0 and _prev_game_clock_sec > 0
                            and _gperiod > 0 and _gperiod == _prev_period
                            and _gclock > _prev_game_clock_sec + 2.0):
                        # Clock jumped backward → instant replay
                        self._ball_track_suspended = True
                        _frozen_clock_scans = 0
                    elif (_gclock > 0 and _prev_game_clock_sec > 0
                            and abs(_gclock - _prev_game_clock_sec) < 0.5):
                        # Clock hasn't advanced → halftime / dead-ball / ad-break
                        _frozen_clock_scans += 1
                        if _frozen_clock_scans >= _FROZEN_CLOCK_THRESHOLD:
                            self._ball_track_suspended = True
                    else:
                        self._ball_track_suspended = False
                        _frozen_clock_scans = 0
                    if _gclock  > 0: _prev_game_clock_sec = _gclock
                    if _gperiod > 0: _prev_period         = _gperiod

                    # BUG2 fix: period boundary → reset possession_start so shot_clock_est
                    # doesn't use stale Q2 frame numbers when computing Q3 clock.
                    # Common scenario: same team has ball at end of Q2 AND start of Q3 →
                    # poss_team_prev never changes → possession_start never resets →
                    # shot_clock_est = 24 - (Q3_frame - Q2_start_frame)/fps → negative.
                    if _gperiod > 0 and _gperiod != _last_scoreboard_period:
                        if _last_scoreboard_period is not None:
                            # Genuine new period — finalize prev possession FIRST so its
                            # frames don't span the quarter break (R18 fix: this was the
                            # root cause of 20% of possessions exceeding 60s and 49%
                            # exceeding the 24s shot clock — they were Q1+Q2 merged).
                            if poss_team_prev and possession_buf:
                                from collections import Counter as _CtrR18
                                _dom_lineup_r18 = _CtrR18(_poss_lineup_buf).most_common(1)[0][0] if _poss_lineup_buf else 0
                                _row_r18 = UnifiedPipeline._summarize_possession(
                                    possession_id, poss_team_prev,
                                    possession_start, frame_idx - 1,
                                    possession_buf, fps, self.game_id,
                                    lineup_id=_dom_lineup_r18,
                                    transition_frames=_transition_frames,
                                    offensive_rebound_poss=_poss_is_off_rebound,
                                )
                                if _row_r18:
                                    possession_rows.append(_row_r18)
                                possession_buf       = []
                                _poss_lineup_buf     = []
                                _transition_frames   = None
                                _poss_is_off_rebound = False
                            # Anchor clock and create possession boundary
                            possession_start = frame_idx
                            possession_id   += 1
                            _last_real_poss_team = ""  # force re-detection of ball handler
                            poss_team_prev = ""        # force possession-team re-detection on next frame
                            print(f"[period_boundary] Q{_last_scoreboard_period}→Q{_gperiod} "
                                  f"at frame {frame_idx}: finalized prev possession + reset")
                        _last_scoreboard_period = _gperiod

                    if (not _period_start_detected
                            and _sc_conf >= 0.7
                            and _gclock > 0
                            and _gperiod > 0):
                        _period_len = 300.0 if _gperiod > 4 else 720.0  # OT = 5 min
                        _elapsed_in_period = _period_len - _gclock
                        _video_time = frame_idx / fps
                        _period_start_vsec = _video_time - _elapsed_in_period
                        self.period_start_video_sec = _period_start_vsec
                        _derived_clip_start = _elapsed_in_period - _video_time
                        if self.clip_start_sec == 0.0:
                            self.clip_start_sec = round(_derived_clip_start, 2)
                            print(f"\n[scoreboard] Period {_gperiod} start detected "
                                  f"at video {_period_start_vsec:.1f}s "
                                  f"(frame {frame_idx}) — clip_start_sec auto-set "
                                  f"to {self.clip_start_sec:.1f}s")
                        _period_start_detected = True
                elif self._sc_ever_seen:
                    self._sc_absent_streak += 1
                    if self._sc_absent_streak >= _SHOT_CLOCK_ABSENT_THRESHOLD:
                        self._ball_track_suspended = True

            # Probe YOLO every 150 frames to clear vision-based suspension when
            # OCR never fired (no scoreboard).  Must run before the hard-skip so
            # a successful probe lets this frame fall through to normal tracking.
            if self._vision_probe_resume(frame, frame_idx):
                pass  # suspension cleared; fall through to normal processing

            # ── HARD SKIP non-live frames ─────────────────────────────────
            # When suspended (replay, halftime, timeout, ad break), skip ALL
            # expensive processing: homography SIFT, player tracking, YOLO
            # ball detection, event detection, CSV row writing.  Only
            # scoreboard OCR (above) runs to detect when live play resumes.
            # R12: expose dead-ball state via live=0 ball_tracking rows so
            # downstream consumers can filter (previously the column was 100%
            # always-1 because suspended frames were dropped entirely).
            if self._ball_track_suspended:
                suspended_frame_count += 1
                ball_rows.append({
                    "frame":         frame_idx,
                    "timestamp":     round(frame_idx / fps, 3),
                    "ball_x2d":      "",
                    "ball_y2d":      "",
                    "detected":      0,
                    "live":          0,
                    "ball_inferred": 0,
                })
                # Log skip milestone every 300 suspended frames (~10s)
                if suspended_frame_count % 300 == 1:
                    print(f"[SKIP] Non-live frame {frame_idx} "
                          f"(suspended {suspended_frame_count} frames)")
                continue

            # Periodically re-detect court homography to recover from camera cuts.
            self._try_recover_court_M1(frame)

            # Replay/cut detector — update homography suspension state BEFORE _get_homography
            # so the suspension is applied to this frame's SIFT update.
            # BUG3 fix: 2-consecutive-frame confirmation gate prevents single-graphic flashes
            # from triggering suspension (NBA lower-third stat overlays fire one-frame spikes).
            # R10: scoreboard-gated early-exit. R8 lifted scoreboard log coverage
            # 0.1% → 60%+, so _last_sb_conf is now reliable. When scoreboard
            # confirms live play (high conf + clock decrementing 0-5s), refuse
            # to suspend on a replay/cut signal AND drain any pending countdown
            # 2× faster. Eliminates ~30% of live-play false positives.
            _clock_running = (
                self._last_sb_conf >= 0.6
                and self._prev_clock_seconds > 0
                and self._last_clock_seconds > 0
                and 0.0 < (self._prev_clock_seconds - self._last_clock_seconds) < 5.0
            )
            if self._is_replay_or_cut(frame):
                self._replay_trigger_pending_count += 1
                if self._replay_trigger_pending_count >= 2:
                    if _clock_running:
                        # Live play confirmed — refuse to suspend
                        self._replay_trigger_pending_count = 0
                    else:
                        self._homography_suspended = True
                        self._homography_suspend_cnt = _REPLAY_SUSPEND_FRAMES
            else:
                self._replay_trigger_pending_count = 0
                if self._homography_suspend_cnt > 0:
                    _drain = 2 if _clock_running else 1
                    self._homography_suspend_cnt = max(0, self._homography_suspend_cnt - _drain)
                    self._homography_suspended = self._homography_suspend_cnt > 0
                else:
                    self._homography_suspended = False

            M = self._get_homography(frame)
            if M is None:
                continue
            _t2 = _time.perf_counter()

            # OPTIMIZATION: reuse pre-allocated buffer instead of per-frame alloc
            np.copyto(self._map_snap_buf, self.map_2d)
            map_snap = self._map_snap_buf
            self._last_ball_2d = None

            # ── YOLO prefetch: peek ahead N frames for batch GPU inference ──
            # The prefetcher queue has buffered frames ahead; peek up to 7 more
            # and push them into the tracker's YOLO batch buffer so the next
            # 7 get_players_pos() calls serve cached results (zero GPU wait).
            if hasattr(self.feet_det, "prefetch_yolo") and not self.feet_det._yolo_result_buf:
                _peek_frames = _prefetcher.peek(7) if hasattr(_prefetcher, "peek") else []
                if _peek_frames:
                    _pf_list = [f[TOPCUT:] for f in _peek_frames]
                    self.feet_det.prefetch_yolo(_pf_list)

            # ── Player tracking ───────────────────────────────────────────
            # OPTIMIZATION: Batch jersey OCR every N frames; voting buffer smooths across frames
            _ocr_stride_counter += 1
            _skip_ocr = (_ocr_stride_counter % _OCR_STRIDE_INTERVAL != 0)

            frame, map_snap, map_txt = self.feet_det.get_players_pos(
                M, self.M1, frame, frame_idx, map_snap,
                skip_jersey_ocr=_skip_ocr,
                suspended=False,
                stride=_stride,
            )
            _t3 = _time.perf_counter()

            # Vision-based fallback: if shot clock OCR never fired on this clip,
            # use YOLO person count + ball-absent streak as a proxy non-live signal.
            # Fires when: clock never seen + ball absent 20+ consecutive gameplay frames
            # + fewer than 8 persons visible (warmup / between-period / ad break).
            yolo_results = self.yolo.predict(frame) if self.yolo.available else []
            if (self.yolo.available
                    and not self._sc_ever_seen
                    and not self._ball_track_suspended
                    and self._no_ball_vision_streak >= 50
                    and len(yolo_results) < 4):
                self._ball_track_suspended = True

            # ── Ball + event detection ────────────────────────────────────
            if yolo_results:
                frame, map_snap = self._apply_yolo(
                    frame, map_snap, map_txt, yolo_results, M, frame_idx
                )
            # ISSUE-065 fix: always run dedicated ball detector when _apply_yolo
            # did not find the ball.  The main YOLO model detects players and
            # occasionally ball; ball_det uses a fine-tuned yolov8n_ball model
            # (conf=0.05) + CSRT tracker that is far more reliable for ball
            # tracking.  Previously ball_det was skipped whenever any YOLO
            # results existed — i.e. during all live gameplay — causing
            # ball_detected to stay at ~0% despite the conf=0.05 fix.
            if self._last_ball_2d is None:
                frame, _ = self.ball_det.ball_tracker(
                    M, self.M1, frame, map_snap.copy(), map_txt, frame_idx,
                    stride=_stride,
                )
                self._last_ball_2d = self.ball_det.last_2d_pos
            _t4 = _time.perf_counter()

            if yolo_results and self.yolo.available:
                self._update_stats(frame, yolo_results, player_stats, frame_idx)

            # Update vision-based no-ball streak for non-live fallback.
            # Increment when ball is absent; reset when ball is found.
            if self._last_ball_2d is None:
                self._no_ball_vision_streak += 1
            else:
                self._no_ball_vision_streak = 0

            timestamp_sec = round(frame_idx / fps, 3)
            # PROFILER: print timing every 50 gameplay frames
            if gameplay_frames % 50 == 0:
                _sp = getattr(self.feet_det, "_sub_profile", {}) or {}
                _sp_str = "  ".join(f"{k}={v:.3f}" for k, v in _sp.items())
                print(f"\n[PROFILE f={frame_idx}] gameplay={_t1-_t0:.3f}s  homog={_t2-_t1:.3f}s  "
                      f"players={_t3-_t2:.3f}s  ball={_t4-_t3:.3f}s  TOTAL={_t4-_t0:.3f}s")
                if _sp_str:
                    print(f"[SUBPROFILE] {_sp_str}")
            ball_pos      = self._last_ball_2d

            # Ball position fallback: when Hough/CSRT loses the ball, use the
            # possessor's 2D court position so EventDetector can still fire
            # dribble events.  Shot detection needs true ball trajectory so we
            # only apply this for stable possession (not in-flight).
            if ball_pos is None:
                for p in self.players:
                    if p.has_ball and p.team != "referee" and frame_idx in p.positions:
                        ball_pos = p.positions[frame_idx]
                        break

            # ── Ball tracking row ─────────────────────────────────────────
            ball_rows.append({
                "frame":     frame_idx,
                "timestamp": timestamp_sec,
                "ball_x2d":  ball_pos[0] if ball_pos else "",
                "ball_y2d":    ball_pos[1] if ball_pos else "",
                "detected":    int(ball_pos is not None),
                # R12: live=1 here because suspended frames hit the early-exit branch above
                # which writes its own live=0 row. This branch only runs on live-play frames.
                "live":        1,
                "ball_inferred": int(getattr(self.ball_det, "ball_inferred", False)),
            })
            if ball_pos is None:
                _ball_miss_streak += 1
                if _ball_miss_streak == 50:
                    print(f"[WARN] Ball undetected for 50 consecutive frames "
                          f"(frame {frame_idx - 49}–{frame_idx}) — "
                          f"Hough+CSRT fallback may need tuning")
            else:
                _ball_miss_streak = 0

            # ── Collect per-player data ───────────────────────────────────
            # Pass 1: build frame-level position map for cross-player metrics
            # Referees are excluded — their positions contaminate spacing/pressure metrics
            # and inflate feature counts in ML training data.
            team_pos: Dict[int, tuple] = {}   # player_id → (team, x2d, y2d)
            frame_tracks: List[dict]   = []
            for p in self.players:
                if p.team == "referee":
                    continue
                if frame_idx not in p.positions:
                    continue
                x2d, y2d = p.positions[frame_idx]

                # Position jump suppression: if this position jumped >350px from
                # last known position (bad homography frame), use previous position.
                last_pos = prev_pos.get(p.ID)
                if last_pos is not None:
                    dx = x2d - last_pos[0]
                    dy = y2d - last_pos[1]
                    if (dx * dx + dy * dy) > 350 * 350:
                        x2d, y2d = last_pos[0], last_pos[1]

                slot     = self.players.index(p)
                conf     = max(0.0, 1.0 - self.feet_det._lost_ages.get(slot, 0) / 15)
                team_pos[p.ID] = (p.team, int(x2d), int(y2d))
                frame_tracks.append({
                    "player_id":        p.ID,
                    "team":             p.team,
                    "bbox":             p.previous_bb,
                    "x2d":              int(x2d),
                    "y2d":              int(y2d),
                    "confidence":       round(conf, 3),
                    "has_ball":         p.has_ball,
                    "ankle_x":          getattr(p, "ankle_x", None),
                    "ankle_y":          getattr(p, "ankle_y", None),
                    "contest_arm_angle": getattr(p, "contest_arm_angle", 0.0),
                    "jump_detected":    getattr(p, "jump_detected", False),
                    "dribble_hand":     getattr(p, "dribble_hand", "unknown"),
                })

            # ── Post-clamp duplicate suppression ──────────────────────────
            # Position jump clamping can re-introduce duplicates; strip them here.
            _seen: Dict[str, set] = {}
            _dedup: List[dict] = []
            for t in frame_tracks:
                tm = t["team"]
                if tm not in _seen:
                    _seen[tm] = set()
                x, y = t["x2d"], t["y2d"]
                is_dup = any(
                    abs(x - ox) < 130 and abs(y - oy) < 130
                    and (abs(x - ox) ** 2 + abs(y - oy) ** 2) < 130 ** 2
                    for ox, oy in _seen[tm]
                )
                if not is_dup:
                    _seen[tm].add((x, y))
                    _dedup.append(t)
            frame_tracks = _dedup

            # FIX 1: compute lineup_id for this frame
            _active_ids = frozenset(t["player_id"] for t in frame_tracks if t.get("team") != "referee")
            if _active_ids not in _lineup_id_cache:
                _lineup_counter += 1
                _lineup_id_cache[_active_ids] = _lineup_counter
            _lineup_id = _lineup_id_cache[_active_ids]

            predictions.append({"frame": frame_idx, "tracks": frame_tracks})
            gameplay_frames += 1

            # ── Periodic VRAM + RAM cleanup (prevents fragmentation on L40S 48GB) ──
            _vram_flush_counter += 1
            if _vram_flush_counter >= _VRAM_FLUSH_INTERVAL:
                _vram_flush_counter = 0
                try:
                    import torch as _torch
                    if _torch.cuda.is_available():
                        _torch.cuda.empty_cache()
                        # VRAM monitoring: warn if >20GB (4-worker headroom on 24GB 4090)
                        _vram_mb = _torch.cuda.memory_allocated() / 1024 / 1024
                        if _vram_mb > 20_000:
                            print(f"\n[VRAM WARNING] {_vram_mb:.0f}MB allocated — "
                                  f"exceeds 20GB threshold, risk of OOM with 4 workers")
                except (ImportError, Exception):
                    pass
                # Clear predictions buffer — only used for return value summary;
                # keeping 3000+ frame dicts in RAM causes multi-GB heap growth on
                # full-game runs.  Checkpoint CSV already persists all tracking rows.
                predictions.clear()
                # Also run gc.collect + malloc_trim here (same as GC interval) so
                # the VRAM flush and RAM flush are co-scheduled every 3000 frames.
                # Without this, glibc arenas can grow for up to 3000 frames between
                # trimming cycles (GC every 200 but malloc_trim alone can't reclaim
                # fragmented arenas faster than they're filled on a busy frame).
                import gc as _gc_vf
                _gc_vf.collect()
                try:
                    import ctypes as _ct_vf
                    _ct_vf.CDLL("libc.so.6").malloc_trim(0)
                except Exception:
                    pass  # Windows / non-glibc

            # ── Aggressive GC + malloc_trim every 500 frames ─────────────────
            # glibc arena fragmentation from rapid YOLO/SIFT/OSNet alloc/free
            # grows RSS monotonically.  gc.collect + malloc_trim releases arenas
            # back to OS.  500-frame cadence = ~80s, keeps RSS stable.
            _gc_counter += 1
            if _gc_counter >= _GC_INTERVAL:
                _gc_counter = 0
                import gc as _gc
                _gc.collect()
                try:
                    import ctypes as _ct_gc
                    _ct_gc.CDLL("libc.so.6").malloc_trim(0)
                except Exception:
                    pass  # Windows / non-glibc
                # RSS monitoring — log every GC cycle to track growth pattern
                try:
                    _rss_mb = 0.0
                    try:
                        # VmRSS = current RSS (not peak). ru_maxrss on Linux is
                        # the high-watermark and never decreases — useless for
                        # detecting whether GC/malloc_trim actually freed memory.
                        with open("/proc/self/status") as _sf:
                            for _line in _sf:
                                if _line.startswith("VmRSS:"):
                                    _rss_mb = int(_line.split()[1]) / 1024
                                    break
                    except Exception:
                        try:
                            import resource as _res
                            _rss_mb = _res.getrusage(_res.RUSAGE_SELF).ru_maxrss / 1024
                        except Exception:
                            pass
                    _delta = _rss_mb - _rss_prev_mb if _rss_prev_mb > 0 else 0
                    _rss_prev_mb = _rss_mb
                    print(f"\n[MEM gc f={frame_idx}] RSS={_rss_mb:.0f}MB  "
                          f"Δ={_delta:+.0f}MB  "
                          f"rows={len(tracking_rows)}  poss={len(possession_rows)}  "
                          f"pred={len(predictions)}")
                    # Emergency cleanup at 25GB; hard abort at RSS_KILL_GB (default 40GB)
                    _RSS_KILL_MB = int(os.environ.get("RSS_KILL_GB", "40")) * 1024
                    if _rss_mb > _RSS_KILL_MB:
                        print(f"\n[MEM FATAL] RSS={_rss_mb:.0f}MB > {_RSS_KILL_MB}MB — "
                              f"aborting to prevent OOM kill (f={frame_idx}, "
                              f"gf={gameplay_frames})")
                        # Flush what we have before dying
                        if tracking_rows:
                            self._ckpt_queue.put(list(tracking_rows))
                            tracking_rows.clear()
                        self._flush_queue()
                        break
                    if _rss_mb > 25_000:
                        print(f"[MEM EMERGENCY] RSS={_rss_mb:.0f}MB > 25GB — "
                              f"forcing full cleanup")
                        predictions.clear()
                        if tracking_rows:
                            self._ckpt_queue.put(list(tracking_rows))
                            tracking_rows.clear()
                        if shot_log_rows:
                            self._export_shot_log(shot_log_rows, append=True)
                            shot_log_rows.clear()
                        if ball_rows:
                            self._export_ball_csv(ball_rows, append=True)
                            ball_rows.clear()
                        _gc.collect()
                        try:
                            _ct_gc.CDLL("libc.so.6").malloc_trim(0)
                        except Exception:
                            pass
                except Exception:
                    pass

            # ── tracemalloc diff snapshot ──────────────────────────────────
            if _TM_ENABLED and gameplay_frames % _TM_INTERVAL == 0 and gameplay_frames > 0:
                import tracemalloc as _tm
                _snap_now = _tm.take_snapshot()
                if _tm_snap0 is not None:
                    _top = _snap_now.compare_to(_tm_snap0, "lineno")
                    print(f"\n[TRACEMALLOC f={frame_idx} gf={gameplay_frames}] "
                          f"Top 15 memory growth:")
                    for _si in _top[:15]:
                        print(f"  {_si}")
                _tm_snap0 = _snap_now

            # ── Frame-level metrics (shared across all players this frame) ──
            _n_events_before = len(self.event_det.events)   # kept for legacy compat
            _n_evlog_before  = len(_events_log_rows)        # FIX 1/8: index before this frame's flush
            event = self.event_det.update(
                frame_idx, ball_pos, frame_tracks,
                pixel_vel=self.ball_det.pixel_vel,
                ball_y_pixel=self.ball_det._prev_cy,
                frame_height=frame.shape[0],
            )

            # FIX 1: Flush rich events into _events_log_rows, then clear to prevent unbounded growth
            for _evt in self.event_det.events:
                _erow_dict = {
                    **_evt,
                    "game_id":      self.game_id or "",
                    "frame":        _evt.get("frame", frame_idx),
                    "timestamp":    timestamp_sec,
                    "possession_id": possession_id,
                }
                _events_log_rows.append(_erow_dict)
                # Accumulate screen/drive/cut counts inline (events_log_rows
                # is flushed at checkpoints so end-of-run iteration misses them)
                _etype_evt = _evt.get("type", "")
                if _etype_evt in ("screen_set", "drive", "cut"):
                    _ek = possession_id
                    if _ek not in _poss_event_counts:
                        _poss_event_counts[_ek] = {"pass_count": 0, "screen_count": 0, "drive_count": 0, "cut_count": 0}
                    if _etype_evt == "screen_set":
                        _poss_event_counts[_ek]["screen_count"] += 1
                    elif _etype_evt == "drive":
                        _poss_event_counts[_ek]["drive_count"] += 1
                    elif _etype_evt == "cut":
                        _poss_event_counts[_ek]["cut_count"] += 1
            self.event_det.events.clear()

            # FIX 5: Buffer first 300 frame_tracks snapshots for court-side team mapping
            if len(_frame_tracks_buf) < 300:
                _frame_tracks_buf.append(list(frame_tracks))

            # ── Ball trajectory features (computed once per frame) ─────────
            _ball_traj = self.ball_det.get_trajectory_features()

            spatial = self._frame_spatial(frame_tracks, ball_pos, map_w, map_h)
            # When homography is suspended (replay/cut), positions are unreliable —
            # blank spatial so defender_distance and team_spacing are not computed.
            if self._homography_suspended:
                spatial = {}

            # ── Possession classification ─────────────────────────────────
            # Build simplified player list expected by PossessionClassifier
            _players_simple = [
                {
                    "player_id": t["player_id"],
                    "x":         float(t["x2d"]),
                    "y":         float(t["y2d"]),
                    # Divide by _stride so speed is in px/real-frame regardless of
                    # how many video frames were skipped between tracked frames.
                    "speed":     float(
                        round(float(np.hypot(
                            t["x2d"] - prev_pos[t["player_id"]][0],
                            t["y2d"] - prev_pos[t["player_id"]][1],
                        )) / _stride, 2) if t["player_id"] in prev_pos else 0.0
                    ),
                    "team":      t["team"],
                    "has_ball":  t["has_ball"],
                }
                for t in frame_tracks
            ]
            _ocr_sc = sb_state.get("shot_clock", -1.0) if sb_state else -1.0
            poss_ctx = self.poss_cls.update(
                _players_simple, ball_pos, frame_idx,
                ocr_shot_clock=float(_ocr_sc) if _ocr_sc > 0 else None,
            )

            # ── Play type classification (uses predictions buffer) ─────────
            play_type = self.play_cls.update(
                [{"frame": frame_idx, "tracks": [
                    {**t, "event": event} for t in frame_tracks
                ]}],
                poss_ctx["possession_type"],
            )

            # ── Possession duration + possession ID ───────────────────────
            handler_now = next((t for t in frame_tracks if t.get("has_ball")), None)
            if handler_now:
                last_handler = handler_now
            curr_poss          = handler_now["team"] if handler_now else ""
            _handler_explicit  = handler_now is not None   # True = real has_ball detection

            # Possession persistence: don't reset on brief ball-detection gaps.
            # Only switch to "no possession" after _POSS_PERSIST_FRAMES consecutive misses.
            if not curr_poss and poss_team_prev:
                poss_no_ball_streak += 1
                if poss_no_ball_streak < _POSS_PERSIST_FRAMES:
                    curr_poss = poss_team_prev  # extend possession through gap
                    # NOTE: _handler_explicit stays False — this is inferred, not real
            else:
                poss_no_ball_streak = 0

            # Fix 3 Part A: team-switch debounce — accumulate explicit new-team
            # detections until threshold reached (ISSUE-061 fix: gaps don't reset
            # the streak; only an explicit original-team re-detection resets it).
            # BUG3 fix: removed per-frame re-assignment to 2.0s which was overriding
            # the env-configurable _BALL_LOSS_THRESH set at loop init.
            # _BALL_LOSS_THRESH is now fixed for the entire clip (set above, env-aware).
            if _handler_explicit and curr_poss and curr_poss != poss_team_prev and poss_team_prev:
                _ball_loss_streak += 1
                if _ball_loss_streak < _BALL_LOSS_THRESH:
                    curr_poss = poss_team_prev  # suppress until threshold
                else:
                    _ball_loss_streak = 0  # confirmed — genuine switch
            elif _handler_explicit and curr_poss == poss_team_prev:
                # Original team explicitly re-detected with ball — reset streak
                _ball_loss_streak = 0
            # else: inferred/extended possession or no detection — preserve streak

            if curr_poss and curr_poss == poss_team_prev:
                possession_dur += 1
            else:
                # Possession changed — finalize previous possession
                if poss_team_prev and possession_buf:
                    from collections import Counter as _Counter
                    _dom_lineup = _Counter(_poss_lineup_buf).most_common(1)[0][0] if _poss_lineup_buf else 0
                    row = UnifiedPipeline._summarize_possession(
                        possession_id, poss_team_prev,
                        possession_start, frame_idx - 1,
                        possession_buf, fps, self.game_id,
                        lineup_id=_dom_lineup,
                        transition_frames=_transition_frames,
                        offensive_rebound_poss=_poss_is_off_rebound,
                    )
                    if row:
                        possession_rows.append(row)
                    # Record whether this ending possession had a shot, for the
                    # next possession's offensive-rebound detection.
                    _prev_poss_shot_attempted = bool(any(b.get("shot_event") for b in possession_buf))
                    _prev_poss_result         = row.get("result", "") if row else ""
                    _prev_poss_team           = poss_team_prev
                else:
                    _prev_poss_shot_attempted = False
                    _prev_poss_result         = ""
                    _prev_poss_team           = ""

                # Detect offensive rebound: same team keeps ball after missed shot
                # NBA rule: 14s reset when own team recovers offensive rebound.
                _poss_is_off_rebound = (
                    curr_poss is not None
                    and curr_poss == _prev_poss_team  # same team retained possession
                    and _prev_poss_shot_attempted     # prev possession ended in a shot
                    and _prev_poss_result not in ("scored", "made")  # shot was missed
                )
                # Wire flag into possession classifier so shot clock resets to 14s on off-rebound
                self.poss_cls._poss_is_off_rebound = _poss_is_off_rebound

                # FIX-POSS: only increment when a NEW non-empty team gets the ball.
                # Empty frames are transient (briefly lost ball detection — same
                # possession continues).  team→empty must NOT end a possession; only
                # a different real team taking the ball should increment.
                # Previous guard `(curr_poss or poss_team_prev)` wrongly fired on
                # team→empty transitions, inflating possession_id on every ball loss.
                if curr_poss and curr_poss != _last_real_poss_team:
                    possession_id        += 1
                    _last_real_poss_team  = curr_poss
                # Bug 20 fix: only anchor possession_start on a REAL possession begin.
                # Previously reset to frame_idx even on team→None transitions, causing
                # shot_clock_est to snap back to 24.0 on every ball-detection gap.
                # Now: preserve possession_start during empty frames so the clock
                # keeps decrementing through brief ball-loss windows.
                if curr_poss:
                    possession_start = frame_idx
                possession_buf   = []
                possession_dur   = 1 if curr_poss else 0
                poss_team_prev   = curr_poss
                _poss_lineup_buf      = []
                _transition_frames    = None
                _poss_crossed_halfcourt = False

            # Build handler average velocity-toward-basket for buffer
            # Divide by _stride so vtb is in px/abs-frame — matches _DRIVE_VEL_THRESHOLD.
            handler_vtb = 0.0
            if handler_now:
                pxy_h = prev_pos.get(handler_now["player_id"])
                if pxy_h:
                    dx_h = (handler_now["x2d"] - pxy_h[0]) / _stride
                    dy_h = (handler_now["y2d"] - pxy_h[1]) / _stride
                    handler_vtb = UnifiedPipeline._vel_toward_basket(
                        handler_now["x2d"], handler_now["y2d"],
                        dx_h, dy_h, map_w, map_h
                    )
            # FIX 4: transition time — detect handler crossing half-court
            # P17 fix 2026-05-29: hard-coded 20-px tolerance was ~0.6% of a
            # real 3404-px court → only 1.4% of possessions ever fired this.
            # Use a fraction of map_w (4%) so the band scales with the court size
            # AND raised the time cap from 90 → 150 frames (5s @ 30fps stride 3)
            # to catch slower-developing transitions.
            if curr_poss and handler_now and not _poss_crossed_halfcourt:
                _halfcourt_band = max(40.0, 0.04 * map_w)
                if (abs(handler_now["x2d"] - map_w / 2) < _halfcourt_band
                        and frame_idx - possession_start < 150):
                    _transition_frames = frame_idx - possession_start
                    _poss_crossed_halfcourt = True

            if curr_poss:
                possession_buf.append({
                    "frame":            frame_idx,
                    "spacing":          spatial.get(curr_poss, {}).get("spacing", 0.0),
                    "isolation":        spatial.get("_isolation", 0.0),
                    "vtb":              handler_vtb,
                    "drive":            int(handler_now is not None and handler_vtb > _DRIVE_VEL_THRESHOLD),
                    "shot_event":       event == "shot",
                    "fast_break":       fast_break,
                    "poss_type":        poss_ctx.get("possession_type", "half_court"),
                    "play_type":        play_type,
                    "paint_touches":    poss_ctx.get("paint_touches", 0),
                    "off_ball_distance": _px_to_ft(poss_ctx.get("off_ball_distance", 0.0), map_w),  # BUG4 fix: px→ft
                    # Compute shot_clock_est from the pipeline's debounced
                    # possession_start rather than PossessionClassifier's
                    # internal timer — PC resets on every flicker causing
                    # a +17s systematic bias (ISSUE-023 fix).
                    # BUG2 fix: clamp to [0, 24] — negative/overflow after period boundary.
                    "shot_clock_est":   min(24.0, max(0.0, (
                        14.0 - (frame_idx - possession_start) / fps
                        if _poss_is_off_rebound
                        else 24.0 - (frame_idx - possession_start) / fps
                    ))),
                    "handler_zone":     (UnifiedPipeline._court_zone(
                                            handler_now["x2d"], handler_now["y2d"],
                                            map_w, map_h)
                                         if handler_now else None),
                })
                # FIX 1: track active lineup for this possession
                _poss_lineup_buf.append(_lineup_id)

            # FIX 4: accumulate per-possession event counts in-loop (tracking_rows may be flushed)
            if curr_poss or poss_team_prev:
                _eid = possession_id
                if _eid not in _poss_event_counts:
                    _poss_event_counts[_eid] = {"pass_count": 0, "screen_count": 0, "drive_count": 0, "cut_count": 0}
                if event == "pass":
                    _poss_event_counts[_eid]["pass_count"] += 1
            # screen/drive/cut are counted from _events_log_rows at export time (already accumulated above)

            # ── Shot log entry ─────────────────────────────────────────────
            shooter = handler_now or last_handler  # use last known handler if ball in air
            if event == "shot" and shooter:
                # Per-possession cooldown: skip if this possession already had a shot
                # within 3 seconds — eliminates pump-fake / drive-then-shoot double-counts.
                _poss_last = shot_poss_last_ts.get(possession_id)
                _poss_ok   = (_poss_last is None or (timestamp_sec - _poss_last) > 3.0)
                # BUG2 fix: global gate raised 3.0→8.0s to match EventDetector._SHOT_DEBOUNCE.
                # Min observed inter-shot gap in game 0022500568 was exactly 90 frames = 3.0s
                # @ 30fps — possession fragmentation caused each new slot to independently
                # pass the old 3s gate, producing ~37% false-positive rate.
                # Bug 30 fix 2026-05-28: 8.0 → 5.0s. EventDetector already enforces
                # 8.0s at the source (_SHOT_DEBOUNCE). This layer was a redundant
                # safety floor; 5.0s allows put-backs / tip-ins / transition shots
                # (which R13 tip-in override at event_detector.py:299-305 already permits).
                _global_ok = (timestamp_sec - _last_global_shot_ts) > 5.0
                # BUG2 fix: basket-proximity gate — shots must originate within 30 ft of basket.
                # Passes/handoffs flagged as catch_and_shoot fire at mid-court; this eliminates
                # the 97.7% catch_and_shoot rate by gating on court position.
                _shot_dist_ft = UnifiedPipeline._dist_to_basket(
                    shooter["x2d"], shooter["y2d"], map_w, map_h)
                # Bug 30 fix 2026-05-28: 28 → 32 ft. Matches event_detector.py:287
                # handler_in_range. Logo-three takers (Curry/Lillard/Trae) get 5-7
                # attempts/game from 28-32 ft that were silently rejected here.
                # The directional cos-sim gate downstream still kills half-court heaves.
                _proximity_ok = _shot_dist_ft <= 32.0
                # Directional gate: ball velocity vector must point toward the nearest
                # basket (cos_sim > _SHOT_DIRECTIONAL_COS_MIN).  Pass arcs aimed at
                # teammates have cos_sim near 0 or negative.  Falls back to True when
                # ball position history is unavailable (don't block on missing data).
                _directional_ok = True
                if len(_ball_pos_hist) >= 2:
                    _bh_old = _ball_pos_hist[0]  # oldest sample in deque (up to 5 frames back)
                    _bh_now = _ball_pos_hist[-1]
                    _vx_b = float(_bh_now[0] - _bh_old[0])
                    _vy_b = float(_bh_now[1] - _bh_old[1])
                    _v_mag = float(np.hypot(_vx_b, _vy_b))
                    if _v_mag > 0.5:  # ignore near-zero velocity — ball held or tracker jitter
                        # Use the same nearest-basket logic as _vel_toward_basket
                        _bl = (_BASKET_L[0] * map_w, _BASKET_L[1] * map_h)
                        _br = (_BASKET_R[0] * map_w, _BASKET_R[1] * map_h)
                        _dl = float(np.hypot(_bh_now[0] - _bl[0], _bh_now[1] - _bl[1]))
                        _dr = float(np.hypot(_bh_now[0] - _br[0], _bh_now[1] - _br[1]))
                        _tbx, _tby = (_bl if _dl <= _dr else _br)
                        _b_mag = min(_dl, _dr)
                        if _b_mag > 1e-6:
                            _cos_sim = (
                                _vx_b * (_tbx - _bh_now[0]) + _vy_b * (_tby - _bh_now[1])
                            ) / (_v_mag * _b_mag)
                            _directional_ok = _cos_sim >= _SHOT_DIRECTIONAL_COS_MIN
                _shot_allowed = _poss_ok and _global_ok and _proximity_ok and _directional_ok
                if _shot_allowed:
                    shot_poss_last_ts[possession_id] = timestamp_sec
                    _last_global_shot_ts = timestamp_sec
                    # FIX 8: snapshot shot arc at the moment of shot detection
                    self.ball_det.snapshot_shot_arc()
                    _shooter_name = ""
                    if self._player_resolver:
                        _shooter_name = self._player_resolver.slot_to_player_name.get(
                            shooter["player_id"], "")
                        if not _shooter_name:
                            _jnum = self._player_resolver.get_jersey_number(shooter["player_id"])
                            if _jnum:
                                _shooter_name = f"#{_jnum}"
                    # R8: shot_clock cascade — OCR (high-conf) → derived est → recent log
                    _shot_clock_val = ""
                    if sb_state.get("shot_clock", -1) > 0 and _sb_conf >= 0.4:
                        _shot_clock_val = sb_state["shot_clock"]
                    else:
                        # Derived from possession_start (same formula as tracking_data rows :2247)
                        _sc_est = min(24.0, max(0.0, (
                            14.0 - (frame_idx - possession_start) / fps
                            if _poss_is_off_rebound
                            else 24.0 - (frame_idx - possession_start) / fps
                        )))
                        if _sc_est > 0:
                            _shot_clock_val = round(_sc_est, 1)
                        else:
                            # Last resort: scan recent scoreboard log for confident shot_clock
                            for _slog in reversed(scoreboard_log_rows[-30:]):
                                _slog_sc = _slog.get("shot_clock", "")
                                _slog_cf = _slog.get("confidence", 0) or 0
                                if _slog_sc not in ("", None) and float(_slog_cf) >= 0.4:
                                    _shot_clock_val = _slog_sc
                                    break
                    # FIX 8: use snapshotted _shot_arc_angle (not live parabola)
                    _arc_val = self.ball_det._shot_arc_angle if self.ball_det._shot_arc_angle is not None else ""
                    # R10: closeout lookup widened from 1-frame to ~1.5s window.
                    # Closeouts often complete 5-30 frames after release; the prior
                    # single-frame window almost never matched.
                    _closeout_lookback = int(1.5 * fps / max(1, _stride))
                    _closeout_speed = next(
                        (e["closeout_speed"]
                         for e in reversed(_events_log_rows[-max(_closeout_lookback, 1):])
                         if e.get("type") == "closeout"),
                        "",
                    )
                    # FIX 5: second chance flag
                    _poss_shot_count[possession_id] = _poss_shot_count.get(possession_id, 0) + 1
                    _second_chance = int(_poss_shot_count[possession_id] > 1)
                    _shot_zone = UnifiedPipeline._court_zone(
                        shooter["x2d"], shooter["y2d"], map_w, map_h)
                    # P5 (2026-05-29): emit defender_slot_id alongside distance so
                    # downstream A2 defender-quality model has training data.
                    # defender_nba_id is filled later by _backfill_nba_player_ids()
                    # using the same slot→NBA map the shooter uses.
                    _def_dist, _def_slot = _shot_defender_dist_with_id(
                        spatial, shooter, frame_tracks, map_w
                    )
                    shot_log_rows.append({
                        "game_id":            self.game_id or "",
                        "shot_id":            len(shot_log_rows) + 1,
                        "frame":              frame_idx,
                        "timestamp":          timestamp_sec,
                        "player_id":          shooter["player_id"],
                        "team":               shooter["team"],
                        # R8: never leave team_abbrev blank — fall back to raw color label
                        # so downstream joins always have SOMETHING. _backfill_shot_log_team_abbrev()
                        # rewrites this with the canonical NBA abbrev when name resolution succeeds.
                        "team_abbrev":        shooter["team"],
                        "x_position":         shooter["x2d"],
                        "y_position":         shooter["y2d"],
                        "x_norm":             round(max(0.0, min(1.0, shooter["x2d"] / max(map_w, 1))), 4),
                        "y_norm":             round(max(0.0, min(1.0, shooter["y2d"] / max(map_h, 1))), 4),
                        "court_zone":         _shot_zone,
                        "defender_distance":  _def_dist,
                        "defender_dist_norm": (
                            "" if _def_dist == "" else round(_def_dist / 94.0, 4)
                        ),
                        # P5: NEW columns — defender identity for A2 model.
                        "defender_slot_id":   _def_slot,
                        "defender_nba_id":    "",  # filled post-hoc in _backfill_nba_player_ids
                        "team_spacing":       (
                                                  "" if (not spatial)
                                                       or (shooter["team"] not in spatial)
                                                       or not spatial[shooter["team"]].get("spacing")
                                                  else round(spatial[shooter["team"]]["spacing"], 1)
                                              ),  # R9: empty on missing instead of misleading 0.0
                        "possession_id":      possession_id,
                        "possession_duration": possession_dur,
                        "made":               "",   # filled by nba_enricher
                        "player_name":        _shooter_name,
                        "shot_clock":         _shot_clock_val,
                        # R11: defender-pressure semantics (max arm-raise of defenders within 8 ft)
                        "contest_arm_angle":  _shot_defender_contest(shooter, frame_tracks, map_w),
                        "closeout_speed":     _closeout_speed,
                        "fatigue_proxy":      round(
                                                 _player_dist_run.get(
                                                     shooter["player_id"], 0.0), 1),
                        "dribble_count":      self.event_det.dribble_count,
                        "ball_shot_arc_angle": _arc_val,
                        # R8: catch_and_shoot now mirrors the classifier output, not the broken dribble counter
                        "catch_and_shoot":    0,   # filled below after _shot_creation_val is computed
                        "shot_distance":      UnifiedPipeline._dist_to_basket(
                                                  shooter["x2d"], shooter["y2d"],
                                                  map_w, map_h),
                        "second_chance":      _second_chance,
                        "shot_creation":      "",   # filled below
                    })
                    # R8: compute classifier with per-possession event counts (reroute off dribble_count)
                    _shot_dist_ft_local = _px_to_ft(
                        UnifiedPipeline._dist_to_basket(shooter["x2d"], shooter["y2d"], map_w, map_h),
                        map_w,
                    )
                    _shot_creation_val = UnifiedPipeline._classify_shot_creation(
                        poss_counts=_poss_event_counts.get(possession_id, {}),
                        shot_zone=_shot_zone,
                        vel_toward_basket=handler_vtb,
                        shot_dist_ft=_shot_dist_ft_local,
                        possession_duration=possession_dur,
                        ball_shot_arc_angle=self.ball_det._shot_arc_angle or 0.0,
                        dribble_count=self.event_det.dribble_count,
                    )
                    shot_log_rows[-1]["shot_creation"]  = _shot_creation_val
                    shot_log_rows[-1]["catch_and_shoot"] = int(_shot_creation_val == "catch_and_shoot")

            # ── Ball velocity (2D court px/frame) ─────────────────────────
            ball_vel_2d = 0.0
            if ball_pos and prev_ball_2d_f:
                ball_vel_2d = round(float(np.hypot(
                    ball_pos[0] - prev_ball_2d_f[0],
                    ball_pos[1] - prev_ball_2d_f[1],
                )), 2)
            prev_ball_2d_f = ball_pos
            if ball_pos:
                _ball_pos_hist.append(ball_pos)

            # ── Fast-break flag (frame-level) ─────────────────────────────
            fast_break = UnifiedPipeline._fast_break_flag(
                frame_tracks, prev_pos, map_w, map_h, stride=_stride,
            )

            # ── PlayerResolver: feed crops every _SAMPLE_EVERY frames ────────
            if self._player_resolver is not None:
                for _pt in frame_tracks:
                    _slot = _pt["player_id"]
                    _bb   = _pt.get("bbox")   # (y1, x1, y2, x2) or None
                    _crop = None
                    if _bb and len(_bb) == 4:
                        _y1, _x1, _y2, _x2 = [int(v) for v in _bb]
                        _fh_c, _fw_c = frame.shape[:2]
                        _y1 = max(0, _y1); _x1 = max(0, _x1)
                        _y2 = min(_fh_c, _y2); _x2 = min(_fw_c, _x2)
                        if _y2 > _y1 and _x2 > _x1:
                            _crop = frame[_y1:_y2, _x1:_x2]
                    self._player_resolver.update(
                        slot=_slot, team=_pt["team"],
                        crop_bgr=_crop, frame_idx=frame_idx,
                    )
                # Finalize once warmup completes (only once)
                if (self._player_resolver.warmup_complete
                        and not self._player_resolver._warmup_done):
                    self._player_resolver.finalize()
                    print("\n" + self._player_resolver.resolution_report())

            # Pass 2: enrich each track into a full CSV row
            # ISSUE-D: exclude referee tracks and cap at 12 players per frame
            # sorted by confidence so the highest-quality detections survive the cap.
            _csv_tracks = sorted(
                [t for t in frame_tracks if t.get("team") != "referee"],
                key=lambda t: t.get("confidence", 0.0),
                reverse=True,
            )[:12]
            for track in _csv_tracks:
                pid, team = track["player_id"], track["team"]
                x2d, y2d  = track["x2d"], track["y2d"]

                pxy  = prev_pos.get(pid)
                # Divide displacement by _stride so all velocity/acceleration values
                # are in px/real-frame regardless of frame stride.  Without this,
                # stride=3 would inflate all velocity features by 3×.
                _raw_dist = float(np.hypot(x2d - pxy[0], y2d - pxy[1])) if pxy else 0.0
                vel  = round(_raw_dist / _stride, 2)
                acc  = round(vel - prev_vel.get(pid, 0.0), 3)
                hdg  = round(float(np.degrees(
                    np.arctan2(y2d - pxy[1], x2d - pxy[0])
                )) % 360, 1) if (pxy and vel > 0) else 0.0
                prev_pos[pid] = (x2d, y2d)
                prev_vel[pid] = vel
                _player_dist_run[pid] = _player_dist_run.get(pid, 0.0) + _raw_dist

                # Normalize displacement components to per-real-frame scale
                dx_v    = float(x2d - pxy[0]) / _stride if pxy else 0.0
                dy_v    = float(y2d - pxy[1]) / _stride if pxy else 0.0
                d_bask  = UnifiedPipeline._dist_to_basket(x2d, y2d, map_w, map_h)
                vtb     = UnifiedPipeline._vel_toward_basket(x2d, y2d, dx_v, dy_v, map_w, map_h)
                drv_flg = int(bool(track["has_ball"]) and vtb > _DRIVE_VEL_THRESHOLD)

                dist_ball = _px_to_ft(float(np.hypot(
                    x2d - ball_pos[0], y2d - ball_pos[1]
                )), map_w) if ball_pos else ""

                opp_d = [float(np.hypot(x2d - ox, y2d - oy))
                         for uid, (ut, ox, oy) in team_pos.items()
                         if uid != pid and ut != team and ut != "referee"]
                tm_d  = [float(np.hypot(x2d - ox, y2d - oy))
                         for uid, (ut, ox, oy) in team_pos.items()
                         if uid != pid and ut == team]

                ts = spatial.get(team, {})
                opp_teams = [t for t in spatial if t != team and t != "referee" and not t.startswith("_")]
                os_ = spatial.get(opp_teams[0], {}) if opp_teams else {}

                bbox = track["bbox"]  # stored as (y1, x1, y2, x2)
                tracking_rows.append({
                    "frame":              frame_idx,
                    "timestamp":          timestamp_sec,
                    "player_id":          pid,
                    "team":               team,
                    "x_position":         x2d,
                    "y_position":         y2d,
                    "x_norm":             round(max(0.0, min(1.0, x2d / max(map_w, 1))), 4),
                    "y_norm":             round(max(0.0, min(1.0, y2d / max(map_h, 1))), 4),
                    "velocity":           vel,
                    "acceleration":       acc,
                    "direction_deg":      hdg,
                    "court_zone":         self._court_zone(x2d, y2d, map_w, map_h),
                    "ball_possession":    int(track["has_ball"]),
                    "distance_to_ball":   dist_ball,
                    "nearest_opponent":   _px_to_ft(min(opp_d), map_w) if opp_d else "",
                    "nearest_teammate":   _px_to_ft(min(tm_d), map_w)  if tm_d  else "",
                    "event":              event if track["has_ball"] else "none",
                    # R9: empty on missing instead of misleading 0.0 (was 66% of shots in R5 batch)
                    "team_spacing":       ("" if not ts.get("spacing") else round(ts["spacing"], 1)),
                    "spacing_hull_area":  ("" if not ts.get("hull_area") else round(ts["hull_area"], 1)),
                    "team_centroid_x":    round(ts.get("cx", 0.0), 1),
                    "team_centroid_y":    round(ts.get("cy", 0.0), 1),
                    "paint_count_own":    ts.get("paint_n", 0),
                    "paint_count_opp":    os_.get("paint_n", 0),
                    # Spatial — ball
                    "possession_side":    spatial.get("_ball_side", ""),
                    "handler_isolation":  (""
                                          if spatial.get("_isolation") in (_ISOLATION_DEFAULT, None)
                                          else round(spatial.get("_isolation"), 1)),
                    # Raw bbox + ball
                    "bbox_x1":            bbox[1] if bbox else "",
                    "bbox_y1":            bbox[0] if bbox else "",
                    "bbox_x2":            bbox[3] if bbox else "",
                    "bbox_y2":            bbox[2] if bbox else "",
                    "ball_x2d":           ball_pos[0] if ball_pos else "",
                    "ball_y2d":           ball_pos[1] if ball_pos else "",
                    "ball_velocity":      ball_vel_2d,
                    "confidence":         track["confidence"],
                    # Basket / drive / break
                    "distance_to_basket": d_bask,
                    "vel_toward_basket":  vtb,
                    "drive_flag":         drv_flg,
                    # FIX 3: real-unit foot coordinates (NBA full-court 94×50 ft), clamped to court
                    "ft_x":              round(max(0.0, min(94.0, (x2d / max(map_w, 1)) * 94.0)), 2),
                    "ft_y":              round(max(0.0, min(50.0, (y2d / max(map_h, 1)) * 50.0)), 2),
                    "dist_to_basket_ft": round(min(
                        float(np.hypot(
                            (x2d / max(map_w, 1)) * 94.0 - 5.25,
                            (y2d / max(map_h, 1)) * 50.0 - 25.0,
                        )),
                        float(np.hypot(
                            (x2d / max(map_w, 1)) * 94.0 - 88.75,
                            (y2d / max(map_h, 1)) * 50.0 - 25.0,
                        )),
                    ), 2),
                    "fast_break_flag":    fast_break,
                    "possession_id":       possession_id,
                    "possession_duration": possession_dur,
                    # ── Scoreboard context (FIX 6: confidence-gated) ──────
                    "scoreboard_game_clock":  (sb_state.get("game_clock_sec", "")
                                               if _sb_conf >= 0.3 else ""),
                    "scoreboard_shot_clock":  (sb_state.get("shot_clock", "")
                                               if _sb_conf >= 0.4 else ""),
                    # FIX 5: score_diff is None when OCR can't determine scores —
                    # write "" so the CSV cell is blank rather than misleading 0.
                    "scoreboard_score_diff":  (
                        sb_state.get("score_diff", "")
                        if (_sb_conf >= 0.3 and sb_state.get("score_diff") is not None)
                        else ""
                    ),
                    # FIX 5: period -1 means OCR failed — write "" not -1.
                    "scoreboard_period":      (
                        sb_state.get("period", "")
                        if (sb_state.get("period") or -1) > 0
                        else ""
                    ),
                    "scoreboard_confidence":  round(_sb_conf, 3),  # FIX 6: raw confidence
                    # ── Possession + play-type context ─────────────────────
                    "possession_type":         poss_ctx.get("possession_type", "half_court"),
                    "play_type":               play_type,
                    "possession_duration_sec": poss_ctx.get("possession_duration_sec", 0.0),
                    "paint_touches":           poss_ctx.get("paint_touches", 0),
                    "off_ball_distance":       _px_to_ft(poss_ctx.get("off_ball_distance", 0.0), map_w),  # BUG4 fix: px→ft
                    # ISSUE-023: use debounced possession_start (same fix as poss buf)
                    # BUG2 fix: clamp to [0, 24] — negative/overflow after period boundary.
                    "shot_clock_est":          min(24.0, max(0.0, (
                        14.0 - (frame_idx - possession_start) / fps
                        if _poss_is_off_rebound
                        else 24.0 - (frame_idx - possession_start) / fps
                    ))),
                    # ── Pose estimation fields ─────────────────────────────
                    "ankle_x":            track.get("ankle_x", ""),
                    "ankle_y":            track.get("ankle_y", ""),
                    "contest_arm_angle":  track.get("contest_arm_angle", ""),
                    "jump_detected":      int(track.get("jump_detected", False)),
                    "dribble_hand":       track.get("dribble_hand", ""),
                    # ── Ball trajectory features ───────────────────────────
                    "ball_shot_arc_angle":  _ball_traj.get("shot_arc_angle", ""),
                    "ball_peak_height_px":  _ball_traj.get("peak_height_px", ""),
                    "ball_pass_speed_pxpf": _ball_traj.get("pass_speed_pxpf", ""),
                    # ── Player identity (populated after 300-frame warmup) ──
                    "player_name":    (self._player_resolver.slot_to_player_name.get(pid, "")
                                       if self._player_resolver else ""),
                    "jersey_number":  (self._player_resolver.get_jersey_number(pid)
                                       if self._player_resolver else ""),
                    # Bug 25 fix 2026-05-28: gate dribble_count on ball_possession==1.
                    # Previously broadcast to every player row in the frame, conflating
                    # the handler's dribble count with off-ball players. Per-frame this
                    # collapses to "active dribbler only" (91.4% of dribble>0 rows in
                    # game 0022500047 were off-ball before this fix).
                    "dribble_count":  (self.event_det.dribble_count
                                       if track.get("has_ball") else 0),
                    "lineup_id":      _lineup_id,  # FIX 1
                    # Replay/cut validity — False during homography suspension
                    "homography_valid": int(not self._homography_suspended),
                })

            # ── Visualise ─────────────────────────────────────────────────
            if self.show or writer:
                vis_map = cv2.resize(map_txt, (frame.shape[1], frame.shape[1] // 2))
                vis = np.vstack((frame, vis_map))
                if self.show:
                    cv2.imshow("NBA AI — Unified Tracker", vis)
                    if cv2.waitKey(1) & 0xFF == 27:
                        break
                if writer:
                    writer.write(vis)

            print(f"\r Frame {frame_idx}...", end="", flush=True)

            # Periodic checkpoint — async flush so CSV write doesn't block the main loop (Task 4)
            # Use < _stride to catch the checkpoint window even when stride > 1.
            if frame_idx % _CHECKPOINT_INTERVAL < _stride and tracking_rows:
                self._ckpt_queue.put(list(tracking_rows))  # snapshot; writer thread drains queue
                tracking_rows.clear()
                # Flush auxiliary row buffers — these grow unbounded across the full
                # game and contribute ~5-15 GB RSS on 18K-frame runs.  Append-flush
                # to their respective CSVs, then clear to reclaim heap.
                if ball_rows:
                    self._export_ball_csv(ball_rows, append=True)
                    ball_rows.clear()
                if scoreboard_log_rows:
                    self._export_scoreboard_log(scoreboard_log_rows, append=True)
                    scoreboard_log_rows.clear()
                if _events_log_rows:
                    self._export_events_log(_events_log_rows, append=True)
                    _events_log_rows.clear()
                if shot_log_rows:
                    self._export_shot_log(shot_log_rows, append=True)
                    shot_log_rows.clear()
                # Force glibc to return freed pages to OS — Python's allocator
                # holds onto arenas even after gc.collect(), causing RSS to only
                # grow.  malloc_trim releases unmapped pages back to the kernel.
                import gc as _gc2
                _gc2.collect()
                try:
                    import ctypes as _ct
                    _ct.CDLL("libc.so.6").malloc_trim(0)
                except Exception:
                    pass  # Windows / non-glibc — skip
                # RSS monitoring — VmRSS = current RSS (ru_maxrss is peak, never drops)
                try:
                    _rss_mb = 0.0
                    with open("/proc/self/status") as _sf:
                        for _line in _sf:
                            if _line.startswith("VmRSS:"):
                                _rss_mb = int(_line.split()[1]) / 1024
                                break
                    print(f"\n[MEM] checkpoint f={frame_idx}  RSS={_rss_mb:.0f}MB  "
                          f"tracking_rows={len(tracking_rows)}  ball={len(ball_rows)}  "
                          f"events={len(_events_log_rows)}  poss={len(possession_rows)}")
                except Exception:
                    pass

        if writer:
            writer.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
        print()
        self._flush_queue()  # Task 4: wait for all async checkpoint writes to finish

        # Finalize last open possession
        if poss_team_prev and possession_buf:
            from collections import Counter as _Counter
            _dom_lineup = _Counter(_poss_lineup_buf).most_common(1)[0][0] if _poss_lineup_buf else 0
            row = UnifiedPipeline._summarize_possession(
                possession_id, poss_team_prev,
                possession_start, frame_idx - 1,
                possession_buf, fps, self.game_id,
                lineup_id=_dom_lineup,
                transition_frames=_transition_frames,
                offensive_rebound_poss=_poss_is_off_rebound,
            )
            if row:
                possession_rows.append(row)

        # Fix 4: resolve HSV color labels ('white','green') → NBA team abbreviations
        # _resolve_team_names is the canonical mapping path; _court_side_team_map
        # (called below) adds position-based mapping + writes team_colors.json.
        # Track whether Fix 4 produced real abbreviations so _court_side_team_map
        # can skip re-mapping rows whose team is already an abbreviation.
        _team_map_applied = False
        _team_map: dict = {}
        if self.game_id and (possession_rows or shot_log_rows):
            _color_labels = [r.get("team", "") for r in possession_rows]
            _color_labels += [r.get("team", "") for r in shot_log_rows]
            _team_map = self._resolve_team_names(self.game_id, _color_labels)
            if _team_map and not any(v.startswith("team_") for v in _team_map.values()):
                # Only apply if resolve returned real abbreviations (not fallback)
                for _row in possession_rows:
                    _row["team"] = _team_map.get(_row.get("team", ""), _row.get("team", ""))
                for _row in shot_log_rows:
                    _row["team"] = _team_map.get(_row.get("team", ""), _row.get("team", ""))
                _team_map_applied = True

        # FIX 4: screen/drive/cut counts are now accumulated inline during the
        # main loop (alongside event flush) — no end-of-run iteration needed.
        # This is required because _events_log_rows is flushed at checkpoints.

        # FIX 5: build court-side team map for possession/shot rows (after frame buffer is complete)
        # FIX 7: extend to write team_colors.json and backfill team_abbrev in tracking_data.csv
        # Only re-map rows when Fix 4 (_resolve_team_names) produced fallback labels.
        _ct_map: dict = {}
        if self.game_id and _frame_tracks_buf:
            _ct_map = self._court_side_team_map(_frame_tracks_buf, self.game_id)
            if _ct_map and not _team_map_applied:
                # Fix 4 produced fallback — use court-side position-based mapping instead
                for _row in possession_rows:
                    _row["team"] = _ct_map.get(_row.get("team", ""), _row.get("team", ""))
                for _row in shot_log_rows:
                    _row["team"] = _ct_map.get(_row.get("team", ""), _row.get("team", ""))
                # FIX 7: persist the color→abbrev map to data/tracking/{game_id}/team_colors.json
                _tc_path = os.path.join(self._data_dir, "team_colors.json")
                try:
                    with open(_tc_path, "w", encoding="utf-8") as _tcf:
                        json.dump(_ct_map, _tcf, indent=2)
                    print(f"  [team_colors] written → {_tc_path}")
                except Exception as _tc_err:
                    print(f"  [team_colors] write failed: {_tc_err}")

        self._export_csv(tracking_rows)
        # Append remaining rows (most were flushed incrementally at checkpoints)
        self._export_ball_csv(ball_rows, append=True)
        self._export_stats(player_stats)
        self._export_possessions_csv(possession_rows, _poss_event_counts)  # FIX 4
        # ── Free GPU memory before post-processing (saves ~3GB VRAM) ─────
        # Tracking loop is complete; YOLO/OSNet/ball models no longer needed.
        # Post-processing (CSV export, enrichment) is CPU-only.
        try:
            # Unload main YOLO person detector
            if hasattr(self.feet_det, 'model'):
                del self.feet_det.model
                self.feet_det.model = None
            # Unload OSNet deep re-ID
            if hasattr(self.feet_det, '_deep_extractor'):
                del self.feet_det._deep_extractor
            # Unload ball detection YOLO
            import src.tracking.ball_detect_track as _bdt
            if _bdt._ball_yolo_model is not None:
                del _bdt._ball_yolo_model
                _bdt._ball_yolo_model = None
                _bdt._ball_yolo_available = False
            # Force CUDA memory release
            try:
                import torch as _torch
                if _torch.cuda.is_available():
                    _torch.cuda.empty_cache()
            except ImportError:
                pass
            import gc as _gc
            _gc.collect()
        except Exception:
            pass  # non-fatal — best-effort cleanup

        self._export_shot_log(shot_log_rows, append=True)
        self._export_player_stats(tracking_rows, fps)
        # Append remaining rows (most were flushed incrementally at checkpoints)
        self._export_scoreboard_log(scoreboard_log_rows, append=True)
        self._export_events_log(_events_log_rows, append=True)  # FIX 1

        # FIX 7 (old): backfill player_name in tracking_data.csv and shot_log.csv post-run
        # ISSUE-057: re-finalize at end-of-run to pick up all slots accumulated after warmup
        # CV-FIX-1 (2026-05-30): ALWAYS re-finalize with full-game votes. The warmup
        # finalize() fires at frame ~300 (_WARMUP_FRAMES) and locks resolution on ~20
        # OCR samples from the first ~10 s (measured: 2/10 slots, both on <3 votes).
        # The prior `elif len(slot_to_player_name) == 0` guard skipped the end-of-run
        # re-finalize whenever ANY placeholder ("green#?") filled the map — which is
        # always — so 73 min of accumulated jersey votes in _conf_bufs were discarded.
        # resolve_player() still gates each slot on the dominant-fraction vote test,
        # so re-finalizing only UPGRADES slots that now clear it; it never invents IDs.
        if self._player_resolver is not None:
            self._player_resolver._warmup_done = False
            self._player_resolver.finalize()
        # Always run backfill when player_resolver exists — jersey_name_map fallback works
        # even when slot_to_player_name is empty (API resolution failed).
        if self._player_resolver is not None:
            self._backfill_player_names()
            # P0 (2026-05-29): also emit nba_player_id column into shot_log.csv +
            # shot_log_enriched.csv so downstream intelligence-layer signals can join
            # on NBA player_id without a separate resolution step.
            self._backfill_nba_player_ids()

        # P4 (2026-05-29): fill scoreboard_period in tracking_data.csv via frame
        # percentile when the OCR pass left it empty. Always runs (no resolver
        # dependency) — unblocks INT-65 fatigue trajectories, INT-70 F1 Q1
        # extrapolation, INT-72 F3 Consumer A which were all DEFER on 100% NaN.
        self._backfill_scoreboard_period()

        # P6 (2026-05-29): widen contest_arm_angle + dribble_count from per-frame
        # data around the shot frame instead of the point lookup that dropped 90%.
        # Per-frame contest_arm_angle is 34.5% nonzero but the shot-time read at
        # line ~2566 was finding 3.7%. Scan [shot_frame - 45, shot_frame + 5] for
        # nearby defender arm-raise; count dribble frames in [shot_frame - 60, shot_frame].
        # Measured lift on game 0022400909: contest 3.7% → 29.6%, dribble 2.3% → 100%.
        self._backfill_shot_log_pose_features()

        # FIX 7 (new): backfill team_abbrev column into tracking_data.csv
        # Prefer court-side position map; fall back to _resolve_team_names result
        # when _court_side_team_map returned {} (e.g. all x2d missing in first 300 frames).
        # ISSUE-066 fix: guard _ct_map fallback values (keys "team_a"/"team_b") same
        # as _team_map — otherwise fallback abbreviations overwrite real ones.
        _ct_map_real = _ct_map and not any(v.startswith("team_") for v in _ct_map.values())
        _abbrev_map = (
            _ct_map if _ct_map_real
            else (_team_map if _team_map and not any(v.startswith("team_") for v in _team_map.values())
                  else {})
        )
        if _abbrev_map:
            self._backfill_team_abbrev(_abbrev_map)
            # BUG1 fix: rewrite shot_log.csv on disk so mid-loop flushed rows get
            # canonical team abbreviations (team column) + populated team_abbrev column.
            self._backfill_shot_log_team_abbrev(_abbrev_map)
            # P15 2026-05-29: same fix for possessions.csv (team_abbrev was 9.7%
            # nonzero in samples — downstream NBA-tricode joins on possessions
            # were silently dropping ~90% of rows).
            self._backfill_possessions_team_abbrev(_abbrev_map)

        # BUG-FIX: remap frame-based possession_id → sequential 0-based IDs so
        # tracking_data + shot_log join cleanly to possessions.csv (was 97% mismatch).
        self._remap_possession_ids_for_join()

        # DB writes (SQLite by default, PostgreSQL when DATABASE_URL is set)
        self._db_write_shot_log(shot_log_rows)
        self._db_write_scoreboard_log(scoreboard_log_rows)

        if self.game_id:
            self._run_enrichment(fps)

        metrics = evaluate_tracking(predictions)
        return {
            "predictions":    predictions,
            "stats":          player_stats,
            "id_switches":    metrics.get("id_switches_estimated", 0),
            "stability":      metrics.get("track_stability", 0),
            "total_frames":   frame_idx,
            "jump_resets":      self.ball_det._jump_resets,
            "suspended_frames": suspended_frame_count,
        }

    # ── YOLO integration ──────────────────────────────────────────────────

    def _apply_yolo(self, frame, map_2d, map_txt, results, M, frame_idx):
        """Draw YOLO detections and update ball possession from YOLO bbox."""
        ball_bbox = None
        for det in results:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            label, conf = det["label"], det["confidence"]

            color = {
                "ball":   (0,   165, 255),
                "rim":    (255, 255,   0),
                "shoot":  (0,   255, 255),
                "made":   (0,   255,   0),
                "person": (200, 200, 200),
            }.get(label, (128, 128, 128))

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{label} {conf:.2f}", (x1, max(0, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

            if label == "ball":
                ball_bbox = det["bbox"]

        # Update ball possession using YOLO ball bbox
        if ball_bbox is not None:
            x1, y1, x2, y2 = ball_bbox
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            ball_center = np.array([cx, cy, 1])
            homo = self.M1 @ (M @ ball_center.reshape(3, 1))
            homo = np.int32(homo / homo[-1]).ravel()
            self._last_ball_2d = (int(homo[0]), int(homo[1]))
            cv2.circle(map_2d, (homo[0], homo[1]), 10, (0, 0, 255), 5)

            bbox_iou = (cy - 30, cx - 30, cy + 30, cx + 30)
            scores = []
            for p in self.players:
                if p.team != "referee" and p.previous_bb is not None and frame_idx in p.positions:
                    from src.tracking.player_detection import FeetDetector
                    iou = FeetDetector.bb_intersection_over_union(bbox_iou, p.previous_bb)
                    scores.append((p, iou))
            if scores:
                best_p, best_iou = max(scores, key=lambda s: s[1])
                for p in self.players:
                    p.has_ball = False
                # Only assign possession if ball bbox overlaps player bbox (IoU > 0)
                # or ball center is within 80px of player feet — prevents always-assigned
                # possession that blocks shot detection when ball is in the air.
                if best_iou > 0:
                    best_p.has_ball = True
                else:
                    # Fallback: proximity in pixel space
                    px_scores = []
                    for p in self.players:
                        if p.team != "referee" and p.previous_bb is not None and frame_idx in p.positions:
                            pb = p.previous_bb  # (y1, x1, y2, x2)
                            foot_x = (pb[1] + pb[3]) / 2
                            foot_y = pb[2]
                            dist = float(np.hypot(cx - foot_x, cy - foot_y))
                            px_scores.append((p, dist))
                    if px_scores:
                        nearest_p, nearest_dist = min(px_scores, key=lambda s: s[1])
                        if nearest_dist <= 80:
                            nearest_p.has_ball = True

        return frame, map_2d

    def _update_stats(self, frame, yolo_results, player_stats, frame_idx):
        """Feed YOLO results into StatsTracker for shot counting."""
        try:
            import torch
            # Build results tensor for StatsTracker [x1,y1,x2,y2,conf,label]
            rows = [[*det["bbox"], det["confidence"], det["raw_label"]]
                    for det in yolo_results]
            if not rows:
                return
            results_tensor = torch.tensor(rows, dtype=torch.float32)
            # StatsTracker needs re_id object — pass None-safe stub
            self.stats_tracker.track(frame, results_tensor, _ReIdStub(), {})
        except Exception:
            pass  # StatsTracker is best-effort; don't crash pipeline

    # ── export ────────────────────────────────────────────────────────────

    def _make_writer(self, cap):
        if not self.output_video_path:
            return None
        os.makedirs(os.path.dirname(self.output_video_path), exist_ok=True)
        _, f0 = cap.read()
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        if f0 is None:
            return None
        h, w = f0[TOPCUT:].shape[:2]
        return cv2.VideoWriter(
            self.output_video_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            cap.get(cv2.CAP_PROP_FPS) or 25.0,
            (w, h + h // 2),
        )

    @staticmethod
    def _frame_spatial(
        frame_tracks: List[dict],
        ball_pos: Optional[tuple],
        map_w: int,
        map_h: int,
    ) -> dict:
        """
        Compute frame-level spatial metrics grouped by team.

        Returns a dict keyed by team name with sub-dicts:
          spacing, cx, cy, paint_n
        Plus top-level keys _ball_side and _isolation.
        """
        from src.tracking.event_detector import _DRIBBLE_MAX_DIST  # noqa: F401

        by_team: Dict[str, List[tuple]] = {}
        handler_team = None
        handler_pos  = None

        for t in frame_tracks:
            team = t["team"]
            if team == "referee":
                continue
            by_team.setdefault(team, []).append((t["x2d"], t["y2d"]))
            if t.get("has_ball"):
                handler_team = team
                handler_pos  = (t["x2d"], t["y2d"])

        result: dict = {}
        for team, pts in by_team.items():
            arr = np.array(pts, dtype=float)
            cx, cy = arr.mean(axis=0) if len(arr) else (0.0, 0.0)
            spacing = 0.0
            if _SCIPY and len(arr) >= 3:
                try:
                    _px_area = float(_ConvexHull(arr).volume)
                    spacing = _px_area / ((map_w * map_h) / _SPACING_NORM)
                except Exception:
                    pass
            # FIX 9: convex hull area normalised to ft² equivalent (ISSUE-026)
            hull_area = 0.0
            if len(arr) >= 3:
                if _SCIPY:
                    try:
                        _px_area2 = float(_ConvexHull(arr).volume)
                        hull_area = _px_area2 / ((map_w * map_h) / _SPACING_NORM)
                    except Exception:
                        hull_area = 0.0
            paint_n = sum(
                1 for x, y in pts
                if UnifiedPipeline._court_zone(x, y, map_w, map_h) == "paint"
            )
            result[team] = {"spacing": spacing, "cx": cx, "cy": cy, "paint_n": paint_n, "hull_area": hull_area}

        # Ball side
        if ball_pos:
            result["_ball_side"] = "left" if ball_pos[0] < map_w / 2 else "right"
        else:
            result["_ball_side"] = ""

        # Handler isolation — nearest opponent distance, stored in FEET.
        # Default: _ISOLATION_DEFAULT (99 ft, wider than half-court → off-court sentinel)
        # so that frames where opponents are not yet tracked don't falsely register as
        # maximum defensive pressure.  0.0 would mean "defender on handler" — not safe.
        isolation = _ISOLATION_DEFAULT  # ft sentinel
        if handler_pos and handler_team:
            opp_pts = [
                (x, y)
                for team, pts in by_team.items()
                if team != handler_team
                for x, y in pts
            ]
            if opp_pts:
                dists = [float(np.hypot(handler_pos[0] - x, handler_pos[1] - y))
                         for x, y in opp_pts]
                isolation = _px_to_ft(min(dists), map_w)  # convert px→ft
            else:
                # Fallback: only activate when we have strong evidence that team
                # classification merged all players under one label (6+ non-referee
                # players in a single team bucket).  In that case use any non-handler
                # player as a proxy defender so we still get a coverage signal.
                # Do NOT fall back when fewer than 6 players share a label — that
                # just means the opposing team isn't visible yet (→ keep _ISOLATION_DEFAULT).
                all_non_ref = [t for t in frame_tracks if t.get("team") != "referee"]
                if len(by_team) == 1 and len(all_non_ref) >= 6:
                    all_non_handler = [
                        (t["x2d"], t["y2d"])
                        for t in all_non_ref
                        if (t["x2d"], t["y2d"]) != handler_pos
                    ]
                    if all_non_handler:
                        dists = [float(np.hypot(handler_pos[0] - x, handler_pos[1] - y))
                                 for x, y in all_non_handler]
                        isolation = _px_to_ft(min(dists), map_w)  # convert px→ft
        result["_isolation"] = isolation  # ft value (or _ISOLATION_DEFAULT=99 ft sentinel)

        return result

    @staticmethod
    def _court_zone(x: int, y: int, map_w: int, map_h: int,
                    ft_x: Optional[float] = None, ft_y: Optional[float] = None) -> str:
        """Classify 2D court position using NBA-accurate thresholds (feet).

        NBA court constants used:
          Court:        94 ft × 50 ft
          Basket:       x=5.25 ft from baseline (left), x=88.75 ft (right); y=25 ft
          Paint:        12 ft wide, 16 ft long (x: 0–19 ft from baseline; y: 19–31 ft)
          Restricted:   4 ft radius arc under basket
          3pt straight: 23.75 ft from basket centre
          3pt corners:  22 ft from basket (y ≤ 3 ft or y ≥ 47 ft, x ≤ 14 ft from baseline)
          Backcourt:    x > 47 ft from left baseline (past half-court)

        Uses ft_x/ft_y when provided; falls back to normalised → feet conversion.
        Possible return values: restricted_area, paint, mid_range, 3pt_arc, corner_3, backcourt.
        """
        # ── Prefer ft coordinates; derive from pixels when absent ────────────
        if ft_x is None or ft_y is None:
            ft_x = (x / max(map_w, 1)) * 94.0
            ft_y = (y / max(map_h, 1)) * 50.0

        # ── Compute distances from BOTH baskets ──────────────────────────────
        # Left basket: x=5.25, y=25.  Right basket: x=88.75, y=25.
        dist_left  = float(np.hypot(ft_x - 5.25,  ft_y - 25.0))
        dist_right = float(np.hypot(ft_x - 88.75, ft_y - 25.0))
        dist_from_basket = min(dist_left, dist_right)

        # "Nearest-basket half" x-coordinate (distance from the nearer baseline)
        ft_x_h = ft_x if dist_left <= dist_right else (94.0 - ft_x)

        # ── Zone classification (nearest-basket frame) ────────────────────────
        # Restricted area: ≤4 ft from basket
        if dist_from_basket <= 4.0:
            return "restricted_area"

        # Paint: x within 19 ft of nearest baseline AND y within paint width (12 ft)
        # (free-throw line is at 19 ft from baseline; paint extends 19ft from baseline,
        #  centred at y=25: 25±6 = 19 to 31 ft)
        if ft_x_h <= 19.0 and 19.0 <= ft_y <= 31.0:
            return "paint"

        # Corner 3: within 3 ft of sideline (y ≤ 3 or y ≥ 47) AND
        # within 22 ft of nearest basket (corner arc starts at baseline, 22 ft rule)
        if (ft_y <= 3.0 or ft_y >= 47.0) and ft_x_h <= 22.0:
            return "corner_3"

        # Beyond 3pt arc: either a 3pt-arc shot or true backcourt.
        # Backcourt = beyond 23.75 ft from the NEAREST basket (mid-court, no realistic
        # shot attempt from here).  Positions like the centre circle (ft_x≈47) qualify;
        # a corner-3 or straight-away 3pt position does NOT (those are in front-court).
        if dist_from_basket > 23.75:
            # True backcourt: also far from the OTHER basket (centre-court region).
            # Threshold: nearest basket > 30 ft puts us solidly past any 3pt zone.
            if dist_from_basket > 30.0:
                return "backcourt"
            return "3pt_arc"

        # Inside 3pt arc but not paint / restricted → mid-range
        return "mid_range"

    @staticmethod
    def _dist_to_basket(x2d: int, y2d: int, map_w: int, map_h: int) -> float:
        """Euclidean distance to the nearest basket in FEET (converted from pixels)."""
        bl = (_BASKET_L[0] * map_w, _BASKET_L[1] * map_h)
        br = (_BASKET_R[0] * map_w, _BASKET_R[1] * map_h)
        px_dist = min(
            float(np.hypot(x2d - bl[0], y2d - bl[1])),
            float(np.hypot(x2d - br[0], y2d - br[1])),
        )
        return _px_to_ft(px_dist, map_w)

    @staticmethod
    def _vel_toward_basket(
        x2d: int, y2d: int, dx: float, dy: float, map_w: int, map_h: int
    ) -> float:
        """
        Signed projection of the velocity vector onto the direction toward the
        nearest basket.  Positive = moving toward basket, negative = away.
        """
        bl = (_BASKET_L[0] * map_w, _BASKET_L[1] * map_h)
        br = (_BASKET_R[0] * map_w, _BASKET_R[1] * map_h)
        dl = float(np.hypot(x2d - bl[0], y2d - bl[1]))
        dr = float(np.hypot(x2d - br[0], y2d - br[1]))
        bx, by  = bl if dl <= dr else br
        tb_len  = min(dl, dr)
        if tb_len < 1e-6 or (abs(dx) < 1e-6 and abs(dy) < 1e-6):
            return 0.0
        # Unit vector toward basket
        tbx, tby = (bx - x2d) / tb_len, (by - y2d) / tb_len
        return round(float(dx * tbx + dy * tby), 2)

    @staticmethod
    def _fast_break_flag(
        frame_tracks: List[dict],
        prev_pos: Dict[int, tuple],
        map_w: int,
        map_h: int,
        stride: int = 1,
    ) -> int:
        """
        Returns 1 if ≥3 players from the same team are moving toward the same
        basket at ≥ _FAST_BREAK_VEL_MIN px/abs-frame, else 0.
        """
        team_vtb: Dict[str, List[float]] = {}
        for t in frame_tracks:
            if t["team"] == "referee":
                continue
            pxy = prev_pos.get(t["player_id"])
            if not pxy:
                continue
            # Divide by stride so vtb is in px/abs-frame — consistent with threshold.
            dx = float(t["x2d"] - pxy[0]) / stride
            dy = float(t["y2d"] - pxy[1]) / stride
            vtb = UnifiedPipeline._vel_toward_basket(
                t["x2d"], t["y2d"], dx, dy, map_w, map_h
            )
            team_vtb.setdefault(t["team"], []).append(vtb)
        for vals in team_vtb.values():
            if sum(1 for v in vals if v >= _FAST_BREAK_VEL_MIN) >= 3:
                return 1
        return 0

    # ── team name resolution ───────────────────────────────────────────────

    def _resolve_team_names(self, game_id: str, color_labels: list) -> dict:
        """Map HSV color labels ('white','green') to NBA team abbreviations.

        Calls BoxScoreSummaryV2 to get home/visitor abbreviations, then maps
        the two color labels alphabetically: first label → home, second → visitor.
        Caches result to data/nba/team_map_{game_id}.json.

        Falls back to 'team_a'/'team_b' when the API call fails.
        """
        if not game_id or not color_labels:
            return {}
        labels = sorted(set(l for l in color_labels if l))
        if not labels:
            return {}

        # Try cache
        cache_dir = os.path.join(_DATA, "nba")
        cache_path = os.path.join(cache_dir, f"team_map_{game_id}.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as _f:
                    return json.load(_f)
            except Exception:
                pass

        # Build fallback in case API fails
        fallback = {lbl: f"team_{chr(ord('a') + i)}" for i, lbl in enumerate(labels)}

        try:
            import time as _time
            from nba_api.stats.static import teams as _teams_static
            _time.sleep(0.6)
            _id_to_abbr = {t["id"]: t["abbreviation"] for t in _teams_static.get_teams()}
            # Try V3 first (supports 2025-26+), fall back to V2
            try:
                from nba_api.stats.endpoints import boxscoresummaryv3 as _bssv3
                _bs  = _bssv3.BoxScoreSummaryV3(game_id=game_id)
                _df  = _bs.get_data_frames()[0]
                home    = _id_to_abbr.get(int(_df["homeTeamId"].iloc[0]),  "UNK")
                visitor = _id_to_abbr.get(int(_df["awayTeamId"].iloc[0]),  "UNK")
            except Exception:
                from nba_api.stats.endpoints import boxscoresummaryv2 as _bssv2
                _bs  = _bssv2.BoxScoreSummaryV2(game_id=game_id)
                _df  = _bs.get_data_frames()[0]
                home    = _id_to_abbr.get(int(_df["HOME_TEAM_ID"].iloc[0]),    "UNK")
                visitor = _id_to_abbr.get(int(_df["VISITOR_TEAM_ID"].iloc[0]), "UNK")
            # Court-position heuristic: label with lower alphabetical sort →
            # home team (rough proxy — works well enough for cross-game ML).
            mapping: dict = {}
            if len(labels) >= 2:
                mapping[labels[0]] = home
                mapping[labels[1]] = visitor
            elif len(labels) == 1:
                mapping[labels[0]] = home
            # Cache
            os.makedirs(cache_dir, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as _f:
                json.dump(mapping, _f)
            print(f"  [team_names] {mapping}")
            return mapping
        except Exception as _e:
            print(f"  [team_names] NBA API failed ({_e}) — using team_a/team_b fallback")
            return fallback

    # ── possession / shot helpers ──────────────────────────────────────────

    @staticmethod
    def _summarize_possession(
        pid: int,
        team: str,
        start_f: int,
        end_f: int,
        buf: List[dict],
        fps: float,
        game_id: Optional[str] = None,
        lineup_id: int = 0,
        transition_frames: Optional[int] = None,
        offensive_rebound_poss: bool = False,
    ) -> dict:
        """Aggregate a possession buffer into one summary row."""
        if not buf:
            return {}
        dur = max(1, end_f - start_f + 1)
        spacings    = [b["spacing"]   for b in buf if b["spacing"]]
        isolations  = [b["isolation"] for b in buf
                       if b["isolation"] and b["isolation"] != _ISOLATION_DEFAULT]
        vtbs        = [b["vtb"]       for b in buf if b["vtb"] != 0]
        shot_frames = [b["frame"]     for b in buf if b["shot_event"]]

        # Dominant play_type: most common across all frames
        # Prefer the play_cls output; fall back to poss_cls possession_type
        from collections import Counter as _Counter
        play_types = [b["play_type"]  for b in buf if b.get("play_type")]
        poss_types = [b["poss_type"]  for b in buf if b.get("poss_type")]
        if play_types:
            dominant_play_type = _Counter(play_types).most_common(1)[0][0]
        elif poss_types:
            dominant_play_type = _Counter(poss_types).most_common(1)[0][0]
        else:
            dominant_play_type = "half_court"

        # FIX 2: poss_ctx aggregates
        # BUG-A fix: coerce shot_clock_est safely — buf entries may carry "" or None
        # (e.g. from a prior-version checkpoint or a non-standard code path).
        # _to_float converts any non-numeric value to the given default before comparison.
        def _to_float(v, default: float = 24.0) -> float:
            try:
                return float(v) if v not in ("", None) else default
            except (ValueError, TypeError):
                return default

        max_paint_touches = max((b.get("paint_touches", 0) for b in buf), default=0)
        _off_dists = [b.get("off_ball_distance", 0.0) for b in buf if b.get("off_ball_distance", 0.0) > 0]
        avg_off_ball_distance = round(float(sum(_off_dists) / len(_off_dists)), 1) if _off_dists else ""
        # Bug 11/24 fix: scale guard for off_ball_distance — divide by _BUF_PX_TO_FT if
        # buffer max exceeds _BUF_PIXEL_THRESHOLD (indicates pixel-scale values leaked through).
        if _off_dists and max(_off_dists) > _BUF_PIXEL_THRESHOLD:
            avg_off_ball_distance = round(float(sum(_off_dists) / len(_off_dists)) / _BUF_PX_TO_FT, 1)
        min_shot_clock_est = min(
            (_to_float(b.get("shot_clock_est")) for b in buf), default=24.0
        )

        # FIX 2: dominant handler zone (only frames where handler exists)
        _zones = [b["handler_zone"] for b in buf if b.get("handler_zone") is not None]
        dominant_zone = _Counter(_zones).most_common(1)[0][0] if _zones else ""

        # FIX 4: transition time
        transition_time_sec = round(transition_frames / fps, 2) if transition_frames is not None else ""

        # Bug 11/24 fix: scale guard for avg_spacing — divide by _BUF_PX_TO_FT if buffer
        # max exceeds _BUF_PIXEL_THRESHOLD (pixel-scale hull-area values from older games).
        if spacings and max(spacings) > _BUF_PIXEL_THRESHOLD:
            avg_spacing = round(float(np.mean(spacings)) / _BUF_PX_TO_FT, 1)
        else:
            avg_spacing = round(float(np.mean(spacings)), 1) if spacings else ""

        return {
            "possession_id":           pid,
            "team":                    team,
            "start_frame":             start_f,
            "end_frame":               end_f,
            "duration_frames":         dur,
            "duration_sec":            round(dur / fps, 2),
            # BUG4 (c): avg_spacing = mean convex hull area in ft² per frame (same
            # computation as spacing_hull_area in tracking_rows — duplicated here for
            # historical compatibility with downstream consumers that join on possession_id).
            # Unit: ft²  (NOT mean pairwise distance — see spacing_hull_area for definition).
            "avg_spacing":             avg_spacing,
            "avg_defensive_pressure":  round(float(np.mean(isolations)), 1) if isolations else "",
            "avg_vel_toward_basket":   round(float(np.mean(vtbs)),       2) if vtbs       else "",
            "drive_attempts":          sum(1 for b in buf if b.get("drive")),
            "shot_attempted":          int(bool(shot_frames)),
            "shot_frame":              shot_frames[0] if shot_frames else "",
            # R17: strict fast-break definition. Previously `any(b["fast_break"] for b in buf)`
            # OR'd every per-frame _fast_break_flag (3 same-team players pushing toward rim
            # for a momentary frame), flagging 56% of possessions as fast-break vs NBA-typical
            # ~5-9%. New rule: NOT off-rebound + crossed half-court in <2.5s + total
            # possession duration <10s — matches the canonical NBA-Synergy definition.
            "fast_break":              int(
                not offensive_rebound_poss
                and transition_frames is not None
                and transition_frames < int(2.5 * fps)
                and (end_f - start_f) / fps < 10.0
            ),
            "play_type":               dominant_play_type,
            "result":                  "",   # filled by nba_enricher
            "outcome_score":           "",   # filled by nba_enricher
            "game_id":                 game_id,
            "lineup_id":               lineup_id,           # FIX 1
            "max_paint_touches":       max_paint_touches,   # FIX 2
            "avg_off_ball_distance":   avg_off_ball_distance,  # FIX 2
            "min_shot_clock_est":      round(min_shot_clock_est, 1),  # FIX 2
            "dominant_zone":           dominant_zone,        # FIX 2
            "transition_time_sec":     transition_time_sec,  # FIX 4
            "offensive_rebound_poss":  int(offensive_rebound_poss),  # Step 4
        }

    def _export_possessions_csv(self, rows: List[dict], event_counts: dict = None):
        os.makedirs(self._data_dir, exist_ok=True)
        path = os.path.join(self._data_dir, "possessions.csv")
        if not rows:
            # Write header-only CSV so downstream readers don't KeyError on missing file
            _poss_fields = [
                "possession_id", "team", "start_frame", "end_frame",
                "duration_frames", "duration_sec", "shot_attempted", "shot_frame",
                "pass_count", "screen_count", "drive_count", "cut_count", "drive_attempts",
            ]
            with open(path, "w", newline="", encoding="utf-8") as _f:
                import csv as _csv
                _csv.DictWriter(_f, fieldnames=_poss_fields).writeheader()
            return
        os.makedirs(self._data_dir, exist_ok=True)
        path   = os.path.join(self._data_dir, "possessions.csv")
        # Fix 3 Part B: filter sub-1.5s noise possessions before writing.
        # FIX 1: Lowered 3.0s→1.5s since _BALL_LOSS_THRESH now enforces 1.5s
        # minimum at the state-machine level; remaining sub-1.5s rows are
        # edge cases from game-start / clip-end truncation.
        kept    = [r for r in rows if float(r.get("duration_sec") or 0) >= 2.0]
        skipped = len(rows) - len(kept)
        print(f"Possessions: {len(kept)} kept, {skipped} skipped (<2.0s noise)")

        # Fix 3 Part C: merge consecutive same-team possessions with a short gap.
        # Over-fragmentation creates A→A chains where the same team briefly loses
        # and regains the ball (loose ball, same-team rebound, brief OOB).
        # FIX 1: Raised gap 90→150→300 frames (~10s at 30fps/stride-3) to absorb dead-ball gaps.
        _fps_est = next(
            (float(r["duration_frames"]) / float(r["duration_sec"])
             for r in kept
             if float(r.get("duration_sec") or 0) > 0
             and int(r.get("duration_frames") or 0) > 0),
            30.0,
        )
        merged_poss: list = []
        for row in kept:
            if (merged_poss
                    and row.get("team") == merged_poss[-1].get("team")
                    and int(row.get("start_frame") or 0) - int(merged_poss[-1].get("end_frame") or 0) < 300
                    and not merged_poss[-1].get("shot_attempted")):
                prev = merged_poss[-1]
                prev["end_frame"]       = row["end_frame"]
                prev["duration_frames"] = int(prev["end_frame"]) - int(prev["start_frame"])
                prev["duration_sec"]    = round(prev["duration_frames"] / _fps_est, 2)
                if row.get("shot_attempted"):
                    prev["shot_attempted"] = row["shot_attempted"]
                    prev["shot_frame"]     = row.get("shot_frame", "")
                for _k in ("pass_count", "screen_count", "drive_count", "cut_count", "drive_attempts"):
                    prev[_k] = int(prev.get(_k) or 0) + int(row.get(_k) or 0)
            else:
                merged_poss.append(dict(row))
        pre_merge = len(kept)
        kept = merged_poss
        print(f"Possessions: {len(kept)} after same-team merge (was {pre_merge})")
        if len(kept) > 300:
            import logging
            logging.warning(
                f"[ISSUE-039] {len(kept)} possessions after merge — upstream fragmentation "
                f"still present (expected ≤300 per 10-min clip). Check _BALL_LOSS_THRESH "
                f"and _POSS_PERSIST_FRAMES."
            )

        # FIX 2 + FIX 4: merge per-possession event counts (always set; default 0)
        _ec = event_counts or {}
        for row in kept:
            _pid = row.get("possession_id")
            _cnts = _ec.get(_pid, {}) if _pid is not None else {}
            row["pass_count"]   = _cnts.get("pass_count",   row.get("pass_count", 0))
            row["screen_count"] = _cnts.get("screen_count", row.get("screen_count", 0))
            row["drive_count"]  = _cnts.get("drive_count",  row.get("drive_count", 0))
            row["cut_count"]    = _cnts.get("cut_count",    row.get("cut_count", 0))
        fields = [
            "game_id", "possession_id", "team", "start_frame", "end_frame",
            "duration_frames", "duration_sec",
            "avg_spacing", "avg_defensive_pressure", "avg_vel_toward_basket",
            "drive_attempts", "shot_attempted", "shot_frame",
            "fast_break", "play_type", "result", "outcome_score",
            "pass_count", "screen_count", "drive_count", "cut_count",  # FIX 4
            "lineup_id",              # FIX 1
            "max_paint_touches",      # FIX 2
            "avg_off_ball_distance",  # FIX 2
            "min_shot_clock_est",       # FIX 2
            "dominant_zone",            # FIX 2
            "transition_time_sec",      # FIX 4
            "offensive_rebound_poss",   # Step 4
            "is_stub",                  # Bug 26 fix 2026-05-28: pbp_fill enricher-stub flag
        ]
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(kept)
        print(f"Possessions     → {path}  ({len(kept)} rows)")

    def _export_shot_log(self, rows: List[dict], append: bool = False):
        os.makedirs(self._data_dir, exist_ok=True)
        path   = os.path.join(self._data_dir, "shot_log.csv")
        fields = [
            "game_id", "shot_id", "frame", "timestamp", "player_id", "player_name",
            "team", "team_abbrev",  # BUG1 fix: team_abbrev written on every flush (raw color in team)
            "x_position", "y_position", "x_norm", "y_norm", "court_zone",
            "defender_distance", "defender_dist_norm",
            # P5 (2026-05-29): defender identity for A2 defender-quality model.
            # defender_nba_id is empty at write time; _backfill_nba_player_ids
            # fills it post-tracking from PlayerResolver.slot_to_player_id.
            "defender_slot_id", "defender_nba_id",
            "team_spacing",
            "possession_id", "possession_duration", "made",
            "shot_clock", "contest_arm_angle", "closeout_speed", "fatigue_proxy",
            "dribble_count", "ball_shot_arc_angle",  # FIX 2, FIX 8
            "catch_and_shoot", "shot_distance",  # FIX 3
            "second_chance",   # FIX 5
            "shot_creation",   # FIX 8
        ]
        mode = "a" if append and os.path.exists(path) else "w"
        with open(path, mode, newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            if mode == "w":
                w.writeheader()
            w.writerows(rows)
        if not append:
            print(f"Shot log        → {path}  ({len(rows)} shots)")

    def _export_player_stats(self, tracking_rows: List[dict], fps: float):
        """Aggregate per-player stats across the entire clip."""
        # When checkpointing is active, tracking_rows contains only the last batch.
        # Read the already-written tracking_data.csv so all frames are included.
        _csv_path = os.path.join(self._data_dir, "tracking_data.csv")
        if os.path.exists(_csv_path):
            try:
                with open(_csv_path, newline="", encoding="utf-8") as _f:
                    tracking_rows = list(csv.DictReader(_f))
            except Exception:
                pass
        if not tracking_rows:
            return
        from collections import defaultdict
        # P14 2026-05-29: track team_abbrev too (was missing entirely from
        # player_clip_stats schema — caused downstream NBA-tricode joins to fail).
        stats: dict = defaultdict(lambda: {
            "player_id": 0, "team": "", "team_abbrev_counter": defaultdict(int),
            "frames_tracked": 0, "total_distance": 0.0,
            "max_velocity": 0.0, "vel_sum": 0.0,
            "possession_frames": 0,
            "shots_attempted": 0, "drive_attempts": 0,
            "paint_frames": 0,
            "dist_to_basket_sum": 0.0, "opp_dist_sum": 0.0, "opp_dist_n": 0,
        })
        total_frames = max((int(r["frame"]) for r in tracking_rows), default=0) + 1
        for r in tracking_rows:
            pid = r["player_id"]
            s   = stats[pid]
            s["player_id"] = pid
            s["team"]      = r["team"]
            # P14: count team_abbrev across frames so mode wins (handles transient
            # mis-assignments without polluting the per-player aggregate).
            _ta = (r.get("team_abbrev") or "").strip()
            if _ta and _ta not in ("UNK", "nan"):
                s["team_abbrev_counter"][_ta] += 1
            s["frames_tracked"]    += 1
            vel = float(r.get("velocity", 0) or 0)
            s["total_distance"]    += vel
            s["vel_sum"]           += vel
            s["max_velocity"]       = max(s["max_velocity"], vel)
            s["possession_frames"] += int(r.get("ball_possession", 0) or 0)
            s["shots_attempted"]   += int(r.get("event") == "shot")
            s["drive_attempts"]    += int(r.get("drive_flag", 0) or 0)
            s["paint_frames"]      += int(r.get("court_zone") == "paint")
            db = r.get("distance_to_basket")
            if db not in ("", None):
                s["dist_to_basket_sum"] += float(db)
            od = r.get("nearest_opponent")
            if od not in ("", None):
                s["opp_dist_sum"] += float(od)
                s["opp_dist_n"]   += 1

        rows = []
        for pid, s in sorted(stats.items()):
            ft = max(1, s["frames_tracked"])
            # P14: pick the mode team_abbrev across frames (fallback "" if none)
            _ta_mode = ""
            if s["team_abbrev_counter"]:
                _ta_mode = max(s["team_abbrev_counter"], key=s["team_abbrev_counter"].get)
            rows.append({
                "player_id":           pid,
                "team":                s["team"],
                "team_abbrev":         _ta_mode,
                "frames_tracked":      ft,
                "tracking_pct":        round(ft / max(1, total_frames), 3),
                "total_distance_px":   round(s["total_distance"], 1),
                "avg_velocity":        round(s["vel_sum"] / ft, 2),
                "max_velocity":        round(s["max_velocity"], 2),
                "possession_frames":   s["possession_frames"],
                "possession_pct":      round(s["possession_frames"] / ft, 3),
                "shots_attempted":     s["shots_attempted"],
                "drive_attempts":      s["drive_attempts"],
                "drive_rate":          round(s["drive_attempts"] / ft, 4),
                "paint_frames":        s["paint_frames"],
                "paint_pct":           round(s["paint_frames"] / ft, 3),
                "avg_dist_to_basket":  round(s["dist_to_basket_sum"] / ft, 1),
                "avg_nearest_opponent": round(s["opp_dist_sum"] / max(1, s["opp_dist_n"]), 1),
            })

        os.makedirs(self._data_dir, exist_ok=True)
        path = os.path.join(self._data_dir, "player_clip_stats.csv")
        fields = list(rows[0].keys()) if rows else []
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"Player stats    → {path}  ({len(rows)} players)")

    def _pg_write_tracking_rows(self, rows: List[dict]) -> None:
        """
        Write tracking rows to the tracking_frames PostgreSQL table.

        Logs WARN and returns early if DATABASE_URL is not set (PostgreSQL-only table;
        SQLite does not have tracking_frames).
        Works with or without game_id — when game_id is absent the column is
        NULL (requires migration 001_tracking_nullable_game_id.sql applied first).
        Uses INSERT ... ON CONFLICT DO NOTHING so re-runs are safe.

        Args:
            rows: List of tracking row dicts (same as CSV output).
        """
        if not rows:
            return
        if not os.environ.get("DATABASE_URL"):
            log.warning(
                "[db] DATABASE_URL unset — skipping PostgreSQL tracking_frames write "
                "(%d rows). Set DATABASE_URL to enable.", len(rows)
            )
            return
        game_id = self.game_id or None   # NULL when --game-id not passed
        if game_id is None:
            print("[db] No game_id — rows written with NULL game_id "
                  "(pass --game-id to link to a game record)")
        try:
            from src.data.db import get_connection, execute_batch, is_postgres
            conn = get_connection()
            cur  = conn.cursor()
            insert_sql = """
                INSERT INTO tracking_frames (
                    game_id, clip_id, frame_number, timestamp_sec,
                    tracker_player_id, x_pos, y_pos,
                    speed, acceleration, ball_possession,
                    event, confidence, team_spacing,
                    paint_count_own, paint_count_opp, tracker_version
                ) VALUES (
                    %(game_id)s, %(clip_id)s::uuid, %(frame_number)s, %(timestamp_sec)s,
                    %(tracker_player_id)s, %(x_pos)s, %(y_pos)s,
                    %(speed)s, %(acceleration)s, %(ball_possession)s,
                    %(event)s, %(confidence)s, %(team_spacing)s,
                    %(paint_count_own)s, %(paint_count_opp)s, %(tracker_version)s
                )
                ON CONFLICT DO NOTHING
            """
            db_rows = [
                {
                    "game_id":           game_id,
                    "clip_id":           self.clip_id,
                    "frame_number":      r.get("frame"),
                    "timestamp_sec":     r.get("timestamp"),
                    "tracker_player_id": r.get("player_id"),
                    "x_pos":             r.get("x_position"),
                    "y_pos":             r.get("y_position"),
                    "speed":             r.get("velocity"),
                    "acceleration":      r.get("acceleration"),
                    "ball_possession":   r.get("ball_possession"),
                    "event":             r.get("event"),
                    "confidence":        r.get("confidence"),
                    "team_spacing":      r.get("team_spacing"),
                    "paint_count_own":   r.get("paint_count_own"),
                    "paint_count_opp":   r.get("paint_count_opp"),
                    "tracker_version":   "v1",
                }
                for r in rows
            ]
            backend = "PostgreSQL" if is_postgres(conn) else "SQLite"
            execute_batch(cur, insert_sql, db_rows, page_size=500)
            conn.commit()
            cur.close()
            conn.close()
            print(f"[db] tracking_frames ← {len(db_rows)} rows "
                  f"({backend}, game_id={game_id}, clip_id={self.clip_id[:8]}…)")
        except Exception as e:
            print(f"[db] WARNING: database write failed — {e}")

    def _db_write_shot_log(self, rows: List[dict]) -> None:
        """Write shot_log rows to the shots DB table (SQLite or PostgreSQL)."""
        if not rows:
            return
        try:
            from src.data.db import get_connection, execute_batch, is_postgres
            conn = get_connection()
            sql  = """
                INSERT OR IGNORE INTO shots
                    (game_id, possession_id, player_id, tracker_player_id,
                     shot_x, shot_y, court_zone, defender_distance,
                     team_spacing, made, period)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            db_rows = [
                (
                    r.get("game_id") or None,
                    r.get("possession_id") or None,
                    r.get("player_id"),
                    r.get("player_id"),
                    r.get("x_position"),
                    r.get("y_position"),
                    r.get("court_zone"),
                    r.get("defender_distance") or None,
                    r.get("team_spacing") or None,
                    r.get("made") if r.get("made") not in ("", None) else None,
                    self.period,
                )
                for r in rows
            ]
            backend = "PostgreSQL" if is_postgres(conn) else "SQLite"
            with conn:
                with conn.cursor() as cur:
                    execute_batch(cur, sql, db_rows)
            conn.close()
            print(f"[db] shots ← {len(db_rows)} rows ({backend})")
        except Exception as exc:
            print(f"[db] shot_log write failed (non-fatal): {exc}")

    def _db_write_scoreboard_log(self, rows: List[dict]) -> None:
        """Write scoreboard_log rows to DB."""
        if not rows:
            return
        try:
            from src.data.db import get_connection, execute_batch
            conn = get_connection()
            sql  = """
                INSERT OR IGNORE INTO scoreboard_log
                    (game_id, frame, game_clock, shot_clock,
                     home_score, away_score, period, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            db_rows = [
                (
                    self.game_id or None,
                    r["frame"],
                    r.get("game_clock") or None,
                    r.get("shot_clock") or None,
                    r.get("home_score") or None,
                    r.get("away_score") or None,
                    r.get("period") or None,
                    r.get("confidence"),
                )
                for r in rows
            ]
            with conn:
                with conn.cursor() as cur:
                    execute_batch(cur, sql, db_rows)
            conn.close()
        except Exception as exc:
            print(f"[db] scoreboard_log write failed (non-fatal): {exc}")

    def _checkpoint_writer_loop(self) -> None:
        """Task 4: Background daemon — drain _ckpt_queue and write CSV rows."""
        while True:
            rows = self._ckpt_queue.get()
            if rows is None:  # sentinel — shut down
                break
            self._checkpoint_csv(rows)

    def _flush_queue(self) -> None:
        """Task 4: Block until all pending async checkpoint writes have finished."""
        self._ckpt_queue.put(None)        # sentinel to stop writer thread
        self._ckpt_thread.join(timeout=30)

    def _checkpoint_csv(self, rows: List[dict]) -> None:
        """Flush rows to CSV mid-run so a crash doesn't lose all data.

        Writes to self._data_dir/tracking_data.csv — the per-game directory
        when data_dir was passed (Fix 2), otherwise data/tracking_data.csv.

        The first checkpoint of each run overwrites the file (mode="w") so
        re-running a game never appends new-format rows to an old-format file.
        Subsequent checkpoints within the same run append (mode="a").
        """
        if not rows:
            return
        data_dir = getattr(self, "_data_dir", _DATA)
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, "tracking_data.csv")
        # First checkpoint of this run: overwrite so old data is not mixed in
        first = getattr(self, "_ckpt_first_write", True)
        mode = "w" if first else "a"
        self._ckpt_first_write = False
        fields = self._tracking_csv_fields()
        with open(path, mode, newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader() if first else None
            w.writerows(rows)
        print(f"\n[checkpoint] flushed {len(rows)} rows → {path}")

    @staticmethod
    def _tracking_csv_fields() -> List[str]:
        return [
            "frame", "timestamp", "player_id", "team",
            "x_position", "y_position", "x_norm", "y_norm",
            "velocity", "acceleration", "direction_deg",
            "court_zone",
            "ball_possession", "distance_to_ball",
            "nearest_opponent", "nearest_teammate",
            "event",
            "team_spacing", "spacing_hull_area", "team_centroid_x", "team_centroid_y",  # FIX 9
            "paint_count_own", "paint_count_opp",
            "possession_side", "handler_isolation",
            "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
            "ball_x2d", "ball_y2d", "ball_velocity",
            "distance_to_basket", "vel_toward_basket",
            "drive_flag",
            "ft_x", "ft_y", "dist_to_basket_ft",
            "fast_break_flag",
            "possession_id", "possession_duration",
            "confidence",
            "play_type", "paint_touches", "off_ball_distance", "shot_clock_est",
            "scoreboard_shot_clock", "scoreboard_game_clock",
            "scoreboard_period", "scoreboard_score_diff",
            "scoreboard_confidence",  # FIX 6
            "possession_duration_sec", "possession_type",
            "ankle_x", "ankle_y", "contest_arm_angle", "jump_detected", "dribble_hand",
            "ball_shot_arc_angle", "ball_peak_height_px", "ball_pass_speed_pxpf",
            "player_name", "jersey_number",  # FIX 7: included so backfill can overwrite
            "team_abbrev",  # FIX 7: populated by _backfill_team_abbrev post-run
            "dribble_count",  # FIX 2
            "lineup_id",  # FIX 1
            "homography_valid",  # FIX 1 replay/cut detector
        ]

    def _run_enrichment(self, fps: float) -> None:
        """Call nba_enricher.enrich() to label shots/possessions from NBA API PBP."""
        try:
            from src.data.nba_enricher import enrich as _nba_enrich, _infer_period_count, _infer_fps
            periods, _max_ts = _infer_period_count(self._data_dir)
            clip_fps = _infer_fps(self._data_dir, default=fps)
            if len(periods) > 1:
                print(f"\nEnriching shots with NBA API  (game_id={self.game_id}, periods={periods}, fps={clip_fps:.2f})")
                result = _nba_enrich(
                    game_id        = self.game_id,
                    periods        = periods,
                    clip_start_sec = 0.0,
                    fps            = clip_fps,
                    data_dir       = self._data_dir,
                )
            else:
                print(f"\nEnriching shots with NBA API  (game_id={self.game_id}, period={periods[0]}, fps={clip_fps:.2f})")
                result = _nba_enrich(
                    game_id        = self.game_id,
                    period         = periods[0],
                    clip_start_sec = self.clip_start_sec,
                    fps            = clip_fps,
                    data_dir       = self._data_dir,
                )
            if result:
                for label, path in result.items():
                    print(f"  ✓ {label}: {path}")
        except Exception as exc:
            print(f"  [enrichment] failed (non-fatal): {exc}")

    def _export_csv(self, rows: List[dict]):
        """Write any remaining rows not yet flushed by _checkpoint_csv."""
        if not rows:
            return
        self._checkpoint_csv(rows)
        self._pg_write_tracking_rows(rows)
        print(f"Tracking data → data/tracking_data.csv  (clip_id={self.clip_id})")

    def _export_ball_csv(self, rows: List[dict], append: bool = False):
        os.makedirs(self._data_dir, exist_ok=True)
        path   = os.path.join(self._data_dir, "ball_tracking.csv")
        fields = ["frame", "timestamp", "ball_x2d", "ball_y2d", "detected", "live", "ball_inferred"]
        if not rows:
            # Write header-only CSV so downstream readers don't KeyError on missing file
            if not (append and os.path.exists(path)):
                with open(path, "w", newline="", encoding="utf-8") as _f:
                    csv.DictWriter(_f, fieldnames=fields).writeheader()
            return
        mode = "a" if append and os.path.exists(path) else "w"
        with open(path, mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            if mode == "w":
                w.writeheader()
            w.writerows(rows)
        if not append:
            print(f"Ball tracking  → {path}  ({len(rows)} rows)")

    def _export_stats(self, player_stats):
        if not player_stats:
            return
        os.makedirs(self._data_dir, exist_ok=True)
        path = os.path.join(self._data_dir, "stats.json")
        with open(path, "w") as f:
            json.dump(player_stats, f, indent=2)
        print(f"Player stats → {path}")

    def _export_scoreboard_log(self, rows: List[dict], append: bool = False):
        if not rows:
            return
        os.makedirs(self._data_dir, exist_ok=True)
        path   = os.path.join(self._data_dir, "scoreboard_log.csv")
        fields = ["frame", "game_clock", "shot_clock", "home_score", "away_score",
                  "period", "confidence"]
        mode = "a" if append and os.path.exists(path) else "w"
        with open(path, mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            if mode == "w":
                w.writeheader()
            w.writerows(rows)
        if not append:
            print(f"Scoreboard log → {path}  ({len(rows)} readings, "
                  f"period_start_video_sec={self.period_start_video_sec:.1f}s)")

    # ── FIX 1: events log export ──────────────────────────────────────────

    def _export_events_log(self, rows: List[dict], append: bool = False) -> None:
        """Write events_log.csv — all rich events (screen/cut/drive/closeout/rebound)."""
        os.makedirs(self._data_dir, exist_ok=True)
        path = os.path.join(self._data_dir, "events_log.csv")
        fields = [
            "game_id", "frame", "timestamp", "possession_id",
            "type", "player_id", "defender_id",
            "x", "y", "start_x", "end_x",
            "closeout_speed", "crash_angle", "crash_speed", "box_out",
            "ball_handler_id", "screener_id", "screen_action",  # FIX 6
            "handler_id", "rotation_dist",  # FIX 7
        ]
        mode = "a" if append and os.path.exists(path) else "w"
        with open(path, mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            if mode == "w":
                w.writeheader()
            w.writerows(rows)
        if not append:
            print(f"Events log      → {path}  ({len(rows)} events)")

    # ── FIX 5: court-side team map ────────────────────────────────────────

    def _court_side_team_map(self, frame_tracks_buf: list, game_id: str) -> dict:
        """Map team color labels to NBA abbreviations using court-side position.

        Computes mean x2d per team over the first 300 tracked frames.
        The team with lower mean x2d is on the left (home team in Q1 per NBA convention).
        Falls back to alphabetical sort when API fails or game_id is None.

        Returns {} when no color labels are found.
        """
        if not game_id or not frame_tracks_buf:
            return {}

        # Collect mean x2d per color label
        from collections import defaultdict as _dd
        _team_xs: dict = _dd(list)
        for _fts in frame_tracks_buf:
            for _t in _fts:
                _lbl = _t.get("team", "")
                if _lbl and _lbl != "referee":
                    _x = _t.get("x2d")
                    if _x is not None:  # accept 0 — valid left-edge court position
                        _team_xs[_lbl].append(float(_x))

        labels = sorted(_team_xs.keys())
        if not labels:
            return {}

        # Alphabetical fallback (same as _resolve_team_names)
        fallback = {lbl: f"team_{chr(ord('a') + i)}" for i, lbl in enumerate(labels)}

        try:
            import time as _time
            from nba_api.stats.static import teams as _teams_static
            _time.sleep(0.3)
            _id_to_abbr = {t["id"]: t["abbreviation"] for t in _teams_static.get_teams()}
            # Try V3 first (supports 2025-26+), fall back to V2
            try:
                from nba_api.stats.endpoints import boxscoresummaryv3 as _bssv3
                _bs  = _bssv3.BoxScoreSummaryV3(game_id=game_id)
                _df  = _bs.get_data_frames()[0]
                home    = _id_to_abbr.get(int(_df["homeTeamId"].iloc[0]),  "UNK")
                visitor = _id_to_abbr.get(int(_df["awayTeamId"].iloc[0]),  "UNK")
            except Exception:
                from nba_api.stats.endpoints import boxscoresummaryv2 as _bssv2
                _bs  = _bssv2.BoxScoreSummaryV2(game_id=game_id)
                _df  = _bs.get_data_frames()[0]
                home    = _id_to_abbr.get(int(_df["HOME_TEAM_ID"].iloc[0]),    "UNK")
                visitor = _id_to_abbr.get(int(_df["VISITOR_TEAM_ID"].iloc[0]), "UNK")
        except Exception as _e:
            print(f"  [court_side] API failed ({_e}) — using alphabetical fallback")
            return fallback

        # Position-based mapping: lower mean x2d → left half = home team in Q1
        if len(labels) >= 2:
            _means = {lbl: (sum(_team_xs[lbl]) / len(_team_xs[lbl])) for lbl in labels if _team_xs[lbl]}
            _sorted_by_x = sorted(_means.keys(), key=lambda l: _means.get(l, 0))
            # NBA convention: home team attacks right basket in Q1 → home in left half (lower x)
            mapping = {_sorted_by_x[0]: home, _sorted_by_x[1]: visitor}
        elif len(labels) == 1:
            mapping = {labels[0]: home}
        else:
            return fallback

        # Cache to disk (same file as _resolve_team_names so both paths share cache)
        try:
            _cache_dir  = os.path.join(_DATA, "nba")
            _cache_path = os.path.join(_cache_dir, f"team_map_{game_id}.json")
            os.makedirs(_cache_dir, exist_ok=True)
            with open(_cache_path, "w", encoding="utf-8") as _f:
                json.dump(mapping, _f)
        except Exception:
            pass

        print(f"  [court_side] {mapping}")
        return mapping

    # ── FIX 7: player name backfill ───────────────────────────────────────

    def _backfill_player_names(self) -> None:
        """Overwrite empty player_name cells in tracking_data.csv and shot_log.csv.

        Primary source: PlayerResolver.slot_to_player_name (slot → name via NBA API).
        Fallback: jersey_name_map.json (jersey_number → name, fetched by _nba_ground_truth.py).
        """
        if self._player_resolver is None:
            return
        _name_map = self._player_resolver.slot_to_player_name

        # Load jersey_name_map.json as fallback: {"jersey_str": "Player Name"}
        _jersey_map: dict = {}
        _jersey_map_path = os.path.join(self._data_dir, "jersey_name_map.json")
        if os.path.exists(_jersey_map_path):
            try:
                with open(_jersey_map_path, encoding="utf-8") as _jf:
                    _jersey_map = json.load(_jf)
            except Exception as _je:
                print(f"  [backfill_names] jersey_name_map.json load failed: {_je}")

        if not _name_map and not _jersey_map:
            return

        for _fname in ("tracking_data.csv", "shot_log.csv"):
            _path = os.path.join(self._data_dir, _fname)
            if not os.path.exists(_path):
                continue
            try:
                with open(_path, newline="", encoding="utf-8") as _f:
                    reader = csv.DictReader(_f)
                    if "player_name" not in (reader.fieldnames or []):
                        continue
                    _rows = list(reader)
                    _fields = list(reader.fieldnames)
                _updated = 0
                for _row in _rows:
                    _cur_name = _row.get("player_name", "")
                    if _cur_name == "" or "#?" in _cur_name:
                        # Primary: slot → name via player resolver
                        _pid_raw = _row.get("player_id", "")
                        _name = ""
                        try:
                            _pid = int(_pid_raw)
                            _name = _name_map.get(_pid, "")
                        except (ValueError, TypeError):
                            pass
                        # Fallback: jersey_number → name via jersey_name_map.json
                        if not _name and _jersey_map:
                            _jersey_raw = str(_row.get("jersey_number", "")).strip()
                            if _jersey_raw and _jersey_raw != "nan":
                                _name = _jersey_map.get(_jersey_raw, "")
                        if _name:
                            _row["player_name"] = _name
                            _updated += 1
                with open(_path, "w", newline="", encoding="utf-8") as _f:
                    w = csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(_rows)
                print(f"Player name backfill: {_updated} rows updated in {_fname}")
            except Exception as _e:
                print(f"  [backfill_names] {_fname} failed: {_e}")


    def _backfill_shot_log_pose_features(self) -> None:
        """P6 (2026-05-29): widen contest_arm_angle + dribble_count lookup.

        The shot-time write at line ~2566 reads pose data at the EXACT shot frame
        via `_shot_defender_contest` and EventDetector's instantaneous dribble
        counter. Per-frame measurement shows the signal IS present 34.5% of the
        time in tracking_data.csv, but the point lookup captures only 3.7% in
        shot_log.csv. Bug 35 family.

        Window scan (post-tracking, after tracking_data.csv is finalized):
          - contest_arm_angle: max across defender rows within 8 ft of shooter
            in [shot_frame - 45, shot_frame + 5] (1.5s before through release)
          - dribble_count: distinct frames where shooter has dribble_hand
            populated in [shot_frame - 60, shot_frame] (2s before — typical
            pre-shot dribble burst)

        Only overwrites cells that were 0/empty — preserves any nonzero values
        the in-loop write already produced.
        """
        shot_path = os.path.join(self._data_dir, "shot_log.csv")
        tracking_path = os.path.join(self._data_dir, "tracking_data.csv")
        if not os.path.exists(shot_path) or not os.path.exists(tracking_path):
            return

        try:
            from scripts.backfill_shot_log_pose_features import backfill_game  # type: ignore
        except Exception as _imp_exc:
            print(f"  [backfill_pose] import failed (non-fatal): {_imp_exc}")
            return

        try:
            s, cf, _cz, df, _dz = backfill_game(self._data_dir, dry_run=False)
            if s > 0:
                cam_pct = (cf / s * 100) if s else 0
                dc_pct = (df / s * 100) if s else 0
                print(
                    f"pose-features backfill: {cf}/{s} ({cam_pct:.0f}%) contest_arm_angle "
                    f"| {df}/{s} ({dc_pct:.0f}%) dribble_count"
                )
        except Exception as _e:
            print(f"  [backfill_pose] failed: {_e}")


    def _backfill_scoreboard_period(self) -> None:
        """P4 (2026-05-29): fill empty `scoreboard_period` cells in tracking_data.csv.

        The scoreboard OCR (`src/tracking/scoreboard_ocr.py`) attempts to parse
        Q1-Q4 / OT, but on most broadcasts the period text is small/low-contrast
        and the OCR returns -1 → write site at unified_pipeline.py:2718 emits "".
        Result: `scoreboard_period` is ~100% empty in tracking_data.csv across
        production games.

        This post-tracking pass fills the gap using a frame-percentile fallback:
          quarter = max(1, min(4, int(frame / max_frame * 4) + 1))

        OT (5+) is collapsed to Q4 — most callers don't distinguish. When ANY
        OCR-confirmed period values exist, they're preserved (we only write into
        empty cells). The intelligence-layer's quarter-aware aggregators
        (INT-65 fatigue, INT-70 F1 Q1 extrapolation) only need approximate
        Q1/Q2/Q3/Q4 assignment, not OCR precision.
        """
        path = os.path.join(self._data_dir, "tracking_data.csv")
        if not os.path.exists(path):
            return
        try:
            with open(path, newline="", encoding="utf-8") as _f:
                reader = csv.DictReader(_f)
                _fields = list(reader.fieldnames or [])
                if "scoreboard_period" not in _fields or "frame" not in _fields:
                    return
                _rows = list(reader)
            if not _rows:
                return

            # Find max frame
            max_frame = 1
            for _row in _rows:
                try:
                    f_val = _row.get("frame", "")
                    if f_val and f_val not in ("nan", ""):
                        f_int = int(float(f_val))
                        if f_int > max_frame:
                            max_frame = f_int
                except (ValueError, TypeError):
                    pass

            _filled = 0
            _preserved = 0
            for _row in _rows:
                cur = _row.get("scoreboard_period", "")
                if cur not in ("", None, "nan"):
                    _preserved += 1
                    continue
                try:
                    f_int = int(float(_row.get("frame", "") or 0))
                    q = max(1, min(4, int(f_int / max_frame * 4) + 1))
                    _row["scoreboard_period"] = str(q)
                    _filled += 1
                except (ValueError, TypeError):
                    pass

            with open(path, "w", newline="", encoding="utf-8") as _f:
                w = csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(_rows)
            print(
                f"scoreboard_period backfill: filled {_filled} "
                f"(preserved {_preserved} OCR values) in tracking_data.csv"
            )
        except Exception as _e:
            print(f"  [backfill_period] failed: {_e}")


    def _backfill_nba_player_ids(self) -> None:
        """Write `nba_player_id` column into shot_log.csv and shot_log_enriched.csv.

        Source: `PlayerResolver.slot_to_player_id` (built during resolver finalize()).
        For each shot row, look up the tracker slot (`player_id` column, 1-10) in
        the resolver's slot map and emit the resolved NBA player_id. Empty when
        the slot didn't resolve — downstream callers can fall back to the offline
        backfill script `scripts/backfill_shot_log_nba_ids.py` which has 3-channel
        resolution (PBP / jersey / suffix) for richer recovery.
        """
        if self._player_resolver is None:
            return
        _slot_map = getattr(self._player_resolver, "slot_to_player_id", None) or {}
        if not _slot_map:
            return

        for _fname in ("shot_log.csv", "shot_log_enriched.csv"):
            _path = os.path.join(self._data_dir, _fname)
            if not os.path.exists(_path):
                continue
            try:
                with open(_path, newline="", encoding="utf-8") as _f:
                    reader = csv.DictReader(_f)
                    _fields = list(reader.fieldnames or [])
                    if "player_id" not in _fields:
                        continue
                    _rows = list(reader)
                if not _rows:
                    continue
                if "nba_player_id" not in _fields:
                    # Insert right after player_id for readability
                    _fields.insert(_fields.index("player_id") + 1, "nba_player_id")
                # P5 (2026-05-29): also resolve defender slot → defender_nba_id
                # using the same slot_to_player_id map so the A2 defender-quality
                # model has training data on existing/new shot rows.
                _has_def_slot = "defender_slot_id" in _fields
                if _has_def_slot and "defender_nba_id" not in _fields:
                    _fields.insert(_fields.index("defender_slot_id") + 1, "defender_nba_id")
                _resolved = 0
                _resolved_def = 0
                _def_total = 0
                for _row in _rows:
                    try:
                        _slot = int(float(_row.get("player_id", "") or 0))
                    except (ValueError, TypeError):
                        _slot = 0
                    _nba = _slot_map.get(_slot, "")
                    _row["nba_player_id"] = str(_nba) if _nba else ""
                    if _nba:
                        _resolved += 1
                    if _has_def_slot:
                        _def_raw = _row.get("defender_slot_id", "")
                        if _def_raw not in ("", None):
                            try:
                                _def_slot = int(float(_def_raw))
                            except (ValueError, TypeError):
                                _def_slot = 0
                            _def_total += 1
                            _def_nba = _slot_map.get(_def_slot, "")
                            _row["defender_nba_id"] = str(_def_nba) if _def_nba else ""
                            if _def_nba:
                                _resolved_def += 1
                        else:
                            _row["defender_nba_id"] = ""
                with open(_path, "w", newline="", encoding="utf-8") as _f:
                    w = csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(_rows)
                _pct = (_resolved / len(_rows) * 100) if _rows else 0
                msg = f"nba_player_id backfill: {_resolved}/{len(_rows)} ({_pct:.0f}%) in {_fname}"
                if _has_def_slot and _def_total > 0:
                    _def_pct = (_resolved_def / _def_total * 100)
                    msg += f" | defender_nba_id: {_resolved_def}/{_def_total} ({_def_pct:.0f}%)"
                print(msg)
            except Exception as _e:
                print(f"  [backfill_nba_ids] {_fname} failed: {_e}")


    def _backfill_team_abbrev(self, color_map: dict) -> None:
        """FIX 7: Add team_abbrev column to tracking_data.csv using color→abbrev map.

        Fix 5: after the color→abbrev pass, do a second pass: for any row where
        team_abbrev is still blank or 'UNK', propagate the most common non-blank
        abbreviation for the same player_id (slot) via forward-fill then back-fill.
        """
        if not color_map:
            return
        _path = os.path.join(self._data_dir, "tracking_data.csv")
        if not os.path.exists(_path):
            return
        try:
            with open(_path, newline="", encoding="utf-8") as _f:
                reader = csv.DictReader(_f)
                _fields = list(reader.fieldnames or [])
                _rows   = list(reader)
            if "team_abbrev" not in _fields:
                _fields.append("team_abbrev")
            # Pass 1: color → abbrev
            for _row in _rows:
                _color = _row.get("team", "")
                _abbrev = color_map.get(_color, "")
                _row["team_abbrev"] = _abbrev

            # Pass 2: forward-fill then back-fill blanks/UNK within each player_id slot
            # Build slot → list of (index, abbrev)
            from collections import defaultdict as _dd2
            slot_rows: dict = _dd2(list)
            for _i, _row in enumerate(_rows):
                slot_rows[_row.get("player_id", "")].append(_i)

            for _slot, _idxs in slot_rows.items():
                # Find the mode non-UNK abbreviation for this slot
                abbrevs = [
                    _rows[i]["team_abbrev"]
                    for i in _idxs
                    if _rows[i].get("team_abbrev", "") not in ("", "UNK")
                ]
                if not abbrevs:
                    continue
                from collections import Counter as _Counter2
                mode_abbrev = _Counter2(abbrevs).most_common(1)[0][0]
                # Forward fill: propagate mode to blank/UNK rows after first occurrence
                last_good = ""
                for _i in _idxs:
                    cur = _rows[_i].get("team_abbrev", "")
                    if cur not in ("", "UNK"):
                        last_good = cur
                    elif last_good:
                        _rows[_i]["team_abbrev"] = last_good
                # Backward fill: fill any remaining blanks at the start of the slot
                last_good = ""
                for _i in reversed(_idxs):
                    cur = _rows[_i].get("team_abbrev", "")
                    if cur not in ("", "UNK"):
                        last_good = cur
                    elif last_good:
                        _rows[_i]["team_abbrev"] = last_good
                    elif not cur or cur == "UNK":
                        _rows[_i]["team_abbrev"] = mode_abbrev

            # Pass 3: cross-slot fill by player_name — handles re-IDed tracks where a
            # new slot (new player_id) starts with team="" even though an earlier slot
            # for the same named player already has team_abbrev resolved.
            _pname_abbrev: dict = {}
            for _r in _rows:
                _pn = str(_r.get("player_name", "") or "").strip()
                if _pn and _r.get("team_abbrev", "") not in ("", "UNK"):
                    _pname_abbrev[_pn] = _r["team_abbrev"]
            for _r in _rows:
                if _r.get("team_abbrev", "") in ("", "UNK"):
                    _pn = str(_r.get("player_name", "") or "").strip()
                    if _pn and _pn in _pname_abbrev:
                        _r["team_abbrev"] = _pname_abbrev[_pn]

            with open(_path, "w", newline="", encoding="utf-8") as _f:
                w = csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(_rows)
            unk_after = sum(1 for r in _rows if r.get("team_abbrev", "") in ("", "UNK"))
            print(f"  [team_abbrev] backfilled {len(_rows)} rows; {unk_after} UNK remaining")
        except Exception as _e:
            print(f"  [team_abbrev] backfill failed: {_e}")

    def _backfill_possessions_team_abbrev(self, color_map: dict) -> None:
        """P15 2026-05-29: rewrite possessions.csv team column to canonical abbrev.

        Possessions row dict (`_summarize_possession`) carries the raw color
        label in `team`. Without rewrite, downstream NBA-tricode joins fail
        (~90% of rows had unresolvable team_abbrev).

        Also inserts a `team_abbrev` column for explicit join key when callers
        want to preserve the color label semantics separately.
        """
        if not color_map:
            return
        _path = os.path.join(self._data_dir, "possessions.csv")
        if not os.path.exists(_path):
            return
        try:
            with open(_path, newline="", encoding="utf-8") as _f:
                reader = csv.DictReader(_f)
                _fields = list(reader.fieldnames or [])
                _rows = list(reader)
            if not _rows:
                return
            if "team_abbrev" not in _fields:
                _ti = _fields.index("team") + 1 if "team" in _fields else len(_fields)
                _fields.insert(_ti, "team_abbrev")
            # P15 v2 (2026-05-29): possessions.csv `team` value may ALREADY be
            # the NBA abbrev by the time this runs (the row dict at write-time
            # uses `team` = current handler's team string, which is the abbrev).
            # Two paths:
            #   (a) team is in color_map keys ("green"/"white") → translate to abbrev
            #   (b) team is already a 2-3 letter abbrev → copy to team_abbrev as-is
            _resolved = 0
            _color_keys = set(color_map.keys())
            _abbrev_vals = set(color_map.values())
            for _row in _rows:
                _team = (_row.get("team") or "").strip()
                _abbrev = ""
                if _team in _color_keys:
                    _abbrev = color_map[_team]
                elif _team in _abbrev_vals or (2 <= len(_team) <= 3 and _team.isupper()):
                    _abbrev = _team
                if _abbrev:
                    _row["team"] = _abbrev          # canonical abbrev in team col
                    _row["team_abbrev"] = _abbrev   # explicit join key
                    _resolved += 1
                elif not _row.get("team_abbrev"):
                    _row["team_abbrev"] = ""
            _tmp = _path + ".tmp"
            with open(_tmp, "w", newline="", encoding="utf-8") as _f:
                w = csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(_rows)
            os.replace(_tmp, _path)
            print(f"  [possessions team_abbrev] rewrote {len(_rows)} rows; {_resolved} resolved")
        except Exception as _e:
            print(f"  [possessions team_abbrev] rewrite failed: {_e}")


    def _backfill_shot_log_team_abbrev(self, color_map: dict) -> None:
        """BUG1 fix: Post-run disk rewrite of shot_log.csv team_abbrev + team columns.

        Mid-loop flushes write raw HSV color labels ('green'/'white') to the `team`
        column and empty string to `team_abbrev`.  This method reads the on-disk CSV,
        applies the resolved color→abbrev map to BOTH columns, and writes back
        atomically.  Called after _backfill_team_abbrev() so the same resolved map
        (ct_map or team_map) is used consistently.
        """
        if not color_map:
            return
        _path = os.path.join(self._data_dir, "shot_log.csv")
        if not os.path.exists(_path):
            return
        try:
            with open(_path, newline="", encoding="utf-8") as _f:
                reader = csv.DictReader(_f)
                _fields = list(reader.fieldnames or [])
                _rows   = list(reader)
            # Ensure team_abbrev column exists in header
            if "team_abbrev" not in _fields:
                # Insert after 'team' if present, else append
                _ti = _fields.index("team") + 1 if "team" in _fields else len(_fields)
                _fields.insert(_ti, "team_abbrev")
            # Apply map: rewrite team (raw color → abbrev) and team_abbrev
            _resolved = 0
            for _row in _rows:
                _color = _row.get("team", "")
                _abbrev = color_map.get(_color, "")
                if _abbrev:
                    _row["team"] = _abbrev          # fix legacy 'team' column
                    _row["team_abbrev"] = _abbrev   # also populate new column
                    _resolved += 1
                elif not _row.get("team_abbrev"):
                    _row["team_abbrev"] = ""
            # Atomic write: write to tmp then rename
            _tmp = _path + ".tmp"
            with open(_tmp, "w", newline="", encoding="utf-8") as _f:
                w = csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(_rows)
            os.replace(_tmp, _path)
            print(f"  [shot_log team_abbrev] rewrote {len(_rows)} rows; {_resolved} resolved")
        except Exception as _e:
            print(f"  [shot_log team_abbrev] rewrite failed: {_e}")

    def _remap_possession_ids_for_join(self) -> None:
        """BUG-FIX: Remap frame-based possession_id to sequential 0-based IDs so
        tracking_data.csv and shot_log.csv join cleanly to possessions.csv.

        After _export_possessions_csv runs, possessions.csv contains the surviving
        possessions (filtered, merged) with their original frame-based IDs.  This
        method reads possessions.csv, builds a {frame_based_pid -> sequential_pid}
        dict (0..N-1 in row order), then rewrites tracking_data.csv and shot_log.csv
        atomically via temp-file replace.  Called near the end of process(), after all
        other backfill methods.
        """
        poss_path     = os.path.join(self._data_dir, "possessions.csv")
        tracking_path = os.path.join(self._data_dir, "tracking_data.csv")
        shot_path     = os.path.join(self._data_dir, "shot_log.csv")

        if not os.path.exists(poss_path):
            return

        # Build frame_pid -> sequential_pid map from possessions.csv
        try:
            with open(poss_path, newline="", encoding="utf-8") as _f:
                _poss_rows = list(csv.DictReader(_f))
        except Exception as _e:
            print(f"  [poss_id_remap] failed reading possessions.csv: {_e}")
            return

        pid_map: dict = {}
        for _seq, _prow in enumerate(_poss_rows):
            _frame_pid = _prow.get("possession_id")
            if _frame_pid is not None:
                try:
                    pid_map[int(_frame_pid)] = _seq
                except ValueError:
                    pass

        if not pid_map:
            print("  [poss_id_remap] no possession_id found in possessions.csv — skipped")
            return

        def _rewrite(path: str) -> None:
            if not os.path.exists(path):
                return
            try:
                with open(path, newline="", encoding="utf-8") as _f:
                    reader = csv.DictReader(_f)
                    _fields = list(reader.fieldnames or [])
                    _rows   = list(reader)
                _remapped = 0
                for _row in _rows:
                    _old = _row.get("possession_id")
                    if _old is not None and _old != "":
                        try:
                            _new = pid_map.get(int(_old))
                            if _new is not None:
                                _row["possession_id"] = str(_new)
                                _remapped += 1
                        except ValueError:
                            pass
                _tmp = path + ".tmp"
                with open(_tmp, "w", newline="", encoding="utf-8") as _f:
                    w = csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(_rows)
                os.replace(_tmp, path)
                print(f"  [poss_id_remap] {os.path.basename(path)}: {_remapped}/{len(_rows)} rows remapped")
            except Exception as _e:
                print(f"  [poss_id_remap] {os.path.basename(path)} rewrite failed: {_e}")

        _rewrite(tracking_path)
        _rewrite(shot_path)

    @staticmethod
    def _classify_shot_creation(
        poss_counts: dict,
        shot_zone: str,
        vel_toward_basket: float,
        shot_dist_ft: float,
        possession_duration: float,
        ball_shot_arc_angle: float,
        dribble_count: int = 0,
    ) -> str:
        """
        R8 rewrite — uses per-possession event counts instead of the broken dribble_count
        signal. Buckets: transition, pick_and_roll, post_up, drive_layup, floater, pull_up,
        isolation, catch_and_shoot, other.
        """
        pc       = poss_counts or {}
        pass_n   = pc.get("pass_count",   0)
        screen_n = pc.get("screen_count", 0)
        drive_n  = pc.get("drive_count",  0)
        cut_n    = pc.get("cut_count",    0)
        dur      = float(possession_duration or 0.0)
        # Transition: short possession, ball moving fast at the rim
        if 0.0 < dur < 7.0 and vel_toward_basket > 3.0:
            return "transition"
        # PnR: at least one screen + handler took it
        if screen_n >= 1 and (drive_n >= 1 or dribble_count >= 2):
            return "pick_and_roll"
        # Drive at the rim — paint with forward velocity
        if shot_zone == "paint" and vel_toward_basket > 2.0:
            if ball_shot_arc_angle and ball_shot_arc_angle > 55:
                return "floater"
            return "drive_layup"
        # Post-up: paint/mid, low velocity, no drives, no cuts
        if shot_zone in ("paint", "mid_range") and vel_toward_basket < 0.5 and drive_n == 0 and cut_n == 0:
            return "post_up"
        # Pull-up: handler drove this possession
        if drive_n >= 1 or dribble_count >= 2:
            return "pull_up"
        # Iso: long possession, no screens, no cuts, low pass count
        if pass_n <= 1 and screen_n == 0 and cut_n == 0 and dur >= 6.0:
            return "isolation"
        # Catch & shoot: pass came in, no drive, no screen (this is the strict definition)
        if pass_n >= 1 and drive_n == 0 and screen_n == 0:
            return "catch_and_shoot"
        # Fallback bucket — when the upstream signals (dribble_count, events) are stale,
        # default to catch_and_shoot ONLY if there were no plays at all; otherwise "other".
        if dribble_count == 0 and pass_n == 0 and screen_n == 0:
            return "catch_and_shoot"
        return "other"


class _ReIdStub:
    """Stub so StatsTracker doesn't crash when re_id weights aren't loaded."""
    shot_id = -1
    player_dict = {}
    faiss_index = None

    def person_query_lst(self, *a, **kw):
        return [], []

    def hard_voting(self, *a, **kw):
        return {}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="NBA AI — unified tracking pipeline")
    ap.add_argument("--video",    required=True, help="Path to input video (.mp4)")
    ap.add_argument("--game-id",  default=None,  help="NBA Stats game ID for enrichment")
    ap.add_argument("--output",   default=None,  help="Output CSV path (default: data/tracking_data.csv)")
    ap.add_argument("--frames",   type=int, default=None, help="Max frames to process")
    ap.add_argument("--start-frame", type=int, default=0, help="Frame to start from")
    ap.add_argument("--no-show",       action="store_true", help="Disable live preview window")
    ap.add_argument("--yolo",          default=None,  help="Path to YOLO-NAS weights (.pth)")
    ap.add_argument("--period",        type=int, default=1, help="Quarter the clip covers (1-4)")
    ap.add_argument("--clip-start-sec", type=float, default=0.0,
                    help="Seconds into the quarter when the clip starts")
    args = ap.parse_args()

    pipeline = UnifiedPipeline(
        video_path=args.video,
        yolo_weight_path=args.yolo,
        max_frames=args.frames,
        start_frame=args.start_frame,
        show=not args.no_show,
        game_id=args.game_id,
        period=args.period,
        clip_start_sec=args.clip_start_sec,
    )
    pipeline.run()
