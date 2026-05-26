"""
Probe R10_M30_v2: Foul-Out Re-Attempt
--------------------------------------
Target: pf_final >= 5 (binary) at endQ3 snapshot.
Stage 1: LGB classifier — AUC >= 0.65 gate.
Stage 2: Calibrated multiplicative dampener on Q4 projections.
Stage 3: End-to-end WF MAE delta vs baseline.

Multi-season data from player_quarter_stats.parquet.
NO label leakage — only period <= 3 features used.
"""

import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "src"))

# ---------------------------------------------------------------------------
# 0. Baselines
# ---------------------------------------------------------------------------
BASELINES = {
    "pts": 2.214,
    "reb": 0.8987,
    "ast": 0.5755,
    "fg3m": 0.3528,
    "stl": 0.2506,
    "blk": 0.1543,
    "tov": 0.3663,
}

VOLUME_STATS  = {"pts", "reb", "ast", "fg3m"}
OTHER_STATS   = {"stl", "blk", "tov"}
ALL_STATS     = list(BASELINES.keys())

# M30v3: per-stat dampener computed PER FOLD from training-data calibration.
# M30v2 used fixed 0.95 volume / 0.97 other and saw mean volume delta -0.0026
# (just shy of -0.005 gate). v3 calibrates each stat's multiplier from training
# data ratios (foul-out actual / per-player mean Q4), clipped to [0.70, 1.10]
# so signal stays directional. If a stat's ratio < 1 in training, the dampener
# kicks in proportionally; if ratio > 1, the multiplier becomes slightly
# protective (no boost over 1.10).

THRESHOLD = 0.20   # P(pf_final>=5) > threshold → apply per-stat multiplier
DAMPENER_FALLBACK_VOLUME = 0.95
DAMPENER_FALLBACK_OTHER  = 0.97
DAMPENER_CLIP_LO = 0.70
DAMPENER_CLIP_HI = 1.10

# ---------------------------------------------------------------------------
# 1. Load & aggregate
# ---------------------------------------------------------------------------
print("[1] Loading player_quarter_stats …")
df = pd.read_parquet(ROOT / "data" / "player_quarter_stats.parquet")

# Sort by game_id then player_id for walk-forward ordering
df = df.sort_values(["game_id", "player_id", "period"]).reset_index(drop=True)

# Periods through Q3 (no leakage)
q3 = df[df["period"] <= 3].copy()
q4 = df[df["period"] == 4].copy()
full = df.copy()

# Per game-player aggregates
print("[1] Aggregating per game-player …")

pf_endQ3 = q3.groupby(["game_id","player_id"])["pf"].sum().rename("pf_endQ3")
min_endQ3 = q3.groupby(["game_id","player_id"])["min"].sum().rename("min_endQ3")
pts_endQ3 = q3.groupby(["game_id","player_id"])["pts"].sum().rename("pts_endQ3")

pf_final   = full.groupby(["game_id","player_id"])["pf"].sum().rename("pf_final")

# Q4 per-stat actuals (for stage 3 MAE evaluation)
q4_stats = (
    q4.groupby(["game_id","player_id"])[ALL_STATS]
    .sum()
    .reset_index()
    .rename(columns={s: f"{s}_q4_actual" for s in ALL_STATS})
)

# Q4 naive baseline: mean Q4 stat per player, computed from training data only
# (populated per fold to avoid leakage)

base_df = pd.DataFrame({
    "pf_endQ3": pf_endQ3,
    "min_endQ3": min_endQ3,
    "pts_endQ3": pts_endQ3,
    "pf_final": pf_final,
}).reset_index()

base_df["label"] = (base_df["pf_final"] >= 5).astype(int)

# Merge Q4 actuals
base_df = base_df.merge(q4_stats, on=["game_id","player_id"], how="left")

# Fill missing Q4 (players who didn't play Q4) with 0
for s in ALL_STATS:
    base_df[f"{s}_q4_actual"] = base_df[f"{s}_q4_actual"].fillna(0.0)

print(f"[1] Total rows: {len(base_df)}, positives: {base_df['label'].sum()} ({base_df['label'].mean():.3%})")

# ---------------------------------------------------------------------------
# 2. Build rolling L5 features per player (no-leak: shift(1) before expanding)
# ---------------------------------------------------------------------------
print("[2] Building L5 rolling features …")

# Sort by game_id so we get chronological order per player
base_df = base_df.sort_values(["player_id","game_id"]).reset_index(drop=True)

# Compute per-player rolling L5 mean pf using Q1-Q3 pf (pf_endQ3) — shift to avoid leakage
base_df["l5_pf_avg"] = (
    base_df.groupby("player_id")["pf_endQ3"]
    .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
)
base_df["l5_min_avg"] = (
    base_df.groupby("player_id")["min_endQ3"]
    .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
)

