"""predict_service.frontend.improve_sharpening_routes -- GET /api/improve/sharpening.

Derived sharpening-observability view: wires improvement_trend.compute_trends,
coverage_map.build_coverage_map, and ledger_reconcile.reconcile into one endpoint.

Response: {status, enabled, edge_claimed:false, trends, coverage, reconcile, honest_note}
  trends.<market>: {status, monotone_improving, regression_flag, deltas, n_data_cycles}
  coverage: {summary, gaps:[{family,aspect}], ledger_present, vs_close, note}
  reconcile: {status, n_drift, drift_flags, clean, note}

INVARIANTS: read-only; no $ / pnl / roi / profit key; enabled mirrors sentinel;
missing ledger -> unavailable (never green); untried cells = honest gaps;
daemon SHIP w/o graded row -> drift flag; ASCII; never raises to caller.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover
    raise ImportError("improve_sharpening_routes requires fastapi.") from exc

logger = logging.getLogger(__name__)

router = APIRouter()

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_LEDGER = _REPO / "data" / "frontend" / "improve_ledger_segmented.jsonl"

_HONEST_NOTE = (
    "Calibration metrics only -- no $ / edge / profit claim. "
    "monotone_improving reflects shrinking Brier across cycles, NOT market edge. "
    "INSUFFICIENT_DATA is honest when < 2 graded cycles exist for a market. "
    "untried cells are honest gaps, not failures. "
    "vs_close UNPROVEN until CLV 2nd corpus is wired."
)


# ---------------------------------------------------------------------------
# Helpers (import-safe wrappers so missing deps -> graceful degradation)
# ---------------------------------------------------------------------------


def _pipeline_enabled() -> bool:
    """True only when the human-managed PIPELINE_ENABLED sentinel exists."""
    try:
        from scripts.platformkit.improve.pipeline_flag import (  # noqa: PLC0415
            pipeline_enabled,
        )
        return bool(pipeline_enabled())
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_sharpening: pipeline_flag import error: %s", exc)
        return False


def _ledger_exists(ledger_path: Optional[Path] = None) -> bool:
    p = ledger_path if ledger_path else _DEFAULT_LEDGER
    try:
        return Path(p).exists()
    except Exception:  # noqa: BLE001
        return False


def _compute_trends(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Call improvement_trend.compute_trends; return {} on import/IO error."""
    try:
        from scripts.platformkit.improve.improvement_trend import (  # noqa: PLC0415
            compute_trends,
        )
        return compute_trends(ledger_path=ledger_path) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_sharpening: compute_trends error: %s", exc)
        return {}


