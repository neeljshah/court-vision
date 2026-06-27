"""frontend.status_routes -- read-only self-improve + parity JSON endpoints.

Surfaces two existing internal sources over HTTP so the CourtVision P6 dashboard
can render the ratchet / self-improvement panel and the cross-sport parity grid
without recomputing anything:

  GET /api/improve/status
      The recalibration ratchet FSM state (improve.ratchet_state) plus the
      versioned calibration registry (improve.registry) per kind. A fresh box
      with no calib artifacts yet degrades to status='idle' with empty kinds --
      NEVER a fabricated number.

  GET /api/parity
      The cross-sport coverage / loop-health grid (scripts.platformkit
      .parity_matrix.build_parity_matrix) serialized to JSON: per sport x
      {census, manifest, feature_spec} -> {status, detail}. Pure offline read.
      Any failure -> status='unavailable' sentinel (the panel detects the gap).

  GET /api/clv/over-time
      The MULTI-GAME aggregate CLV/calibration read (scripts.platformkit.ingame
      .inplay_aggregate_grade.aggregate_grade): the per-game CLV-over-time series
      (ordered by settle time) + the honest pooled verdict (BEAT / MATCH / BEHIND /
      INSUFFICIENT_DATA). MEASUREMENT-ONLY -- CLV is probability space, NEVER $; one
      game is variance so the honest default is INSUFFICIENT_DATA. Any failure ->
      status='unavailable' with an empty series (the panel degrades, never fabricates).

Both endpoints NEVER raise: a missing module / torn file / build error always
collapses to an explicit unavailable/idle sentinel the UI degrades on. No $
field is ever emitted -- this is calibrated decision-support observability only.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.status_routes requires fastapi.") from exc

from predict_service.honest_route import honest_route

logger = logging.getLogger(__name__)

router = APIRouter()

# The calibration kinds the ratchet may version. Kept in one place; an absent
# kind simply reports current=null (no artifact promoted yet).
_KINDS = ("nba_winprob", "mlb_winprob", "soccer_totals", "soccer_intl", "tennis")

HONEST_NOTE = (
    "Calibrated decision-support only. No $ edge is claimed. The ratchet only "
    "ships a recalibration when EVERY gate passes (a partial pass is a REJECT)."
)


def _ratchet_block() -> Dict[str, Any]:
    """The persisted ratchet FSM state, or an idle sentinel."""
    try:
        from improve.ratchet_state import load_state  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        logger.warning("status_routes: ratchet import failed: %s", exc)
        return {"status": "unavailable", "reason": "ratchet module unavailable",
                "state": "idle"}
    try:
        st = load_state()
        d = st.to_dict()
        d["status"] = "ok"
        return d
    except Exception as exc:  # noqa: BLE001 -- load_state is guarded; belt+braces
        logger.warning("status_routes: load_state failed: %s", exc)
        return {"status": "idle", "state": "idle",
                "reason": "no ratchet state persisted yet"}


def _registry_block() -> List[Dict[str, Any]]:
    """Per-kind current calibration version (or null) from the registry."""
    out: List[Dict[str, Any]] = []
    try:
        from improve import registry  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        logger.warning("status_routes: registry import failed: %s", exc)
        return out
    for kind in _KINDS:
        entry: Dict[str, Any] = {"kind": kind, "current_version": None,
                                 "versions": []}
        try:
            entry["versions"] = list(registry.list_versions(kind))
        except Exception as exc:  # noqa: BLE001
            logger.debug("status_routes: list_versions(%s) failed: %s", kind, exc)
        try:
            art = registry.current(kind)
            if art is not None:
                entry["current_version"] = getattr(art, "version", None)
                entry["created_at"] = getattr(art, "created_at", None)
        except Exception as exc:  # noqa: BLE001
            logger.debug("status_routes: current(%s) failed: %s", kind, exc)
        out.append(entry)
    return out


@router.get("/api/improve/status")
@honest_route(extra={"ratchet": {"state": "idle"}, "kinds": []})
def improve_status() -> JSONResponse:
    """Ratchet FSM state + per-kind calibration registry. Never raises."""
    ratchet = _ratchet_block()
    kinds = _registry_block()
    promoted = sum(1 for k in kinds if k.get("current_version"))
    body = {
        "status": ratchet.get("status", "ok"),
        "ratchet": ratchet,
        "kinds": kinds,
        "n_kinds": len(kinds),
        "n_promoted": promoted,
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    }
    return JSONResponse(body)


def _parity_to_dict() -> Dict[str, Any]:
    from scripts.platformkit.parity_matrix import (  # noqa: PLC0415
        build_parity_matrix, is_green, DIMENSIONS,
    )
    rows = build_parity_matrix()
    sports: List[Dict[str, Any]] = []
    for r in rows:
        cells = {
            dim: {"status": r.cells[dim].status, "detail": r.cells[dim].detail}
            for dim in DIMENSIONS if dim in r.cells
        }
        sports.append({"sport": r.sport, "cells": cells})
    return {
        "status": "ok",
        "green": bool(is_green(rows)),
        "dimensions": list(DIMENSIONS),
        "sports": sports,
        "honest_note": (
            "Fail-closed coverage grid: a PRESENT-but-broken cell is red and "
            "fails the gate; a not-yet-built cell is n/a and does not."
        ),
        "edge_claimed": False,
    }


def _clv_over_time_block() -> Dict[str, Any]:
    """Multi-game aggregate CLV-over-time series + pooled verdict. Measurement-only.

    Reuses inplay_aggregate_grade.aggregate_grade (which reuses the leak-free per-game
    P1 CLV replay). Surfaces ONLY numbers in probability space -- no $ field. A fresh
    box with one/few games degrades to INSUFFICIENT_DATA with whatever short series
    exists; an import/build error -> status='unavailable' with an empty series.
    """
    try:
        from scripts.platformkit.ingame.inplay_aggregate_grade import (  # noqa: PLC0415
            aggregate_grade,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("status_routes: aggregate grader import failed: %s", exc)
        return {"status": "unavailable", "reason": "aggregate grader unavailable",
                "pool_verdict": "INSUFFICIENT_DATA", "clv_over_time": [],
                "units": "probability", "edge_claimed": False}
    try:
        pool = aggregate_grade()
        return {
            "status": "ok",
            "pool_verdict": pool.get("pool_verdict", "INSUFFICIENT_DATA"),
            "n_games": pool.get("n_games", 0),
            "n_settled_games": pool.get("n_settled_games", 0),
            "total_ticks_scored": pool.get("total_ticks_scored", 0),
            "pooled_mean_clv": pool.get("pooled_mean_clv", 0.0),
            "clv_ci95": pool.get("clv_ci95", [0.0, 0.0]),
            "clv_over_time": pool.get("clv_over_time", []),
            "vs_close": pool.get("vs_close", "UNPROVEN"),
            "label": "measurement only -- CLV/calibration in probability space, no currency",
            "units": "probability",
            "edge_claimed": False,
        }
    except Exception as exc:  # noqa: BLE001 -- pure offline read; belt + braces
        logger.warning("status_routes: aggregate_grade failed: %s", exc)
        return {"status": "unavailable",
                "reason": "aggregate grade failed (%s)" % type(exc).__name__,
                "pool_verdict": "INSUFFICIENT_DATA", "clv_over_time": [],
                "units": "probability", "edge_claimed": False}


@router.get("/api/clv/over-time")
@honest_route(extra={"pool_verdict": "INSUFFICIENT_DATA", "clv_over_time": [],
                     "units": "probability"})
def clv_over_time() -> JSONResponse:
    """Multi-game aggregate CLV-over-time series + pooled verdict. Measurement-only; no $."""
    return JSONResponse(_clv_over_time_block())


@router.get("/api/parity")
@honest_route(extra={"dimensions": [], "sports": [], "green": False})
def parity() -> JSONResponse:
    """Cross-sport coverage / loop-health grid as JSON. Never raises."""
    try:
        return JSONResponse(_parity_to_dict())
    except Exception as exc:  # noqa: BLE001 -- pure offline read; belt + braces
        logger.warning("status_routes /api/parity failed: %s", exc)
        return JSONResponse(
            {"status": "unavailable",
             "reason": "parity build failed (%s)" % type(exc).__name__,
             "dimensions": [], "sports": [], "green": False,
             "edge_claimed": False},
            status_code=503,
        )


__all__ = ["router"]
