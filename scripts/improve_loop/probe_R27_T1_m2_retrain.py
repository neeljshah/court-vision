"""probe_R27_T1_m2_retrain.py — Retry of R24_Q3 with 2025-26 backfills landed.

R25_R1 backfilled 1225/1230 2025-26 pregame feature rows (home_off_rtg etc).
R26_S2 backfilled 600+ 2025-26 linescores. This probe re-runs the
m2_family multi5 retraining decision now that the holdout has signal.

What it does
------------
1. Load all 4 seasons' pregame features (2022-23 ... 2025-26) + linescores
   from the canonical ROOT data dir (worktree's data/nba/ only carries the
   freshly backfilled 2025-26 schedule; everything else lives at root).
2. Score the EXISTING (deployed) m2_family artifacts on the 2025-26
   subset → per-target MAE_old.
3. Train a fresh 5-model multi5 ensemble per target on
   (2022-23 + 2023-24 + 2024-25) and score on 2025-26 → per-target MAE_new
   for the holdout fold + same architecture trained walk-forward
   (4 expanding folds, last = 2025-26).
4. SHIP GATE (strict):
     - new wins on >=3/4 targets by >=2% MAE on 2025-26 holdout
     - no target regresses by more than +1%
     - walk-forward 4/4 folds positive (new <= old) across at least 2 targets
5. If SHIP: backup old artifacts and refit on the full 4-season corpus
   (matching scripts/train_final_M2_family.py), persist to ROOT
   data/models/m2_family/. Clear R21_N5 cache.
6. If REJECT: leave artifacts untouched and write the diagnostic to
   data/cache/probe_R27_T1_results.json.

Hard rules
----------
LOCAL only — no SSH, no RunPod calls. Reads/writes the user's canonical
ROOT data dir (env NBA_AI_ROOT, defaulting to C:\\Users\\neelj\\nba-ai-system).

Usage
-----
    python scripts/improve_loop/probe_R27_T1_m2_retrain.py
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)


def _resolve_root() -> str:
    cand = os.environ.get("NBA_AI_ROOT") or r"C:\Users\neelj\nba-ai-system"
    return cand if os.path.isdir(os.path.join(cand, "data", "nba")) else PROJECT_DIR


ROOT_DIR = _resolve_root()
ROOT_DATA_NBA = os.path.join(ROOT_DIR, "data", "nba")
ROOT_MODELS_DIR = os.path.join(ROOT_DIR, "data", "models", "m2_family")
ROOT_BACKUP_DIR = os.path.join(ROOT_DIR, "data", "models", "m2_family_R20_M7_backup_R27_T1")
ROOT_CACHE_PATH = os.path.join(ROOT_DIR, "data", "cache", "probe_R27_T1_results.json")
ROOT_PRED_CACHE = os.path.join(ROOT_DIR, "data", "cache", "m2_family_predictions_cache.json")

# Worktree may carry its own freshly-backfilled 2025-26 — prefer it when present.
WORKTREE_2526 = os.path.join(PROJECT_DIR, "data", "nba", "season_games_2025-26.json")

FEAT_COLS = [
    "home_off_rtg", "home_def_rtg", "home_net_rtg", "home_pace",
    "home_efg_pct", "home_ts_pct", "home_tov_pct", "home_rest_days",
    "home_back_to_back", "home_last5_wins", "home_season_win_pct",
    "away_off_rtg", "away_def_rtg", "away_net_rtg", "away_pace",
    "away_efg_pct", "away_ts_pct", "away_tov_pct", "away_rest_days",
    "away_back_to_back", "away_last5_wins", "away_season_win_pct",
    "net_rtg_diff", "pace_diff", "home_advantage",
    "home_off_rtg_L10", "home_def_rtg_L10", "home_net_rtg_L10",
    "away_off_rtg_L10", "away_def_rtg_L10", "away_net_rtg_L10",
    "home_efg_L10", "away_efg_L10",
    "home_pace_variance", "away_pace_variance",
    "home_travel_miles", "away_travel_miles",
    "home_top_lineup_net_rtg", "away_top_lineup_net_rtg",
    "iso_matchup_edge", "home_pnr_ppp", "away_pnr_ppp",
    "home_hustle_deflections_pg", "away_hustle_deflections_pg",
    "home_stars_available", "away_stars_available",
    "home_bench_net_rtg", "away_bench_net_rtg",
    "home_tov_pct_L10", "away_tov_pct_L10",
    "home_oreb_pct_L10", "away_oreb_pct_L10",
    "home_ft_rate_L10", "away_ft_rate_L10",
    "home_off_rtg_home_L10", "away_off_rtg_away_L10",
    "home_off_rtg_vs_top_def", "away_off_rtg_vs_top_def",
    "home_srs", "away_srs",
    "home_elo", "away_elo", "elo_differential",
    "home_def_rtg_trend", "away_def_rtg_trend",
    "b2b_diff", "elo_pace_interaction",
    "ref_avg_fouls", "ref_home_win_pct", "ref_fta_tendency",
    "sim_win_prob", "sim_score_diff_mean", "sim_score_diff_std", "sim_pace_adj",
]

LGB_SEEDS = [42, 7, 100]
XGB_SEEDS = [42, 7]

TARGETS = {
    "total":    "total_pts_box",
    "spread":   "score_diff",
    "home_pts": "home_score",
    "away_pts": "away_score",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _load_season(fname: str) -> List[dict]:
    """Prefer worktree copy when present (worktree carries the freshly
    backfilled 2025-26), otherwise pull from ROOT."""
    if fname == "season_games_2025-26.json" and os.path.exists(WORKTREE_2526):
        p = WORKTREE_2526
    else:
        p = os.path.join(ROOT_DATA_NBA, fname)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    rows = d.get("rows", d) if isinstance(d, dict) else d
    return rows if isinstance(rows, list) else []


def load_dataset() -> Tuple[pd.DataFrame, List[str]]:
    rows: List[dict] = []
    for fname in ("season_games_2022-23.json", "season_games_2023-24.json",
                  "season_games_2024-25.json", "season_games_2025-26.json"):
        rows.extend(_load_season(fname))
    sg = pd.DataFrame(rows)

    with open(os.path.join(ROOT_DATA_NBA, "linescores_all.json"), encoding="utf-8") as f:
        d = json.load(f)
    ls_rows: List[dict] = []
    for gid, ls in d.items():
        try:
            hq = [float(ls.get(f"home_q{i}", 0) or 0) for i in range(1, 5)]
            aq = [float(ls.get(f"away_q{i}", 0) or 0) for i in range(1, 5)]
        except (TypeError, ValueError):
            continue
        h, a = sum(hq), sum(aq)
        if h <= 0 or a <= 0:
            continue
        # add OT pts if present (matches the original script's behaviour of
        # using just q1-q4 sums for h/a — keep parity)
        ls_rows.append({
            "game_id":       gid,
            "home_score":    h,
            "away_score":    a,
            "score_diff":    h - a,
            "total_pts_box": h + a,
        })
    ls = pd.DataFrame(ls_rows)
    merged = sg.merge(ls, on="game_id", how="inner")
    for col in ("home_off_rtg", "away_off_rtg", "home_pace", "away_pace"):
        merged = merged[merged[col] > 0]
    merged = merged.sort_values("game_date").reset_index(drop=True)
    avail = [c for c in FEAT_COLS if c in merged.columns]
    merged[avail] = merged[avail].fillna(0.0)
    return merged, avail


# ---------------------------------------------------------------------------
# Training / predicting helpers
# ---------------------------------------------------------------------------
def train_ensemble(X: np.ndarray, y: np.ndarray, seed_kwargs=None) -> List:
    """Return [3 LGB + 2 XGB] fitted models."""
    import lightgbm as lgb
    import xgboost as xgb
    models = []
    for seed in LGB_SEEDS:
        m = lgb.LGBMRegressor(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=seed, n_jobs=2, verbose=-1)
        m.fit(X, y)
        models.append(("lgb", seed, m))
    for seed in XGB_SEEDS:
        m = xgb.XGBRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=6,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            random_state=seed, n_jobs=2, verbosity=0)
        m.fit(X, y)
        models.append(("xgb", seed, m))
    return models


def predict_ensemble(models: List, X: np.ndarray) -> np.ndarray:
    preds = np.zeros(X.shape[0], dtype=float)
    for _, _, m in models:
        preds += m.predict(X)
    return preds / len(models)


def load_old_ensembles_from_disk() -> Dict[str, list]:
    """Load the currently-deployed m2_family ensemble (per target -> 5 models)
    from ROOT_MODELS_DIR. Returns {} if any artifact is missing."""
    import joblib
    out: Dict[str, list] = {}
    for tgt in TARGETS:
        models = []
        for seed in LGB_SEEDS:
            p = os.path.join(ROOT_MODELS_DIR, f"{tgt}_lgb_s{seed}.joblib")
            if not os.path.exists(p):
                return {}
            models.append(("lgb", seed, joblib.load(p)))
        for seed in XGB_SEEDS:
            p = os.path.join(ROOT_MODELS_DIR, f"{tgt}_xgb_s{seed}.joblib")
            if not os.path.exists(p):
                return {}
            models.append(("xgb", seed, joblib.load(p)))
        out[tgt] = models
    return out


def load_old_feature_cols() -> List[str]:
    p = os.path.join(ROOT_MODELS_DIR, "feature_cols.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Walk-forward evaluation
# ---------------------------------------------------------------------------
def _season_for_row(gid: str) -> str:
    """Map game_id prefix '00222' / '00223' / '00224' / '00225' to season."""
    if gid.startswith("00222"):
        return "2022-23"
    if gid.startswith("00223"):
        return "2023-24"
    if gid.startswith("00224"):
        return "2024-25"
    if gid.startswith("00225"):
        return "2025-26"
    return "unknown"


def walk_forward_per_target(df: pd.DataFrame, feat_cols: List[str],
                            old_ensembles: Dict[str, list],
                            old_feats: List[str]) -> Dict[str, dict]:
    """4 expanding folds, season-boundary splits.

    Fold 1: train 2022-23           val 2023-24
    Fold 2: train 2022-23..2023-24  val 2024-25
    Fold 3: train 2022-23..2024-25  val 2025-26 (first half)
    Fold 4: train + first half 2526 val 2025-26 (second half)
    """
    df = df.copy()
    df["season"] = df["game_id"].apply(_season_for_row)
    seasons_order = ["2022-23", "2023-24", "2024-25", "2025-26"]
    s2526 = df[df["season"] == "2025-26"].sort_values("game_date").reset_index(drop=True)
    if len(s2526) >= 2:
        mid = len(s2526) // 2
        first_half_ids  = set(s2526.iloc[:mid]["game_id"])
        second_half_ids = set(s2526.iloc[mid:]["game_id"])
    else:
        first_half_ids, second_half_ids = set(), set()

    # Apples-to-apples WF — the OLD ensemble was trained on 2022-23..(most of)2024-25,
    # so evaluating it on those seasons is leakage. We only score OLD on folds where
    # its training cutoff is strictly before the validation set.  The current OLD
    # manifest reports n_games=2836; the freshly merged corpus is len(df)=~2865
    # → OLD was trained on everything EXCEPT the 29 played 2025-26 games. We
    # therefore only score OLD on folds 3 and 4 (the 2025-26 splits).  Folds 1
    # and 2 are NEW-only sanity folds that confirm the new training pipeline
    # converges on its own data.
    folds = []
    folds.append({
        "name":       "F1_train22_val23",
        "train_mask": df["season"].isin(["2022-23"]),
        "val_mask":   df["season"] == "2023-24",
        "score_old":  False,  # OLD saw 2023-24 in training
    })
    folds.append({
        "name":       "F2_train22-23_val24",
        "train_mask": df["season"].isin(["2022-23", "2023-24"]),
        "val_mask":   df["season"] == "2024-25",
        "score_old":  False,  # OLD saw 2024-25 in training
    })
    folds.append({
        "name":       "F3_train22-24_val2526H1",
        "train_mask": df["season"].isin(["2022-23", "2023-24", "2024-25"]),
        "val_mask":   df["game_id"].isin(first_half_ids),
        "score_old":  True,
    })
    folds.append({
        "name":       "F4_train22-25_val2526H2",
        "train_mask": (df["season"].isin(["2022-23", "2023-24", "2024-25"])
                       | df["game_id"].isin(first_half_ids)),
        "val_mask":   df["game_id"].isin(second_half_ids),
        "score_old":  True,
    })

    per_target: Dict[str, dict] = {tgt: {"folds": [], "mae_old": [], "mae_new": [],
                                          "n_train": [], "n_val": []}
                                    for tgt in TARGETS}

    for fold_idx, fold in enumerate(folds, 1):
        train_df = df[fold["train_mask"]].copy()
        val_df   = df[fold["val_mask"]].copy()
        n_train, n_val = len(train_df), len(val_df)
        print(f"[WF fold {fold_idx} {fold['name']}] n_train={n_train} n_val={n_val}", flush=True)
        if n_train < 100 or n_val < 10:
            for tgt in TARGETS:
                per_target[tgt]["folds"].append(fold["name"])
                per_target[tgt]["mae_old"].append(None)
                per_target[tgt]["mae_new"].append(None)
                per_target[tgt]["n_train"].append(n_train)
                per_target[tgt]["n_val"].append(n_val)
            continue

        X_train = train_df[feat_cols].values
        X_val   = val_df[feat_cols].values

        # Old (deployed) ensemble — feature order may differ. Only score on folds
        # the OLD model didn't see in training (fold["score_old"]).
        X_val_old_order = None
        if fold.get("score_old", False) and old_ensembles and old_feats:
            X_val_old_order = val_df[[c for c in old_feats if c in val_df.columns]].copy()
            for c in old_feats:
                if c not in X_val_old_order.columns:
                    X_val_old_order[c] = 0.0
            X_val_old_order = X_val_old_order[old_feats].values

        for tgt, ycol in TARGETS.items():
            y_train = train_df[ycol].astype(float).values
            y_val   = val_df[ycol].astype(float).values
            models_new = train_ensemble(X_train, y_train)
            pred_new   = predict_ensemble(models_new, X_val)
            mae_new    = float(np.mean(np.abs(pred_new - y_val)))
            if X_val_old_order is not None and old_ensembles.get(tgt):
                pred_old = predict_ensemble(old_ensembles[tgt], X_val_old_order)
                mae_old  = float(np.mean(np.abs(pred_old - y_val)))
            else:
                mae_old = None

            per_target[tgt]["folds"].append(fold["name"])
            per_target[tgt]["mae_old"].append(mae_old)
            per_target[tgt]["mae_new"].append(mae_new)
            per_target[tgt]["n_train"].append(n_train)
            per_target[tgt]["n_val"].append(n_val)
            old_str = f"{mae_old:.4f}" if mae_old is not None else "skipped (leak)"
            print(f"  {tgt:9s}: mae_old={old_str}  mae_new={mae_new:.4f}", flush=True)

    return per_target


def holdout_2025_26_eval(df: pd.DataFrame, feat_cols: List[str],
                          old_ensembles: Dict[str, list],
                          old_feats: List[str]) -> Dict[str, dict]:
    """Single train/test: train on 2022..2024-25, eval on full 2025-26 played."""
    df = df.copy()
    df["season"] = df["game_id"].apply(_season_for_row)
    train_df = df[df["season"].isin(["2022-23", "2023-24", "2024-25"])]
    val_df   = df[df["season"] == "2025-26"]
    n_train, n_val = len(train_df), len(val_df)
    print(f"[holdout 2025-26] n_train={n_train} n_val={n_val}", flush=True)
    X_train = train_df[feat_cols].values
    X_val_new = val_df[feat_cols].values

    # Old order
    X_val_old = None
    if old_ensembles and old_feats:
        X_val_old = val_df[[c for c in old_feats if c in val_df.columns]].copy()
        for c in old_feats:
            if c not in X_val_old.columns:
                X_val_old[c] = 0.0
        X_val_old = X_val_old[old_feats].values

    out: Dict[str, dict] = {}
    for tgt, ycol in TARGETS.items():
        y_train = train_df[ycol].astype(float).values
        y_val   = val_df[ycol].astype(float).values
        models_new = train_ensemble(X_train, y_train)
        pred_new   = predict_ensemble(models_new, X_val_new)
        mae_new    = float(np.mean(np.abs(pred_new - y_val)))
        if X_val_old is not None and old_ensembles.get(tgt):
            pred_old = predict_ensemble(old_ensembles[tgt], X_val_old)
            mae_old  = float(np.mean(np.abs(pred_old - y_val)))
        else:
            mae_old = None
        delta_pct = ((mae_new - mae_old) / mae_old * 100.0) if mae_old else None
        out[tgt] = {
            "mae_old":   mae_old,
            "mae_new":   mae_new,
            "delta_pct": delta_pct,
            "n_train":   int(n_train),
            "n_val":     int(n_val),
        }
        old_str = f"{mae_old:.4f}" if mae_old is not None else "n/a "
        dpct = f"{delta_pct:+.2f}%" if delta_pct is not None else "n/a"
        print(f"  {tgt:9s}: old={old_str}  new={mae_new:.4f}  delta={dpct}", flush=True)
    return out


# ---------------------------------------------------------------------------
# Ship gate + artifact persistence
# ---------------------------------------------------------------------------
def evaluate_ship_gate(holdout: Dict[str, dict],
                        per_target_wf: Dict[str, dict]) -> Dict:
    """SHIP gate (strict):
        - new wins on >=3/4 targets by >= -2% MAE on 2025-26 holdout
        - no target regresses by more than +1%
        - WF 4/4 folds positive across at least 2 targets
    """
    targets_improving = 0
    worst_regress_pct = 0.0
    wf_folds_passing  = 0
    wf_full_pass_targets = 0
    n_targets_with_old = 0
    for tgt, h in holdout.items():
        if h.get("mae_old") is None:
            continue
        n_targets_with_old += 1
        dp = h["delta_pct"]
        if dp is not None and dp <= -2.0:
            targets_improving += 1
        if dp is not None and dp > worst_regress_pct:
            worst_regress_pct = dp
        wf = per_target_wf[tgt]
        full_pass = True
        per_fold_pass = 0
        for mo, mn in zip(wf["mae_old"], wf["mae_new"]):
            if mo is None or mn is None:
                full_pass = False
                continue
            if mn <= mo:
                per_fold_pass += 1
            else:
                full_pass = False
        wf_folds_passing += per_fold_pass
        if full_pass and len([m for m in wf["mae_old"] if m is not None]) >= 1:
            wf_full_pass_targets += 1

    cond_3_of_4 = targets_improving >= 3
    cond_no_regress = worst_regress_pct <= 1.0
    cond_wf_2tgt = wf_full_pass_targets >= 2

    decision = "SHIP" if (cond_3_of_4 and cond_no_regress and cond_wf_2tgt) else "REJECT"
    reasons = []
    if not cond_3_of_4:
        reasons.append(f"only {targets_improving}/4 targets improve by >=2% on 2025-26 holdout")
    if not cond_no_regress:
        reasons.append(f"worst regression {worst_regress_pct:+.2f}% exceeds +1% cap")
    if not cond_wf_2tgt:
        reasons.append(f"only {wf_full_pass_targets} targets pass all 4 WF folds (need >=2)")
    return {
        "decision":              decision,
        "n_targets_improving":   targets_improving,
        "worst_regress_pct":     worst_regress_pct,
        "wf_folds_passing":      wf_folds_passing,
        "wf_full_pass_targets":  wf_full_pass_targets,
        "n_targets_with_old":    n_targets_with_old,
        "reasons":               reasons,
    }


def backup_old_artifacts() -> bool:
    if not os.path.isdir(ROOT_MODELS_DIR):
        return False
    if os.path.exists(ROOT_BACKUP_DIR):
        # Already backed up — leave as is (don't overwrite a prior session's backup)
        return True
    try:
        shutil.copytree(ROOT_MODELS_DIR, ROOT_BACKUP_DIR)
        return True
    except Exception as exc:
        print(f"[R27_T1] backup failed: {exc}", flush=True)
        return False


def persist_new_artifacts(df: pd.DataFrame, feat_cols: List[str]) -> Dict[str, list]:
    """Re-train on the FULL 4-season corpus and write to ROOT_MODELS_DIR."""
    import joblib
    os.makedirs(ROOT_MODELS_DIR, exist_ok=True)
    X = df[feat_cols].values
    new_manifest = {
        "version":           "M2_family_v2_R27_T1",
        "trained_at":        time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_games":           int(len(df)),
        "n_features":        int(len(feat_cols)),
        "lgb_seeds":         LGB_SEEDS,
        "xgb_seeds":         XGB_SEEDS,
        "ensemble_weights":  "equal (1/5 per model)",
        "targets":           {},
        "probe_ancestry":    {
            "round": "R27_T1",
            "predecessor": "R20_M7 (M2_family_v1, n_games=2836, no 2025-26 backfill)",
            "trigger": "R25_R1 + R26_S2 backfills added 1225 + 600 new rows of 2025-26 data",
        },
        "usage": "Load each model via joblib.load, predict, average predictions equally.",
    }
    saved_map: Dict[str, list] = {}
    for tgt, ycol in TARGETS.items():
        print(f"[persist] training {tgt} ({ycol}) on n={len(df)}", flush=True)
        y = df[ycol].astype(float).values
        models = train_ensemble(X, y)
        labels = []
        for kind, seed, m in models:
            lab = f"{kind}_s{seed}"
            p = os.path.join(ROOT_MODELS_DIR, f"{tgt}_{lab}.joblib")
            joblib.dump(m, p)
            labels.append(lab)
        new_manifest["targets"][tgt] = {"label": ycol, "models": labels}
        saved_map[tgt] = labels

    with open(os.path.join(ROOT_MODELS_DIR, "feature_cols.json"), "w") as f:
        json.dump(feat_cols, f, indent=2)
    with open(os.path.join(ROOT_MODELS_DIR, "manifest.json"), "w") as f:
        json.dump(new_manifest, f, indent=2)
    return saved_map


def clear_r21_cache() -> bool:
    if os.path.exists(ROOT_PRED_CACHE):
        try:
            os.remove(ROOT_PRED_CACHE)
            return True
        except OSError:
            return False
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Skip writing artifacts on SHIP — just print decision.")
    args = ap.parse_args()

    t0 = time.time()
    print(f"[R27_T1] root={ROOT_DIR}", flush=True)
    print(f"[R27_T1] models_dir={ROOT_MODELS_DIR}", flush=True)

    print("[1] loading dataset ...", flush=True)
    df, feat_cols = load_dataset()
    print(f"  merged: n={len(df)}  n_features={len(feat_cols)}", flush=True)
    seasons_count = df["game_id"].apply(_season_for_row).value_counts().to_dict()
    print(f"  by season: {seasons_count}", flush=True)

    print("[2] loading OLD m2_family artifacts ...", flush=True)
    old_ensembles = load_old_ensembles_from_disk()
    old_feats = load_old_feature_cols()
    if not old_ensembles:
        print("  [warn] OLD m2_family artifacts missing — first deploy, no head-to-head", flush=True)
    else:
        print(f"  OLD loaded: {len(old_ensembles)} targets, {len(old_feats)} feature cols", flush=True)

    print("\n[3] HOLDOUT 2025-26 evaluation ...", flush=True)
    holdout = holdout_2025_26_eval(df, feat_cols, old_ensembles, old_feats)

    print("\n[4] WALK-FORWARD 4 folds ...", flush=True)
    wf = walk_forward_per_target(df, feat_cols, old_ensembles, old_feats)

    print("\n[5] evaluating SHIP gate ...", flush=True)
    gate = evaluate_ship_gate(holdout, wf)
    print(f"  decision: {gate['decision']}", flush=True)
    print(f"  targets_improving:  {gate['n_targets_improving']}/4", flush=True)
    print(f"  worst_regress_pct:  {gate['worst_regress_pct']:+.2f}%", flush=True)
    print(f"  wf_folds_passing:   {gate['wf_folds_passing']}/16", flush=True)
    print(f"  wf_full_pass_tgts:  {gate['wf_full_pass_targets']}/4", flush=True)
    if gate["reasons"]:
        for r in gate["reasons"]:
            print(f"  reason: {r}", flush=True)

    backup_ok = False
    if gate["decision"] == "SHIP" and not args.dry_run:
        print("\n[6] backing up + persisting new artifacts ...", flush=True)
        backup_ok = backup_old_artifacts()
        print(f"  backup_ok: {backup_ok}", flush=True)
        persist_new_artifacts(df, feat_cols)
        cleared = clear_r21_cache()
        print(f"  cleared_r21_cache: {cleared}", flush=True)

    runtime_min = (time.time() - t0) / 60.0
    n_train_rows = int(holdout[next(iter(TARGETS))]["n_train"])
    n_val_rows   = int(holdout[next(iter(TARGETS))]["n_val"])
    data_warnings: List[str] = []
    if n_val_rows < 50:
        data_warnings.append(
            f"2025-26 holdout has only {n_val_rows} playable games (linescores "
            f"with non-zero q1-q4) — R26_S2 wrote ~600 BoxScoreSummary stubs "
            f"with all-zero quarters for unfinished games; only the "
            f"PBP-sourced + completed-game BoxScoreSummary rows merge. Need a "
            f"real R28_X probe to backfill quarter-by-quarter from a played-"
            f"games endpoint."
        )
    payload = {
        "probe":                 "R27_T1_m2_family_retrain",
        "computed_at":           time.strftime("%Y-%m-%dT%H:%M:%S"),
        "decision":              gate["decision"],
        "runtime_min":           round(runtime_min, 2),
        "n_train_rows":          n_train_rows,
        "n_val_rows":            n_val_rows,
        "data_warnings":         data_warnings,
        "per_target_mae_old":    {t: holdout[t]["mae_old"] for t in TARGETS},
        "per_target_mae_new":    {t: holdout[t]["mae_new"] for t in TARGETS},
        "per_target_delta_pct":  {t: holdout[t]["delta_pct"] for t in TARGETS},
        "per_target_wf_folds":   {t: wf[t]["folds"] for t in TARGETS},
        "per_target_wf_mae_old": {t: wf[t]["mae_old"] for t in TARGETS},
        "per_target_wf_mae_new": {t: wf[t]["mae_new"] for t in TARGETS},
        "per_target_wf_folds_positive": {
            t: sum(
                1 for mo, mn in zip(wf[t]["mae_old"], wf[t]["mae_new"])
                if mo is not None and mn is not None and mn <= mo
            )
            for t in TARGETS
        },
        "n_targets_improving":   gate["n_targets_improving"],
        "worst_regress_pct":     gate["worst_regress_pct"],
        "wf_folds_passing":      gate["wf_folds_passing"],
        "wf_full_pass_targets":  gate["wf_full_pass_targets"],
        "reasons":               gate["reasons"],
        "backup_dir_created":    bool(backup_ok),
        "seasons_count":         seasons_count,
        "feat_cols_count":       len(feat_cols),
    }
    os.makedirs(os.path.dirname(ROOT_CACHE_PATH), exist_ok=True)
    with open(ROOT_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\n[R27_T1] wrote -> {ROOT_CACHE_PATH}", flush=True)
    print(f"[R27_T1] runtime: {runtime_min:.2f} min", flush=True)
    return 0 if gate["decision"] in ("SHIP", "REJECT") else 1


if __name__ == "__main__":
    sys.exit(main())