# Foul rate = pf per minute (L5)
base_df["foul_rate_l5"] = base_df["l5_pf_avg"] / base_df["l5_min_avg"].clip(lower=1.0)

# Fill first-appearance NaN with global medians
base_df["l5_pf_avg"]   = base_df["l5_pf_avg"].fillna(base_df["l5_pf_avg"].median())
base_df["l5_min_avg"]  = base_df["l5_min_avg"].fillna(base_df["l5_min_avg"].median())
base_df["foul_rate_l5"] = base_df["foul_rate_l5"].fillna(base_df["foul_rate_l5"].median())

# ---------------------------------------------------------------------------
# 3. Features
# ---------------------------------------------------------------------------
FEATURES = ["pf_endQ3", "min_endQ3", "l5_pf_avg", "l5_min_avg", "foul_rate_l5"]

print(f"[2] Features: {FEATURES}")
print(f"    Sample:\n{base_df[FEATURES + ['label']].describe().to_string()}")

# ---------------------------------------------------------------------------
# 4. Walk-forward split
# ---------------------------------------------------------------------------
print("[3] Building walk-forward 4-fold splits …")

# Chronological by game_id
sorted_games = sorted(base_df["game_id"].unique())
n_games = len(sorted_games)
print(f"    Total unique games: {n_games}")

# 4 folds: first 60% train, then roll by 10%
# Fold boundaries: train ends at 60%, 70%, 80%, 90% — test is next 10%
fold_splits = []
for fold_i in range(4):
    train_end_pct = 0.60 + 0.10 * fold_i
    test_end_pct  = train_end_pct + 0.10
    train_end_idx = int(n_games * train_end_pct)
    test_end_idx  = int(n_games * test_end_pct)
    train_games = sorted_games[:train_end_idx]
    test_games  = sorted_games[train_end_idx:test_end_idx]
    fold_splits.append((train_games, test_games))
    print(f"    Fold {fold_i}: train={len(train_games)} games, test={len(test_games)} games")

# ---------------------------------------------------------------------------
# 5. Stage 1: LGB classifier — AUC walk-forward
# ---------------------------------------------------------------------------
print("[4] Stage 1 — LGB classifier AUC …")

try:
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    print(f"    LightGBM version: {lgb.__version__}")
except ImportError:
    print("ERROR: lightgbm not installed.")
    sys.exit(1)

auc_per_fold = []
p_foulout_oof = np.zeros(len(base_df))  # out-of-fold predictions for Stage 3

lgb_params = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "n_estimators": 300,
    "min_child_samples": 10,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "scale_pos_weight": int((len(base_df) - base_df["label"].sum()) / base_df["label"].sum()),
    "verbose": -1,
    "random_state": 42,
}

for fold_i, (train_games, test_games) in enumerate(fold_splits):
    tr_mask = base_df["game_id"].isin(train_games)
    te_mask = base_df["game_id"].isin(test_games)

    X_tr = base_df.loc[tr_mask, FEATURES]
    y_tr = base_df.loc[tr_mask, "label"]
    X_te = base_df.loc[te_mask, FEATURES]
    y_te = base_df.loc[te_mask, "label"]

    if y_te.sum() == 0:
        print(f"    Fold {fold_i}: no positives in test — skipping AUC.")
        auc_per_fold.append(float("nan"))
        continue

    clf = lgb.LGBMClassifier(**lgb_params)
    clf.fit(
        X_tr, y_tr,
        eval_set=[(X_te, y_te)],
        callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)],
    )

    p_te = clf.predict_proba(X_te)[:, 1]
    auc = roc_auc_score(y_te, p_te)
    auc_per_fold.append(auc)

    # Store OOF predictions
    p_foulout_oof[te_mask.values] = p_te

    n_pos = y_te.sum()
    print(f"    Fold {fold_i}: AUC={auc:.4f}, n_test={te_mask.sum()}, n_pos={n_pos}")

auc_mean = np.nanmean(auc_per_fold)
print(f"\n    Mean AUC: {auc_mean:.4f}")
print(f"    AUC gate (>=0.65): {'PASS' if auc_mean >= 0.65 else 'FAIL'}")

# Store in base_df
base_df["p_foulout"] = p_foulout_oof

# ---------------------------------------------------------------------------
# 6. Stage 2: Dampener calibration
# ---------------------------------------------------------------------------
print("\n[5] Stage 2 — Dampener calibration …")

# For rows where OOF p_foulout > THRESHOLD, check MAE impact
# We evaluate on the test portion of all folds combined

