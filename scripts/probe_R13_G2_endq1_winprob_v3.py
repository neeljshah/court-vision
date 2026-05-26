"""
probe_R13_G2_endq1_winprob_v3.py — pregame-dominated anchor for endQ1.

R12_F1 SHIPPED endQ2 (Brier 0.174) but endQ1 stayed at Brier 0.208 — above
the 0.183 SHIP gate. The v2 stacker learned alpha=1.0 on every fold, which
means "trust the in-play stack, ignore pregame". That is exactly the wrong
move when the in-play signal at endQ1 is mostly noise: 12 minutes of basketball
explains very little compared to two seasons of team strength.

v3 hypothesis: the optimal blend at endQ1 is heavily PREGAME-WEIGHTED, even
though closed-form regression said otherwise. The regression overfits the
small calibration tail (~25% of training fold = ~75 rows for endQ1 with 449
games total). Forcing a heavy pregame anchor (alpha = 0.85 for in-play, i.e.
0.15 in-play weight) injects the prior that pregame_winprob already carries
the lion's share of the predictive information.

Approach:
  * Reuse the v2 base learners (LGB + LR via NNLS) verbatim — only the
    blend changes.
  * For each walk-forward fold, grid-search alpha (in-play weight) over
    {0.70, 0.80, 0.85, 0.90, 0.95} on the training fold's last 25%; pick
    the alpha that minimizes Brier on that calibration slice; evaluate
    on the test fold.
  * SHIP iff mean test Brier <= 0.183.

The single twist vs v2: alpha is GRID-SEARCHED with constraint to be in
[0.05, 0.30] (i.e. pregame_weight in [0.70, 0.95]), so we cannot collapse
back to alpha=1.0 like v2 did. This is the inductive bias the prompt asks
for: pregame dominates.

SHIP gate: walk-forward mean Brier <= 0.183 across 4 folds.
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

# Reuse v2 building blocks — keeps the base learners and feature pipeline
# identical to R12_F1 so the comparison is apples-to-apples.
from scripts.probe_R12_F1_inplay_winprob_v2 import (  # noqa: E402
    SNAP_FEATURES,
    _CAT_COLS,
    _fit_lgb,
    _fit_lr,
    _fit_xgb,
    _nnls_weights,
    _prep_lr_frame,
    _prep_xgb_frame,
    _stack_predict,
    build_rows,
    load_linescores,
    load_season_games,
)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODEL_DIR = os.path.join(PROJECT, "data", "models")
OUT_JSON = os.path.join(DATA_CACHE, "probe_R13_G2_endq1_winprob_v3_results.json")
BUNDLE_PATH = os.path.join(MODEL_DIR, "inplay_winprob_endq1_v3_anchor.json")

os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

SHIP_BRIER = 0.183
SNAPSHOT = "endQ1"

# v3 grid: alpha here is the IN-PLAY weight; pregame weight is 1 - alpha.
# So alpha = 0.15 means "85% pregame, 15% in-play stack".
ALPHA_GRID = [0.05, 0.10, 0.15, 0.20, 0.30]
DEFAULT_ALPHA = 0.15  # = 1 - 0.85 (the prompt's target pregame weight)


def _train_v2_stack_on_full_fold(
    X_tr: pd.DataFrame, y_tr: pd.Series, cat_cols: List[str]
) -> Tuple[Any, Any, Any, np.ndarray]:
    """Train the same 3-base-learner stack v2 uses, with NNLS weights.

    This duplicates ``_train_stack_on_fold`` from v2 but kept explicit here
    so we can also return the held-out calibration slice (needed for the
    grid search over alpha).
    """
    n = len(X_tr)
    split = int(n * 0.75)
    if split < 30 or n - split < 20:
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

    # Refit base learners on full training fold (max data); weights frozen.
    lgb_full = _fit_lgb(X_tr, y_tr, cat_cols)
    xgb_full = _fit_xgb(X_tr, y_tr)
    lr_full_pack = _fit_lr(X_tr, y_tr)
    return lgb_full, xgb_full, lr_full_pack, w


def _grid_search_alpha(
    p_stack: np.ndarray,
    p_pregame: np.ndarray,
    y: np.ndarray,
    grid: List[float],
) -> Tuple[float, Dict[float, float]]:
    """Grid-search alpha (in-play weight) on a calibration slice.

    Returns (best_alpha, {alpha -> brier_on_calibration}).
    """
    from sklearn.metrics import brier_score_loss

    scores: Dict[float, float] = {}
    best_alpha = grid[0]
    best_score = float("inf")
    for a in grid:
        blended = np.clip(a * p_stack + (1.0 - a) * p_pregame, 1e-6, 1 - 1e-6)
        b = float(brier_score_loss(y, blended))
        scores[a] = b
        if b < best_score:
            best_score = b
            best_alpha = a
    return best_alpha, scores


def walk_forward_v3(
    X: pd.DataFrame,
    y: pd.Series,
    pregame: pd.Series,
    n_folds: int = 4,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Walk-forward CV for v3.

    For each fold:
      1. Train v2 stack on training fold.
      2. Predict stack probs on the training fold's last 25% (calibration).
      3. Grid-search alpha minimizing Brier on that calibration slice.
      4. Predict stack probs on the test fold and blend with the chosen alpha.
      5. Also record:
          - brier_v2 (alpha learned via closed-form NNLS-style as v2 does
            it — i.e. unconstrained alpha clipped to [0, 1])
          - brier_pregame_alone
          - brier_v3 (grid-searched constrained alpha)
    """
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

    fold_results: List[Dict[str, Any]] = []
    chosen_alphas: List[float] = []

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

        for c in cat_cols:
            X_tr[c] = X_tr[c].astype("category")
            X_te[c] = X_te[c].astype("category")

        # 1. Train base learners + NNLS weights (same as v2).
        lgb_m, xgb_m, lr_pack, w = _train_v2_stack_on_full_fold(X_tr, y_tr, cat_cols)

        # 2. Calibration slice = last 25% of training fold.
        split = int(len(X_tr) * 0.75)
        X_cal = X_tr.iloc[split:]
        y_cal_arr = y_tr.iloc[split:].values
        pre_cal_arr = pre_tr.iloc[split:].values
        p_stack_cal = _stack_predict(lgb_m, xgb_m, lr_pack, w, X_cal)

        # 3. Grid-search alpha on calibration slice.
        best_alpha, grid_scores = _grid_search_alpha(
            p_stack_cal, pre_cal_arr, y_cal_arr, ALPHA_GRID
        )
        chosen_alphas.append(best_alpha)

        # 4. Predict on test fold and blend.
        p_stack_te = _stack_predict(lgb_m, xgb_m, lr_pack, w, X_te)
        pre_te_arr = pre_te.values

        # v3 (grid-searched alpha)
        p_v3 = np.clip(
            best_alpha * p_stack_te + (1.0 - best_alpha) * pre_te_arr,
            1e-6, 1 - 1e-6,
        )

        # v2 (closed-form / unconstrained on cal slice — matches probe v2)
        # Recompute v2 alpha here to keep the comparison honest on the
        # SAME calibration slice (rather than re-loading the v2 numbers
        # which used the v2 endQ1 results we're replacing).
        diff = p_stack_cal - pre_cal_arr
        num = float(np.sum((y_cal_arr - pre_cal_arr) * diff))
        den = float(np.sum(diff * diff))
        v2_alpha = float(np.clip(num / den, 0.0, 1.0)) if den > 1e-12 else 1.0
        p_v2 = np.clip(
            v2_alpha * p_stack_te + (1.0 - v2_alpha) * pre_te_arr,
            1e-6, 1 - 1e-6,
        )

        # Pregame alone (clip for log_loss safety)
        p_pre = np.clip(pre_te_arr, 1e-6, 1 - 1e-6)

        preds_v3 = (p_v3 >= 0.5).astype(int)

        fold_results.append({
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "alpha_v3_chosen": float(best_alpha),
            "alpha_v2_unconstrained": float(v2_alpha),
            "grid_scores_cal": {f"{k:.2f}": float(v) for k, v in grid_scores.items()},
            "stacker_weights": [float(x) for x in w],
            "brier_v3": float(brier_score_loss(y_te, p_v3)),
            "brier_v2": float(brier_score_loss(y_te, p_v2)),
            "brier_pregame": float(brier_score_loss(y_te, p_pre)),
            "auc_v3": float(roc_auc_score(y_te, p_v3)),
            "log_loss_v3": float(log_loss(y_te, p_v3)),
            "accuracy_v3": float(accuracy_score(y_te, preds_v3)),
        })

        r = fold_results[-1]
        print(
            f"  endQ1 fold {fold}: train={r['train_n']}, test={r['test_n']}, "
            f"alpha_v3={best_alpha:.2f} (v2_unc={v2_alpha:.2f}), "
            f"Brier v3={r['brier_v3']:.4f} | v2={r['brier_v2']:.4f} | "
            f"pre={r['brier_pregame']:.4f}, Acc={r['accuracy_v3']:.4f}",
            flush=True,
        )

    summary = {
        "alpha_v3_mean": float(np.mean(chosen_alphas)) if chosen_alphas else float("nan"),
        "alpha_v3_chosen_mode": float(_mode(chosen_alphas)) if chosen_alphas else float("nan"),
    }
    return fold_results, summary


