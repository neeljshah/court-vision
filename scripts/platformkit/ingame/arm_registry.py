"""Fail-closed registry for in-game shadow arms.

The registry is deliberately not a promotion mechanism.  A registered arm can
only return a shadow prediction when its declared inputs are present and its
game-clustered effective sample size can be computed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence


FEATURE_MANIFEST = ("schedule_context", "market_micro", "market_coherence")
EXCLUDED_FEATURES = ("officials",)
OFFICIALS_CACHE_VERIFIED_EMPTY = True
MEASURED_DELTA_BRIER_LOCK = -0.03425595343964605
MEASURED_EFFECTIVE_N_LOCK = 268.0
MINIMUM_DELTA_BRIER_IMPROVEMENT = 0.004
MARKET_GUARD = 0.15
VERDICTS = frozenset(("MATCH", "BEHIND", "INSUFFICIENT", "SHIP_TO_SHADOW"))


@dataclass(frozen=True)
class ArmSpec:
    """One shadow-only arm and its non-negotiable runtime prerequisites."""

    name: str
    predict: Callable[[Mapping[str, Any]], Optional[float]]
    effective_n: Callable[[Sequence[Mapping[str, Any]]], Optional[float]]
    feature_manifest: tuple[str, ...] = FEATURE_MANIFEST
    market_guard: float = MARKET_GUARD
    enabled: bool = False


@dataclass(frozen=True)
class ArmResult:
    prediction: Optional[float]
    effective_n: Optional[float]
    reason: Optional[str] = None


def _has_manifest(row: Mapping[str, Any], manifest: Sequence[str]) -> bool:
    return all(row.get(name) is not None for name in manifest)


def run_shadow(spec: ArmSpec, row: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]) -> ArmResult:
    """Run one arm with hard evidence and input guards; never supply a default."""
    if spec.enabled:
        return ArmResult(None, None, "promotion_flags_must_remain_off")
    if "officials" in row or not _has_manifest(row, spec.feature_manifest):
        return ArmResult(None, None, "feature_manifest_unavailable")
    try:
        n_eff = spec.effective_n(evidence)
    except (KeyError, TypeError, ValueError):
        return ArmResult(None, None, "effective_n_unavailable")
    if n_eff is None or float(n_eff) <= 0.0:
        return ArmResult(None, None, "effective_n_unavailable")
    prediction = spec.predict(row)
    if prediction is None:
        return ArmResult(None, float(n_eff), "arm_returned_no_prediction")
    value = float(prediction)
    if not 0.0 <= value <= 1.0:
        return ArmResult(None, float(n_eff), "invalid_prediction")
    return ArmResult(value, float(n_eff))


def verdict(delta_brier: Optional[float], n_eff: Optional[float], corpora: int,
            null_shuffle_z: Optional[float], market_guard_ok: bool) -> str:
    """Apply the ship-to-shadow gate without changing any runtime flag."""
    if None in (delta_brier, n_eff, null_shuffle_z) or n_eff <= 0 or corpora < 2:
        return "INSUFFICIENT"
    if delta_brier < MEASURED_DELTA_BRIER_LOCK + MINIMUM_DELTA_BRIER_IMPROVEMENT:
        return "BEHIND"
    if abs(null_shuffle_z) >= 1.0 or not market_guard_ok:
        return "BEHIND"
    return "SHIP_TO_SHADOW"
