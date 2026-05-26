"""probe_R11_M2v69_to_v80_batch5.py — 12-variant joint/parlay + architecture sweep.

NEW ANGLES:
  - Joint binaries (parlay-style markets that exist in NBA books)
  - XGBoost architecture comparison (was LGB)
  - Time-of-season features (week_of_season as proxy)
  - DK-format margin bins (P(margin 1-5), P(margin 6-10), P(margin 11-20), P(margin 20+))

Variants:
  M2v69 total_with_dow regression   (add weekday + month features)
  M2v70 joint_over230_home_covers3  (joint binary)
  M2v71 joint_over240_home_wins     (joint)
  M2v72 joint_over220_close         (joint)
  M2v73 xgb_total regression        (XGB instead of LGB)
  M2v74 xgb_spread regression       (XGB spread)
  M2v75 margin_bin_close (1-5)      (binary)
  M2v76 margin_bin_mid (6-10)       (binary)
  M2v77 margin_bin_high (11-20)     (binary)
  M2v78 margin_bin_blowout (20+)    (binary)
  M2v79 home_pts_O108               (binary)
  M2v80 away_pts_O115               (binary, mirror v63)
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


def _train_predict(model_kind, X_tr, y_tr, X_te, is_classifier):
    if model_kind == "xgb":
        import xgboost as xgb
        if is_classifier:
            m = xgb.XGBClassifier(n_estimators=300, learning_rate=0.05, max_depth=6,
                subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
                random_state=42, n_jobs=2, verbosity=0,
                use_label_encoder=False, eval_metric="logloss")
        else:
            m = xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
                subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
                random_state=42, n_jobs=2, verbosity=0)
    else:
        import lightgbm as lgb
        if is_classifier:
            m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
                min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
        else:
            m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
                subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
                min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
    m.fit(X_tr, y_tr)
    if is_classifier:
        return m.predict_proba(X_te)[:, 1]
    return m.predict(X_te)


def wf_regression(merged, label_col, naive_pred, feat_cols, probe_name, model_kind="lgb"):
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
        pred = _train_predict(model_kind, X_tr, y[tr], X_te, is_classifier=False)
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
    return {"probe": probe_name, "kind": "regression", "model": model_kind,
            "label": label_col,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {n_p}/{n_v}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(p_n,4), "pooled_lgb_mae": round(p_l,4),
            "pooled_delta_pct": round(dp,2),
            "n_folds_positive": n_p, "n_valid_folds": n_v, "fold_results": folds}


def wf_binary(merged, label_col, naive_pred, feat_cols, probe_name, desc, model_kind="lgb"):
    from sklearn.metrics import brier_score_loss, accuracy_score, roc_auc_score
    y = merged[label_col].astype(int).values
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
        pred = _train_predict(model_kind, X_tr, y[tr], X_te, is_classifier=True)
        nv = naive_pred[ti]
        folds.append({"fold": fi,
                      "naive_brier": round(brier_score_loss(y[ti], nv), 5),
                      "lgb_brier": round(brier_score_loss(y[ti], pred), 5)})
        aa.extend(y[ti].tolist()); al.extend(pred.tolist()); an.extend(nv.tolist())
    p_nb = float(brier_score_loss(aa, an))
    p_lb = float(brier_score_loss(aa, al))
    try: p_lu = float(roc_auc_score(aa, al))
    except: p_lu = float("nan")
    bdp = (p_lb - p_nb) / p_nb * 100
    n_v = len(folds)
    ship = ((p_lb <= p_nb * 0.95) or (p_lu >= 0.60)) and n_v >= 3
    return {"probe": probe_name, "kind": "binary", "model": model_kind,
            "label": label_col, "label_desc": desc,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {p_lb:.4f} ({bdp:+.2f}%); AUC {p_lu:.4f}",
            "n_games": int(len(merged)), "pos_rate": float(np.mean(y)),
            "pooled_lgb_brier": round(p_lb,5), "pooled_naive_brier": round(p_nb,5),
            "pooled_lgb_auc": round(p_lu,5), "brier_delta_pct": round(bdp,3),
            "n_valid_folds": n_v, "fold_results": folds}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("BATCH-5 PROBE R11 M2v69-M2v80 — joint + xgb + dow", flush=True)
    print("=" * 70, flush=True)

    sg = load_season_games()
    ls = load_linescores()
    merged = sg.merge(ls, on="game_id", how="inner")
    for col in ["home_off_rtg", "away_off_rtg", "home_pace", "away_pace"]:
        merged = merged[merged[col] > 0]
    merged = merged.sort_values("game_date").reset_index(drop=True)

    # Time-of-season features
    merged["game_date_dt"] = pd.to_datetime(merged["game_date"])
    merged["day_of_year"] = merged["game_date_dt"].dt.dayofyear
    merged["month"] = merged["game_date_dt"].dt.month
    merged["weekday"] = merged["game_date_dt"].dt.weekday

    avail = [c for c in FEAT_COLS if c in merged.columns]
    merged[avail] = merged[avail].fillna(0.0)
    dow_cols = ["day_of_year", "month", "weekday"]
    feat_dow = avail + dow_cols

    # Labels
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_covers3"] = (merged["score_diff"] > 3).astype(int)
    merged["over_240"] = (merged["total_pts_box"] > 240).astype(int)
    merged["home_wins"] = (merged["score_diff"] > 0).astype(int)
    merged["over_220"] = (merged["total_pts_box"] > 220).astype(int)
    merged["close_game5"] = (np.abs(merged["score_diff"]) <= 5).astype(int)

    merged["joint_O230_H3"] = (merged["over_230"] & merged["home_covers3"]).astype(int)
    merged["joint_O240_HW"] = (merged["over_240"] & merged["home_wins"]).astype(int)
    merged["joint_O220_close5"] = (merged["over_220"] & merged["close_game5"]).astype(int)
    merged["margin_1_5"] = ((np.abs(merged["score_diff"]) >= 1) & (np.abs(merged["score_diff"]) <= 5)).astype(int)
    merged["margin_6_10"] = ((np.abs(merged["score_diff"]) >= 6) & (np.abs(merged["score_diff"]) <= 10)).astype(int)
    merged["margin_11_20"] = ((np.abs(merged["score_diff"]) >= 11) & (np.abs(merged["score_diff"]) <= 20)).astype(int)
    merged["margin_20p"] = (np.abs(merged["score_diff"]) > 20).astype(int)
    merged["home_pts_O108"] = (merged["home_score"] > 108).astype(int)
    merged["away_pts_O115"] = (merged["away_score"] > 115).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values
    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    variants = [
        ("R11_M2v69_total_with_dow", "reg", "total_pts_box", feat_dow, "lgb", None),
        ("R11_M2v70_joint_O230_H3", "bin", "joint_O230_H3", avail, "lgb", "P(O230 AND home covers -3)"),
        ("R11_M2v71_joint_O240_HW", "bin", "joint_O240_HW", avail, "lgb", "P(O240 AND home wins)"),
        ("R11_M2v72_joint_O220_close5", "bin", "joint_O220_close5", avail, "lgb", "P(O220 AND close <=5)"),
        ("R11_M2v73_xgb_total", "reg", "total_pts_box", avail, "xgb", None),
        ("R11_M2v74_xgb_spread", "reg", "score_diff", avail, "xgb", None),
        ("R11_M2v75_margin_1_5", "bin", "margin_1_5", avail, "lgb", "P(margin 1-5)"),
        ("R11_M2v76_margin_6_10", "bin", "margin_6_10", avail, "lgb", "P(margin 6-10)"),
        ("R11_M2v77_margin_11_20", "bin", "margin_11_20", avail, "lgb", "P(margin 11-20)"),
        ("R11_M2v78_margin_20p", "bin", "margin_20p", avail, "lgb", "P(margin > 20)"),
        ("R11_M2v79_home_pts_O108", "bin", "home_pts_O108", avail, "lgb", "P(home > 108)"),
        ("R11_M2v80_away_pts_O115", "bin", "away_pts_O115", avail, "lgb", "P(away > 115)"),
    ]

    results = {}
    for name, kind, label, fc, model_kind, desc in variants:
        t_v = time.time()
        if kind == "reg":
            out = wf_regression(merged, label, naive_l5_mean(label), fc, name, model_kind)
        else:
            out = wf_binary(merged, label, naive_l5_prop(label), fc, name, desc, model_kind)
        out["elapsed_s"] = round(time.time() - t_v, 1)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        if out["kind"] == "regression":
            print(f"  {name} [{out['model']}]: {out['status']} delta {out['pooled_delta_pct']:+.2f}% "
                  f"({out['n_folds_positive']}/{out['n_valid_folds']}) [{out['elapsed_s']}s]", flush=True)
        else:
            print(f"  {name} [{out['model']}]: {out['status']} Brier {out['pooled_lgb_brier']:.4f} "
                  f"AUC {out['pooled_lgb_auc']:.4f} ({out['brier_delta_pct']:+.2f}%) "
                  f"[{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
