"""Per-posgroup weight fitting + walk-forward statistics for the LANE
positional-weights gate. Split out of positional_weight_gate.py (orchestration
+ verdict) to stay under the 300-LOC/file cap.

Fits (w_ts, w_efg, w_ft) per posgroup on TRAIN folds only, maximizing mean
Spearman rho of the within-group weighted composite vs future-30d realized
TS%, constrained to a non-negative 3-simplex via a 2-DOF softmax reparam.

GRID PRE-SEARCH (same fix pattern as composition_blend.py): the objective
is flat/plateaued right at the softmax reparam's own origin (z=(0,0,0) ->
uniform 1/3,1/3,1/3), so Nelder-Mead seeded there can terminate at the
untuned init with no local signal to move on -- verified live this session
(a direct simplex grid search found materially better weights, e.g. center
group -0.547 vs -0.361 mean neg-rho at uniform). Fix: pre-search a coarse
grid directly on the (w1, w2) simplex (w3 = 1 - w1 - w2) for the best start
point, convert to z-space, then refine with Nelder-Mead.
"""
from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from domains.basketball_nba.quality_indices_score import percentile_rank
from domains.basketball_nba.quality_validity_stats import spearman as _spearman

from scripts.platformkit.weights.positional_weight_io import POSGROUPS

RAW_FACTORS = ("ts_pct", "efg_pct", "ft_pct")
MIN_GROUP_N = 10  # floor to fit/score a posgroup cell within a fold
_GRID = np.linspace(0.0, 1.0, 11)  # simplex pre-search resolution (0.1 steps)


def _softmax3(z: np.ndarray) -> np.ndarray:
    """2-DOF reparam -> non-negative 3-simplex weights (w_ts, w_efg, w_ft)."""
    e = np.exp(z - z.max())
    return e / e.sum()


def _to_z(w: np.ndarray) -> np.ndarray:
    """Inverse of _softmax3 (up to the additive z.max() shift, which cancels
    in softmax): log-space of a simplex point, floored to avoid log(0)."""
    return np.log(np.clip(w, 1e-9, None))


def composite(table: pd.DataFrame, w: np.ndarray) -> pd.Series:
    return (w[0] * table["ts_pct"].astype(float)
            + w[1] * table["efg_pct"].astype(float)
            + w[2] * table["ft_pct"].astype(float))


def _neg_rho_for_group(z: np.ndarray, group_tables: list[pd.DataFrame]) -> float:
    w = _softmax3(z)
    rhos = []
    for t in group_tables:
        if len(t) < MIN_GROUP_N:
            continue
        comp = composite(t, w)
        rho = _spearman(comp, t["realized_ts_pct"])
        if np.isfinite(rho):
            rhos.append(rho)
    if not rhos:
        return 0.0
    return -float(np.mean(rhos))


def _grid_prescan_best(group_tables: list[pd.DataFrame]) -> np.ndarray:
    """Coarse grid search directly on the (w1, w2, w3=1-w1-w2) simplex to
    find a start point off the flat plateau surrounding the softmax
    reparam's own origin. Returns the best-scoring grid point in z-space
    (includes the uniform point, so it never does worse than the un-seeded
    fit)."""
    best_w, best_val = np.array([1 / 3, 1 / 3, 1 / 3]), None
    for w1, w2 in product(_GRID, _GRID):
        w3 = 1.0 - w1 - w2
        if w3 < -1e-9 or w3 > 1 + 1e-9:
            continue
        w = np.array([w1, w2, max(w3, 0.0)])
        val = _neg_rho_for_group(_to_z(w), group_tables)
        if best_val is None or val < best_val:
            best_val, best_w = val, w
    return _to_z(best_w)


def fit_group_weights(train_tables: list[pd.DataFrame], posgroup: str) -> np.ndarray:
    """Fit (w_ts, w_efg, w_ft) on TRAIN folds only, maximizing mean Spearman
    rho within `posgroup`. Falls back to the naive (0.55/0.30/0.15) weights
    if too few TRAIN rows exist to fit (degenerate-fold guard)."""
    group_tables = [t[t["posgroup"] == posgroup] for t in train_tables]
    if sum(len(t) for t in group_tables) < MIN_GROUP_N:
        return np.array([0.55, 0.30, 0.15])
    z0 = _grid_prescan_best(group_tables)
    res = minimize(_neg_rho_for_group, x0=z0, args=(group_tables,),
                    method="Nelder-Mead",
                    options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 300})
    return _softmax3(res.x)


def fit_all_group_weights(train_tables: list[pd.DataFrame]) -> dict[str, np.ndarray]:
    return {g: fit_group_weights(train_tables, g) for g in POSGROUPS}


