"""scripts.platformkit.predict_matchup -- the ONE buyer-facing CLI.

Run it for an arbitrary matchup in any of the 4 sports and get a calibrated PRE-GAME
prediction, plus an IN-GAME prediction if a live state is supplied. Honest framing only:
pregame MATCHES the devigged close (calibration/sharpness, not a fabricated edge); in-game
ADDS the realized state through the validated repricer + in-game recalibrator. No $ edge.

Reuses the cached, guarded predictor factory (scripts.platformkit.predictor_jd._build_predictor):
a fresh clone with no gitignored corpus degrades cleanly -> prints an "unavailable" note and
exits 0 (never raises, never fabricates numbers).

Usage:
  python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL
  python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL \
         --elapsed 24 --home-score 55 --away-score 50 --markdown

INVARIANTS: never edit src/ or kernel/; reuse the domain predictors; <=300 LOC; no secrets.
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.predictor_jd import _build_predictor

_SPORTS = ("nba", "mlb", "soccer", "tennis")
_ALIASES = {"basketball_nba": "nba"}

_UNAVAILABLE = (
    "corpus unavailable on this clone (real per-sport corpora are local/gitignored); "
    "see docs. No prediction produced; this is expected on a fresh public clone."
)


def build_parser() -> argparse.ArgumentParser:
    """The buyer-facing argument parser (pure -- no corpus required to construct)."""
    ap = argparse.ArgumentParser(
        prog="predict_matchup",
        description="Calibrated pre-game (+ optional in-game) prediction for any matchup.")
    ap.add_argument("--sport", required=True,
                    choices=list(_SPORTS) + list(_ALIASES.keys()))
    ap.add_argument("--home", required=True, help="home team / player p1")
    ap.add_argument("--away", required=True, help="away team / player p2")
    # in-game state (sport-appropriate; partial/inapplicable -> ignored with a note)
    ap.add_argument("--elapsed", type=float, default=None,
                    help="nba minutes 0-48 / soccer minute 0-90")
    ap.add_argument("--inning", type=int, default=None, help="mlb inning (1-9+)")
    ap.add_argument("--half", choices=["top", "bottom"], default=None, help="mlb half")
    ap.add_argument("--home-score", type=int, default=None, dest="home_score")
    ap.add_argument("--away-score", type=int, default=None, dest="away_score")
    ap.add_argument("--sets-home", type=int, default=None, dest="sets_home")
    ap.add_argument("--sets-away", type=int, default=None, dest="sets_away")
    ap.add_argument("--games-home", type=int, default=None, dest="games_home")
    ap.add_argument("--games-away", type=int, default=None, dest="games_away")
    ap.add_argument("--surface", default="Hard", help="tennis surface (default Hard)")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="JSON output (default)")
    fmt.add_argument("--markdown", action="store_true", help="Markdown output")
    return ap


def _norm_sport(sport: str) -> str:
    s = sport.lower()
    return _ALIASES.get(s, s)


def live_kwargs(sport: str, a: argparse.Namespace) -> Optional[Dict[str, Any]]:
    """Map the generic CLI flags onto a sport's predict_live(**kwargs).

    Returns the kwargs dict if a COMPLETE, applicable live state was supplied, else None
    (so the CLI cleanly prints pregame-only with a note). Pure -- no corpus needed.
    """
    s = _norm_sport(sport)
    hs, as_ = a.home_score, a.away_score
    if s == "nba":
        if a.elapsed is None or hs is None or as_ is None:
            return None
        return {"elapsed_minutes": float(a.elapsed), "home_score": int(hs),
                "away_score": int(as_)}
    if s == "soccer":
        if a.elapsed is None or hs is None or as_ is None:
            return None
        return {"minute": float(a.elapsed), "home_goals": int(hs), "away_goals": int(as_)}
    if s == "mlb":
        if a.inning is None or a.half is None or hs is None or as_ is None:
            return None
        return {"inning": int(a.inning), "half": str(a.half), "home_runs": int(hs),
                "away_runs": int(as_)}
    if s == "tennis":
        if a.sets_home is None or a.sets_away is None:
            return None
        kw: Dict[str, Any] = {"sets_p1": int(a.sets_home), "sets_p2": int(a.sets_away),
                              "surface": a.surface}
        if a.games_home is not None and a.games_away is not None:
            kw["games_p1"] = int(a.games_home)
            kw["games_p2"] = int(a.games_away)
        return kw
    return None


def _p_home_of(d: Dict[str, Any]) -> Optional[float]:
    """Normalize the home/p1 win prob across sports (tennis uses p1_match_win)."""
    for k in ("p_home_win", "p1_match_win"):
        if k in d:
            return float(d[k])
    return None


def _pregame_block(sport: str, pred: Any, home: str, away: str,
                   surface: str) -> Dict[str, Any]:
    s = _norm_sport(sport)
    raw = pred.predict(home, away, surface=surface) if s == "tennis" \
        else pred.predict(home, away)
    block: Dict[str, Any] = {"p_home_win": _p_home_of(raw)}
    if "p_draw" in raw:
        block["p_draw"] = raw["p_draw"]
    # a compact, sport-appropriate market summary off predict()
    if s == "nba":
        block["total_mean"] = raw.get("total_mean")
        block["margin_home"] = raw.get("margin_home")
    elif s == "mlb":
        block["expected_total"] = raw.get("expected_total")
        block["expected_runs_home"] = raw.get("expected_runs_home")
        block["expected_runs_away"] = raw.get("expected_runs_away")
    elif s == "soccer":
        block["over_2.5"] = raw.get("over_2.5")
        block["lam_home"] = raw.get("lam_home")
        block["lam_away"] = raw.get("lam_away")
    elif s == "tennis":
        block["total_games_mean"] = raw.get("total_games_mean")
        block["straight_sets_p1"] = raw.get("straight_sets_p1")
    block["honest_note"] = raw.get("honest_note")
    return block


def _ingame_block(sport: str, pred: Any, home: str, away: str,
                  kw: Dict[str, Any]) -> Dict[str, Any]:
    s = _norm_sport(sport)
    live = pred.predict_live(home, away, **kw)
    block: Dict[str, Any] = {"p_home_win": _p_home_of(live)}
    if "p_draw" in live:
        block["p_draw"] = live["p_draw"]
    # pregame comparison field the in-game head reports
    for k in ("pregame_p_home", "pregame_p1_match_win"):
        if k in live:
            block["pregame_p_home"] = live[k]
    # a couple of key realized-state projections per sport
    for k in ("proj_total", "proj_margin_home", "proj_remaining_runs",
              "run_line_home_minus15", "over_2.5", "remaining_minutes",
              "innings_remaining", "current_sets", "decided"):
        if k in live:
            block[k] = live[k]
    block["honest_note"] = live.get("honest_note")
    return block


def build_result(sport: str, pred: Any, a: argparse.Namespace) -> Dict[str, Any]:
    """Assemble the coherent pregame (+ optional in-game) result for a BUILT predictor."""
    s = _norm_sport(sport)
    home, away = a.home, a.away
    out: Dict[str, Any] = {
        "sport": s, "home": home, "away": away, "edge_claimed": False,
        "framing": ("Pregame MATCHES the devigged close (calibration/sharpness, not an "
                    "edge); in-game ADDS the realized state. No $ edge."),
    }
    if s == "tennis":
        out["surface"] = a.surface
    out["pregame"] = _pregame_block(s, pred, home, away, a.surface)
    kw = live_kwargs(s, a)
    if kw is not None:
        try:
            out["ingame"] = _ingame_block(s, pred, home, away, kw)
        except Exception as e:  # noqa: BLE001 - never crash on a live-state edge case
            out["ingame_note"] = f"in-game skipped (live-state error: {type(e).__name__})"
    else:
        out["ingame_note"] = ("no complete in-game state supplied for this sport; "
                              "pregame only")
    return out


def _md(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# {result['sport'].upper()}: {result['home']} vs {result['away']}")
    lines.append(f"edge_claimed: {result['edge_claimed']}")
    lines.append("")
    lines.append("## Pregame")
    for k, v in result["pregame"].items():
        if k == "honest_note":
            continue
        lines.append(f"- {k}: {v}")
    lines.append(f"- note: {result['pregame'].get('honest_note')}")
    if "ingame" in result:
        lines.append("")
        lines.append("## In-game")
        for k, v in result["ingame"].items():
            if k == "honest_note":
                continue
            lines.append(f"- {k}: {v}")
        lines.append(f"- note: {result['ingame'].get('honest_note')}")
    elif "ingame_note" in result:
        lines.append("")
        lines.append(f"_{result['ingame_note']}_")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    a = build_parser().parse_args(argv)
    sport = _norm_sport(a.sport)
    pred = _build_predictor(sport)
    if pred is None:
        print(f"{sport}: {_UNAVAILABLE}")
        return 0
    result = build_result(sport, pred, a)
    if a.markdown:
        print(_md(result))
    else:
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
