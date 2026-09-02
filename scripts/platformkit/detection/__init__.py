"""License-aware object-detection backends for PlatformKit."""

from .shim import (
    Detection,
    DetectorBackend,
    UltralyticsYoloBackend,
    YoloxOnnxBackend,
    get_detector,
)

__all__ = [
    "Detection",
    "DetectorBackend",
    "UltralyticsYoloBackend",
    "YoloxOnnxBackend",
    "get_detector",
]
