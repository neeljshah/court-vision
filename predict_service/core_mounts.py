"""predict_service.core_mounts -- guarded core API router mounts.

Each router: import/boot failure yields a 503 sentinel; never sinks siblings.
register(app) called once from predict_service.app.

/api/ops/status pipes rows through normalize_rows (fresh=null->stale) so
/api/ops/status and /api/ops/doctor cannot disagree for the same poll window.
No $ field; stale-never-green; <=300 LOC; ASCII only.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi.responses import JSONResponse

from predict_service.contracts import HONEST_NOTE
from predict_service.frontend._guarded_mounts import (
    _mount_funnel,
    _mount_lines_matrix,
)

logger = logging.getLogger(__name__)


def _s503(reason: str, **extra: Any) -> JSONResponse:
    """Return a 503 unavailable sentinel with status+reason merged with *extra*."""
    return JSONResponse({"status": "unavailable", "reason": reason, **extra}, status_code=503)


def _mount_edge(app) -> None:  # noqa: ANN001
    """Deep lines-vs-predictions comparison: /api/v1/edges/{sport}[/{game_id}]."""
    try:
        from frontend.edge_routes import router as _edge_router  # noqa: PLC0415
        app.include_router(_edge_router)
        logger.info("core_mounts: edge_routes mounted at /api/v1/edges/*")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: edge_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/v1/edges/{sport}")
        def _edge_sport_unavailable(sport: str) -> JSONResponse:  # noqa: ANN202
            return _s503("edge_routes failed to load",
                         sport=sport, count=0, games=[], edge_claimed=False)

        @app.get("/api/v1/edges/{sport}/{game_id}")
        def _edge_game_unavailable(sport: str, game_id: str) -> JSONResponse:  # noqa: ANN202
            return _s503("edge_routes failed to load",
                         sport=sport, game_id=game_id, edge_claimed=False)


def _mount_bestbets(app) -> None:  # noqa: ANN001
    """P5 EXECUTION API: /api/v1/bestbets/{sport}[/{game_id}] (units only, NO $)."""
    try:
        from frontend.bestbets_routes import router as _bestbets_router  # noqa: PLC0415
        app.include_router(_bestbets_router)
        logger.info("core_mounts: bestbets_routes mounted at /api/v1/bestbets/*")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: bestbets_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/v1/bestbets/{sport}")
        def _bestbets_sport_unavailable(sport: str) -> JSONResponse:  # noqa: ANN202
            return _s503("bestbets_routes failed to load",
                         sport=sport, count=0, n_best_bets=0, games=[], edge_claimed=False)

        @app.get("/api/v1/bestbets/{sport}/{game_id}")
        def _bestbets_game_unavailable(sport: str, game_id: str) -> JSONResponse:  # noqa: ANN202
            return _s503("bestbets_routes failed to load",
                         sport=sport, game_id=game_id, candidates=[], best_bets=[],
                         edge_claimed=False)


def _mount_paper(app) -> None:  # noqa: ANN001
    """Paper-trail read routes: /api/paper/trail, /api/paper/clv."""
    try:
        from frontend.paper_routes import router as _paper_router  # noqa: PLC0415
        app.include_router(_paper_router)
        logger.info("core_mounts: paper_routes mounted at /api/paper/*")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: paper_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/paper/trail")
        def _paper_trail_unavailable() -> JSONResponse:  # noqa: ANN202
            return _s503("paper_routes failed to load", trail=[], count=0)

        @app.get("/api/paper/clv")
        def _paper_clv_unavailable() -> JSONResponse:  # noqa: ANN202
            return _s503("paper_routes failed to load", n_bets=0)


def _mount_exec(app) -> None:  # noqa: ANN001
    """Manual paper-trade execution: POST /api/paper/place, GET /api/paper/open."""
    try:
        from frontend.exec_routes import router as _exec_router  # noqa: PLC0415
        app.include_router(_exec_router)
        logger.info("core_mounts: exec_routes mounted at /api/paper/place,/open")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: exec_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.post("/api/paper/place")
        def _paper_place_unavailable() -> JSONResponse:  # noqa: ANN202
            return _s503("exec_routes failed to load")

        @app.get("/api/paper/open")
        def _paper_open_unavailable() -> JSONResponse:  # noqa: ANN202
            return _s503("exec_routes failed to load", open=[], count=0)


def _mount_report(app) -> None:  # noqa: ANN001
    """Per-game report routes: /api/report/{sport}[/{game_id}]."""
    try:
        from frontend.report_routes import router as _report_router  # noqa: PLC0415
        app.include_router(_report_router)
        logger.info("core_mounts: report_routes mounted at /api/report/*")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: report_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/report/{sport}/{game_id}")
        def _report_game_unavailable(sport: str, game_id: str) -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "unavailable",
                 "sport": sport, "game_id": game_id,
                 "reason": "report_routes failed to load",
                 "pregame": None, "markets": [], "edges": [],
                 "live": {"status": "unavailable", "reason": "report_routes failed to load"},
                 "intel": None,
                 "meta": {"as_of": None, "honest_note": HONEST_NOTE,
                          "schema_version": "1.0.0"}},
                status_code=503)

        @app.get("/api/report/{sport}")
        def _report_sport_unavailable(sport: str) -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "unavailable",
                 "sport": sport,
                 "game_ids": [], "count": 0,
                 "generated_at": None,
                 "reason": "report_routes failed to load",
                 "honest_note": HONEST_NOTE},
                status_code=503)


def _mount_sse(app) -> None:  # noqa: ANN001
    """SSE stream routes: /api/stream/game/{sport}/{game_id}, /api/stream/paper."""
    try:
        from frontend.sse import router as _sse_router  # noqa: PLC0415
        app.include_router(_sse_router)
        logger.info("core_mounts: sse routes mounted at /api/stream/*")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: sse routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/stream/game/{sport}/{game_id}")
        def _stream_game_unavailable(sport: str, game_id: str) -> JSONResponse:  # noqa: ANN202
            return _s503("sse routes failed to load", sport=sport, game_id=game_id)

        @app.get("/api/stream/paper")
        def _stream_paper_unavailable() -> JSONResponse:  # noqa: ANN202
            return _s503("sse routes failed to load", trail=[], count=0)


def _mount_doctor_consensus(app) -> None:  # noqa: ANN001
    """Consensus /api/ops/doctor -- MUST be called before _mount_ops."""
    try:
        from predict_service.frontend.doctor_consensus_routes import (  # noqa: PLC0415
            router as _dc_router,
        )
        app.include_router(_dc_router)
        logger.info("core_mounts: doctor_consensus mounted at /api/ops/doctor")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: doctor_consensus not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/ops/doctor")
        def _doctor_consensus_unavailable() -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"overall": "down", "edge_claimed": False,
                 "summary": "doctor_consensus_routes failed to load",
                 "problems": [], "ok_services": []},
                status_code=503)


def _mount_ops(app) -> None:  # noqa: ANN001
    """Ops: /api/ops/status (normalized, direct) + /api/ops/metrics (via router).
    Ops router's /api/ops/status+doctor stripped before include_router; those paths
    are owned by the direct handler below and _mount_doctor_consensus respectively.
    """
    @app.get("/api/ops/status")
    def _ops_status_normalized() -> JSONResponse:  # noqa: ANN202
        """Pipe services[] through normalize_rows; fresh=null->stale; no $."""
        try:
            from ops import health_aggregator as _agg  # noqa: PLC0415
            from predict_service.status_freshness_normalizer import normalize_rows  # noqa: PLC0415
            raw = _agg.aggregate()
            raw_rows = raw.get("services") or []
            norm = normalize_rows(raw_rows, default_sla_sec=300.0)
            out = dict(raw)
            out["services"] = norm.get("rows") or raw_rows
            out["overall"] = norm.get("overall") or raw.get("overall")
            out["_normalized"] = True
            return JSONResponse(out)
        except Exception as exc:  # noqa: BLE001
            logger.warning("core_mounts: _ops_status_normalized failed: %s", exc)
            return JSONResponse(
                {"overall": "down", "services": [],
                 "notes": ["status normalization failed: %s" % type(exc).__name__],
                 "_normalized": False},
                status_code=503)
    try:
        from ops.status_endpoint import router as _ops_router  # noqa: PLC0415
        # Strip /api/ops/status + /api/ops/doctor before include_router so those
        # paths are owned exclusively by the direct handlers (status above;
        # doctor in _mount_doctor_consensus). Only /api/ops/metrics passes through.
        _OWNED = {"/api/ops/status", "/api/ops/doctor"}
        _ops_router.routes = [
            r for r in _ops_router.routes if getattr(r, "path", None) not in _OWNED
        ]
        app.include_router(_ops_router)
        logger.info("core_mounts: ops mounted /api/ops/metrics (status+doctor stripped)")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: ops routes not mounted (%s: %s)",
                       type(exc).__name__, exc)
        @app.get("/api/ops/metrics")
        def _ops_metrics_unavailable() -> JSONResponse:  # noqa: ANN202
            return _s503("ops.status_endpoint failed to load", clv=None, liveness=None)


def _mount_status(app) -> None:  # noqa: ANN001
    """Self-improve + parity routes: /api/improve/status, /api/parity."""
    try:
        from frontend.status_routes import router as _status_router  # noqa: PLC0415
        app.include_router(_status_router)
        logger.info("core_mounts: status_routes mounted at /api/improve/status,/api/parity")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: status_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/improve/status")
        def _improve_status_unavailable() -> JSONResponse:  # noqa: ANN202
            return _s503("status_routes failed to load",
                         ratchet={"state": "idle"}, kinds=[], edge_claimed=False)

        @app.get("/api/parity")
        def _parity_unavailable() -> JSONResponse:  # noqa: ANN202
            return _s503("status_routes failed to load",
                         dimensions=[], sports=[], green=False, edge_claimed=False)


def register(app) -> None:  # noqa: ANN001
    """Mount all core API routers onto *app* (each guarded)."""
    _mount_edge(app)
    _mount_bestbets(app)
    _mount_paper(app)
    _mount_exec(app)
    _mount_report(app)
    _mount_sse(app)
    _mount_doctor_consensus(app)  # before _mount_ops -- owns /api/ops/doctor
    _mount_ops(app)
    _mount_status(app)
    _mount_funnel(app)
    _mount_lines_matrix(app)


__all__ = ["register"]
