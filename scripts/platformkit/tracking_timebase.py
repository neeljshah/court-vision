"""Make tracking sampling and rate reporting explicit and reproducible.

The frozen harness scores distance per sampled observation.  Adapters therefore
choose a stride from each source's fps, targeting a 0.1 second observation
interval, and retain both the raw per-step and derived per-second values.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping


TARGET_SAMPLE_SECONDS = 0.1


@dataclass(frozen=True)
class SamplingPlan:
    """The actual temporal spacing requested from an adapter."""

    source_frame_rate: float | None
    stride: int
    target_interval_seconds: float
    sample_interval_seconds: float | None

    def to_dict(self) -> dict:
        """Return JSON-safe sampling provenance."""
        return asdict(self)


def sampling_plan(frame_rate: float | None,
                  target_seconds: float = TARGET_SAMPLE_SECONDS) -> SamplingPlan:
    """Choose the nearest whole-frame stride for a target wall-clock interval."""
    if frame_rate is None or frame_rate <= 0:
        return SamplingPlan(None, 3, target_seconds, None)
    stride = max(1, int(round(frame_rate * target_seconds)))
    return SamplingPlan(float(frame_rate), stride, target_seconds,
                        float(stride / frame_rate))


def per_second(value_per_step: float | None,
               interval_seconds: float | None) -> float | None:
    """Convert a raw per-observation distance to a reported per-second value."""
    if value_per_step is None or interval_seconds is None or interval_seconds <= 0:
        return None
    return float(value_per_step / interval_seconds)


def timebase_metrics(raw: Mapping[str, object], plan: SamplingPlan) -> dict:
    """Expose raw harness quantities and their non-gating rate equivalents."""
    interval = plan.sample_interval_seconds
    median = raw.get("median_step_distance")
    jump = raw.get("jump_p95")
    return {
        "sample_interval_seconds": interval,
        "median_step_distance_raw": median,
        "median_step_distance_per_second": per_second(median, interval),
        "jump_p95_raw": jump,
        "jump_p95_per_second": per_second(jump, interval),
        "note": "per_second values are reporting-only; frozen harness gates use raw per-step values",
    }
