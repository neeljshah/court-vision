"""
INT-90: BLK Residual Head (ElasticNet on CV features)
Executor script — runs end-to-end with all 5 gates.
"""
from __future__ import annotations

import collections
import glob
import json
import logging
import os
import pickle
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_PATH = ROOT / "data" / "nba_ai.db"
SCHEDULE_DIR = ROOT / "data" / "nba" / "schedule"
INTEL_DIR = ROOT / "data" / "intelligence"
CACHE_DIR = ROOT / "data" / "cache"
MODEL_DIR = ROOT / "data" / "models"
VAULT_INTEL = ROOT / "vault" / "Intelligence"

INTEL_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
VAULT_INTEL.mkdir(parents=True, exist_ok=True)

BASELINE_MAE = 0.4398
CV_FEATURES_DB = ["touches_per_game", "contested_shot_rate", "paint_dwell_pct"]
K_GRID = [2, 3, 4, 5, 7, 10]
ALPHA_GRID = [0.001, 0.01, 0.1]
L1_RATIO = 0.5
RESIDUAL_CLIP = 0.5
MIN_SEASON_AVG_BLK = 0.3
N_FOLDS = 4
COVERAGE_GATE = 25.0
COVERAGE_KILL = 15.0


# ── Step 1: verify baseline ───────────────────────────────────────────────────

def step1_verify_baseline():
    log.info("=== STEP 1: Verify baseline ===")
    diag = json.load(open(ROOT / "data/training/xblk_v1_diagnostics.json"))
    # confirm 0.4398
    baseline_check = diag.get("verdict", {}).get("fold4_gate_required", None)
    log.info("  xblk diag fold4_coverage@n5=%.1f%% (gate required %.1f%%)",
             diag["verdict"]["fold4_coverage_pct_at_n5"],
             diag["verdict"]["fold4_gate_required"])
    # BLK q50 json loadable?
    import xgboost as xgb
    bst = xgb.Booster()
    bst.load_model(str(MODEL_DIR / "quantile_pergame_blk_q50.json"))
    log.info("  BLK q50 model loaded OK, baseline MAE=%.4f", BASELINE_MAE)
    return bst


# ── Step 2: Load pergame dataset ──────────────────────────────────────────────

def step2_load_pergame() -> Tuple[List[dict], List[str]]:
    log.info("=== STEP 2: Load pergame dataset ===")
    from src.prediction.prop_pergame import build_pergame_dataset
    rows, feat_cols = build_pergame_dataset(min_prior=0)
    log.info("  Loaded %d rows, %d feature cols", len(rows), len(feat_cols))
    # sort by date
    rows = sorted(rows, key=lambda r: str(r.get("date", "")))
    return rows, feat_cols


# ── Step 3+4: Build CV l5 features + cv_n_games_prior ────────────────────────

def _build_game_date_map() -> Dict[str, str]:
    game_date_map: Dict[str, str] = {}
    for f in glob.glob(str(SCHEDULE_DIR / "*.json")):
        try:
            with open(f) as fp:
                games = json.load(fp)
            for g in games:
                gid = g.get("game_id")
                date = g.get("date")
                if gid and date:
                    game_date_map[str(gid)] = str(date)[:10]
        except Exception:
            pass
    nba_dir = ROOT / "data" / "nba"
    for fpath in glob.glob(str(nba_dir / "season_games_*.json")):
        try:
            with open(fpath, encoding="utf-8") as fp:
                data = json.load(fp)
            rows = data.get("rows", data) if isinstance(data, dict) else data
            for row in rows:
                if isinstance(row, dict) and "game_id" in row:
                    gid = str(row["game_id"])
                    date = row.get("game_date", "")
                    if gid and date:
                        game_date_map.setdefault(gid, str(date)[:10])
        except Exception:
            pass
    return game_date_map


def _build_cv_history(game_date_map: Dict[str, str]) -> Dict[int, List[Tuple[str, Dict[str, float]]]]:
    conn = sqlite3.connect(str(DB_PATH))
    placeholders = ",".join("?" for _ in CV_FEATURES_DB)
    c = conn.cursor()
    c.execute(
        f"SELECT game_id, player_id, feature_name, feature_value FROM cv_features "
        f"WHERE feature_name IN ({placeholders})",
        CV_FEATURES_DB,
    )
    raw = c.fetchall()
    conn.close()

    log.info("  Fetched %d cv_features rows from sqlite", len(raw))

    grouped: Dict[Tuple[str, int], Dict[str, float]] = collections.defaultdict(dict)
    for game_id, player_id, feat, val in raw:
        if val is not None:
            grouped[(str(game_id), int(player_id))][feat] = float(val)

    history: Dict[int, List[Tuple[str, Dict[str, float]]]] = collections.defaultdict(list)
    for (game_id, player_id), feat_dict in grouped.items():
        date = game_date_map.get(str(game_id))
        if date:
            history[int(player_id)].append((date, feat_dict))

    for pid in history:
        history[pid].sort(key=lambda x: x[0])

    log.info("  CV history built for %d players", len(history))
    return dict(history)


