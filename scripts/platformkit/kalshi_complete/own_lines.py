"""scripts.platformkit.kalshi_complete.own_lines -- OUR fair two-sided quote.

KALSHI-COMPLETE program, phase 1: own the pregame moneyline ourselves. Computes
p_fair off the SANCTIONED prediction path -- scripts/platformkit/answers/
winprob_dispatch.py, which itself subprocess-dispatches
scripts/platformkit/predict_matchup.py. This module never imports src/ or a
domains/*/predictor directly (same forecast/concept decoupling guard
winprob_dispatch.py enforces) -- it calls dispatch(), a plain function import
of an existing platformkit resolver, and quotes p_home_win verbatim.

BAND (preregistered here BEFORE backtest.py scores anything):
  half_width = max(MIN_HALF_WIDTH, Z * sqrt(p*(1-p) / n_eff))
  - Z = 1.96 (fixed 95%-normal-CI multiplier, never tuned post-hoc).
  - n_eff: checked winprob_dispatch.py's envelope and predict_matchup.py's
    _pregame_block -- neither exposes a stated sample-size/n field today
    (only p_home_win, a markets dict, and honest_note). Absent that stated
    basis, n_eff falls back to DEFAULT_N_EFF below, a declared constant.
    backtest.py imports THIS SAME constant so band math is identical in the
    live quote and the historical grading (never re-tuned per sport/game).
  - MIN_HALF_WIDTH = 0.01, a floor so the band never collapses to a point
    estimate when p is near 0 or 1.

IN-GAME n_eff HEURISTIC (DECLARED, pending calibration -- never backtested,
never a tuned claim): remaining_frac is the fraction of the game clock still
to play (1.0 at tip-off/first-pitch, ->0 in the closing seconds). As the game
runs down the realized state pins the outcome down further, so the band should
TIGHTEN, not widen -- n_eff must rise as remaining_frac falls (n_eff shrinking
here would be the wrong direction). Rule: n_eff = DEFAULT_N_EFF /
max(remaining_frac, 0.1) -- pregame (remaining_frac=1 or unknown) reduces to
the plain DEFAULT_N_EFF baseline above; the 0.1 floor caps the tightening at
10x so the band never collapses toward a point estimate near final possession.

This is an UNCERTAINTY band on a probability, never a bid/ask spread /
vig / margin claim. edge_claimed is always False on every row.

Run: python -m scripts.platformkit.kalshi_complete.own_lines --sport nba --home BOS --away MIA
Run (in-game): ... --elapsed 40 --home-score 88 --away-score 81
Run (mlb in-game): ... --sport mlb --home NYY --away BOS --inning 8 --half bottom --home-score 4 --away-score 2
Test: python -m pytest scripts/platformkit/kalshi_complete/test_own_lines.py -q
"""
from __future__ import annotations

import argparse
import json
import math
from typing import Any, Dict, Optional

from scripts.platformkit.answers.winprob_dispatch import dispatch

Z: float = 1.96
MIN_HALF_WIDTH: float = 0.01
DEFAULT_N_EFF: float = 100.0  # declared constant; see module docstring


def band_half_width(p: float, n_eff: float = DEFAULT_N_EFF, z: float = Z) -> float:
    """half_width = max(MIN_HALF_WIDTH, z*sqrt(p(1-p)/n_eff)); monotone non-increasing in n_eff."""
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return max(MIN_HALF_WIDTH, z * math.sqrt(p * (1.0 - p) / float(n_eff)))


def quote_from_p(p_fair: float, n_eff: float = DEFAULT_N_EFF) -> Dict[str, float]:
    """(bid, ask, half_width) around p_fair; bid/ask always contain p_fair, clipped to [0, 1]."""
    hw = band_half_width(p_fair, n_eff)
    bid = max(0.0, p_fair - hw)
    ask = min(1.0, p_fair + hw)
    return {"bid": round(bid, 4), "ask": round(ask, 4), "half_width": round(hw, 4)}


_GAME_MINUTES = {"nba": 48.0, "wnba": 40.0}
_MLB_INNINGS = 9.0


