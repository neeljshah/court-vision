"""scripts.platformkit.bestbets.clv_sort_key -- CLV-based secondary sort key (BB-Q6).

Produces a single float 'clv_sort_key' to be used as the SECONDARY sort dimension
when ranking best-bet cards. Divergence (model vs market) remains the PRIMARY key;
this is ONLY the tiebreak within the same divergence bucket.

Design invariants (BB-Q6 acceptance criteria):
  1. TRUE-CLOSE CLV: clv_sort_key = clv_pct (float, signed, higher = better rank).
  2. PROXY CLV:      clv_sort_key = 0.0 -- a proxy close is honest noise; it must
                     never inflate rank above a card with no CLV data at all.
  3. NULL / INSUFFICIENT_DATA: clv_sort_key = 0.0 (same as proxy -- does not inflate).
  4. Divergence remains primary: callers must sort by (divergence_score DESC,
     clv_sort_key DESC). This module never re-orders by divergence; it only
     computes the secondary scalar.
  5. No dollar / roi / pnl / profit field. UNITS only. Probabilities + percentages ok.
  6. Pure module: no I/O, no network, no global state mutation.
  7. <= 300 LOC; ASCII only.

Proxy rationale:
  A proxy close (is_true_close=False, or clv_is_proxy=True in the index shape) is
  interpolated / estimated -- not a real captured market close. Its clv_pct is
  therefore unreliable. Treating it as 0.0 means proxy cards are ranked on
  divergence alone (their honest basis), while true-close cards can use their
  real CLV signal to differentiate further. This is the conservative, honest default:
  proxy contributes NOTHING to the sort key -- it does not inflate rank.

Input shapes accepted (any one of):
  a) ClvAudit dataclass from quant.clv_core:
       .clv_pct (float or None), .is_true_close (bool), .proxy (bool)
  b) Index dict from bestbets.clv_index.lookup:
       {"clv_pct": float|None, "clv_status": str, "clv_is_proxy": bool, ...}
  c) Raw dict with keys: clv_pct, is_true_close (or clv_is_proxy)
  d) None / anything else -> 0.0

Build on:
  * quant.clv_core.ClvAudit (read-only, duck-typed at runtime)
  * bestbets.clv_index lookup value shape
  * bestbets.divergence_rank.rank_cards (divergence is primary -- this is secondary)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

__all__ = [
    "clv_sort_key",
    "attach_clv_sort_keys",
]

# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------

# Proxy and null inputs both resolve to this value. Using exactly 0.0 (not
# -inf) so that proxy cards tie with null cards on the secondary key and are
# then broken by the same divergence_score they share (honest, stable sort).
_PROXY_OR_NULL: float = 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float:
    """Return float(value) clamped to finite; 0.0 on bad input. Never raises."""
    if value is None:
        return _PROXY_OR_NULL
    try:
        f = float(value)
    except (TypeError, ValueError):
        return _PROXY_OR_NULL
    if not math.isfinite(f):
        return _PROXY_OR_NULL
    return f


def _from_dict(clv: Dict[str, Any]) -> float:
    """Extract CLV sort key from a dict. See module docstring for accepted shapes.

    Provenance priority:
      1. 'is_true_close' key (ClvAudit.as_record / raw shape)
      2. 'clv_is_proxy' key (clv_index lookup shape, inverted)
      3. Neither present -> conservative default: treat as proxy -> 0.0
    """
    if "is_true_close" in clv:
        raw_tc = clv["is_true_close"]
        is_true = bool(raw_tc) if raw_tc is not None else False
    elif "clv_is_proxy" in clv:
        is_true = not bool(clv["clv_is_proxy"])
    else:
        # No provenance info -> treat as proxy (conservative, honest)
        return _PROXY_OR_NULL

    if not is_true:
        return _PROXY_OR_NULL

    # True-close: reject INSUFFICIENT_DATA status even if is_true_close=True (defensive)
    status = str(clv.get("clv_status") or "").strip()
    if status == "INSUFFICIENT_DATA":
        return _PROXY_OR_NULL

    return _safe_float(clv.get("clv_pct"))


# ---------------------------------------------------------------------------
# Core scalar computation
# ---------------------------------------------------------------------------

def clv_sort_key(clv: Any) -> float:
    """Compute the CLV secondary sort key for one card's CLV reading.

    Parameters
    ----------
    clv:
        One of:
          * ClvAudit dataclass (from quant.clv_core): duck-typed via .is_true_close
            and .clv_pct attributes.
          * dict with 'clv_pct' (float|None) and either 'is_true_close' (bool) or
            'clv_is_proxy' (bool) -- mirrors clv_index lookup value shape.
          * None or anything else -> 0.0.

    Returns
    -------
    float
        TRUE-CLOSE graded:  real clv_pct value (signed float; may be negative).
        PROXY or NULL:      0.0 exactly -- never inflates rank.
        Non-finite clv_pct: 0.0 (safe fallback).

    Guarantees
    ----------
    * Always returns a finite float; never raises.
    * No dollar / roi / pnl / profit field produced or consumed.
    * Proxy and null both return 0.0 -- proxy does NOT outrank null.
    """
    if clv is None:
        return _PROXY_OR_NULL

    # ---- ClvAudit dataclass path (duck-typed) ---------------------------
    # Detect by attribute presence; avoids a hard import of the forward_capture chain.
    if hasattr(clv, "is_true_close") and hasattr(clv, "clv_pct"):
        if not clv.is_true_close:
            return _PROXY_OR_NULL
        return _safe_float(clv.clv_pct)

    # ---- dict path (clv_index shape or raw dict) ------------------------
    if isinstance(clv, dict):
        return _from_dict(clv)

    # ---- anything else -> 0.0 -------------------------------------------
    return _PROXY_OR_NULL


# ---------------------------------------------------------------------------
# Batch helper: attach key to card list
# ---------------------------------------------------------------------------

def attach_clv_sort_keys(
    cards: List[Any],
    *,
    clv_key: str = "clv",
    output_key: str = "clv_sort_key",
) -> List[Any]:
    """Attach 'clv_sort_key' float to each card dict in-place.

    Reads the sub-dict (or ClvAudit) at card[clv_key] and writes the scalar
    to card[output_key]. Cards missing clv_key get 0.0. Pure: no I/O.

    Parameters
    ----------
    cards:
        List of card dicts (mutated in-place).
    clv_key:
        Key on each card that holds the CLV reading (default 'clv').
    output_key:
        Key to write the float onto each card (default 'clv_sort_key').

    Returns
    -------
    The same list (mutated in-place) for chaining. Empty input returns [].

    Guarantees
    ----------
    * Never raises on any input shape.
    * No dollar / roi / pnl / profit field is written.
    """
    for card in cards:
        if not isinstance(card, dict):
            continue
        clv_val = card.get(clv_key)
        card[output_key] = clv_sort_key(clv_val)
    return cards
