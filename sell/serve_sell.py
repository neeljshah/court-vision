"""sell.serve_sell -- FastAPI sell API (mountable, NOT api/main.py).

Exposes the sellable surface of the calibrated predictor behind HMAC key auth
and entitlement-plan gating.  Run with:

    uvicorn sell.serve_sell:app --port 8101

Endpoints
---------
GET /sell/health          -- liveness; no auth required; edge_claimed=false.
GET /sell/track_record    -- signed CLV + calibration TrackRecord.
                             Requires ANY valid key (free/pro/enterprise).
GET /sell/evidence        -- evidence pack manifest + governance verdicts.
                             Requires enterprise plan (evidence_pack feature).

Auth
----
Pass the API key in the Authorization header:
    Authorization: Bearer <key>
or in the query string:
    ?api_key=<key>

No secret -> all auth denied (DENY-safe default).

Honesty
-------
* edge_claimed=false on every response body.
* No dollar / ROI / P&L / $-edge field anywhere.
* honest_note on every response.
* Governance honesty linter runs over every signed track record before serving.

INVARIANTS: <=300 LOC; ASCII only; no secrets in code; no $-edge field;
mountable FastAPI sub-application only (no api/main.py edits);
never writes data/registry/; public deploy is HUMAN-GATED.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

import sell.authz as _authz
import sell.entitlements as _ent
import sell.usage_meter as _meter
from governance.honesty_linter import lint_obj
from sell.track_record import build_track_record, sign_track_record
from sell.signing import verify as _verify_sig, is_signed

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

_EDGE_CLAIMED: bool = False  # hard constant; never True
_HONEST_NOTE: str = (
    "Calibrated predictor with a CLV-tracked paper trail. "
    "No dollar edge is claimed. edge_claimed=false always. "
    "CLV is the honest yardstick; calibration (Brier/ECE) is the honest metric."
)

_REPO = Path(__file__).resolve().parent.parent
_ARTIFACT_PATH: Path = (
    _REPO / "data" / "frontend" / "sell" / "track_record.signed.json"
)

# --------------------------------------------------------------------------- #
# FastAPI app                                                                  #
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Sell API",
    description=(
        "Calibrated predictor sell surface. "
        "No dollar edge claimed. edge_claimed=false always."
    ),
    version="1.0.0",
    docs_url="/sell/docs",
    redoc_url=None,
)

# --------------------------------------------------------------------------- #
# Internal helpers                                                              #
# --------------------------------------------------------------------------- #


def _extract_key(
    authorization: Optional[str],
    api_key: Optional[str],
) -> Optional[str]:
    """Extract the raw API key from header or query param."""
    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    if api_key:
        return api_key.strip()
    return None


def _authenticate(
    authorization: Optional[str],
    api_key: Optional[str],
) -> Tuple[str, str]:
    """Return (tenant, plan) or raise HTTPException 401."""
    key = _extract_key(authorization, api_key)
    if not key:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_api_key",
                    "message": "Provide key via Authorization: Bearer <key> or ?api_key=",
                    "edge_claimed": _EDGE_CLAIMED},
        )
    result = _authz.verify_key(key)
    if result is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_api_key",
                    "message": "Key is invalid, forged, or expired.",
                    "edge_claimed": _EDGE_CLAIMED},
        )
    return result  # (tenant, plan)


def _require_feature(plan: str, feature: str) -> None:
    """Raise HTTPException 403 if plan does not grant feature."""
    if not _ent.allowed(plan, feature):
        min_plan = _ent.feature_min_plan(feature)
        raise HTTPException(
            status_code=403,
            detail={
                "error": "plan_insufficient",
                "feature": feature,
                "your_plan": plan,
                "required_plan": min_plan or "enterprise",
                "edge_claimed": _EDGE_CLAIMED,
                "honest_note": _HONEST_NOTE,
            },
        )


def _honest_envelope(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Inject honesty invariants; remove any stray $ keys (defence-in-depth)."""
    out = {k: v for k, v in payload.items()
           if not any(tok in k.lower() for tok in ("roi", "profit", "$edge",
                                                   "pnl", "bankroll", "dollar"))}
    out["edge_claimed"] = _EDGE_CLAIMED
    out["honest_note"] = _HONEST_NOTE
    return out


def _load_or_build_signed_track_record() -> Dict[str, Any]:
    """Load the on-disk signed artifact if present and valid; else build live."""
    if _ARTIFACT_PATH.exists():
        try:
            record = json.loads(_ARTIFACT_PATH.read_text(encoding="utf-8"))
            if is_signed(record) and _verify_sig(record):
                return record
            # Unsigned / tampered: fall through to live build.
        except Exception:
            pass
    # No artifact or stale -- build live (scoreboard may be empty; that is honest).
    tr = build_track_record()
    return sign_track_record(tr)


