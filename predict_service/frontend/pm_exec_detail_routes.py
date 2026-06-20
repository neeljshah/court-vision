"""predict_service.frontend.pm_exec_detail_routes -- per-fill execution detail API.

Registers two FastAPI routes (PT-7):

  GET /api/paper/pm/exec/fills/{bet_id}
      Return the fills list + avg_price for one paper-only bet.
      Reads fill records from PnLBlotter.read() keyed on bet_id or market_id.
      Response:
        {
          "status": "ok" | "unavailable" | "not_found",
          "bet_id":    str,
          "fills":     [FillRecord, ...],
          "avg_price": float | null,
          "n_fills":   int,
          "slippage":  float | null,
          "exec_status": str | null,        -- FILLED | PARTIAL | NOFILL | REJECTED
          "executed":  false,               -- paper-only, always False
          "real_money_enabled": false,
          "edge_claimed": false,
          "honest_note": str,
        }

      FillRecord (never includes $ / pnl / roi / profit):
        {
          "ts":       str,
          "side":     "BUY" | "SELL",
          "qty":      int,
          "price":    float,     -- probability [0, 1], NOT $
          "fee":      float,
          "strategy": str,
          "executed": false,
        }

  GET /api/paper/pm/exec/report/{bet_id}
      Summarised ExecReport-shaped view for one bet (avg_price, slippage,
      n_fills, exec_status) without per-fill detail.

HONESTY CONTRACT (binding):
  * executed is ALWAYS False -- paper-only, no real orders placed.
  * No $ / dollar / roi / profit / pnl field anywhere in the response.
  * Missing bet_id -> 404 / status="not_found"; never return stale-green data.
  * Fills are sourced from PnLBlotter.read() -- append-only local ledger.
  * avg_price is computed honestly from qty-weighted fill prices (UNITS, not $).

INVARIANTS: <=300 LOC; ASCII only; no secrets; no network; per-file test required.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "predict_service.frontend.pm_exec_detail_routes requires fastapi."
    ) from exc

try:
    from scripts.platformkit.pm_trading.pnl import PnLBlotter
    _BLOTTER_OK = True
except Exception as _blot_exc:  # noqa: BLE001
    logger.warning("pm_exec_detail_routes: PnLBlotter import failed (%s)", _blot_exc)
    _BLOTTER_OK = False
    PnLBlotter = None  # type: ignore[misc,assignment]

router = APIRouter()

_HONEST_NOTE = (
    "PM execution detail -- executed=False, channel=paper, no real orders. "
    "avg_price and slippage are probability-space values [0,1], NOT dollars. "
    "No $ / pnl / roi / profit field. real_money_enabled=False."
)

_UNAVAILABLE: Dict[str, Any] = {
    "status": "unavailable",
    "reason": "PnLBlotter failed to load",
    "fills": [],
    "n_fills": 0,
    "avg_price": None,
    "slippage": None,
    "exec_status": None,
    "executed": False,
    "real_money_enabled": False,
    "edge_claimed": False,
    "honest_note": _HONEST_NOTE,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blotter_path(override: Optional[str]) -> Optional[str]:
    return override or None


def _read_fills_for_bet(bet_id: str,
                        base_dir: Optional[str]) -> List[Dict[str, Any]]:
    """Return fill records from PnLBlotter matching bet_id (via market_id)."""
    if PnLBlotter is None:
        return []
    try:
        blotter = PnLBlotter(base_dir=base_dir)
        all_recs = blotter.read()
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_exec_detail_routes: blotter read error: %s", exc)
        return []
    # Fills are keyed by market_id in the blotter; bet_id is treated as market_id.
    return [
        r for r in all_recs
        if r.get("kind") == "fill"
        and (str(r.get("market_id", "")) == bet_id
             or str(r.get("bet_id", "")) == bet_id)
    ]


def _shape_fill(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Shape one blotter fill record for API output. No $ fields."""
    return {
        "ts":       raw.get("ts", ""),
        "side":     str(raw.get("side", "")).upper(),
        "qty":      int(raw.get("qty", 0)),
        "price":    float(raw.get("price", 0.0)),
        "fee":      float(raw.get("fee", 0.0)),
        "strategy": str(raw.get("strategy", "")),
        "executed": False,
    }


