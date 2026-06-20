"""scripts.platformkit.improve.clv_lifecycle_reconcile -- CLV ledger open/settled lifecycle.

Cross-checks the append-only CLV ledger's open/settled lifecycle and surfaces:
  * unsettled_open  -- opens with no settled twin (expected during active session)
  * settled_orphans -- settled rows whose open parent is MISSING (drift signal)

clean=True iff settled_orphans==0. Unsettled opens alone do NOT trigger drift.
Empty ledger -> clean=True. Missing file -> INSUFFICIENT_DATA.

Two ledger generations are handled:
  Gen 1: settle_key = sport|matchup|side|book|taken_decimal|ts (old format)
  Gen 2: settle_key = bet_id (sport|matchup|market|side|book|game_date)

Read-only. No $/roi/pnl key. Calibration not edge.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.clv_ledger import load_ledger, bet_id as _make_bet_id

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CALIBRATION_NOTE = (
    "calibration != edge: CLV lifecycle drift is a data-quality metric, "
    "not a profit or market-edge claim"
)

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _assert_no_banned_keys(obj: Any) -> None:
    """Recursively assert no banned key ($/roi/pnl/profit) appears anywhere."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _BANNED_KEY_RE.search(str(k)):
                raise ValueError("Banned key %r in lifecycle output" % k)
            _assert_no_banned_keys(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _assert_no_banned_keys(item)


def _gen1_open_key(row: Dict[str, Any]) -> str:
    """Generation-1 identity key for an open row.

    Mirrors the settle_key written by older grading code:
      sport|matchup|side|taken_book|taken_decimal|ts
    """
    return "|".join([
        str(row.get("sport", "")),
        str(row.get("matchup", "")),
        str(row.get("side", "")),
        str(row.get("taken_book", "")),
        str(row.get("taken_decimal", "")),
        str(row.get("ts", "")),
    ])


def _build_open_indexes(open_rows: List[Dict[str, Any]]) -> tuple:
    """(gen1_index, gen2_index): gen1 keyed by composite ts-key, gen2 by bet_id."""
    gen1: Dict[str, Dict[str, Any]] = {}
    gen2: Dict[str, Dict[str, Any]] = {}
    for row in open_rows:
        gen1[_gen1_open_key(row)] = row
        bid = str(row.get("bet_id") or "").strip()
        if bid:
            gen2[bid] = row
    return gen1, gen2


def _sk_is_gen1(sk: str) -> bool:
    """True if the last pipe-field of *sk* looks like an ISO timestamp."""
    parts = sk.split("|")
    return len(parts) == 6 and ("T" in parts[-1] or ":" in parts[-1])


def _find_open_for_settled(
    settled: Dict[str, Any],
    gen1_index: Dict[str, Dict[str, Any]],
    gen2_index: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return the open row that matches *settled*, or None (orphan)."""
    sk = str(settled.get("settle_key") or "").strip()
    if sk:
        # Gen-1: settle_key last field is ISO ts -> look in gen1
        if _sk_is_gen1(sk):
            hit = gen1_index.get(sk)
            if hit is not None:
                return hit
        else:
            # Gen-2: settle_key == bet_id
            hit = gen2_index.get(sk)
            if hit is not None:
                return hit
        # Try both regardless
        hit = gen1_index.get(sk) or gen2_index.get(sk)
        if hit is not None:
            return hit
    # Fallback: reconstruct bet_id from settled row's own fields
    try:
        hit = gen2_index.get(_make_bet_id(settled))
        if hit is not None:
            return hit
    except Exception:  # noqa: BLE001
        pass
    # Final fallback: gen1 key from settled row's own preserved fields
    return gen1_index.get(_gen1_open_key(settled))


def _build_settled_lookup_sets(settled_rows: List[Dict[str, Any]]) -> tuple:
    """(gen1_key_set, bid_key_set) for O(1) open->settled existence checks."""
    gen1_keys: set = set()
    bid_keys: set = set()
    for row in settled_rows:
        sk = str(row.get("settle_key") or "").strip()
        if sk:
            (gen1_keys if _sk_is_gen1(sk) else bid_keys).add(sk)
        try:
            bid_keys.add(_make_bet_id(row))
        except Exception:  # noqa: BLE001
            pass
        gen1_keys.add(_gen1_open_key(row))
    return gen1_keys, bid_keys


def _find_settled_for_open(
    open_row: Dict[str, Any],
    settled_gen1_keys: set,
    settled_bid_keys: set,
) -> bool:
    """True if *open_row* has a settled twin in the precomputed key sets."""
    if _gen1_open_key(open_row) in settled_gen1_keys:
        return True
    bid = str(open_row.get("bet_id") or "").strip()
    return bool(bid and bid in settled_bid_keys)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reconcile_clv_lifecycle(
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Cross-check the CLV ledger's open/settled row lifecycle.

    Returns:
      {
        "status":            "clean" | "drift" | "INSUFFICIENT_DATA",
        "clean":             bool,
        "n_open":            int,
        "n_settled":         int,
        "unsettled_open":    int,   # opens with no settled twin (expected during session)
        "settled_orphans":   int,   # settled rows with NO matching open row (drift signal)
        "orphan_details":    [ {"matchup":..., "sport":..., "settle_key":...}, ... ],
        "unsettled_details": [ {"matchup":..., "sport":..., "bet_id_or_key":...}, ... ],
        "note":              CALIBRATION_NOTE,
      }

    clean=True iff settled_orphans==0 (drift==0).
    Unsettled opens alone do NOT make clean=False.
    Empty ledger -> clean=True (status="clean").
    Missing ledger file -> status="INSUFFICIENT_DATA", clean=False.
    No $ / roi / pnl / profit key anywhere.
    Read-only: never mutates the ledger.
    """
    from scripts.platformkit.clv_ledger import DEFAULT_LEDGER
    target = Path(path) if path is not None else DEFAULT_LEDGER

    if not target.exists():
        result: Dict[str, Any] = {
            "status": "INSUFFICIENT_DATA",
            "clean": False,
            "n_open": 0,
            "n_settled": 0,
            "unsettled_open": 0,
            "settled_orphans": 0,
            "orphan_details": [],
            "unsettled_details": [],
            "reason": "ledger file missing: %s" % target,
            "note": CALIBRATION_NOTE,
        }
        _assert_no_banned_keys(result)
        return result

    rows = load_ledger(path=target)

    open_rows = [r for r in rows if r.get("status") == "open"]
    settled_rows = [r for r in rows if r.get("status") == "settled"]

    n_open = len(open_rows)
    n_settled = len(settled_rows)

    # Empty ledger -- trivially clean
    if n_open == 0 and n_settled == 0:
        result = {
            "status": "clean",
            "clean": True,
            "n_open": 0,
            "n_settled": 0,
            "unsettled_open": 0,
            "settled_orphans": 0,
            "orphan_details": [],
            "unsettled_details": [],
            "note": CALIBRATION_NOTE,
        }
        _assert_no_banned_keys(result)
        return result

    # Build open indexes for settled->open lookup
    gen1_idx, gen2_idx = _build_open_indexes(open_rows)

    settled_gen1_keys, settled_bid_keys = _build_settled_lookup_sets(settled_rows)

    # Pass 1: settled orphans (settled with no matching open row)
    orphan_details: List[Dict[str, Any]] = []
    for s in settled_rows:
        if _find_open_for_settled(s, gen1_idx, gen2_idx) is None:
            orphan_details.append({"matchup": str(s.get("matchup") or ""),
                "sport": str(s.get("sport") or ""),
                "settle_key": str(s.get("settle_key") or ""),
                "settled_at": str(s.get("settled_at") or "")})

    # Pass 2: unsettled opens (open with no settled twin)
    unsettled_details: List[Dict[str, Any]] = []
    for o in open_rows:
        has_settled = _find_settled_for_open(o, settled_gen1_keys, settled_bid_keys)
        if not has_settled:
            bid = str(o.get("bet_id") or "")
            unsettled_details.append({"matchup": str(o.get("matchup") or ""),
                "sport": str(o.get("sport") or ""),
                "bet_id_or_key": bid if bid else _gen1_open_key(o),
                "ts": str(o.get("ts") or "")})

    n_orphans = len(orphan_details)
    n_unsettled = len(unsettled_details)

    # clean = no settled orphans; unsettled opens are informational only
    is_clean = n_orphans == 0
    status = "clean" if is_clean else "drift"

    result = {
        "status": status,
        "clean": is_clean,
        "n_open": n_open,
        "n_settled": n_settled,
        "unsettled_open": n_unsettled,
        "settled_orphans": n_orphans,
        "orphan_details": orphan_details,
        "unsettled_details": unsettled_details,
        "note": CALIBRATION_NOTE,
    }
    _assert_no_banned_keys(result)
    return result


__all__ = [
    "reconcile_clv_lifecycle",
    "CALIBRATION_NOTE",
]