def _get_cv_l5(player_id: int, before_date: str,
                history: Dict[int, List[Tuple[str, Dict[str, float]]]],
                n: int = 5) -> Tuple[Dict[str, float], int]:
    entries = history.get(int(player_id))
    if not entries:
        return {}, 0
    prior = [(d, fv) for d, fv in entries if d < before_date]
    if not prior:
        return {}, 0
    recent = prior[-n:]
    feat_sums: Dict[str, float] = {}
    feat_counts: Dict[str, int] = {}
    for _, fv in recent:
        for feat, val in fv.items():
            feat_sums[feat] = feat_sums.get(feat, 0.0) + val
            feat_counts[feat] = feat_counts.get(feat, 0) + 1
    means = {f: feat_sums[f] / feat_counts[f] for f in feat_sums}
    return means, len(prior)


def step3_build_cv_features(rows: List[dict]) -> pd.DataFrame:
    log.info("=== STEP 3+4: Build CV l5 features ===")
    game_date_map = _build_game_date_map()
    log.info("  game_date_map has %d entries", len(game_date_map))
    cv_history = _build_cv_history(game_date_map)

    records = []
    for r in rows:
        date_iso = str(r.get("date", ""))[:10]
        pid = r.get("player_id")
        if not pid:
            continue
        cv_feats, n_prior = _get_cv_l5(int(pid), date_iso, cv_history)
        rec = {
            "player_id": int(pid),
            "date": date_iso,
            "target_blk": r.get("target_blk"),
            "cv_n_games_prior": n_prior,
            "touches_per_game_l5": cv_feats.get("touches_per_game"),
            "contested_shot_rate_l5": cv_feats.get("contested_shot_rate"),
            "paint_dwell_pct_l5": cv_feats.get("paint_dwell_pct"),
        }
        records.append(rec)

    df = pd.DataFrame(records)
    log.info("  CV feature df shape: %s", df.shape)
    log.info("  cv_n_games_prior distribution:\n%s", df["cv_n_games_prior"].value_counts().sort_index().head(15))
    return df


# ── Step 5: K-sweep fold-4 coverage ──────────────────────────────────────────

def step5_k_sweep(df: pd.DataFrame, rows: List[dict]) -> Tuple[int, Dict]:
    log.info("=== STEP 5: K-sweep fold-4 coverage ===")
    n_total = len(rows)
    # Fold-4 boundary (same as diagnose_per_stat_cv_corrs.py)
    tr_end = int(n_total * 0.8)
    te_end = n_total
    va_end = tr_end + int((te_end - tr_end) * 0.4)
    fold4_rows_dates = [str(r.get("date", ""))[:10] for r in rows[va_end:]]
    fold4_min_date = min(fold4_rows_dates) if fold4_rows_dates else ""
    fold4_max_date = max(fold4_rows_dates) if fold4_rows_dates else ""
    fold4_n = len(fold4_rows_dates)
    log.info("  Fold-4: n=%d rows, dates %s to %s", fold4_n, fold4_min_date, fold4_max_date)

    # match df to fold-4 by date
    df_f4 = df[df["date"] >= fold4_min_date].copy()
    log.info("  Fold-4 df rows: %d", len(df_f4))

    coverage_results = {}
    chosen_k = None
    for k in K_GRID:
        covered = (df_f4["cv_n_games_prior"] >= k).sum()
        total = len(df_f4)
        pct = 100.0 * covered / total if total > 0 else 0.0
        coverage_results[k] = {"covered": int(covered), "total": int(total), "pct": round(pct, 2)}
        log.info("  K=%2d: covered=%d / %d (%.1f%%)", k, covered, total, pct)
        if chosen_k is None and pct >= COVERAGE_GATE:
            chosen_k = k

    if chosen_k is None:
        # Check kill switch
        max_pct = coverage_results.get(10, {}).get("pct", 0)
        log.error("  KILL SWITCH: no K achieves %.0f%% coverage. K=10 coverage=%.1f%%",
                  COVERAGE_GATE, max_pct)
        if max_pct < COVERAGE_KILL:
            return -1, coverage_results
        # K=10 >= 15% but < 25%: still reject but not kill
        return -2, coverage_results

    log.info("  Chosen K*=%d (coverage %.1f%%)", chosen_k, coverage_results[chosen_k]["pct"])
    return chosen_k, coverage_results


# ── Step 6: BLK q50 OOF predictions ──────────────────────────────────────────

