"""generic_rating.py — one parameterized walk-forward rating model (C14 prototype).

03_MODELS §2.3: collapse NBA/MLB/tennis/soccer ratings into ONE object that differs
only by link + constants.  This prototype implements the LOGISTIC (Elo) link — the
win-probability ratings shared by NBA/MLB/tennis — as a strictly leak-free
expanding-replay: the PREGAME expectation is recorded BEFORE the post-game update,
ratings regress toward the mean at each new season.

Validation goal (honest): a SINGLE generic Elo should be COMPETITIVE with each sport's
hand-tuned baseline (the adapter's ``signal_col``) — proving the abstraction is real.
It is NOT expected to beat it, and CALIBRATION/ACCURACY != EDGE.  Durable home:
kernel/model_ops/rating.py (HUMAN-GATED) — this is the platformkit prototype.

CLI: ``python -m scripts.platformkit.generic_rating [--sport nba] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SPORT_CFG: Dict[str, Dict[str, str]] = {
    "nba": {"path": "data/domains/basketball_nba/games.parquet",
            "team_a": "home_team", "team_b": "away_team",
            "win_col": "home_win", "season": "season"},
    "mlb": {"path": "data/domains/mlb/games.parquet",
            "team_a": "home_team", "team_b": "away_team",
            "win_col": "target_home_win", "season": "season"},
    "tennis": {"path": "data/domains/tennis/matches.parquet", "kind": "player",
               "team_a": "p1_id", "team_b": "p2_id", "winner": "winner",
               "date": "date"},  # winner==1 -> p1 won; season = year(date); hfa=0
    "soccer": {"path": "data/domains/soccer/matches.parquet", "kind": "score",
               "team_a": "home_team", "team_b": "away_team", "result": "ftr",
               "season": "season"},  # ftr H/D/A -> home result-score 1/0.5/0 (draws)
}
# Per-sport pinned constants (the 03 design: the adapter supplies these).  Home
# advantage in Elo points: NBA strong, MLB modest, soccer moderate, tennis none.
_SPORT_HFA: Dict[str, float] = {"nba": 65.0, "mlb": 24.0, "soccer": 46.0, "tennis": 0.0}
_NOTE = ("One generic Elo across sports; CALIBRATION/ACCURACY != EDGE. A competitive "
         "match with the per-sport baseline validates the abstraction, not a market edge.")

# (games, baseline_probs, baseline_outcomes)
Loader = Callable[[str], Tuple[List[Dict], Optional[np.ndarray], Optional[np.ndarray]]]


class GenericRatingModel:
    """Leak-free walk-forward Elo (logistic link) with per-season regression."""

    def __init__(self, k: float = 20.0, hfa: float = 65.0,
                 season_regress: float = 0.25, base: float = 1500.0,
                 scale: float = 400.0) -> None:
        self.k = k
        self.hfa = hfa
        self.season_regress = season_regress
        self.base = base
        self.scale = scale

    def _expect(self, rh: float, ra: float) -> float:
        return 1.0 / (1.0 + 10.0 ** (-((rh + self.hfa - ra) / self.scale)))

    def walkforward(self, games: List[Dict]) -> np.ndarray:
        """Return the per-game PREGAME home-win probability (leak-free).

        games: ordered list of {home, away, season, home_win}. The expectation for
        game i uses only ratings updated strictly from games < i.
        """
        ratings: Dict[str, float] = {}
        cur_season = None
        out = np.empty(len(games), dtype=float)
        for i, g in enumerate(games):
            season = g["season"]
            if cur_season is not None and season != cur_season:
                for t in list(ratings):  # new season -> regress toward the mean
                    ratings[t] = self.base + (1.0 - self.season_regress) * (ratings[t] - self.base)
            cur_season = season
            rh = ratings.get(g["home"], self.base)
            ra = ratings.get(g["away"], self.base)
            exp_home = self._expect(rh, ra)
            out[i] = exp_home  # pregame, recorded BEFORE the update
            y = float(g["home_win"])
            ratings[g["home"]] = rh + self.k * (y - exp_home)
            ratings[g["away"]] = ra + self.k * ((1.0 - y) - (1.0 - exp_home))
        return out


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #

def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p))))


def _ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.any():
            e += abs(p[m].mean() - y[m].mean()) * m.mean()
    return float(e)


def _default_loader(sport: str) -> Tuple[List[Dict], Optional[np.ndarray], Optional[np.ndarray]]:
    """Load ordered games + the adapter baseline probs/outcomes (heavy, lazy)."""
    import pandas as pd  # noqa: PLC0415

    cfg = _SPORT_CFG[sport]
    df = pd.read_parquet(_REPO_ROOT / cfg["path"])
    a, b = cfg["team_a"], cfg["team_b"]
    kind = cfg.get("kind")
    if kind == "player":  # tennis: p1/p2, winner in {1,2}, season=year(date)
        yr = pd.to_datetime(df[cfg["date"]]).dt.year.astype(str)
        games = [{"home": str(r_a), "away": str(r_b), "season": str(r_s),
                  "home_win": 1.0 if int(r_w) == 1 else 0.0}
                 for r_a, r_b, r_s, r_w in zip(df[a], df[b], yr, df[cfg["winner"]])]
    elif kind == "score":  # soccer: ftr H/D/A -> home result-score 1/0.5/0 (draws)
        _M = {"H": 1.0, "D": 0.5, "A": 0.0}
        games = [{"home": str(r_a), "away": str(r_b), "season": str(r_s),
                  "home_win": _M.get(str(r_r), 0.5)}
                 for r_a, r_b, r_s, r_r in zip(df[a], df[b], df[cfg["season"]], df[cfg["result"]])]
        return games, None, None  # adapter baseline is O/U-2.5, not result-score
    else:
        w, s = cfg["win_col"], cfg["season"]
        games = [{"home": str(r_a), "away": str(r_b), "season": str(r_s), "home_win": float(r_w)}
                 for r_a, r_b, r_s, r_w in zip(df[a], df[b], df[s], df[w])]
    base_p = base_y = None
    try:
        from scripts.platformkit.recalibration import _ADAPTER_REGISTRY  # noqa: PLC0415
        import importlib  # noqa: PLC0415
        mod_path, cls = _ADAPTER_REGISTRY[sport]
        adapter = getattr(importlib.import_module(mod_path), cls)()
        bundle = adapter.feature_bundle(hypothesis=None, seasons=[])
        base_p = np.asarray(bundle.signal_col, dtype=float)
        base_y = np.asarray(bundle.target, dtype=float)
    except Exception:  # noqa: BLE001 - baseline optional
        pass
    return games, base_p, base_y


def validate_sport(sport: str, *, min_history: int = 200,
                   loader: Optional[Loader] = None,
                   model: Optional[GenericRatingModel] = None) -> Dict:
    """Run the generic Elo on a sport and compare OOS metrics vs the baseline."""
    if sport not in _SPORT_CFG:
        return {"sport": sport, "error": f"sport not wired (have {list(_SPORT_CFG)})", "note": _NOTE}
    load = loader or _default_loader
    mdl = model or GenericRatingModel(hfa=_SPORT_HFA.get(sport, 65.0))
    try:
        games, base_p, base_y = load(sport)
    except Exception as exc:  # noqa: BLE001
        return {"sport": sport, "error": str(exc), "note": _NOTE}
    if len(games) <= min_history:
        return {"sport": sport, "error": f"too few games ({len(games)})", "note": _NOTE}

    probs = mdl.walkforward(games)
    y = np.array([g["home_win"] for g in games], dtype=float)
    sl = slice(min_history, None)
    out: Dict = {"sport": sport, "n_games": len(games),
                 "n_eval": int(len(y) - min_history), "note": _NOTE}
    if _SPORT_CFG[sport].get("kind") == "score":
        # fractional outcome (W/D/L = 1/.5/0): RMSE of expected-score vs a leak-free
        # naive expanding-mean predictor (binary log-loss/ECE don't apply).
        cum = np.cumsum(y)
        idx = np.arange(len(y))
        naive = (cum - y) / np.maximum(idx, 1)  # mean of strictly-prior results
        rmse = float(np.sqrt(np.mean((probs[sl] - y[sl]) ** 2)))
        n_rmse = float(np.sqrt(np.mean((naive[sl] - y[sl]) ** 2)))
        out["generic_elo"] = {"rmse": round(rmse, 5), "naive_rmse": round(n_rmse, 5),
                              "beats_naive": bool(rmse < n_rmse)}
        return out
    gen = {"brier": round(_brier(probs[sl], y[sl]), 5),
           "logloss": round(_logloss(probs[sl], y[sl]), 5),
           "ece": round(_ece(probs[sl], y[sl]), 5)}
    out["generic_elo"] = gen
    if base_p is not None and base_y is not None and len(base_p) > min_history:
        bsl = slice(min_history, None)
        out["baseline"] = {"brier": round(_brier(base_p[bsl], base_y[bsl]), 5),
                           "logloss": round(_logloss(base_p[bsl], base_y[bsl]), 5),
                           "ece": round(_ece(base_p[bsl], base_y[bsl]), 5)}
        out["brier_gap_vs_baseline"] = round(gen["brier"] - out["baseline"]["brier"], 5)
    return out


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    sport = None
    if "--sport" in argv:
        i = argv.index("--sport")
        sport = argv[i + 1] if i + 1 < len(argv) else None
    sports = [sport] if sport else list(_SPORT_CFG)
    results = {s: validate_sport(s) for s in sports}
    if "--json" in argv:
        print(json.dumps(results, indent=2))
        return 0
    print(f"generic_rating — one Elo vs per-sport baseline (OOS)\nNOTE: {_NOTE}")
    for s, r in results.items():
        if "error" in r:
            print(f"\n[{s}] ERROR: {r['error']}")
            continue
        g = r["generic_elo"]
        print(f"\n[{s}] n={r['n_games']} n_eval={r['n_eval']}")
        if "rmse" in g:  # score kind (soccer expected-score W/D/L)
            print(f"  generic Elo : expected-score rmse={g['rmse']} "
                  f"naive_rmse={g['naive_rmse']} beats_naive={g['beats_naive']}")
            continue
        print(f"  generic Elo : brier={g['brier']} logloss={g['logloss']} ece={g['ece']}")
        if "baseline" in r:
            b = r["baseline"]
            print(f"  baseline    : brier={b['brier']} logloss={b['logloss']} ece={b['ece']}")
            print(f"  brier gap (generic - baseline) = {r['brier_gap_vs_baseline']:+.5f} "
                  f"(>0 means baseline better)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
