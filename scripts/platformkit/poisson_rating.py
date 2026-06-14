"""poisson_rating.py — the POISSON link of the generic rating object (C14 prototype).

Companion to ``generic_rating.GenericRatingModel`` (the LOGISTIC/Elo link). Together
they are the "one parameterized rating object, two links" of 03_MODELS §2.3:
  logistic -> win-probability Elo (NBA/MLB/tennis)
  poisson  -> attack/defense ratings -> expected runs/goals (MLB runs; soccer goals)

Each team carries log attack + log defense ratings; expected counts are
  lam_home = exp(base + atk_home - def_away + hfa);  lam_away = exp(base + atk_away - def_home)
Strictly leak-free expanding replay: the PREGAME lambdas are recorded BEFORE the
post-game online Poisson-GLM gradient update; ratings regress to the mean each season.

Validation (honest): does a generic team-rating Poisson beat a NAIVE league-mean
predictor on real MLB runs?  ACCURACY != EDGE — a calibrated count model is not a
market beat.  Durable home: kernel/model_ops/rating.py (HUMAN-GATED) — this is the prototype.

CLI: ``python -m scripts.platformkit.poisson_rating [--json]``
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SPORT_CFG: Dict[str, Dict[str, str]] = {
    "mlb": {"path": "data/domains/mlb/games.parquet",
            "team_a": "home_team", "team_b": "away_team",
            "home_ct": "home_runs", "away_ct": "away_runs", "season": "season"},
}
_NOTE = ("Generic Poisson team-rating; ACCURACY != EDGE. Beating a naive mean validates "
         "the rating, not a market edge.")

Loader = Callable[[str], List[Dict]]


class PoissonRatingModel:
    """Leak-free walk-forward attack/defense Poisson rating (count link)."""

    def __init__(self, lr: float = 0.04, hfa: float = 0.06,
                 season_regress: float = 0.25, base_log: float = 1.5,
                 clip: float = 1.5) -> None:
        self.lr = lr
        self.hfa = hfa
        self.season_regress = season_regress
        self.base_log = base_log
        self.clip = clip  # clamp |atk|,|def| for stability

    def _lam(self, atk: float, opp_def: float, home: bool) -> float:
        z = self.base_log + atk - opp_def + (self.hfa if home else 0.0)
        return math.exp(min(max(z, -3.0), 3.0))

    def walkforward(self, games: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """Return (lam_home, lam_away) pregame expected counts (leak-free)."""
        atk: Dict[str, float] = {}
        dfn: Dict[str, float] = {}
        cur_season = None
        n = len(games)
        lh = np.empty(n, dtype=float)
        la = np.empty(n, dtype=float)
        for i, g in enumerate(games):
            season = g["season"]
            if cur_season is not None and season != cur_season:
                r = 1.0 - self.season_regress
                for t in list(atk):
                    atk[t] *= r
                    dfn[t] *= r
            cur_season = season
            h, a = g["home"], g["away"]
            ah, dh = atk.get(h, 0.0), dfn.get(h, 0.0)
            aa, da = atk.get(a, 0.0), dfn.get(a, 0.0)
            lam_h = self._lam(ah, da, home=True)
            lam_a = self._lam(aa, dh, home=False)
            lh[i], la[i] = lam_h, lam_a  # pregame, before update
            yh, ya = float(g["home_ct"]), float(g["away_ct"])
            c = self.clip
            atk[h] = min(max(ah + self.lr * (yh - lam_h), -c), c)
            dfn[a] = min(max(da + self.lr * (lam_h - yh), -c), c)
            atk[a] = min(max(aa + self.lr * (ya - lam_a), -c), c)
            dfn[h] = min(max(dh + self.lr * (lam_a - ya), -c), c)
        return lh, la


def _pois_dev(lam: np.ndarray, y: np.ndarray) -> float:
    """Mean Poisson deviance (lower better)."""
    lam = np.clip(lam, 1e-9, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(y > 0, y * np.log(y / lam), 0.0)
    return float(np.mean(2.0 * (term - (y - lam))))


def _default_loader(sport: str) -> List[Dict]:
    import pandas as pd  # noqa: PLC0415

    cfg = _SPORT_CFG[sport]
    df = pd.read_parquet(_REPO_ROOT / cfg["path"])
    a, b, hc, ac, s = (cfg["team_a"], cfg["team_b"], cfg["home_ct"],
                       cfg["away_ct"], cfg["season"])
    return [{"home": str(rh), "away": str(rb), "season": str(rs),
             "home_ct": float(rhc), "away_ct": float(rac)}
            for rh, rb, rs, rhc, rac in zip(df[a], df[b], df[s], df[hc], df[ac])]


def validate_sport(sport: str = "mlb", *, min_history: int = 500,
                   loader: Optional[Loader] = None,
                   model: Optional[PoissonRatingModel] = None) -> Dict:
    """Compare the generic Poisson rating vs a naive league-mean predictor (OOS)."""
    if sport not in _SPORT_CFG:
        return {"sport": sport, "error": f"sport not wired (have {list(_SPORT_CFG)})", "note": _NOTE}
    load = loader or _default_loader
    mdl = model or PoissonRatingModel()
    try:
        games = load(sport)
    except Exception as exc:  # noqa: BLE001
        return {"sport": sport, "error": str(exc), "note": _NOTE}
    if len(games) <= min_history:
        return {"sport": sport, "error": f"too few games ({len(games)})", "note": _NOTE}

    lh, la = mdl.walkforward(games)
    yh = np.array([g["home_ct"] for g in games], dtype=float)
    ya = np.array([g["away_ct"] for g in games], dtype=float)
    sl = slice(min_history, None)
    pred_tot = (lh + la)[sl]
    act_tot = (yh + ya)[sl]
    # naive: predict the expanding-mean total (leak-free) at each point
    cum = np.cumsum(yh + ya)
    idx = np.arange(len(games))
    naive_tot = (cum - (yh + ya)) / np.maximum(idx, 1)  # mean of strictly-prior totals
    naive_tot = naive_tot[sl]

    model_dev = _pois_dev(lh[sl], yh[sl]) + _pois_dev(la[sl], ya[sl])
    return {
        "sport": sport, "n_games": len(games), "n_eval": int(len(games) - min_history),
        "model_total_rmse": round(float(np.sqrt(np.mean((pred_tot - act_tot) ** 2))), 4),
        "naive_total_rmse": round(float(np.sqrt(np.mean((naive_tot - act_tot) ** 2))), 4),
        "model_poisson_deviance": round(model_dev, 4),
        "mean_pred_total": round(float(pred_tot.mean()), 3),
        "mean_act_total": round(float(act_tot.mean()), 3),
        "note": _NOTE,
    }


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    res = validate_sport("mlb")
    if "--json" in argv:
        print(json.dumps(res, indent=2))
        return 0
    print(f"poisson_rating — generic Poisson team-rating vs naive mean (MLB runs)\nNOTE: {_NOTE}")
    if "error" in res:
        print(f"ERROR: {res['error']}")
        return 0
    print(f"\nn={res['n_games']} n_eval={res['n_eval']}")
    print(f"  total runs RMSE : model={res['model_total_rmse']}  naive_mean={res['naive_total_rmse']}")
    print(f"  Poisson deviance (model, sum home+away) = {res['model_poisson_deviance']}")
    print(f"  mean predicted total={res['mean_pred_total']}  actual={res['mean_act_total']}")
    better = res["model_total_rmse"] < res["naive_total_rmse"]
    print(f"  -> model {'BEATS' if better else 'does NOT beat'} naive mean on total-runs RMSE (honest)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