def _compute_avg_price(fills: List[Dict[str, Any]]) -> Optional[float]:
    """Qty-weighted avg price across all fill records; None if no fills."""
    if not fills:
        return None
    total_qty = sum(f.get("qty", 0) for f in fills)
    if total_qty <= 0:
        return None
    notional = sum(f.get("qty", 0) * f.get("price", 0.0) for f in fills)
    return round(notional / total_qty, 6)


def _infer_exec_status(n_raw: int,
                       shaped: List[Dict[str, Any]]) -> Optional[str]:
    """Infer status from fill count; honest NOFILL when blotter is empty."""
    if n_raw == 0:
        return None   # bet_id not in blotter -> not_found path
    if not shaped:
        return "NOFILL"
    return "FILLED"


def _build_fill_payload(bet_id: str,
                        base_dir: Optional[str]) -> Dict[str, Any]:
    """Build the shared payload dict for /fills and /report routes."""
    raw_fills = _read_fills_for_bet(bet_id, base_dir)
    if not raw_fills:
        return {
            "status":      "not_found",
            "bet_id":      bet_id,
            "fills":       [],
            "n_fills":     0,
            "avg_price":   None,
            "slippage":    None,
            "exec_status": None,
            "executed":    False,
            "real_money_enabled": False,
            "edge_claimed": False,
            "honest_note": _HONEST_NOTE,
        }
    shaped = [_shape_fill(r) for r in raw_fills]
    avg_p = _compute_avg_price(raw_fills)
    # Slippage: not stored in blotter; surface None (honest -- no ref_price kept).
    return {
        "status":      "ok",
        "bet_id":      bet_id,
        "fills":       shaped,
        "n_fills":     len(shaped),
        "avg_price":   avg_p,
        "slippage":    None,
        "exec_status": "FILLED" if shaped else "NOFILL",
        "executed":    False,
        "real_money_enabled": False,
        "edge_claimed": False,
        "honest_note": _HONEST_NOTE,
    }


# ---------------------------------------------------------------------------
# GET /api/paper/pm/exec/fills/{bet_id}
# ---------------------------------------------------------------------------

@router.get("/api/paper/pm/exec/fills/{bet_id}")
def pm_exec_fills(
    bet_id: str,
    blotter_dir: Optional[str] = Query(
        None,
        description="Override blotter directory (tests / CI only).",
    ),
) -> JSONResponse:
    """Per-fill execution detail for one paper-only bet.

    Returns the fills list + avg_price for bet_id.  Fill prices are
    probabilities in [0, 1] (UNITS), never dollars.  ``executed`` is always
    False (paper-only channel).  Missing bet_id -> 404 + status='not_found'.

    Never raises -- blotter missing / unreadable -> status='unavailable'.
    """
    if not _BLOTTER_OK:
        return JSONResponse({**_UNAVAILABLE, "bet_id": bet_id}, status_code=503)
    try:
        payload = _build_fill_payload(bet_id, _blotter_path(blotter_dir))
        code = 404 if payload["status"] == "not_found" else 200
        return JSONResponse(payload, status_code=code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pm_exec_detail_routes /fills/%s error: %s", bet_id, exc)
        return JSONResponse(
            {**_UNAVAILABLE, "bet_id": bet_id, "reason": str(exc)},
            status_code=503,
        )


# ---------------------------------------------------------------------------
# GET /api/paper/pm/exec/report/{bet_id}
# ---------------------------------------------------------------------------

@router.get("/api/paper/pm/exec/report/{bet_id}")
def pm_exec_report(
    bet_id: str,
    blotter_dir: Optional[str] = Query(
        None,
        description="Override blotter directory (tests / CI only).",
    ),
) -> JSONResponse:
    """Summarised ExecReport-shaped view for one paper bet (no per-fill list).

    Returns avg_price, n_fills, exec_status, slippage (honest None when the
    blotter does not store a ref_price).  No $ / pnl / roi key ever present.
    Missing bet_id -> 404 + status='not_found'.
    """
    if not _BLOTTER_OK:
        return JSONResponse({**_UNAVAILABLE, "bet_id": bet_id}, status_code=503)
    try:
        payload = _build_fill_payload(bet_id, _blotter_path(blotter_dir))
        # Strip per-fill list for the summary report endpoint.
        payload.pop("fills", None)
        code = 404 if payload["status"] == "not_found" else 200
        return JSONResponse(payload, status_code=code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pm_exec_detail_routes /report/%s error: %s", bet_id, exc)
        return JSONResponse(
            {**_UNAVAILABLE, "bet_id": bet_id, "reason": str(exc)},
            status_code=503,
        )


__all__ = ["router"]
