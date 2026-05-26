"""probe_R12_batch4_team_recency.py — per-team exp-weighted recency features.

Builds per-team chronological history and computes shift(1) (strictly prior)
features:
  exp_ortg_for_h4  — exp-weighted mean of team's scoring per game, halflife 4
  exp_drtg_for_h4  — exp-weighted mean of team's points-allowed
  L5_pts_for       — last-5-games mean points scored
  L5_pts_against   — last-5-games mean points allowed
  L3_vs_L20_pts_z  — z-score delta of last-3 vs last-20 mean (trend up/down)
  L3_vs_L20_def_z  — same for defense

Combined with R12 B3's 94-feature base.
"""
from __future__ import annotations
import json, os, time
from collections import defaultdict
from datetime import datetime
import math
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


def add_team_recency(merged: pd.DataFrame) -> pd.DataFrame:
    """For each team, compute exp-weighted recency stats from prior games.
    Uses strict shift(1) — features at game N use games 0..N-1.
    """
    merged = merged.reset_index(drop=True).copy()
    # team_history[team] = list of (date_str, pts_for, pts_against)
    th = defaultdict(list)

    n = len(merged)
    exp_ortg = np.zeros(n); exp_drtg = np.zeros(n)
    l5_pts_for = np.zeros(n); l5_pts_against = np.zeros(n)
    l3_vs_l20_pts = np.zeros(n); l3_vs_l20_def = np.zeros(n)

    home_arrs = {"exp_ortg":exp_ortg.copy(), "exp_drtg":exp_drtg.copy(),
                 "l5_pts_for":l5_pts_for.copy(), "l5_pts_against":l5_pts_against.copy(),
                 "l3_vs_l20_pts":l3_vs_l20_pts.copy(), "l3_vs_l20_def":l3_vs_l20_def.copy()}
    away_arrs = {"exp_ortg":exp_ortg.copy(), "exp_drtg":exp_drtg.copy(),
                 "l5_pts_for":l5_pts_for.copy(), "l5_pts_against":l5_pts_against.copy(),
                 "l3_vs_l20_pts":l3_vs_l20_pts.copy(), "l3_vs_l20_def":l3_vs_l20_def.copy()}

    HALFLIFE = 4.0
    LAMBDA = math.log(2) / HALFLIFE  # weight = exp(-lambda * k_ago)

    def _compute_features(history_list):
        """history_list is list of (date, pts_for, pts_against) in chronological order.
        Returns dict of features computed on these prior games."""
        if not history_list:
            return None
        n_h = len(history_list)
        # exp-weighted
        pts_for = np.array([h[1] for h in history_list])
        pts_aga = np.array([h[2] for h in history_list])
        # weights: most recent gets highest weight
        weights = np.exp(-LAMBDA * np.arange(n_h)[::-1])
        weights /= weights.sum()
        exp_pts_for = float(np.sum(weights * pts_for))
        exp_pts_aga = float(np.sum(weights * pts_aga))
        # L5
        l5_for = float(np.mean(pts_for[-5:]))
        l5_aga = float(np.mean(pts_aga[-5:]))
        # L3 vs L20
        l3_for = float(np.mean(pts_for[-3:])) if n_h >= 3 else l5_for
        l3_aga = float(np.mean(pts_aga[-3:])) if n_h >= 3 else l5_aga
        l20_for = float(np.mean(pts_for[-20:])) if n_h >= 20 else float(np.mean(pts_for))
        l20_aga = float(np.mean(pts_aga[-20:])) if n_h >= 20 else float(np.mean(pts_aga))
        l20_std_for = float(np.std(pts_for[-20:])) if n_h >= 20 else float(np.std(pts_for) + 1e-6)
        l20_std_aga = float(np.std(pts_aga[-20:])) if n_h >= 20 else float(np.std(pts_aga) + 1e-6)
        z_for = (l3_for - l20_for) / max(l20_std_for, 1e-6)
        z_aga = (l3_aga - l20_aga) / max(l20_std_aga, 1e-6)
        return {"exp_ortg":exp_pts_for, "exp_drtg":exp_pts_aga,
                "l5_pts_for":l5_for, "l5_pts_against":l5_aga,
                "l3_vs_l20_pts":z_for, "l3_vs_l20_def":z_aga}

    for idx in range(n):
        row = merged.iloc[idx]
        h, a = str(row["home_team"]), str(row["away_team"])
        # Compute features from prior history
        h_feats = _compute_features(th[h])
        a_feats = _compute_features(th[a])
        if h_feats:
            for k, v in h_feats.items():
                home_arrs[k][idx] = v
        if a_feats:
            for k, v in a_feats.items():
                away_arrs[k][idx] = v
        # Update history with this game
        th[h].append((row["game_date"], row["home_score"], row["away_score"]))
        th[a].append((row["game_date"], row["away_score"], row["home_score"]))

    for k in home_arrs:
        merged[f"home_{k}"] = home_arrs[k]
        merged[f"away_{k}"] = away_arrs[k]
    # Diffs
    for k in home_arrs:
        merged[f"{k}_diff"] = merged[f"home_{k}"] - merged[f"away_{k}"]
    return merged


