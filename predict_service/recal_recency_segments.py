"""predict_service.recal_recency_segments -- Multi-segment recency stability check.

Extends recal_pregame with a two-window replication gate: Brier improvement must
hold in BOTH a recent window AND a holdout window for ship=True.  A single-window
improvement is rejected as a single-fold artifact per the single-fold-artifact
discipline.

CALIBRATION not edge.  No $ field.  Honest no-improvement = success.

Public API::
    from predict_service.recal_recency_segments import recal_segment_check
    result = recal_segment_check(raw_probs, outcomes)
    # result.ship     -- True iff Brier improves in BOTH recency windows
    # result.windows  -- list of WindowMetrics (per-window Brier/ECE/n)
    # result.status   -- "ok" | "INSUFFICIENT_DATA"
    # result.note     -- human-readable verdict (no $ sign)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, NamedTuple, Sequence

import numpy as np

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.recalibration import (  # noqa: E402
    CALIBRATION_NOTE,
    _ece,
    walk_forward_recalibrate,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_WINDOW_EVENTS: int = 30   # minimum events required per recency window
MIN_TOTAL_EVENTS: int = 80    # minimum total events to attempt a 2-window split
_INSUFFICIENT = "INSUFFICIENT_DATA"

FORBIDDEN_KEYS = frozenset({
    "pnl", "roi", "bankroll", "profit", "dollar", "dollars",
    "usd", "stake", "edge_dollar", "payout",
})


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class WindowMetrics(NamedTuple):
    """Per-window calibration metrics (no $ field)."""
    window_label: str    # "recent" | "holdout"
    brier_raw: float     # Brier score of raw probs in this window
    brier_recal: float   # Brier score of recalibrated probs in this window
    ece_raw: float       # ECE of raw probs in this window
    ece_recal: float     # ECE of recalibrated probs in this window
    brier_improved: bool # True if brier_recal < brier_raw
    n: int               # number of events in this window


class SegmentCheckResult(NamedTuple):
    """Result of recal_segment_check() (no $ field).

    ship=True only when Brier improves in ALL windows (replication criterion).
    ship=False on single-window improvement, no improvement, or thin data.
    """
    ship: bool
    windows: List[WindowMetrics]
    status: str   # "ok" | "INSUFFICIENT_DATA"
    note: str     # human-readable verdict; no $ sign


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    mask = np.isfinite(probs) & np.isfinite(outcomes)
    if not mask.any():
        return float("nan")
    d = probs[mask] - outcomes[mask]
    return float(np.mean(d * d))


def _eval_window(p: np.ndarray, y: np.ndarray,
                 recal: np.ndarray, label: str) -> WindowMetrics:
    b_raw = _brier(p, y)
    b_recal = _brier(recal, y)
    mask = np.isfinite(p) & np.isfinite(y) & np.isfinite(recal)
    e_raw = float(_ece(p[mask], y[mask])) if mask.any() else float("nan")
    e_recal = float(_ece(recal[mask], y[mask])) if mask.any() else float("nan")
    improved = bool(np.isfinite(b_raw) and np.isfinite(b_recal) and b_recal < b_raw)
    return WindowMetrics(label, b_raw, b_recal, e_raw, e_recal, improved, len(p))


def _insufficient(note: str) -> SegmentCheckResult:
    return SegmentCheckResult(ship=False, windows=[], status=_INSUFFICIENT, note=note)


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def recal_segment_check(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    *,
    min_history: int = 50,
    split_fraction: float = 0.5,
    min_window_events: int = MIN_WINDOW_EVENTS,
    min_total_events: int = MIN_TOTAL_EVENTS,
    refit_every: int = 1,
) -> SegmentCheckResult:
    """Multi-segment recency stability check for walk-forward recalibration.

    Fits walk-forward isotonic recalibration (expanding window, leak-free) on
    the full sequence, then evaluates Brier/ECE on two non-overlapping windows
    of the eval portion (events >= min_history):
      "recent"  -- the later  split_fraction of eval events (most recent)
      "holdout" -- the earlier (1 - split_fraction) of eval events

    ship=True requires Brier improvement in BOTH windows.
    ship=False (NO_CANDIDATE) when:
      - improvement only in one window (single-fold artifact rejected)
      - no improvement in any window
      - either window has < min_window_events events (INSUFFICIENT_DATA)
      - total events < min_total_events (INSUFFICIENT_DATA)
      - length mismatch or degenerate input (INSUFFICIENT_DATA)

    Parameters
    ----------
    raw_probs : Sequence[float]
        Raw model probabilities in [0, 1], shape (N,), chronological order.
    outcomes : Sequence[float]
        Binary outcomes {0, 1}, shape (N,), same order.
    min_history : int
        Walk-forward warmup; events before this index excluded from eval windows.
    split_fraction : float
        Fraction of eval events assigned to the "recent" window (default 0.5).
    min_window_events : int
        Minimum events required in EACH window.
    min_total_events : int
        Minimum total events before attempting a split.
    refit_every : int
        Passed to walk_forward_recalibrate (default 1 = per-row refit).

    Returns
    -------
    SegmentCheckResult
        ship=True only when Brier improves in BOTH windows.
        CALIBRATION != EDGE.  No $ field.  Honest null = success.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    n = len(p)

    if n != len(y):
        return _insufficient("raw_probs and outcomes length mismatch -- INSUFFICIENT_DATA")

    if n < min_total_events:
        return _insufficient(
            f"n={n} < min_total_events={min_total_events} -- "
            "INSUFFICIENT_DATA; cannot form two stable recency windows"
        )

    recal = walk_forward_recalibrate(p, y, min_history=min_history,
                                     refit_every=refit_every)

    eval_idx = np.where(
        (np.arange(n) >= min_history)
        & np.isfinite(p) & np.isfinite(y) & np.isfinite(recal)
    )[0]
    n_eval = len(eval_idx)

    min_needed = max(2, 2 * min_window_events)
    if n_eval < min_needed:
        return _insufficient(
            f"eval window n_eval={n_eval} < 2*min_window_events={min_needed} -- "
            "INSUFFICIENT_DATA; cannot form two stable recency windows"
        )

    frac = float(np.clip(split_fraction, 0.1, 0.9))
    split_at = int(np.clip(
        int(round(n_eval * (1.0 - frac))),
        min_window_events, n_eval - min_window_events
    ))

    holdout_idx = eval_idx[:split_at]
    recent_idx = eval_idx[split_at:]

    if len(holdout_idx) < min_window_events or len(recent_idx) < min_window_events:
        return _insufficient(
            f"window sizes holdout={len(holdout_idx)}, recent={len(recent_idx)} "
            f"< min_window_events={min_window_events} -- INSUFFICIENT_DATA"
        )

    recent_m = _eval_window(p[recent_idx], y[recent_idx], recal[recent_idx], "recent")
    holdout_m = _eval_window(p[holdout_idx], y[holdout_idx], recal[holdout_idx], "holdout")
    windows: List[WindowMetrics] = [recent_m, holdout_m]

    all_improve = all(w.brier_improved for w in windows)
    n_improved = sum(1 for w in windows if w.brier_improved)
    nw = len(windows)

    if all_improve:
        ship = True
        verdict = (
            f"Brier improved in {n_improved}/{nw} windows "
            f"(recent: {recent_m.brier_raw:.5f}->{recent_m.brier_recal:.5f}, "
            f"holdout: {holdout_m.brier_raw:.5f}->{holdout_m.brier_recal:.5f}) "
            "-- replication criterion MET; ship=True"
        )
    elif n_improved == 0:
        ship = False
        verdict = (
            f"Brier did not improve in any window "
            f"(recent: improved={recent_m.brier_improved}, "
            f"holdout: improved={holdout_m.brier_improved}) "
            "-- no calibration benefit; ship=False (NO_CANDIDATE)"
        )
    else:
        ship = False
        verdict = (
            f"Brier improved in {n_improved}/{nw} windows only "
            "(single-fold artifact per discipline) -- "
            "improvement did NOT replicate; ship=False (NO_CANDIDATE)"
        )

    note = (
        f"{verdict}. "
        f"n_total={n}, n_eval={n_eval}, "
        f"recent_n={recent_m.n}, holdout_n={holdout_m.n}. "
        f"{CALIBRATION_NOTE[:70]}"
    )
    return SegmentCheckResult(ship=ship, windows=windows, status="ok", note=note)
