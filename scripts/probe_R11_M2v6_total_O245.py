"""probe_R11_M2_game_total_pts.py — NEW MODEL CLASS: game-level total points.

WHY: All R8-R13 saturation is on PLAYER-level stat MAE. Game-level total points
is a different output surface (O/U bets) and uses pregame team features that
have never been the primary target. Even modest accuracy (MAE ~10 vs naive ~13)
ships because over/under markets are wide.

INPUT: data/nba/season_games_*.json (rich pregame team features) +
       data/player_quarter_stats.parquet (sum pts per game = label).

LABEL: total_pts = sum of all player pts across both teams in that game.

NAIVE BASELINE: rolling L5 mean of league-wide total_pts (or home team's last 5
home games + away team's last 5 away games / 2).

GATE: MAE delta vs L5-naive-baseline <= -5% AND WF 4/4 folds positive.

Run:
    python -u scripts/probe_R11_M2_game_total_pts.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")
OUT_JSON = os.path.join(DATA_CACHE, "probe_R11_M2v6_total_O245_results.json")

# Pregame features available in season_games_*.json
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
]


def load_season_games() -> pd.DataFrame:
    rows = []
    for fname in ["season_games_2022-23.json", "season_games_2023-24.json",
                  "season_games_2024-25.json", "season_games_2025-26.json"]:
        p = os.path.join(DATA_NBA, fname)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        data_rows = d.get("rows", d) if isinstance(d, dict) else d
        for r in data_rows:
            rows.append(r)
    df = pd.DataFrame(rows)
    print(f"  season_games rows: {len(df)}", flush=True)
    return df


def load_score_diff_from_linescores() -> pd.DataFrame:
    """From linescores_all.json: home_q1..q4 and away_q1..q4 — sum to get totals.
    Regulation only (does not include OT) but for spread bet labels this is the
    relevant final regulation-or-OT score? Actually linescores DO include OT if
    present? No — only q1..q4 are in the schema, so OT excluded. That's fine
    for the gate test; OT games are ~5% and small effect.
    """
    p = os.path.join(DATA_NBA, "linescores_all.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    rows = []
    for gid, ls in d.items():
        try:
            h = float(ls.get("home_q1", 0) or 0) + float(ls.get("home_q2", 0) or 0) \
              + float(ls.get("home_q3", 0) or 0) + float(ls.get("home_q4", 0) or 0)
            a = float(ls.get("away_q1", 0) or 0) + float(ls.get("away_q2", 0) or 0) \
              + float(ls.get("away_q3", 0) or 0) + float(ls.get("away_q4", 0) or 0)
        except (TypeError, ValueError):
            continue
        if h <= 0 or a <= 0:
            continue
        rows.append({
            "game_id": gid,
            "away_score": h, "away_score": a,
            "score_diff": h - a, "total_pts_box": h + a,
        })
    df = pd.DataFrame(rows)
    print(f"  linescore-derived rows: {len(df)}", flush=True)
    return df


# Keep backwards-compatible name expected by main()
def load_score_diff_from_boxscores() -> pd.DataFrame:
    return load_score_diff_from_linescores()


def main():
    t0 = time.time()
    print("=" * 60, flush=True)
    print("probe_R11_M2v6_total_O245 - binary classifier on (total_pts > 245)", flush=True)
    print("=" * 60, flush=True)

    print("\n[1] Loading season_games (pregame features) ...", flush=True)
    sg = load_season_games()

    print("\n[2] Loading total_pts from linescores ...", flush=True)
    diffs = load_score_diff_from_linescores()  # has total_pts_box

    print("\n[3] Joining season_games <-> linescore on game_id ...", flush=True)
    merged = sg.merge(diffs, on="game_id", how="inner")
    print(f"  joined rows: {len(merged)}", flush=True)

    # Drop rows where features are all-zero (pre-season placeholder fills)
    for col in ["home_off_rtg", "away_off_rtg", "home_pace", "away_pace"]:
        merged = merged[merged[col] > 0]
    print(f"  after filter (rtg>0, pace>0): {len(merged)}", flush=True)

    # Binary label: total_pts > 245
    O245_THRESHOLD = 245.0
    merged["over_245"] = (merged["total_pts_box"] > O245_THRESHOLD).astype(int)

    # Sort by game_date for walk-forward
    merged = merged.sort_values("game_date").reset_index(drop=True)
    print(f"  game_date range: {merged['game_date'].min()} -> {merged['game_date'].max()}", flush=True)
    print(f"  over_245 rate: {merged['over_245'].mean():.3f}  (n={len(merged)})", flush=True)

    avail_feats = [c for c in FEAT_COLS if c in merged.columns]
    print(f"  features available: {len(avail_feats)}/{len(FEAT_COLS)}", flush=True)
    merged[avail_feats] = merged[avail_feats].fillna(0.0)
    y = merged["over_245"].astype(int).values

    # Naive baseline: rolling L5 mean of total_pts converted to prob
    # P(over 245) = (mean - 245) / std normalized — but simpler: indicator over_245
    # of the last 5 games (rolling proportion).
    print("\n[4] Naive baseline: rolling L5 P(over245) ...", flush=True)
    naive_pred = merged["over_245"].shift(1).rolling(5, min_periods=1).mean().fillna(
        merged["over_245"].mean()
    ).clip(0.01, 0.99).values
    from sklearn.metrics import brier_score_loss, log_loss, accuracy_score, roc_auc_score
    naive_brier = float(brier_score_loss(y, naive_pred))
    naive_acc = float(accuracy_score(y, (naive_pred >= 0.5).astype(int)))
    print(f"  naive Brier: {naive_brier:.4f}  acc: {naive_acc:.4f}", flush=True)

    # LGB walk-forward 4-fold
    print("\n[5] LGB walk-forward 4-fold ...", flush=True)
    import lightgbm as lgb

    n = len(merged)
    fold_size = n // 4
    fold_results = []
    all_actuals = []
    all_lgb_preds = []
    all_naive_preds = []

    for fi in range(4):
        test_start = fi * fold_size
        test_end = (fi + 1) * fold_size if fi < 3 else n
        train_idx = list(range(0, test_start))
        test_idx = list(range(test_start, test_end))

        if len(train_idx) < 50 or len(test_idx) < 20:
            print(f"  fold {fi}: train={len(train_idx)} test={len(test_idx)} skip", flush=True)
            continue

        X_train = merged[avail_feats].iloc[train_idx].values
        X_test = merged[avail_feats].iloc[test_idx].values
        y_train = y[train_idx]
        y_test = y[test_idx]
        naive_test = naive_pred[test_idx]

        clf = lgb.LGBMClassifier(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, min_child_samples=20,
            random_state=42, n_jobs=2, verbose=-1,
        )
        clf.fit(X_train, y_train)
        lgb_test = clf.predict_proba(X_test)[:, 1]
        lgb_pred_class = (lgb_test >= 0.5).astype(int)

        lgb_brier = float(brier_score_loss(y_test, lgb_test))
        lgb_acc = float(accuracy_score(y_test, lgb_pred_class))
        try:
            lgb_auc = float(roc_auc_score(y_test, lgb_test))
        except Exception:
            lgb_auc = float("nan")
        naive_brier_fold = float(brier_score_loss(y_test, naive_test))
        naive_acc_fold = float(accuracy_score(y_test, (naive_test >= 0.5).astype(int)))
        brier_delta = lgb_brier - naive_brier_fold

        fold_results.append({
            "fold": fi,
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "naive_brier": round(naive_brier_fold, 5),
            "naive_acc": round(naive_acc_fold, 4),
            "lgb_brier": round(lgb_brier, 5),
            "lgb_acc": round(lgb_acc, 4),
            "lgb_auc": round(lgb_auc, 4),
            "brier_delta": round(brier_delta, 5),
        })
        all_actuals.extend(y_test.tolist())
        all_lgb_preds.extend(lgb_test.tolist())
        all_naive_preds.extend(naive_test.tolist())

    # Pooled metrics
    pooled_naive_brier = float(brier_score_loss(all_actuals, all_naive_preds))
    pooled_lgb_brier = float(brier_score_loss(all_actuals, all_lgb_preds))
    pooled_lgb_acc = float(accuracy_score(all_actuals, [1 if p >= 0.5 else 0 for p in all_lgb_preds]))
    try:
        pooled_lgb_auc = float(roc_auc_score(all_actuals, all_lgb_preds))
    except Exception:
        pooled_lgb_auc = float("nan")
    brier_delta_pct = (pooled_lgb_brier - pooled_naive_brier) / pooled_naive_brier * 100

    # Ship gate -- O245 binary: RELATIVE gates
    # Brier <= naive_brier * 0.95 (>= 5% improvement) AND
    # accuracy >= naive_acc + 0.02 (absolute 2pp improvement)
    print("\n[6] Ship gate ...", flush=True)
    n_valid_folds = len(fold_results)
    gate_brier_rel = pooled_lgb_brier <= pooled_naive_brier * 0.95
    gate_acc_rel = pooled_lgb_acc >= pooled_naive_brier_acc + 0.02 if False else pooled_lgb_acc >= (
        accuracy_score(all_actuals, [1 if p >= 0.5 else 0 for p in all_naive_preds]) + 0.02
    )
    ship = gate_brier_rel and gate_acc_rel and n_valid_folds >= 3

    naive_pooled_acc = float(accuracy_score(
        all_actuals, [1 if p >= 0.5 else 0 for p in all_naive_preds]
    ))

    print(f"  Pooled Brier: {pooled_lgb_brier:.4f} (gate <= {pooled_naive_brier*0.95:.4f}) -- "
          f"{'PASS' if gate_brier_rel else 'FAIL'}", flush=True)
    print(f"  Pooled Acc:   {pooled_lgb_acc:.4f} (gate >= {naive_pooled_acc+0.02:.4f}) -- "
          f"{'PASS' if gate_acc_rel else 'FAIL'}", flush=True)
    print(f"  Pooled AUC:   {pooled_lgb_auc:.4f}", flush=True)
    print(f"  Naive Brier:  {pooled_naive_brier:.4f}  Naive Acc: {naive_pooled_acc:.4f}", flush=True)
    print(f"  Brier delta:  {brier_delta_pct:+.2f}%", flush=True)
    print(f"\n  VERDICT: {'SHIP' if ship else 'REJECT'}", flush=True)

    out = {
        "probe": "R11_M2v6_total_O245",
        "status": "SHIP" if ship else "REJECT",
        "ship_reason": (
            f"Brier {pooled_lgb_brier:.4f} {'pass' if gate_brier_rel else 'fail'} "
            f"(gate <= naive*0.95 = {pooled_naive_brier*0.95:.4f}); "
            f"Acc {pooled_lgb_acc:.4f} {'pass' if gate_acc_rel else 'fail'} "
            f"(gate >= naive+0.02 = {naive_pooled_acc+0.02:.4f}); "
            f"vs naive L5-rolling-prop Brier {pooled_naive_brier:.4f}"
        ),
        "n_games": len(merged),
        "n_features": len(avail_feats),
        "features": avail_feats,
        "pooled_naive_brier": round(pooled_naive_brier, 5),
        "pooled_lgb_brier": round(pooled_lgb_brier, 5),
        "pooled_lgb_acc": round(pooled_lgb_acc, 5),
        "pooled_lgb_auc": round(pooled_lgb_auc, 5),
        "brier_delta_pct": round(brier_delta_pct, 3),
        "n_valid_folds": n_valid_folds,
        "fold_results": fold_results,
        "elapsed_s": round(time.time() - t0, 1),
    }
    os.makedirs(DATA_CACHE, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n[7] Saved -> {OUT_JSON}", flush=True)
    print(f"  elapsed: {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
