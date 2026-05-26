"""probe_R12_batch3_cross_stat.py — R12 batch 3: cross-stat & normalized features.

Tests on top of the 86-feature R12_B2 base:
  (A) Cross-stat ratios: home_off / away_def, away_off / home_def
  (B) Pace-adjusted scoring: ortg * pace / 100 (implied possessions × eff)
  (C) Z-score normalization (per-season standardization of net_rtg)
  (D) Trap-game indicators: home_fav AND b2b AND coming-off-win
  (E) Combined cross-stat + pace-adj
"""
from __future__ import annotations
import json, os, time
from collections import defaultdict
from datetime import datetime
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

FEAT_COLS_BASE = [
    "home_off_rtg","home_def_rtg","home_net_rtg","home_pace","home_efg_pct",
    "home_ts_pct","home_tov_pct","home_rest_days","home_back_to_back",
    "home_last5_wins","home_season_win_pct","away_off_rtg","away_def_rtg",
    "away_net_rtg","away_pace","away_efg_pct","away_ts_pct","away_tov_pct",
    "away_rest_days","away_back_to_back","away_last5_wins","away_season_win_pct",
    "net_rtg_diff","pace_diff","home_advantage","home_off_rtg_L10",
    "home_def_rtg_L10","home_net_rtg_L10","away_off_rtg_L10","away_def_rtg_L10",
    "away_net_rtg_L10","home_efg_L10","away_efg_L10","home_pace_variance",
    "away_pace_variance","home_travel_miles","away_travel_miles",
    "home_top_lineup_net_rtg","away_top_lineup_net_rtg","iso_matchup_edge",
    "home_pnr_ppp","away_pnr_ppp","home_hustle_deflections_pg",
    "away_hustle_deflections_pg","home_stars_available","away_stars_available",
    "home_bench_net_rtg","away_bench_net_rtg","home_tov_pct_L10",
    "away_tov_pct_L10","home_oreb_pct_L10","away_oreb_pct_L10",
    "home_ft_rate_L10","away_ft_rate_L10","home_off_rtg_home_L10",
    "away_off_rtg_away_L10","home_off_rtg_vs_top_def","away_off_rtg_vs_top_def",
    "home_srs","away_srs","home_elo","away_elo","elo_differential",
    "home_def_rtg_trend","away_def_rtg_trend","b2b_diff","elo_pace_interaction",
    "ref_avg_fouls","ref_home_win_pct","ref_fta_tendency",
    "sim_win_prob","sim_score_diff_mean","sim_pace_adj",
]