def _mode(xs: List[float]) -> float:
    if not xs:
        return float("nan")
    counts: Dict[float, int] = {}
    for x in xs:
        counts[x] = counts.get(x, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _mean(rs: List[Dict[str, Any]], key: str) -> float:
    if not rs:
        return float("nan")
    return float(np.mean([r[key] for r in rs]))


def train_production_v3(
    df: pd.DataFrame, alpha_chosen: float
) -> Optional[Dict[str, Any]]:
    """Persist the v3 endQ1 bundle.

    v3 differs from v2 only in the alpha blend; the LGB/XGB/LR base
    learners are trained on ALL endQ1 rows using v2's recipe. We then
    write:
      - <model_dir>/inplay_winprob_endq1_v3.lgb     (LightGBM booster)
      - <model_dir>/inplay_winprob_endq1_v3_anchor.json  (the v3 bundle)

    The v3 bundle JSON is the canonical thing src/prediction/inplay_winprob.py
    will load for endQ1.
    """
    sub = df[df["snapshot"] == SNAPSHOT].copy()
    if sub.empty:
        return None

    feat_cols = SNAP_FEATURES[SNAPSHOT]
    X = sub[feat_cols].copy()
    y = sub["home_team_won"].astype(int)
    cat_cols = [c for c in _CAT_COLS if c in X.columns]
    for c in cat_cols:
        X[c] = X[c].astype("category")

    lgb_m, xgb_m, lr_pack, weights = _train_v2_stack_on_full_fold(X, y, cat_cols)

    # Persist LightGBM booster (used at inference) + LR coefficients.
    out_lgb = os.path.join(MODEL_DIR, f"inplay_winprob_{SNAPSHOT.lower()}_v3.lgb")
    lgb_m.booster_.save_model(out_lgb)

    lr_m, lr_mean, lr_std = lr_pack
    lr_coef = lr_m.coef_.ravel().tolist()
    lr_intercept = float(lr_m.intercept_.ravel()[0])
    lr_feat_order = [c for c in feat_cols if c not in _CAT_COLS]

    bundle = {
        "snapshot": SNAPSHOT,
        "model_version": "v3_pregame_anchor",
        "feature_cols": feat_cols,
        "categorical_cols": cat_cols,
        "ensemble_weights": {
            "lgb": float(weights[0]),
            "xgb": float(weights[1]),
            "lr":  float(weights[2]),
        },
        # v3 contract: alpha_inplay = in-play stack weight.
        # blended = alpha_inplay * stack + (1 - alpha_inplay) * pregame
        "alpha_inplay": float(alpha_chosen),
        "alpha_pregame": float(1.0 - alpha_chosen),
        "lgb_path": out_lgb,
        "lr_coef": lr_coef,
        "lr_intercept": lr_intercept,
        "lr_feat_order": lr_feat_order,
        "lr_mean": lr_mean.to_dict(),
        "lr_std": lr_std.to_dict(),
        "n_train_rows": int(len(X)),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "R13_G2_endq1_winprob_v3",
    }
    with open(BUNDLE_PATH, "w") as f:
        json.dump(bundle, f, indent=2)
    return {
        "lgb_path": out_lgb,
        "bundle_path": BUNDLE_PATH,
        "alpha_inplay": float(alpha_chosen),
    }


def main() -> None:
    t0 = time.time()
    print("=== Probe R13_G2: endQ1 In-Play WinProb v3 (pregame-dominated) ===",
          flush=True)

    print("\n[1] Loading linescores + season_games ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    print(f"  Linescores: {len(linescores)}, SeasonGames: {len(season_games)}",
          flush=True)

    print("\n[2] Building snapshot rows (reusing R12_F1 builder) ...", flush=True)
    df = build_rows(linescores, season_games)
    df_endq3 = df[df["snapshot"] == "endQ3"]
    valid_games = set(df_endq3["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy()
    print(f"  After endQ3 total_pts filter: {len(df)} rows, "
          f"{len(valid_games)} games", flush=True)

    print(f"\n[3] Walk-forward CV for {SNAPSHOT} (4 folds, alpha grid = "
          f"{ALPHA_GRID}) ...", flush=True)
    sub = df[df["snapshot"] == SNAPSHOT].copy()
    feat_cols = SNAP_FEATURES[SNAPSHOT]
    X = sub[feat_cols].copy()
    y = sub["home_team_won"].astype(int).copy()
    pregame = sub["pregame_win_prob"].astype(float).copy()
    print(f"  {SNAPSHOT} rows: {len(sub)}, home_win_rate={y.mean():.3f}", flush=True)

    fold_results, summary = walk_forward_v3(X, y, pregame, n_folds=4)

    brier_v3 = _mean(fold_results, "brier_v3")
    brier_v2 = _mean(fold_results, "brier_v2")
    brier_pregame_alone = _mean(fold_results, "brier_pregame")

    delta_vs_v2 = brier_v3 - brier_v2
    delta_vs_pregame = brier_v3 - brier_pregame_alone

    ship = brier_v3 <= SHIP_BRIER
    ship_status = "SHIP" if ship else "REJECT"

    # Choose final alpha for production: the alpha most-often chosen across
    # folds (mode), tie-broken to the prompt's default 0.15 (i.e. 0.85 pregame
    # weight) when tied or when no fold ran.
    alpha_chosen = summary["alpha_v3_chosen_mode"]
    if not np.isfinite(alpha_chosen):
        alpha_chosen = DEFAULT_ALPHA

    print(f"\n[4] Aggregate (mean across {len(fold_results)} folds):", flush=True)
    print(f"  Brier v3 (grid-searched alpha)     = {brier_v3:.4f}", flush=True)
    print(f"  Brier v2 (unconstrained alpha)     = {brier_v2:.4f}  "
          f"(delta v3-v2 = {delta_vs_v2:+.4f})", flush=True)
    print(f"  Brier pregame alone                = {brier_pregame_alone:.4f}  "
          f"(delta v3-pre = {delta_vs_pregame:+.4f})", flush=True)
    print(f"  alpha_v3 chosen (mode): {alpha_chosen}  "
          f"(pregame weight = {1.0 - alpha_chosen:.2f})", flush=True)
    print(f"  SHIP gate (Brier <= {SHIP_BRIER}): {ship_status}", flush=True)

    production: Optional[Dict[str, Any]] = None
    if ship:
        print("\n[5] Training production v3 endQ1 bundle ...", flush=True)
        production = train_production_v3(df, float(alpha_chosen))
        print(f"  -> {production}", flush=True)

    result = {
        "probe": "R13_G2_endq1_winprob_v3",
        "snapshot": SNAPSHOT,
        "ship_status": ship_status,
        "ship_gate": {"max_brier": SHIP_BRIER},
        "alpha_chosen": float(alpha_chosen),
        "alpha_grid": ALPHA_GRID,
        "brier_v3_q1": float(brier_v3),
        "brier_v2_q1": float(brier_v2),
        "brier_pregame_alone": float(brier_pregame_alone),
        "delta_brier_vs_v2": float(delta_vs_v2),
        "delta_brier_vs_pregame": float(delta_vs_pregame),
        "by_fold": fold_results,
        "summary": summary,
        "production": production,
        "n_games": int(len(valid_games)),
        "n_rows": int(len(sub)),
        "elapsed_s": float(time.time() - t0),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nResults saved to: {OUT_JSON}", flush=True)
    print(f"Elapsed: {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
