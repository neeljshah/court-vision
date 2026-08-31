"""Jersey-number OCR helpers with tracklet-level, confidence-weighted voting."""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol

import cv2
import numpy as np


class OcrBackend(Protocol):
    """OCR provider returning text and confidence pairs for one image."""

    def read(self, crop: np.ndarray) -> list[tuple[str, float]]:
        """Read candidate strings from a BGR crop."""


class EasyOcrBackend:
    """EasyOCR adapter that imports the optional dependency on first use."""

    def __init__(self, languages: Sequence[str] = ("en",), gpu: bool = False) -> None:
        self.languages = list(languages)
        self.gpu = gpu
        self._reader: Any | None = None

    def read(self, crop: np.ndarray) -> list[tuple[str, float]]:
        """Return EasyOCR text candidates without exposing its bounding boxes."""
        if self._reader is None:
            import easyocr

            self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        return [(str(text), float(conf)) for _, text, conf in self._reader.readtext(crop)]


class StubBackend:
    """Fixed OCR output for deterministic tests and offline integration checks."""

    def __init__(self, results: Sequence[tuple[str, float]] = ()) -> None:
        self.results = [(str(text), float(conf)) for text, conf in results]

    def read(self, crop: np.ndarray) -> list[tuple[str, float]]:
        """Return the configured results, ignoring the crop."""
        return list(self.results)


def legibility_score(crop_bgr: np.ndarray) -> float:
    """Return a v1 0..1 OCR-legibility heuristic from crop quality signals."""
    if crop_bgr is None or crop_bgr.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY) if crop_bgr.ndim == 3 else crop_bgr
    sharpness = min(cv2.Laplacian(gray, cv2.CV_64F).var() / 500.0, 1.0)
    height, width = gray.shape[:2]
    size = min((height * width) / 1600.0, 1.0)
    contrast = min(float(np.std(gray)) / 64.0, 1.0)
    return float(np.clip(0.45 * sharpness + 0.25 * size + 0.30 * contrast, 0.0, 1.0))


def _point(keypoints: Any, name: str, position: int) -> tuple[float, float] | None:
    value = keypoints.get(name) if isinstance(keypoints, Mapping) else keypoints[position]
    if value is None or len(value) < 2:
        return None
    return float(value[0]), float(value[1])


def torso_crop(
    frame: np.ndarray, bbox: Sequence[float], keypoints: Any | None = None
) -> np.ndarray:
    """Extract a rectified pose torso, or a central-upper region of an xyxy box."""
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = (float(value) for value in bbox)
    if keypoints is not None:
        try:
            shoulders = (_point(keypoints, "left_shoulder", 0), _point(keypoints, "right_shoulder", 1))
            hips = (_point(keypoints, "left_hip", 2), _point(keypoints, "right_hip", 3))
        except (IndexError, KeyError, TypeError):
            shoulders, hips = (None, None), (None, None)
        if all((*shoulders, *hips)):
            left_shoulder, right_shoulder = shoulders
            left_hip, right_hip = hips
            torso_width = max(int(np.hypot(right_shoulder[0] - left_shoulder[0], right_shoulder[1] - left_shoulder[1])), 1)
            torso_height = max(
                int((np.hypot(left_hip[0] - left_shoulder[0], left_hip[1] - left_shoulder[1]) + np.hypot(right_hip[0] - right_shoulder[0], right_hip[1] - right_shoulder[1])) / 2),
                1,
            )
            source = np.float32([left_shoulder, right_shoulder, right_hip, left_hip])
            target = np.float32([[0, 0], [torso_width - 1, 0], [torso_width - 1, torso_height - 1], [0, torso_height - 1]])
            return cv2.warpPerspective(frame, cv2.getPerspectiveTransform(source, target), (torso_width, torso_height))
    box_width, box_height = x2 - x1, y2 - y1
    left = max(0, int(x1 + box_width * 0.15))
    right = min(width, int(x2 - box_width * 0.15))
    top = max(0, int(y1 + box_height * 0.12))
    bottom = min(height, int(y1 + box_height * 0.70))
    return frame[top:bottom, left:right]


class TrackletVoter:
    """Aggregate legibility-weighted OCR reads and preserve honest unknowns."""

    def __init__(self, min_votes: int = 3, min_confidence: float = 0.6) -> None:
        self.min_votes = min_votes
        self.min_confidence = min_confidence
        self._votes: dict[Any, list[tuple[str, float]]] = defaultdict(list)

    def add(self, track_id: Any, text: str, conf: float, legibility: float) -> None:
        """Add one valid one- or two-digit OCR reading for a track."""
        match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", str(text))
        weight = max(0.0, min(1.0, float(conf))) * max(0.0, min(1.0, float(legibility)))
        if match and weight:
            self._votes[track_id].append((match.group(1), weight))

    def number(self, track_id: Any) -> tuple[str | None, float]:
        """Return the winning number and its vote share, or an honest unknown."""
        votes = self._votes.get(track_id, [])
        if len(votes) < self.min_votes:
            return None, 0.0
        totals: dict[str, float] = defaultdict(float)
        for number, weight in votes:
            totals[number] += weight
        number, winning_weight = max(totals.items(), key=lambda item: item[1])
        confidence = winning_weight / sum(totals.values())
        return (number, confidence) if confidence >= self.min_confidence else (None, confidence)

    def track_ids(self) -> Iterable[Any]:
        """Yield track IDs that received valid OCR reads."""
        return self._votes.keys()


def _tracks_for_frame(tracks: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(tracks, Mapping):
        if "track_id" in tracks or "id" in tracks:
            return (tracks,)
        return (dict(item, track_id=track_id) for track_id, item in tracks.items())
    return tracks


def identify(
    frames_iter: Iterable[np.ndarray], tracks: Iterable[Any], backend: OcrBackend
) -> dict[Any, tuple[str | None, float]]:
    """OCR legible torso crops and return conservative jersey numbers by track ID.

    ``tracks`` yields the tracks for each frame. Each track is a mapping with
    ``track_id`` (or ``id``), ``bbox`` in xyxy order, and optional ``keypoints``.
    """
    voter = TrackletVoter()
    for frame, frame_tracks in zip(frames_iter, tracks):
        for track in _tracks_for_frame(frame_tracks):
            track_id = track.get("track_id", track.get("id"))
            crop = torso_crop(frame, track["bbox"], track.get("keypoints"))
            score = legibility_score(crop)
            if score >= 0.4:
                for text, confidence in backend.read(crop):
                    voter.add(track_id, text, confidence, score)
    return {track_id: voter.number(track_id) for track_id in voter.track_ids()}