def _build_coverage(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Call coverage_map.build_coverage_map; return minimal stub on error."""
    try:
        from scripts.platformkit.improve.coverage_map import (  # noqa: PLC0415
            build_coverage_map,
        )
        return build_coverage_map(ledger_path=ledger_path) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_sharpening: coverage_map error: %s", exc)
        return {}


def _reconcile(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Call ledger_reconcile.reconcile; return INSUFFICIENT_DATA stub on error."""
    try:
        from scripts.platformkit.improve.ledger_reconcile import (  # noqa: PLC0415
            reconcile,
            CALIBRATION_NOTE,
        )
        return reconcile(graded_path=ledger_path) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_sharpening: reconcile error: %s", exc)
        return {
            "status": "INSUFFICIENT_DATA",
            "n_ship_rows": 0,
            "n_graded_rows": 0,
            "n_matched": 0,
            "n_drift": 0,
            "drift_flags": [],
            "matched": [],
            "clean": False,
            "note": "calibration != edge: import error; reconcile unavailable",
        }


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _build_trends_block(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Reproject raw compute_trends output into a compact, no-banned-key block."""
    out: Dict[str, Any] = {}
    for mkt, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "INSUFFICIENT_DATA"))
        item: Dict[str, Any] = {
            "status": status,
            "n_data_cycles": entry.get("n_data_cycles", 0),
            "n_excluded": entry.get("n_excluded", 0),
            "note": entry.get("note", ""),
        }
        if status == "ok":
            item["monotone_improving"] = entry.get("monotone_improving")
            item["regression_flag"] = entry.get("regression_flag")
            item["deltas"] = entry.get("deltas")
            item["briers"] = entry.get("briers")
        else:
            item["monotone_improving"] = None
            item["regression_flag"] = None
            item["deltas"] = None
            item["reason"] = entry.get("reason", "INSUFFICIENT_DATA")
        out[mkt] = item
    return out


def _build_coverage_block(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract gap list (untried cells) and summary from coverage_map output."""
    if not raw:
        return {
            "summary": {},
            "gaps": [],
            "ledger_present": False,
            "vs_close": "UNPROVEN",
            "note": "coverage_map unavailable",
        }
    cells: List[Dict[str, Any]] = raw.get("cells", [])
    gaps = [
        {"family": c["family"], "aspect": c["aspect"]}
        for c in cells
        if isinstance(c, dict) and c.get("status") == "untried"
    ]
    return {
        "summary": raw.get("summary", {}),
        "gaps": gaps,
        "ledger_present": raw.get("ledger_present", False),
        "vs_close": raw.get("vs_close", "UNPROVEN"),
        "note": raw.get("note", ""),
    }


def _build_reconcile_block(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Reproject reconcile output; keep only non-banned fields."""
    if not raw:
        return {
            "status": "INSUFFICIENT_DATA",
            "n_drift": 0,
            "drift_flags": [],
            "clean": False,
            "note": "reconcile unavailable",
        }
    return {
        "status": raw.get("status", "INSUFFICIENT_DATA"),
        "n_ship_rows": raw.get("n_ship_rows", 0),
        "n_graded_rows": raw.get("n_graded_rows", 0),
        "n_matched": raw.get("n_matched", 0),
        "n_drift": raw.get("n_drift", 0),
        "drift_flags": raw.get("drift_flags", []),
        "clean": bool(raw.get("clean", False)),
        "note": raw.get("note", ""),
    }


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


_UNAVAILABLE_RESPONSE = {
    "status": "unavailable",
    "enabled": False,
    "edge_claimed": False,
    "trends": {},
    "coverage": {
        "summary": {},
        "gaps": [],
        "ledger_present": False,
        "vs_close": "UNPROVEN",
        "note": "ledger absent",
    },
    "reconcile": {
        "status": "INSUFFICIENT_DATA",
        "n_ship_rows": 0,
        "n_graded_rows": 0,
        "n_matched": 0,
        "n_drift": 0,
        "drift_flags": [],
        "clean": False,
        "note": "ledger absent; reconcile unavailable",
    },
    "honest_note": _HONEST_NOTE,
}


@router.get("/api/improve/sharpening")
def improve_sharpening(
    ledger: Optional[str] = None,
) -> JSONResponse:
    """Derived sharpening-observability view.

    Unifies improvement_trend, coverage_map, and ledger_reconcile into one
    read-only endpoint. Missing ledger -> status=unavailable, edge_claimed=false.
    No $ / pnl / roi field is ever emitted.  enabled mirrors the human sentinel.
    Never raises to the caller; any unexpected error returns unavailable.
    """
    try:
        enabled = _pipeline_enabled()
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_sharpening: pipeline_enabled error: %s", exc)
        enabled = False

    try:
        ledger_path: Optional[Path] = Path(ledger) if ledger else None
        present = _ledger_exists(ledger_path)

        # Guard: if ledger is absent, short-circuit to unavailable (never green).
        if not present:
            resp = dict(_UNAVAILABLE_RESPONSE)
            resp["enabled"] = enabled
            return JSONResponse(resp)

        # Compute derived blocks (each helper never raises).
        raw_trends = _compute_trends(ledger_path)
        raw_coverage = _build_coverage(
            _DEFAULT_LEDGER if not ledger_path else ledger_path
        )
        raw_reconcile = _reconcile(
            _DEFAULT_LEDGER if not ledger_path else ledger_path
        )

        trends_block = _build_trends_block(raw_trends)
        coverage_block = _build_coverage_block(raw_coverage)
        reconcile_block = _build_reconcile_block(raw_reconcile)

        return JSONResponse({
            "status": "ok",
            "enabled": enabled,
            "edge_claimed": False,
            "trends": trends_block,
            "coverage": coverage_block,
            "reconcile": reconcile_block,
            "honest_note": _HONEST_NOTE,
        })
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_sharpening: unexpected error: %s", exc)
        resp = dict(_UNAVAILABLE_RESPONSE)
        resp["enabled"] = enabled
        return JSONResponse(resp)


__all__ = ["router"]
