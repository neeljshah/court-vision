"""probe_R12_h2h_uncertainty_batch1.py — Round 12 opening batch.

R11 game-level family is saturated. R12 tests NEW FEATURE AXES that weren't
in any R11 batch:

  (A) Head-to-head (H2H) history features per matchup
      - Last 5 H2H meetings of these two teams
      - H2H avg total, H2H avg margin (home perspective)
  (B) sim_score_diff_std as standalone uncertainty signal
      - Test if uncertainty-aware features help in regression
  (C) Recency-weighted ortg/drtg (vs season-average or L10)
      - Use exponential decay with halflife 7 days

Variants:
  R12_T1_total_with_h2h        regression
  R12_T2_spread_with_h2h       regression
  R12_T3_total_with_unc        regression
  R12_T4_spread_with_unc       regression
  R12_T5_total_with_h2h_unc    regression (both)
  R12_T6_spread_with_h2h_unc   regression (both)
  R12_T7_O230_with_h2h_unc     binary
  R12_T8_AH3_with_h2h_unc      binary
"""
from __future__ import annotations
import json, os, time
from collections import defaultdict
from typing import Dict, List
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
    "sim_win_prob","sim_score_diff_mean","sim_pace_adj",  # NOTE: sim_score_diff_std deliberately excluded from BASE
]

# NEW FEATURE COLUMNS (R12)
UNC_COLS = ["sim_score_diff_std"]  # uncertainty signal
H2H_COLS = ["h2h_avg_total_L5", "h2h_avg_home_margin_L5", "h2h_n_games_L5"]


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


def add_h2h_features(merged: pd.DataFrame) -> pd.DataFrame:
    """For each game, find the previous 5 H2H matchups (either direction) and
    compute avg total + avg home_margin (from current home team's perspective).
    Strictly prior games only (shift discipline)."""
    merged = merged.reset_index(drop=True)
    # Build per-pair history (sorted by date)
    pair_history = defaultdict(list)  # frozenset({home, away}) -> list[(date, gid, home_team, score_diff, total)]
    h2h_total = np.full(len(merged), np.nan)
    h2h_margin = np.full(len(merged), np.nan)
    h2h_n = np.zeros(len(merged))

    for idx, row in merged.iterrows():
        h, a = str(row["home_team"]), str(row["away_team"])
        date = row["game_date"]
        key = frozenset({h, a})
        # Compute features from prior games
        priors = [r for r in pair_history[key] if r[0] < date]
        if priors:
            last5 = priors[-5:]
            totals = [r[4] for r in last5]
            # margin from CURRENT home team's perspective
            margins = []
            for prior_date, prior_gid, prior_home, prior_diff, prior_total in last5:
                # prior_diff is from prior_home's perspective; flip if current home != prior home
                m_from_curr_home = prior_diff if prior_home == h else -prior_diff
                margins.append(m_from_curr_home)
            h2h_total[idx] = float(np.mean(totals))
            h2h_margin[idx] = float(np.mean(margins))
            h2h_n[idx] = len(last5)
        # Add this game to history
        pair_history[key].append((date, row["game_id"], h, row["score_diff"], row["total_pts_box"]))

    merged["h2h_avg_total_L5"] = pd.Series(h2h_total).fillna(merged["total_pts_box"].mean())
    merged["h2h_avg_home_margin_L5"] = pd.Series(h2h_margin).fillna(0.0)
    merged["h2h_n_games_L5"] = h2h_n
    return merged


def _fit_ens_reg(X_tr, y_tr):
    """LGB + XGB equal-weight ensemble (matches M2v89 architecture)."""
    import lightgbm as lgb, xgboost as xgb
    l = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
    x = xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, n_jobs=2, verbosity=0)
    l.fit(X_tr, y_tr); x.fit(X_tr, y_tr)
    return l, x


def _ens_pred(l, x, X_te):
    return 0.5 * l.predict(X_te) + 0.5 * x.predict(X_te)


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


def _ens_pred_proba(l, x, X_te):
    return 0.5 * l.predict_proba(X_te)[:,1] + 0.5 * x.predict_proba(X_te)[:,1]


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
        pred = _ens_pred(l, x, X_te)
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
        pred = _ens_pred_proba(l, x, X_te)
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
    print("R12 BATCH-1 — head-to-head + uncertainty features", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)

    # Add H2H features (this is per-pair-history, sequential)
    print("[2] computing H2H history features ...", flush=True)
    merged = add_h2h_features(merged)
    print(f"  h2h_n_games_L5 distribution: min={merged['h2h_n_games_L5'].min()}, "
          f"mean={merged['h2h_n_games_L5'].mean():.2f}, max={merged['h2h_n_games_L5'].max()}", flush=True)

    avail_base = [c for c in FEAT_COLS_BASE if c in merged.columns]
    avail_unc = avail_base + [c for c in UNC_COLS if c in merged.columns]
    avail_h2h = avail_base + H2H_COLS
    avail_both = avail_base + [c for c in UNC_COLS if c in merged.columns] + H2H_COLS

    for cols in [avail_base, avail_unc, avail_h2h, avail_both]:
        merged[cols] = merged[cols].fillna(0.0)

    print(f"  feature sets: base={len(avail_base)}, +unc={len(avail_unc)}, +h2h={len(avail_h2h)}, +both={len(avail_both)}", flush=True)

    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values
    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    variants = [
        ("R12_T1_total_with_h2h",     "reg", "total_pts_box", avail_h2h,  None),
        ("R12_T2_spread_with_h2h",    "reg", "score_diff",    avail_h2h,  None),
        ("R12_T3_total_with_unc",     "reg", "total_pts_box", avail_unc,  None),
        ("R12_T4_spread_with_unc",    "reg", "score_diff",    avail_unc,  None),
        ("R12_T5_total_with_h2h_unc", "reg", "total_pts_box", avail_both, None),
        ("R12_T6_spread_with_h2h_unc","reg", "score_diff",    avail_both, None),
        ("R12_T7_O230_with_h2h_unc",  "bin", "over_230",      avail_both, "P(total > 230)"),
        ("R12_T8_AH3_with_h2h_unc",   "bin", "home_cover_AH3",avail_both, "P(home covers -3)"),
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
