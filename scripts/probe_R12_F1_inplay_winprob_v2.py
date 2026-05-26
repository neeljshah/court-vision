"""
probe_R12_F1_inplay_winprob_v2.py — v2 attempt to clear the 0.183 Brier gate
for endQ1 and/or endQ2 in-play winprob (R10_M5 v1 had Brier 0.232 / 0.190).

Approach: hybrid Architecture v2 + Anchor v2.
  * Architecture v2: LightGBM + XGBoost + Logistic Regression base learners
    stacked with non-negative least squares (NNLS) — the proven pattern from
    R7_A WinProb where a single-LGB at the ceiling gained meaningfully from
    ensembling.
  * Anchor v2: blend the stacked in-play probability with the pregame
    win-probability via a learned per-snapshot alpha. At endQ1 the in-play
    signal is noisy and pregame still carries weight; the blend is allowed
    to learn alpha in [0, 1] on the training fold and then applied to the
    test fold (so it stays walk-forward honest).
  * Feature v2 additions: pace-normalized projected total margin, projected
    final-score margin, star differential, rest differential, elo
    differential, season-level form differentials, and quarter-by-quarter
    variance for snapshots where multiple quarters are observed.

SHIP gate: endQ1 OR endQ2 mean walk-forward Brier <= 0.183 across 4 folds.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODEL_DIR = os.path.join(PROJECT, "data", "models")
OUT_JSON = os.path.join(DATA_CACHE, "probe_R12_F1_inplay_winprob_v2_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SHIP_BRIER = 0.183


# ── Data loading ─────────────────────────────────────────────────────────────

def load_linescores() -> Dict[str, Dict]:
    path = os.path.join(NBA_CACHE, "linescores_all.json")
    with open(path) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    out: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            print(f"  [WARN] missing {path}", flush=True)
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            out[row["game_id"]] = row
    return out


def _pregame_wp_from_features(row: Dict) -> float:
    """Elo + HCA logistic. Falls back to 0.55 (league-average home edge)."""
    hca = 65.0
    home_elo = row.get("home_elo")
    away_elo = row.get("away_elo")
    if home_elo is None or away_elo is None:
        return 0.55
    try:
        diff = float(home_elo) - float(away_elo) + hca
        return float(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))
    except (TypeError, ValueError):
        return 0.55


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


# ── Feature engineering (v2 — adds anchor + projections + diffs) ─────────────

def build_rows(linescores: Dict, season_games: Dict) -> pd.DataFrame:
    records: List[Dict] = []

    for gid, ls in linescores.items():
        sg = season_games.get(gid)
        if sg is None:
            continue

        required_qs = ["home_q1", "home_q2", "home_q3", "home_q4",
                       "away_q1", "away_q2", "away_q3", "away_q4"]
        if any(ls.get(k) is None for k in required_qs):
            continue

        hq = [ls["home_q1"], ls["home_q2"], ls["home_q3"], ls["home_q4"]]
        aq = [ls["away_q1"], ls["away_q2"], ls["away_q3"], ls["away_q4"]]
        home_total = sum(hq)
        away_total = sum(aq)
        home_team_won = int(home_total > away_total)

        game_date = sg.get("game_date", "1900-01-01")
        home_team_id = ls.get("home_team_id", 0) or sg.get("home_team", "UNK")
        season = sg.get("season", "unknown")

        # Pregame WP — prefer sim_win_prob, fall back to elo logistic.
        pregame_wp = sg.get("sim_win_prob")
        if pregame_wp is None:
            pregame_wp = _pregame_wp_from_features(sg)
        pregame_wp = float(pregame_wp)

        # Pre-game differentials (available at all snapshots).
        net_rtg_diff = _safe_float(sg.get("net_rtg_diff"))
        pace_diff = _safe_float(sg.get("pace_diff"))
        elo_diff = _safe_float(sg.get("elo_differential"))
        stars_diff = (
            _safe_float(sg.get("home_stars_available"))
            - _safe_float(sg.get("away_stars_available"))
        )
        rest_diff = (
            _safe_float(sg.get("home_rest_days"))
            - _safe_float(sg.get("away_rest_days"))
        )
        b2b_diff = (
            _safe_float(sg.get("home_back_to_back"))
            - _safe_float(sg.get("away_back_to_back"))
        )
        last5_diff = (
            _safe_float(sg.get("home_last5_wins"))
            - _safe_float(sg.get("away_last5_wins"))
        )

        for snap_idx, snapshot in enumerate(["endQ1", "endQ2", "endQ3"]):
            n_qtrs = snap_idx + 1
            minutes_played = n_qtrs * MINUTES_PER_QUARTER

            h_cum = sum(hq[:n_qtrs])
            a_cum = sum(aq[:n_qtrs])
            total_pts = h_cum + a_cum

            if snapshot == "endQ3" and total_pts < 60:
                continue

            score_margin = h_cum - a_cum
            pace_so_far = total_pts / minutes_played

            # Pace-normalized projections (v2 feature):
            #   project remaining 48 - minutes_played minutes at current pace,
            #   keeping the in-game margin trajectory linear.
            rem_minutes = 48.0 - minutes_played
            if minutes_played > 0:
                margin_per_min = score_margin / minutes_played
            else:
                margin_per_min = 0.0
            projected_final_margin = score_margin + margin_per_min * rem_minutes
            projected_total_score = total_pts + pace_so_far * rem_minutes

            q1_delta = hq[0] - aq[0]
            q2_delta = (hq[1] - aq[1]) if n_qtrs >= 2 else np.nan
            q3_delta = (hq[2] - aq[2]) if n_qtrs >= 3 else np.nan
            last_q_margin = hq[n_qtrs - 1] - aq[n_qtrs - 1]

            # Quarter-margin variance: a noisy quarter signal is less
            # informative than a steady one. Use deltas observed so far.
            observed_deltas = [hq[i] - aq[i] for i in range(n_qtrs)]
            if len(observed_deltas) >= 2:
                qtr_margin_var = float(np.var(observed_deltas))
                qtr_margin_mean = float(np.mean(observed_deltas))
            else:
                qtr_margin_var = 0.0
                qtr_margin_mean = float(observed_deltas[0])

            # Anchor blend signal: how much weight to give pregame.
            # Stored as a feature; the meta-stacker can learn how to use it.
            anchor_w_pregame = 1.0 - (minutes_played / 48.0)  # 0.75, 0.50, 0.25

            row = {
                "game_id": gid,
                "game_date": game_date,
                "snapshot": snapshot,
                "home_team_id": home_team_id,
                "season": season,
                "score_margin": score_margin,
                "total_pts": total_pts,
                "pace_so_far": pace_so_far,
                "q1_delta": q1_delta,
                "q2_delta": q2_delta,
                "q3_delta": q3_delta,
                "last_q_margin": last_q_margin,
                "qtr_margin_var": qtr_margin_var,
                "qtr_margin_mean": qtr_margin_mean,
                "projected_final_margin": projected_final_margin,
                "projected_total_score": projected_total_score,
                "anchor_w_pregame": anchor_w_pregame,
                "pregame_win_prob": pregame_wp,
                "net_rtg_diff": net_rtg_diff,
                "pace_diff": pace_diff,
                "elo_diff": elo_diff,
                "stars_diff": stars_diff,
                "rest_diff": rest_diff,
                "b2b_diff": b2b_diff,
                "last5_diff": last5_diff,
                "home_team_won": home_team_won,
            }
            records.append(row)

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").reset_index(drop=True)
    print(f"  Built {len(df)} snapshot rows from "
          f"{len(df['game_id'].unique())} games", flush=True)
    return df


# ── Feature columns per snapshot (v2 = v1 + projection + diffs) ───────────────

_BASE_NUMERIC = [
    "score_margin", "total_pts", "pace_so_far",
    "projected_final_margin", "projected_total_score",
    "qtr_margin_var", "qtr_margin_mean",
    "last_q_margin", "pregame_win_prob",
    "net_rtg_diff", "pace_diff", "elo_diff",
    "stars_diff", "rest_diff", "b2b_diff", "last5_diff",
]
_CAT_COLS = ["home_team_id", "season"]

SNAP_FEATURES: Dict[str, List[str]] = {
    "endQ1": _BASE_NUMERIC + ["q1_delta"] + _CAT_COLS,
    "endQ2": _BASE_NUMERIC + ["q1_delta", "q2_delta"] + _CAT_COLS,
    "endQ3": _BASE_NUMERIC + ["q1_delta", "q2_delta", "q3_delta"] + _CAT_COLS,
}


# ── Base learners ────────────────────────────────────────────────────────────

def _fit_lgb(X_tr: pd.DataFrame, y_tr: pd.Series,
             cat_cols: List[str]):
    import lightgbm as lgb
    model = lgb.LGBMClassifier(
        n_estimators=400,
        learning_rate=0.04,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=4,
        verbose=-1,
    )
    model.fit(
        X_tr, y_tr,
        categorical_feature=cat_cols if cat_cols else "auto",
    )
    return model


def _prep_xgb_frame(X: pd.DataFrame) -> pd.DataFrame:
    """XGBoost wants numeric features — drop categoricals, fill NaN."""
    Xn = X.drop(columns=[c for c in _CAT_COLS if c in X.columns], errors="ignore")
    Xn = Xn.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return Xn


def _fit_xgb(X_tr: pd.DataFrame, y_tr: pd.Series):
    import xgboost as xgb
    model = xgb.XGBClassifier(
        n_estimators=400,
        learning_rate=0.04,
        max_depth=4,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        eval_metric="logloss",
        n_jobs=4,
        random_state=42,
        verbosity=0,
    )
    model.fit(_prep_xgb_frame(X_tr), y_tr)
    return model


def _prep_lr_frame(X: pd.DataFrame, mean: Optional[pd.Series] = None,
                   std: Optional[pd.Series] = None
                   ) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    Xn = X.drop(columns=[c for c in _CAT_COLS if c in X.columns], errors="ignore")
    Xn = Xn.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    if mean is None:
        mean = Xn.mean()
        std = Xn.std().replace(0.0, 1.0)
    Xs = (Xn - mean) / std
    return Xs, mean, std


def _fit_lr(X_tr: pd.DataFrame, y_tr: pd.Series):
    from sklearn.linear_model import LogisticRegression
    Xs, m, s = _prep_lr_frame(X_tr)
    model = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs")
    model.fit(Xs, y_tr)
    return (model, m, s)


# ── Stacking + anchor blend ──────────────────────────────────────────────────

def _nnls_weights(P: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Non-negative least squares on probabilities -> y, normalized to sum=1."""
    from scipy.optimize import nnls
    w, _ = nnls(P, y.astype(float))
    s = w.sum()
    if s <= 0:
        # Fallback to uniform if everything zeroed out.
        return np.ones(P.shape[1]) / P.shape[1]
    return w / s