def _evidence_manifest() -> Dict[str, Any]:
    """Build the evidence pack manifest from known governance / eval artifacts."""
    artifacts = []

    def _probe(label: str, path: Path) -> None:
        artifacts.append({
            "label": label,
            "path": str(path.relative_to(_REPO)) if _REPO in path.parents or path == _REPO else str(path),
            "present": path.exists(),
        })

    _probe("governance_run_log", _REPO / "governance" / "run_governance.py")
    _probe("honesty_linter", _REPO / "governance" / "honesty_linter.py")
    _probe("realmoney_gate", _REPO / "governance" / "realmoney_gate.py")
    _probe("eval_gate", _REPO / "scripts" / "platformkit" / "eval_gate")
    _probe("track_record_signed", _ARTIFACT_PATH)

    return {
        "schema_version": "1.0.0",
        "description": (
            "Evidence pack: OOS calibration audit, walk-forward transcript, "
            "governance run artifacts, and methodology. "
            "All numbers are real or labelled unavailable."
        ),
        "artifacts": artifacts,
        "methodology_note": (
            "Leak-free + walk-forward + truncation-invariant OOS evaluation. "
            ">=2 independent corpora. Single-fold lifts are treated as artifacts. "
            "No dollar ROI is asserted anywhere."
        ),
        "edge_claimed": _EDGE_CLAIMED,
        "honest_note": _HONEST_NOTE,
    }


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


@app.get("/sell/health")
async def health() -> JSONResponse:
    """Liveness endpoint. No auth required. Always returns edge_claimed=false."""
    body = _honest_envelope({
        "status": "ok",
        "service": "sell_api",
        "schema_version": "1.0.0",
    })
    return JSONResponse(content=body, headers={"X-Edge-Claimed": "false"})


@app.get("/sell/track_record")
async def track_record(
    authorization: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None),
) -> JSONResponse:
    """Return the signed CLV + calibration TrackRecord.

    Requires any valid API key (free/pro/enterprise).
    The signed envelope is verified before serving; tampered records are rejected.
    """
    tenant, plan = _authenticate(authorization, api_key)
    _require_feature(plan, "paper_trail_read")

    _meter.record(tenant, "/sell/track_record")

    signed = _load_or_build_signed_track_record()

    # Honesty gate: lint before serving.
    verdict = lint_obj(signed)
    if not verdict["clean"]:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "honesty_lint_failed",
                "violations": verdict["violations"],
                "edge_claimed": _EDGE_CLAIMED,
            },
        )

    body = _honest_envelope(signed)
    return JSONResponse(content=body, headers={"X-Edge-Claimed": "false"})


@app.get("/sell/evidence")
async def evidence(
    authorization: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None),
) -> JSONResponse:
    """Return the evidence pack manifest and governance verdicts.

    Requires enterprise plan (evidence_pack feature).
    """
    tenant, plan = _authenticate(authorization, api_key)
    _require_feature(plan, "evidence_pack")

    _meter.record(tenant, "/sell/evidence")

    manifest = _evidence_manifest()

    # Honesty gate on the manifest itself.
    verdict = lint_obj(manifest)
    if not verdict["clean"]:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "honesty_lint_failed",
                "violations": verdict["violations"],
                "edge_claimed": _EDGE_CLAIMED,
            },
        )

    body = _honest_envelope(manifest)
    return JSONResponse(content=body, headers={"X-Edge-Claimed": "false"})


# --------------------------------------------------------------------------- #
# Mounted sell edge + paper-place routes (guarded include_router)             #
# GET /sell/v1/edges/{sport}          live_edges feature (pro+enterprise)     #
# GET /sell/v1/edges/{sport}/{game_id}                                        #
# POST /sell/v1/paper/place           paper_place feature (pro+enterprise)    #
# A load failure degrades these three paths to 503 sentinels rather than 404. #
# --------------------------------------------------------------------------- #
try:
    from sell.sell_edge_routes import router as _edge_router  # noqa: PLC0415

    app.include_router(_edge_router)
    import logging as _logging_se
    _logging_se.getLogger(__name__).info(
        "sell.serve_sell: sell_edge_routes mounted at /sell/v1/*")
except Exception as _edge_exc:  # noqa: BLE001
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "sell.serve_sell: sell_edge_routes could not be mounted -- "
        "/sell/v1/edges/* + /sell/v1/paper/place will return a degraded "
        "sentinel (%s: %s)", type(_edge_exc).__name__, _edge_exc,
    )

    @app.get("/sell/v1/edges/{sport}")
    async def _sell_edges_unavailable(sport: str) -> JSONResponse:  # noqa: ANN202
        return JSONResponse(
            {"status": "unavailable",
             "reason": "sell_edge_routes failed to load",
             "sport": sport, "games": [], "count": 0,
             "edge_claimed": False, "honest_note": _HONEST_NOTE},
            status_code=503,
        )

    @app.get("/sell/v1/edges/{sport}/{game_id}")
    async def _sell_game_unavailable(sport: str, game_id: str) -> JSONResponse:  # noqa: ANN202
        return JSONResponse(
            {"status": "unavailable",
             "reason": "sell_edge_routes failed to load",
             "sport": sport, "game_id": game_id,
             "edge_claimed": False, "honest_note": _HONEST_NOTE},
            status_code=503,
        )

    @app.post("/sell/v1/paper/place")
    async def _sell_place_unavailable() -> JSONResponse:  # noqa: ANN202
        return JSONResponse(
            {"status": "unavailable",
             "reason": "sell_edge_routes failed to load",
             "edge_claimed": False, "honest_note": _HONEST_NOTE},
            status_code=503,
        )


# --------------------------------------------------------------------------- #
# Note: public deploy is HUMAN-GATED. Never push origin automatically.        #
# To run locally:                                                              #
#   uvicorn sell.serve_sell:app --port 8101                                    #
# --------------------------------------------------------------------------- #