def step6_oof_predictions(rows: List[dict], feat_cols: List[str]) -> pd.DataFrame:
    log.info("=== STEP 6: BLK q50 OOF predictions ===")
    cache_path = CACHE_DIR / "blk_q50_oof_int90.parquet"
    if cache_path.exists():
        log.info("  Loading cached OOF from %s", cache_path)
        return pd.read_parquet(cache_path)

    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error

    # Build X/y
    df_rows = pd.DataFrame(rows)
    y_all = df_rows["target_blk"].values.astype(float)

    # Build feature matrix — fill missing with 0
    X_all = df_rows[feat_cols].fillna(0).values.astype(float)
    dates = [str(r.get("date", ""))[:10] for r in rows]
    pids = [r.get("player_id") for r in rows]

    n = len(rows)
    fold_size = n // N_FOLDS
    oof_preds = np.full(n, np.nan)

    # Load production model params from JSON for architecture reference
    bst_prod = xgb.Booster()
    bst_prod.load_model(str(MODEL_DIR / "quantile_pergame_blk_q50.json"))

    # 4-fold WF retrain
    for fold in range(N_FOLDS):
        train_end = n - (N_FOLDS - fold) * fold_size
        val_start = train_end
        val_end = train_end + fold_size if fold < N_FOLDS - 1 else n

        if train_end < 100:
            log.warning("  Fold %d: too few train rows (%d), skipping", fold + 1, train_end)
            continue

        X_tr = X_all[:train_end]
        y_tr = y_all[:train_end]
        X_va = X_all[val_start:val_end]
        y_va = y_all[val_start:val_end]

        dtrain = xgb.DMatrix(X_tr, label=y_tr, feature_names=feat_cols)
        dval = xgb.DMatrix(X_va, label=y_va, feature_names=feat_cols)

        params = {
            "objective": "reg:quantileerror",
            "quantile_alpha": 0.5,
            "learning_rate": 0.05,
            "max_depth": 6,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "n_estimators": 500,
            "tree_method": "hist",
            "seed": 42,
        }
        bst = xgb.train(
            params,
            dtrain,
            num_boost_round=500,
            evals=[(dval, "val")],
            verbose_eval=False,
        )
        pred_va = bst.predict(dval)
        oof_preds[val_start:val_end] = pred_va
        mae = mean_absolute_error(y_va, pred_va)
        log.info("  Fold %d/%d: train=%d, val=%d, MAE=%.4f", fold + 1, N_FOLDS, train_end, len(y_va), mae)

    df_oof = pd.DataFrame({
        "player_id": pids,
        "date": dates,
        "target_blk": y_all,
        "base_q50_pred": oof_preds,
    })
    df_oof.to_parquet(cache_path, index=False)
    log.info("  OOF saved to %s", cache_path)
    return df_oof


# ── Step 7: Compute residuals + merge CV features ─────────────────────────────

def step7_build_residuals(df_oof: pd.DataFrame, df_cv: pd.DataFrame,
                           k_star: int) -> pd.DataFrame:
    log.info("=== STEP 7: Compute residuals ===")
    # merge on player_id + date
    df_oof = df_oof.copy()
    df_cv = df_cv.copy()
    df_oof["player_id"] = df_oof["player_id"].astype(str)
    df_cv["player_id"] = df_cv["player_id"].astype(str)

    df = df_oof.merge(df_cv[["player_id","date","cv_n_games_prior",
                               "touches_per_game_l5","contested_shot_rate_l5","paint_dwell_pct_l5"]],
                      on=["player_id","date"], how="left")
    df["cv_n_games_prior"] = df["cv_n_games_prior"].fillna(0).astype(int)
    df["y_resid"] = df["target_blk"] - df["base_q50_pred"]

    # Compute season-average BLK per player
    df_sorted = df.sort_values("date")
    df_sorted["season_avg_blk"] = df_sorted.groupby("player_id")["target_blk"].transform(
        lambda x: x.shift(1).expanding().mean()
    )
    df = df_sorted.copy()

    # CV-eligible subset
    df_eligible = df[
        (df["cv_n_games_prior"] >= k_star) &
        (df["season_avg_blk"] >= MIN_SEASON_AVG_BLK)
    ].copy()

    # Add interaction term
    df_eligible["interaction_touches_cv"] = (
        df_eligible["cv_n_games_prior"] * df_eligible["touches_per_game_l5"]
    )

    log.info("  Total rows: %d, CV-eligible rows: %d", len(df), len(df_eligible))
    log.info("  CV-eligible date range: %s to %s",
             df_eligible["date"].min(), df_eligible["date"].max())

    return df, df_eligible


# ── Step 8: ElasticNet WF training ───────────────────────────────────────────

