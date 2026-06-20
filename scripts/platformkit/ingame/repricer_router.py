"""scripts.platformkit.ingame.repricer_router -- sport-blind in-game reprice router.

reprice(sport, game_state, pregame_record, *, surface=None) composes:
  * the EXISTING per-sport repricer (domains.basketball_nba.repricer.NBARepricer via
    scripts.platformkit.live_repricer.get_repricer) for the per-market surface, and
  * scripts.platformkit.ingame.blend_apply.apply_surface for the freshness-weighted
    win-prob blend (pregame prior -> realized live state),
into one clean output. It does NOT reimplement the repricing or blend math.

GUARDED + NEVER RAISES: an unknown sport, a missing pregame prior, or any internal
error returns a clean {'available': False, ...} dict -- the live loop must never sink.

HONEST in-game invariants (binding):
  * Only validated lever = FRESHNESS. The blended win-prob variance SHRINKS as the
    game progresses (Q1 wide -> Q4 tight); the seed surface enforces it.
  * Pooled naive in-game win-prob has tested WORSE than a coin flip on PBP replay;
    this router only EMITS a number -- it does not assert it beats the close. That
    verdict is a gate question (fit_w_surface / eval_gate), not answered here.
  * No dollar edge anywhere. EDGE_CLAIMED is False. Markets are efficient.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; no network.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from scripts.platformkit.ingame.blend_apply import apply_surface

EDGE_CLAIMED = False

# Surface seeds live next to this module. Each sport may seed its own blend grid.
_SURFACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "surfaces")

# Alias map mirrors ingest_router so callers can pass platform ids interchangeably.
_ALIASES = {"basketball_nba": "nba", "worldcup": "soccer_intl", "wc": "soccer_intl"}

_SURFACE_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}


def _norm_sport(sport: str) -> str:
    s = str(sport or "").lower()
    return _ALIASES.get(s, s)


def load_surface(sport: str) -> Optional[Dict[str, Any]]:
    """Load (and cache) the seed blend surface for *sport*, or None if absent."""
    sport = _norm_sport(sport)
    if sport in _SURFACE_CACHE:
        return _SURFACE_CACHE[sport]
    path = os.path.join(_SURFACE_DIR, "%s.json" % sport)
    surf: Optional[Dict[str, Any]] = None
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="ascii") as fh:
                surf = json.load(fh)
    except Exception:  # pragma: no cover - defensive; a bad seed must not crash
        surf = None
    _SURFACE_CACHE[sport] = surf
    return surf


def _unavailable(sport: str, reason: str) -> Dict[str, Any]:
    return {
        "available": False, "sport": sport, "reason": reason,
        "probs": {}, "markets": [], "variance": None, "basis": "unavailable",
        "edge_claimed": EDGE_CLAIMED,
        "_honest_note": (
            "In-game reprice unavailable (no edge claimed; re-pricing machinery "
            "only). A missing prior / unknown sport returns this dict gracefully."
        ),
    }


def _coerce_repricer_state(game_state: Any, pregame_record: Dict[str, Any]) -> Any:
    """Adapt a sport-blind GameState into the duck-typed shape the existing NBA
    repricer reads (elapsed_minutes / home_score / away_score / pregame_params).

    Reuses fraction_elapsed() (the validated freshness lever) so we never recompute
    elapsed time inconsistently with the rest of the spine.
    """
    reg_min = float(pregame_record.get("regulation_min", 48.0))
    frac = None
    fe = getattr(game_state, "fraction_elapsed", None)
    if callable(fe):
        frac = fe()
    elapsed_min = reg_min * float(frac) if frac is not None else 0.0
    pp = dict(pregame_record.get("pregame_params") or {})

    class _RState:
        home_score = int(getattr(game_state, "home_score", 0) or 0)
        away_score = int(getattr(game_state, "away_score", 0) or 0)
        elapsed_minutes = elapsed_min
        pregame_params = pp

    return _RState()


def _markets_from_repricer(rep: Dict[str, Any]) -> list:
    """Flatten the per-sport repricer dict into a list of repriced market rows.

    Skips private (_-prefixed) metadata keys. Each row: {market, prob}.
    """
    out = []
    for k, v in rep.items():
        if k.startswith("_") or not isinstance(v, (int, float)):
            continue
        if k in ("proj_margin_home", "proj_total"):
            out.append({"market": k, "value": float(v)})
        else:
            out.append({"market": k, "prob": float(v)})
    return out


def reprice(sport: str, game_state: Any, pregame_record: Optional[Dict[str, Any]],
            *, surface: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Reprice live markets for *sport* from realized state + a pregame prior.

    Parameters
    ----------
    sport : str            platform sport id (aliases accepted; e.g. basketball_nba).
    game_state : GameState  the realized live snapshot (duck-typed; fraction_elapsed).
    pregame_record : dict   the calibrated pregame prior. Keys read:
        'p0' or 'win_home'  : P(home win) prior (required for the blend);
        'variance'          : optional pregame win-prob variance to shrink;
        'pregame_params'    : optional repricer params (mu_home/away, *_sigma);
        'regulation_min'    : optional regulation minutes (default 48).
    surface : dict          optional override blend surface; else the sport seed.

    Returns
    -------
    dict:
        available : bool
        probs     : {p_home, p_away, w, p_live}  (the freshness-blended win-prob)
        markets   : [ {market, prob|value}, ... ]  per-market repriced surface
        variance  : float  win-prob variance, SHRINKS as the game progresses
        basis     : 'blend' | 'pregame_fallback' | 'unavailable'
        remaining_frac, sport, edge_claimed(False), _honest_note

    GUARDED: unknown sport or missing prior -> a clean unavailable result; never
    raises.
    """
    sport = _norm_sport(sport)
    if not isinstance(pregame_record, dict) or not pregame_record:
        return _unavailable(sport, "missing pregame prior")
    if "p0" not in pregame_record and "win_home" not in pregame_record:
        return _unavailable(sport, "pregame prior has no win-prob (p0/win_home)")

    surf = surface if surface is not None else load_surface(sport)
    if surf is None:
        return _unavailable(sport, "no blend surface seeded for sport")

    try:
        # 1) Freshness-weighted win-prob blend (the validated lever).
        blended = apply_surface(pregame_record, game_state, surf)

        # 2) Per-market surface from the EXISTING per-sport repricer (best-effort).
        markets: list = []
        try:
            from scripts.platformkit.live_repricer import get_repricer
            rstate = _coerce_repricer_state(game_state, pregame_record)
            rep = get_repricer(sport).reprice(rstate)
            if isinstance(rep, dict) and rep.get("status") != "not_wired":
                markets = _markets_from_repricer(rep)
        except Exception:  # pragma: no cover - per-market surface is optional
            markets = []

        return {
            "available": True, "sport": sport,
            "probs": {
                "p_home": blended["p_home"], "p_away": blended["p_away"],
                "w": blended["w"], "p_live": blended["p_live"],
            },
            "markets": markets,
            "variance": blended["variance"],
            "remaining_frac": blended["remaining_frac"],
            "basis": blended["basis"],
            "edge_claimed": EDGE_CLAIMED,
            "_honest_note": (
                "Freshness-blended in-game number (calibration on realized state, "
                "no dollar edge). Variance shrinks as the game progresses. Whether "
                "it beats the close is a gate question (fit_w_surface / eval_gate)."
            ),
        }
    except Exception as exc:  # pragma: no cover - router must never sink the loop
        return _unavailable(sport, "reprice error: %s" % type(exc).__name__)