def predict_positional(table: pd.DataFrame, weights: dict[str, np.ndarray]) -> pd.Series:
    """Within-group weighted composite, then percentile-ranked over the
    WHOLE pooled cutoff population (matches naive_pctile's normalization,
    so the two scores are compared on the same scale)."""
    raw = pd.Series(np.nan, index=table.index, dtype=float)
    for g in POSGROUPS:
        mask = table["posgroup"] == g
        if mask.any():
            raw.loc[mask] = composite(table[mask], weights[g])
    return percentile_rank(raw)


def fold_eval(test_table: pd.DataFrame, weights: dict[str, np.ndarray]) -> dict:
    pred = predict_positional(test_table, weights)
    overall = {
        "n": int(len(test_table)),
        "rho_positional": _spearman(pred, test_table["realized_ts_pct"]),
        "rho_naive": _spearman(test_table["naive_pctile"], test_table["realized_ts_pct"]),
    }
    overall["delta"] = overall["rho_positional"] - overall["rho_naive"]
    per_group = {}
    for g in POSGROUPS:
        sub = test_table[test_table["posgroup"] == g]
        if len(sub) < MIN_GROUP_N:
            per_group[g] = None
            continue
        pred_sub = pred.loc[sub.index]
        rho_p = _spearman(pred_sub, sub["realized_ts_pct"])
        rho_n = _spearman(sub["naive_pctile"], sub["realized_ts_pct"])
        if np.isnan(rho_p) or np.isnan(rho_n):
            per_group[g] = None
            continue
        per_group[g] = {"n": int(len(sub)), "rho_positional": rho_p, "rho_naive": rho_n,
                         "delta": rho_p - rho_n}
    return {"overall": overall, "per_group": per_group}


def leave_one_fold_out(tables: list[pd.DataFrame], cutoffs: list[str]) -> list[dict]:
    per_fold = []
    for i, cutoff in enumerate(cutoffs):
        train_tables = [tables[j] for j in range(len(tables)) if j != i]
        weights = fit_all_group_weights(train_tables)
        result = fold_eval(tables[i], weights)
        per_fold.append({"cutoff": cutoff,
                          "weights": {g: w.tolist() for g, w in weights.items()},
                          **result})
    return per_fold


def bootstrap_delta(tables: list[pd.DataFrame], weights_per_fold: list[dict[str, np.ndarray]],
                     n_boot: int, seed: int, group: str | None = None) -> dict[str, float]:
    """Cluster-by-player paired bootstrap on mean-across-folds
    rho(positional)-rho(naive), restricted to `group` if given, else overall."""
    rng = np.random.default_rng(seed)
    all_pids = sorted(set().union(*[set(t["player_id"]) for t in tables]))
    indexed = [t.set_index("player_id", drop=False) for t in tables]
    deltas = []
    for _ in range(n_boot):
        sample_pids = rng.choice(all_pids, size=len(all_pids), replace=True)
        counts = pd.Series(sample_pids).value_counts()
        fold_deltas = []
        for idx, weights in zip(indexed, weights_per_fold):
            present = idx.index.intersection(pd.unique(sample_pids))
            if len(present) == 0:
                continue
            reps = counts.reindex(present).astype(int)
            test = idx.loc[present].loc[idx.loc[present].index.repeat(reps.values)]
            test = test.reset_index(drop=True)  # resampled rows repeat player_id labels
            if group is not None:
                test = test[test["posgroup"] == group]
            if len(test) < MIN_GROUP_N:
                continue
            pred = predict_positional(test, weights)
            rho_p = _spearman(pred, test["realized_ts_pct"])
            rho_n = _spearman(test["naive_pctile"], test["realized_ts_pct"])
            if not (np.isnan(rho_p) or np.isnan(rho_n)):
                fold_deltas.append(rho_p - rho_n)
        if fold_deltas:
            deltas.append(float(np.mean(fold_deltas)))
    arr = np.array(deltas)
    if len(arr) == 0:
        return {"mean_delta": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"),
                "n_boot_effective": 0}
    return {"mean_delta": float(np.mean(arr)), "ci_lo": float(np.percentile(arr, 2.5)),
            "ci_hi": float(np.percentile(arr, 97.5)), "n_boot_effective": int(len(arr))}


def shuffle_posgroup_within_cutoff(table: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    out = table.copy()
    perm = rng.permutation(len(out))
    out["posgroup"] = out["posgroup"].to_numpy()[perm]
    return out


def sign_holds(per_fold: list[dict], key_path) -> tuple[int, int]:
    holds, n = 0, 0
    for f in per_fold:
        d = f
        for k in key_path:
            if d is None:
                break
            d = d.get(k)
        if d is None:
            continue
        n += 1
        if d["delta"] > 0:
            holds += 1
    return holds, n
