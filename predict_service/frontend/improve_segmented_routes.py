"""predict_service.frontend.improve_segmented_routes -- GET /api/improve/ledger/segmented.

Per-market segmented improve-ledger DATA endpoint.  Reads
improve_ledger_segmented.jsonl (built by per_market_ledger.py), filters rows by
the `market` query param, and returns segmented rows with honest status.

Response shape:
  {
    status: "ok" | "unavailable",
    market: <str | null>,           # echoed from ?market=
    rows: [                         # filtered or all rows
      {market, ts, status, brier, ece, note}
    ],
    n_rows: <int>,
    n_promoted: <int>,              # SHIP-status rows (whole ledger, or per market)
    summary: {<market>: {n_rows, n_promoted, latest_brier, latest_status}},
    edge_claimed: false,
    honest_note: <str>
  }

Honesty invariants:
  - Missing file        -> status="unavailable" (never green)
  - Under-N per market  -> INSUFFICIENT_DATA surfaced verbatim (never fabricated)
  - n_promoted=0        -> explicit '0 ships' marker in honest_note
  - No $ / pnl / roi key anywhere
  - edge_claimed=False always

Mirrors improve_ledger_routes.py style.  <=300 LOC.  ASCII only.  Never raises.
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover
    raise ImportError("improve_segmented_routes requires fastapi.") from exc

logger = logging.getLogger(__name__)

router = APIRouter()

_REPO = pathlib.Path(__file__).resolve().parents[2]
_SEGMENTED_LEDGER_PATH = (
    _REPO / "data" / "frontend" / "improve_ledger_segmented.jsonl"
)

# Minimum settled rows per market before metrics are considered reliable.
_MIN_N_PER_MARKET: int = 10

_HONEST_NOTE = (
    "Calibration metrics only -- no $ / edge / profit claim. "
    "INSUFFICIENT_DATA is honest when a market has fewer than "
    "%d settled rows.  n_promoted counts only real SHIP-status "
    "promotions from the segmented ledger, never fabricated." % _MIN_N_PER_MARKET
)
_ZERO_SHIPS_NOTE = "0 ships -- ratchet has not promoted any version for this market yet. "


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_jsonl(path: pathlib.Path) -> List[Dict[str, Any]]:
    """Read all valid JSON objects from a JSONL file.  Never raises."""
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except json.JSONDecodeError:
                continue
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_segmented_routes: read error on %s: %s", path, exc)
    return rows


def _project_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Project one raw JSONL row to the public schema.  No banned keys."""
    readout = row.get("readout") or {}
    status = str(row.get("status", "UNKNOWN"))
    brier = readout.get("raw_brier")
    ece = readout.get("raw_ece")

    # Rows that have no readout and say INSUFFICIENT_DATA must surface that
    # verbatim with null metrics (never fabricated).
    if status == "INSUFFICIENT_DATA":
        brier = None
        ece = None

    return {
        "market":  str(row.get("market", "")),
        "ts":      row.get("ts"),
        "status":  status,
        "brier":   brier,
        "ece":     ece,
        "note":    str(row.get("note", "")),
    }


def _filter_rows(
    rows: List[Dict[str, Any]],
    market: Optional[str],
) -> List[Dict[str, Any]]:
    """Return rows matching market (case-insensitive) or all rows if market is None."""
    if not market:
        return rows
    needle = market.strip().lower()
    return [r for r in rows if str(r.get("market", "")).lower() == needle]


