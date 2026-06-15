"""scripts.platformkit.live_read — the IN-GAME counterpart of the cohesive read.

Given a live GameState, fuses the two layers into ONE honest in-game read:
  - NUMBERS  -> the sport's Repricer re-prices the remaining markets (gate-owned engine)
  - INTELLIGENCE -> the brain's relevant IN-GAME concepts (InGameAdaptation, Closing-
    Execution, MomentumSwings, PressureResponse, LeadManagement, ... — person-free)

This makes the funnel work BOTH ways: cohesive_read (pregame) + live_read (in-game).
Exercised in the real rebuild by scripts.platformkit.system_map (per-sport in-game
section, sane demo state) — no longer orphaned to its own test+CLI.
The Repricer owns every number; concept retrieval is descriptive understanding only.
No un-gated pick, no edge — markets are efficient; calibration is not edge.

Public API:
    build_live_read(sport, state, root=None, top_k=6) -> dict
    render_markdown(read: dict) -> str
CLI:
    python -m scripts.platformkit.live_read --sport nba --demo
"""
from __future__ import annotations

import argparse
import json
import sys
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
_BANNER = ("LIVE READ — re-priced surface (gate-owned engine) + in-game brain concepts. "
           "Machinery only; no edge; markets efficient.")


def build_live_read(sport: str, state: GameState,
                    root: Optional[Any] = None, top_k: int = 6) -> Dict[str, Any]:
    """Assemble the in-game read: re-priced surface + relevant in-game concepts."""
    sport_l = sport.lower()
    try:
        surface = get_repricer(sport_l).reprice(state)
    except Exception:  # noqa: BLE001
        surface = {"status": "repricer_error"}
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


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="live_read: in-game re-priced surface + brain concepts; no edge.")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--elapsed", type=float, default=24.0)
    ap.add_argument("--home", type=int, default=58)
    ap.add_argument("--away", type=int, default=50)
    ap.add_argument("--demo", action="store_true", help="use sport-appropriate demo params")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    sport = a.sport.lower()
    demo_params = {
        "nba": {"mu_home": 114, "mu_away": 112},
        "mlb": {"lam_home": 4.6, "lam_away": 4.3},
        "soccer": {"lam_home": 1.6, "lam_away": 1.2},
        "tennis": {"best_of": 3, "p_set": 0.55},
    }
    # The --elapsed/--home/--away defaults are NBA-shaped (24min, 58/50 points).
    # Fed raw to MLB/Soccer/Tennis they produce nonsensical in-game states (58 runs,
    # 24 innings, 58 goals, an instantly-decided match). When the user leaves them
    # untouched, substitute a sane per-sport mid-event demo; otherwise honour the
    # custom values (clamping tennis sets so a match can never instantly finish).
    untouched = (a.elapsed == 24.0 and a.home == 58 and a.away == 50)
    _SANE = {  # elapsed, home, away (mid-event, in-progress)
        "nba": (24.0, 58, 50), "mlb": (5.0, 3, 2),
        "soccer": (60.0, 1, 1), "tennis": (1.0, 1, 0),
    }
    elapsed = a.elapsed
    home, away = a.home, a.away
    if untouched and sport in _SANE:
        elapsed, home, away = _SANE[sport]
    extra = {}
    if sport == "mlb":
        extra = {"innings_played": elapsed}
    elif sport == "tennis":
        sets_to_win = int(demo_params["tennis"]["best_of"]) // 2 + 1
        home = max(0, min(home, sets_to_win - 1))
        away = max(0, min(away, sets_to_win - 1))
        extra = {"sets_1": home, "sets_2": away}
    state = GameState(sport=sport, elapsed_minutes=elapsed,
                      home_score=home, away_score=away,
                      pregame_params=demo_params.get(sport, {}) if a.demo else {},
                      extra=extra)
    read = build_live_read(sport, state)
    if a.json:
        print(json.dumps(read, indent=2, default=str))
    else:
        print(render_markdown(read))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
