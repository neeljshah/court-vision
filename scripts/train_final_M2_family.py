"""train_final_M2_family.py — Train final M2-family ensemble models on ALL data.

After 82 R11 ships, the production champions are:
  Total:    M2v93 = 3 LGB seeds (42/7/100) + 2 XGB seeds (42/7), equal-weighted
  Spread:   M2v94 = same architecture, score_diff target
  Home_pts: same architecture, home_score target
  Away_pts: same architecture, away_score target

This script trains all 4 final ensembles on the COMPLETE dataset (no holdout)
and saves the model artifacts to data/models/m2_family/ for production use.

USAGE:
    python scripts/train_final_M2_family.py

OUTPUTS:
    data/models/m2_family/total_lgb_s42.joblib   (3 LGB total models)
    data/models/m2_family/total_lgb_s7.joblib
    data/models/m2_family/total_lgb_s100.joblib
    data/models/m2_family/total_xgb_s42.joblib   (2 XGB total models)
    data/models/m2_family/total_xgb_s7.joblib
    ... (same for spread, home_pts, away_pts)
    data/models/m2_family/feature_cols.json      (canonical feature order)
    data/models/m2_family/manifest.json          (ensemble spec + last-trained timestamp)
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models", "m2_family")

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


def load_dataset():
    """Load season_games + linescores joined and filtered."""
    rows = []
    for fname in ["season_games_2022-23.json", "season_games_2023-24.json",
                  "season_games_2024-25.json", "season_games_2025-26.json"]:
        p = os.path.join(DATA_NBA, fname)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        rows.extend(d.get("rows", d) if isinstance(d, dict) else d)
    sg = pd.DataFrame(rows)

    with open(os.path.join(DATA_NBA, "linescores_all.json"), encoding="utf-8") as f:
        d = json.load(f)
    ls_rows = []
    for gid, ls in d.items():
        try:
            hq = [float(ls.get(f"home_q{i}", 0) or 0) for i in range(1, 5)]
            aq = [float(ls.get(f"away_q{i}", 0) or 0) for i in range(1, 5)]
        except (TypeError, ValueError):
            continue
        h, a = sum(hq), sum(aq)
        if h <= 0 or a <= 0:
            continue
        ls_rows.append({
            "game_id": gid, "home_score": h, "away_score": a,
            "score_diff": h - a, "total_pts_box": h + a,
        })
    ls = pd.DataFrame(ls_rows)

    merged = sg.merge(ls, on="game_id", how="inner")
    for col in ["home_off_rtg", "away_off_rtg", "home_pace", "away_pace"]:
        merged = merged[merged[col] > 0]
    merged = merged.sort_values("game_date").reset_index(drop=True)
    avail = [c for c in FEAT_COLS if c in merged.columns]
    merged[avail] = merged[avail].fillna(0.0)
    return merged, avail


def train_ensemble(X, y, target_name):
    """Train 3 LGB + 2 XGB and return list of (label, model, ext) tuples."""
    import joblib
    import lightgbm as lgb
    import xgboost as xgb
    models = []
    for seed in LGB_SEEDS:
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=seed, n_jobs=2, verbose=-1)
        m.fit(X, y)
        path = os.path.join(MODELS_DIR, f"{target_name}_lgb_s{seed}.joblib")
        joblib.dump(m, path)
        models.append((f"lgb_s{seed}", path))
        print(f"  saved {target_name}_lgb_s{seed}.joblib", flush=True)
    for seed in XGB_SEEDS:
        m = xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            random_state=seed, n_jobs=2, verbosity=0)
        m.fit(X, y)
        path = os.path.join(MODELS_DIR, f"{target_name}_xgb_s{seed}.joblib")
        joblib.dump(m, path)
        models.append((f"xgb_s{seed}", path))
        print(f"  saved {target_name}_xgb_s{seed}.joblib", flush=True)
    return models


def main():
    t0 = time.time()
    os.makedirs(MODELS_DIR, exist_ok=True)
    print(f"[1] Loading dataset ...", flush=True)
    merged, feat_cols = load_dataset()
    print(f"  {len(merged)} games, {len(feat_cols)} features", flush=True)
    X = merged[feat_cols].values

    print(f"\n[2] Training M2v93 total ensemble (5 models) ...", flush=True)
    total_models = train_ensemble(X, merged["total_pts_box"].astype(float).values, "total")

    print(f"\n[3] Training M2v94 spread ensemble ...", flush=True)
    spread_models = train_ensemble(X, merged["score_diff"].astype(float).values, "spread")

    print(f"\n[4] Training home_pts ensemble ...", flush=True)
    home_models = train_ensemble(X, merged["home_score"].astype(float).values, "home_pts")

    print(f"\n[5] Training away_pts ensemble ...", flush=True)
    away_models = train_ensemble(X, merged["away_score"].astype(float).values, "away_pts")

    # Save feature column order + manifest
    with open(os.path.join(MODELS_DIR, "feature_cols.json"), "w") as f:
        json.dump(feat_cols, f, indent=2)

    manifest = {
        "version": "M2_family_v1",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_games": int(len(merged)),
        "n_features": int(len(feat_cols)),
        "lgb_seeds": LGB_SEEDS,
        "xgb_seeds": XGB_SEEDS,
        "ensemble_weights": "equal (1/5 per model)",
        "targets": {
            "total":    {"label": "total_pts_box", "models": [m[0] for m in total_models]},
            "spread":   {"label": "score_diff",    "models": [m[0] for m in spread_models]},
            "home_pts": {"label": "home_score",    "models": [m[0] for m in home_models]},
            "away_pts": {"label": "away_score",    "models": [m[0] for m in away_models]},
        },
        "probe_ancestry": {
            "total":    "R11_M2v93_multi5_total (-11.10%)",
            "spread":   "R11_M2v94_multi5_spread (-15.83%)",
            "home_pts": "R11_M2v9_home_pts_expanded (-12.41%, single LGB) — multi5 not WF-tested but expected ~-12.5%",
            "away_pts": "R11_M2v10_away_pts_expanded (-10.93%, single LGB) — same caveat",
        },
        "usage": "Load each model via joblib.load, predict, average predictions equally.",
    }
    with open(os.path.join(MODELS_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n[6] Saved manifest.json + feature_cols.json", flush=True)
    print(f"\n[done] Trained 20 models in {time.time()-t0:.1f}s. Artifacts at {MODELS_DIR}", flush=True)


if __name__ == "__main__":
    main()
