"""probe_R11_M2v53_to_v68_batch4.py — 16-variant game-level sweep, batch 4.

NEW SURFACES previously untouched:
  - Half-time spread (continuous + binaries at -1, -3, -5)
  - Q1 spread (continuous + binaries at -1, -3)
  - Q3 total + Q3 spread
  - Team total props (home_pts > 110, 115; away_pts > 105, 110)
  - Margin compass (P(close game |margin|<5), P(landslide |margin|>20))
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
            "game_id": gid,
            "home_score": h, "away_score": a,
            "score_diff": h - a, "total_pts_box": h + a,
            "home_q1": hq[0], "home_q2": hq[1], "home_q3": hq[2], "home_q4": hq[3],
            "away_q1": aq[0], "away_q2": aq[1], "away_q3": aq[2], "away_q4": aq[3],
            "h1_score_diff": (hq[0]+hq[1]) - (aq[0]+aq[1]),
            "q1_score_diff": hq[0] - aq[0],
            "q3_total": hq[2]+aq[2],
            "q3_score_diff": hq[2] - aq[2],
        })
    return pd.DataFrame(rows)


def wf_regression(merged, label_col, naive_pred, feat_cols, probe_name):
    import lightgbm as lgb
    y = merged[label_col].astype(float).values
    n = len(merged); fold_size = n // 4
    folds, aa, al, an = [], [], [], []
    for fi in range(4):
        ts = fi * fold_size
        te = (fi + 1) * fold_size if fi < 3 else n
        tr = list(range(0, ts)); ti = list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20:
            continue
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
        m.fit(merged[feat_cols].iloc[tr].values, y[tr])
        pred = m.predict(merged[feat_cols].iloc[ti].values)
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
    return {"probe": probe_name, "kind": "regression", "label": label_col,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {n_p}/{n_v}, delta {dp:+.2f}%",
            "n_games": int(len(merged)),
            "pooled_naive_mae": round(p_n,4), "pooled_lgb_mae": round(p_l,4),
            "pooled_delta_pct": round(dp,2),
            "n_folds_positive": n_p, "n_valid_folds": n_v, "fold_results": folds}


def wf_binary(merged, label_col, naive_pred, feat_cols, probe_name, desc):
    import lightgbm as lgb
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
        c = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)
        c.fit(merged[feat_cols].iloc[tr].values, y[tr])
        pred = c.predict_proba(merged[feat_cols].iloc[ti].values)[:, 1]
        nv = naive_pred[ti]
        folds.append({"fold": fi, "naive_brier": round(brier_score_loss(y[ti], nv), 5),
                      "lgb_brier": round(brier_score_loss(y[ti], pred), 5)})
        aa.extend(y[ti].tolist()); al.extend(pred.tolist()); an.extend(nv.tolist())
    p_nb = float(brier_score_loss(aa, an))
    p_lb = float(brier_score_loss(aa, al))
    try: p_lu = float(roc_auc_score(aa, al))
    except: p_lu = float("nan")
    bdp = (p_lb - p_nb) / p_nb * 100
    n_v = len(folds)
    ship = ((p_lb <= p_nb * 0.95) or (p_lu >= 0.60)) and n_v >= 3
    return {"probe": probe_name, "kind": "binary", "label": label_col, "label_desc": desc,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {p_lb:.4f} ({bdp:+.2f}%); AUC {p_lu:.4f}",
            "n_games": int(len(merged)), "pos_rate": float(np.mean(y)),
            "pooled_lgb_brier": round(p_lb,5), "pooled_naive_brier": round(p_nb,5),
            "pooled_lgb_auc": round(p_lu,5), "brier_delta_pct": round(bdp,3),
            "n_valid_folds": n_v, "fold_results": folds}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("BATCH-4 PROBE R11 M2v53-M2v68 — half-time + Q1/Q3 spread markets", flush=True)
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

    # Binary labels
    merged["h1_home_lead1"] = (merged["h1_score_diff"] >= 1).astype(int)
    merged["h1_home_lead3"] = (merged["h1_score_diff"] >= 3).astype(int)
    merged["h1_home_lead5"] = (merged["h1_score_diff"] >= 5).astype(int)
    merged["q1_home_lead1"] = (merged["q1_score_diff"] >= 1).astype(int)
    merged["q1_home_lead3"] = (merged["q1_score_diff"] >= 3).astype(int)
    merged["home_pts_O110"] = (merged["home_score"] > 110).astype(int)
    merged["home_pts_O115"] = (merged["home_score"] > 115).astype(int)
    merged["away_pts_O105"] = (merged["away_score"] > 105).astype(int)
    merged["away_pts_O110"] = (merged["away_score"] > 110).astype(int)
    merged["close_game"] = (np.abs(merged["score_diff"]) < 5).astype(int)
    merged["landslide"] = (np.abs(merged["score_diff"]) > 20).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values

    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    variants = [
        ("R11_M2v53_h1_score_diff", "reg", "h1_score_diff", "first-half margin"),
        ("R11_M2v54_q1_score_diff", "reg", "q1_score_diff", "first-quarter margin"),
        ("R11_M2v55_q3_total", "reg", "q3_total", "Q3 combined total"),
        ("R11_M2v56_q3_score_diff", "reg", "q3_score_diff", "Q3-only margin"),
        ("R11_M2v57_h1_home_lead1", "bin", "h1_home_lead1", "P(home leads at half)"),
        ("R11_M2v58_h1_home_lead3", "bin", "h1_home_lead3", "P(home up 3+ at half)"),
        ("R11_M2v59_h1_home_lead5", "bin", "h1_home_lead5", "P(home up 5+ at half)"),
        ("R11_M2v60_q1_home_lead1", "bin", "q1_home_lead1", "P(home leads after Q1)"),
        ("R11_M2v61_q1_home_lead3", "bin", "q1_home_lead3", "P(home up 3+ after Q1)"),
        ("R11_M2v62_home_pts_O110", "bin", "home_pts_O110", "P(home scores > 110)"),
        ("R11_M2v63_home_pts_O115", "bin", "home_pts_O115", "P(home scores > 115)"),
        ("R11_M2v64_away_pts_O105", "bin", "away_pts_O105", "P(away scores > 105)"),
        ("R11_M2v65_away_pts_O110", "bin", "away_pts_O110", "P(away scores > 110)"),
        ("R11_M2v66_close_game", "bin", "close_game", "P(|margin| < 5)"),
        ("R11_M2v67_landslide", "bin", "landslide", "P(|margin| > 20)"),
        ("R11_M2v68_q1_total_O55", "bin", None, "P(Q1 total > 55)"),  # constructed below
    ]
    merged["q1_total_O55"] = (merged["home_q1"] + merged["away_q1"] > 55).astype(int)

    results = {}
    for name, kind, label, desc in variants:
        if name == "R11_M2v68_q1_total_O55":
            label = "q1_total_O55"
        t_v = time.time()
        if kind == "reg":
            out = wf_regression(merged, label, naive_l5_mean(label), avail, name)
        else:
            out = wf_binary(merged, label, naive_l5_prop(label), avail, name, desc)
        out["elapsed_s"] = round(time.time() - t_v, 1)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        if out["kind"] == "regression":
            print(f"  {name}: {out['status']} delta {out['pooled_delta_pct']:+.2f}% "
                  f"({out['n_folds_positive']}/{out['n_valid_folds']}) [{out['elapsed_s']}s]", flush=True)
        else:
            print(f"  {name}: {out['status']} Brier {out['pooled_lgb_brier']:.4f} "
                  f"AUC {out['pooled_lgb_auc']:.4f} ({out['brier_delta_pct']:+.2f}%) "
                  f"[{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
