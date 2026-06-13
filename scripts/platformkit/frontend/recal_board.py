"""scripts.platformkit.frontend.recal_board — board-side recalibration glue.

Wires the EXISTING leak-free walk-forward recalibrator into the multi-sport
board so the displayed ``model_prob`` is the recalibrated probability and the
row ``calibration_tag`` reflects what actually happened ("recalibrated" once
there is enough strictly-past history, else "raw").

HONESTY: calibration != edge.  Better-calibrated probabilities do NOT imply
beating the closing line or a positive expected value.  This module only fixes
a previously-false "calibrated" tag; it makes no edge claim whatsoever.

Leak-free: delegates to ``walk_forward_recalibrate``, which for event ``i`` fits
ONLY on events ``[:i]`` (strictly past).  No isotonic logic is reimplemented here.
"""
from __future__ import annotations

from typing import Any, Tuple

import numpy as np

from scripts.platformkit.recalibration import walk_forward_recalibrate

try:  # CALIBRATION_NOTE is optional; import defensively so a rename can't break us.
    from scripts.platformkit.recalibration import CALIBRATION_NOTE
except ImportError:  # pragma: no cover - defensive
    CALIBRATION_NOTE = (
        "calibration != edge: better-calibrated probabilities do NOT imply "
        "beating the market close or a positive expected value"
    )

__all__ = ["recalibrate_signal", "recalibrated_board_rows", "CALIBRATION_NOTE"]

# Target ~this-many isotonic refits regardless of corpus size.  Per-row refit is
# O(n^2) and made the board build take ~55min on the 25-30k-row corpora; block
# refit (still strictly leak-free) keeps it to seconds.  Small arrays (n <= this)
# get refit_every=1 == bit-identical per-row behaviour (so the unit tests and any
# rigor path are unaffected).
_BOARD_REFITS = 300


def recalibrate_signal(
    raw_probs: Any,
    outcomes: Any,
    *,
    min_history: int = 50,
    refit_every: int | None = None,
) -> np.ndarray:
    """Leak-free walk-forward recalibration of raw probabilities.

    Thin wrapper delegating to ``walk_forward_recalibrate``.  For event ``i``
    the calibration map is fit ONLY on events ``[:i]`` (strictly past), so the
    output for index ``i`` cannot depend on any future outcome.  Rows with a
    NaN raw probability or NaN outcome are handled by the underlying engine
    (the fit window drops them; an invalid query point passes through unchanged).

    ``refit_every`` defaults to ``max(1, n // _BOARD_REFITS)`` so large display
    corpora refit in blocks (fast) while small arrays stay per-row (exact).

    calibration != edge.  See CALIBRATION_NOTE.
    """
    raw = np.asarray(raw_probs, dtype=float)
    step = refit_every if refit_every is not None else max(1, len(raw) // _BOARD_REFITS)
    return walk_forward_recalibrate(
        raw, outcomes, min_history=min_history, refit_every=step
    )


def recalibrated_board_rows(
    sport_id: str,
    bundle: Any,
    *,
    min_history: int = 50,
) -> Tuple[np.ndarray, str]:
    """Return (recalibrated_probs, calibration_tag) for a feature bundle.

    The tag is the HONEST, dynamic tag — never the bare lie "calibrated":
      * "recalibrated" when there are more than ``min_history`` rows (so at
        least one row was actually transformed against strictly-past history);
      * "raw"          otherwise (every row passed through unchanged).

    calibration != edge.
    """
    raw = np.asarray(bundle.signal_col, dtype=float)
    y = np.asarray(bundle.target, dtype=float)
    cal = recalibrate_signal(raw, y, min_history=min_history)
    tag = "recalibrated" if len(raw) > min_history else "raw"
    return cal, tag
