"""predict_service.recal_pregame -- Walk-forward pregame probability recalibrator.

Wraps the validated calibrator_zoo.select_calibrator into a served-pregame helper
that is:
  - identity-safe: if the input sequence is already well-calibrated (low raw ECE)
    or if select_calibrator picks the identity method, the output is unchanged
    within floating-point epsilon.
  - leak-free: all fits use ONLY strictly-past events (walk-forward, no future
    row touches the calibration window).
  - INSUFFICIENT_DATA-aware: fewer than MIN_HISTORY events (default 50) produce
    passthrough with INSUFFICIENT_DATA status -- stale-never-green.
  - no $ field: calibration only; odds/probs/units OK; no ROI/PnL/edge field.

Design constraints
------------------
- <=300 LOC. ASCII only. Python 3.9+.
- Reuses select_calibrator and measure_recal / CALIBRATION_NOTE from platformkit.
- No corpus path baked in -- caller supplies (raw_probs, outcomes).
- No side effects. No file I/O. Pure function returning a RecalResult.

Usage::

    from predict_service.recal_pregame import recal_pregame, MIN_HISTORY

    result = recal_pregame(
        raw_probs=[0.72, 0.65, 0.58, ...],
        outcomes=[1.0, 0.0, 1.0, ...],
    )
    # result.calibrated_probs  -- recalibrated (N,) array
    # result.chosen_method     -- e.g. "isotonic", "temperature", "identity"
    # result.raw_ece           -- ECE before recal (eval window only)
    # result.recal_ece         -- ECE after recal  (eval window only)
    # result.status            -- "ok" | "INSUFFICIENT_DATA"
    # result.note              -- short human-readable verdict (no $ sign)

CALIBRATION != EDGE. A near-zero or negative ECE delta for a well-calibrated
model (e.g. tennis/MLB Elo) is the honest expected result, not a failure.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence

import numpy as np

# ---------------------------------------------------------------------------
# Ensure repo root is on path so platformkit imports resolve in any cwd.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.calibrator_zoo import (  # noqa: E402
    CALIBRATION_NOTE,
    select_calibrator,
)
from scripts.platformkit.recalibration import _ece  # noqa: E402

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

MIN_HISTORY: int = 50  # walk-forward warmup; events below this pass through raw
_INSUFFICIENT = "INSUFFICIENT_DATA"

# Forbidden keys -- kept as a module-level guard for test_no_dollar_key.
FORBIDDEN_KEYS = frozenset({
    "pnl", "roi", "bankroll", "profit", "dollar", "dollars",
    "usd", "stake", "edge_dollar", "payout",
})


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

class RecalResult(NamedTuple):
    """Result of recal_pregame().

    Fields
    ------
    calibrated_probs : np.ndarray (N,)
        Recalibrated probabilities clipped to [0, 1]. When status is
        INSUFFICIENT_DATA or chosen_method is "identity", equals the raw input
        within floating-point epsilon.
    chosen_method : str
        The calibration method selected by walk-forward OOS log-loss minimisation
        ("identity", "temperature", "platt", "beta", "isotonic").
    raw_ece : Optional[float]
        ECE of raw probabilities over the eval window (indices >= MIN_HISTORY).
        None when status is INSUFFICIENT_DATA.
    recal_ece : Optional[float]
        ECE of calibrated_probs over the eval window. None when INSUFFICIENT_DATA.
    n_total : int
        Total number of events supplied.
    n_eval : int
        Number of events in the eval window (n_total - MIN_HISTORY, or 0 if thin).
    status : str
        "ok" if n_total >= MIN_HISTORY and the data are valid; otherwise
        "INSUFFICIENT_DATA". Never green on thin or degenerate data.
    note : str
        Short human-readable verdict. Contains no $ sign, no ROI/PnL claim.
    """
    calibrated_probs: np.ndarray
    chosen_method: str
    raw_ece: Optional[float]
    recal_ece: Optional[float]
    n_total: int
    n_eval: int
    status: str
    note: str


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def recal_pregame(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    *,
    min_history: int = MIN_HISTORY,
    refit_every: int = 1,
    methods: Optional[List[str]] = None,
) -> RecalResult:
    """Apply walk-forward pregame recalibration to a sequence of model probabilities.

    Parameters
    ----------
    raw_probs :
        Raw model P(home_win) or similar binary probability, shape (N,), in [0,1].
    outcomes :
        Binary realised outcomes {0, 1}, shape (N,). Must match len(raw_probs).
    min_history :
        Walk-forward warmup (default MIN_HISTORY=50). Events before this index
        pass through raw. If n < min_history, returns INSUFFICIENT_DATA.
    refit_every :
        Refit the calibrator every K events (1 = per-row; higher is faster for
        large corpora). Leak-free for any K >= 1.
    methods :
        Subset of calibrator methods to evaluate. Default: all five
        ("identity", "temperature", "platt", "beta", "isotonic").

    Returns
    -------
    RecalResult
        calibrated_probs is the walk-forward recalibrated output (identity-safe
        when already calibrated or when select_calibrator chooses "identity").

    Notes
    -----
    CALIBRATION != EDGE. A near-zero or negative ECE delta (recal_ece >= raw_ece)
    for an already-calibrated model is the honest expected result.
    No $ field anywhere. See CALIBRATION_NOTE.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    n = len(p)

    # ------------------------------------------------------------------
    # Guard: length mismatch -> INSUFFICIENT_DATA passthrough
    # ------------------------------------------------------------------
    if n != len(y):
        return RecalResult(
            calibrated_probs=p.copy(),
            chosen_method="identity",
            raw_ece=None,
            recal_ece=None,
            n_total=0,
            n_eval=0,
            status=_INSUFFICIENT,
            note="raw_probs and outcomes length mismatch",
        )

    # ------------------------------------------------------------------
    # Guard: too few events -> INSUFFICIENT_DATA passthrough.
    # Require n > min_history (strictly greater) so the eval window has
    # at least one row; n == min_history yields 0 eval rows which makes
    # select_calibrator raise on an empty tied-list.
    # ------------------------------------------------------------------
    if n <= min_history:
        return RecalResult(
            calibrated_probs=np.clip(p, 0.0, 1.0),
            chosen_method="identity",
            raw_ece=None,
            recal_ece=None,
            n_total=n,
            n_eval=0,
            status=_INSUFFICIENT,
            note=(
                f"n={n} <= min_history={min_history} -- "
                "INSUFFICIENT_DATA; raw passthrough"
            ),
        )

    # ------------------------------------------------------------------
    # Run N-method walk-forward OOS selector
    # ------------------------------------------------------------------
    result = select_calibrator(
        p, y,
        min_history=min_history,
        refit_every=refit_every,
        methods=methods,
    )
    cal_probs: np.ndarray = result["chosen_probs"]
    chosen: str = result["chosen_method"]
    n_eval: int = result["n_eval"]

    # ------------------------------------------------------------------
    # ECE on eval window only (indices >= min_history, finite outcomes)
    # ------------------------------------------------------------------
    eval_mask = np.arange(n) >= min_history
    eval_mask &= np.isfinite(y) & np.isfinite(p) & np.isfinite(cal_probs)
    n_eval_actual = int(eval_mask.sum())

    if n_eval_actual > 0:
        raw_ece_val = float(_ece(p[eval_mask], y[eval_mask]))
        recal_ece_val = float(_ece(cal_probs[eval_mask], y[eval_mask]))
    else:
        raw_ece_val = None
        recal_ece_val = None

    # ------------------------------------------------------------------
    # Build verdict note (no $ sign, no ROI/edge claim)
    # ------------------------------------------------------------------
    if n_eval_actual == 0:
        note = (
            f"chosen={chosen}; eval window empty after min_history={min_history}; "
            "calibration cannot be assessed -- INSUFFICIENT_DATA"
        )
        status = _INSUFFICIENT
    else:
        delta = (raw_ece_val - recal_ece_val) if (
            raw_ece_val is not None and recal_ece_val is not None
        ) else 0.0
        if abs(delta) < 1e-5:
            verdict = "no meaningful ECE change (already well-calibrated)"
        elif delta > 0:
            verdict = f"ECE improved by {delta:.4f} ({chosen})"
        else:
            verdict = (
                f"ECE unchanged or slightly worse ({delta:+.4f}) -- "
                "honest result for well-calibrated input"
            )
        note = (
            f"chosen={chosen}; n_eval={n_eval_actual}; "
            f"raw_ece={raw_ece_val:.4f}; recal_ece={recal_ece_val:.4f}; "
            f"{verdict}. {CALIBRATION_NOTE[:60]}"
        )
        status = "ok"

    return RecalResult(
        calibrated_probs=cal_probs,
        chosen_method=chosen,
        raw_ece=raw_ece_val,
        recal_ece=recal_ece_val,
        n_total=n,
        n_eval=n_eval_actual,
        status=status,
        note=note,
    )
