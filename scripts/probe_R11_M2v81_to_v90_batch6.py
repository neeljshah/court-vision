"""probe_R11_M2v81_to_v90_batch6.py — stacked ensemble + HP sweeps.

Tests whether STACKING (LGB + XGB base learners → meta LGB) extracts more
signal than single-architecture models. Also runs HP sweep on canonical
M2v8 total to find optimal config.

Variants:
  M2v81 stack_total_lgb_xgb           (meta: [lgb_pred, xgb_pred, base])
  M2v82 stack_spread_lgb_xgb          (meta on spread)
  M2v83 stack_home_pts                (meta on home_pts)
  M2v84 stack_away_pts                (meta on away_pts)
  M2v85 stack_5way                    (lgb_total + xgb_total + lgb_spread + lgb_home + lgb_away → total)
  M2v86 hp_n800                       (LGB with 800 estimators, deeper)
  M2v87 hp_lr01                       (LGB with lr=0.01, 1500 estimators)
  M2v88 hp_leaves63                   (LGB with 63 leaves, more capacity)
  M2v89 ensemble_avg                  (simple average of LGB + XGB)
  M2v90 quantile_q50                  (LGB with q50 objective for total)
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

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


def load_season_games():
    rows = []
    for fname in ["season_games_2022-23.json", "season_games_2023-24.json",
                  "season_games_2024-25.json", "season_games_2025-26.json"]:
        p = os.path.join(DATA_NBA, fname)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        rows.extend(d.get("rows", d) if isinstance(d, dict) else d)
    return pd.DataFrame(rows)


def load_linescores():
    p = os.path.join(DATA_NBA, "linescores_all.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    rows = []
    for gid, ls in d.items():
        try:
            hq = [float(ls.get(f"home_q{i}", 0) or 0) for i in range(1, 5)]
            aq = [float(ls.get(f"away_q{i}", 0) or 0) for i in range(1, 5)]
        except (TypeError, ValueError):
            continue
        h, a = sum(hq), sum(aq)
        if h <= 0 or a <= 0:
            continue
        rows.append({
            "game_id": gid, "home_score": h, "away_score": a,
            "score_diff": h - a, "total_pts_box": h + a,
        })
    return pd.DataFrame(rows)


def _fit_lgb(X_tr, y_tr, params=None):
    import lightgbm as lgb
    p = dict(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
    if params: p.update(params)
    m = lgb.LGBMRegressor(**p)
    m.fit(X_tr, y_tr)
    return m


def _fit_xgb(X_tr, y_tr):
    import xgboost as xgb
    m = xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, n_jobs=2, verbosity=0)
    m.fit(X_tr, y_tr)
    return m


def wf_single(merged, label_col, naive_pred, feat_cols, probe_name, model_fn, model_label):
    y = merged[label_col].astype(float).values
    n = len(merged); fold_size = n // 4
    folds, aa, al, an = [], [], [], []
    for fi in range(4):
        ts = fi * fold_size
        te = (fi + 1) * fold_size if fi < 3 else n
        tr = list(range(0, ts)); ti = list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20:
            continue
        X_tr = merged[feat_cols].iloc[tr].values
        X_te = merged[feat_cols].iloc[ti].values
        m = model_fn(X_tr, y[tr])
        pred = m.predict(X_te)
        lgb_mae = float(np.mean(np.abs(pred - y[ti])))
        nv = naive_pred[ti]
        nmae = float(np.mean(np.abs(nv - y[ti])))
        d = lgb_mae - nmae; dp = d / nmae * 100
        folds.append({"fold": fi, "naive_mae": round(nmae,4), "lgb_mae": round(lgb_mae,4),
                      "delta": round(d,4), "delta_pct": round(dp,2)})
        aa.extend(y[ti].tolist()); al.extend(pred.tolist()); an.extend(nv.tolist())
    p_n = float(np.mean(np.abs(np.array(an) - np.array(aa))))
    p_l = float(np.mean(np.abs(np.array(al) - np.array(aa))))
    dp = (p_l - p_n) / p_n * 100
    n_v = len(folds); n_p = sum(1 for f in folds if f["delta"] < 0)
    ship = (n_v >= 3) and (n_p == n_v) and (dp <= -5.0)
    return {"probe": probe_name, "kind": "regression", "model": model_label,
            "label": label_col,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {n_p}/{n_v}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(p_n,4), "pooled_lgb_mae": round(p_l,4),
            "pooled_delta_pct": round(dp,2),
            "n_folds_positive": n_p, "n_valid_folds": n_v, "fold_results": folds}


def wf_stacked(merged, target_col, naive_pred, feat_cols, probe_name, base_targets):
    """Stacked ensemble:
       For each fold, train base learners (lgb_target, xgb_target) on train,
       predict on test → get base predictions per row.
       Train meta-LGB on [base_preds + base_features] vs target_col.
       Compare meta to naive baseline.
       base_targets: list of (label_col, model_kind) for base learners.
    """
    y = merged[target_col].astype(float).values
    n = len(merged); fold_size = n // 4
    folds, aa, al, an = [], [], [], []
    for fi in range(4):
        ts = fi * fold_size
        te = (fi + 1) * fold_size if fi < 3 else n
        tr = list(range(0, ts)); ti = list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20:
            continue
        X_tr = merged[feat_cols].iloc[tr].values
        X_te = merged[feat_cols].iloc[ti].values

        # Train each base learner
        base_te_preds = []
        base_tr_preds = []
        for blab, bmodel in base_targets:
            yb = merged[blab].astype(float).values
            if bmodel == "xgb":
                m = _fit_xgb(X_tr, yb[tr])
            else:
                m = _fit_lgb(X_tr, yb[tr])
            base_te_preds.append(m.predict(X_te))
            # For train set, use OOF approximation via CV-3 split within train
            # Simplification: also use fit-predict on full train (slight leakage but
            # consistent across folds, acceptable for WF comparison)
            base_tr_preds.append(m.predict(X_tr))

        # Build meta features
        meta_X_tr = np.concatenate([X_tr] + [p.reshape(-1, 1) for p in base_tr_preds], axis=1)
        meta_X_te = np.concatenate([X_te] + [p.reshape(-1, 1) for p in base_te_preds], axis=1)

        meta = _fit_lgb(meta_X_tr, y[tr])
        pred = meta.predict(meta_X_te)
        lgb_mae = float(np.mean(np.abs(pred - y[ti])))
        nv = naive_pred[ti]
        nmae = float(np.mean(np.abs(nv - y[ti])))
        d = lgb_mae - nmae; dp = d / nmae * 100
        folds.append({"fold": fi, "naive_mae": round(nmae,4), "lgb_mae": round(lgb_mae,4),
                      "delta": round(d,4), "delta_pct": round(dp,2)})
        aa.extend(y[ti].tolist()); al.extend(pred.tolist()); an.extend(nv.tolist())
    p_n = float(np.mean(np.abs(np.array(an) - np.array(aa))))
    p_l = float(np.mean(np.abs(np.array(al) - np.array(aa))))
    dp = (p_l - p_n) / p_n * 100
    n_v = len(folds); n_p = sum(1 for f in folds if f["delta"] < 0)
    ship = (n_v >= 3) and (n_p == n_v) and (dp <= -5.0)
    return {"probe": probe_name, "kind": "regression", "model": "stack",
            "label": target_col, "base_targets": [b[0] for b in base_targets],
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {n_p}/{n_v}, delta {dp:+.2f}% (vs naive)",
            "pooled_naive_mae": round(p_n,4), "pooled_lgb_mae": round(p_l,4),
            "pooled_delta_pct": round(dp,2),
            "n_folds_positive": n_p, "n_valid_folds": n_v, "fold_results": folds}


def wf_ensemble_avg(merged, target_col, naive_pred, feat_cols, probe_name):
    """Simple average of LGB and XGB predictions, no meta-learner."""
    y = merged[target_col].astype(float).values
    n = len(merged); fold_size = n // 4
    folds, aa, al, an = [], [], [], []
    for fi in range(4):
        ts = fi * fold_size
        te = (fi + 1) * fold_size if fi < 3 else n
        tr = list(range(0, ts)); ti = list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20:
            continue
        X_tr = merged[feat_cols].iloc[tr].values
        X_te = merged[feat_cols].iloc[ti].values
        lgb_m = _fit_lgb(X_tr, y[tr])
        xgb_m = _fit_xgb(X_tr, y[tr])
        pred = 0.5 * lgb_m.predict(X_te) + 0.5 * xgb_m.predict(X_te)
        lgb_mae = float(np.mean(np.abs(pred - y[ti])))
        nv = naive_pred[ti]
        nmae = float(np.mean(np.abs(nv - y[ti])))
        d = lgb_mae - nmae; dp = d / nmae * 100
        folds.append({"fold": fi, "naive_mae": round(nmae,4), "lgb_mae": round(lgb_mae,4),
                      "delta": round(d,4), "delta_pct": round(dp,2)})
        aa.extend(y[ti].tolist()); al.extend(pred.tolist()); an.extend(nv.tolist())
    p_n = float(np.mean(np.abs(np.array(an) - np.array(aa))))
    p_l = float(np.mean(np.abs(np.array(al) - np.array(aa))))
    dp = (p_l - p_n) / p_n * 100
    n_v = len(folds); n_p = sum(1 for f in folds if f["delta"] < 0)
    ship = (n_v >= 3) and (n_p == n_v) and (dp <= -5.0)
    return {"probe": probe_name, "kind": "regression", "model": "ensemble_avg",
            "label": target_col,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {n_p}/{n_v}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(p_n,4), "pooled_lgb_mae": round(p_l,4),
            "pooled_delta_pct": round(dp,2),
            "n_folds_positive": n_p, "n_valid_folds": n_v, "fold_results": folds}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("BATCH-6 PROBE R11 M2v81-M2v90 — stacking + HP sweep", flush=True)
    print("=" * 70, flush=True)

    sg = load_season_games()
    ls = load_linescores()
    merged = sg.merge(ls, on="game_id", how="inner")
    for col in ["home_off_rtg", "away_off_rtg", "home_pace", "away_pace"]:
        merged = merged[merged[col] > 0]
    merged = merged.sort_values("game_date").reset_index(drop=True)
    avail = [c for c in FEAT_COLS if c in merged.columns]
    merged[avail] = merged[avail].fillna(0.0)
    print(f"  data: {len(merged)} games, {len(avail)} features", flush=True)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values

    variants = [
        ("R11_M2v81_stack_total_lgb_xgb", "stack", "total_pts_box",
         [("total_pts_box", "lgb"), ("total_pts_box", "xgb")]),
        ("R11_M2v82_stack_spread_lgb_xgb", "stack", "score_diff",
         [("score_diff", "lgb"), ("score_diff", "xgb")]),
        ("R11_M2v83_stack_home_pts", "stack", "home_score",
         [("home_score", "lgb"), ("home_score", "xgb")]),
        ("R11_M2v84_stack_away_pts", "stack", "away_score",
         [("away_score", "lgb"), ("away_score", "xgb")]),
        ("R11_M2v85_stack_5way_total", "stack", "total_pts_box",
         [("total_pts_box", "lgb"), ("total_pts_box", "xgb"),
          ("score_diff", "lgb"), ("home_score", "lgb"), ("away_score", "lgb")]),
        ("R11_M2v86_hp_n800", "single", "total_pts_box",
         lambda X,y: _fit_lgb(X, y, dict(n_estimators=800, num_leaves=31, learning_rate=0.05)), "lgb_n800"),
        ("R11_M2v87_hp_lr01", "single", "total_pts_box",
         lambda X,y: _fit_lgb(X, y, dict(n_estimators=1500, num_leaves=31, learning_rate=0.01)), "lgb_lr01"),
        ("R11_M2v88_hp_leaves63", "single", "total_pts_box",
         lambda X,y: _fit_lgb(X, y, dict(n_estimators=300, num_leaves=63, learning_rate=0.05)), "lgb_l63"),
        ("R11_M2v89_ensemble_avg", "avg", "total_pts_box", None),
        ("R11_M2v90_ensemble_avg_spread", "avg", "score_diff", None),
    ]

    results = {}
    for tup in variants:
        name, kind, label = tup[:3]
        t_v = time.time()
        if kind == "stack":
            out = wf_stacked(merged, label, naive_l5_mean(label), avail, name, tup[3])
        elif kind == "single":
            out = wf_single(merged, label, naive_l5_mean(label), avail, name, tup[3], tup[4])
        elif kind == "avg":
            out = wf_ensemble_avg(merged, label, naive_l5_mean(label), avail, name)
        else:
            continue
        out["elapsed_s"] = round(time.time() - t_v, 1)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        print(f"  {name} [{out.get('model','?')}]: {out['status']} delta {out['pooled_delta_pct']:+.2f}% "
              f"({out['n_folds_positive']}/{out['n_valid_folds']}) [{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
