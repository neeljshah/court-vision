"""Conservative jersey-number identification from player tracklets."""

from .pipeline import (
    EasyOcrBackend,
    OcrBackend,
    StubBackend,
    TrackletVoter,
    identify,
    legibility_score,
    torso_crop,
)

__all__ = [
    "EasyOcrBackend",
    "OcrBackend",
    "StubBackend",
    "TrackletVoter",
    "identify",
    "legibility_score",
    "torso_crop",
]
