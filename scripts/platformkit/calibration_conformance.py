"""scripts/platformkit/calibration_conformance.py — Calibration-conformance check.

HONESTY NOTE: Good calibration means P(outcome=1 | pred=p) ≈ p. It does NOT mean
the model beats the closing line or has a positive expected value vs the market.
Calibration ≠ edge. See: feedback_accuracy_is_not_edge.md.

Metrics
-------
brier_score  : float   — MSE of probability forecasts; perfect = 0.0.
ece          : float   — Expected Calibration Error (frequency-weighted |pred-obs|).
base_rate    : float   — Empirical mean outcome frequency.
reliability_bins : list[BinResult] — per-decile (pred, obs, n).
verdict      : PASS (ECE < 0.05) / WARN (< 0.10) / FAIL (>= 0.10) / SKIP.
               Verdict refers ONLY to reliability quality, NOT profitability.

CLI: python scripts/platformkit/calibration_conformance.py
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

import numpy as np

from kernel.validation.proof_metrics import brier as _brier, ece as _ece

# ---------------------------------------------------------------------------
# Thresholds (documented: sane empirical bar for sports models, 0.05–0.10 window)
# ---------------------------------------------------------------------------
ECE_PASS_THRESHOLD: float = 0.05
ECE_WARN_THRESHOLD: float = 0.10
N_BINS: int = 10
HONESTY_NOTE: str = (
    "CALIBRATION != EDGE: a well-calibrated model confirms the probability scale "
    "is reliable. It does NOT imply the model beats the market close or has a "
    "positive expected value. See feedback_accuracy_is_not_edge.md."
)

_ADAPTER_REGISTRY: Dict[str, Tuple[str, str]] = {
    "tennis": ("domains.tennis.adapter", "TennisAdapter"),
    "soccer": ("domains.soccer.adapter", "SoccerAdapter"),
    "mlb":    ("domains.mlb.adapter",    "MLBAdapter"),
    "nba":    ("domains.basketball_nba.adapter", "NBAAdapter"),
}


@dataclass
class BinResult:
    """Reliability diagram bin."""
    bin_lo: float
    bin_hi: float
    mean_pred: float   # NaN when bin is empty
    mean_obs: float    # NaN when bin is empty
    n: int


@dataclass
class CalibrationResult:
    """Calibration report for one adapter/corpus.

    Attributes: sport, n, brier_score, ece, base_rate, reliability_bins,
    verdict, honesty_note, seasons_used, error.
    verdict is PASS/WARN/FAIL/SKIP — reliability quality only, NOT edge.
    """
    sport: str
    n: int = 0
    brier_score: float = float("nan")
    ece: float = float("nan")
    base_rate: float = float("nan")
    reliability_bins: List[BinResult] = field(default_factory=list)
    verdict: str = "SKIP"
    honesty_note: str = HONESTY_NOTE
    seasons_used: List[int] = field(default_factory=list)
    error: Optional[str] = None


def _load_adapter_class(sport: str) -> Optional[Type[Any]]:
    if sport not in _ADAPTER_REGISTRY:
        return None
    module_path, class_name = _ADAPTER_REGISTRY[sport]
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)
    except Exception:  # noqa: BLE001
        return None


def _reliability_bins(probs: np.ndarray, outcomes: np.ndarray,
                      n_bins: int = N_BINS) -> List[BinResult]:
    """Compute per-decile reliability diagram; always returns n_bins items."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: List[BinResult] = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        mask = (probs >= lo) & (probs < hi) if i < n_bins - 1 else (probs >= lo) & (probs <= hi)
        n_bin = int(mask.sum())
        bins.append(BinResult(
            lo, hi,
            float(probs[mask].mean()) if n_bin else float("nan"),
            float(outcomes[mask].mean()) if n_bin else float("nan"),
            n_bin,
        ))
    return bins


def _verdict(ece_val: float) -> str:
    """Map ECE to PASS / WARN / FAIL / SKIP verdict."""
    if np.isnan(ece_val):
        return "SKIP"
    if ece_val < ECE_PASS_THRESHOLD:
        return "PASS"
    if ece_val < ECE_WARN_THRESHOLD:
        return "WARN"
    return "FAIL"


