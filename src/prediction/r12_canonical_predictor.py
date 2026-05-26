"""r12_canonical_predictor.py — R12 improvement-loop canonical predictor.

Exports a reusable interface to R12's per-target winning recipes:
  - build_r12_features(merged_df): augment a season-games DataFrame with all
    R12 features (B5 base + interactions + halflife2 + opp_allowed).
  - get_canonical_feature_set(target, df): return the per-target winning
    feature subset (with keep_top50 trim when applicable).
  - train_canonical_model(df, target): train the B6 OOF-stack ensemble.
  - predict_canonical(model, X): return final blended prediction.
  - calibrate_inplay_platt(raw_probs, oof_probs, oof_y): Platt-scale probs.

This module deliberately keeps the SINGLE-MODEL canonicals callable end-to-end
(total, spread, home_score, O230). The ensemble canonicals (B15 nnls_top3 for
away_score, B15 top4_avg for AH3) are documented but not bundled here — see
scripts/probe_R12_batch15_top3_top4_blends.py for their construction.

CANONICAL recipes (R12 final, per-target winner):
  total_pts_box  → B9 interactions_only (141 feats, full set, single model)
  score_diff     → B19 keep_top50 of opp_full (top 50 of 162)
  home_score     → B19 keep_top50 of all_b9   (top 50 of 153)
  away_score     → B15 nnls_top3 (ensemble of 3 — see probe script)
  over_230       → B19 keep_top50 of opp_full (top 50 of 162)
  home_cover_AH3 → B15 top4_avg (ensemble of 4 — see probe script)
"""
from __future__ import annotations
import importlib.util, os
from collections import Counter
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")


def _load(name: str, file: str):
    p = os.path.join(_SCRIPTS_DIR, file)
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_b5 = _load("probe_R12_batch5_quality_opp", "probe_R12_batch5_quality_opp.py")
_b6 = _load("probe_R12_batch6_bagging_variance", "probe_R12_batch6_bagging_variance.py")
_b9 = _load("probe_R12_batch9_rest_travel_halflife2",
            "probe_R12_batch9_rest_travel_halflife2.py")
_b11 = _load("probe_R12_batch11_opp_allowed_stat_specific",
             "probe_R12_batch11_opp_allowed_stat_specific.py")

add_b3_features = _b5.add_b3_features
add_recency_features = _b5.add_recency_features
add_quality_features = _b5.add_quality_features
add_interactions = _b9.add_interactions
add_recency_h2 = _b9.add_recency_h2
add_opp_allowed_features = _b11.add_opp_allowed_features
_build_b5_feature_columns = _b6._build_b5_feature_columns


CANONICAL_RECIPES = {
    "total_pts_box":   {"type": "single",  "fc": "interactions_only"},
    "score_diff":      {"type": "top50",   "fc": "opp_full"},
    "home_score":      {"type": "top50",   "fc": "all_b9"},
    "away_score":      {"type": "ensemble","fcs": ["halflife2_only", "all_b9", "interactions_only"],
                        "blend": "nnls_top3 (see probe_R12_batch15)"},
    "over_230":        {"type": "top50",   "fc": "opp_full",   "kind": "bin"},
    "home_cover_AH3":  {"type": "ensemble","fcs": ["intersection", "opp_pts_pace",
                                                    "opp_full", "all_b9"],
                        "blend": "top4_avg (see probe_R12_batch15)", "kind": "bin"},
}


def build_r12_features(merged: pd.DataFrame) -> pd.DataFrame:
    """Augment a season-games DataFrame with the full R12 feature set."""
    merged = add_b3_features(merged)
    merged = add_recency_features(merged)
    merged = add_quality_features(merged)
    merged = add_interactions(merged)
    merged = add_recency_h2(merged)
    merged = add_opp_allowed_features(merged)
    return merged


