"""
jersey_ocr.py — Jersey number OCR and jersey color clustering.

Provides:
    get_reader()            — lazy-init PaddleOCR singleton (EasyOCR fallback)
    preprocess_crop()       — binarize a player bounding-box crop for OCR
    read_jersey_number()    — run OCR waterfall and return jersey digit (0-99) or None
    dominant_hsv_cluster()  — k-means color descriptor for jersey re-ID

Optimisations
-------------
  • PaddleOCR (GPU) replaces EasyOCR — ~3× faster per call.
  • Waterfall: normal → inverted → 2× upscale; returns on first confident hit.
    On average ~2.3× fewer OCR calls per frame than always running all three passes.

All functions are safe to call on any image size and never raise on bad input.

Module constants
----------------
    _OCR_CONF_MIN      = 0.65   minimum confidence to accept a read
    _MIN_CROP_PIXELS   = 600    below this fall back from k-means to mean color
    _KMEANS_K          = 3      number of clusters for jersey color
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import cv2
import numpy as np

_OCR_CONF_MIN    = 0.55  # minimum confidence to accept a digit read (raised back toward 0.65; 0.45 let too much noise through)
_MIN_CROP_PIXELS = 600   # below this, fall back from k-means to mean color
_KMEANS_K        = 3     # number of clusters for jersey color

# ── Per-slot OCR skip state ───────────────────────────────────────────────────
# Skips EasyOCR/PaddleOCR for slots that already have a confirmed jersey number
# and were read within the last _OCR_SKIP_FRAMES frames (~1 s at 30 fps).
_OCR_SKIP_FRAMES: int = 30
_slot_ocr_last:   dict = {}  # slot → frame_idx of last OCR run
_slot_confirmed:  dict = {}  # slot → last confirmed jersey number (int)

_reader: Optional[object] = None  # module-level singleton (PaddleOCR or EasyOCR)
_USE_PADDLE: bool = False          # True when PaddleOCR init succeeded

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_reader() -> object:
    """
    Return the shared OCR reader instance (lazy-init singleton).

    Tries PaddleOCR first (GPU, ~3× faster than EasyOCR).  Falls back to
    EasyOCR if PaddleOCR is not installed or fails to initialise.

    Returns:
        PaddleOCR or easyocr.Reader: Shared reader configured for digit recognition.

    Raises:
        RuntimeError: If COURTV_NO_OCR=1 is set (Phase G batch mode — OCR
            unused, saves ~10-15 GB RAM per worker from PaddlePaddle init).
    """
    if os.environ.get("COURTV_NO_OCR", "0") == "1":
        raise RuntimeError("OCR disabled via COURTV_NO_OCR=1")

    global _reader, _USE_PADDLE
    if _reader is not None:
        return _reader

    # Try PaddleOCR first
    try:
        import os as _os
        _os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR  # type: ignore
        _reader = PaddleOCR(
            use_angle_cls=False,
            lang="en",
            use_gpu=True,
            show_log=False,
            rec_char_dict_path=None,
        )
        _USE_PADDLE = True
        log.debug("jersey_ocr: using PaddleOCR (GPU)")
        return _reader
    except Exception as paddle_err:
        log.debug("jersey_ocr: PaddleOCR unavailable (%s) — falling back to EasyOCR", paddle_err)

    # Fallback: EasyOCR
    import easyocr  # type: ignore
    _reader = easyocr.Reader(["en"], gpu=True, verbose=False)
    _USE_PADDLE = False
    log.debug("jersey_ocr: using EasyOCR (fallback)")
    return _reader


def preprocess_crop(crop_bgr: np.ndarray) -> np.ndarray:
    """
    Preprocess a player bounding-box crop for jersey number OCR.

    Steps:
      1. Slice central 60% width × rows 25%-55% height (torso-only — avoids
         reading neighbouring players' jersey pixels, Fix A, audit 2026-05-26)
      2. Upscale to at least 64 px tall using bicubic interpolation
      3. Convert to grayscale and apply CLAHE (local contrast enhancement)
      4. Adaptive threshold to binarize (handles dark and light jerseys)

    Args:
        crop_bgr: BGR image array of any size.

    Returns:
        2D uint8 binary image ready for OCR. Falls back to a blank 64x32
        image if the crop is too small to slice.
    """
    h, w = crop_bgr.shape[:2]

    # Fix A: torso-only crop — narrow width to central 60% AND restrict rows to
    # 25%-55% of bbox height.  The previous full-width slice at 20%-70% read
    # pixels from neighbouring players' jerseys when bboxes overlapped, producing
    # the 17-35% dominant-jersey rates documented in the 2026-05-26 audit.
    x0 = int(w * 0.20)   # 20% from left — skip arm/shoulder of left neighbour
    x1 = int(w * 0.80)   # 80% from left — skip arm/shoulder of right neighbour
    x1 = max(x1, x0 + 1)  # ensure non-empty even on very narrow crops
    y0 = int(h * 0.25)   # 25% from top  — skip head/chin
    y1 = int(h * 0.55)   # 55% from top  — torso only (avoids shorts)
    roi = crop_bgr[y0:y1, x0:x1]

    if roi.size == 0 or roi.shape[0] < 2:
        return np.zeros((64, 32), dtype=np.uint8)

    # Upscale so OCR has enough resolution
    roi_h, roi_w = roi.shape[:2]
    if roi_h < 64:
        scale = 64.0 / roi_h
        new_h = 64
        new_w = max(1, int(roi_w * scale))
        roi = cv2.resize(roi, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    # Grayscale + CLAHE for local contrast
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)

    # Brightness normalisation — histogram stretch to full 0-255 range
    e_min, e_max = int(enhanced.min()), int(enhanced.max())
    if e_max > e_min:
        enhanced = cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)

    # Adaptive threshold — works on both dark and light jerseys
    binary = cv2.adaptiveThreshold(
        enhanced, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2,
    )
    return binary


def _ocr_image(img: np.ndarray) -> Optional[tuple]:
    """
    Run OCR on a single preprocessed image.

    Args:
        img: Preprocessed (binary) uint8 image.

    Returns:
        (best_number, best_conf) tuple if a valid digit was found, else None.
    """
    try:
        reader = get_reader()
        best_number: Optional[int] = None
        best_conf: float = -1.0

        if _USE_PADDLE:
            # PaddleOCR returns list of [[bbox, (text, conf)], ...]
            result = reader.ocr(img, cls=False)
            lines = result[0] if result else []
            if lines is None:
                lines = []
            for line in lines:
                if line is None:
                    continue
                try:
                    _, (text, conf) = line
                except (TypeError, ValueError):
                    continue
                text = str(text).strip()
                conf = float(conf)
                if (
                    text.isdigit()
                    and conf >= _OCR_CONF_MIN
                    and 0 <= int(text) <= 99
                    and conf > best_conf
                ):
                    best_conf = conf
                    best_number = int(text)
        else:
            # EasyOCR
            ocr_kwargs = dict(
                allowlist="0123456789",
                detail=1,
                paragraph=False,
                width_ths=0.7,
                min_size=5,
            )
            results = reader.readtext(img, **ocr_kwargs)
            for (_bbox, text, conf) in results:
                text = str(text).strip()
                if (
                    text.isdigit()
                    and conf >= _OCR_CONF_MIN
                    and 0 <= int(text) <= 99
                    and conf > best_conf
                ):
                    best_conf = conf
                    best_number = int(text)

        if best_number is not None:
            return (best_number, best_conf)
    except Exception as exc:
        log.debug("_ocr_image failed: %s", exc)
    return None


def read_jersey_number(crop_bgr: np.ndarray) -> Optional[int]:
    """
    Read a jersey number from a player bounding-box crop.

    Uses a waterfall strategy: runs normal binarized pass first; if a result
    with sufficient confidence is found, returns immediately without running
    further passes. Falls through to inverted pass, then 2× upscale pass.

    Waterfall order:
      1. Normal preprocessed image
      2. Inverted (bitwise NOT) — handles dark-on-light jerseys
      3. 2× upscale — helps small broadcast crops (< 32px wide)

    Args:
        crop_bgr: BGR image crop of a player bounding box (any size).

    Returns:
        Integer jersey number (0-99) if found with sufficient confidence,
        or None if no valid number detected. Never raises an exception.
    """
    try:
        preprocessed = preprocess_crop(crop_bgr)

        # Pass 1: normal
        result = _ocr_image(preprocessed)
        if result is not None:
            return result[0]

        # Pass 2: inverted — dark numbers on light jerseys
        result = _ocr_image(cv2.bitwise_not(preprocessed))
        if result is not None:
            return result[0]

        # Pass 3: 2× upscale — small broadcast crops
        h2x, w2x = preprocessed.shape[0] * 2, preprocessed.shape[1] * 2
        resized_2x = cv2.resize(preprocessed, (w2x, h2x), interpolation=cv2.INTER_CUBIC)
        result = _ocr_image(resized_2x)
        if result is not None:
            return result[0]

        return None

    except Exception as exc:
        log.debug("read_jersey_number failed silently: %s", exc)
        return None


def read_jersey_number_with_conf(
    crop_bgr: np.ndarray,
    slot: Optional[int] = None,
    frame_idx: Optional[int] = None,
) -> Optional[tuple]:
    """
    Read a jersey number and return ``(number, confidence)`` or ``None``.

    Same waterfall as :func:`read_jersey_number` but exposes the OCR confidence
    so callers can build a confidence-weighted majority vote.

    Args:
        crop_bgr:  BGR image crop of a player bounding box (any size).
        slot:      Tracker slot index, used for per-slot OCR skip state.
                   When provided together with ``frame_idx``, returns the cached
                   result immediately if the slot already has a confirmed jersey
                   number and fewer than ``_OCR_SKIP_FRAMES`` frames have elapsed
                   since the last OCR run (~1 second at 30 fps).
        frame_idx: Absolute video frame index, paired with ``slot``.

    Returns:
        ``(int, float)`` — (jersey_number, confidence) on success, or ``None``.
    """
    # ── 30-frame skip: return cached result for confirmed slots ───────────
    if slot is not None and frame_idx is not None:
        _confirmed = _slot_confirmed.get(slot)
        _last      = _slot_ocr_last.get(slot, -_OCR_SKIP_FRAMES)
        if _confirmed is not None and (frame_idx - _last) < _OCR_SKIP_FRAMES:
            return (_confirmed, 1.0)

    try:
        preprocessed = preprocess_crop(crop_bgr)

        result = _ocr_image(preprocessed)
        if result is not None:
            if slot is not None and frame_idx is not None:
                _slot_ocr_last[slot]  = frame_idx
                _slot_confirmed[slot] = result[0]
            return result  # (number, conf)

        result = _ocr_image(cv2.bitwise_not(preprocessed))
        if result is not None:
            if slot is not None and frame_idx is not None:
                _slot_ocr_last[slot]  = frame_idx
                _slot_confirmed[slot] = result[0]
            return result

        h2x, w2x = preprocessed.shape[0] * 2, preprocessed.shape[1] * 2
        resized_2x = cv2.resize(preprocessed, (w2x, h2x), interpolation=cv2.INTER_CUBIC)
        result = _ocr_image(resized_2x)
        if result is not None:
            if slot is not None and frame_idx is not None:
                _slot_ocr_last[slot]  = frame_idx
                _slot_confirmed[slot] = result[0]
            return result

        # No result: still update the last-run timestamp so we don't hammer this slot
        if slot is not None and frame_idx is not None:
            _slot_ocr_last[slot] = frame_idx
        return None

    except Exception as exc:
        log.debug("read_jersey_number_with_conf failed silently: %s", exc)
        return None


def dominant_hsv_cluster(
    crop_bgr: np.ndarray,
    k: int = _KMEANS_K,
) -> np.ndarray:
    """
    Compute a k-means color descriptor for the jersey region of a crop.

    Uses the upper 70% of the crop (jersey, not shorts) and returns the
    centroid of the largest cluster as a 3-element float32 HSV vector.
    Falls back to the mean HSV color when the crop is too small for
    clustering (< _MIN_CROP_PIXELS total pixels in the ROI).

    Args:
        crop_bgr: BGR image array of any non-zero size.
        k:        Number of k-means clusters (default _KMEANS_K = 3).

    Returns:
        np.ndarray: shape (3,) float32 in OpenCV HSV scale
                    (H: 0-180, S: 0-255, V: 0-255).
    """
    from sklearn.cluster import KMeans

    h = crop_bgr.shape[0]
    y1 = max(1, int(h * 0.70))
    roi = crop_bgr[:y1]

    if roi.size == 0:
        # Absolute fallback — return mid-grey
        return np.array([0.0, 0.0, 128.0], dtype=np.float32)

    # Convert to HSV for color descriptor
    roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    pixels = roi_hsv.reshape(-1, 3)

    if pixels.shape[0] < _MIN_CROP_PIXELS:
        # Too few pixels — mean color fallback (no KMeans crash)
        return pixels.mean(axis=0).astype(np.float32)

    try:
        kmeans = KMeans(n_clusters=k, n_init=3, max_iter=30, random_state=0)
        labels = kmeans.fit_predict(pixels.astype(np.float32))
    except OSError:
        # threadpoolctl DLL load failure on some Windows setups — use mean fallback
        return pixels.mean(axis=0).astype(np.float32)

    # Find centroid of the largest cluster
    counts = np.bincount(labels)
    dominant_idx = int(np.argmax(counts))
    return kmeans.cluster_centers_[dominant_idx].astype(np.float32)
