"""predict_service.prop_surface_tiering -- tier + sort PlayerPropRow lists.

P2-8: Given a list of PlayerPropRow dicts (from prop_surface.build_prop_rows /
build_props_response), assign calibration-based tiers and return the rows sorted
by (tier, confidence) descending.

PUBLIC API:
  tier_and_sort(rows, calibration=None)  -> list[dict]
    Sort a priced row list.  Never raises.
  apply_tiering_to_response(body, calibration=None)  -> dict
    Top-level: patch an entire /api/predict/props response (UNAVAILABLE passes
    through unchanged; 'rows' list gets tier + sort applied in place).

TIER ASSIGNMENT:
  prop_tiering.classify(stat, calibration) -> (label, bss, n)
  label == "proven" AND p_over is not None  -> tier "CALIBRATION_PROVEN"
  label in {"marginal","weak","unmeasured"} -> tier "MODEL_VIEW"
  p_over is None (unpriced / no history)    -> tier None (sinks to bottom)

SORT KEY (descending priority):
  1. tier rank: CALIBRATION_PROVEN=0, MODEL_VIEW=1, None=2
  2. confidence rank: "recency_gaussian"=0, any-other-str=1, None=2
  3. |edge_vs_market| descending (calibration divergence proxy; no $ interpretation)

HONESTY: No $ / pnl / roi field is added or mutated.  edge_vs_market is a
probability difference.  UNAVAILABLE responses pass through unchanged.  The
calibration cache defaults to the NBA OOF cache (P0-1); if absent, falls back
to the soccer soccer cache; if both absent, all rows classify as "unmeasured"
-> tier "MODEL_VIEW" (sorted by confidence then edge_vs_market).

INVARIANTS: <=300 LOC; ASCII only; no src/ imports; no network I/O; read-only
except for dict mutations on the returned row copies.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier rank table (lower = higher priority in descending sort)
# ---------------------------------------------------------------------------
_TIER_RANK: Dict[Optional[str], int] = {
    "CALIBRATION_PROVEN": 0,
    "MODEL_VIEW": 1,
    None: 2,
}

_CONF_RANK: Dict[Optional[str], int] = {
    "recency_gaussian": 0,
    None: 2,
}

_DEFAULT_CONF_RANK = 1  # any other non-None string


def _conf_rank(confidence: Optional[str]) -> int:
    if confidence is None:
        return _CONF_RANK[None]
    return _CONF_RANK.get(confidence, _DEFAULT_CONF_RANK)


def _sort_key(row: Dict[str, Any]):
    """(tier_rank, confidence_rank, -abs_edge_vs_market) for ascending sort."""
    tier = row.get("tier")
    # None is not in _TIER_RANK unless explicitly mapped; guard unknown strings
    t_rank = _TIER_RANK.get(tier, 2) if tier is None else _TIER_RANK.get(str(tier), 1)
    c_rank = _conf_rank(row.get("confidence"))
    evm = row.get("edge_vs_market")
    try:
        abs_evm = abs(float(evm)) if evm is not None else 0.0
    except (TypeError, ValueError):
        abs_evm = 0.0
    return (t_rank, c_rank, -abs_evm)


# ---------------------------------------------------------------------------
# Tier assignment
# ---------------------------------------------------------------------------

def _assign_tier_to_row(
    row: Dict[str, Any],
    calibration: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a shallow copy of *row* with tier assigned.

    Uses prop_tiering.classify(stat, calibration).  Never raises.
    """
    try:
        from scripts.platformkit import prop_tiering  # noqa: PLC0415
        stat = str(row.get("stat", "")).lower()
        label, _bss, _n = prop_tiering.classify(stat, calibration)
    except Exception as exc:  # noqa: BLE001 -- never raise
        logger.debug("prop_surface_tiering: classify failed (%s)", exc)
        label = "unmeasured"

    p_over = row.get("p_over")
    # Only rows that were priced get a non-None tier
    if p_over is None:
        tier = None
    elif label == "proven":
        tier = "CALIBRATION_PROVEN"
    else:
        # marginal / weak / unmeasured all map to MODEL_VIEW
        tier = "MODEL_VIEW"

    out = dict(row)
    out["tier"] = tier
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _load_default_calibration() -> Dict[str, Any]:
    """Load NBA calibration (P0-1 cache) or fall back to soccer cache.

    Returns {} on all failures (rows degrade to unmeasured -> MODEL_VIEW).
    Never raises.
    """
    try:
        from scripts.platformkit.props_eval_nba import load_nba_calibration  # noqa: PLC0415
        cal = load_nba_calibration()
        if cal:
            return cal
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_surface_tiering: load_nba_calibration failed (%s)", exc)

    try:
        from scripts.platformkit import prop_tiering  # noqa: PLC0415
        return prop_tiering.load_calibration()
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_surface_tiering: load_calibration fallback failed (%s)", exc)

    return {}


def tier_and_sort(
    rows: List[Dict[str, Any]],
    calibration: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Assign tiers and sort PlayerPropRow list.

    *calibration*: pre-loaded map {stat: {bss, n, ...}} from prop_tiering.
      If None, loads the default cache (NBA OOF -> soccer -> empty {}).
    *rows*: list of PlayerPropRow dicts (may be empty).
    Returns a new list with tier assigned and sorted by (tier, confidence,
    -|edge_vs_market|) descending.  Never raises; degrades gracefully.
    """
    if not rows:
        return []

    if calibration is None:
        calibration = _load_default_calibration()

    tiered: List[Dict[str, Any]] = []
    for row in rows:
        tiered.append(_assign_tier_to_row(row, calibration))

    tiered.sort(key=_sort_key)
    return tiered


def apply_tiering_to_response(
    body: Dict[str, Any],
    calibration: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply tier + sort to a full /api/predict/props response body.

    UNAVAILABLE (status != 'ok') responses pass through unchanged.
    No $ field is added.  Returns the (mutated) body dict.  Never raises.
    """
    if not isinstance(body, dict):
        return body

    status = body.get("status")
    if status != "ok":
        # UNAVAILABLE / not_found / error -> pass through unchanged
        return body

    rows = body.get("rows")
    if not isinstance(rows, list):
        return body

    try:
        body["rows"] = tier_and_sort(rows, calibration=calibration)
        body["count"] = len(body["rows"])
    except Exception as exc:  # noqa: BLE001 -- never raise
        logger.warning("prop_surface_tiering: apply failed (%s)", exc)

    return body


__all__ = [
    "tier_and_sort",
    "apply_tiering_to_response",
]
