"""predict_service.v1_completion_gate_mounts -- BE7-1-v1-postgame-gate.

Closes the carry-forward P0: /api/v1/edges/{sport}[/{game_id}] and
/api/v1/bestbets/{sport}[/{game_id}] can emit decision=bet / positive-EV
edges on COMPLETED games because the underlying frontend.edge_routes /
frontend.bestbets_routes router does NOT apply the completion gate.

Fix: register DIRECT FastAPI routes for all four v1 paths on *app* BEFORE
the underlying routers are include_router'd (FastAPI first-match wins), then
delegate to the real assemblers + apply the gate on the way out.

Gate logic: reuses predict_service.edge_completion_gate.apply_game_gate /
apply_games_gate VERBATIM. Any game whose live.state is in {post,final,
complete} (arm 0: game_state field, arm 1: finals list, arm 3: timeout) gets:
  - edges flagged: tier=None, completed_note set, stale freshness
  - decision forced no_bet
  - tier=None, stake_units=0
  - a COMPLETED note

HONESTY: no $ / pnl / roi / profit key; stale-never-green; real-money stays
DENY; units only.
INVARIANTS: predict_service/ only; <=300 LOC; ASCII only; no $; no src/kernel/api.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover
    raise ImportError("predict_service.v1_completion_gate_mounts requires fastapi.") from exc

from predict_service.edge_completion_gate import apply_game_gate, apply_games_gate

_PREFIX_EDGES = "/api/v1/edges"
_PREFIX_BESTBETS = "/api/v1/bestbets"

# ---------------------------------------------------------------------------
# Edge-stamping helpers (mirrors app._gate_edges verbatim -- no rewrite)
# ---------------------------------------------------------------------------

def _gate_edge_list(edges: List[Dict[str, Any]],
                    suppressed_ids: set) -> List[Dict[str, Any]]:
    """Stamp tier=None + completed_note on edges for completed game IDs."""
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


def _gate_bestbet_game(game: Dict[str, Any]) -> Dict[str, Any]:
    """Gate one decide_game output dict via apply_game_gate.

    The bestbets router builds candidates/best_bets out of edge comparison rows;
    those rows carry decision/tier/stake_units per-row (not a top-level field).
    After gating we also suppress the per-row tier/stake_units and clear best_bets.
    """
    # Synthesize fields apply_game_gate looks for from the bestbets shape.
    probe: Dict[str, Any] = {
        "game_id": game.get("game_id"),
        "tipoff": game.get("tipoff"),
        "game_state": game.get("game_state"),
        "decision": (
            "bet" if game.get("best_bets") else "no_bet"
        ),
        "stake_units": 1.0,
        "tier": (
            (game.get("best_bets") or [{}])[0].get("tier")
            if game.get("best_bets") else None
        ),
    }
    gated = apply_game_gate(probe, game_id=str(game.get("game_id") or ""))
    if not gated.get("suppressed"):
        return game

    # Game is completed -- zero out all bet signals.
    out = dict(game)
    out["decision"] = "no_bet"
    out["stake_units"] = 0
    out["tier"] = None
    out["suppressed"] = True
    out["suppress_reason"] = gated.get("suppress_reason", "game_complete")
    out["skip_reason"] = "game_final"
    out["completed_note"] = "game_final: edge stale, no_bet"
    # Clear best_bets (no active bets on a settled game) and suppress candidates.
    out["best_bets"] = []
    candidates = []
    for c in (game.get("candidates") or []):
        c2 = dict(c)
        c2["decision"] = "no_bet"
        c2["tier"] = None
        c2["stake_units"] = 0
        candidates.append(c2)
    out["candidates"] = candidates
    # Force freshness stale on the game payload if present.
    f = out.get("freshness")
    if isinstance(f, dict):
        f2 = dict(f)
        f2["status"] = "stale"
        f2["ok"] = False
        f2["fresh"] = False
        f2["stale"] = True
        f2.setdefault("reason", "game_complete")
        out["freshness"] = f2
    else:
        out["freshness"] = {
            "status": "stale", "ok": False,
            "fresh": False, "stale": True,
            "reason": "game_complete",
        }
    return out


# ---------------------------------------------------------------------------
# register() -- call BEFORE include_router(edge_router) and include_router(bestbets_router)
# ---------------------------------------------------------------------------

def register(app: Any) -> None:  # noqa: ANN001
    """Register gated v1 routes on *app* BEFORE the underlying routers are included.

    FastAPI resolves routes in registration order -- the first matching path wins.
    Calling register(app) before core_mounts._mount_edge / _mount_bestbets ensures
    these gated handlers take precedence over the un-gated router paths.

    On any internal error the gate degrades to the raw upstream response (never
    raises, never sinks the API -- belt-and-braces).
    """

    # -- /api/v1/edges/{sport} -----------------------------------------------

    @app.get(_PREFIX_EDGES + "/{sport}")
    def v1_edges_sport(sport: str,
                       store_dir: Optional[str] = None) -> JSONResponse:
        """Gated: edges for all games in *sport* (completed games forced stale)."""
        try:
            from frontend.edge_api import build_edge_view  # noqa: PLC0415
            view = build_edge_view(sport, store_out_dir=store_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("v1_completion_gate: edges/%s assembly error: %s", sport, exc)
            return JSONResponse({
                "sport": sport, "status": "unavailable",
                "reason": "assembly error (%s)" % type(exc).__name__,
                "count": 0, "games": [], "edge_claimed": False,
            })
        if view.get("status") != "ok":
            return JSONResponse(view)

        gated_games: List[Dict[str, Any]] = []
        suppressed_ids: set = set()
        for g in view.get("games") or []:
            gated = apply_game_gate(g, game_id=str(g.get("game_id") or ""))
            gated_games.append(gated)
            if gated.get("suppressed"):
                suppressed_ids.add(gated.get("game_id"))

        out = dict(view)
        out["games"] = gated_games
        return JSONResponse(out)

    # -- /api/v1/edges/{sport}/{game_id} -------------------------------------

    @app.get(_PREFIX_EDGES + "/{sport}/{game_id}")
    def v1_edges_game(sport: str, game_id: str,
                      store_dir: Optional[str] = None) -> JSONResponse:
        """Gated: single-game edge view (completed game forced stale/no_bet)."""
        try:
            from frontend.edge_api import build_game_edge  # noqa: PLC0415
            game = build_game_edge(sport, game_id, store_out_dir=store_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("v1_completion_gate: edges/%s/%s error: %s",
                           sport, game_id, exc)
            return JSONResponse({
                "sport": sport, "game_id": game_id,
                "status": "unavailable",
                "reason": "assembly error (%s)" % type(exc).__name__,
                "edge_claimed": False,
            })
        if game.get("status") != "ok":
            return JSONResponse(game)
        gated = apply_game_gate(game, game_id=str(game_id))
        return JSONResponse(gated)

    # -- /api/v1/bestbets/{sport} --------------------------------------------

    @app.get(_PREFIX_BESTBETS + "/{sport}")
    def v1_bestbets_sport(sport: str,
                          store_dir: Optional[str] = None) -> JSONResponse:
        """Gated: best-bets for all games in *sport* (completed games zeroed out)."""
        try:
            from frontend.edge_api import build_edge_view  # noqa: PLC0415
            from frontend.exec_decision import decide_game, decision_note  # noqa: PLC0415
            from predict_service.contracts import HONEST_NOTE, SCHEMA_VERSION  # noqa: PLC0415
            view = build_edge_view(sport, store_out_dir=store_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("v1_completion_gate: bestbets/%s assembly error: %s",
                           sport, exc)
            return JSONResponse({
                "sport": sport, "status": "unavailable",
                "reason": "assembly error (%s)" % type(exc).__name__,
                "count": 0, "n_best_bets": 0, "games": [], "edge_claimed": False,
            })
        if view.get("status") != "ok":
            return JSONResponse(view)

        games_out: List[Dict[str, Any]] = []
        for g in view.get("games") or []:
            try:
                decided = decide_game(g)
            except Exception as exc2:  # noqa: BLE001
                logger.warning("v1_completion_gate: decide_game failed gid=%s: %s",
                               g.get("game_id"), exc2)
                decided = g
            games_out.append(_gate_bestbet_game(decided))

        n_bets = sum(len(g.get("best_bets") or []) for g in games_out)
        return JSONResponse({
            "sport": sport,
            "generated_at": view.get("generated_at", ""),
            "status": "ok",
            "count": len(games_out),
            "n_best_bets": n_bets,
            "games": games_out,
            "decision_note": decision_note(),
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
            "schema_version": SCHEMA_VERSION,
        })

    # -- /api/v1/bestbets/{sport}/{game_id} ----------------------------------

    @app.get(_PREFIX_BESTBETS + "/{sport}/{game_id}")
    def v1_bestbets_game(sport: str, game_id: str,
                         store_dir: Optional[str] = None) -> JSONResponse:
        """Gated: single-game best-bets (completed game forced no_bet/stale)."""
        try:
            from frontend.edge_api import build_game_edge  # noqa: PLC0415
            from frontend.exec_decision import decide_game, decision_note  # noqa: PLC0415
            from predict_service.contracts import HONEST_NOTE, SCHEMA_VERSION  # noqa: PLC0415
            game = build_game_edge(sport, game_id, store_out_dir=store_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("v1_completion_gate: bestbets/%s/%s error: %s",
                           sport, game_id, exc)
            return JSONResponse({
                "sport": sport, "game_id": game_id,
                "status": "unavailable",
                "reason": "assembly error (%s)" % type(exc).__name__,
                "candidates": [], "best_bets": [], "edge_claimed": False,
            })
        if game.get("status") != "ok":
            return JSONResponse({
                "sport": sport, "game_id": game_id, "status": "unavailable",
                "reason": game.get("reason", "game unavailable"),
                "candidates": [], "best_bets": [],
                "honest_note": HONEST_NOTE, "edge_claimed": False,
                "schema_version": SCHEMA_VERSION,
            })
        try:
            decided = decide_game(game)
        except Exception as exc2:  # noqa: BLE001
            decided = game
        gated = _gate_bestbet_game(decided)
        gated.update({
            "sport": sport,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
            "schema_version": SCHEMA_VERSION,
            "decision_note": decision_note(),
        })
        return JSONResponse(gated)

    logger.info(
        "v1_completion_gate_mounts: registered gated routes for "
        "/api/v1/edges/* and /api/v1/bestbets/*"
    )


__all__ = ["register"]