def remaining_frac(sport: str, ingame_state: Optional[Dict[str, Any]]) -> Optional[float]:
    """Fraction of the game clock still to play, in [0, 1]. None if pregame or if
    this sport/state combination isn't covered by the heuristic yet (see module
    docstring, IN-GAME n_eff HEURISTIC)."""
    if not ingame_state:
        return None
    s = sport.lower()
    if s in _GAME_MINUTES:
        elapsed = ingame_state.get("elapsed")
        if elapsed is None:
            return None
        total = _GAME_MINUTES[s]
        return min(max((total - float(elapsed)) / total, 0.0), 1.0)
    if s == "mlb":
        inning, half = ingame_state.get("inning"), ingame_state.get("half")
        if inning is None or half is None:
            return None
        progress = (int(inning) - 1) + (0.5 if half == "bottom" else 0.0)
        return min(max((_MLB_INNINGS - progress) / _MLB_INNINGS, 0.0), 1.0)
    return None


def n_eff_for_state(sport: str, ingame_state: Optional[Dict[str, Any]],
                    base: float = DEFAULT_N_EFF) -> float:
    """DECLARED heuristic (module docstring) -- n_eff = base / max(remaining_frac, 0.1).
    Pregame / uncovered state -> base unchanged. Never tuned, never backtested here."""
    frac = remaining_frac(sport, ingame_state)
    if frac is None:
        return base
    return base / max(frac, 0.1)


def own_quote(sport: str, home: str, away: str,
              ingame_state: Optional[Dict[str, Any]] = None,
              n_eff: Optional[float] = None) -> Dict[str, Any]:
    """Fail-closed: dispatch() is the sanctioned resolver -- its own no_data/refused
    statuses pass through verbatim; a missing p_home_win never fabricates a quote.

    n_eff=None (default) auto-derives from ingame_state via the declared
    remaining_frac heuristic (pregame -> DEFAULT_N_EFF, unchanged). Pass an
    explicit n_eff to override."""
    env = dispatch(sport, home, away, ingame_state)
    base = {"sport": sport, "event": f"{away}@{home}", "as_of": env.get("as_of"),
            "edge_claimed": False}
    if env.get("status") != "ok" or env.get("p_home_win") is None:
        return {**base, "status": env.get("status", "no_data"), "p_fair": None,
                "bid": None, "ask": None, "band_basis": None,
                "honest_note": env.get("note") or "no priceable p_home_win from dispatch"}
    p_fair = float(env["p_home_win"])
    auto = n_eff is None
    eff_n_eff = n_eff_for_state(sport, ingame_state) if auto else n_eff
    q = quote_from_p(p_fair, eff_n_eff)
    if eff_n_eff == DEFAULT_N_EFF:
        basis = (f"n_eff={eff_n_eff:g} (declared constant, no stated sample-size field "
                 f"in the predictor envelope)")
    elif auto:
        basis = (f"n_eff={eff_n_eff:g} (in-game heuristic: DEFAULT_N_EFF/"
                 f"max(remaining_frac, 0.1), declared, pending calibration)")
    else:
        basis = f"n_eff={eff_n_eff:g}"
    pregame_note = (env.get("pregame") or {}).get("honest_note") or ""
    return {**base, "status": "ok", "p_fair": round(p_fair, 4),
            "bid": q["bid"], "ask": q["ask"], "band_basis": basis,
            "honest_note": "uncertainty band only, not a vig/margin claim. " + pregame_note}


def _main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sport", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    # in-game state, same generic flags winprob_dispatch.py forwards to predict_matchup.
    ap.add_argument("--elapsed", type=float, default=None, help="nba/wnba minutes elapsed")
    ap.add_argument("--home-score", type=int, default=None, dest="home_score")
    ap.add_argument("--away-score", type=int, default=None, dest="away_score")
    ap.add_argument("--inning", type=int, default=None, help="mlb inning (1-9+)")
    ap.add_argument("--half", choices=["top", "bottom"], default=None, help="mlb half")
    a = ap.parse_args(argv)
    ingame_state = {k: v for k, v in {
        "elapsed": a.elapsed, "home_score": a.home_score, "away_score": a.away_score,
        "inning": a.inning, "half": a.half,
    }.items() if v is not None}
    row = own_quote(a.sport, a.home, a.away, ingame_state or None)
    print(json.dumps(row, indent=2))
    return 0 if row.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
