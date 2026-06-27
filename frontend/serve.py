"""frontend.serve -- minimal FastAPI app for the predict-service / paper-trail front end.

Distinct from scripts/platformkit/frontend/serve.py (port 8098).
This app serves the React panel's API surface: /health and the paper-trail
endpoints (/api/paper/trail, /api/paper/clv) via paper_routes.

Port 8099 by default (override FRONTEND_SERVE_PORT). Never collides with
api/main.py (8077) or scripts.platformkit.frontend.serve (8098).

Run: python -m frontend.serve  OR  uvicorn frontend.serve:app

INVARIANTS: build only under frontend/; <=300 LOC; ASCII-only; no secrets.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "frontend.serve requires fastapi (pip install fastapi uvicorn)."
    ) from exc

logger = logging.getLogger(__name__)

DEFAULT_PORT = int(os.environ.get("FRONTEND_SERVE_PORT", "8099"))

app = FastAPI(
    title="CourtVision predict-service / paper-trail API",
    description=(
        "Calibrated decision-support only. No $ edge is claimed. "
        "Paper trail endpoints: /api/paper/trail and /api/paper/clv."
    ),
)


@app.get("/health")
def health() -> Dict[str, Any]:
    """Liveness probe."""
    return {"status": "ok"}


# -- Guarded router mount: paper-trail endpoints.
# A failure here (bad import, syntax error, etc.) is caught and logged;
# the rest of serve.py continues to boot so /health always responds.
try:
    from frontend.paper_routes import router as _paper_router  # noqa: PLC0415
    app.include_router(_paper_router)
    logger.info("frontend.serve: paper_routes mounted at /api/paper/*")
except Exception as _paper_exc:  # noqa: BLE001
    logger.warning(
        "frontend.serve: paper_routes could not be mounted -- "
        "/api/paper/* will return 404 (%s: %s)",
        type(_paper_exc).__name__,
        _paper_exc,
    )

    # Expose a degraded sentinel so the React panel can detect the gap.
    @app.get("/api/paper/trail")
    def _paper_trail_unavailable() -> JSONResponse:  # noqa: ANN202
        return JSONResponse(
            {"status": "unavailable",
             "reason": "paper_routes failed to load",
             "trail": [], "count": 0},
            status_code=503,
        )

    @app.get("/api/paper/clv")
    def _paper_clv_unavailable() -> JSONResponse:  # noqa: ANN202
        return JSONResponse(
            {"status": "unavailable",
             "reason": "paper_routes failed to load",
             "n_bets": 0},
            status_code=503,
        )


# -- Additional guarded router mounts (closes the M1 stopgap gap) -------------
# The M1 frontend.serve historically mounted ONLY paper_routes, so the
# self-improve / parity / clv-over-time observability surface and the autonomy,
# quant and gateway faces 404'd here even though the routers were fully built
# (they ARE mounted by the canonical predict_service.app on the same port). To
# keep both entry points honest and avoid silent 404s, mount every router that
# imports cleanly. Each mount is independently guarded: a bad import is logged
# and skipped (never sinks the app, never green-on-missing). NO router is mounted
# unless it imports successfully. All faces are CALIBRATION/units only, no $.
def _mount_extra_routers() -> None:
    """Mount the built-but-previously-unmounted routers (each guarded)."""
    # (module attribute path, import target) -- import target is "<mod>:router".
    _specs = (
        ("status", "frontend.status_routes"),       # /api/improve/status,/api/parity,/api/clv/over-time
        ("autonomy", "frontend.autonomy_routes"),   # /api/improve/timeline,/api/ops/autonomy
        ("catalog", "frontend.catalog_routes"),     # /api/catalog,/api/status.all_honest
        ("intel", "frontend.intel_routes"),         # /api/intel/{query}
        ("quant", "frontend.quant_routes"),         # /api/quant/*
        ("bestbets", "frontend.bestbets_routes"),   # /api/v1/bestbets/*
    )
    import importlib  # noqa: PLC0415
    for name, modpath in _specs:
        try:
            mod = importlib.import_module(modpath)
            app.include_router(mod.router)
            logger.info("frontend.serve: %s mounted (%s)", name, modpath)
        except Exception as exc:  # noqa: BLE001 -- a bad router never sinks the app
            logger.warning(
                "frontend.serve: %s could not be mounted -- its paths will 404 "
                "(%s: %s)", name, type(exc).__name__, exc,
            )


_mount_extra_routers()


# -- Progress ledger route (honest "getting better" data spine) ---------------
# GET /api/progress -> latest snapshot + the time series + the honest
# "model static until self-improve enabled" flag. MEASUREMENT-ONLY aggregation of
# the existing artifacts (funnel verdicts + backlog + parity + sentinel); it never
# trains/ships/flips a flag and emits NO $ field. Guarded: a bad import logs and
# falls back to an explicit unavailable sentinel (never green-on-missing).
try:
    from scripts.platformkit.progress.progress_ledger import (  # noqa: PLC0415
        progress_payload,
    )

    @app.get("/api/progress")
    def api_progress() -> JSONResponse:  # noqa: ANN202
        """Latest progress snapshot + time series + the model-static flag.

        PROGRESS = validation coverage / completeness / a proven-READY-but-INERT
        improvement engine. The model is STATIC until a human enables the loop;
        engine_enabled mirrors the PIPELINE_ENABLED sentinel (False here). No $.
        """
        try:
            return JSONResponse(progress_payload())
        except Exception as exc:  # noqa: BLE001 -- read-only aggregation; belt+braces
            logger.warning("frontend.serve: /api/progress failed: %s", exc)
            return JSONResponse(
                {"status": "unavailable",
                 "reason": "progress aggregation error (%s)" % type(exc).__name__,
                 "snapshot": None, "series": [], "reconstructed_history": [],
                 "model_static": True, "engine_enabled": False,
                 "edge_claimed": False},
                status_code=503,
            )

    logger.info("frontend.serve: /api/progress mounted (progress_ledger)")
except Exception as _prog_exc:  # noqa: BLE001 -- a bad import never sinks the app
    logger.warning(
        "frontend.serve: /api/progress could not be mounted -- it will 404 "
        "(%s: %s)", type(_prog_exc).__name__, _prog_exc,
    )

    @app.get("/api/progress")
    def _progress_unavailable() -> JSONResponse:  # noqa: ANN202
        return JSONResponse(
            {"status": "unavailable",
             "reason": "progress_ledger failed to load",
             "snapshot": None, "series": [], "reconstructed_history": [],
             "model_static": True, "engine_enabled": False,
             "edge_claimed": False},
            status_code=503,
        )


def main() -> int:
    """Entry point for `python -m frontend.serve`."""
    try:
        import uvicorn  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        print("uvicorn not installed; pip install uvicorn to serve.")
        return 1
    host = os.environ.get("FRONTEND_SERVE_HOST", "127.0.0.1")
    print("Serving predict-service / paper-trail API on "
          "http://{}:{}/  (Ctrl-C to stop)".format(host, DEFAULT_PORT))
    uvicorn.run(app, host=host, port=DEFAULT_PORT, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
