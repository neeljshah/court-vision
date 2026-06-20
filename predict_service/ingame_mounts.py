"""predict_service.ingame_mounts -- register the in-game read routes (guarded).

Keeps predict_service.app under the <=300 LOC budget by factoring the in-game
read endpoints into one place, mirroring the predict_service.extra_mounts /
core_mounts register(app) pattern:

  * GET /api/ingame/{sport}/{game_id}       -- live CALIBRATED win-prob via the
    served in-game model (state_diff/frac_elapsed from keyless feed + p0).
  * GET /api/ingame/gates                   -- 4-sport in-game calibration gate
    verdicts read from data/frontend/ingame/*.json.
  * GET /api/ingame/{sport}/{game_id}/full  -- composed response: live score +
    win-prob tick + player boxscore + honest in-game CLV state (W4 addition).
  * Mounts boxscore_routes router:
    GET /api/boxscore/{sport}/{game_id}     -- player pts/reb/ast/min live box.

register(app) is called once from predict_service.app. All routes are read-only,
never raise, and degrade to an honest 'unavailable' / null-verdict sentinel. No $
field anywhere; CALIBRATION label only (markets are efficient, no edge claimed).
clv_status is always INSUFFICIENT_DATA until liquid in-play prices are wired.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $-edge fabrication; reuse the canonical store verbatim.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi.responses import JSONResponse

from predict_service import store

_STORE_OUT_DIR_ENV = "PREDICT_SERVICE_STORE_DIR"

# 4-sport in-game calibration gate verdict files (under data/frontend/ingame/).
_GATE_FILES = {
    "nba": "layer_gate_nba.json",
    "mlb": "gate_mlb.json",
    "soccer": "gate_soccer.json",
    "tennis": "gate_tennis.json",
}


def _store_out_dir() -> Optional[str]:
    """Resolve the store-root override env var, or None to use the store default."""
    val = os.environ.get(_STORE_OUT_DIR_ENV)
    return val or None


def _home_p0(record) -> Optional[float]:  # noqa: ANN001
    """Pull a home-side leak-free pregame prior from a record's pregame_probs.

    Tries common keys ('home_ml','home','home_win','p_home'); None if absent.
    """
    pp = getattr(record, "pregame_probs", None) or {}
    for k in ("home_ml", "home", "home_win", "p_home", "p_home_win"):
        if k in pp:
            try:
                return float(pp[k])
            except (TypeError, ValueError):
                return None
    return None


def _mount_boxscore_router(app) -> None:  # noqa: ANN001
    """Mount the /api/boxscore/{sport}/{game_id} router (guarded)."""
    try:
        from predict_service.frontend.boxscore_routes import router as _bsr  # noqa: PLC0415
        app.include_router(_bsr)
    except Exception as exc:  # noqa: BLE001
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "ingame_mounts: boxscore_routes not mounted (%s: %s)",
            type(exc).__name__, exc)

        from fastapi.responses import JSONResponse as _JR  # noqa: PLC0415

        @app.get("/api/boxscore/{sport}/{game_id}")
        def _boxscore_unavailable(sport: str, game_id: str) -> _JR:  # noqa: ANN202
            return _JR({"status": "unavailable",
                        "sport": sport, "game_id": game_id,
                        "game_meta": None, "players": [],
                        "reason": "boxscore_routes failed to load",
                        "edge_claimed": False}, status_code=503)


def register(app) -> None:  # noqa: ANN001
    """Mount the in-game read routes onto *app* (called once from predict_service.app)."""

    # Mount boxscore router (guarded) before the inline routes.
    _mount_boxscore_router(app)

    @app.get("/api/ingame/{sport}/{game_id}")
    def ingame_game(sport: str, game_id: str) -> JSONResponse:  # noqa: ANN202
        """Live in-game CALIBRATED win-prob for *sport*/*game_id* via the served model.

        Extracts live (state_diff, frac_elapsed) from the keyless ESPN feed, pulls the
        leak-free pregame prior p0 from the latest snapshot (if present), and serves the
        persisted in-game model. The served model NEVER applies an unproven prior as proven
        (MLB serves BASE only; soccer marks the prior experimental). No $ field; CALIBRATION
        only. Degrades to p0 / unavailable honestly -- never fabricates a live state.
        """
        try:
            from scripts.platformkit.ingame.ingame_serve import serve_ingame  # noqa: PLC0415
            from scripts.platformkit.ingame.ingame_live_state import live_state  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"status": "unavailable",
                                 "reason": "ingame serving module not importable: %s" % exc})
        p0 = None
        env = store.read_latest(sport, out_dir=_store_out_dir())
        if env.status == "ok":
            rec = next((p for p in env.predictions if p.game_id == game_id), None)
            if rec is not None:
                p0 = _home_p0(rec)
        live = live_state(sport, game_id, p0=p0)
        if live is None:
            served = serve_ingame(sport, state_diff=None, frac_elapsed=None, p0=p0)
            return JSONResponse({"status": "no_live_state", "sport": sport,
                                 "game_id": game_id, "p0": p0, "served": served})
        served = serve_ingame(sport, state_diff=live["state_diff"],
                              frac_elapsed=live["frac_elapsed"], p0=live["p0"])
        return JSONResponse({"status": "ok", "sport": sport, "game_id": game_id,
                             "live_state": live, "served": served})

    @app.get("/api/ingame/gates")
    def ingame_gates() -> JSONResponse:  # noqa: ANN202
        """4-sport in-game calibration gate verdicts. Never raises; degrades gracefully."""
        import json as _json  # noqa: PLC0415
        import pathlib as _pathlib  # noqa: PLC0415

        base = _pathlib.Path(__file__).parent.parent / "data" / "frontend" / "ingame"
        sports = []
        for sport, fname in _GATE_FILES.items():
            fp = base / fname
            entry: dict = {"sport": sport, "verdict": None, "vs_close": None,
                           "honest_label": "CALIBRATION only -- not a market edge"}
            try:
                d = _json.loads(fp.read_text())
                entry["verdict"] = d.get("verdict")
                vc = d.get("vs_close")
                entry["vs_close"] = vc if isinstance(vc, str) else (
                    vc.get("verdict") if isinstance(vc, dict) else None
                )
            except Exception:  # noqa: BLE001 -- degrade gracefully
                entry["verdict"] = None
            sports.append(entry)
        return JSONResponse({
            "status": "ok",
            "sports": sports,
            "honest_note": (
                "In-game calibration gate verdicts only. "
                "REPLICATED/SHIP = model is calibrated OOS. "
                "vs_close UNPROVEN = no in-play odds available to benchmark against. "
                "No $ edge is claimed."
            ),
            "edge_claimed": False,
        })

    @app.get("/api/ingame/{sport}/{game_id}/full")
    def ingame_full(sport: str, game_id: str) -> JSONResponse:  # noqa: ANN202
        """Composed in-game response: score + win-prob + boxscore + CLV status.

        Merges three independent read-only sources:
          1. ESPN keyless scoreboard -> live score / frac_elapsed / p0
          2. NBA CDN (basketball only) -> player boxscore rows
          3. Persisted in-game model  -> calibrated win-prob

        clv_status is always INSUFFICIENT_DATA (NBA offseason; no liquid in-play
        prices available to benchmark against). Shown honestly, never fabricated.
        No $ field; CALIBRATION only.
        """
        p0 = None
        try:
            env = store.read_latest(sport, out_dir=_store_out_dir())
            if env.status == "ok":
                rec = next((p for p in env.predictions if p.game_id == game_id), None)
                if rec is not None:
                    p0 = _home_p0(rec)
        except Exception:  # noqa: BLE001
            pass

        try:
            from predict_service.ingame_compose import compose_default  # noqa: PLC0415
            result = compose_default(sport, game_id, p0=p0)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({
                "sport": sport, "game_id": game_id,
                "status": "unavailable",
                "reason": str(exc),
                "edge_claimed": False,
            }, status_code=503)

        return JSONResponse(result)


__all__ = ["register"]
