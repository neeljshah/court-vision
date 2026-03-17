"""
jersey_ocr.py — Jersey number OCR and jersey color clustering.

Provides:
    get_reader()            — lazy-init EasyOCR singleton
    preprocess_crop()       — binarize a player bounding-box crop for OCR
    read_jersey_number()    — run OCR and return jersey digit (0-99) or None
    dominant_hsv_cluster()  — k-means color descriptor for jersey re-ID

All functions are safe to call on any image size and never raise on bad input.

Module constants
----------------
    _OCR_CONF_MIN      = 0.65   minimum EasyOCR confidence to accept a read
    _MIN_CROP_PIXELS   = 600    below this fall back from k-means to mean color
    _KMEANS_K          = 3      number of clusters for jersey color
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

_OCR_CONF_MIN = 0.65    # minimum EasyOCR confidence to accept a digit read
_MIN_CROP_PIXELS = 600  # below this, fall back from k-means to mean color
_KMEANS_K = 3           # number of clusters for jersey color

_reader: Optional["easyocr.Reader"] = None  # module-level singleton

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_reader() -> "easyocr.Reader":
    """
    Return the shared EasyOCR reader instance (lazy-init singleton).

    The reader is created once on first call and reused on subsequent calls.
    Uses GPU when available, English digit allowlist only.

    Returns:
        easyocr.Reader: Shared reader configured for digit recognition.
    """
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["en"], gpu=True, verbose=False)
    return _reader


def preprocess_crop(crop_bgr: np.ndarray) -> np.ndarray:
    """
    Preprocess a player bounding-box crop for jersey number OCR.

    Steps:
      1. Slice rows 20%-70% of crop height (jersey number zone)
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

    # Slice jersey number region (rows 20%-70%)
    y0 = int(h * 0.20)
    y1 = int(h * 0.70)
    roi = crop_bgr[y0:y1]

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


def read_jersey_number(crop_bgr: np.ndarray) -> Optional[int]:
    """
    Read a jersey number from a player bounding-box crop.

    Runs OCR on both the preprocessed image and its inverse (to handle
    dark numbers on light jerseys and vice versa), then accepts the
    highest-confidence result that passes confidence and range checks.

    Args:
        crop_bgr: BGR image crop of a player bounding box (any size).

    Returns:
        Integer jersey number (0-99) if found with sufficient confidence,
        or None if no valid number detected. Never raises an exception.
    """
    try:
        preprocessed = preprocess_crop(crop_bgr)
        reader = get_reader()

        ocr_kwargs = dict(
            allowlist="0123456789",
            detail=1,
            paragraph=False,
            width_ths=0.7,
            min_size=5,
        )

        results_normal = reader.readtext(preprocessed, **ocr_kwargs)
        results_inverted = reader.readtext(cv2.bitwise_not(preprocessed), **ocr_kwargs)

        # Third pass: 2x upscale — small broadcast crops (< 32px wide) fail at native size
        h2x, w2x = preprocessed.shape[0] * 2, preprocessed.shape[1] * 2
        resized_2x = cv2.resize(preprocessed, (w2x, h2x), interpolation=cv2.INTER_CUBIC)
        results_2x = reader.readtext(resized_2x, **ocr_kwargs)

        # Pick best result across all three passes
        best_number: Optional[int] = None
        best_conf: float = -1.0

        for results in (results_normal, results_inverted, results_2x):
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

        return best_number

    except Exception as exc:
        log.debug("read_jersey_number failed silently: %s", exc)
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

    kmeans = KMeans(n_clusters=k, n_init=3, max_iter=30, random_state=0)
    labels = kmeans.fit_predict(pixels.astype(np.float32))

    # Find centroid of the largest cluster
    counts = np.bincount(labels)
    dominant_idx = int(np.argmax(counts))
    return kmeans.cluster_centers_[dominant_idx].astype(np.float32)
