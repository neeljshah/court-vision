"""Degenerate-base guard for recal-variant self-improvement candidates (MF2).

The 5-gate ratchet (`improve/proper_score_gate.py`) has a degenerate-INPUT guard
only (empty / non-finite / sigma<=0). It has NO degenerate-BASE guard: nothing
stops a pure recalibration variant (platt / isotonic / shin) from posting a
spuriously-good Brier by COLLAPSING -- to base, to a constant, or onto the
reference close -- and clearing all-proper-scores + multifold as a fabricated
"improvement." `ingame_gate_generic.decide` carries that guard ONLY for in-game
candidates; recal-variant candidates never flow through it. This module is the
guard for that path, per SKEPTIC_REVIEW MF2.

`degenerate_base_reason(cand_preds, base_preds, y, p_close=None)` returns a short
reason string when the candidate is degenerate, else None:

  (a) 'no_op'              -- within epsilon of base_preds everywhere; the
                             "candidate" is the base, so any "win" is noise.
  (b) 'collapsed_constant' -- sharpness (forecast variance) below a floor; the
                             stream collapsed toward a single value (e.g. the
                             base rate), which scores low Brier on imbalanced
                             corpora without any discrimination.
  (c) 'collapsed_to_close' -- within epsilon of p_close everywhere; any BSS-vs-
                             close was achieved by COPYING the reference, not by
                             skill. Only checked when p_close is supplied.

REUSE: sharpness comes from the validated eval-gate scoring module
(`scripts.platformkit.eval_gate.scoring.sharpness`, variance of forecasts).
This module adds NO new scoring math; it only decides degeneracy.

Calibration, not edge. This is an HONESTY guard: a degenerate candidate is a
REJECT (an honest null), never a SHIP. Purity: never raises -- malformed /
non-finite input returns a reason so the caller defaults to REJECT. ASCII only.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from scripts.platformkit.eval_gate.scoring import sharpness

ArrayLike = Sequence[float]

# A candidate within this max-abs distance of a reference stream EVERYWHERE is
# treated as identical to it (float noise of an identity transform stays inside
# this band; a real, distinct recalibration does not).
_EPS = 1e-9

# Sharpness (variance of the forecasts) below this floor means the stream has
# collapsed toward a single constant. A genuinely discriminating forecaster
# spreads probability mass; a collapse-to-base-rate forecaster does not. The
# floor is deliberately tiny -- it flags only true collapse, not a merely
# low-variance-but-still-distinct stream.
_SHARPNESS_FLOOR = 1e-6


def _arr(x: Any) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _finite(*arrays: np.ndarray) -> bool:
    return all(a.size > 0 and np.all(np.isfinite(a)) for a in arrays)


def _matches_everywhere(cand: np.ndarray, ref: np.ndarray) -> bool:
    """True iff cand is within _EPS of ref at every position (same length)."""
    if cand.shape != ref.shape:
        return False
    return bool(np.all(np.abs(cand - ref) <= _EPS))


def degenerate_base_reason(
    cand_preds: ArrayLike,
    base_preds: ArrayLike,
    y: ArrayLike,
    p_close: Optional[ArrayLike] = None,
) -> Optional[str]:
    """Return a degeneracy reason for a recal-variant candidate, else None.

    Parameters
    ----------
    cand_preds
        The recalibration CANDIDATE's probability stream.
    base_preds
        The current BASE's probability stream (what the candidate must beat).
    y
        Realized binary outcomes -- carried for parity with the gate signature
        and length validation; degeneracy is judged on the prediction streams.
    p_close
        Optional devigged-close reference. When supplied, a candidate that
        merely COPIES it is flagged 'collapsed_to_close' (BSS by matching the
        reference, not by skill).

    Returns
    -------
    str | None
        'no_op' | 'collapsed_constant' | 'collapsed_to_close' when degenerate;
        None when the candidate is a genuine, distinct, non-collapsed stream.

    Never raises: malformed / non-finite / mismatched input -> a reason string
    (so the caller defaults to REJECT, never an accidental SHIP).
    """
    try:
        cand = _arr(cand_preds)
        base = _arr(base_preds)
        y_arr = _arr(y)
        if cand.ndim != 1 or base.ndim != 1 or y_arr.ndim != 1:
            return "degenerate_input: preds and y must be 1-D"
        if not _finite(cand, base, y_arr):
            return "degenerate_input: empty or non-finite values"
        if not (len(cand) == len(base) == len(y_arr)):
            return "degenerate_input: length mismatch between cand, base, and y"

        # (a) no-op: the candidate IS the base (within float noise).
        if _matches_everywhere(cand, base):
            return "no_op"

        # (b) collapse toward a constant: forecast variance below the floor.
        if sharpness(cand) < _SHARPNESS_FLOOR:
            return "collapsed_constant"

        # (c) collapse onto the reference close: any BSS came from copying it.
        if p_close is not None:
            pc = _arr(p_close)
            if pc.ndim != 1 or not _finite(pc) or len(pc) != len(cand):
                return "degenerate_input: malformed p_close"
            if _matches_everywhere(cand, pc):
                return "collapsed_to_close"

        # Genuine, distinct, non-collapsed candidate.
        return None
    except Exception as exc:  # purity contract: never raise to the caller
        return f"degenerate_input: {type(exc).__name__}: {exc}"