def load_data():
    rows = []
    for f in ["season_games_2022-23.json","season_games_2023-24.json",
              "season_games_2024-25.json","season_games_2025-26.json"]:
        p = os.path.join(DATA_NBA, f)
        if not os.path.exists(p): continue
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        rows.extend(d.get("rows", d) if isinstance(d, dict) else d)
    sg = pd.DataFrame(rows)
    with open(os.path.join(DATA_NBA, "linescores_all.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    ls_rows = []
    for gid, ls in d.items():
        try:
            h = sum(float(ls.get(f"home_q{i}",0) or 0) for i in range(1,5))
            a = sum(float(ls.get(f"away_q{i}",0) or 0) for i in range(1,5))
        except: continue
        if h<=0 or a<=0: continue
        ls_rows.append({"game_id":gid,"home_score":h,"away_score":a,
                        "score_diff":h-a,"total_pts_box":h+a})
    ls = pd.DataFrame(ls_rows)
    m = sg.merge(ls, on="game_id", how="inner")
    for c in ["home_off_rtg","away_off_rtg","home_pace","away_pace"]:
        m = m[m[c] > 0]
    m = m.sort_values("game_date").reset_index(drop=True)
    return m


def add_cross_stat(merged: pd.DataFrame) -> pd.DataFrame:
    m = merged.copy()
    # Cross-stat ratios (clipped to avoid div by zero)
    away_def = m["away_def_rtg"].replace(0, np.nan).fillna(110.0)
    home_def = m["home_def_rtg"].replace(0, np.nan).fillna(110.0)
    m["home_off_to_away_def"] = m["home_off_rtg"] / away_def
    m["away_off_to_home_def"] = m["away_off_rtg"] / home_def
    m["off_def_ratio_diff"] = m["home_off_to_away_def"] - m["away_off_to_home_def"]
    # L10 versions
    away_def_l10 = m["away_def_rtg_L10"].replace(0, np.nan).fillna(110.0)
    home_def_l10 = m["home_def_rtg_L10"].replace(0, np.nan).fillna(110.0)
    m["home_off_L10_to_away_def_L10"] = m["home_off_rtg_L10"] / away_def_l10
    m["away_off_L10_to_home_def_L10"] = m["away_off_rtg_L10"] / home_def_l10
    return m


def add_pace_adjusted(merged: pd.DataFrame) -> pd.DataFrame:
    m = merged.copy()
    # Pace-adjusted scoring: implied possessions × efficiency
    m["home_pace_adj_score"] = m["home_off_rtg"] * m["home_pace"] / 100.0
    m["away_pace_adj_score"] = m["away_off_rtg"] * m["away_pace"] / 100.0
    m["pace_adj_total"] = m["home_pace_adj_score"] + m["away_pace_adj_score"]
    m["pace_adj_diff"] = m["home_pace_adj_score"] - m["away_pace_adj_score"]
    # L10 versions
    m["home_pace_adj_score_L10"] = m["home_off_rtg_L10"] * m["home_pace"] / 100.0
    m["away_pace_adj_score_L10"] = m["away_off_rtg_L10"] * m["away_pace"] / 100.0
    return m


def add_zscore_norm(merged: pd.DataFrame) -> pd.DataFrame:
    m = merged.copy()
    if "season" not in m.columns:
        m["season"] = m["game_date"].astype(str).str[:7]  # rough proxy
    # Z-score net_rtg per season
    for col in ["home_net_rtg", "away_net_rtg", "home_off_rtg", "away_off_rtg",
                "home_def_rtg", "away_def_rtg"]:
        if col in m.columns:
            grp = m.groupby("season")[col]
            mu = grp.transform("mean")
            sd = grp.transform("std").replace(0, np.nan).fillna(1.0)
            m[f"{col}_zsea"] = (m[col] - mu) / sd
    return m


def add_trap_game(merged: pd.DataFrame) -> pd.DataFrame:
    """Trap game: home favored (net_rtg_diff > 5), home on b2b, away coming off win.
    We use home_form_streak proxy if we had it; here we approximate with
    home_back_to_back + home_last5_wins/2.5 (above 50% wins = warm).
    """
    m = merged.copy()
    # Home strong, on b2b, recent form warm
    home_fav = (m["net_rtg_diff"] > 5).astype(int)
    home_b2b = m["home_back_to_back"].astype(int)
    home_warm = (m["home_last5_wins"] >= 3).astype(int)
    away_warm = (m["away_last5_wins"] >= 3).astype(int)
    m["trap_home_signals"] = home_fav * home_b2b
    m["trap_home_overconf"] = home_fav * home_warm
    m["trap_away_motivated"] = ((m["net_rtg_diff"] < -3) & (m["away_last5_wins"] >= 3)).astype(int)
    m["trap_combo"] = m["trap_home_signals"] + m["trap_home_overconf"] + m["trap_away_motivated"]
    return m


def _fit_ens_reg(X_tr, y_tr):
    import lightgbm as lgb, xgboost as xgb
    l = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
    x = xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, n_jobs=2, verbosity=0)
    l.fit(X_tr, y_tr); x.fit(X_tr, y_tr)
    return l, x


def _fit_ens_clf(X_tr, y_tr):
    import lightgbm as lgb, xgboost as xgb
    l = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
    x = xgb.XGBClassifier(n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, n_jobs=2, verbosity=0, eval_metric="logloss")
    l.fit(X_tr, y_tr); x.fit(X_tr, y_tr)
    return l, x


def wf_regression(merged, label_col, naive_pred, feat_cols, probe_name):
    y = merged[label_col].astype(float).values
    n = len(merged); fold_size = n // 4
    folds, aa, al, an = [], [], [], []
    for fi in range(4):
        ts = fi * fold_size
        te = (fi + 1) * fold_size if fi < 3 else n
        tr, ti = list(range(0, ts)), list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20: continue
        X_tr = merged[feat_cols].iloc[tr].values
        X_te = merged[feat_cols].iloc[ti].values
        l, x = _fit_ens_reg(X_tr, y[tr])
        pred = 0.5 * l.predict(X_te) + 0.5 * x.predict(X_te)
        nv = naive_pred[ti]
        lgb_mae = float(np.mean(np.abs(pred - y[ti])))
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
    return {"probe":probe_name,"kind":"regression","label":label_col,
            "n_features":len(feat_cols),
            "status":"SHIP" if ship else "REJECT",
            "ship_reason":f"WF {n_p}/{n_v}, delta {dp:+.2f}%",
            "pooled_naive_mae":round(p_n,4),"pooled_lgb_mae":round(p_l,4),
            "pooled_delta_pct":round(dp,2),
            "n_folds_positive":n_p,"n_valid_folds":n_v,"fold_results":folds}


def wf_binary(merged, label_col, naive_pred, feat_cols, probe_name, desc):
    from sklearn.metrics import brier_score_loss, accuracy_score, roc_auc_score
    y = merged[label_col].astype(int).values
    n = len(merged); fold_size = n // 4
    folds, aa, al, an = [], [], [], []
    for fi in range(4):
        ts = fi * fold_size
        te = (fi + 1) * fold_size if fi < 3 else n
        tr, ti = list(range(0, ts)), list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20: continue
        X_tr = merged[feat_cols].iloc[tr].values
        X_te = merged[feat_cols].iloc[ti].values
        l, x = _fit_ens_clf(X_tr, y[tr])
        pred = 0.5 * l.predict_proba(X_te)[:,1] + 0.5 * x.predict_proba(X_te)[:,1]
        nv = naive_pred[ti]
        folds.append({"fold": fi,
                      "naive_brier": round(brier_score_loss(y[ti], nv),5),
                      "lgb_brier": round(brier_score_loss(y[ti], pred),5)})
        aa.extend(y[ti].tolist()); al.extend(pred.tolist()); an.extend(nv.tolist())
    p_nb = float(brier_score_loss(aa, an))
    p_lb = float(brier_score_loss(aa, al))
    try: p_lu = float(roc_auc_score(aa, al))
    except: p_lu = float("nan")
    bdp = (p_lb - p_nb) / p_nb * 100
    n_v = len(folds)
    ship = ((p_lb <= p_nb*0.95) or (p_lu >= 0.60)) and n_v >= 3
    return {"probe":probe_name,"kind":"binary","label":label_col,"label_desc":desc,
            "n_features":len(feat_cols),
            "status":"SHIP" if ship else "REJECT",
            "ship_reason":f"Brier {p_lb:.4f} ({bdp:+.2f}%); AUC {p_lu:.4f}",
            "n_games":int(len(merged)),"pos_rate":float(np.mean(y)),
            "pooled_lgb_brier":round(p_lb,5),"pooled_naive_brier":round(p_nb,5),
            "pooled_lgb_auc":round(p_lu,5),"brier_delta_pct":round(bdp,3),
            "n_valid_folds":n_v,"fold_results":folds}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-3 — cross-stat, pace-adj, z-score, trap-game", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    merged = add_cross_stat(merged)
    merged = add_pace_adjusted(merged)
    merged = add_zscore_norm(merged)
    merged = add_trap_game(merged)
    print(f"[1] loaded {len(merged)} games + derived features", flush=True)

    avail_base = [c for c in FEAT_COLS_BASE if c in merged.columns]
    CROSS_COLS = ["home_off_to_away_def","away_off_to_home_def","off_def_ratio_diff",
                  "home_off_L10_to_away_def_L10","away_off_L10_to_home_def_L10"]
    PACE_COLS = ["home_pace_adj_score","away_pace_adj_score","pace_adj_total",
                 "pace_adj_diff","home_pace_adj_score_L10","away_pace_adj_score_L10"]
    Z_COLS = [c for c in merged.columns if c.endswith("_zsea")]
    TRAP_COLS = ["trap_home_signals","trap_home_overconf","trap_away_motivated","trap_combo"]

    avail_cross = avail_base + CROSS_COLS
    avail_pace = avail_base + PACE_COLS
    avail_z = avail_base + Z_COLS
    avail_trap = avail_base + TRAP_COLS
    avail_all = avail_base + CROSS_COLS + PACE_COLS + Z_COLS + TRAP_COLS

    for cols in [avail_base, avail_cross, avail_pace, avail_z, avail_trap, avail_all]:
        merged[cols] = merged[cols].fillna(0.0)

    print(f"  feat sets: base={len(avail_base)}, +cross={len(avail_cross)}, +pace={len(avail_pace)}, +z={len(avail_z)}, +trap={len(avail_trap)}, all={len(avail_all)}", flush=True)

    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values
    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    variants = [
        ("R12_B3_total_with_cross",  "reg", "total_pts_box", avail_cross, None),
        ("R12_B3_spread_with_cross", "reg", "score_diff",    avail_cross, None),
        ("R12_B3_total_with_pace",   "reg", "total_pts_box", avail_pace,  None),
        ("R12_B3_spread_with_pace",  "reg", "score_diff",    avail_pace,  None),
        ("R12_B3_total_with_z",      "reg", "total_pts_box", avail_z,     None),
        ("R12_B3_spread_with_z",     "reg", "score_diff",    avail_z,     None),
        ("R12_B3_total_with_trap",   "reg", "total_pts_box", avail_trap,  None),
        ("R12_B3_spread_with_trap",  "reg", "score_diff",    avail_trap,  None),
        ("R12_B3_total_with_all",    "reg", "total_pts_box", avail_all,   None),
        ("R12_B3_spread_with_all",   "reg", "score_diff",    avail_all,   None),
        ("R12_B3_O230_with_all",     "bin", "over_230",      avail_all,   "P(total > 230)"),
        ("R12_B3_AH3_with_all",      "bin", "home_cover_AH3",avail_all,   "P(home covers -3)"),
    ]

    results = {}
    for name, kind, label, fc, desc in variants:
        t_v = time.time()
        if kind == "reg":
            out = wf_regression(merged, label, naive_l5_mean(label), fc, name)
        else:
            out = wf_binary(merged, label, naive_l5_prop(label), fc, name, desc)
        out["elapsed_s"] = round(time.time() - t_v, 1)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        if out["kind"] == "regression":
            print(f"  {name}: {out['status']} feats={out['n_features']} delta {out['pooled_delta_pct']:+.2f}% "
                  f"({out['n_folds_positive']}/{out['n_valid_folds']}) [{out['elapsed_s']}s]", flush=True)
        else:
            print(f"  {name}: {out['status']} feats={out['n_features']} Brier {out['pooled_lgb_brier']:.4f} "
                  f"AUC {out['pooled_lgb_auc']:.4f} ({out['brier_delta_pct']:+.2f}%) "
                  f"[{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