def _all_feature_sets(merged: pd.DataFrame) -> Dict[str, List[str]]:
    fc_b5 = _build_b5_feature_columns(merged)
    INTERACT = [c for c in ["home_rest_x_travel", "away_rest_x_travel",
                             "rest_x_travel_diff", "b2b_x_pace_diff",
                             "rest_diff_x_elo_diff"] if c in merged.columns]
    H4 = [c for c in fc_b5 if (c.endswith("_exp_ortg") or c.endswith("_exp_drtg")
          or c.endswith("_l5_pts_for") or c.endswith("_l5_pts_against")
          or c.endswith("_l3_vs_l20_pts") or c.endswith("_l3_vs_l20_def")
          or c in ("exp_ortg_diff", "exp_drtg_diff", "l5_pts_for_diff",
                   "l5_pts_against_diff", "l3_vs_l20_pts_diff", "l3_vs_l20_def_diff"))]
    H2 = []
    for prefix in ["home_", "away_"]:
        for k in ["exp_ortg_h2", "exp_drtg_h2", "l3_pts_for_h2", "l3_pts_against_h2"]:
            H2.append(f"{prefix}{k}")
    for k in ["exp_ortg_h2", "exp_drtg_h2", "l3_pts_for_h2", "l3_pts_against_h2"]:
        H2.append(f"{k}_diff")
    H2 = [c for c in H2 if c in merged.columns]
    OPP_PTS = []
    for prefix in ["home_", "away_"]:
        for k in ["opp_allowed_PTS_l5", "opp_allowed_PTS_home_l5",
                  "opp_allowed_PTS_away_l5", "opp_allowed_PTS_l3"]:
            OPP_PTS.append(f"{prefix}{k}")
    for k in ["opp_allowed_PTS_l5", "opp_allowed_PTS_home_l5",
              "opp_allowed_PTS_away_l5", "opp_allowed_PTS_l3"]:
        OPP_PTS.append(f"{k}_diff")
    OPP_PTS = [c for c in OPP_PTS if c in merged.columns]
    OPP_PACE = [c for c in ["home_opp_l5_pace", "away_opp_l5_pace",
                             "opp_l5_pace_diff"] if c in merged.columns]
    OPP_RATE = [c for c in ["home_opp_l5_oreb_pct_against",
                             "away_opp_l5_oreb_pct_against",
                             "opp_l5_oreb_pct_against_diff",
                             "home_opp_l5_tov_pct_against",
                             "away_opp_l5_tov_pct_against",
                             "opp_l5_tov_pct_against_diff"] if c in merged.columns]

    interactions_only = fc_b5 + INTERACT
    opp_full          = fc_b5 + INTERACT + OPP_PTS + OPP_PACE + OPP_RATE
    all_b9            = fc_b5 + H2 + INTERACT
    halflife2_only    = [c for c in fc_b5 if c not in H4] + H2
    opp_pts_pace      = fc_b5 + INTERACT + OPP_PTS + OPP_PACE
    cnt = Counter()
    for fc in [interactions_only, opp_full, all_b9, halflife2_only, opp_pts_pace]:
        cnt.update(set(fc))
    intersection = sorted([c for c, k in cnt.items() if k >= 3])

    return {
        "interactions_only": interactions_only,
        "opp_full":          opp_full,
        "all_b9":            all_b9,
        "halflife2_only":    halflife2_only,
        "opp_pts_pace":      opp_pts_pace,
        "intersection":      intersection,
    }


def _compute_perm_importance(df: pd.DataFrame, fc: List[str], target: str,
                              kind: str, n_repeats: int = 5) -> Dict[str, float]:
    """Permutation importance on the last 25% split with LGB."""
    from sklearn.inspection import permutation_importance
    import lightgbm as lgb
    n = len(df)
    split = (n * 3) // 4
    tr = list(range(0, split)); te = list(range(split, n))
    X_tr = df[fc].iloc[tr].values; X_te = df[fc].iloc[te].values
    y_all = df[target].astype(int if kind == "bin" else float).values
    if kind == "reg":
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
        scoring = "neg_mean_absolute_error"
    else:
        m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
        scoring = "neg_brier_score"
    m.fit(X_tr, y_all[tr])
    r = permutation_importance(m, X_te, y_all[te], n_repeats=n_repeats,
                                random_state=42, n_jobs=1, scoring=scoring)
    return {fc[i]: float(r.importances_mean[i]) for i in range(len(fc))}


def get_canonical_feature_set(target: str, df: pd.DataFrame,
                                feature_sets: Dict[str, List[str]] = None,
                                top_k: int = 50) -> List[str]:
    """Return the per-target winning feature subset, applying top-50 trim
    when the recipe says so."""
    if target not in CANONICAL_RECIPES:
        raise KeyError(f"Unknown target {target}; recipes: {list(CANONICAL_RECIPES)}")
    recipe = CANONICAL_RECIPES[target]
    if feature_sets is None:
        feature_sets = _all_feature_sets(df)
    if recipe["type"] == "ensemble":
        # Return the FIRST component's feature set as a fallback. Caller should
        # use scripts/probe_R12_batch15_top3_top4_blends.py for the full ensemble.
        return feature_sets[recipe["fcs"][0]]
    fc = feature_sets[recipe["fc"]]
    if recipe["type"] == "single":
        return fc
    if recipe["type"] == "top50":
        # Compute permutation importance and trim to top_k
        kind = recipe.get("kind", "reg")
        # Ensure features are filled before importance computation
        df_filled = df.copy()
        df_filled[fc] = df_filled[fc].fillna(0.0)
        importances = _compute_perm_importance(df_filled, fc, target, kind)
        ranked = sorted(fc, key=lambda c: importances.get(c, 0.0), reverse=True)
        return ranked[:top_k]
    raise ValueError(f"Unknown recipe type: {recipe['type']}")


