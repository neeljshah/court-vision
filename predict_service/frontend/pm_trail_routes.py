"""predict_service.frontend.pm_trail_routes -- PM paper-trail browse + per-trade API.

Routes (W5-api-papertrail):
  GET /api/paper/pm/trail   -- Kalshi/Polymarket paper-trade list, paginated.
                               0 is_pm rows -> honest-empty with empty_reason.
  GET /api/paper/pm/trade/{bet_id} -- full detail for one PM trade.

HONESTY CONTRACT: executed=False always; no $/roi/profit; CLV null when no
close (never 0-fill); real_money_enabled=False always.

PARITY CONTRACT (WS5): parity_check(ledger_path) -> (ok, detail) asserts
route total_pm == raw ledger is_pm line count.  Route embeds _parity_ok stamp.

INVARIANTS: <=300 LOC; ASCII only; no secrets; no network.
"""
from __future__ import annotations

import json as _json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError(
        "predict_service.frontend.pm_trail_routes requires fastapi "
        "(pip install fastapi)."
    ) from exc

try:
    from scripts.platformkit.pm_trail_browse import (
        browse_pm_trail,
        best_pm_trades,
        trade_detail,
    )
    _BROWSE_OK = True
except Exception as _browse_exc:  # noqa: BLE001
    logger.warning("pm_trail_routes: pm_trail_browse import failed (%s)", _browse_exc)
    _BROWSE_OK = False
    browse_pm_trail = None  # type: ignore[assignment]
    best_pm_trades = None  # type: ignore[assignment]
    trade_detail = None  # type: ignore[assignment]

router = APIRouter()

_HONEST_NOTE = (
    "PM paper trail -- executed=False, channel=paper, no real orders. "
    "CLV = better-number-than-close (positive = good). "
    "null CLV = no closing line available (INSUFFICIENT_DATA). "
    "Venue filter: kalshi|polymarket only. No $ edge claimed. "
    "real_money_enabled=False."
)

_UNAVAILABLE: Dict[str, Any] = {
    "status": "unavailable",
    "reason": "pm_trail_browse failed to load",
    "trades": [],
    "count": 0,
    "real_money_enabled": False,
    "edge_claimed": False,
}


def _ledger_path(override: Optional[str]) -> Optional[Path]:
    return Path(override) if override else None


# ---------------------------------------------------------------------------
# Parity helpers (WS5 -- route count must match ledger is_pm count)
# ---------------------------------------------------------------------------

def _count_is_pm_lines(ledger: Path) -> int:
    """Count raw is_pm:true lines in the ledger JSONL without enrichment.

    Uses the raw file so the count is independent of the browse layer.
    Never raises -- missing file -> 0.
    """
    if not ledger.exists():
        return 0
    count = 0
    try:
        with ledger.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = _json.loads(line)
                    if bool(row.get("is_pm", False)):
                        count += 1
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    return count


def parity_check(ledger_path: Optional[Path] = None) -> Tuple[bool, str]:
    """Return (ok, detail): ok=True iff route total_pm == raw ledger is_pm count.

    Never raises; always returns (bool, str).
    """
    if not _BROWSE_OK or browse_pm_trail is None:
        return (False, "pm_trail_browse unavailable")
    from scripts.platformkit.pm_trail_browse import _DEFAULT_LEDGER  # noqa: PLC0415
    target = ledger_path or _DEFAULT_LEDGER
    raw_count = _count_is_pm_lines(target)
    try:
        route_total = browse_pm_trail(ledger_path, limit=1, offset=0).get("total_pm", -1)
    except Exception as exc:  # noqa: BLE001
        return (False, "browse_pm_trail raised: %s" % exc)
    if raw_count == route_total:
        return (True, "parity OK: raw=%d route_total_pm=%d" % (raw_count, route_total))
    return (
        False,
        "PARITY MISMATCH: raw is_pm=%d route total_pm=%d" % (raw_count, route_total),
    )


def assert_parity(ledger_path: Optional[Path] = None) -> None:
    """Raise AssertionError if route count != raw is_pm line count."""
    ok, detail = parity_check(ledger_path)
    assert ok, detail