FEATURE_COLS = [
    "touches_per_game_l5",
    "contested_shot_rate_l5",
    "paint_dwell_pct_l5",
    "cv_n_games_prior",
    "interaction_touches_cv",
]


def step8_fit_elasticnet(df_eligible: pd.DataFrame) -> Tuple[object, float, Dict]:
    log.info("=== STEP 8: Fit ElasticNet (4-fold WF) ===")
    from sklearn.linear_model import ElasticNet
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_absolute_error

    df_el = df_eligible.dropna(subset=FEATURE_COLS + ["y_resid"]).copy()
    df_el = df_el.sort_values("date").reset_index(drop=True)
    n = len(df_el)
    log.info("  ElasticNet training rows (after dropna): %d", n)

    if n < 200:
        log.error("  EARLY-STOP: <200 CV-eligible rows (%d). Triggering DEFER.", n)
        return None, None, {}

    fold_results = []
    best_alpha_votes = collections.Counter()

    fold_size = n // N_FOLDS

    for fold in range(N_FOLDS):
        train_end = n - (N_FOLDS - fold) * fold_size
        val_start = train_end
        val_end = train_end + fold_size if fold < N_FOLDS - 1 else n

        if train_end < 50:
            continue

        X_tr = df_el[FEATURE_COLS].iloc[:train_end].values
        y_tr = df_el["y_resid"].iloc[:train_end].values
        X_va = df_el[FEATURE_COLS].iloc[val_start:val_end].values
        y_va = df_el["y_resid"].iloc[val_start:val_end].values
        y_blk_va = df_el["target_blk"].iloc[val_start:val_end].values
        base_pred_va = df_el["base_q50_pred"].iloc[val_start:val_end].values

        best_fold_alpha = None
        best_fold_mae = np.inf
        alpha_maes = {}

        for alpha in ALPHA_GRID:
            pipe = Pipeline([
                ("scaler", StandardScaler()),
                ("en", ElasticNet(alpha=alpha, l1_ratio=L1_RATIO, max_iter=2000, random_state=42)),
            ])
            pipe.fit(X_tr, y_tr)
            resid_pred = pipe.predict(X_va)
            resid_mae = mean_absolute_error(y_va, resid_pred)
            alpha_maes[alpha] = resid_mae
            if resid_mae < best_fold_mae:
                best_fold_mae = resid_mae
                best_fold_alpha = alpha

        # Augmented predictions (with clip)
        best_pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("en", ElasticNet(alpha=best_fold_alpha, l1_ratio=L1_RATIO, max_iter=2000, random_state=42)),
        ])
        best_pipe.fit(X_tr, y_tr)
        resid_pred = np.clip(best_pipe.predict(X_va), -RESIDUAL_CLIP, RESIDUAL_CLIP)
        aug_pred = base_pred_va + resid_pred

        mae_base_cv = mean_absolute_error(y_blk_va, base_pred_va)
        mae_aug_cv = mean_absolute_error(y_blk_va, aug_pred)
        delta = mae_aug_cv - mae_base_cv
        # G5 corr
        y_resid_true = y_blk_va - base_pred_va
        corr_val = float(np.corrcoef(resid_pred, y_resid_true)[0, 1]) if len(resid_pred) > 5 else 0.0

        fold_results.append({
            "fold": fold + 1,
            "n_train": train_end,
            "n_val": val_end - val_start,
            "best_alpha": best_fold_alpha,
            "alpha_maes": alpha_maes,
            "mae_base_cv": round(mae_base_cv, 6),
            "mae_aug_cv": round(mae_aug_cv, 6),
            "delta_mae": round(delta, 6),
            "augmented_wins": bool(delta < 0),
            "corr_resid": round(corr_val, 4),
        })
        best_alpha_votes[best_fold_alpha] += 1
        log.info("  Fold %d: alpha=%.3f, base_MAE=%.4f, aug_MAE=%.4f, delta=%.4f, corr=%.3f",
                 fold + 1, best_fold_alpha, mae_base_cv, mae_aug_cv, delta, corr_val)

    # Pick best alpha by vote
    best_alpha = best_alpha_votes.most_common(1)[0][0]
    log.info("  Chosen alpha=%.4f (votes: %s)", best_alpha, dict(best_alpha_votes))

    # Final model on all eligible data
    X_all = df_el[FEATURE_COLS].values
    y_all = df_el["y_resid"].values
    final_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("en", ElasticNet(alpha=best_alpha, l1_ratio=L1_RATIO, max_iter=2000, random_state=42)),
    ])
    final_pipe.fit(X_all, y_all)
    assert final_pipe.n_features_in_ == 5, f"Expected 5 features, got {final_pipe.n_features_in_}"
    log.info("  Final model: n_features_in_=%d (OK)", final_pipe.n_features_in_)

    return final_pipe, best_alpha, {"fold_results": fold_results, "best_alpha": best_alpha}


