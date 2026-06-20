"""domains.soccer.pregame_winprob -- leak-free PREGAME P(home win) forecasters.

Deepens the pregame layer beyond the simple Elo P(home win) that currently feeds the
in-game gate's p0. Three forecasters, ALL leak-free walk-forward (each match scored
from ONLY strictly-prior matches), keyed for cross-league gating:

  elo      : Elo + HFA logistic baseline. The HFA is a TUNABLE parameter (`hfa`),
             selected OUT-OF-FOLD (leave-one-league-out / temporal split) -- NOT the
             legacy HFA=60 strawman. For this binary home-win-vs-not target the fair,
             out-of-fold HFA is ~0 (home-win rate is ~0.43-0.46, below 0.5, so a large
             additive HFA over-predicts home wins); see pregame_winprob_gate for the
             selection protocol and the honest deltas it produces.
  poisson  : independent-Poisson goal model from EW attack/defense goals rates
             (domains.soccer.ratings lambdas) -> P(home win) by summing the
             score-grid P(h>a). Captures attack/defense strength, not just W/D/L Elo.
  poisson_xg: SAME score grid but lambdas SHRUNK toward a shots-based xG-proxy rate
             (K_SOT*SoT + K_OFF*off, per team, EW) -> tests whether shot volume/quality
             adds pregame win-prob calibration over goals alone.

P(home win) = sum_{h>a} Pois(h;lam_h) Pois(a;lam_a)  (independent Poisson, h,a in 0..9).
Draw mass is excluded from "home win" (binary home-win-vs-not, matching the in-game
outcome convention). All rates are PRIOR snapshots (update strictly after scoring).

NETWORK: zero. PURE pandas/numpy/stdlib. ASCII only. No src.*/kernel.* imports.
ACCURACY ONLY -- held-out Brier; NO market edge claimed.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_ELO_K, _ELO_INIT = 20.0, 1500.0
_HFA = 0.0              # FAIR default: out-of-fold-selected HFA (was a 60 strawman)
_ALPHA = 0.18            # EW rate update step
_PRIOR_GF, _PRIOR_GA = 1.35, 1.35
_RATE_LO, _RATE_HI = 0.2, 4.0
_K_SOT, _K_OFF = 0.33, 0.03   # xG-proxy weights (mirror asof_xg_proxy)
_XG_SHRINK = 0.5        # blend weight: lam = (1-s)*lam_goals + s*lam_xg
_MAXG = 9               # score-grid cap


def _pois_pmf(lam: float, k: int) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def p_home_win(lam_h: float, lam_a: float) -> float:
    """P(home goals > away goals) under independent Poisson, score grid 0..9."""
    ph = [_pois_pmf(lam_h, h) for h in range(_MAXG + 1)]
    pa = [_pois_pmf(lam_a, a) for a in range(_MAXG + 1)]
    tot = 0.0
    for h in range(_MAXG + 1):
        for a in range(h):
            tot += ph[h] * pa[a]
    return float(tot)


def _clip(x: float) -> float:
    return min(max(x, _RATE_LO), _RATE_HI)


def _result_to_score(ftr: str) -> float:
    f = str(ftr).upper()
    return 1.0 if f == "H" else (0.0 if f == "A" else 0.5)


def walk_forward(matches: pd.DataFrame, match_stats: Optional[pd.DataFrame] = None,
                 hfa: Optional[float] = None) -> pd.DataFrame:
    """Leak-free per-match P(home win) from elo / poisson / poisson_xg forecasters.

    matches needs: date, div, home_team, away_team, fthg, ftag, ftr.
    match_stats (optional, keyed event_id) supplies home_/away_shots + sot for the
    xG-proxy rates; if absent, poisson_xg falls back to the goals lambdas.
    hfa: Elo home-field advantage (Elo points). None -> fair module default (_HFA).
         The gate passes an OUT-OF-FOLD-selected value here so the Elo baseline is
         fair, not the legacy HFA=60 strawman.
    Returns matches (chronological) + columns p_elo, p_poisson, p_poisson_xg, y_home.
    """
    hfa = _HFA if hfa is None else float(hfa)
    df = matches.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "div", "home_team", "away_team"],
                        kind="mergesort").reset_index(drop=True)
    def _f(v: object) -> float:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return 0.0
        return x if math.isfinite(x) else 0.0

    sot_map: Dict[str, Tuple[float, float, float, float]] = {}
    if match_stats is not None:
        for r in match_stats.itertuples(index=False):
            sot_map[str(r.event_id)] = (_f(getattr(r, "home_shots", 0)),
                                        _f(getattr(r, "home_sot", 0)),
                                        _f(getattr(r, "away_shots", 0)),
                                        _f(getattr(r, "away_sot", 0)))

    elo: Dict[str, float] = {}
    gf: Dict[str, float] = {}
    ga: Dict[str, float] = {}
    xgf: Dict[str, float] = {}
    xga: Dict[str, float] = {}
    mu_h, mu_a = _PRIOR_GF, _PRIOR_GA
    p_elo: List[float] = []
    p_poi: List[float] = []
    p_xg: List[float] = []
    y: List[int] = []

    for r in df.itertuples(index=False):
        h, a = str(r.home_team), str(r.away_team)
        for d in (gf, ga, xgf, xga):
            d.setdefault(h, _PRIOR_GF if d in (gf, xgf) else _PRIOR_GA)
            d.setdefault(a, _PRIOR_GF if d in (gf, xgf) else _PRIOR_GA)
        rh, ra = elo.get(h, _ELO_INIT), elo.get(a, _ELO_INIT)
        # ---- elo P(home win) ----
        p_elo.append(1.0 / (1.0 + 10.0 ** ((ra - (rh + hfa)) / 400.0)))
        # ---- poisson P(home win) ----
        mu_all = max((mu_h + mu_a) / 2.0, 0.25)
        lam_h = _clip(gf[h]) * _clip(ga[a]) / mu_all
        lam_a = _clip(gf[a]) * _clip(ga[h]) / mu_all
        p_poi.append(p_home_win(lam_h, lam_a))
        # ---- poisson_xg: shrink lambdas toward xG-proxy rates ----
        lxg_h = _clip(xgf[h]) * _clip(xga[a]) / mu_all
        lxg_a = _clip(xgf[a]) * _clip(xga[h]) / mu_all
        bh = (1 - _XG_SHRINK) * lam_h + _XG_SHRINK * lxg_h
        ba = (1 - _XG_SHRINK) * lam_a + _XG_SHRINK * lxg_a
        p_xg.append(p_home_win(bh, ba))
        y.append(int(str(r.ftr).upper() == "H"))

        # ---- UPDATE (strictly post-snapshot) ----
        fhg, fag = float(r.fthg), float(r.ftag)
        if math.isfinite(fhg) and math.isfinite(fag):
            sc = _result_to_score(r.ftr)
            exp_h = 1.0 / (1.0 + 10.0 ** ((ra - rh) / 400.0))
            elo[h] = rh + _ELO_K * (sc - exp_h)
            elo[a] = ra + _ELO_K * ((1.0 - sc) - (1.0 - exp_h))
            gf[h] += _ALPHA * (fhg - gf[h]); ga[h] += _ALPHA * (fag - ga[h])
            gf[a] += _ALPHA * (fag - gf[a]); ga[a] += _ALPHA * (fhg - ga[a])
            mu_h += _ALPHA * (fhg - mu_h); mu_a += _ALPHA * (fag - mu_a)
            st = sot_map.get(str(getattr(r, "event_id", "")))
            if st is not None and (st[0] > 0 or st[2] > 0):
                hs, hsot, as_, asot = st       # real shot line available
                hxg = _K_SOT * hsot + _K_OFF * max(hs - hsot, 0.0)
                axg = _K_SOT * asot + _K_OFF * max(as_ - asot, 0.0)
            else:
                hxg, axg = fhg, fag            # missing shots -> use goals (no zero-inject)
            xgf[h] += _ALPHA * (hxg - xgf[h]); xga[h] += _ALPHA * (axg - xga[h])
            xgf[a] += _ALPHA * (axg - xgf[a]); xga[a] += _ALPHA * (hxg - xga[a])

    df["p_elo"] = p_elo
    df["p_poisson"] = p_poi
    df["p_poisson_xg"] = p_xg
    df["y_home"] = y
    return df
