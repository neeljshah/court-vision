"""Offline-only bidirectional calibration smoothing with bounded adjustments.

The centered Savitzky-Golay window needs ``delay`` future frames.  It therefore
cannot be used for causal or streaming calibration.
"""
from __future__ import annotations

from typing import Union

import numpy as np
from scipy.signal import savgol_filter


ArrayLike = Union[np.ndarray, list[float], list[list[float]]]


def smooth_bidirectional(
    parameters: ArrayLike,
    adjustment_limits: Union[float, ArrayLike],
    delay: int = 15,
    mode: str = "offline",
) -> tuple[np.ndarray, np.ndarray]:
    """Smooth an ordered calibration series using a delayed, centered window.

    Args:
        parameters: One value per frame, shaped ``(frames,)`` or
            ``(frames, parameters)``.
        adjustment_limits: Maximum allowed absolute adjustment, either one
            nonnegative scalar or one value per parameter.
        delay: Number of future frames used by the centered smoothing window.
        mode: Must be ``"offline"``; causal and streaming modes are rejected.

    Returns:
        The smoothed values and a per-frame rejection mask. A frame is rejected
        when any parameter's smoothed value differs from its raw value by more
        than its adjustment limit.
    """
    if mode != "offline":
        raise ValueError("bidirectional smoothing is offline-only; causal modes are unsupported")
    if not isinstance(delay, int) or isinstance(delay, bool) or delay < 1:
        raise ValueError("delay must be a positive integer")

    raw = np.asarray(parameters, dtype=float)
    original_shape = raw.shape
    if raw.ndim == 1:
        values = raw[:, np.newaxis]
    elif raw.ndim == 2:
        values = raw
    else:
        raise ValueError("parameters must have shape (frames,) or (frames, parameters)")
    if len(values) == 0:
        raise ValueError("parameters must contain at least one frame")
    if not np.isfinite(values).all():
        raise ValueError("parameters must be finite")

    limits = np.asarray(adjustment_limits, dtype=float)
    if limits.ndim == 0:
        limits = np.full(values.shape[1], float(limits))
    if limits.shape != (values.shape[1],):
        raise ValueError("adjustment_limits must be scalar or one value per parameter")
    if not np.isfinite(limits).all() or (limits < 0).any():
        raise ValueError("adjustment_limits must be finite and nonnegative")

    window_length = 2 * delay + 1
    if len(values) < window_length:
        smoothed = values.copy()
    else:
        smoothed = savgol_filter(values, window_length, 2, axis=0, mode="interp")
    rejected = np.any(np.abs(smoothed - values) > limits, axis=1)

    if len(original_shape) == 1:
        return smoothed[:, 0], rejected
    return smoothed, rejected