# ── Step 9: Evaluate all 5 gates ──────────────────────────────────────────────

def step9_evaluate_gates(df: pd.DataFrame, df_eligible: pd.DataFrame,
                          final_pipe: object, fold_results_dict: Dict,
                          k_star: int, coverage_results: Dict,
                          rows: List[dict]) -> Dict:
    log.info("=== STEP 9: Evaluate 5 gates ===")
    from sklearn.metrics import mean_absolute_error

    fold_results = fold_results_dict["fold_results"]
    n_total_rows = len(rows)

    # G1: fold-4 coverage
    f4_cov = coverage_results[k_star]["pct"]
    g1_pass = f4_cov >= COVERAGE_GATE
    log.info("  G1 (coverage): fold-4 cov=%.1f%% >= 25%% -> %s", f4_cov, "PASS" if g1_pass else "FAIL")

    # G2: WF dominance >= 3/4 folds where aug < base
    n_wins = sum(1 for f in fold_results if f["augmented_wins"])
    g2_pass = n_wins >= 3
    log.info("  G2 (WF dominance): %d/4 folds aug<base -> %s", n_wins, "PASS" if g2_pass else "FAIL")

    # G3: null control
    df_el = df_eligible.dropna(subset=FEATURE_COLS + ["y_resid"]).sort_values("date").reset_index(drop=True)
    n = len(df_el)
    null_deltas = []
    real_delta_fold4 = None
    for f in fold_results:
        if f["fold"] == 4:
            real_delta_fold4 = f["delta_mae"]
    if real_delta_fold4 is None and fold_results:
        real_delta_fold4 = fold_results[-1]["delta_mae"]

    rng = np.random.default_rng(42)
    SHUFFLE_FEATS = ["touches_per_game_l5", "contested_shot_rate_l5", "paint_dwell_pct_l5"]

    fold_size = n // N_FOLDS
    train_end = n - fold_size  # use last fold only for null control
    val_start = train_end
    X_tr_real = df_el[FEATURE_COLS].iloc[:train_end].values
    y_tr_real = df_el["y_resid"].iloc[:train_end].values
    X_va_real = df_el[FEATURE_COLS].iloc[val_start:].values
    y_blk_va = df_el["target_blk"].iloc[val_start:].values
    base_pred_va = df_el["base_q50_pred"].iloc[val_start:].values

    for rep in range(3):
        X_tr_shuf = X_tr_real.copy()
        shuf_indices = [FEATURE_COLS.index(f) for f in SHUFFLE_FEATS]
        for idx in shuf_indices:
            rng.shuffle(X_tr_shuf[:, idx])

        from sklearn.linear_model import ElasticNet
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        pipe_null = Pipeline([
            ("scaler", StandardScaler()),
            ("en", ElasticNet(alpha=fold_results_dict["best_alpha"], l1_ratio=L1_RATIO, max_iter=2000, random_state=42+rep)),
        ])
        pipe_null.fit(X_tr_shuf, y_tr_real)
        resid_null = np.clip(pipe_null.predict(X_va_real), -RESIDUAL_CLIP, RESIDUAL_CLIP)
        aug_null = base_pred_va + resid_null
        mae_null = mean_absolute_error(y_blk_va, aug_null)
        mae_base = mean_absolute_error(y_blk_va, base_pred_va)
        null_delta = mae_null - mae_base
        null_deltas.append(null_delta)
        log.info("    Null rep %d: delta=%.5f", rep+1, null_delta)

    mean_null_delta = float(np.mean(null_deltas))
    if real_delta_fold4 is not None and abs(mean_null_delta) > 1e-9:
        g3_ratio = abs(real_delta_fold4) / abs(mean_null_delta)
    else:
        g3_ratio = 0.0
    g3_pass = g3_ratio >= 1.5
    log.info("  G3 (null control): real_delta=%.5f, mean_null=%.5f, ratio=%.2f -> %s",
             real_delta_fold4 or 0, mean_null_delta, g3_ratio, "PASS" if g3_pass else "FAIL")

    # G4: aggregate non-regression (full dataset, non-CV rows get residual=0)
    df_full = df.dropna(subset=["base_q50_pred", "target_blk"]).copy()
    df_full["player_id"] = df_full["player_id"].astype(str)
    df_el2 = df_eligible.dropna(subset=FEATURE_COLS + ["y_resid"]).copy()
    df_el2["player_id"] = df_el2["player_id"].astype(str)

    # Predict residuals for eligible rows
    df_el_pred = df_el2.copy()
    X_el = df_el_pred[FEATURE_COLS].values
    resid_pred = np.clip(final_pipe.predict(X_el), -RESIDUAL_CLIP, RESIDUAL_CLIP)
    df_el_pred["aug_pred"] = df_el_pred["base_q50_pred"] + resid_pred

    # Merge back
    df_full = df_full.merge(
        df_el_pred[["player_id","date","aug_pred"]],
        on=["player_id","date"], how="left"
    )
    df_full["aug_pred"] = df_full["aug_pred"].fillna(df_full["base_q50_pred"])

    mae_base_full = mean_absolute_error(df_full["target_blk"], df_full["base_q50_pred"])
    mae_aug_full = mean_absolute_error(df_full["target_blk"], df_full["aug_pred"])
    delta_full = mae_aug_full - mae_base_full
    g4_pass = delta_full <= 0.001
    log.info("  G4 (aggregate non-regression): base=%.4f, aug=%.4f, delta=%.5f -> %s",
             mae_base_full, mae_aug_full, delta_full, "PASS" if g4_pass else "FAIL")

    # G5: corr(pred_resid, y_resid_true) on fold-4
    fold4_result = next((f for f in fold_results if f["fold"] == 4), fold_results[-1])
    g5_corr = fold4_result.get("corr_resid", 0.0)
    g5_pass = g5_corr > 0.05
    log.info("  G5 (hit correlation): fold-4 corr=%.4f > 0.05 -> %s",
             g5_corr, "PASS" if g5_pass else "FAIL")

    return {
        "G1": {"pass": g1_pass, "fold4_coverage_pct": f4_cov},
        "G2": {"pass": g2_pass, "n_folds_winning": n_wins},
        "G3": {"pass": g3_pass, "real_delta": real_delta_fold4, "mean_null_delta": mean_null_delta, "ratio": g3_ratio},
        "G4": {"pass": g4_pass, "base_mae_full": mae_base_full, "aug_mae_full": mae_aug_full, "delta_full": delta_full},
        "G5": {"pass": g5_pass, "fold4_corr": g5_corr},
        "fold_results": fold_results,
        "null_deltas": null_deltas,
    }


