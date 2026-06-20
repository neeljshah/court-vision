"""scripts/platformkit/calib_drift_monitor.py -- Calibration drift monitor.

Detects regime shift by comparing rolling ECE/Brier windows against a
baseline window and flagging when recent windows diverge significantly.

CALIBRATION NOT EDGE.  This module is diagnostic only.  A stale flag means
the recalibration map was trained under a prior regime and should be refit;
it does NOT indicate a betting edge.

PUBLIC API
----------
check_drift(probs, outcomes, window_size, threshold_ece, threshold_brier)
    -> DriftResult  (status in {NOT_STALE, STALE, INSUFFICIENT_DATA})

RAILS
-----
- UNITS not $.  No dollar / roi / pnl keys.
- stale-never-green: INSUFFICIENT_DATA when < 2 full windows of data.
- Honest REJECT is a success.
- ASCII only.  <= 300 LOC.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np

# ---------------------------------------------------------------------------
# Import calibration helpers -- with self-contained fallbacks so tests run
# in any environment (mirrors recalibration._ece / eval_gate.scoring patterns).
# ---------------------------------------------------------------------------
try:
    from scripts.platformkit.eval_gate.scoring import brier as _brier_fn, ece as _ece_fn
except Exception:
    def _brier_fn(p: Sequence[float], y: Sequence[float]) -> float:  # type: ignore[misc]
        p_, y_ = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
        return float(np.mean((p_ - y_) ** 2))

    def _ece_fn(p: Sequence[float], y: Sequence[float], bins: int = 10) -> float:  # type: ignore[misc]
        p_, y_ = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
        edges = np.linspace(0.0, 1.0, bins + 1)
        n = len(p_)
        if n == 0:
            return 0.0
        total = 0.0
        for k in range(bins):
            lo, hi = edges[k], edges[k + 1]
            m = (p_ >= lo) & (p_ < hi) if k < bins - 1 else (p_ >= lo) & (p_ <= hi)
            if not m.any():
                continue
            total += (m.sum() / n) * abs(float(y_[m].mean()) - float(p_[m].mean()))
        return float(total)


# ---------------------------------------------------------------------------
# Constants / public sentinels
# ---------------------------------------------------------------------------

STATUS_NOT_STALE = "NOT_STALE"
STATUS_STALE = "STALE"
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

CALIBRATION_NOTE = (
    "calibration != edge: a stale recal map means the map should be refit "
    "under the new regime, NOT that a positive expected value exists"
)

# Default thresholds: ECE delta > 0.05 or Brier delta > 0.03 flags stale.
_DEFAULT_THRESHOLD_ECE: float = 0.05
_DEFAULT_THRESHOLD_BRIER: float = 0.03
_DEFAULT_WINDOW_SIZE: int = 100


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class WindowMetrics:
    """Calibration metrics for one rolling window."""

    window_index: int
    start: int
    end: int
    ece: float
    brier: float
    n: int


@dataclass
class DriftResult:
    """Output of check_drift().

    Fields
    ------
    status : str
        One of STATUS_NOT_STALE, STATUS_STALE, STATUS_INSUFFICIENT_DATA.
    stale : bool
        True iff status == STATUS_STALE.  Never True when INSUFFICIENT_DATA.
    offending_window_index : Optional[int]
        Index (0-based) of the FIRST window whose ECE or Brier diverges
        beyond the threshold.  None when not stale.
    baseline_ece : float
        ECE of the baseline (first) window.
    baseline_brier : float
        Brier of the baseline (first) window.
    windows : List[WindowMetrics]
        Per-window metrics (empty when INSUFFICIENT_DATA).
    note : str
        CALIBRATION_NOTE -- no edge meaning.
    """

    status: str
    stale: bool
    offending_window_index: Optional[int]
    baseline_ece: float
    baseline_brier: float
    windows: List[WindowMetrics] = field(default_factory=list)
    note: str = CALIBRATION_NOTE

    def as_dict(self) -> dict:
        """Serialise to a plain dict (no $ / roi / pnl keys)."""
        return {
            "status": self.status,
            "stale": self.stale,
            "offending_window_index": self.offending_window_index,
            "baseline_ece": self.baseline_ece,
            "baseline_brier": self.baseline_brier,
            "n_windows": len(self.windows),
            "windows": [
                {
                    "window_index": w.window_index,
                    "start": w.start,
                    "end": w.end,
                    "ece": w.ece,
                    "brier": w.brier,
                    "n": w.n,
                }
                for w in self.windows
            ],
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# Core public function
# ---------------------------------------------------------------------------


def check_drift(
    probs: Sequence[float],
    outcomes: Sequence[float],
    window_size: int = _DEFAULT_WINDOW_SIZE,
    threshold_ece: float = _DEFAULT_THRESHOLD_ECE,
    threshold_brier: float = _DEFAULT_THRESHOLD_BRIER,
    bins: int = 10,
) -> DriftResult:
    """Detect calibration drift via rolling ECE/Brier windows.

    Splits the ordered (probs, outcomes) sequence into non-overlapping windows
    of `window_size`.  The FIRST window is the baseline.  Every subsequent
    window is compared against the baseline; if |ECE_window - ECE_baseline|
    exceeds `threshold_ece` OR |Brier_window - Brier_baseline| exceeds
    `threshold_brier`, the recalibration map is flagged STALE.

    Parameters
    ----------
    probs : Sequence[float]
        Raw model probabilities in chronological order.
    outcomes : Sequence[float]
        Binary outcomes {0, 1} aligned to probs.
    window_size : int
        Number of events per rolling window (default 100).
    threshold_ece : float
        Absolute ECE increase that triggers a stale flag (default 0.05).
    threshold_brier : float
        Absolute Brier increase that triggers a stale flag (default 0.03).
    bins : int
        ECE bin count forwarded to the ECE helper (default 10).

    Returns
    -------
    DriftResult
        status=INSUFFICIENT_DATA when fewer than 2 complete windows are
        available (stale is always False in that case -- stale-never-green).
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if len(p) != len(y):
        raise ValueError(
            f"probs and outcomes must have the same length ({len(p)} vs {len(y)})"
        )

    n_total = len(p)
    n_windows = n_total // window_size  # floor -- only complete windows

    _insufficient = DriftResult(
        status=STATUS_INSUFFICIENT_DATA,
        stale=False,
        offending_window_index=None,
        baseline_ece=float("nan"),
        baseline_brier=float("nan"),
        windows=[],
    )

    if n_windows < 2:
        return _insufficient

    # Build per-window metrics
    windows: List[WindowMetrics] = []
    for idx in range(n_windows):
        s = idx * window_size
        e = s + window_size
        p_w = p[s:e]
        y_w = y[s:e]
        wm = WindowMetrics(
            window_index=idx,
            start=s,
            end=e,
            ece=_ece_fn(p_w, y_w, bins),
            brier=_brier_fn(p_w, y_w),
            n=window_size,
        )
        windows.append(wm)

    baseline = windows[0]
    offending: Optional[int] = None

    for wm in windows[1:]:
        ece_delta = abs(wm.ece - baseline.ece)
        brier_delta = abs(wm.brier - baseline.brier)
        if ece_delta > threshold_ece or brier_delta > threshold_brier:
            offending = wm.window_index
            break  # report the FIRST offending window

    stale = offending is not None
    status = STATUS_STALE if stale else STATUS_NOT_STALE

    return DriftResult(
        status=status,
        stale=stale,
        offending_window_index=offending,
        baseline_ece=baseline.ece,
        baseline_brier=baseline.brier,
        windows=windows,
    )