# Re-use the cross-stat / pace / z / trap from B3 to get to 94 base
def add_b3_features(merged: pd.DataFrame) -> pd.DataFrame:
    m = merged.copy()
    # Cross-stat
    away_def = m["away_def_rtg"].replace(0, np.nan).fillna(110.0)
    home_def = m["home_def_rtg"].replace(0, np.nan).fillna(110.0)
    m["home_off_to_away_def"] = m["home_off_rtg"] / away_def
    m["away_off_to_home_def"] = m["away_off_rtg"] / home_def
    m["off_def_ratio_diff"] = m["home_off_to_away_def"] - m["away_off_to_home_def"]
    away_def_l10 = m["away_def_rtg_L10"].replace(0, np.nan).fillna(110.0)
    home_def_l10 = m["home_def_rtg_L10"].replace(0, np.nan).fillna(110.0)
    m["home_off_L10_to_away_def_L10"] = m["home_off_rtg_L10"] / away_def_l10
    m["away_off_L10_to_home_def_L10"] = m["away_off_rtg_L10"] / home_def_l10
    # Pace-adj
    m["home_pace_adj_score"] = m["home_off_rtg"] * m["home_pace"] / 100.0
    m["away_pace_adj_score"] = m["away_off_rtg"] * m["away_pace"] / 100.0
    m["pace_adj_total"] = m["home_pace_adj_score"] + m["away_pace_adj_score"]
    m["pace_adj_diff"] = m["home_pace_adj_score"] - m["away_pace_adj_score"]
    m["home_pace_adj_score_L10"] = m["home_off_rtg_L10"] * m["home_pace"] / 100.0
    m["away_pace_adj_score_L10"] = m["away_off_rtg_L10"] * m["away_pace"] / 100.0
    # Z-score per season
    if "season" not in m.columns:
        m["season"] = m["game_date"].astype(str).str[:7]
    for col in ["home_net_rtg","away_net_rtg","home_off_rtg","away_off_rtg",
                "home_def_rtg","away_def_rtg"]:
        if col in m.columns:
            grp = m.groupby("season")[col]
            mu = grp.transform("mean")
            sd = grp.transform("std").replace(0, np.nan).fillna(1.0)
            m[f"{col}_zsea"] = (m[col] - mu) / sd
    # Trap-game
    home_fav = (m["net_rtg_diff"] > 5).astype(int)
    home_b2b = m["home_back_to_back"].astype(int)
    home_warm = (m["home_last5_wins"] >= 3).astype(int)
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
    print("R12 BATCH-4 — per-team exp-weighted recency + trend features", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)

    print("[2] adding R12 B3 features (cross + pace + z + trap) ...", flush=True)
    merged = add_b3_features(merged)
    print("[3] computing per-team recency features (exp-weighted, L5, L3 vs L20) ...", flush=True)
    merged = add_team_recency(merged)
    print(f"  added exp_ortg, exp_drtg, l5_pts_for/against, l3_vs_l20 (z) for home+away+diffs", flush=True)

    base_94 = [c for c in FEAT_COLS_BASE if c in merged.columns]
    # R12 B3 additions
    B3_COLS = ["home_off_to_away_def","away_off_to_home_def","off_def_ratio_diff",
               "home_off_L10_to_away_def_L10","away_off_L10_to_home_def_L10",
               "home_pace_adj_score","away_pace_adj_score","pace_adj_total",
               "pace_adj_diff","home_pace_adj_score_L10","away_pace_adj_score_L10",
               "trap_home_signals","trap_home_overconf","trap_away_motivated","trap_combo"]
    Z_COLS = [c for c in merged.columns if c.endswith("_zsea")]
    base_94 = base_94 + B3_COLS + Z_COLS

    # New recency features
    RECENCY_COLS = []
    for prefix in ["home_","away_"]:
        for k in ["exp_ortg","exp_drtg","l5_pts_for","l5_pts_against",
                 "l3_vs_l20_pts","l3_vs_l20_def"]:
            RECENCY_COLS.append(f"{prefix}{k}")
    for k in ["exp_ortg","exp_drtg","l5_pts_for","l5_pts_against",
              "l3_vs_l20_pts","l3_vs_l20_def"]:
        RECENCY_COLS.append(f"{k}_diff")

    avail_base = [c for c in base_94 if c in merged.columns]
    avail_recency = avail_base + [c for c in RECENCY_COLS if c in merged.columns]

    for cols in [avail_base, avail_recency]:
        merged[cols] = merged[cols].fillna(0.0)

    print(f"  feat sets: base94={len(avail_base)}, +recency={len(avail_recency)}", flush=True)

    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values
    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    variants = [
        ("R12_B4_total_with_recency",   "reg", "total_pts_box", avail_recency, None),
        ("R12_B4_spread_with_recency",  "reg", "score_diff",    avail_recency, None),
        ("R12_B4_home_pts_recency",     "reg", "home_score",    avail_recency, None),
        ("R12_B4_away_pts_recency",     "reg", "away_score",    avail_recency, None),
        ("R12_B4_O230_recency",         "bin", "over_230",      avail_recency, "P(total > 230)"),
        ("R12_B4_AH3_recency",          "bin", "home_cover_AH3",avail_recency, "P(home covers -3)"),
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