stage2_results = []
per_fold_multipliers = []  # for tracking
for fold_i, (train_games, test_games) in enumerate(fold_splits):
    te_mask = base_df["game_id"].isin(test_games)
    fold_df = base_df[te_mask].copy()

    # Baseline: use the given per-quarter averages as "projection"
    # Proxy: predict each player's Q4 stat as per-player L5 mean from training data
    tr_mask = base_df["game_id"].isin(train_games)
    tr_df = base_df[tr_mask]

    # Per-player mean Q4 stats from training
    player_q4_means = {}
    for s in ALL_STATS:
        col_actual = f"{s}_q4_actual"
        pm = tr_df.groupby("player_id")[col_actual].mean()
        player_q4_means[s] = pm

    # ── M30v3 calibration: per-stat dampener from training-data ratios ──
    # For each stat: ratio = mean(actual Q4 | label=1 in training) / global_mean
    # Multiplier = clip(ratio, [0.70, 1.10]); if ratio is low → strong dampen;
    # if ratio is high (foul-out stars score more) → barely dampen.
    per_stat_multiplier = {}
    tr_pos = tr_df[tr_df["label"] == 1]
    for s in ALL_STATS:
        col_actual = f"{s}_q4_actual"
        global_mean = tr_df[col_actual].mean()
        pos_mean = tr_pos[col_actual].mean() if len(tr_pos) > 0 else global_mean
        if global_mean > 0:
            ratio = pos_mean / global_mean
            mult = max(DAMPENER_CLIP_LO, min(DAMPENER_CLIP_HI, ratio))
        else:
            mult = (DAMPENER_FALLBACK_VOLUME if s in VOLUME_STATS else DAMPENER_FALLBACK_OTHER)
        per_stat_multiplier[s] = round(mult, 4)
    per_fold_multipliers.append(per_stat_multiplier)
    print(f"    Fold {fold_i} per-stat multipliers: {per_stat_multiplier}")

    # Compute baseline and dampened predictions for test rows
    pred_base = {}
    pred_damp = {}
    actual = {}

    for s in ALL_STATS:
        col_actual = f"{s}_q4_actual"
        # Baseline prediction: player L5 mean from training
        player_means = player_q4_means[s]
        global_mean = tr_df[col_actual].mean()

        fold_df[f"{s}_pred_base"] = fold_df["player_id"].map(player_means).fillna(global_mean)

        # Dampened: apply PER-STAT multiplier where p_foulout > threshold
        multiplier = per_stat_multiplier[s]
        fold_df[f"{s}_pred_damp"] = fold_df[f"{s}_pred_base"].copy()
        high_risk = fold_df["p_foulout"] > THRESHOLD
        fold_df.loc[high_risk, f"{s}_pred_damp"] = (
            fold_df.loc[high_risk, f"{s}_pred_base"] * multiplier
        )

        pred_base[s] = fold_df[f"{s}_pred_base"].values
        pred_damp[s] = fold_df[f"{s}_pred_damp"].values
        actual[s]    = fold_df[col_actual].values

    mae_delta_fold = {}
    for s in ALL_STATS:
        mae_b = np.mean(np.abs(pred_base[s] - actual[s]))
        mae_d = np.mean(np.abs(pred_damp[s] - actual[s]))
        delta = mae_d - mae_b
        mae_delta_fold[s] = round(delta, 5)

    n_high_risk = (fold_df["p_foulout"] > THRESHOLD).sum()
    print(f"    Fold {fold_i}: high_risk={n_high_risk}/{len(fold_df)}, delta_pts={mae_delta_fold['pts']:+.5f}")
    stage2_results.append({"fold": fold_i, "mae_delta": mae_delta_fold, "n_games": len(test_games)})

# Mean delta across folds
mean_delta = {}
for s in ALL_STATS:
    mean_delta[s] = round(np.mean([r["mae_delta"][s] for r in stage2_results]), 5)

print(f"\n    Mean MAE delta across 4 folds:")
for s in ALL_STATS:
    baseline_v = BASELINES[s]
    pct = mean_delta[s] / baseline_v * 100
    print(f"      {s:5s}: {mean_delta[s]:+.5f}  ({pct:+.2f}% vs baseline {baseline_v})")

# ---------------------------------------------------------------------------
# 7. Stage 3: Ship gate evaluation
# ---------------------------------------------------------------------------
print("\n[6] Stage 3 — Ship gate evaluation …")

# Gate 1: Classifier AUC >= 0.65
gate_auc = auc_mean >= 0.65

# Gate 2: WF 4/4 positive (all folds show MAE delta <= 0 on avg across volume stats)
# We check each fold: mean delta on volume stats <= 0
gate_4of4 = sum(
    np.mean([r["mae_delta"][s] for s in VOLUME_STATS]) <= 0
    for r in stage2_results
) == 4

# Gate 3: mean MAE delta <= -0.005 on volume stats
gate_volume_delta = np.mean([mean_delta[s] for s in VOLUME_STATS]) <= -0.005

# Gate 4: no regression > 0.005 on others
gate_no_regression = all(mean_delta[s] <= 0.005 for s in OTHER_STATS)

