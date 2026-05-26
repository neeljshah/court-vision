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
OUT_JSON = os.path.join(DATA_CACHE, "probe_R11_M2v7_score_diff_expanded_results.json")

# M2v7: EXPANDED pregame feature set — adds lineup, matchup, hustle, and
# additional L10 features from season_games_*.json that M2v2's 35-feature
# base did not include.
FEAT_COLS = [
    # Base 35 (M2v2)
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
    # M2v7 ADDITIONS — lineup quality, matchup, hustle, additional L10, travel
    "home_travel_miles", "away_travel_miles",
    "home_top_lineup_net_rtg", "away_top_lineup_net_rtg",
    "iso_matchup_edge",
    "home_pnr_ppp", "away_pnr_ppp",
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
            "home_score": h, "away_score": a,
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
    print("probe_R11_M2v2_score_diff - game-level score margin (spread bets)", flush=True)
    print("=" * 60, flush=True)

    print("\n[1] Loading season_games (pregame features) ...", flush=True)
    sg = load_season_games()

    print("\n[2] Loading score_diff from boxscore_<gid>.json ...", flush=True)
    diffs = load_score_diff_from_boxscores()

    print("\n[3] Joining season_games <-> boxscore on game_id ...", flush=True)
    merged = sg.merge(diffs, on="game_id", how="inner")
    print(f"  joined rows: {len(merged)} (of {len(sg)} pregame games)", flush=True)

    # Drop rows where features are all-zero (pre-season placeholder fills)
    for col in ["home_off_rtg", "away_off_rtg", "home_pace", "away_pace"]:
        merged = merged[merged[col] > 0]
    print(f"  after filter (rtg>0, pace>0): {len(merged)}", flush=True)

    # Sort by game_date for walk-forward
    merged = merged.sort_values("game_date").reset_index(drop=True)
    print(f"  game_date range: {merged['game_date'].min()} -> {merged['game_date'].max()}", flush=True)

    # Compute features and label
    avail_feats = [c for c in FEAT_COLS if c in merged.columns]
    print(f"  features available: {len(avail_feats)}/{len(FEAT_COLS)}", flush=True)
    merged[avail_feats] = merged[avail_feats].fillna(0.0)
    y = merged["score_diff"].astype(float).values

    # Naive baseline: rolling L5 mean of score_diff (strictly prior games)
    print("\n[4] Naive baseline: L5 rolling mean of score_diff ...", flush=True)
    naive_pred = merged["score_diff"].shift(1).rolling(5, min_periods=1).mean().fillna(
        merged["score_diff"].mean()
    ).values
    naive_mae = float(np.mean(np.abs(naive_pred - y)))
    print(f"  naive L5-mean baseline MAE: {naive_mae:.4f}", flush=True)

    # ── LGB walk-forward 4-fold ──
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

        model = lgb.LGBMRegressor(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, min_child_samples=20,
            random_state=42, n_jobs=2, verbose=-1,
        )
        model.fit(X_train, y_train)
        lgb_test = model.predict(X_test)

        lgb_mae = float(np.mean(np.abs(lgb_test - y_test)))
        naive_mae_fold = float(np.mean(np.abs(naive_test - y_test)))
        delta = lgb_mae - naive_mae_fold
        delta_pct = delta / naive_mae_fold * 100

        fold_results.append({
            "fold": fi,
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "naive_mae": round(naive_mae_fold, 4),
            "lgb_mae": round(lgb_mae, 4),
            "delta": round(delta, 4),
            "delta_pct": round(delta_pct, 2),
        })
        all_actuals.extend(y_test.tolist())
        all_lgb_preds.extend(lgb_test.tolist())
        all_naive_preds.extend(naive_test.tolist())
        print(f"  fold {fi}: train={len(train_idx)} test={len(test_idx)} "
              f"naive={naive_mae_fold:.3f} lgb={lgb_mae:.3f} delta={delta:+.3f} ({delta_pct:+.1f}%)",
              flush=True)

    pooled_naive = float(np.mean(np.abs(np.array(all_naive_preds) - np.array(all_actuals))))
    pooled_lgb = float(np.mean(np.abs(np.array(all_lgb_preds) - np.array(all_actuals))))
    pooled_delta = pooled_lgb - pooled_naive
    pooled_delta_pct = pooled_delta / pooled_naive * 100

    # Ship gate -- M2 family: use ALL VALID folds (fold 0 routinely skipped)
    print("\n[6] Ship gate ...", flush=True)
    n_valid_folds = len(fold_results)
    n_folds_pos = sum(1 for f in fold_results if f["delta"] < 0)
    wf_all_valid_pos = (n_valid_folds >= 3) and (n_folds_pos == n_valid_folds)
    gate_5pct = pooled_delta_pct <= -5.0
    ship = wf_all_valid_pos and gate_5pct

    print(f"  WF folds positive: {n_folds_pos}/{n_valid_folds} valid -- "
          f"{'PASS' if wf_all_valid_pos else 'FAIL'}", flush=True)
    print(f"  pooled delta_pct: {pooled_delta_pct:+.2f}% (gate -5%) -- "
          f"{'PASS' if gate_5pct else 'FAIL'}", flush=True)
    print(f"\n  VERDICT: {'SHIP' if ship else 'REJECT'}", flush=True)

    out = {
        "probe": "R11_M2v7_score_diff_expanded",
        "status": "SHIP" if ship else "REJECT",
        "ship_reason": (
            f"WF {n_folds_pos}/{n_valid_folds} valid folds positive "
            f"{'pass' if wf_all_valid_pos else 'fail'}, "
            f"delta {pooled_delta_pct:+.2f}% vs -5% gate "
            f"{'pass' if gate_5pct else 'fail'}"
        ),
        "n_games": len(merged),
        "n_features": len(avail_feats),
        "features": avail_feats,
        "naive_baseline_mae": round(naive_mae, 4),
        "pooled_naive_mae": round(pooled_naive, 4),
        "pooled_lgb_mae": round(pooled_lgb, 4),
        "pooled_delta": round(pooled_delta, 4),
        "pooled_delta_pct": round(pooled_delta_pct, 2),
        "n_folds_positive": n_folds_pos,
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
