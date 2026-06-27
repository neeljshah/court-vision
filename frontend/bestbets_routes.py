"""frontend.bestbets_routes -- the EXECUTION API (lines + best bets, units only).

The P5 execution surface, mounted into predict_service.app alongside the edge /
report / paper routes.  It builds on the existing deep edge assembler (which
line-shops across books and SHIN-devigs every price) and the exec_decision layer
(tier floors + no-bet + flat-unit + capped quarter-Kelly), then attaches the
live CLV beat-scoreboard.

  GET /api/v1/bestbets/{sport}
      Every game's execution candidates + ranked best_bets (decision=='bet'
      only), plus the aggregate CLV scoreboard.  Below-floor candidates are
      marked decision='no_bet' (kept for transparency, never promoted).

  GET /api/v1/bestbets/{sport}/{game_id}
      One game's execution decision object (same per-game shape).

HONESTY (enforced by shape): stake is in UNITS only -- flat_unit + kelly_units;
there is NO dollar / $ / roi / profit / pnl / bankroll / stake_dollars key
anywhere.  Edge = model_prob - SHIN-devigged market_prob; EV = p*odds - 1.  CLV
(better-number-than-close) is the only money-adjacent yardstick and is surfaced
from the vetted clv_ledger, flagged clv_is_proxy.  Markets are efficient;
edge_claimed is always False.  Line-shopping prefers the best bettable price
(low-/no-vig PM venues like Kalshi/Polymarket win when they quote the longest
price), an EXECUTION edge -- not a beat-the-close edge.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no $ key; no secrets.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Serve-stale-while-revalidate cache for the per-sport OK envelope. build_edge_view
# line-shops + decides every market for every game live (~30-90s for a full slate under
# load), so an uncached route makes the UI hang/time out. Strategy: once an OK envelope
# exists we ALWAYS serve it instantly; when it is older than _VIEW_TTL_SEC we kick off a
# SINGLE background rebuild (never blocking the request) and keep serving the last-good
# copy until it lands. Only the very first request per sport (cold, no cache) blocks; the
# stack warms each sport at startup so users never hit that. Only the live path caches (a
# caller passing store_dir -- tests -- bypasses entirely, so tests stay deterministic).
# Only OK envelopes are cached (stale-never-green: an 'unavailable' never gets stored).
_VIEW_TTL_SEC: float = 300.0
_view_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_view_refreshing: set = set()          # sports with a background rebuild in flight
_view_lock = threading.Lock()

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.bestbets_routes requires fastapi.") from exc

from frontend.edge_api import build_edge_view, build_game_edge
from frontend.exec_decision import decide_game, decision_note
from predict_service.contracts import HONEST_NOTE, SCHEMA_VERSION
from predict_service.honest_route import honest_route

router = APIRouter()

_PREFIX = "/api/v1/bestbets"
# Same env var as predict_service.app so test monkeypatches flow through.
_STORE_DIR_ENV = "PREDICT_SERVICE_STORE_DIR"


def _store_out_dir() -> Optional[str]:
    val = os.environ.get(_STORE_DIR_ENV)
    return val or None


def _clv_scoreboard() -> Dict[str, Any]:
    """The live beat-the-close CLV scoreboard (vetted clv_ledger; never raises)."""
    try:
        from frontend.paper_trail import clv_summary
        summary = clv_summary()
    except Exception as exc:  # noqa: BLE001 -- CLV is advisory, never fatal
        logger.warning("bestbets_routes: clv_summary failed: %s", exc)
        return {"n_bets": 0, "pct_beat_close": None, "mean_clv_pct": None,
                "clv_is_proxy": False, "by_sport": {},
                "note": "CLV ledger unavailable (%s)" % type(exc).__name__}
    return summary


def _live_for(sport: str, game: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort in-game number for this game via the frozen live read.

    Reuses frontend.report._live (M6 ingame spine snapshot -> keyless ESPN
    live_board), so the execution surface serves the SAME in-game number the
    report serves.  Any miss -> a clean unavailable sentinel (never fabricated).
    """
    try:
        from frontend.report import _live
        return _live(sport, str(game.get("home", "")), str(game.get("away", "")),
                     game_id=str(game.get("game_id", "")))
    except Exception as exc:  # noqa: BLE001 -- live is best-effort
        logger.debug("bestbets_routes: live read failed: %s", exc)
        return {"status": "unavailable",
                "reason": "live read error (%s)" % type(exc).__name__}