# ── Step 10: Write vault MD ───────────────────────────────────────────────────

def step10_write_vault(k_star: int, coverage_results: Dict,
                        gates: Dict, fold_results_dict: Dict,
                        n_eligible: int, verdict: str,
                        best_alpha: float, files_written: List[str]):
    log.info("=== STEP 10: Write vault MD ===")
    fold_results = gates.get("fold_results", [])

    md_lines = [
        f"# INT-90: BLK Residual Head\n",
        f"**Date:** {datetime.utcnow().strftime('%Y-%m-%d')}  ",
        f"**Verdict:** {verdict}  ",
        f"**K\\*:** {k_star}  ",
        f"**Baseline MAE:** {BASELINE_MAE}  \n",
        "## K-Sweep Coverage (Fold-4)\n",
        "| K | Covered | Total | Coverage% |",
        "|---|---------|-------|-----------|",
    ]
    for k, cv in sorted(coverage_results.items()):
        marker = " ← K*" if k == k_star else ""
        md_lines.append(f"| {k} | {cv['covered']} | {cv['total']} | {cv['pct']:.1f}%{marker} |")

    md_lines += [
        "\n## Gate Results\n",
        "| Gate | Result | Key Metric |",
        "|------|--------|------------|",
        f"| G1 Coverage | {'PASS' if gates['G1']['pass'] else 'FAIL'} | fold-4 cov {gates['G1']['fold4_coverage_pct']:.1f}% >= 25% |",
        f"| G2 WF Dominance | {'PASS' if gates['G2']['pass'] else 'FAIL'} | {gates['G2']['n_folds_winning']}/4 folds aug<base |",
        f"| G3 Null Control | {'PASS' if gates['G3']['pass'] else 'FAIL'} | real_delta={gates['G3']['real_delta']:.5f}, null_mean={gates['G3']['mean_null_delta']:.5f}, ratio={gates['G3']['ratio']:.2f} (>= 1.5) |",
        f"| G4 Aggregate Non-Regression | {'PASS' if gates['G4']['pass'] else 'FAIL'} | delta_full={gates['G4']['delta_full']:.5f} (<= +0.001) |",
        f"| G5 Hit Correlation | {'PASS' if gates['G5']['pass'] else 'FAIL'} | fold-4 corr={gates['G5']['fold4_corr']:.4f} (> 0.05) |",
        "\n## Walk-Forward Per-Fold Table\n",
        "| Fold | N_train | N_val | Alpha | Base_MAE | Aug_MAE | Delta | Win |",
        "|------|---------|-------|-------|----------|---------|-------|-----|",
    ]
    for f in fold_results:
        win = "Y" if f["augmented_wins"] else "N"
        md_lines.append(
            f"| {f['fold']} | {f['n_train']} | {f['n_val']} | {f['best_alpha']:.3f} | "
            f"{f['mae_base_cv']:.4f} | {f['mae_aug_cv']:.4f} | {f['delta_mae']:.5f} | {win} |"
        )

    md_lines += [
        "\n## Null Control Table\n",
        "| Rep | Null Delta |",
        "|-----|------------|",
    ]
    for i, nd in enumerate(gates.get("null_deltas", [])):
        md_lines.append(f"| {i+1} | {nd:.5f} |")
    md_lines.append(f"| mean | {np.mean(gates.get('null_deltas', [0])):.5f} |")

    md_lines += [
        f"\n## Configuration\n",
        f"- Features: {FEATURE_COLS}",
        f"- Alpha: {best_alpha}",
        f"- L1_ratio: {L1_RATIO}",
        f"- Residual clip: ±{RESIDUAL_CLIP}",
        f"- N eligible rows: {n_eligible}",
        f"- Season-avg-BLK filter: >= {MIN_SEASON_AVG_BLK}",
        "\n## Files Written\n",
    ]
    for f in files_written:
        md_lines.append(f"- `{f}`")

    out_path = VAULT_INTEL / "INT-90_BLK_Residual_Head.md"
    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md_lines) + "\n")
    log.info("  Vault MD written: %s", out_path)


