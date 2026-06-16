"""scripts.platformkit.live_read — the IN-GAME counterpart of the cohesive read.

Given a live GameState, fuses the two layers into ONE honest in-game read:
  - NUMBERS  -> the sport's PREDICTOR.predict_live re-prices the remaining markets with
    every VALIDATED in-game calibration wired in (NBA Elo-anchored mu + W156 temperature
    recal; MLB fitted r_home/r_away + W156 identity NULL; soccer + tennis W156 Platt).
    This is the in-game counterpart of predictor.to_jd -> cohesive_read (pregame, W151).
    Falls back gracefully to the raw gate-owned Repricer if a predictor errors / is missing.
  - INTELLIGENCE -> the brain's relevant IN-GAME concepts (InGameAdaptation, Closing-
    Execution, MomentumSwings, PressureResponse, LeadManagement, ... — person-free)

This makes the funnel work BOTH ways: cohesive_read (pregame) + live_read (in-game).
Exercised in the real rebuild by scripts.platformkit.system_map (per-sport in-game
section, sane demo state) — no longer orphaned to its own test+CLI.
The predictor/Repricer owns every number; concept retrieval is descriptive understanding
only. No un-gated pick, no edge — markets are efficient; calibration is not edge.

Public API:
    build_live_read(sport, state, root=None, top_k=6) -> dict
    render_markdown(read: dict) -> str
CLI:
    python -m scripts.platformkit.live_read --sport nba --demo
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from scripts.platformkit.live_repricer import GameState, get_repricer
from scripts.platformkit.concept_landscape import build_concept_landscape

# In-game-relevant concept families (the brain's "what matters live" lens).
_INGAME_FAMILIES = {
    "ingameadaptation", "closingexecution", "momentumswings", "pressureresponse",
    "transitiondynamics", "recoveryresilience", "leadmanagement", "adjustmentspeed",
    "resourceallocation", "gamephases", "errorcascades", "experiencecomposure",
}
_INGAME_QUERY = ("in-game adjustment momentum pressure closing lead protection "
                 "comeback transition late-game execution")
_BANNER = ("LIVE READ — calibrated in-game prediction (predictor.predict_live; validated "
           "recal) + in-game brain concepts. Machinery only; no edge; markets efficient.")

# ---------------------------------------------------------------------------
# Calibrated predictor wiring (the W157 cohesion fix). build_live_read used to call
# get_repricer(sport).reprice(state) DIRECTLY on the raw repricer, skipping every
# validated calibration each sport's predictor.predict_live now adds. We wire the
# predictors in here so the in-game surface is the VALIDATED CALIBRATED prediction,
# with a graceful fallback to the raw repricer if a predictor errors / data is missing.
# ---------------------------------------------------------------------------

# Lazy/cached predictor instances: building a predictor REPLAYS its whole corpus, so we
# cache one instance per sport (None = construction failed, never retried in this process).
_PREDICTOR_CACHE: Dict[str, Any] = {}


def _get_predictor(sport: str) -> Optional[Any]:
    """Return a cached per-sport predictor instance, or None if it cannot be built.

    Guarded + cached: the corpus is replayed at most ONCE per sport per process. A failed
    construction caches None so we don't repeatedly pay the (failing) replay cost.
    """
    if sport in _PREDICTOR_CACHE:
        return _PREDICTOR_CACHE[sport]
    inst: Optional[Any] = None
    try:
        if sport == "nba":
            from domains.basketball_nba.predictor import NBAPredictor  # noqa: PLC0415
            inst = NBAPredictor()
        elif sport == "mlb":
            from domains.mlb.predictor import MLBPredictor  # noqa: PLC0415
            inst = MLBPredictor()
        elif sport == "soccer":
            from domains.soccer.predictor import SoccerPredictor  # noqa: PLC0415
            inst = SoccerPredictor()
        elif sport == "tennis":
            from domains.tennis.predictor import TennisPredictor  # noqa: PLC0415
            inst = TennisPredictor()
    except Exception:  # noqa: BLE001 - missing data / import error -> graceful fallback
        inst = None
    _PREDICTOR_CACHE[sport] = inst
    return inst


def _demo_matchup(sport: str, pred: Any) -> Optional[tuple]:
    """Pick a deterministic representative (home, away) / (p1, p2) from the predictor's
    known entities so the demo GameState can be priced through predict_live. None if the
    predictor exposes no entities (then we fall back to the raw repricer)."""
    if sport in ("nba", "mlb", "soccer"):
        teams = getattr(pred, "teams", None) or []
        return (teams[0], teams[1]) if len(teams) >= 2 else None
    if sport == "tennis":
        names = list(getattr(pred, "name_to_id", {}) or [])
        return (names[0], names[1]) if len(names) >= 2 else None
    return None


def _surface_from_live(sport: str, live: Dict[str, Any], teams: tuple) -> Dict[str, Any]:
    """Map a predictor.predict_live() dict into the standard market-surface keys the
    renderer/consumers expect (win_home/away, match_win_p1/p2, 1X2_*, proj_*, over_*)."""
    s: Dict[str, Any] = {"_calibrated": True, "_predictor_matchup": list(teams)}
    note = live.get("honest_note") or live.get("recal_note")
    if note:
        s["_honest_note"] = note
    if sport == "nba":
        s["win_home"] = float(live["p_home_win"])
        s["win_away"] = float(live["p_away_win"])
        s["proj_total"] = float(live.get("proj_total", 0.0))
        s["proj_margin_home"] = float(live.get("proj_margin_home", 0.0))
        s["_win_home_raw"] = float(live.get("p_home_win_raw", live["p_home_win"]))
    elif sport == "mlb":
        s["ml_home"] = float(live["p_home_win"])
        s["ml_away"] = float(live["p_away_win"])
        s["rl_home_minus15"] = float(live.get("run_line_home_minus15", 0.0))
        s["proj_total"] = float(live.get("proj_remaining_runs", 0.0))
        s["_ml_home_raw"] = float(live.get("p_home_win_raw", live["p_home_win"]))
    elif sport == "soccer":
        s["1X2_home"] = float(live["p_home_win"])
        s["1X2_away"] = float(live["p_away_win"])
        s["1X2_draw"] = float(live.get("p_draw", 0.0))
        s["over_2.5"] = float(live.get("over_2.5", 0.0))
        s["under_2.5"] = float(live.get("under_2.5", 1.0 - float(live.get("over_2.5", 0.0))))
    elif sport == "tennis":
        s["match_win_p1"] = float(live["p1_match_win"])
        s["match_win_p2"] = float(live["p2_match_win"])
        s["_decided"] = bool(live.get("decided", False))
        s["_match_win_p1_uncalibrated"] = float(
            live.get("p1_match_win_uncalibrated", live["p1_match_win"]))
    return s


def _calibrated_surface(sport: str, state: GameState) -> Optional[Dict[str, Any]]:
    """Re-price the demo state through the sport's CALIBRATED predictor.predict_live.

    Maps the sport-agnostic GameState to each predictor's distinct predict_live signature
    (NBA: elapsed/score; MLB: inning/half/runs; soccer: minute/goals; tennis: set state).
    Returns None on any failure -- including predictor construction (_get_predictor) and
    demo-matchup selection (_demo_matchup, e.g. a malformed teams attr) -- so
    build_live_read can fall back to the raw repricer (W159 belt-and-suspenders).
    """
    try:
        pred = _get_predictor(sport)
        if pred is None:
            return None
        teams = _demo_matchup(sport, pred)
        if teams is None:
            return None
        h, a = teams
        if sport == "nba":
            live = pred.predict_live(h, a, float(state.elapsed_minutes),
                                     int(state.home_score), int(state.away_score))
        elif sport == "mlb":
            ip = float(state.extra.get("innings_played", max(1.0, state.elapsed_minutes / 20.0)))
            inning = max(1, int(ip) + 1)
            half = "bottom" if (ip - int(ip)) >= 0.5 else "top"
            live = pred.predict_live(h, a, inning=inning, half=half,
                                     home_runs=int(state.home_score),
                                     away_runs=int(state.away_score))
        elif sport == "soccer":
            live = pred.predict_live(h, a, float(state.elapsed_minutes),
                                     int(state.home_score), int(state.away_score))
        elif sport == "tennis":
            sets_1 = int(state.extra.get("sets_1", state.home_score))
            sets_2 = int(state.extra.get("sets_2", state.away_score))
            live = pred.predict_live(h, a, sets_1, sets_2)
        else:
            return None
    except Exception:  # noqa: BLE001 - any predict_live failure -> raw-repricer fallback
        return None
    if not isinstance(live, dict):
        return None
    return _surface_from_live(sport, live, teams)


def build_live_read(sport: str, state: GameState,
                    root: Optional[Any] = None, top_k: int = 6) -> Dict[str, Any]:
    """Assemble the in-game read: CALIBRATED predictor surface + relevant in-game concepts.

    The surface is the sport's predictor.predict_live output (every validated in-game
    recalibration wired in), with a GRACEFUL FALLBACK to the raw gate-owned Repricer if the
    predictor errors or its data is missing. surface['_calibrated'] records which path ran.
    """
    sport_l = sport.lower()
    surface = _calibrated_surface(sport_l, state)
    if surface is None:
        # Graceful degrade: the validated predictor is unavailable -> raw repricer.
        try:
            surface = get_repricer(sport_l).reprice(state)
            if isinstance(surface, dict):
                surface.setdefault("_calibrated", False)
        except Exception:  # noqa: BLE001
            surface = {"status": "repricer_error", "_calibrated": False}
    land = build_concept_landscape(sport_l, query=_INGAME_QUERY, root=root, top_k=top_k * 3)
    # Keep only in-game-relevant family hits, capped at top_k.
    concepts = [h for h in land.get("top_hits", [])
                if h.get("family", "").lower() in _INGAME_FAMILIES][:top_k]
    return {
        "sport": sport_l,
        "banner": _BANNER,
        "state": {"elapsed_minutes": getattr(state, "elapsed_minutes", None),
                  "score": (state.home_score, state.away_score),
                  "extra": getattr(state, "extra", {})},
        "surface": surface,
        "ingame_concepts": concepts,
        "edge_claimed": False,
    }


def _fmt_surface(surface: Dict[str, Any]) -> List[str]:
    """Render the most relevant re-priced lines compactly, per sport shape."""
    if not isinstance(surface, dict) or surface.get("status"):
        return [f"- _(repricer: {surface.get('status', 'unavailable')})_"]
    L: List[str] = []
    # Win/match probabilities (whichever the sport emits).
    for k_home, k_away, lbl in (("win_home", "win_away", "Win prob"),
                                ("ml_home", "ml_away", "Moneyline"),
                                ("match_win_p1", "match_win_p2", "Match win"),
                                ("1X2_home", "1X2_away", "1X2")):
        if k_home in surface:
            extra = ""
            if "1X2_draw" in surface and lbl == "1X2":
                extra = f"  draw={surface['1X2_draw']:.3f}"
            L.append(f"- {lbl}: home/p1={surface[k_home]:.3f}  away/p2={surface[k_away]:.3f}{extra}")
            break
    if "proj_margin_home" in surface:
        L.append(f"- Projected: margin={surface['proj_margin_home']:+.1f}  total={surface.get('proj_total', 0):.0f}")
    # A couple of totals lines if present.
    overs = sorted(k for k in surface if k.startswith("over_"))
    for k in overs[:2]:
        L.append(f"- {k}: {surface[k]:.3f}")
    return L or ["- _(no standard market keys)_"]


def render_markdown(read: Dict[str, Any]) -> str:
    """Render the live read as ONE Markdown document."""
    sport = read.get("sport", "unknown").upper()
    st = read.get("state", {})
    L: List[str] = [
        f"# Live Read — {sport}", "",
        f"> **{read.get('banner', '')}**", "",
        f"**State:** score={st.get('score')}  elapsed={st.get('elapsed_minutes')}  extra={st.get('extra')}",
        "",
        "## Re-priced surface _(gate-owned engine; not a pick)_",
    ]
    L += _fmt_surface(read.get("surface", {}))
    note = read.get("surface", {}).get("_honest_note")
    if note:
        L += ["", f"> _{note}_"]
    L += ["", "## Relevant in-game concepts _(brain; descriptive understanding)_"]
    concepts = read.get("ingame_concepts", [])
    if concepts:
        for c in concepts:
            L.append(f"- **{c['title']}** _({c['family']})_  `{c['provenance']}`")
    else:
        L.append("- _(no in-game concept nodes matched for this sport)_")
    L += ["", "> The engine owns every number; concepts are understanding only. "
          "No un-gated pick; no edge claimed.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    import sys

    from scripts.platformkit.live_read_cli import _cli  # noqa: PLC0415

    sys.exit(_cli())