def train_canonical_model(df: pd.DataFrame, target: str, fc: List[str] = None,
                            kind: str = None) -> Dict:
    """Train the B6 OOF-stack ensemble on the canonical feature set.
    Returns a dict with level-1 (LGB), level-2 (LGB+XGB), and feature columns.
    """
    import lightgbm as lgb, xgboost as xgb
    if kind is None:
        kind = CANONICAL_RECIPES.get(target, {}).get("kind", "reg")
    if fc is None:
        fc = get_canonical_feature_set(target, df)
    df_filled = df.copy()
    df_filled[fc] = df_filled[fc].fillna(0.0)
    X = df_filled[fc].values
    y = df_filled[target].astype(int if kind == "bin" else float).values

    # Generate OOF preds for level-1 via 5-fold inner CV
    n = len(df_filled)
    oof = np.zeros(n, dtype=float)
    k = 5; fs = n // k
    for ki in range(k):
        a = ki * fs; b = (ki + 1) * fs if ki < k - 1 else n
        tr = list(range(0, a)) + list(range(b, n))
        te = list(range(a, b))
        if len(tr) < 50 or len(te) < 5:
            continue
        if kind == "reg":
            m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
                subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
                min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
            m.fit(X[tr], y[tr]); oof[te] = m.predict(X[te])
        else:
            m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
                min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
            m.fit(X[tr], y[tr]); oof[te] = m.predict_proba(X[te])[:, 1]

    # Level-1 full retrain (used at predict time for unseen test rows)
    if kind == "reg":
        l1_full = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
    else:
        l1_full = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
    l1_full.fit(X, y)

    # Level-2 = LGB+XGB ensemble on (base + oof)
    X_aug = np.hstack([X, oof.reshape(-1, 1)])
    if kind == "reg":
        l2_lgb = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
        l2_xgb = xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            random_state=42, n_jobs=2, verbosity=0)
    else:
        l2_lgb = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
        l2_xgb = xgb.XGBClassifier(n_estimators=300, learning_rate=0.05, max_depth=6,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            random_state=42, n_jobs=2, verbosity=0, eval_metric="logloss")
    l2_lgb.fit(X_aug, y); l2_xgb.fit(X_aug, y)
    return {"target": target, "kind": kind, "fc": fc,
            "l1_full": l1_full, "l2_lgb": l2_lgb, "l2_xgb": l2_xgb}


def predict_canonical(model: Dict, X: np.ndarray) -> np.ndarray:
    """Generate level-1 preds with l1_full, then level-2 LGB+XGB 50/50 average."""
    l1 = model["l1_full"]
    kind = model["kind"]
    if kind == "reg":
        l1_pred = l1.predict(X)
    else:
        l1_pred = l1.predict_proba(X)[:, 1]
    X_aug = np.hstack([X, l1_pred.reshape(-1, 1)])
    if kind == "reg":
        return 0.5 * model["l2_lgb"].predict(X_aug) + 0.5 * model["l2_xgb"].predict(X_aug)
    return 0.5 * model["l2_lgb"].predict_proba(X_aug)[:, 1] + \
           0.5 * model["l2_xgb"].predict_proba(X_aug)[:, 1]


def calibrate_inplay_platt(raw_probs: np.ndarray, oof_probs: np.ndarray,
                             oof_y: np.ndarray) -> np.ndarray:
    """Platt sigmoid calibration via logistic regression on log-odds."""
    from sklearn.linear_model import LogisticRegression
    O = np.clip(oof_probs, 1e-6, 1 - 1e-6).reshape(-1, 1)
    lo = np.log(O / (1 - O))
    lr = LogisticRegression(C=1.0); lr.fit(lo, oof_y.astype(int))
    R = np.clip(raw_probs, 1e-6, 1 - 1e-6).reshape(-1, 1)
    lo_r = np.log(R / (1 - R))
    return lr.predict_proba(lo_r)[:, 1]
