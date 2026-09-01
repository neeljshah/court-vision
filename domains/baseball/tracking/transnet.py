"""Optional TransNetV2 shot-boundary inference for baseball measurements.

The upstream implementation and released SavedModel are MIT licensed.  The
model was trained on ClipShots/IACC lineage; that provenance is recorded in the
baseball research report.  This module deliberately has no silent histogram
fallback: an unavailable or corrupt model makes a requested TransNet run fail.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

import cv2
import numpy as np


MODEL_FRAME_SHAPE = (27, 48, 3)


class TransNetV2UnavailableError(RuntimeError):
    """Raised when a requested TransNetV2 model cannot be loaded."""


class _RawModel(Protocol):
    def __call__(self, frames: Any) -> tuple[Any, dict[str, Any]]:
        ...


class TransNetV2BoundaryDetector:
    """Return source-frame boundaries from released TransNetV2 SavedModel weights."""

    def __init__(self, model_dir: Path | str, threshold: float = 0.5) -> None:
        if not 0.0 < threshold < 1.0:
            raise ValueError("threshold must be strictly between zero and one")
        self.model_dir = Path(model_dir)
        self.threshold = threshold
        self._model: Optional[_RawModel] = None
        self._tensorflow: Any = None

    def boundaries(self, bgr_frames: Sequence[np.ndarray]) -> np.ndarray:
        """Return one index for each threshold-crossing transition interval."""
        frames = _to_model_frames(bgr_frames)
        if not len(frames):
            return np.empty(0, dtype=np.int64)
        scores = self._predict_frames(frames)
        crossing = scores >= self.threshold
        starts = crossing & np.concatenate(([True], ~crossing[:-1]))
        return np.flatnonzero(starts).astype(np.int64)

    def scores(self, bgr_frames: Sequence[np.ndarray]) -> np.ndarray:
        """Return one single-frame transition probability per input frame."""
        frames = _to_model_frames(bgr_frames)
        if not len(frames):
            return np.empty(0, dtype=float)
        return self._predict_frames(frames)

    def _predict_frames(self, frames: np.ndarray) -> np.ndarray:
        model, tensorflow = self._load()
        padded = _padded_windows(frames)
        predictions: list[np.ndarray] = []
        for window in padded:
            logits, _ = model(tensorflow.cast(window[np.newaxis], tensorflow.float32))
            probabilities = tensorflow.sigmoid(logits).numpy()[0, 25:75, 0]
            predictions.append(np.asarray(probabilities, dtype=float))
        return np.concatenate(predictions)[:len(frames)]

    def _load(self) -> tuple[_RawModel, Any]:
        if self._model is not None:
            return self._model, self._tensorflow
        if not self.model_dir.is_dir():
            raise TransNetV2UnavailableError("TransNetV2 model directory is missing: %s" % self.model_dir)
        try:
            import tensorflow as tensorflow
            model = tensorflow.saved_model.load(str(self.model_dir))
        except (ImportError, OSError) as exc:
            raise TransNetV2UnavailableError("TransNetV2 model could not be loaded: %s" % exc) from exc
        self._model, self._tensorflow = model, tensorflow
        return model, tensorflow


def _to_model_frames(bgr_frames: Sequence[np.ndarray]) -> np.ndarray:
    converted: list[np.ndarray] = []
    for frame in bgr_frames:
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("each frame must be a BGR image with three channels")
        resized = cv2.resize(frame, (48, 27), interpolation=cv2.INTER_AREA)
        converted.append(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB))
    return np.asarray(converted, dtype=np.uint8)


def _padded_windows(frames: np.ndarray) -> list[np.ndarray]:
    """Use upstream's 100-frame windows with 25-frame temporal context."""
    if frames.ndim != 4 or tuple(frames.shape[1:]) != MODEL_FRAME_SHAPE:
        raise ValueError("model frames must have shape [frames, 27, 48, 3]")
    remainder = len(frames) % 50
    end_padding = 25 + 50 - (remainder if remainder else 50)
    padded = np.concatenate((
        np.repeat(frames[:1], 25, axis=0), frames,
        np.repeat(frames[-1:], end_padding, axis=0),
    ))
    return [padded[index:index + 100] for index in range(0, len(padded) - 99, 50)]