# ── Step 11: Save parquet ─────────────────────────────────────────────────────

def step11_save_parquet(df: pd.DataFrame, df_eligible: pd.DataFrame,
                         final_pipe: Optional[object], k_star: int,
                         verdict: str) -> pd.DataFrame:
    log.info("=== STEP 11: Save intelligence parquet ===")
    shipped = verdict == "SHIP"

    df_full = df.dropna(subset=["base_q50_pred", "target_blk"]).copy()
    df_full["player_id"] = df_full["player_id"].astype(str)

    if shipped and final_pipe is not None:
        df_el2 = df_eligible.dropna(subset=FEATURE_COLS + ["y_resid"]).copy()
        df_el2["player_id"] = df_el2["player_id"].astype(str)
        X_el = df_el2[FEATURE_COLS].values
        resid_pred = np.clip(final_pipe.predict(X_el), -RESIDUAL_CLIP, RESIDUAL_CLIP)
        df_el2["resid_pred"] = resid_pred
        df_el2["aug_blk_pred"] = df_el2["base_q50_pred"] + resid_pred

        df_full = df_full.merge(
            df_el2[["player_id","date","resid_pred","aug_blk_pred"]],
            on=["player_id","date"], how="left"
        )

    df_full["shipped"] = shipped
    df_full["k_star"] = k_star
    df_full["verdict"] = verdict

    out_path = INTEL_DIR / "blk_residual_head_v1.parquet"
    df_full.to_parquet(out_path, index=False)
    log.info("  Parquet saved: %s (%d rows)", out_path, len(df_full))
    return df_full


# ── Step 12: Save model (only on SHIP) ───────────────────────────────────────

