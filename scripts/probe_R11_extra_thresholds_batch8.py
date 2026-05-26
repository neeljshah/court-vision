"""probe_R11_extra_thresholds_batch8.py — fill remaining untested NBA bet lines.

Quick coverage sweep of unusual thresholds book offers (half-point hooks,
edge values). All use the canonical 70-feature pregame set + LGB+XGB
ensemble averaging.
"""
from __future__ import annotations
import json, os, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

FEAT_COLS = [
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
    "sim_win_prob","sim_score_diff_mean","sim_score_diff_std","sim_pace_adj",
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
    avail = [c for c in FEAT_COLS if c in m.columns]
    m[avail] = m[avail].fillna(0.0)
    return m, avail


def lgb_xgb_avg_predict(X_tr, y_tr, X_te, is_classifier):
    import lightgbm as lgb, xgboost as xgb
    if is_classifier:
        l = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
        x = xgb.XGBClassifier(n_estimators=300, learning_rate=0.05, max_depth=6,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            random_state=42, n_jobs=2, verbosity=0, eval_metric="logloss")
        l.fit(X_tr, y_tr); x.fit(X_tr, y_tr)
        return 0.5 * l.predict_proba(X_te)[:,1] + 0.5 * x.predict_proba(X_te)[:,1]
    else:
        l = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
        x = xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            random_state=42, n_jobs=2, verbosity=0)
        l.fit(X_tr, y_tr); x.fit(X_tr, y_tr)
        return 0.5 * l.predict(X_te) + 0.5 * x.predict(X_te)


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
        pred = lgb_xgb_avg_predict(X_tr, y[tr], X_te, True)
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
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {p_lb:.4f} ({bdp:+.2f}%); AUC {p_lu:.4f}",
            "n_games": int(len(merged)), "pos_rate": float(np.mean(y)),
            "pooled_lgb_brier": round(p_lb,5),
            "pooled_naive_brier": round(p_nb,5),
            "pooled_lgb_auc": round(p_lu,5),
            "brier_delta_pct": round(bdp,3),
            "n_valid_folds": n_v, "fold_results": folds}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("BATCH-8 EXTRA THRESHOLDS — half-point hooks + edges", flush=True)
    print("=" * 70, flush=True)
    merged, avail = load_data()
    print(f"  data: {len(merged)} games, {len(avail)} feats", flush=True)

    # Untested O/U thresholds (half-point hooks + edge values)
    for t in [216, 218, 222, 224, 226, 228, 234, 242, 246]:
        merged[f"over_{t}"] = (merged["total_pts_box"] > t).astype(int)
    # Untested ATS thresholds
    for s in [13, 14, 15, 16]:
        merged[f"home_cover_AH{s}"] = (merged["score_diff"] + s > 0).astype(int)

    def naive_p(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    variants = []
    for t in [216, 218, 222, 224, 226, 228, 234, 242, 246]:
        variants.append((f"R11_M2x_total_O{t}", f"over_{t}", f"P(total > {t})"))
    for s in [13, 14, 15, 16]:
        variants.append((f"R11_M2x_spread_AH{s}", f"home_cover_AH{s}", f"P(home covers -{s})"))

    results = {}
    for name, label, desc in variants:
        t_v = time.time()
        out = wf_binary(merged, label, naive_p(label), avail, name, desc)
        out["elapsed_s"] = round(time.time() - t_v, 1)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        print(f"  {name}: {out['status']} Brier {out['pooled_lgb_brier']:.4f} "
              f"AUC {out['pooled_lgb_auc']:.4f} ({out['brier_delta_pct']:+.2f}%) "
              f"[{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
