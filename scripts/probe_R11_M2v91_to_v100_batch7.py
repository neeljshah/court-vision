"""probe_R11_M2v91_to_v100_batch7.py — multi-seed ensembles + isotonic calibration.

Tests:
  - 3-seed LGB ensemble (seeds 42, 7, 100) — does seed diversity beat single seed?
  - 5-model ensemble (3 LGB seeds + XGB seed 42 + XGB seed 7) — bigger ensemble
  - Isotonic calibration on binary classifier (O230, spread_AH3, home_pts_O110)
  - Triple-weighted ensemble (LGB w=0.5, XGB w=0.5 vs other weights)

Variants:
  M2v91 lgb_3seed_total        regression (avg of 3 LGB seeds)
  M2v92 lgb_3seed_spread       regression
  M2v93 multi5_total           regression (3 LGB + 2 XGB)
  M2v94 multi5_spread          regression
  M2v95 calibrated_O230        binary with isotonic post-cal
  M2v96 calibrated_spread_AH3  binary with isotonic
  M2v97 calibrated_home_pts_O110 binary with isotonic
  M2v98 weighted_60_40_total   regression (LGB 0.6, XGB 0.4)
  M2v99 weighted_40_60_total   regression (LGB 0.4, XGB 0.6)
  M2v100 weighted_70_30_total  regression (LGB 0.7, XGB 0.3)
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


def _lgb_reg(X, y, seed=42):
    import lightgbm as lgb
    m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=seed, n_jobs=2, verbose=-1)
    m.fit(X, y); return m


def _xgb_reg(X, y, seed=42):
    import xgboost as xgb
    m = xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        random_state=seed, n_jobs=2, verbosity=0)
    m.fit(X, y); return m


def _lgb_clf(X, y, seed=42):
    import lightgbm as lgb
    m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=seed, n_jobs=2, verbose=-1)
    m.fit(X, y); return m


def wf_ensemble(merged, target_col, naive_pred, feat_cols, probe_name, model_fns, weights=None):
    """Generic walk-forward ensemble.
    model_fns: list of (fitter_fn(X,y), label_str). All regressors.
    weights: list of floats summing to 1. None = equal weights.
    """
    y = merged[target_col].astype(float).values
    n = len(merged); fold_size = n // 4
    folds, aa, al, an = [], [], [], []
    K = len(model_fns)
    if weights is None:
        weights = [1.0 / K] * K
    for fi in range(4):
        ts = fi * fold_size
        te = (fi + 1) * fold_size if fi < 3 else n
        tr = list(range(0, ts)); ti = list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20:
            continue
        X_tr = merged[feat_cols].iloc[tr].values
        X_te = merged[feat_cols].iloc[ti].values
        preds = np.zeros(len(ti))
        for (fn, _), w in zip(model_fns, weights):
            m = fn(X_tr, y[tr])
            preds += w * m.predict(X_te)
        lgb_mae = float(np.mean(np.abs(preds - y[ti])))
        nv = naive_pred[ti]
        nmae = float(np.mean(np.abs(nv - y[ti])))
        d = lgb_mae - nmae; dp = d / nmae * 100
        folds.append({"fold": fi, "naive_mae": round(nmae,4), "lgb_mae": round(lgb_mae,4),
                      "delta": round(d,4), "delta_pct": round(dp,2)})
        aa.extend(y[ti].tolist()); al.extend(preds.tolist()); an.extend(nv.tolist())
    p_n = float(np.mean(np.abs(np.array(an) - np.array(aa))))
    p_l = float(np.mean(np.abs(np.array(al) - np.array(aa))))
    dp = (p_l - p_n) / p_n * 100
    n_v = len(folds); n_p = sum(1 for f in folds if f["delta"] < 0)
    ship = (n_v >= 3) and (n_p == n_v) and (dp <= -5.0)
    return {"probe": probe_name, "kind": "regression",
            "ensemble": [lab for (_,lab) in model_fns], "weights": list(weights),
            "label": target_col,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {n_p}/{n_v}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(p_n,4), "pooled_lgb_mae": round(p_l,4),
            "pooled_delta_pct": round(dp,2),
            "n_folds_positive": n_p, "n_valid_folds": n_v, "fold_results": folds}


def wf_calibrated_binary(merged, label_col, naive_pred, feat_cols, probe_name, desc):
    """Train LGB classifier, then fit isotonic on each fold's OOF preds for calibration."""
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import brier_score_loss, accuracy_score, roc_auc_score
    y = merged[label_col].astype(int).values
    n = len(merged); fold_size = n // 4
    folds, aa, al, ac, an = [], [], [], [], []  # ac = calibrated preds
    for fi in range(4):
        ts = fi * fold_size
        te = (fi + 1) * fold_size if fi < 3 else n
        tr = list(range(0, ts)); ti = list(range(ts, te))
        if len(tr) < 100 or len(ti) < 20:
            continue
        X_tr = merged[feat_cols].iloc[tr].values
        X_te = merged[feat_cols].iloc[ti].values
        # Split train into inner-train (80%) and calibration set (20%)
        n_tr = len(tr)
        n_inner = int(n_tr * 0.8)
        inner_idx = tr[:n_inner]
        cal_idx = tr[n_inner:]
        X_inner = merged[feat_cols].iloc[inner_idx].values
        X_cal = merged[feat_cols].iloc[cal_idx].values
        y_inner = y[inner_idx]
        y_cal = y[cal_idx]
        # Train base LGB on inner
        m = _lgb_clf(X_inner, y_inner)
        # Calibration set predictions
        cal_preds = m.predict_proba(X_cal)[:, 1]
        # Fit isotonic on cal_preds → y_cal
        try:
            iso = IsotonicRegression(out_of_bounds='clip')
            iso.fit(cal_preds, y_cal)
        except Exception:
            iso = None
        # Predict on test set (uncalibrated + calibrated)
        raw_te = m.predict_proba(X_te)[:, 1]
        cal_te = iso.transform(raw_te) if iso is not None else raw_te
        nv = naive_pred[ti]
        folds.append({"fold": fi,
                      "naive_brier": round(brier_score_loss(y[ti], nv), 5),
                      "raw_brier": round(brier_score_loss(y[ti], raw_te), 5),
                      "cal_brier": round(brier_score_loss(y[ti], cal_te), 5)})
        aa.extend(y[ti].tolist()); al.extend(raw_te.tolist())
        ac.extend(cal_te.tolist()); an.extend(nv.tolist())
    p_nb = float(brier_score_loss(aa, an))
    p_rb = float(brier_score_loss(aa, al))
    p_cb = float(brier_score_loss(aa, ac))
    try:
        p_ra = float(roc_auc_score(aa, al))
        p_ca = float(roc_auc_score(aa, ac))
    except Exception:
        p_ra = p_ca = float("nan")
    cal_gain_pct = (p_cb - p_rb) / p_rb * 100  # negative = better
    bdp = (p_cb - p_nb) / p_nb * 100
    n_v = len(folds)
    ship = (p_cb <= p_nb * 0.95 or p_ca >= 0.60) and n_v >= 3
    return {"probe": probe_name, "kind": "binary_calibrated", "label": label_col, "label_desc": desc,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Cal Brier {p_cb:.4f} ({bdp:+.2f}% vs naive); raw->cal gain {cal_gain_pct:+.2f}%",
            "pooled_naive_brier": round(p_nb,5),
            "pooled_raw_brier": round(p_rb,5),
            "pooled_cal_brier": round(p_cb,5),
            "pooled_raw_auc": round(p_ra,5),
            "pooled_cal_auc": round(p_ca,5),
            "calibration_gain_pct": round(cal_gain_pct,3),
            "brier_delta_pct": round(bdp,3),
            "n_valid_folds": n_v, "fold_results": folds}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("BATCH-7 PROBE R11 M2v91-M2v100 — multi-seed + calibration", flush=True)
    print("=" * 70, flush=True)

    sg = load_season_games()
    ls = load_linescores()
    merged = sg.merge(ls, on="game_id", how="inner")
    for col in ["home_off_rtg", "away_off_rtg", "home_pace", "away_pace"]:
        merged = merged[merged[col] > 0]
    merged = merged.sort_values("game_date").reset_index(drop=True)
    avail = [c for c in FEAT_COLS if c in merged.columns]
    merged[avail] = merged[avail].fillna(0.0)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)
    merged["home_pts_O110"] = (merged["home_score"] > 110).astype(int)
    print(f"  data: {len(merged)} games", flush=True)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values

    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    # 3-seed LGB
    lgb_3seed = [
        (lambda X, y: _lgb_reg(X, y, 42), "lgb_s42"),
        (lambda X, y: _lgb_reg(X, y, 7),  "lgb_s7"),
        (lambda X, y: _lgb_reg(X, y, 100), "lgb_s100"),
    ]
    # 5-model multi
    multi5 = [
        (lambda X, y: _lgb_reg(X, y, 42), "lgb_s42"),
        (lambda X, y: _lgb_reg(X, y, 7),  "lgb_s7"),
        (lambda X, y: _lgb_reg(X, y, 100), "lgb_s100"),
        (lambda X, y: _xgb_reg(X, y, 42), "xgb_s42"),
        (lambda X, y: _xgb_reg(X, y, 7),  "xgb_s7"),
    ]
    # Weighted LGB+XGB
    lgb_xgb = [
        (lambda X, y: _lgb_reg(X, y, 42), "lgb"),
        (lambda X, y: _xgb_reg(X, y, 42), "xgb"),
    ]

    variants = [
        ("R11_M2v91_lgb_3seed_total", "ens", "total_pts_box", lgb_3seed, None),
        ("R11_M2v92_lgb_3seed_spread", "ens", "score_diff", lgb_3seed, None),
        ("R11_M2v93_multi5_total", "ens", "total_pts_box", multi5, None),
        ("R11_M2v94_multi5_spread", "ens", "score_diff", multi5, None),
        ("R11_M2v95_cal_O230", "cal_bin", "over_230", None, "P(O230) calibrated"),
        ("R11_M2v96_cal_spread_AH3", "cal_bin", "home_cover_AH3", None, "P(home covers -3) calibrated"),
        ("R11_M2v97_cal_home_pts_O110", "cal_bin", "home_pts_O110", None, "P(home > 110) calibrated"),
        ("R11_M2v98_weighted_60_40_total", "ens", "total_pts_box", lgb_xgb, [0.6, 0.4]),
        ("R11_M2v99_weighted_40_60_total", "ens", "total_pts_box", lgb_xgb, [0.4, 0.6]),
        ("R11_M2v100_weighted_70_30_total", "ens", "total_pts_box", lgb_xgb, [0.7, 0.3]),
    ]

    results = {}
    for name, kind, label, fns_or_none, extra in variants:
        t_v = time.time()
        if kind == "ens":
            out = wf_ensemble(merged, label, naive_l5_mean(label), avail, name, fns_or_none, extra)
        else:  # cal_bin
            out = wf_calibrated_binary(merged, label, naive_l5_prop(label), avail, name, extra)
        out["elapsed_s"] = round(time.time() - t_v, 1)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        if out["kind"] == "regression":
            print(f"  {name}: {out['status']} delta {out['pooled_delta_pct']:+.2f}% "
                  f"({out['n_folds_positive']}/{out['n_valid_folds']}) [{out['elapsed_s']}s]", flush=True)
        else:
            print(f"  {name}: {out['status']} cal_Brier {out['pooled_cal_brier']:.4f} "
                  f"raw->cal {out['calibration_gain_pct']:+.2f}% AUC {out['pooled_cal_auc']:.4f} "
                  f"[{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
