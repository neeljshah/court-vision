"""challenger -- composed game-level NBA model, walk-forward vs an Elo base.

Same discipline as scripts/platformkit/intel_weighting/relevance_gate.py and it
REUSES that module's helpers (Elo base logit, BFGS log-loss fit, sigmoid, Brier)
plus eval_gate.dm_test -- base and candidate differ ONLY by the feature terms
(comparability rail): same games, same temporal split, same optimizer.

  base       = leak-free walk-forward Elo + fitted intercept (train prefix).
  candidate  = base logit + intercept + beta . composed feature-diffs (home-away),
               each feature standardized on the TRAIN prefix only (no test leak).

Walk-forward: 2025-26 games date-ordered, train prefix (_TRAIN_FRAC) fits
{intercept, betas}, test suffix is scored. Truncation: delta recomputed after
dropping the last 20% of the test window (relevance_gate parity).

Ablation ladder: Elo -> +offense -> +concession -> +synergy/gravity -> +rest,
so we learn WHICH composed feature carries any lift. Verdict per rung:
MATTERS_PROVISIONAL / NULL (single-fold within one season -> at most PROVISIONAL).

NO dollar/edge language: Brier / log-loss deltas only.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.compose.team_form import build_team_form
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.generic_rating import GenericRatingModel, _SPORT_HFA
from scripts.platformkit.intel_weighting.relevance_gate import (
    GateResult, _MIN_TEST, _TRAIN_FRAC, _DM_ALPHA, _brier, _fit, _sigmoid,
)

METHOD = "composed_challenger_v1_walkforward"

# Ablation ladder: (rung label, feature diff columns added at this rung).
# Concession diff is home_D_faces minus away_D_faces; a LOWER value is a better
# defense, so the fitted beta simply learns the sign -- we pass the raw diff.
_LADDER: List[Tuple[str, List[str]]] = [
    ("elo_base", []),
    ("+offense", ["off"]),
    ("+concession", ["off", "conc"]),
    ("+synergy_gravity", ["off", "conc", "net"]),
    ("+rest", ["off", "conc", "net", "rest"]),
]


def _base_logit_nba() -> Tuple[pd.DataFrame, np.ndarray]:
    """Leak-free walk-forward Elo home-win logit over ALL seasons (warm-up), and
    the full games frame -- mirrors relevance_gate._base_probs for NBA."""
    from pathlib import Path  # noqa: PLC0415
    repo = Path(__file__).resolve().parents[3]
    games = pd.read_parquet(repo / "data" / "domains" / "basketball_nba" / "games.parquet")
    games["date"] = pd.to_datetime(games["date"])
    games = games.sort_values(["date", "game_id"]).reset_index(drop=True)
    rows = [{"home": str(h), "away": str(a), "season": str(s), "home_win": float(w)}
            for h, a, s, w in zip(games["home_team"], games["away_team"],
                                  games["season"], games["home_win"])]
    mdl = GenericRatingModel(hfa=_SPORT_HFA["nba"])
    p = np.clip(mdl.walkforward(rows), 1e-9, 1 - 1e-9)
    return games, np.log(p / (1 - p))


def _feature_diffs(tf: pd.DataFrame) -> pd.DataFrame:
    """Raw home-minus-away diffs, one column per feature (pre-standardization)."""
    return pd.DataFrame({
        "off": tf["off_home"] - tf["off_away"],
        "conc": tf["conc_home"] - tf["conc_away"],
        "net": tf["net_home"] - tf["net_away"],
        "rest": tf["rest_diff"],
    })


def _standardize(diffs: pd.DataFrame, tr: slice) -> pd.DataFrame:
    """z-score each diff on the TRAIN prefix only; fill NaN (early as-of gaps)
    with the train mean -> a neutral z of 0 (leak-free: params from train)."""
    out = {}
    for c in diffs.columns:
        col = diffs[c].to_numpy(dtype=float)
        mu = float(np.nanmean(col[tr]))
        sd = float(np.nanstd(col[tr])) or 1.0
        z = (np.where(np.isnan(col), mu, col) - mu) / sd
        out[c] = z
    return pd.DataFrame(out, index=diffs.index)


def run_challenger(season: str = "2025-26") -> List[GateResult]:
    """The composed ablation ladder as a list of GateResult (rung = metric)."""
    tf = build_team_form(season)
    games_all, base_logit_all = _base_logit_nba()
    # align base logit to the season rows in the SAME date order as team_form
    idx = games_all.reset_index().set_index("game_id")["index"]
    order = [int(idx[g]) for g in tf["game_id"]]
    base_logit = base_logit_all[order]
    y = tf["home_win"].to_numpy(dtype=float)
    gid = tf["game_id"].astype(str).to_numpy()

    n = len(tf)
    n_tr = int(n * _TRAIN_FRAC)
    n_te = n - n_tr
    tr, te = slice(0, n_tr), slice(n_tr, n)
    if n_te < _MIN_TEST:
        return [GateResult("composed", "nba", "elo_base", "team_asof", n,
                           0.0, 0.0, 0.0, 0.0, 1.0, "UNTESTABLE",
                           [f"only {n_te} OOS games"])]

    z = _standardize(_feature_diffs(tf), tr)
    ones_tr, ones_te = np.ones((n_tr, 1)), np.ones((n_te, 1))
    yb = y[te]

    # base rung: intercept only (Elo recalibrated) -- the honest comparison point
    a_base = _fit(base_logit[tr], ones_tr, y[tr])
    p_base = _sigmoid(base_logit[te] + a_base[0])
    brier_base = _brier(p_base, yb)

    results: List[GateResult] = []
    for label, cols in _LADDER:
        if not cols:  # elo_base rung: candidate IS the base
            p_cond = p_base
        else:
            Xtr = np.column_stack([ones_tr] + [z[c].to_numpy()[tr] for c in cols])
            Xte = np.column_stack([ones_te] + [z[c].to_numpy()[te] for c in cols])
            theta = _fit(base_logit[tr], Xtr, y[tr])   # same optimizer as base
            p_cond = _sigmoid(base_logit[te] + Xte @ theta)
        brier_cond = _brier(p_cond, yb)
        delta = brier_base - brier_cond
        d = (p_base - yb) ** 2 - (p_cond - yb) ** 2
        dm_p = diebold_mariano(d, gid[te]).p_value
        cut = int(n_te * 0.8)
        delta_t80 = (_brier(p_base[:cut], yb[:cut]) - _brier(p_cond[:cut], yb[:cut]))
        if cols and delta > 0 and dm_p < _DM_ALPHA and delta_t80 > 0:
            verdict = "MATTERS_PROVISIONAL"
            caveats = ["single-fold within one season across a 5-rung ladder: "
                       "expected chance hits ~0.05*rungs; stays PROVISIONAL until "
                       "replicated on an independent season/corpus"]
        else:
            verdict = "NULL"
            caveats = []
        results.append(GateResult(
            "composed", "nba", label, "team_asof", n,
            round(brier_base, 6), round(brier_cond, 6), round(delta, 6),
            round(delta_t80, 6), round(dm_p, 4), verdict, caveats))
    return results


if __name__ == "__main__":  # pragma: no cover - smoke
    for r in run_challenger():
        print(f"{r.metric:18s} brier {r.brier_cond:.5f} d {r.delta:+.5f} "
              f"dm_p {r.dm_p:.4f} {r.verdict}")