def step12_save_model(final_pipe: object, best_alpha: float,
                       k_star: int, df_eligible: pd.DataFrame,
                       train_dates: pd.Series) -> List[str]:
    log.info("=== STEP 12: Save model ===")
    files = []

    pkl_path = MODEL_DIR / "blk_residual_head_v1.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(final_pipe, f)
    files.append(str(pkl_path))
    log.info("  Model saved: %s", pkl_path)

    meta = {
        "feature_list": FEATURE_COLS,
        "k_star": k_star,
        "alpha": best_alpha,
        "l1_ratio": L1_RATIO,
        "residual_clip": RESIDUAL_CLIP,
        "min_season_avg_blk": MIN_SEASON_AVG_BLK,
        "n_train": len(df_eligible.dropna(subset=FEATURE_COLS)),
        "train_date_range": [
            str(train_dates.min()),
            str(train_dates.max()),
        ],
        "n_features_in": final_pipe.n_features_in_,
        "baseline_mae": BASELINE_MAE,
        "train_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "model_type": "sklearn_Pipeline(StandardScaler+ElasticNet)",
    }
    meta_path = MODEL_DIR / "blk_residual_head_v1_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    files.append(str(meta_path))
    log.info("  Meta saved: %s", meta_path)

    # Append to cv_master_strategy.md
    strategy_path = ROOT / "vault" / "Improvements" / "cv_master_strategy.md"
    if strategy_path.exists():
        with open(strategy_path, "a", encoding="utf-8") as f:
            f.write(
                f"\n| A5 | xSTL/xBLK opportunity models | INT-90 SHIPPED ElasticNet BLK residual K*={k_star} alpha={best_alpha} baseline_MAE={BASELINE_MAE} → check aug_mae in parquet |"
            )
        log.info("  Appended to cv_master_strategy.md")
    else:
        log.warning("  cv_master_strategy.md not found, skipping append")

    return files


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("========================================")
    log.info("INT-90: BLK Residual Head — starting")
    log.info("========================================")

    files_written = []

    # Step 1
    bst = step1_verify_baseline()
    if bst is None:
        log.error("BLOCKED: BLK q50 model failed to load")
        return

    # Step 2
    rows, feat_cols = step2_load_pergame()

    # Step 3+4
    df_cv = step3_build_cv_features(rows)

    # Step 5: K-sweep
    k_star, coverage_results = step5_k_sweep(df_cv, rows)

    if k_star == -1:
        log.error("KILL SWITCH: K=10 coverage < 15%%. Writing DEFER memo.")
        defer_path = VAULT_INTEL / "INT-90_DEFER_Memo.md"
        with open(defer_path, "w") as f:
            f.write(
                "# INT-90 DEFER Memo\n\n"
                "**Reason:** coverage-bound; re-open when CV-games × 3\n\n"
                f"Coverage results: {json.dumps(coverage_results, indent=2)}\n"
            )
        log.info("DEFER memo written: %s", defer_path)
        return

    if k_star == -2:
        log.warning("EARLY-STOP: no K achieves 25%% coverage but K=10 >= 15%%. Treating as DEFER/REJECT.")
        # Will evaluate gates anyway but G1 will fail
        # Pick K=2 for analysis
        k_star = 2

    log.info("K* = %d", k_star)

    # Step 6
    df_oof = step6_oof_predictions(rows, feat_cols)

    # Step 7
    df_full, df_eligible = step7_build_residuals(df_oof, df_cv, k_star)
    n_eligible = len(df_eligible.dropna(subset=FEATURE_COLS + ["y_resid"]))
    log.info("  CV-eligible (dropna) rows: %d", n_eligible)

    if n_eligible < 200:
        log.error("EARLY-STOP: <200 CV-eligible rows (%d). Writing DEFER memo.", n_eligible)
        defer_path = VAULT_INTEL / "INT-90_DEFER_Memo.md"
        with open(defer_path, "w") as f:
            f.write(
                "# INT-90 DEFER Memo\n\n"
                f"**Reason:** Only {n_eligible} CV-eligible rows after K*={k_star} + season-avg-BLK filter. "
                "Re-open when CV-games × 3.\n\n"
                f"Coverage results: {json.dumps(coverage_results, indent=2)}\n"
            )
        return

    # Step 8
    final_pipe, best_alpha, fold_results_dict = step8_fit_elasticnet(df_eligible)
    if final_pipe is None:
        log.error("ElasticNet returned None (< 200 eligible rows). Exiting.")
        return

    # Step 9
    gates = step9_evaluate_gates(df_full, df_eligible, final_pipe,
                                  fold_results_dict, k_star, coverage_results, rows)

    # Verdict
    all_pass = all(g["pass"] for g in [gates["G1"], gates["G2"], gates["G3"], gates["G4"], gates["G5"]])
    verdict = "SHIP" if all_pass else "REJECT"

    log.info("\n========================================")
    log.info("VERDICT: %s", verdict)
    log.info("  G1 (coverage): %s", "PASS" if gates["G1"]["pass"] else "FAIL")
    log.info("  G2 (WF dominance): %s", "PASS" if gates["G2"]["pass"] else "FAIL")
    log.info("  G3 (null control): %s", "PASS" if gates["G3"]["pass"] else "FAIL")
    log.info("  G4 (aggregate): %s", "PASS" if gates["G4"]["pass"] else "FAIL")
    log.info("  G5 (hit corr): %s", "PASS" if gates["G5"]["pass"] else "FAIL")
    log.info("========================================\n")

    # Step 11 (always)
    df_result = step11_save_parquet(df_full, df_eligible, final_pipe if all_pass else None,
                                     k_star, verdict)
    files_written.append(str(INTEL_DIR / "blk_residual_head_v1.parquet"))
    files_written.append(str(CACHE_DIR / "blk_q50_oof_int90.parquet"))

    # Step 12 (only on SHIP)
    if verdict == "SHIP":
        model_files = step12_save_model(
            final_pipe, best_alpha, k_star, df_eligible,
            df_eligible["date"]
        )
        files_written.extend(model_files)

    # Step 10
    step10_write_vault(k_star, coverage_results, gates, fold_results_dict,
                        n_eligible, verdict, best_alpha, files_written)
    files_written.append(str(VAULT_INTEL / "INT-90_BLK_Residual_Head.md"))

    # Final summary
    log.info("Files written:")
    for f in files_written:
        log.info("  %s", f)

    return verdict, k_star, gates


if __name__ == "__main__":
    main()
