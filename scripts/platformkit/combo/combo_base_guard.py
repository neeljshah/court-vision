"""scripts.platformkit.combo.combo_base_guard -- L0 G5: collinear-with-base guard.

`base_guard.degenerate_base_reason` catches no_op / collapsed_constant /
collapsed_to_close on the PREDICTION streams, but a combination column A*B that is
~collinear with an ALREADY-SHIPPED feature C is a RE-EXPRESSION, not a discovery --
it merely relabels the locked feature ceiling (memory: feature_ceiling_locked, 17
REVERTs). A cross-corpus gate would happily "replicate" such a re-expression, so we
refuse it at build time.

This ports the discovery loop's `_ORTHO_CAP = 0.92` idea (src/loop/discovery.py:44):
if the combo column's |Pearson corr| with ANY already-shipped feature column is
>= tau, the combo is REJECTED as `collinear_with_base`. A combo must BEAT the locked
feature ceiling, not re-express it.

`collinear_with_base_reason(combo_preds, base_feature_cols, tau=0.92)` returns:
  * "collinear_with_base: ..." when the combo re-expresses a shipped feature, else
  * None when the combo is genuinely (sufficiently) orthogonal to every base column.

Purity: never raises -- malformed / non-finite / constant input returns a reason so the
caller defaults to REJECT (an honest null is a SUCCESS, never an accidental SHIP). A
CONSTANT combo column has no orthogonal information to add and is rejected as degenerate.

Calibration, not edge. NO $ / ROI anywhere. numpy + stdlib only. ASCII; <=300 LOC.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

import numpy as np

# Mirrors discovery._ORTHO_CAP: a combo whose |corr| with a shipped feature meets/exceeds
# this is a re-expression, not a discovery, and the gate would reject it anyway.
DEFAULT_TAU = 0.92
# A column with variance below this carries no orthogonal information -- treated as a
# degenerate (constant) combo that cannot be a genuine new signal.
_VAR_FLOOR = 1e-12


def _arr(x: Any) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _abs_corr(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    """|Pearson(a,b)| or None when either column is constant (undefined correlation)."""
    if a.shape != b.shape or a.size < 2:
        return None
    va, vb = float(a.var()), float(b.var())
    if va < _VAR_FLOOR or vb < _VAR_FLOOR:
        return None
    c = float(np.corrcoef(a, b)[0, 1])
    if not np.isfinite(c):
        return None
    return abs(c)


def collinear_with_base_reason(
    combo_preds: Sequence[float],
    base_feature_cols: Mapping[str, Sequence[float]],
    tau: float = DEFAULT_TAU,
) -> Optional[str]:
    """Return a 'collinear_with_base' reason if the combo re-expresses a shipped feature.

    Parameters
    ----------
    combo_preds
        The combination column under test (a per-row stream, e.g. the combo feature).
    base_feature_cols
        name -> column for EVERY already-shipped / proven base feature the combo must
        not merely re-express. Each column must align row-for-row with combo_preds.
    tau
        Collinearity cap (default 0.92, mirroring discovery._ORTHO_CAP). |corr| >= tau
        with ANY base column -> REJECT.

    Returns
    -------
    str | None
        "collinear_with_base: <feature> |r|=<value> >= tau=<tau>" when the combo is a
        re-expression; "degenerate_input: ..." on malformed/constant input; None when
        the combo is sufficiently orthogonal to EVERY base column (a genuine candidate).

    Never raises (purity contract).
    """
    try:
        if not (0.0 < float(tau) <= 1.0):
            return f"degenerate_input: tau must be in (0,1], got {tau}"
        combo = _arr(combo_preds)
        if combo.ndim != 1 or combo.size == 0 or not np.all(np.isfinite(combo)):
            return "degenerate_input: combo column empty or non-finite"
        if float(combo.var()) < _VAR_FLOOR:
            # A constant combo adds no orthogonal information -- it cannot be a discovery.
            return "degenerate_input: combo column is constant (no orthogonal signal)"
        if not base_feature_cols:
            # No base to be collinear with -> nothing to re-express; orthogonal by default.
            return None
        worst_name, worst_r = None, -1.0
        for name, col in base_feature_cols.items():
            b = _arr(col)
            if b.shape != combo.shape or not np.all(np.isfinite(b)):
                return f"degenerate_input: base feature {name!r} misaligned or non-finite"
            r = _abs_corr(combo, b)
            if r is None:
                continue  # a constant base column cannot be re-expressed; skip it
            if r > worst_r:
                worst_name, worst_r = name, r
            if r >= float(tau):
                return (f"collinear_with_base: {name} |r|={r:.4f} >= tau={float(tau):.2f} "
                        "(re-expression of a shipped feature, not a discovery)")
        return None
    except Exception as exc:  # purity contract: never raise to the caller
        return f"degenerate_input: {type(exc).__name__}: {exc}"


__all__ = ["DEFAULT_TAU", "collinear_with_base_reason"]