def calibration_conformance(
    adapter: Any,
    seasons: Optional[List[int]] = None,
) -> CalibrationResult:
    """Compute calibration metrics for one adapter on its corpus.

    Uses adapter.feature_bundle(hypothesis=None, seasons=seasons).
    signal_col = predicted probability (walk-forward Elo/Poisson, strictly pre-match).
    target = binary realized outcome.

    CALIBRATION != EDGE. See HONESTY_NOTE. This function must not be used to
    claim a betting edge.
    """
    sport: str = getattr(adapter, "sport", "unknown")
    seasons_used: List[int] = list(seasons) if seasons else []
    try:
        bundle = adapter.feature_bundle(hypothesis=None, seasons=seasons or [])
    except Exception as exc:  # noqa: BLE001
        return CalibrationResult(sport=sport, error=str(exc), seasons_used=seasons_used)

    raw_probs = np.asarray(bundle.signal_col, dtype=float)
    raw_targets = np.asarray(bundle.target, dtype=float)
    valid = ~(np.isnan(raw_probs) | np.isnan(raw_targets))
    probs, outcomes = raw_probs[valid], raw_targets[valid]
    n = int(len(probs))
    if n == 0:
        return CalibrationResult(sport=sport, error="No valid rows after NaN filter.",
                                  seasons_used=seasons_used)

    bs = _brier(probs, outcomes)
    ece_val = _ece(probs, outcomes, bins=N_BINS)
    return CalibrationResult(
        sport=sport, n=n,
        brier_score=bs, ece=ece_val, base_rate=float(outcomes.mean()),
        reliability_bins=_reliability_bins(probs, outcomes, N_BINS),
        verdict=_verdict(ece_val),
        honesty_note=HONESTY_NOTE,
        seasons_used=seasons_used,
        error=None,
    )


def run_all_sports(seasons: Optional[List[int]] = None) -> List[CalibrationResult]:
    """Run calibration_conformance for all registered adapters.

    Absent corpora and import errors produce verdict=SKIP with an error string;
    exceptions are never propagated to the caller.
    """
    results: List[CalibrationResult] = []
    for sport, (module_path, class_name) in _ADAPTER_REGISTRY.items():
        cls = _load_adapter_class(sport)
        if cls is None:
            results.append(CalibrationResult(
                sport=sport,
                error=f"Could not import {module_path}.{class_name}.",
                seasons_used=list(seasons) if seasons else [],
            ))
            continue
        try:
            adapter = cls()
        except Exception as exc:  # noqa: BLE001
            results.append(CalibrationResult(
                sport=sport, error=f"Adapter init failed: {exc}",
                seasons_used=list(seasons) if seasons else [],
            ))
            continue
        results.append(calibration_conformance(adapter, seasons=seasons))
    return results


def main() -> int:
    """Print per-sport calibration table. Return 1 if any sport FAILs, else 0."""
    results = run_all_sports()
    hdr = f"{'Sport':<14} {'N':>6} {'Brier':>8} {'ECE':>8} {'BaseRate':>9} {'Verdict':<8}"
    sep = "-" * len(hdr)
    print()
    print("Calibration Conformance Report")
    print(f"Thresholds: PASS ECE<{ECE_PASS_THRESHOLD}, WARN ECE<{ECE_WARN_THRESHOLD}, FAIL otherwise")
    print(f"\nNOTE: {HONESTY_NOTE}\n")
    print(hdr)
    print(sep)
    any_fail = False
    for r in results:
        if r.error:
            print(f"{r.sport:<14} [SKIP] {r.error[:70]}")
            continue
        def _f(v: float, w: int = 8) -> str:
            return f"{v:{w}.4f}" if not np.isnan(v) else f"{'n/a':>{w}}"
        print(f"{r.sport:<14} {r.n:>6} {_f(r.brier_score)} {_f(r.ece)} {_f(r.base_rate, 9)}"
              f" {r.verdict:<8}")
        if r.verdict == "FAIL":
            any_fail = True
    print(sep)
    print()
    for r in results:
        if r.error or not r.reliability_bins:
            continue
        print(f"  Reliability bins — {r.sport}:")
        for b in r.reliability_bins:
            if b.n == 0:
                continue
            print(f"    [{b.bin_lo:.1f},{b.bin_hi:.1f})  pred={b.mean_pred:.4f}  "
                  f"obs={b.mean_obs:.4f}  n={b.n}")
        print()
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
