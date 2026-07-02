"""improve.parity_check -- train==inference feature parity assertion.

WHAT THIS GUARDS AGAINST (the most expensive bug class):
  A feature is wired into training but reads a constant 0.0 at inference
  because the inference path never sets it, or uses a different key, or
  the pipeline was rebuilt without re-wiring the new column.  The result is
  a model that trains on signal X but silently bets on X=0 -- which looks
  fine at import time and only manifests as a small-but-permanent Brier
  regression in production.

API:
  parity_ok(train_features, infer_features, *, tol=1e-9)
      -> {"ok": bool, "mismatches": [...], "zero_reads": [...]}

  train_features: dict[str, float]  -- feature dict captured at train time
  infer_features: dict[str, float]  -- feature dict from the same observation
                                        at inference time (must match by key)
  tol: float  -- absolute tolerance for "same value" (default 1e-9)

  Returns a plain dict; never raises.  The caller decides what to do.

ZERO-READ RULE:
  Any feature whose inference value is exactly 0.0 (or within 0.0 +- tol)
  AND whose train value is not also 0.0 is reported in "zero_reads" -- a
  separate bucket from general divergences because a zero-read is almost
  always a wiring bug, not a data difference.

Both lists may be non-empty simultaneously (a zero-read is also a mismatch).

Build context: improve/ is a SAFE new tree; no gated paths touched.
Pure function; no I/O; no side effects; stdlib + no numpy dep required.
<=300 LOC; ASCII; no edge claims.
"""
from __future__ import annotations

from typing import Any, Dict, List

# The public type returned by parity_ok.  Using a plain dict so the function
# needs no imports at the call site -- the caller just reads ["ok"].
ParityResult = Dict[str, Any]


def parity_ok(
    train_features: Dict[str, float],
    infer_features: Dict[str, float],
    *,
    tol: float = 1e-9,
) -> ParityResult:
    """Assert that train and inference feature dicts agree on every key/value.

    Parameters
    ----------
    train_features:
        Feature dict as seen at train time for a single observation.
    infer_features:
        Feature dict produced by the inference pipeline for the same observation.
    tol:
        Absolute tolerance for "close enough" (default 1e-9).  Two float values
        whose absolute difference is <= tol are considered identical.

    Returns
    -------
    dict with keys:
        "ok"         -- True only if both dicts are key-identical AND all values
                        agree within tol.
        "mismatches" -- list of dicts describing every diverging key.
                        Each entry: {"feature": str, "train": val, "infer": val,
                                     "abs_diff": float, "is_zero_read": bool}.
        "zero_reads" -- subset of mismatches where the inference value is
                        (approximately) 0.0 but the train value is not.
                        These are the silent-0.0-wiring bugs we guard against.

    Never raises; on any internal error returns ok=False with a descriptive
    mismatch entry so the caller always has actionable output.
    """
    try:
        return _check(train_features, infer_features, tol)
    except Exception as exc:  # pragma: no cover
        return {
            "ok": False,
            "mismatches": [{"feature": "<internal error>",
                            "train": None, "infer": None,
                            "abs_diff": None, "is_zero_read": False,
                            "error": str(exc)[:200]}],
            "zero_reads": [],
        }


def _check(
    train: Dict[str, float],
    infer: Dict[str, float],
    tol: float,
) -> ParityResult:
    """Inner implementation -- separated so the outer try/except can be thin."""
    mismatches: List[Dict[str, Any]] = []

    # --- key-set divergences ------------------------------------------------
    train_keys = set(train.keys())
    infer_keys = set(infer.keys())

    for k in sorted(train_keys - infer_keys):
        mismatches.append({
            "feature": k,
            "train": train[k],
            "infer": None,
            "abs_diff": None,
            "is_zero_read": False,
            "reason": "present in train, missing at inference",
        })

    for k in sorted(infer_keys - train_keys):
        mismatches.append({
            "feature": k,
            "train": None,
            "infer": infer[k],
            "abs_diff": None,
            "is_zero_read": False,
            "reason": "present at inference, not seen in train",
        })

    # --- value divergences on shared keys -----------------------------------
    for k in sorted(train_keys & infer_keys):
        tv = train[k]
        iv = infer[k]

        # Both must be numeric; handle the non-numeric case gracefully.
        tv_num = _to_float(tv)
        iv_num = _to_float(iv)

        if tv_num is None or iv_num is None:
            # Non-numeric: use equality.
            if tv != iv:
                mismatches.append({
                    "feature": k,
                    "train": tv,
                    "infer": iv,
                    "abs_diff": None,
                    "is_zero_read": False,
                    "reason": "non-numeric values differ",
                })
            continue

        diff = abs(iv_num - tv_num)
        if diff <= tol:
            continue  # within tolerance -> agree

        is_zero_read = (abs(iv_num) <= tol) and (abs(tv_num) > tol)
        mismatches.append({
            "feature": k,
            "train": tv,
            "infer": iv,
            "abs_diff": diff,
            "is_zero_read": is_zero_read,
        })

    zero_reads = [m for m in mismatches if m.get("is_zero_read")]
    return {
        "ok": len(mismatches) == 0,
        "mismatches": mismatches,
        "zero_reads": zero_reads,
    }


def _to_float(v: Any) -> "float | None":
    """Convert v to float if numeric; return None otherwise."""
    if isinstance(v, bool):
        return None  # booleans: use equality comparison, not numeric
    if isinstance(v, (int, float)):
        return float(v)
    return None


__all__ = ["parity_ok", "ParityResult"]