def _learn_anchor_alpha(p_stack: np.ndarray, p_pregame: np.ndarray,
                        y: np.ndarray) -> float:
    """Find alpha in [0, 1] minimizing Brier of alpha*p_stack + (1-alpha)*p_pregame.

    Closed form: minimize sum((alpha*a + (1-alpha)*b - y)^2). Take derivative
    w.r.t. alpha, set to zero, clip to [0, 1].
    """
    a = p_stack
    b = p_pregame
    diff = a - b
    num = np.sum((y - b) * diff)
    den = np.sum(diff * diff)
    if den <= 1e-12:
        return 1.0
    alpha = num / den
    return float(np.clip(alpha, 0.0, 1.0))


def _train_stack_on_fold(X_tr: pd.DataFrame, y_tr: pd.Series,
                         cat_cols: List[str]
                         ) -> Tuple[Any, Any, Any, np.ndarray]:
    """Train three base learners + NNLS weights on training fold via OOF.

    Returns (lgb_model, xgb_model, (lr_model, mean, std), nnls_weights).
    OOF predictions are produced via a single internal 80/20 holdout —
    cheap, walk-forward-safe, and good enough to fit a 3-D simplex.
    """
    n = len(X_tr)
    # Use the last 25% of the training fold (chronologically ordered already)
    # as the internal stacker calibration set.
    split = int(n * 0.75)
    if split < 30 or n - split < 20:
        # Tiny fold — train base learners on full data and use uniform weights.
        lgb_m = _fit_lgb(X_tr, y_tr, cat_cols)
        xgb_m = _fit_xgb(X_tr, y_tr)
        lr_pack = _fit_lr(X_tr, y_tr)
        return lgb_m, xgb_m, lr_pack, np.ones(3) / 3

    X_in, y_in = X_tr.iloc[:split], y_tr.iloc[:split]
    X_cal, y_cal = X_tr.iloc[split:], y_tr.iloc[split:]

    lgb_in = _fit_lgb(X_in, y_in, cat_cols)
    xgb_in = _fit_xgb(X_in, y_in)
    lr_in_pack = _fit_lr(X_in, y_in)

    p_lgb_cal = lgb_in.predict_proba(X_cal)[:, 1]
    p_xgb_cal = xgb_in.predict_proba(_prep_xgb_frame(X_cal))[:, 1]
    lr_m, lr_mean, lr_std = lr_in_pack
    Xs_cal, _, _ = _prep_lr_frame(X_cal, lr_mean, lr_std)
    p_lr_cal = lr_m.predict_proba(Xs_cal)[:, 1]

    P_cal = np.column_stack([p_lgb_cal, p_xgb_cal, p_lr_cal])
    w = _nnls_weights(P_cal, y_cal.values)

    # Refit all three base learners on the full training fold so the
    # production stack has maximum data — weights are fixed.
    lgb_full = _fit_lgb(X_tr, y_tr, cat_cols)
    xgb_full = _fit_xgb(X_tr, y_tr)
    lr_full_pack = _fit_lr(X_tr, y_tr)
    return lgb_full, xgb_full, lr_full_pack, w


