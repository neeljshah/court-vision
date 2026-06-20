"""scripts.platformkit.bestbets.clv_index -- O(1) CLV lookup keyed by (game_id, market_type, side).

BB-Q4: replaces the O(n) per-card ledger scan in bestbets_compute._clv_for with a
dict index that is built ONCE from clv_ledger_io.load_rows and then hit in O(1).

API
---
build_clv_index(rows)   -- build the index from an already-loaded row list (pure, no I/O)
load_clv_index()        -- convenience: load_rows() then build_clv_index()
lookup(index, game_id, market_type, side) -- O(1) hit or INSUFFICIENT_DATA

Key schema
----------
key = (str(game_id), str(market_type), str(side))

Value schema (mirrors _CLV_EMPTY from bestbets_compute; no $ field)
------------
{
    "clv_pct":    float or None,
    "beat_close": bool or None,
    "clv_status": str,        -- "graded" or "proxy"
    "clv_is_proxy": bool,
}

Miss (key absent in index)
--------------------------
{
    "clv_pct":    None,
    "beat_close": None,
    "clv_status": "INSUFFICIENT_DATA",
    "clv_is_proxy": True,
}

Ungraded rows are silently skipped at index-build time.
No dollar / roi / pnl field is written anywhere.

INVARIANTS: <=300 LOC; ASCII only; no $; no network; stdlib + repo-internal only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Sentinel / miss shape (mirrors predict_service.bestbets_compute._CLV_EMPTY)
# ---------------------------------------------------------------------------
_CLV_MISS: Dict[str, Any] = {
    "clv_pct": None,
    "beat_close": None,
    "clv_status": "INSUFFICIENT_DATA",
    "clv_is_proxy": True,
}

# Type alias for the index
_IndexKey = Tuple[str, str, str]
CLVIndex = Dict[_IndexKey, Dict[str, Any]]


# ---------------------------------------------------------------------------
# Key builder
# ---------------------------------------------------------------------------

def _make_key(game_id: Any, market_type: Any, side: Any) -> _IndexKey:
    """Normalise key components to stripped lowercase strings."""
    return (
        str(game_id or "").strip(),
        str(market_type or "").strip().lower(),
        str(side or "").strip().lower(),
    )


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------

def build_clv_index(rows: List[Dict[str, Any]]) -> CLVIndex:
    """Build an O(1) dict index from a list of CLV ledger rows.

    Only GRADED rows (row["graded"] is truthy AND clv_pct is not None) are
    indexed. Ungraded / open / missing-clv rows are silently skipped.

    When the same key appears multiple times (e.g. regraded rows) the LAST
    occurrence wins -- callers writing rows in chronological order naturally
    keep the freshest value.

    Parameters
    ----------
    rows:
        Row dicts from clv_ledger_io.load_rows() (or any compatible source).

    Returns
    -------
    CLVIndex
        dict keyed by (game_id, market_type, side) -> clv value dict.
        Never raises. Empty input returns {}.
    """
    index: CLVIndex = {}
    if not rows:
        return index

    for row in rows:
        if not isinstance(row, dict):
            continue
        # Only index graded rows with a real clv_pct
        if not row.get("graded"):
            continue
        clv_pct = row.get("clv_pct")
        if clv_pct is None:
            continue

        game_id = str(row.get("game_id", "")).strip()
        # Support both market_type and legacy market/side fields
        market_type = str(
            row.get("market_type") or row.get("market") or ""
        ).strip().lower()
        side = str(row.get("side", "")).strip().lower()

        key = _make_key(game_id, market_type, side)

        try:
            clv_pct_f = float(clv_pct)
        except (TypeError, ValueError):
            continue

        beat_close_raw = row.get("beat_close")
        beat_close: Optional[bool] = bool(beat_close_raw) if beat_close_raw is not None else None

        clv_status = str(row.get("clv_status") or "graded")
        clv_is_proxy = bool(row.get("clv_is_proxy", False))

        index[key] = {
            "clv_pct": clv_pct_f,
            "beat_close": beat_close,
            "clv_status": clv_status,
            "clv_is_proxy": clv_is_proxy,
        }

    return index


# ---------------------------------------------------------------------------
# Convenience loader
# ---------------------------------------------------------------------------

def load_clv_index() -> CLVIndex:
    """Load the canonical CLV ledger and build the index. Never raises.

    Falls back to an empty index if the ledger is absent or load fails.
    """
    try:
        from scripts.platformkit.clv_ledger_io import load_rows  # noqa: PLC0415
        rows = load_rows()
    except Exception:  # noqa: BLE001
        rows = []
    return build_clv_index(rows or [])


# ---------------------------------------------------------------------------
# O(1) lookup
# ---------------------------------------------------------------------------

def lookup(
    index: CLVIndex,
    game_id: Any,
    market_type: Any,
    side: Any,
) -> Dict[str, Any]:
    """O(1) CLV lookup. Returns a copy of the stored value or the MISS sentinel.

    Parameters
    ----------
    index:
        CLVIndex produced by build_clv_index or load_clv_index.
    game_id, market_type, side:
        Lookup key components (coerced to str, lowercased).

    Returns
    -------
    dict with keys: clv_pct, beat_close, clv_status, clv_is_proxy.
    A miss returns clv_status="INSUFFICIENT_DATA", clv_is_proxy=True.
    No dollar / roi / pnl field is ever present.
    """
    key = _make_key(game_id, market_type, side)
    hit = index.get(key)
    if hit is None:
        return dict(_CLV_MISS)
    return dict(hit)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "CLVIndex",
    "build_clv_index",
    "load_clv_index",
    "lookup",
]
