"""Cheap, fail-open footage screening before a clip reaches tracking.

This is an ingest decision only.  It must never be consulted by tracking
metrics or the harness: its purpose is to keep non-sport footage out of the
teacher-label corpus, not to change a score denominator.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


QUARANTINE_DIR = Path("data/footage_quarantine")
_GREEN = ((35, 50, 35), (95, 255, 255))
_TAN = ((5, 25, 45), (35, 220, 255))
_TENNIS_BLUE = ((85, 45, 35), (125, 255, 255))


@dataclass(frozen=True)
class GateMetrics:
    sample_seconds: list[float]
    surface_fractions: list[float]
    border_fractions: list[float]
    cut_fraction: float


@dataclass(frozen=True)
class GateVerdict:
    decision: str
    reason: str
    metrics: GateMetrics


def _ranges(sport: str) -> tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...]:
    if sport in {"football", "soccer"}:
        return (_GREEN,)
    if sport in {"mlb", "kbo", "npb", "baseball"}:
        return (_GREEN, _TAN)
    if sport == "tennis":
        return (_GREEN, _TENNIS_BLUE)
    return (_TAN,)


def _surface_fraction(frame: np.ndarray, sport: str) -> float:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    masks = [cv2.inRange(hsv, np.array(low), np.array(high))
             for low, high in _ranges(sport)]
    mask = np.maximum.reduce(masks)
    return float(np.mean(mask > 0))


def _border_fraction(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    dark = gray < 18
    rows = np.mean(dark, axis=1) > 0.95
    cols = np.mean(dark, axis=0) > 0.95

    def edge_run(values: np.ndarray) -> int:
        count = 0
        for value in values:
            if not value:
                break
            count += 1
        return count

    top = edge_run(rows)
    bottom = edge_run(rows[::-1])
    left = edge_run(cols)
    right = edge_run(cols[::-1])
    return max((top + bottom) / gray.shape[0], (left + right) / gray.shape[1])


def _histogram(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [12, 8], [0, 180, 0, 256])
    return cv2.normalize(hist, hist).flatten()


def sample_clip(video: Path, sport: str) -> GateMetrics:
    """Read nine low-resolution frames using seeks, not full-video decoding."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("unreadable video: %s" % video)
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frames = max(capture.get(cv2.CAP_PROP_FRAME_COUNT), 1.0)
    duration = frames / fps
    times = [duration * portion for portion in (0.10, 0.30, 0.50, 0.70, 0.90)]
    burst_start = max(0.0, duration * 0.20)
    times.extend(min(duration * 0.98, burst_start + offset) for offset in range(0, 8, 2))
    surfaces: list[float] = []
    borders: list[float] = []
    histograms: list[np.ndarray] = []
    read_times: list[float] = []
    for second in times:
        capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000.0)
        ok, frame = capture.read()
        if not ok:
            continue
        frame = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
        surfaces.append(_surface_fraction(frame, sport))
        borders.append(_border_fraction(frame))
        histograms.append(_histogram(frame))
        read_times.append(round(second, 2))
    capture.release()
    if len(histograms) < 3:
        raise ValueError("insufficient readable frames: %s" % video)
    distances = [cv2.compareHist(a.astype("float32"), b.astype("float32"),
                                 cv2.HISTCMP_BHATTACHARYYA)
                 for a, b in zip(histograms[-4:], histograms[-3:])]
    cuts = sum(distance >= 0.42 for distance in distances) / len(distances)
    return GateMetrics(read_times, surfaces, borders, float(cuts))


def decide(metrics: GateMetrics) -> GateVerdict:
    """Return an ingest verdict.  Only unambiguous non-game evidence rejects."""
    max_surface = max(metrics.surface_fractions)
    max_border = max(metrics.border_fractions)
    if max_surface < 0.015 and max_border >= 0.20:
        return GateVerdict("reject", "composited_template_no_playing_surface", metrics)
    if max_surface < 0.015 and metrics.cut_fraction <= 0.20:
        return GateVerdict("reject", "static_non_sport_no_playing_surface", metrics)
    if max_surface < 0.06 or max_border >= 0.20 or metrics.cut_fraction >= 0.75:
        return GateVerdict("review", "ambiguous_content_fail_open", metrics)
    return GateVerdict("accept", "playing_surface_and_shot_continuity_present", metrics)


def screen(video: Path, sport: str) -> GateVerdict:
    """Sample and decide a clip before staging it for tracking."""
    return decide(sample_clip(video, sport))


def screen_fail_open(video: Path, sport: str) -> GateVerdict:
    """Screen a clip without allowing a decoder outage to block ingest."""
    try:
        return screen(video, sport)
    except (cv2.error, OSError, ValueError) as exc:
        return GateVerdict(
            "review", "screen_unavailable_fail_open: %s" % str(exc)[:100],
            GateMetrics([], [], [], 0.0),
        )


def _quarantine_file(video: Path, reason: str, payload: dict,
                     destination: Path) -> Path:
    """Shared move + sidecar write for both gate-driven and manual quarantines."""
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / video.name
    if target.exists():
        target = destination / (video.stem + ".duplicate" + video.suffix)
    shutil.move(str(video), str(target))
    write_quarantine_sidecar(target.with_suffix(target.suffix + ".json"), reason,
                             payload)
    return target


def write_quarantine_sidecar(sidecar: Path, reason: str, payload: dict) -> Path:
    """Write a reversible quarantine record without deleting its source video."""
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        json.dumps({"reason": reason, "quarantine_reason": reason,
                    "sport_verified": False, **payload}, indent=2) + "\n",
        encoding="utf-8",
    )
    return sidecar


def quarantine(video: Path, verdict: GateVerdict,
               destination: Path = QUARANTINE_DIR) -> Path:
    """Move a rejected clip and write an adjacent, reversible JSON reason."""
    if verdict.decision != "reject":
        raise ValueError("only rejected clips may be quarantined")
    return _quarantine_file(video, verdict.reason,
                            {"metrics": asdict(verdict.metrics)}, destination)


def quarantine_manual(video: Path, reason: str,
                      destination: Path = QUARANTINE_DIR) -> Path:
    """Quarantine a clip confirmed bad by human/agent review, not the color gate.

    The automatic surface-color gate only catches "no playing surface at all";
    it misses wrong-sport footage that still shows a real green field (a video-
    game replay, a different field sport). Use this once a rendered-frame check
    has confirmed the mislabel.
    """
    return _quarantine_file(video, reason, {"metrics": None}, destination)


def is_quarantined(video: Path) -> bool:
    """True when a clip is flagged bad: inside QUARANTINE_DIR, or carrying a
    sport_verified=false sidecar in place. Enumeration consumers
    (tracking_corpus_ab.corpus_clips, footage_census) call this so a flagged
    clip is skipped whether or not it has physically been moved yet.
    """
    try:
        if QUARANTINE_DIR.resolve() in video.resolve().parents:
            return True
    except OSError:
        pass
    sidecar = video.with_suffix(video.suffix + ".json")
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return payload.get("sport_verified", True) is False


def summary(verdicts: Iterable[GateVerdict]) -> dict[str, int]:
    """Count audit decisions for a report without altering any tracker metric."""
    counts = {"accept": 0, "review": 0, "reject": 0}
    for verdict in verdicts:
        counts[verdict.decision] += 1
    return counts
