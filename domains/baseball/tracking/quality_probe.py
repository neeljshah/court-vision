"""Baseball-specific tracking-depth measurements for pitch-view runs."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class BaseballDepthReport:
    """Coverage and calibration depth, without claiming signal validity."""

    pitch_view_frame_pct: float
    pitches_detected: int
    scale_stability_rate: float
    command_meter_coverage: float
    depth_grade: str

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation of this report."""
        return asdict(self)


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator <= 0 else numerator / denominator


def _grade(view_pct: float, pitches: int, stability: float, command: float) -> str:
    if pitches >= 5 and view_pct >= 0.70 and stability >= 0.80 and command >= 0.70:
        return "A"
    if pitches >= 1 and view_pct >= 0.35 and stability >= 0.50:
        return "B"
    return "C"


def probe_quality(metadata: Mapping[str, object]) -> BaseballDepthReport:
    """Measure pitch-view, scale, and command coverage from adapter metadata.

    ``command_meter_coverage`` is the fraction of detected pitch segments with
    an emitted command row.  A missing crossing detector correctly yields zero
    coverage; the grade measures tracking depth, not prediction quality.
    """
    processed = int(metadata.get("frames_processed", 0))
    view_frames = int(metadata.get("pitch_view_frames", 0))
    pitches = int(metadata.get("pitch_segments", 0))
    raw = metadata.get("raw_calibrations", [])
    stable = metadata.get("calibrations", [])
    raw_count = len(raw) if isinstance(raw, list) else 0
    stable_count = len(stable) if isinstance(stable, list) else 0
    series = metadata.get("command_series")
    command_rows = len(series) if isinstance(series, pd.DataFrame) else 0
    view_pct = _rate(view_frames, processed)
    stability = _rate(stable_count, raw_count)
    command = _rate(command_rows, pitches)
    return BaseballDepthReport(
        pitch_view_frame_pct=view_pct,
        pitches_detected=pitches,
        scale_stability_rate=stability,
        command_meter_coverage=command,
        depth_grade=_grade(view_pct, pitches, stability, command),
    )
