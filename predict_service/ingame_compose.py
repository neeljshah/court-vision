"""predict_service.ingame_compose -- merge live_state + boxscore + ingame prediction.

Produces the composed response for GET /api/ingame/{sport}/{game_id}/full by
pulling from three independent read-only sources:

  1. ingame_live_state.live_state()  -> score / frac_elapsed / p0 from ESPN
  2. boxscore_read.fetch_box()       -> player rows from the NBA CDN (NBA only)
  3. ingame_serve.serve_ingame()     -> calibrated win-prob from the persisted model

The merge is ADDITIVE and HONEST:
  * Each source degrades independently; a missing source contributes None / [].
  * clv_status is always INSUFFICIENT_DATA in offseason or when no in-play prices
    are available; never fabricated.
  * No $ field anywhere; CALIBRATION only (markets are efficient).
  * An optional W2 prop_proj dict may be injected for full compose when that
    workstream ships (defaults to None -> absent from response).

The compose function is pure (all I/O is injected), so it is 100% unit-testable
without network access.

compose(sport, game_id, *, live_fn, box_fn, serve_fn, p0) -> dict
    Returns the full response dict.  Never raises; degrades gracefully.

INVARIANTS: <=300 LOC; ASCII-only; no src/kernel/api imports; no network I/O;
no $ field; stale-never-green.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# CLV status honest constants -- never fabricated.
_CLV_INSUFFICIENT = "INSUFFICIENT_DATA"
_CLV_NOTE = (
    "In-play prices (Kalshi/Polymarket) are not yet available for this sport/game. "
    "CLV vs closing-line CANNOT be computed. Showing INSUFFICIENT_DATA honestly. "
    "No edge is claimed."
)

# Honest note surfaced on every response.
_HONEST_NOTE = (
    "Calibrated decision-support only. Markets are efficient; no $ edge is claimed. "
    "In-game CLV may be INSUFFICIENT_DATA -- shown honestly, never fabricated."
)


# ------------------------------------------------------------------ helpers

def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clv_status(sport: str, live: Optional[dict]) -> str:
    """Always INSUFFICIENT_DATA until liquid in-play prices are wired.

    NBA is offseason; the in-play capture loop excludes NBA (DEFAULT_SPORTS excludes
    it -- map_ingame line 63).  We never fabricate a CLV.  When live prices arrive
    this function can be extended; until then it is always INSUFFICIENT_DATA.
    """
    return _CLV_INSUFFICIENT


# ------------------------------------------------------------------ compose

def compose(
    sport: str,
    game_id: str,
    *,
    live_fn: Callable,            # live_state(sport, game_id, p0=p0) -> dict | None
    box_fn: Callable,             # fetch_box(game_id) -> (GameMeta, players) | (meta, [])
    serve_fn: Callable,           # serve_ingame(sport, state_diff, frac_elapsed, p0) -> dict
    p0: Optional[float] = None,
    prop_proj: Optional[Dict[str, Any]] = None,  # optional W2 prop projections
) -> Dict[str, Any]:
    """Merge live state + boxscore + in-game prediction into one composed response.

    All sources degrade independently:
      * live -> None: win_prob falls back to p0; live_state block is absent.
      * box  -> []:   players block is []; game_meta carries UNAVAILABLE status.
      * serve fails:  served block carries the honest fallback from serve_ingame.
    clv_status is always INSUFFICIENT_DATA until liquid in-play prices are wired.
    """
    out: Dict[str, Any] = {
        "sport":       sport,
        "game_id":     game_id,
        "honest_note": _HONEST_NOTE,
        "edge_claimed": False,
    }

    # --- 1. Live state (ESPN scoreboard) ------------------------------------
    try:
        live = live_fn(sport, game_id, p0=p0)
    except Exception:  # noqa: BLE001
        live = None

    if live is not None:
        out["live_state"] = {
            "home":          live.get("home"),
            "away":          live.get("away"),
            "state_diff":    _safe_float(live.get("state_diff")),
            "frac_elapsed":  _safe_float(live.get("frac_elapsed")),
            "p0":            _safe_float(live.get("p0")),
            "p0_source":     live.get("p0_source"),
            "status":        live.get("status"),
        }
        p0_for_serve = _safe_float(live.get("p0")) if p0 is None else p0
        state_diff = _safe_float(live.get("state_diff"))
        frac_elapsed = _safe_float(live.get("frac_elapsed"))
    else:
        out["live_state"] = None
        p0_for_serve = p0
        state_diff = None
        frac_elapsed = None

    # --- 2. Win-prob (served in-game model) --------------------------------
    try:
        served = serve_fn(sport,
                          state_diff=state_diff,
                          frac_elapsed=frac_elapsed,
                          p0=p0_for_serve)
    except Exception as exc:  # noqa: BLE001
        served = {"p_win": p0_for_serve, "model": "error",
                  "error": str(exc), "provenance": []}
    out["win_prob"] = served

    # --- 3. Boxscore (NBA CDN; degrades for non-NBA or unavailable) --------
    try:
        game_meta, players = box_fn(game_id)
    except Exception:  # noqa: BLE001
        game_meta = {
            "game_id": game_id, "game_status": "UNAVAILABLE",
            "period": 0, "clock": "", "home_score": 0, "away_score": 0,
        }
        players = []
    out["game_meta"] = game_meta
    out["players"] = players

    # --- 4. CLV status (honest; never fabricated) --------------------------
    out["clv_status"] = _clv_status(sport, live)
    out["clv_note"]   = _CLV_NOTE

    # --- 5. Optional W2 prop projections (absent until W2 ships) -----------
    if prop_proj is not None:
        out["prop_proj"] = prop_proj

    return out


# ------------------------------------------------------------------ convenience thin wrappers
# (used by ingame_mounts to supply the default I/O functions)

def _default_live_fn(sport: str, game_id: str, p0: Optional[float] = None) -> Optional[dict]:
    try:
        from scripts.platformkit.ingame.ingame_live_state import live_state  # noqa: PLC0415
        return live_state(sport, game_id, p0=p0)
    except Exception:  # noqa: BLE001
        return None


def _default_box_fn(game_id: str):  # noqa: ANN201
    try:
        from scripts.platformkit.ingame.boxscore_read import fetch_box  # noqa: PLC0415
        return fetch_box(game_id)
    except Exception:  # noqa: BLE001
        meta = {
            "game_id": game_id, "game_status": "UNAVAILABLE",
            "period": 0, "clock": "", "home_score": 0, "away_score": 0,
        }
        return meta, []


def _default_serve_fn(sport: str, *,
                      state_diff: Optional[float],
                      frac_elapsed: Optional[float],
                      p0: Optional[float]) -> dict:
    try:
        from scripts.platformkit.ingame.ingame_serve import serve_ingame  # noqa: PLC0415
        return serve_ingame(sport,
                            state_diff=state_diff,
                            frac_elapsed=frac_elapsed,
                            p0=p0)
    except Exception as exc:  # noqa: BLE001
        return {"p_win": p0, "model": "unavailable", "error": str(exc), "provenance": []}


def compose_default(sport: str, game_id: str, *, p0: Optional[float] = None) -> Dict[str, Any]:
    """compose() wired to the real I/O functions (used by ingame_mounts)."""
    return compose(
        sport, game_id,
        live_fn=_default_live_fn,
        box_fn=_default_box_fn,
        serve_fn=_default_serve_fn,
        p0=p0,
    )


__all__ = [
    "compose",
    "compose_default",
    "_default_live_fn",
    "_default_box_fn",
    "_default_serve_fn",
    "_CLV_INSUFFICIENT",
]