# ---------------------------------------------------------------------------
# GET /api/paper/pm/trail
# ---------------------------------------------------------------------------

@router.get("/api/paper/pm/trail")
def pm_trail(
    venue: Optional[str] = Query(
        None,
        description=(
            "Filter by PM venue: 'kalshi' | 'polymarket'. "
            "Omit for all PM rows (sportsbook rows excluded)."
        ),
    ),
    result: Optional[str] = Query(
        None,
        description=(
            "Filter by outcome: 'win' | 'loss' | 'push' | 'void' | "
            "'open' | 'settled'."
        ),
    ),
    tier: Optional[str] = Query(
        None,
        description="Filter by evidence tier: 'A' | 'B' | 'C'.",
    ),
    offset: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(
        100, ge=1, le=500, description="Max rows per page (default 100)."
    ),
    best: bool = Query(
        False,
        description=(
            "When true, return the top-N 'best trades it would have made' "
            "ranked by tier + confidence (ignores offset / venue / result / "
            "tier filters)."
        ),
    ),
    top_n: int = Query(
        20, ge=1, le=200,
        description="Number of top trades to return when best=true.",
    ),
    ledger: Optional[str] = Query(
        None, description="Override ledger path (tests only)."
    ),
) -> JSONResponse:
    """PM paper-trade list (Kalshi/Polymarket only). Never raises."""
    if not _BROWSE_OK or browse_pm_trail is None or best_pm_trades is None:
        return JSONResponse(_UNAVAILABLE, status_code=503)

    lpath = _ledger_path(ledger)
    try:
        if best:
            data = best_pm_trades(lpath, top_n=top_n)
        else:
            data = browse_pm_trail(
                lpath,
                venue=venue,
                result=result,
                tier=tier,
                offset=offset,
                limit=limit,
            )
        data["real_money_enabled"] = False
        data["edge_claimed"] = False

        # Parity stamp: include raw is_pm line count so callers can self-verify.
        # This is the WS5 parity guarantee: route total_pm == raw ledger count.
        from scripts.platformkit.pm_trail_browse import _DEFAULT_LEDGER  # noqa: PLC0415
        _target = lpath or _DEFAULT_LEDGER
        raw_pm = _count_is_pm_lines(_target)
        data["_parity_raw_is_pm_lines"] = raw_pm
        route_total = data.get("total_pm", 0)
        data["_parity_ok"] = (raw_pm == route_total)

        # Honest-empty: when ledger genuinely has 0 is_pm rows, say why.
        if raw_pm == 0 and not best:
            data["empty_reason"] = (
                "No PM (Kalshi/Polymarket) rows in the ledger. "
                "PM rows are written by WS4 when a Kalshi or Polymarket "
                "market is targeted. Sportsbook-only games have is_pm=False "
                "and are excluded from this route."
            )

        return JSONResponse(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pm_trail_routes /api/paper/pm/trail error: %s", exc)
        return JSONResponse(
            {**_UNAVAILABLE, "reason": str(exc)}, status_code=503
        )


# ---------------------------------------------------------------------------
# GET /api/paper/pm/trade/{bet_id}
# ---------------------------------------------------------------------------

@router.get("/api/paper/pm/trade/{bet_id}")
def pm_trade_detail(
    bet_id: str,
    ledger: Optional[str] = Query(
        None, description="Override ledger path (tests only)."
    ),
) -> JSONResponse:
    """Full detail for one PM paper trade. status='not_found' if absent."""
    if not _BROWSE_OK or trade_detail is None:
        return JSONResponse(
            {**_UNAVAILABLE, "trade": None}, status_code=503
        )

    lpath = _ledger_path(ledger)
    try:
        data = trade_detail(bet_id, lpath)
        data["real_money_enabled"] = False
        data["edge_claimed"] = False
        return JSONResponse(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "pm_trail_routes /api/paper/pm/trade/%s error: %s", bet_id, exc
        )
        return JSONResponse(
            {**_UNAVAILABLE, "trade": None, "reason": str(exc)},
            status_code=503,
        )


__all__ = ["router", "parity_check", "assert_parity", "_count_is_pm_lines"]