def _build_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build per-market summary dict from projected rows."""
    by_mkt: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        mkt = str(row.get("market", ""))
        by_mkt.setdefault(mkt, []).append(row)

    summary: Dict[str, Any] = {}
    for mkt in sorted(by_mkt):
        mkt_rows = by_mkt[mkt]
        n_promoted = sum(
            1 for r in mkt_rows if str(r.get("status", "")).upper() == "SHIP"
        )
        last = mkt_rows[-1] if mkt_rows else {}
        n_rows = len(mkt_rows)
        latest_status = str(last.get("status", "UNKNOWN"))
        # If too few rows, override latest_status to surface INSUFFICIENT_DATA.
        if n_rows < _MIN_N_PER_MARKET and latest_status not in (
            "INSUFFICIENT_DATA", "SHIP"
        ):
            latest_status = "INSUFFICIENT_DATA"

        summary[mkt] = {
            "n_rows":       n_rows,
            "n_promoted":   n_promoted,
            "latest_brier": last.get("brier"),
            "latest_status": latest_status,
        }
    return summary


def _count_promoted(rows: List[Dict[str, Any]]) -> int:
    """Count SHIP-status rows.  Case-insensitive."""
    return sum(1 for r in rows if str(r.get("status", "")).upper() == "SHIP")


def _is_thin(rows: List[Dict[str, Any]], market: Optional[str]) -> bool:
    """Return True when a specific market has fewer than _MIN_N_PER_MARKET rows."""
    if not market:
        return False
    needle = market.strip().lower()
    market_rows = [r for r in rows if str(r.get("market", "")).lower() == needle]
    return len(market_rows) < _MIN_N_PER_MARKET


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/api/improve/ledger/segmented")
def improve_ledger_segmented(
    market: Optional[str] = Query(
        default=None,
        description=(
            "Filter to a specific market key, e.g. 'nba:moneyline', "
            "'nba:total', 'prop:pts'.  Omit to return all markets."
        ),
    ),
    ledger_path: Optional[str] = Query(
        default=None,
        description="Override ledger path (test/dev use only).",
        include_in_schema=False,
    ),
) -> JSONResponse:
    """Per-market segmented improve-ledger rows.

    Reads improve_ledger_segmented.jsonl, optionally filters by `market`, and
    returns projected rows with calibration status.  Honest invariants:

    - Missing ledger      -> status=unavailable, no rows (never green)
    - Thin market (<N)    -> INSUFFICIENT_DATA in summary (never fabricated)
    - n_promoted=0        -> honest_note includes '0 ships' marker
    - No $ / pnl / roi   -> never emitted
    - edge_claimed=False  -> always
    """
    try:
        path = (
            pathlib.Path(ledger_path) if ledger_path else _SEGMENTED_LEDGER_PATH
        )

        # Guard: missing file -> unavailable, never green.
        if not path.exists():
            return JSONResponse({
                "status":       "unavailable",
                "market":       market,
                "rows":         [],
                "n_rows":       0,
                "n_promoted":   0,
                "summary":      {},
                "edge_claimed": False,
                "honest_note":  (
                    "improve_ledger_segmented.jsonl not found -- "
                    "the per-market builder has not run yet. " + _HONEST_NOTE
                ),
            })

        raw_rows = _read_jsonl(path)
        projected = [_project_row(r) for r in raw_rows]

        # Filter by market if provided.
        filtered = _filter_rows(projected, market)
        n_promoted_filtered = _count_promoted(filtered)

        # INSUFFICIENT_DATA override for thin markets.
        thin = _is_thin(projected, market)
        if thin:
            # Surface INSUFFICIENT_DATA on every row for this market so UI never
            # shows a "green" calibration for an under-N market.
            filtered = [
                dict(r, status="INSUFFICIENT_DATA", brier=None, ece=None)
                if str(r.get("status", "")) not in ("SHIP",)
                else r
                for r in filtered
            ]

        summary = _build_summary(projected)

        # Honest note: call out 0-ships explicitly.
        note = _HONEST_NOTE
        if n_promoted_filtered == 0:
            note = _ZERO_SHIPS_NOTE + note

        return JSONResponse({
            "status":       "ok",
            "market":       market,
            "rows":         filtered,
            "n_rows":       len(filtered),
            "n_promoted":   n_promoted_filtered,
            "summary":      summary,
            "edge_claimed": False,
            "honest_note":  note,
        })

    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_segmented_routes: unexpected error: %s", exc)
        return JSONResponse({
            "status":       "unavailable",
            "market":       market,
            "rows":         [],
            "n_rows":       0,
            "n_promoted":   0,
            "summary":      {},
            "edge_claimed": False,
            "honest_note":  "unexpected error; ledger unavailable. " + _HONEST_NOTE,
        })


__all__ = ["router"]