def _decorate(decision: Dict[str, Any], sport: str,
              game: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the in-game number to a per-game decision object."""
    decision["live"] = _live_for(sport, game)
    return decision


def _envelope(sport: str, games: List[Dict[str, Any]],
              generated_at: str) -> Dict[str, Any]:
    n_bets = sum(len(g.get("best_bets", [])) for g in games)
    return {
        "sport": sport,
        "generated_at": generated_at,
        "status": "ok",
        "count": len(games),
        "n_best_bets": n_bets,
        "games": games,
        "clv": _clv_scoreboard(),
        "decision_note": decision_note(),
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
        "schema_version": SCHEMA_VERSION,
    }


def _unavailable(sport: str, generated_at: str, reason: str) -> Dict[str, Any]:
    return {
        "sport": sport, "generated_at": generated_at, "status": "unavailable",
        "reason": reason, "count": 0, "n_best_bets": 0, "games": [],
        "clv": _clv_scoreboard(), "decision_note": decision_note(),
        "honest_note": HONEST_NOTE, "edge_claimed": False,
        "schema_version": SCHEMA_VERSION,
    }


@router.get(_PREFIX + "/{sport}")
@honest_route(extra={"count": 0, "n_best_bets": 0, "games": []})
def bestbets_for_sport(sport: str, store_dir: Optional[str] = None) -> JSONResponse:
    """Execution candidates + ranked best bets for every game in *sport*.

    Builds the deep edge view (line-shopped, Shin-devigged), applies the tier
    floor / no-bet / units decision layer to every comparison row, attaches the
    in-game number per game, and surfaces the CLV beat-scoreboard.  Never raises.
    """
    live_path = store_dir is None  # only the real route caches; tests pass store_dir
    if not live_path:
        envelope = _compute_envelope(sport, store_dir)
        return JSONResponse(envelope)

    hit = _view_cache.get(sport)
    if hit is not None:
        # An OK envelope exists -> serve it instantly. If it is stale, trigger ONE
        # background rebuild (serve-stale-while-revalidate); never block this request.
        if (time.time() - hit[0]) >= _VIEW_TTL_SEC:
            _kick_refresh(sport)
        return JSONResponse(hit[1])

    # Cold (no cache yet): compute synchronously this once, then cache if OK.
    envelope = _compute_envelope(sport, None)
    if envelope.get("status") == "ok":
        _view_cache[sport] = (time.time(), envelope)
    return JSONResponse(envelope)


def _compute_envelope(sport: str, store_dir: Optional[str]) -> Dict[str, Any]:
    """Build the per-sport best-bets envelope (deep edge view -> decision layer). Returns
    an OK envelope or an 'unavailable' one; never raises."""
    out_dir: Any = store_dir if store_dir is not None else _store_out_dir()
    try:
        view = build_edge_view(sport, store_out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001 -- assembler is pure; belt + braces
        logger.warning("bestbets_routes /%s: build_edge_view raised: %s", sport, exc)
        return _unavailable(sport, "", "assembly error (%s)" % type(exc).__name__)
    if view.get("status") != "ok":
        return _unavailable(sport, view.get("generated_at", "") or "",
                            view.get("reason", "snapshot unavailable"))
    games: List[Dict[str, Any]] = []
    for g in view.get("games", []) or []:
        try:
            games.append(_decorate(decide_game(g), sport, g))
        except Exception as exc:  # noqa: BLE001 -- one bad game never sinks all
            logger.warning("bestbets_routes: decide failed gid=%s: %s",
                           g.get("game_id"), exc)
    return _envelope(sport, games, view.get("generated_at", "") or "")


def _kick_refresh(sport: str) -> None:
    """Start at most ONE background rebuild for *sport*; update cache only on an OK result.
    A failed/unavailable rebuild leaves the last-good entry in place (stale-never-green)."""
    with _view_lock:
        if sport in _view_refreshing:
            return
        _view_refreshing.add(sport)

    def _run() -> None:
        try:
            env = _compute_envelope(sport, None)
            if env.get("status") == "ok":
                _view_cache[sport] = (time.time(), env)
        except Exception as exc:  # noqa: BLE001 -- a daemon thread must never crash loud
            logger.warning("bestbets_routes: bg refresh %s failed: %s", sport, exc)
        finally:
            with _view_lock:
                _view_refreshing.discard(sport)

    threading.Thread(target=_run, name="bestbets-refresh-%s" % sport,
                     daemon=True).start()


@router.get(_PREFIX + "/{sport}/{game_id}")
@honest_route(extra={"candidates": [], "best_bets": []})
def bestbets_for_game(sport: str, game_id: str,
                      store_dir: Optional[str] = None) -> JSONResponse:
    """One game's execution decision object (candidates + best_bets + live + CLV)."""
    out_dir: Any = store_dir if store_dir is not None else _store_out_dir()
    try:
        game = build_game_edge(sport, game_id, store_out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("bestbets_routes /%s/%s: raised: %s", sport, game_id, exc)
        game = {"status": "unavailable", "game_id": game_id,
                "reason": "assembly error (%s)" % type(exc).__name__}
    if game.get("status") != "ok":
        body = {
            "sport": sport, "game_id": game_id, "status": "unavailable",
            "reason": game.get("reason", "game unavailable"),
            "candidates": [], "best_bets": [],
            "live": {"status": "unavailable",
                     "reason": game.get("reason", "game unavailable")},
            "clv": _clv_scoreboard(), "decision_note": decision_note(),
            "honest_note": HONEST_NOTE, "edge_claimed": False,
            "schema_version": SCHEMA_VERSION,
        }
        return JSONResponse(body)

    decision = _decorate(decide_game(game), sport, game)
    decision.update({
        "sport": sport,
        "clv": _clv_scoreboard(),
        "decision_note": decision_note(),
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
        "schema_version": SCHEMA_VERSION,
    })
    return JSONResponse(decision)


__all__ = ["router"]