def _stack_predict(lgb_m, xgb_m, lr_pack, weights: np.ndarray,
                   X: pd.DataFrame) -> np.ndarray:
    p_lgb = lgb_m.predict_proba(X)[:, 1]
    p_xgb = xgb_m.predict_proba(_prep_xgb_frame(X))[:, 1]
    lr_m, lr_mean, lr_std = lr_pack
    Xs, _, _ = _prep_lr_frame(X, lr_mean, lr_std)
    p_lr = lr_m.predict_proba(Xs)[:, 1]
    P = np.column_stack([p_lgb, p_xgb, p_lr])
    return np.clip(P @ weights, 1e-6, 1 - 1e-6)


# ── Walk-forward CV ──────────────────────────────────────────────────────────

def walk_forward_cv(
    X: pd.DataFrame,
    y: pd.Series,
    pregame: pd.Series,
    snapshot: str,
    n_folds: int = 4,
) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    from sklearn.metrics import (
        accuracy_score, brier_score_loss, log_loss, roc_auc_score,
    )

    cat_cols = [c for c in _CAT_COLS if c in X.columns]
    Xc = X.copy()
    for c in cat_cols:
        Xc[c] = Xc[c].astype("category")

    n = len(Xc)
    min_train = int(n * 0.60)
    test_size = (n - min_train) // n_folds

    fold_results: List[Dict[str, float]] = []
    alphas: List[float] = []
    weight_logs: List[List[float]] = []

    for fold in range(n_folds):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < n_folds - 1 else n

        if train_end < 30 or test_start >= n:
            continue

        X_tr = Xc.iloc[:train_end]
        y_tr = y.iloc[:train_end]
        X_te = Xc.iloc[test_start:test_end]
        y_te = y.iloc[test_start:test_end]
        pre_tr = pregame.iloc[:train_end]
        pre_te = pregame.iloc[test_start:test_end]

        if len(X_te) < 10:
            continue

        # Re-set categorical dtypes after slicing (pandas can lose them
        # when chained through .iloc).
        for c in cat_cols:
            X_tr[c] = X_tr[c].astype("category")
            X_te[c] = X_te[c].astype("category")

        # Train ensemble on training fold.
        lgb_m, xgb_m, lr_pack, w = _train_stack_on_fold(X_tr, y_tr, cat_cols)
        weight_logs.append([float(x) for x in w])

        # In-training stack probability (for anchor alpha estimation): we use
        # the last 25% of the training fold (same internal cal slice used
        # by the stacker) so the anchor is learned on the same OOF slice.
        split = int(len(X_tr) * 0.75)
        X_cal = X_tr.iloc[split:]
        y_cal_arr = y_tr.iloc[split:].values
        pre_cal_arr = pre_tr.iloc[split:].values
        p_stack_cal = _stack_predict(lgb_m, xgb_m, lr_pack, w, X_cal)
        alpha = _learn_anchor_alpha(p_stack_cal, pre_cal_arr, y_cal_arr)
        alphas.append(alpha)

        # Predict on test fold and blend.
        p_stack_te = _stack_predict(lgb_m, xgb_m, lr_pack, w, X_te)
        p_blended = np.clip(
            alpha * p_stack_te + (1.0 - alpha) * pre_te.values, 1e-6, 1 - 1e-6
        )

        preds = (p_blended >= 0.5).astype(int)
        fold_results.append({
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "auc": float(roc_auc_score(y_te, p_blended)),
            "brier": float(brier_score_loss(y_te, p_blended)),
            "log_loss": float(log_loss(y_te, p_blended)),
            "accuracy": float(accuracy_score(y_te, preds)),
            "alpha_anchor": float(alpha),
            "stacker_weights": [float(x) for x in w],
        })
        print(
            f"  {snapshot} fold {fold}: train={len(X_tr)}, test={len(X_te)}, "
            f"alpha={alpha:.3f}, w={[round(x, 3) for x in w]}, "
            f"AUC={fold_results[-1]['auc']:.4f}, "
            f"Brier={fold_results[-1]['brier']:.4f}, "
            f"Acc={fold_results[-1]['accuracy']:.4f}",
            flush=True,
        )

    summary = {
        "alpha_mean": float(np.mean(alphas)) if alphas else 1.0,
        "weights_mean": (
            [float(np.mean([w[i] for w in weight_logs])) for i in range(3)]
            if weight_logs else [1/3, 1/3, 1/3]
        ),
    }
    return fold_results, summary


