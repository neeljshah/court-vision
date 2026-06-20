"""predict_service.predict_mounts -- the WAVE 3 prediction-contract read routes.

Factored out of predict_service.app to keep that module under the <=300 LOC
budget, mirroring the core_mounts / extra_mounts / ingame_mounts register(app)
pattern. The contracted face of the one model:

  * GET /api/predict/contract              -- the contract version + schema shapes.
  * GET /api/predict/{sport}/surface       -- the full per-sport market surface
        (phase-LABELLED ProbEstimates per game; a merge carries phase='merged',
        NEVER a silent average).
  * GET /api/predict/{sport}/{game_id}/uncertainty -- per-game phase-LABELLED
        estimates + intervals from HELD-OUT residuals only (null when unbacked).

register(app) MUST be called BEFORE app.py defines /api/predict/{sport} and
/api/predict/{sport}/{game_id}, so the literal-segment paths win the FastAPI
match over the {sport}/{game_id} captures (registration order matters).

All read-only, units/probability only, NO $ field; vs_close defaults UNPROVEN.
Each degrades to the store's honest 'unavailable' sentinel, never fabricates.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $-edge fabrication; reuse contracts/surface/store verbatim.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse

from predict_service.contracts import HONEST_NOTE

_STORE_OUT_DIR_ENV = "PREDICT_SERVICE_STORE_DIR"


def _store_out_dir() -> Optional[str]:
    """Resolve the store-root override env var, or None to use the store default."""
    val = os.environ.get(_STORE_OUT_DIR_ENV)
    return val or None


def register(app) -> None:  # noqa: ANN001
    """Mount the WAVE 3 prediction-contract read routes onto *app* (once, early)."""

    @app.get("/api/predict/contract")
    def predict_contract() -> Dict[str, Any]:  # noqa: ANN202
        """The prediction contract: version + a descriptive schema of the shapes.

        Lets a consumer pin the schema_version (1.1.0) and read the additive shapes
        (ProbEstimate / Provenance / Interval + EdgeRow.vs_close) without guessing.
        No data, no $ field -- pure contract metadata.
        """
        from predict_service.contracts import (  # noqa: PLC0415
            SCHEMA_VERSION as _SV,
            VALID_PHASES,
            VALID_VS_CLOSE,
        )
        return {
            "status": "ok",
            "schema_version": _SV,
            "phases": list(VALID_PHASES),
            "vs_close_values": list(VALID_VS_CLOSE),
            "vs_close_default": "UNPROVEN",
            "schemas": {
                "Provenance": ["model", "signal", "calibration", "phase"],
                "Interval": ["lo", "hi", "level", "method"],
                "ProbEstimate": ["label", "prob", "provenance", "interval",
                                 "market_type", "side"],
                "EdgeRow": ["game_id", "market_type", "side", "model_prob",
                            "market_prob", "ev", "tier", "book", "line",
                            "clv_is_proxy", "vs_close"],
            },
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
            "real_money_enabled": False,
        }

    @app.get("/api/predict/{sport}/surface")
    def predict_surface(sport: str) -> JSONResponse:  # noqa: ANN202
        """Full per-sport market surface: phase-LABELLED ProbEstimates per game.

        A merged pregame+ingame number is LABELLED phase='merged' (never a silent
        average); intervals (when present) are from held-out residuals only.
        Units/probability only, NO $ field. Degrades to the store status sentinel.
        """
        from predict_service.surface import build_surface  # noqa: PLC0415
        body = build_surface(sport, out_dir=_store_out_dir())
        return JSONResponse(body)

    @app.get("/api/predict/{sport}/{game_id}/uncertainty")
    def predict_uncertainty(sport: str, game_id: str) -> JSONResponse:  # noqa: ANN202
        """Per-game uncertainty: phase-LABELLED estimates + held-out-residual bands.

        Projects the one game out of the per-sport surface. An interval is present
        only when held-out residuals back it (leak-free); otherwise it is null --
        never a fabricated band. NO $ field. Missing game -> honest unavailable.
        """
        from predict_service.surface import build_surface  # noqa: PLC0415
        body = build_surface(sport, out_dir=_store_out_dir())
        if body.get("status") != "ok":
            return JSONResponse(body)
        game = next((g for g in body.get("games", [])
                     if g.get("game_id") == game_id), None)
        if game is None:
            return JSONResponse({
                "status": "unavailable",
                "sport": sport.lower(),
                "game_id": game_id,
                "reason": "game_id not in latest snapshot",
                "honest_note": HONEST_NOTE,
                "edge_claimed": False,
                "real_money_enabled": False,
            })
        return JSONResponse({
            "status": "ok",
            "sport": body.get("sport"),
            "schema_version": body.get("schema_version"),
            "game_id": game_id,
            "estimates": game.get("estimates", []),
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
            "real_money_enabled": False,
        })


__all__ = ["register"]
