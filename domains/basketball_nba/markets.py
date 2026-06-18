"""domains.basketball_nba.markets -- complete NBA market surface, derived from the
EXISTING calibrated predictor with NO new data and NO new model.

Reads off the SAME game distribution predict() already exposes:
  total ~ N(total_mean, total_sigma),   margin(home-away) ~ N(margin_mean, margin_sigma)
where margin_mean is ANCHORED so P(margin>0) == the Elo win-prob (the validated win
model that matches the close). margin and total are ~independent in basketball, so the
home/away score marginals follow by the linear map home=(total+margin)/2.

COHERENCE GUARANTEES (asserted in tests):
  * spread cover prob at the pick'em line (0.0) == predict()'s p_home_win,
  * team-total means sum to the game total mean,
  * P(over) is monotonically decreasing in the line.

Everything here is a closed-form normal read-off of the predictor's mean/sigma -- it adds
NO information beyond predict(), so it is exactly as leak-free / calibrated as predict().
First-half / quarter lines are emitted as honest TIME-SCALED approximations (clearly
labelled): a per-period split of the game distribution, NOT a separately fitted model.

INVARIANTS: never edit src/ or kernel/; reuse predictor.py; <=300 LOC; no $ edge claimed.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

# fraction of full-game variance/level realized by the end of each period split.
# pace is roughly uniform across regulation, so level scales with elapsed fraction and
# variance with that fraction (independent-increments approximation). Honest label only.
_PERIOD_FRACTION = {"1h": 0.5, "q1": 0.25, "q2": 0.25, "q3": 0.25, "q4": 0.25}

_SPREAD_LADDER = (-12.5, -9.5, -7.5, -6.5, -5.5, -4.5, -3.5, -2.5, -1.5, 0.0,
                  1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 9.5, 12.5)


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _ndtri(p: float) -> float:
    """Inverse standard-normal CDF (rational approx; shared shape with predictor.py)."""
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    bb = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
          6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((bb[0]*r+bb[1])*r+bb[2])*r+bb[3])*r+bb[4])*r+1.0)


def _prob_over(line: float, mean: float, sigma: float) -> float:
    """P(X > line) for X ~ N(mean, sigma)."""
    return 1.0 - _phi((line - mean) / sigma)


def _ladder(lines: Sequence[float], mean: float, sigma: float) -> List[Dict]:
    out: List[Dict] = []
    for ln in lines:
        over = _prob_over(ln, mean, sigma)
        out.append({"line": float(ln), "over": round(over, 4),
                    "under": round(1.0 - over, 4)})
    return out


def game_distribution(predictor, home: str, away: str) -> Dict[str, float]:
    """The single coherent (total, margin) Gaussian summary that ALL markets read off.

    margin_mean is anchored to the Elo win-prob (P(margin>0)==p_home_win), so the spread
    market at pick'em reproduces the moneyline exactly -- coherent with predict()/to_jd().
    """
    s = predictor.predict(home, away)
    p_home = float(s["p_home_win"])
    total_mean = float(s["total_mean"])
    total_sigma = float(predictor.total_sigma)
    margin_sigma = float(predictor.margin_sigma)
    margin_mean = _ndtri(min(max(p_home, 1e-4), 1.0 - 1e-4)) * margin_sigma
    return {"p_home_win": p_home, "total_mean": total_mean, "total_sigma": total_sigma,
            "margin_mean": margin_mean, "margin_sigma": margin_sigma}


def spread(predictor, home: str, away: str, line: float = 0.0) -> Dict:
    """Home-side point-spread cover prob at `line` (home favored by -line).

    Convention: home covers when (home - away) + line > 0, i.e. margin > -line. At line=0
    this equals P(margin>0) == the Elo moneyline. P(home cover) = P(margin > -line).
    """
    g = game_distribution(predictor, home, away)
    p_cover = _prob_over(-line, g["margin_mean"], g["margin_sigma"])
    return {"market": "spread", "home": home.upper(), "away": away.upper(),
            "line_home": float(line), "p_home_cover": round(p_cover, 4),
            "p_away_cover": round(1.0 - p_cover, 4),
            "margin_home": round(g["margin_mean"], 1)}


def total(predictor, home: str, away: str, line: float) -> Dict:
    """Game total over/under at any line."""
    g = game_distribution(predictor, home, away)
    over = _prob_over(line, g["total_mean"], g["total_sigma"])
    return {"market": "total", "line": float(line), "over": round(over, 4),
            "under": round(1.0 - over, 4), "total_mean": round(g["total_mean"], 1)}


def team_total(predictor, home: str, away: str, side: str, line: float) -> Dict:
    """Team total over/under for `side` in {'home','away'}.

    home_score = (total + margin)/2,  away_score = (total - margin)/2. With total and margin
    ~independent normals, each team score is normal with mean (T +/- M)/2 and variance
    (var_total + var_margin)/4. By construction home_mean + away_mean == total_mean.
    """
    g = game_distribution(predictor, home, away)
    sd = math.sqrt(g["total_sigma"]**2 + g["margin_sigma"]**2) / 2.0
    if side.lower() == "home":
        mean = (g["total_mean"] + g["margin_mean"]) / 2.0
    elif side.lower() == "away":
        mean = (g["total_mean"] - g["margin_mean"]) / 2.0
    else:
        raise ValueError("side must be 'home' or 'away'")
    over = _prob_over(line, mean, sd)
    return {"market": "team_total", "side": side.lower(), "line": float(line),
            "over": round(over, 4), "under": round(1.0 - over, 4),
            "team_mean": round(mean, 1), "team_sigma": round(sd, 1)}


def moneyline(predictor, home: str, away: str) -> Dict:
    """Game moneyline (== spread at pick'em == predict() p_home_win)."""
    g = game_distribution(predictor, home, away)
    return {"market": "moneyline", "p_home_win": round(g["p_home_win"], 4),
            "p_away_win": round(1.0 - g["p_home_win"], 4)}


def period_markets(predictor, home: str, away: str, period: str,
                   spread_line: float = 0.0,
                   total_line: Optional[float] = None) -> Dict:
    """First-half / quarter ML, spread and total as TIME-SCALED game-distribution splits.

    HONEST APPROX (clearly labelled): level scales with the elapsed fraction f, variance
    with f (independent-increments). NOT a separately fitted period model -- a coherent
    projection of the game distribution onto a sub-window. Use for surfacing, not as an edge.
    """
    period = period.lower()
    if period not in _PERIOD_FRACTION:
        raise ValueError(f"period must be one of {sorted(_PERIOD_FRACTION)}")
    f = _PERIOD_FRACTION[period]
    g = game_distribution(predictor, home, away)
    p_total_mean = g["total_mean"] * f
    p_total_sigma = g["total_sigma"] * math.sqrt(f)
    p_margin_mean = g["margin_mean"] * f
    p_margin_sigma = g["margin_sigma"] * math.sqrt(f)
    p_home = _prob_over(0.0, p_margin_mean, p_margin_sigma)
    p_cover = _prob_over(-spread_line, p_margin_mean, p_margin_sigma)
    if total_line is None:
        total_line = round(p_total_mean * 2) / 2.0 - 0.5
    p_over = _prob_over(total_line, p_total_mean, p_total_sigma)
    return {"market": f"period_{period}", "fraction": f,
            "p_home_win": round(p_home, 4), "p_away_win": round(1.0 - p_home, 4),
            "spread_line_home": float(spread_line), "p_home_cover": round(p_cover, 4),
            "total_line": float(total_line), "over": round(p_over, 4),
            "under": round(1.0 - p_over, 4),
            "period_total_mean": round(p_total_mean, 1),
            "period_margin_home": round(p_margin_mean, 1),
            "note": ("time-scaled split of the game distribution (level~f, var~f); honest "
                     "approximation for surfacing, not a separately fitted period model")}


def full_surface(predictor, home: str, away: str,
                 spread_lines: Sequence[float] = _SPREAD_LADDER,
                 total_lines: Optional[Sequence[float]] = None) -> Dict:
    """One coherent dict pricing EVERY game-level market off a single distribution.

    Keys: moneyline, spread (main + ladder), total (main + ladder), team totals (home/away
    ladders), and first-half / per-quarter ML+spread+total. All derived from predict()'s
    (total_mean, total_sigma, margin, margin_sigma) -- coherent and leak-free by construction.
    """
    g = game_distribution(predictor, home, away)
    if total_lines is None:
        c = round(g["total_mean"] * 2) / 2.0
        total_lines = [c + d for d in (-10.5, -7.5, -5.5, -3.5, -1.5, 0.5,
                                       2.5, 4.5, 6.5, 9.5)]
    home_mean = (g["total_mean"] + g["margin_mean"]) / 2.0
    away_mean = (g["total_mean"] - g["margin_mean"]) / 2.0
    tt_sd = math.sqrt(g["total_sigma"]**2 + g["margin_sigma"]**2) / 2.0
    hc = round(home_mean * 2) / 2.0
    ac = round(away_mean * 2) / 2.0
    out: Dict = {
        "sport": "nba", "home": home.upper(), "away": away.upper(),
        "distribution": {k: round(v, 4) for k, v in g.items()},
        "moneyline": {"p_home_win": round(g["p_home_win"], 4),
                      "p_away_win": round(1.0 - g["p_home_win"], 4)},
        "spread_main": spread(predictor, home, away, 0.0),
        "spread_ladder": _ladder([-ln for ln in spread_lines][::-1],
                                  g["margin_mean"], g["margin_sigma"]),
        "total_main": round(g["total_mean"], 1),
        "total_ladder": _ladder(total_lines, g["total_mean"], g["total_sigma"]),
        "team_total_home": {"mean": round(home_mean, 1), "sigma": round(tt_sd, 1),
                            "ladder": _ladder([hc + d for d in (-6.5, -3.5, -0.5,
                                               2.5, 5.5)], home_mean, tt_sd)},
        "team_total_away": {"mean": round(away_mean, 1), "sigma": round(tt_sd, 1),
                            "ladder": _ladder([ac + d for d in (-6.5, -3.5, -0.5,
                                               2.5, 5.5)], away_mean, tt_sd)},
        "first_half": period_markets(predictor, home, away, "1h"),
        "q1": period_markets(predictor, home, away, "q1"),
        "q2": period_markets(predictor, home, away, "q2"),
        "q3": period_markets(predictor, home, away, "q3"),
        "q4": period_markets(predictor, home, away, "q4"),
        "honest_note": ("Full game-level NBA market surface read off ONE calibrated "
                        "distribution (predict()'s total/margin Gaussians). Game-level "
                        "markets are exact normal read-offs; halves/quarters are labelled "
                        "time-scaled approximations. No $ edge claimed."),
    }
    return out


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    from domains.basketball_nba.predictor import NBAPredictor
    ap = argparse.ArgumentParser(description="Full NBA market surface from the predictor.")
    ap.add_argument("--home", default="BOS")
    ap.add_argument("--away", default="LAL")
    args = ap.parse_args(argv)
    p = NBAPredictor()
    print(json.dumps(full_surface(p, args.home, args.away), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