def mean_metrics(fold_results: List[Dict]) -> Dict[str, float]:
    if not fold_results:
        return {}
    keys = ["auc", "brier", "log_loss", "accuracy"]
    return {k: float(np.mean([r[k] for r in fold_results])) for k in keys}


# ── Production training (called after probe SHIPs) ───────────────────────────

def train_production_model(
    df_all: pd.DataFrame, snapshot: str
) -> Optional[Dict[str, Any]]:
    """Fit the v2 stack on all available rows for ``snapshot`` and persist.

    Saves the LightGBM booster (the dominant learner) plus a meta JSON
    holding the ensemble weights, anchor alpha, and feature column order.
    The runtime module reads the meta to reconstruct the blend at inference.
    """
    import lightgbm as lgb
    sub = df_all[df_all["snapshot"] == snapshot].copy()
    if sub.empty:
        return None

    feat_cols = SNAP_FEATURES[snapshot]
    X = sub[feat_cols].copy()
    y = sub["home_team_won"].astype(int)
    pregame = sub["pregame_win_prob"].astype(float)
    cat_cols = [c for c in _CAT_COLS if c in X.columns]
    for c in cat_cols:
        X[c] = X[c].astype("category")

    lgb_m, xgb_m, lr_pack, weights = _train_stack_on_fold(X, y, cat_cols)

    # Estimate anchor alpha on the chronological-tail 25% of all-data — same
    # recipe as the walk-forward folds.
    split = int(len(X) * 0.75)
    X_cal = X.iloc[split:]
    pre_cal_arr = pregame.iloc[split:].values
    y_cal_arr = y.iloc[split:].values
    p_stack_cal = _stack_predict(lgb_m, xgb_m, lr_pack, weights, X_cal)
    alpha = _learn_anchor_alpha(p_stack_cal, pre_cal_arr, y_cal_arr)

    out_lgb = os.path.join(MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_v2.lgb")
    lgb_m.booster_.save_model(out_lgb)

    # Linear regression coefficients for portability (avoid pickling).
    lr_m, lr_mean, lr_std = lr_pack
    lr_coef = lr_m.coef_.ravel().tolist()
    lr_intercept = float(lr_m.intercept_.ravel()[0])
    lr_feat_order = [c for c in feat_cols if c not in _CAT_COLS]

    # XGBoost booster as raw bytes (saved alongside).
    out_xgb = os.path.join(MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_v2.xgb")
    xgb_m.save_model(out_xgb)

    meta = {
        "snapshot": snapshot,
        "feature_cols": feat_cols,
        "categorical_cols": cat_cols,
        "ensemble_weights": {
            "lgb": float(weights[0]),
            "xgb": float(weights[1]),
            "lr":  float(weights[2]),
        },
        "anchor_alpha": float(alpha),
        "lr_coef": lr_coef,
        "lr_intercept": lr_intercept,
        "lr_feat_order": lr_feat_order,
        "lr_mean": lr_mean.to_dict(),
        "lr_std": lr_std.to_dict(),
        "n_train_rows": int(len(X)),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "R12_F1_inplay_winprob_v2",
    }
    meta_path = os.path.join(
        MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_v2_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return {
        "lgb_path": out_lgb,
        "xgb_path": out_xgb,
        "meta_path": meta_path,
        "alpha": float(alpha),
        "weights": meta["ensemble_weights"],
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Probe R12_F1: In-Play WinProb v2 (anchor + ensemble) ===", flush=True)

    print("\n[1] Loading linescores + season_games ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    print(f"  Linescores: {len(linescores)}, SeasonGames: {len(season_games)}",
          flush=True)

    print("\n[2] Building snapshot rows ...", flush=True)
    df = build_rows(linescores, season_games)
    df_endq3 = df[df["snapshot"] == "endQ3"]
    valid_games = set(df_endq3["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy()
    print(f"  After endQ3 total_pts filter: {len(df)} rows, "
          f"{len(valid_games)} games", flush=True)

    v1_brier = {"endQ1": 0.2323, "endQ2": 0.1903, "endQ3": 0.1350}

    all_results: Dict[str, Any] = {}
    ship_snapshots: List[str] = []

    for snapshot in ["endQ1", "endQ2", "endQ3"]:
        print(f"\n[3] Snapshot: {snapshot}", flush=True)
        sub = df[df["snapshot"] == snapshot].copy()
        feat_cols = SNAP_FEATURES[snapshot]
        X = sub[feat_cols].copy()
        y = sub["home_team_won"].astype(int).copy()
        pregame = sub["pregame_win_prob"].astype(float).copy()

        print(f"  Rows: {len(sub)}, home_win_rate={y.mean():.3f}", flush=True)

        fold_results, summary = walk_forward_cv(X, y, pregame, snapshot, n_folds=4)
        means = mean_metrics(fold_results)

        snap_ship = means.get("brier", 9.0) <= SHIP_BRIER
        if snap_ship:
            ship_snapshots.append(snapshot)

        all_results[snapshot] = {
            "n_games": int(len(valid_games)),
            "n_rows": int(len(sub)),
            "folds": fold_results,
            "mean": means,
            "anchor_alpha_mean": summary["alpha_mean"],
            "stacker_weights_mean": summary["weights_mean"],
            "v1_brier": v1_brier.get(snapshot),
            "delta_brier_vs_v1": (
                float(means.get("brier", 0.0) - v1_brier[snapshot])
                if snapshot in v1_brier and means else None
            ),
            "passes_ship_gate": snap_ship,
        }
        print(
            f"  {snapshot} MEAN: AUC={means.get('auc', 0):.4f}, "
            f"Brier={means.get('brier', 0):.4f} "
            f"(v1: {v1_brier[snapshot]:.4f}, "
            f"delta {means.get('brier', 0) - v1_brier[snapshot]:+.4f}), "
            f"Acc={means.get('accuracy', 0):.4f} "
            f"=> {'SHIP' if snap_ship else 'REJECT'}",
            flush=True,
        )

    # SHIP gate: endQ1 OR endQ2 must pass.
    target_passes = any(s in ship_snapshots for s in ("endQ1", "endQ2"))
    status = "SHIP" if target_passes else "REJECT"

    # Train production models for any snapshot that passed (endQ1/endQ2).
    production_artifacts: Dict[str, Any] = {}
    if target_passes:
        print("\n[4] Training production v2 models for passing snapshots ...",
              flush=True)
        for snap in ship_snapshots:
            if snap not in ("endQ1", "endQ2"):
                continue
            print(f"  Training {snap} v2 production ...", flush=True)
            production_artifacts[snap] = train_production_model(df, snap)
            print(f"    -> {production_artifacts[snap]}", flush=True)

    elapsed = time.time() - t0
    if target_passes:
        ship_reason = (
            f"Snapshots passing 0.183 gate: {ship_snapshots}; v1 had only endQ3."
        )
    else:
        best = min(all_results[s]["mean"].get("brier", 9.0)
                   for s in ("endQ1", "endQ2"))
        ship_reason = (
            f"Neither endQ1 nor endQ2 cleared 0.183 (best={best:.4f})."
        )

    result = {
        "probe": "R12_F1_inplay_winprob_v2",
        "status": status,
        "ship_reason": ship_reason,
        "ship_snapshots": ship_snapshots,
        "ship_gate": {"max_brier": SHIP_BRIER},
        "snapshots": all_results,
        "production_artifacts": production_artifacts,
        "elapsed_s": float(elapsed),
        "n_folds": 4,
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"\n{'='*60}", flush=True)
    print(f"RESULT: {status}", flush=True)
    print(f"Reason: {ship_reason}", flush=True)
    print(f"Results saved to: {OUT_JSON}", flush=True)
    print(f"Elapsed: {elapsed:.1f}s", flush=True)

    print("\n=== Snapshot Summary (v1 -> v2) ===", flush=True)
    for snap, res in all_results.items():
        m = res["mean"]
        v1 = res["v1_brier"]
        v2 = m.get("brier", 0.0)
        print(
            f"  {snap}: Brier {v1:.4f} -> {v2:.4f} ({v2 - v1:+.4f}), "
            f"Acc={m.get('accuracy', 0):.4f}, "
            f"alpha={res['anchor_alpha_mean']:.3f} "
            f"[{'SHIP' if res['passes_ship_gate'] else 'REJECT'}]",
            flush=True,
        )


if __name__ == "__main__":
    main()
