"""predict_service.app -- THE standalone Auto-API on port 8099.

This CONSOLIDATES and supersedes the M1 stopgap frontend/serve.py. It is the one
FastAPI app that fronts the canonical predict-service store (the single source of
truth) AND mounts the existing paper-trail routes so the React panel's calls keep
working unchanged at the same paths.

READ endpoints (all over predict_service.store -- the canonical store):
  GET /health
      -> {"status": "ok"}
  GET /api/sports
      -> {"status", "active": [<sport>...], "capabilities": {<sport>: {...}},
          "honest_note"}
  GET /api/predict/{sport}
      -> store.read_latest(sport).to_dict() (the full SnapshotEnvelope; the
         status='unavailable' sentinel is returned AS-IS, never fabricated).
  GET /api/predict/{sport}/{game_id}
      -> the single PredictionRecord for game_id plus its markets/edges, or the
         unavailable sentinel when the snapshot or game is missing.

MOUNTED (each router guarded; an import/boot failure degrades that path to a 503
'unavailable' sentinel and can never sink the rest of the API). The guarded mounts
are factored into register(app) helpers to keep this module under the LOC budget:
  * predict_service.core_mounts   -- edge / bestbets / paper / exec / report /
                                     sse / ops / status routers
  * predict_service.extra_mounts  -- produce / lines / gate / results routers
  * predict_service.ingame_mounts -- /api/ingame/{sport}/{game_id} + /api/ingame/gates
e.g. GET /api/paper/trail, /api/paper/clv (core_mounts -> frontend.paper_routes).

HONESTY: every field is real or the explicit unavailable sentinel; NO $ / edge /
roi / profit is fabricated; an honest_note is surfaced on the aggregate endpoints.

Port via PREDICT_SERVICE_PORT (default 8099). `python -m predict_service.app`
runs uvicorn against the module attr predict_service.app:app.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $-edge fabrication; reuse store/registry/contracts verbatim.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi is required at runtime
    raise ImportError(
        "predict_service.app requires fastapi (pip install fastapi uvicorn)."
    ) from exc

from predict_service import registry, store
from predict_service.contracts import HONEST_NOTE, SnapshotEnvelope
from predict_service.edge_completion_gate import apply_game_gate, apply_games_gate
from predict_service.honest_route import honest_route

logger = logging.getLogger(__name__)

DEFAULT_PORT = int(os.environ.get("PREDICT_SERVICE_PORT", "8099"))

# Optional store-root override (tests / alternate cache location). When unset the
# store uses its DEFAULT_BASE_DIR. Tests set this to a tmp_path before import OR
# monkeypatch _store_out_dir().
_STORE_OUT_DIR_ENV = "PREDICT_SERVICE_STORE_DIR"


def _store_out_dir() -> Optional[str]:
    """Resolve the store root override, or None to use the store default."""
    val = os.environ.get(_STORE_OUT_DIR_ENV)
    return val or None


def _gate_edges(edges: list, suppressed_ids: set) -> list:
    """Strip tier and stamp completed_note on edges for completed-game IDs.

    Delegates only when the game was already gated by apply_game_gate (arm 0).
    An edge for a completed game must never surface a positive-EV tier signal --
    tier=None, decision carries no_bet via the prediction, and a completed note
    is attached. Runs in-place on a copy (edge is already a plain dict here).
    No $ field introduced. Never raises.
    """
    if not suppressed_ids:
        return edges
    out = []
    for e in edges:
        if not isinstance(e, dict):
            out.append(e)
            continue
        if e.get("game_id") in suppressed_ids:
            e = dict(e)
            e["tier"] = None
            e["completed_note"] = "game_final: edge stale, no_bet"
        out.append(e)
    return out


app = FastAPI(
    title="CourtVision predict-service Auto-API",
    description=(
        "Calibrated decision-support only. Markets are efficient; no $ edge is "
        "claimed. Canonical predict-service store + paper-trail endpoints."
    ),
)


# -- CORS (LL-P0-05) ----------------------------------------------------------
# The Next.js webapp/ fetches this API from a browser origin; without CORS every
# fetch to :8099 is blocked and every panel reads 'unavailable'. Allowed origins
# come from PREDICT_SERVICE_CORS_ORIGINS (comma-separated); a sensible localhost
# default covers the dev webapp. We do NOT use "*" with credentials.
def _cors_origins() -> list:
    raw = os.environ.get("PREDICT_SERVICE_CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# -- GZip (PERF 2026-07-15, re-applied) ----------------------------------------
# Trail/board payloads run to megabytes of JSON; gzip cuts transfer ~10x.
try:
    from fastapi.middleware.gzip import GZipMiddleware  # noqa: PLC0415

    app.add_middleware(GZipMiddleware, minimum_size=1000)
except Exception as _gz_exc:  # noqa: BLE001
    logger.warning("predict_service.app: gzip middleware unavailable (%s)", _gz_exc)


# -- runtime honesty linter (HL-P1) -------------------------------------------
# Lint every JSON response on the way out and FAIL CLOSED on a banned $/roi/pnl
# key or retracted number, so a runtime fabrication can never reach the browser.
# Guarded: a middleware import failure must not sink the API (the test-time gate
# still covers the contracts), so we log + continue without it.
try:
    from predict_service.honesty_mw import HonestyLinterMiddleware  # noqa: PLC0415

    app.add_middleware(HonestyLinterMiddleware)
    logger.info("predict_service.app: runtime honesty linter middleware enabled")
except Exception as _hon_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: honesty linter middleware NOT enabled (%s: %s)",
        type(_hon_exc).__name__, _hon_exc,
    )


# -- read endpoints -----------------------------------------------------------

@app.get("/health")
def health() -> Dict[str, Any]:
    """Liveness probe. Stable contract: 200 + {"status":"ok"} iff the app is up.

    Kept deliberately shallow (does NOT inspect the route table) so the supervisor's
    m1_api_paper HTTP readiness contract never changes. Route-table depth lives on
    /ready below; a future ProcSpec may point its http_path at /ready.
    """
    return {"status": "ok"}


@app.get("/ready")
def ready() -> JSONResponse:
    """Readiness probe WITH route-table depth (additive; does not touch /health).

    Runs supervisor.health.mount_selfcheck against THIS app so a broken/stale route
    table (a required router failed to import or mount) reads HTTP 503 not-ready
    instead of green. A healthy app reads 200 {"status":"ready", ...}.

    The m1_api_paper ProcSpec currently uses readiness http_path="/health" (a bare
    200 liveness check). To get this deeper readiness, change that ProcSpec to
    http_path="/ready" in supervisor/stack_specs.py (gated file -- propose, do not
    edit autonomously). Until then /ready is available for manual/ops probing and
    never alters the existing /health contract the supervisor depends on.

    Guarded: if mount_selfcheck is unavailable or raises, we fall back to a 200
    liveness-only body (selfcheck="unavailable") so /ready can never be *more*
    fragile than /health -- it only ever ADDS the not-ready signal, never removes
    liveness. Required-route set is owned by supervisor.health._REQUIRED_ROUTES.
    """
    try:
        from supervisor.health import mount_selfcheck  # noqa: PLC0415

        res = mount_selfcheck(app)
    except Exception as exc:  # noqa: BLE001 -- selfcheck unavailable -> liveness only
        logger.warning("/ready: mount_selfcheck unavailable (%s: %s); "
                       "liveness-only response", type(exc).__name__, exc)
        return JSONResponse({"status": "ready", "selfcheck": "unavailable",
                             "reason": "%s" % type(exc).__name__})
    if res.get("ok"):
        return JSONResponse({"status": "ready", "selfcheck": res})
    return JSONResponse({"status": "not_ready", "selfcheck": res}, status_code=503)


@app.get("/api/sports")
def sports() -> Dict[str, Any]:
    """Active sports (predictor built on this machine) + capability descriptors.

    Never raises: registry.active_sports()/capabilities() degrade to safe values
    on a fresh clone (no corpus -> active == []).
    """
    try:
        active = registry.active_sports()
    except Exception as exc:  # noqa: BLE001 -- registry is guarded; belt + braces
        logger.warning("/api/sports active_sports failed: %s", exc)
        active = []
    caps: Dict[str, Any] = {}
    for sport in active:
        try:
            caps[sport] = registry.capabilities(sport)
        except Exception as exc:  # noqa: BLE001
            logger.warning("/api/sports capabilities(%s) failed: %s", sport, exc)
    return {
        "status": "ok",
        "active": active,
        "capabilities": caps,
        "honest_note": HONEST_NOTE,
    }


# -- WAVE 3 prediction-contract read routes (predict_service.predict_mounts) ---
# GET /api/predict/contract + /{sport}/surface + /{sport}/{game_id}/uncertainty.
# Registered HERE -- BEFORE /api/predict/{sport}[/{game_id}] below -- so the
# literal-segment paths win the FastAPI match (registration order matters).
# Guarded: a register failure is logged, never sinks the API. Units only, NO $.
try:
    from predict_service.predict_mounts import register as _register_predict  # noqa: PLC0415

    _register_predict(app)
    logger.info("predict_service.app: predict_mounts registered (WAVE 3 contract)")
except Exception as _pred_exc:  # noqa: BLE001
    logger.warning("predict_service.app: predict_mounts.register failed (%s: %s)",
                   type(_pred_exc).__name__, _pred_exc)


@app.get("/api/predict/{sport}")
@honest_route(extra={"predictions": [], "markets": [], "edges": []})
def predict_sport(sport: str) -> JSONResponse:
    """Full latest SnapshotEnvelope for *sport* from the canonical store.

    Returns store.read_latest(sport).to_dict() verbatim -- including the
    status='unavailable' sentinel when no snapshot exists. Completed games have
    their edges marked stale/no_bet via apply_games_gate (arm 0: game_state).
    Never fabricates.
    """
    env = store.read_latest(sport, out_dir=_store_out_dir())
    body = env.to_dict()
    if body.get("status") == "ok":
        body["predictions"] = apply_games_gate(body.get("predictions") or [])
        gated_ids = {
            p.get("game_id")
            for p in body["predictions"]
            if p.get("suppressed")
        }
        body["edges"] = _gate_edges(body.get("edges") or [], gated_ids)
    return JSONResponse(body)


@app.get("/api/predict/{sport}/{game_id}")
@honest_route(extra={"prediction": None, "markets": [], "edges": []})
def predict_game(sport: str, game_id: str) -> JSONResponse:
    """Single PredictionRecord (+ its markets/edges) for *sport*/*game_id*.

    Reads the canonical snapshot, then projects out the one game. A missing
    snapshot OR a missing game_id yields the unavailable sentinel. Completed games
    have prediction suppressed and edges marked stale via apply_game_gate.
    """
    env = store.read_latest(sport, out_dir=_store_out_dir())
    if env.status != "ok":
        return JSONResponse(env.to_dict())
    record = next((p for p in env.predictions if p.game_id == game_id), None)
    if record is None:
        miss = SnapshotEnvelope.unavailable(
            sport, generated_at=env.generated_at,
            reason="game_id %r not in latest snapshot" % game_id)
        return JSONResponse(miss.to_dict())
    markets = [m for m in env.markets if getattr(m, "game_id", None) == game_id]
    edges = [e for e in env.edges if getattr(e, "game_id", None) == game_id]
    pred_dict = apply_game_gate(record.to_dict(), game_id=game_id)
    suppressed = bool(pred_dict.get("suppressed"))
    gated_ids = {game_id} if suppressed else set()
    return JSONResponse({
        "status": "ok",
        "schema_version": env.schema_version,
        "sport": env.sport,
        "generated_at": env.generated_at,
        "prediction": pred_dict,
        "markets": [m.to_dict() for m in markets],
        "edges": _gate_edges([e.to_dict() for e in edges], gated_ids),
        "honest_note": env.honest_note or HONEST_NOTE,
    })


# -- mounted core API routes (guarded) ----------------------------------------
# The edge / bestbets / paper / exec / report / sse / ops / status routers are
# each mounted GUARDED by predict_service.core_mounts.register: a failure on any
# one is caught + logged and that path degrades to a 503 'unavailable' sentinel
# (never a silent 404, never green) so a single bad module cannot sink the API.
# Factored out (mirroring extra_mounts.register below) to keep this module within
# the <=300 LOC budget.
try:
    from predict_service.core_mounts import register as _register_core  # noqa: PLC0415

    _register_core(app)
    logger.info("predict_service.app: core_mounts registered "
                "(edge/bestbets/paper/exec/report/sse/ops/status)")
except Exception as _core_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: core_mounts.register failed (%s: %s)",
        type(_core_exc).__name__, _core_exc,
    )


# -- Phase-1 backend routers (BE-P0-04/05, BE-P1-01/06, BE-P0-09) -------------
# All mounted (each guarded) by predict_service.extra_mounts.register: producer
# freshness + refresh, the all-books line board + per-game line history, the
# real-money gate status, and settled results. Factored out to keep this module
# within the LOC budget; a register failure is caught so the rest still boots.
try:
    from predict_service.extra_mounts import register as _register_extra  # noqa: PLC0415

    _register_extra(app)
    logger.info("predict_service.app: extra_mounts registered (produce/lines/gate/results)")
except Exception as _extra_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: extra_mounts.register failed (%s: %s)",
        type(_extra_exc).__name__, _extra_exc,
    )


# -- mounted in-game read routes (guarded) ------------------------------------
# GET /api/ingame/{sport}/{game_id} (live calibrated win-prob via the served
# model) and GET /api/ingame/gates (4-sport calibration gate verdicts). Both are
# read-only and CALIBRATION-only (no $ field). Factored into
# predict_service.ingame_mounts.register to keep this module within the <=300 LOC
# budget; a register failure is caught so the rest of the API still boots.
try:
    from predict_service.ingame_mounts import register as _register_ingame  # noqa: PLC0415

    _register_ingame(app)
    logger.info("predict_service.app: ingame_mounts registered (/api/ingame/*)")
except Exception as _ingame_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: ingame_mounts.register failed (%s: %s)",
        type(_ingame_exc).__name__, _ingame_exc,
    )


# -- mounted autonomy/observability routes (guarded) --------------------------
# GET /api/improve/timeline (self-improve loop timeline -- INERT/measurement-only
# honest, enabled=pipeline_enabled()) + GET /api/ops/autonomy (the canonical
# autonomy_status.json, or an honest unavailable sentinel on missing/stale).
# Both are read-only, no $ field. A mount failure is caught + logged so the rest
# of the API still boots; the path then simply 404s rather than green-on-missing.
try:
    from frontend.autonomy_routes import router as _autonomy_router  # noqa: PLC0415

    app.include_router(_autonomy_router)
    logger.info("predict_service.app: autonomy_routes mounted "
                "(/api/improve/timeline, /api/ops/autonomy)")
except Exception as _auto_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: autonomy_routes mount failed (%s: %s)",
        type(_auto_exc).__name__, _auto_exc,
    )


# -- mounted quant Execution API routes (guarded) -----------------------------
# GET-only quant transparency surface: /api/quant/{sport}/validate (per-market
# auditable bet-validation verdicts -- tier/units/edge/ev/clv/gate_proven, MOST
# no_bet/match-the-close), /api/quant/{sport}/devig (Shin consensus),
# /api/quant/{sport}/arb (descriptive, never promoted), /api/quant/risk (UNIT-space
# variance/exposure, RoR descriptive not a guarantee), /api/quant/clv (sign-audited
# scoreboard, vs_close UNPROVEN). NO POST -- placement stays on exec_routes
# (executed=False). Units only; edge_claimed/real_money_enabled stamped False. A
# mount failure is caught + logged so the rest of the API still boots.
try:
    from frontend.quant_routes import router as _quant_router  # noqa: PLC0415

    app.include_router(_quant_router)
    logger.info("predict_service.app: quant_routes mounted (/api/quant/*)")
except Exception as _quant_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: quant_routes mount failed (%s: %s)",
        type(_quant_exc).__name__, _quant_exc,
    )


# -- mounted WAVE 4 unified-gateway routes (guarded) --------------------------
# The unified multi-API gateway over the SAME sports-intelligence model:
#   GET /api/catalog            -- lists the contracted faces + versions + caps
#   GET /api/status.all_honest  -- the SINGLE honesty bit (True iff no face serves
#                                  a $ field / fabricated edge / stale-green /
#                                  real-money-enabled; flips False the instant one does)
#   GET /api/intel/{query}      -- the NUMBER-FREE person-free scouting face
# Each face response inherits the honesty rails via gateway.wrap (units only,
# edge_claimed/real_money_enabled False, freshness serveable=False on stale). All
# pass through a keyless rate guard. A mount failure is caught + logged so the rest
# of the API still boots; the path then 404s rather than green-on-missing.
try:
    from frontend.catalog_routes import router as _catalog_router  # noqa: PLC0415
    from frontend.intel_routes import router as _intel_router  # noqa: PLC0415

    app.include_router(_catalog_router)
    app.include_router(_intel_router)
    logger.info("predict_service.app: gateway routes mounted "
                "(/api/catalog, /api/status.all_honest, /api/intel/*)")
except Exception as _gw_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: gateway routes mount failed (%s: %s)",
        type(_gw_exc).__name__, _gw_exc,
    )


# -- W10: improve_ledger endpoint (GET /api/improve/ledger) -------------------
# Exposes the self-improve loop's per-cycle Brier/ECE/BSS metrics. Read-only;
# never writes; no $ key. A mount failure is caught + logged so the rest of the
# API still boots; the path then 404s rather than green-on-missing.
try:
    from predict_service.frontend.improve_ledger_routes import (  # noqa: PLC0415
        router as _improve_ledger_router,
    )

    app.include_router(_improve_ledger_router)
    logger.info("predict_service.app: improve_ledger_routes mounted "
                "(/api/improve/ledger)")
except Exception as _ilr_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: improve_ledger_routes mount failed (%s: %s)",
        type(_ilr_exc).__name__, _ilr_exc,
    )


# -- be-sharpening-mount: GET /api/improve/sharpening -------------------------
# Sharpening-observability view: wires improvement_trend, coverage_map, and
# ledger_reconcile into one read-only endpoint.  Missing ledger -> status=
# 'unavailable' (never green); enabled mirrors sentinel; edge_claimed=False;
# no $ / pnl / roi field; daemon SHIP w/o graded row -> drift flag.
# A mount failure is caught + logged; the path then 404s rather than silently
# returning a wrong value or sinking the rest of the API.
try:
    from predict_service.frontend.improve_sharpening_routes import (  # noqa: PLC0415
        router as _improve_sharpening_router,
    )

    app.include_router(_improve_sharpening_router)
    logger.info("predict_service.app: improve_sharpening_routes mounted "
                "(/api/improve/sharpening)")
except Exception as _ish_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: improve_sharpening_routes mount failed (%s: %s)",
        type(_ish_exc).__name__, _ish_exc,
    )


# -- W3: bestbets_board endpoint (GET /api/bestbets/board) --------------------
# Multi-sport ranked calibrated divergence cards (props + game markets), tier/
# status filterable. decision==bet rows only, sorted by tier then confidence.
# No $ field; clv may be INSUFFICIENT_DATA; edge_claimed=False; real-money DENY.
# A mount failure is caught + logged so the rest of the API still boots.
try:
    from predict_service.frontend.bestbets_board_routes import (  # noqa: PLC0415
        router as _bestbets_board_router,
    )

    app.include_router(_bestbets_board_router)
    logger.info("predict_service.app: bestbets_board_routes mounted "
                "(/api/bestbets/board)")
except Exception as _bbb_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: bestbets_board_routes mount failed (%s: %s)",
        type(_bbb_exc).__name__, _bbb_exc,
    )


# -- W5: pm_trail endpoints (GET /api/paper/pm/trail, /api/paper/pm/trade/{id}) --
# Kalshi/Polymarket paper-trade browse + per-trade execution detail. Read-only;
# never writes; no $ key; CLV null-honest; executed=False; real-money DENY.
# A mount failure is caught + logged; the paths then 404 rather than green-on-missing.
try:
    from predict_service.frontend.pm_trail_routes import (  # noqa: PLC0415
        router as _pm_trail_router,
    )

    app.include_router(_pm_trail_router)
    logger.info("predict_service.app: pm_trail_routes mounted "
                "(/api/paper/pm/trail, /api/paper/pm/trade/*)")
except Exception as _pmtr_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: pm_trail_routes mount failed (%s: %s)",
        type(_pmtr_exc).__name__, _pmtr_exc,
    )


# -- WS3: paper predictions route (GET /api/paper/predictions) ----------------
# Exposes the 3284 real model predictions from paper_predictions.jsonl with
# pagination and honest per-row fields (sport, matchup, model_prob, market_prob,
# side, tier=null, outcome=null, clv=null when no close, executed=False, no $).
# An empty/missing file yields status='ok' trades=[] (honest empty, never raises).
# A mount failure is caught + logged so the rest of the API still boots.
try:
    from predict_service.frontend.paper_predictions_routes import (  # noqa: PLC0415
        router as _paper_predictions_router,
    )

    app.include_router(_paper_predictions_router)
    logger.info("predict_service.app: paper_predictions_routes mounted "
                "(/api/paper/predictions)")
except Exception as _pp_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: paper_predictions_routes mount failed (%s: %s)",
        type(_pp_exc).__name__, _pp_exc,
    )


# -- WS2: CLV corpus route (GET /api/improve/clv-corpus) ----------------------
# Dedicated 'my records' surface: per-candidate CLV-delta rows from the self-
# improve proposals corpus (data/cache/improve/proposals.jsonl). Each row carries
# honest replication labels (REPLICATION_PENDING / REPLICATED), vs_close=UNPROVEN
# when the corpus was built from proxy closes only, edge_claimed=False, units=
# probability; no $ / pnl / roi / profit field anywhere. Missing proposals file
# -> status='unavailable', never green. A mount failure is caught + logged so
# the rest of the API still boots; the path then 404s rather than silently
# returning a wrong value or green-on-missing.
try:
    from predict_service.frontend.clv_corpus_routes import (  # noqa: PLC0415
        router as _clv_corpus_router,
    )

    app.include_router(_clv_corpus_router)
    logger.info("predict_service.app: clv_corpus_routes mounted "
                "(/api/improve/clv-corpus)")
except Exception as _clv_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: clv_corpus_routes mount failed (%s: %s)",
        type(_clv_exc).__name__, _clv_exc,
    )


# -- WAVE: paper P&L series + bankroll (GET /api/paper/pnl/series, /api/paper/bankroll) --
# Serves the daemon-written data/frontend/paper_pnl_series.json and
# paper_bankroll.json verbatim so the webapp can render the paper track-record
# panel. UNITS only (no $ field); a missing/unreadable file yields an honest
# {status:'unavailable'} sentinel with HTTP 200 -- never a fabricated curve or
# balance. edge_claimed=False; executed=False. A mount failure is caught + logged
# so the rest of the API still boots; the paths then 404 rather than green-on-missing.
try:
    from predict_service.frontend.paper_series_routes import (  # noqa: PLC0415
        router as _paper_series_router,
    )

    app.include_router(_paper_series_router)
    logger.info("predict_service.app: paper_series_routes mounted "
                "(/api/paper/pnl/series, /api/paper/bankroll)")
except Exception as _psr_exc:  # noqa: BLE001
    logger.warning(
        "predict_service.app: paper_series_routes mount failed (%s: %s)",
        type(_psr_exc).__name__, _psr_exc,
    )


# -- WS1: idempotent startup mount self-check ---------------------------------
# Run AFTER all mounts so a route that failed to mount (import error, stale
# process started before the router was added) is caught immediately and logged
# WARN. Never raises; never green-on-missing. supervisor.health.mount_selfcheck
# is idempotent (second call returns the cached result); wiring it here means
# EVERY restart of this module runs the check automatically.
try:
    from supervisor.health import mount_selfcheck as _mount_selfcheck  # noqa: PLC0415
    _selfcheck_result = _mount_selfcheck(app)
    if not _selfcheck_result.get("ok"):
        logger.warning(
            "predict_service.app: startup selfcheck FAILED -- missing routes: %s. "
            "The FE will 404 on these paths. Restart predict_service to fix.",
            _selfcheck_result.get("missing"),
        )
except Exception as _sc_exc:  # noqa: BLE001
    logger.warning("predict_service.app: startup selfcheck raised (%s: %s); "
                   "continuing.", type(_sc_exc).__name__, _sc_exc)


def main() -> int:
    """Entry point for `python -m predict_service.app`."""
    try:
        import uvicorn  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        print("uvicorn not installed; pip install uvicorn to serve.")
        return 1
    host = os.environ.get("PREDICT_SERVICE_HOST", "127.0.0.1")
    print("Serving predict-service Auto-API on "
          "http://{}:{}/  (Ctrl-C to stop)".format(host, DEFAULT_PORT))
    uvicorn.run(app, host=host, port=DEFAULT_PORT, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