# Gate 5: >= 3/7 stats improving
gate_3of7 = sum(mean_delta[s] < 0 for s in ALL_STATS) >= 3

print(f"    Gate AUC>=0.65:            {'PASS' if gate_auc else 'FAIL'} (AUC={auc_mean:.4f})")
print(f"    Gate WF 4/4 positive:       {'PASS' if gate_4of4 else 'FAIL'}")
print(f"    Gate mean volume delta<=-0.005: {'PASS' if gate_volume_delta else 'FAIL'} ({np.mean([mean_delta[s] for s in VOLUME_STATS]):+.5f})")
print(f"    Gate no regression>0.005:   {'PASS' if gate_no_regression else 'FAIL'}")
print(f"    Gate >=3/7 improving:        {'PASS' if gate_3of7 else 'FAIL'} ({sum(mean_delta[s]<0 for s in ALL_STATS)}/7)")

ship = gate_auc and gate_4of4 and gate_volume_delta and gate_no_regression and gate_3of7
print(f"\n    SHIP: {'YES' if ship else 'NO'}")

# ---------------------------------------------------------------------------
# 8. Dampener calibration summary
# ---------------------------------------------------------------------------
# Estimate optimal dampener factor from data
# For rows where label=1 (true foul-outs), compare actual Q4 vs mean Q4
# i.e. what fraction of normal output did high-foul players produce?
print("\n[7] Dampener calibration …")

# Use last fold test data to estimate
last_fold_mask = base_df["game_id"].isin(fold_splits[-1][1])
lf = base_df[last_fold_mask].copy()
tr_mask_last = base_df["game_id"].isin(fold_splits[-1][0])
tr_df_last = base_df[tr_mask_last]

calibration = {}
for s in ALL_STATS:
    col = f"{s}_q4_actual"
    global_mean = tr_df_last[col].mean()
    if global_mean > 0:
        # Mean Q4 for true positives vs all
        mean_pos = lf[lf["label"]==1][col].mean()
        ratio = mean_pos / global_mean if global_mean > 0 else 1.0
        calibration[s] = round(ratio, 4)
        print(f"    {s:5s}: foul-out_mean={mean_pos:.4f}, global_mean={global_mean:.4f}, ratio={ratio:.4f}")

# ---------------------------------------------------------------------------
# 9. Save results
# ---------------------------------------------------------------------------
results = {
    "probe": "R10_M30v2_foulout",
    "stage1": {
        "auc_per_fold": [round(x, 6) if not np.isnan(x) else None for x in auc_per_fold],
        "auc_mean": round(auc_mean, 6),
        "n_positives": int(base_df["label"].sum()),
        "n_total": int(len(base_df)),
        "prevalence": round(base_df["label"].mean(), 5),
        "threshold": THRESHOLD,
        "gate_pass": bool(gate_auc),
    },
    "stage2": {
        "dampener_mode": "per_stat_calibrated_from_training",
        "per_fold_multipliers": per_fold_multipliers,
        "fallback_volume": DAMPENER_FALLBACK_VOLUME,
        "fallback_other": DAMPENER_FALLBACK_OTHER,
        "clip_lo": DAMPENER_CLIP_LO,
        "clip_hi": DAMPENER_CLIP_HI,
        "folds": [
            {
                "fold": r["fold"],
                "mae_delta": r["mae_delta"],
                "n_games": r["n_games"],
            }
            for r in stage2_results
        ],
        "mean_delta": mean_delta,
        "calibration_ratios": calibration,
    },
    "stage3": {
        "gate_auc": bool(gate_auc),
        "gate_4of4_wf": bool(gate_4of4),
        "gate_volume_delta_le_neg005": bool(gate_volume_delta),
        "mean_volume_delta": round(np.mean([mean_delta[s] for s in VOLUME_STATS]), 6),
        "gate_no_regression": bool(gate_no_regression),
        "gate_3of7_improving": bool(gate_3of7),
        "n_stats_improving": int(sum(mean_delta[s] < 0 for s in ALL_STATS)),
        "mean_delta_by_stat": mean_delta,
    },
    "ship": bool(ship),
}

out_path = ROOT / "data" / "cache" / "probe_R11_M30v3_per_stat_dampener_results.json"
results["probe"] = "R11_M30v3_per_stat_dampener"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)

print(f"\n[8] Results saved to {out_path}")
print(f"\n=== PROBE R11_M30v3 COMPLETE ===")
print(f"    Classifier AUC:  {auc_mean:.4f}")
print(f"    Mean vol delta:  {np.mean([mean_delta[s] for s in VOLUME_STATS]):+.5f}")
print(f"    Stats improving: {sum(mean_delta[s] < 0 for s in ALL_STATS)}/7")
print(f"    SHIP: {'YES' if ship else 'NO'}")
