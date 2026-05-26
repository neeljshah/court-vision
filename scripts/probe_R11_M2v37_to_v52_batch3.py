"""probe_R11_M2v37_to_v52_batch3.py — 16-variant game-level sweep, batch 3.

Tests:
  (A) Team-identity features (one-hot encoded home_team + away_team) as
      additional axis on top of the 70-feature expanded base.
  (B) Sim-features (sim_score_diff_mean, sim_score_diff_std, sim_pace_adj,
      sim_win_prob) added to the base — tests if Monte Carlo sims add
      orthogonal signal to point-estimates.
  (C) New thresholds & surfaces: O/U at 213/217/227/232/237/247, ATS at -4/-6/-9/-11,
      P(home_q1 > 28), P(home wins by 10+).

Variants:
  M2v37 total_with_team_ids regression
  M2v38 spread_with_team_ids regression
  M2v39 total_with_sim_feats regression
  M2v40 spread_with_sim_feats regression
  M2v41 total_O213 binary
  M2v42 total_O217 binary
  M2v43 total_O227 binary
  M2v44 total_O232 binary
  M2v45 total_O237 binary
  M2v46 total_O247 binary
  M2v47 spread_AH4 binary
  M2v48 spread_AH6 binary
  M2v49 spread_AH9 binary
  M2v50 spread_AH11 binary
  M2v51 home_q1_over28 binary
  M2v52 home_winby10 binary  (P(home wins by 10+))
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

FEAT_COLS_BASE = [
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
]

SIM_FEATS = ["sim_win_prob", "sim_score_diff_mean", "sim_score_diff_std", "sim_pace_adj"]


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
        folds.append({"fold": fi, "n_train": len(tr), "n_test": len(ti),
                      "naive_mae": round(nmae,4), "lgb_mae": round(lgb_mae,4),
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
            "n_games": int(len(merged)), "n_features": len(feat_cols),
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
        folds.append({"fold": fi, "n_test": len(ti),
                      "naive_brier": round(brier_score_loss(y[ti], nv), 5),
                      "lgb_brier": round(brier_score_loss(y[ti], pred), 5),
                      "lgb_acc": round(accuracy_score(y[ti], (pred>=0.5).astype(int)), 4)})
        aa.extend(y[ti].tolist()); al.extend(pred.tolist()); an.extend(nv.tolist())
    p_nb = float(brier_score_loss(aa, an))
    p_lb = float(brier_score_loss(aa, al))
    p_la = float(accuracy_score(aa, [1 if p>=0.5 else 0 for p in al]))
    try: p_lu = float(roc_auc_score(aa, al))
    except: p_lu = float("nan")
    bdp = (p_lb - p_nb) / p_nb * 100
    n_v = len(folds)
    ship = ((p_lb <= p_nb * 0.95) or (p_lu >= 0.60)) and n_v >= 3
    return {"probe": probe_name, "kind": "binary", "label": label_col, "label_desc": desc,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {p_lb:.4f} delta {bdp:+.2f}%; AUC {p_lu:.4f}",
            "n_games": int(len(merged)), "pos_rate": float(np.mean(y)),
            "pooled_naive_brier": round(p_nb,5),
            "pooled_lgb_brier": round(p_lb,5),
            "pooled_lgb_acc": round(p_la,5),
            "pooled_lgb_auc": round(p_lu,5),
            "brier_delta_pct": round(bdp,3),
            "n_valid_folds": n_v, "fold_results": folds}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("BATCH-3 PROBE R11 M2v37-M2v52", flush=True)
    print("=" * 70, flush=True)

    sg = load_season_games()
    ls = load_linescores()
    merged = sg.merge(ls, on="game_id", how="inner")
    for col in ["home_off_rtg", "away_off_rtg", "home_pace", "away_pace"]:
        merged = merged[merged[col] > 0]
    merged = merged.sort_values("game_date").reset_index(drop=True)
    print(f"  data: {len(merged)} games", flush=True)

    avail = [c for c in FEAT_COLS_BASE if c in merged.columns]
    merged[avail] = merged[avail].fillna(0.0)

    # (A) Team identity one-hot
    if "home_team" in merged.columns:
        team_dummies_h = pd.get_dummies(merged["home_team"], prefix="ht").astype(float)
        team_dummies_a = pd.get_dummies(merged["away_team"], prefix="at").astype(float)
        team_cols = list(team_dummies_h.columns) + list(team_dummies_a.columns)
        merged = pd.concat([merged.reset_index(drop=True),
                            team_dummies_h.reset_index(drop=True),
                            team_dummies_a.reset_index(drop=True)], axis=1)
    else:
        team_cols = []
    print(f"  team_cols: {len(team_cols)}", flush=True)

    # (B) Sim features
    sim_cols = [c for c in SIM_FEATS if c in merged.columns]
    for c in sim_cols:
        merged[c] = merged[c].fillna(0.0)
    print(f"  sim_cols: {sim_cols}", flush=True)

    feat_team = avail + team_cols
    feat_sim = avail + sim_cols
    feat_all = avail + team_cols + sim_cols
    print(f"  feat sets: base {len(avail)}, +team {len(feat_team)}, +sim {len(feat_sim)}, all {len(feat_all)}",
          flush=True)

    # Labels
    merged["over_213"] = (merged["total_pts_box"] > 213).astype(int)
    merged["over_217"] = (merged["total_pts_box"] > 217).astype(int)
    merged["over_227"] = (merged["total_pts_box"] > 227).astype(int)
    merged["over_232"] = (merged["total_pts_box"] > 232).astype(int)
    merged["over_237"] = (merged["total_pts_box"] > 237).astype(int)
    merged["over_247"] = (merged["total_pts_box"] > 247).astype(int)
    merged["home_cover_AH4"] = (merged["score_diff"] + 4 > 0).astype(int)
    merged["home_cover_AH6"] = (merged["score_diff"] + 6 > 0).astype(int)
    merged["home_cover_AH9"] = (merged["score_diff"] + 9 > 0).astype(int)
    merged["home_cover_AH11"] = (merged["score_diff"] + 11 > 0).astype(int)
    merged["home_q1_over28"] = (merged["home_q1"] > 28).astype(int)
    merged["home_winby10"] = (merged["score_diff"] >= 10).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values

    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    variants = [
        ("R11_M2v37_total_with_team_ids", "reg", "total_pts_box", feat_team, None),
        ("R11_M2v38_spread_with_team_ids", "reg", "score_diff", feat_team, None),
        ("R11_M2v39_total_with_sim", "reg", "total_pts_box", feat_sim, None),
        ("R11_M2v40_spread_with_sim", "reg", "score_diff", feat_sim, None),
        ("R11_M2v41_total_O213", "bin", "over_213", avail, "P(total > 213)"),
        ("R11_M2v42_total_O217", "bin", "over_217", avail, "P(total > 217)"),
        ("R11_M2v43_total_O227", "bin", "over_227", avail, "P(total > 227)"),
        ("R11_M2v44_total_O232", "bin", "over_232", avail, "P(total > 232)"),
        ("R11_M2v45_total_O237", "bin", "over_237", avail, "P(total > 237)"),
        ("R11_M2v46_total_O247", "bin", "over_247", avail, "P(total > 247)"),
        ("R11_M2v47_spread_AH4", "bin", "home_cover_AH4", avail, "P(home covers -4)"),
        ("R11_M2v48_spread_AH6", "bin", "home_cover_AH6", avail, "P(home covers -6)"),
        ("R11_M2v49_spread_AH9", "bin", "home_cover_AH9", avail, "P(home covers -9)"),
        ("R11_M2v50_spread_AH11", "bin", "home_cover_AH11", avail, "P(home covers -11)"),
        ("R11_M2v51_home_q1_over28", "bin", "home_q1_over28", avail, "P(home Q1 > 28)"),
        ("R11_M2v52_home_winby10", "bin", "home_winby10", avail, "P(home wins by 10+)"),
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
            print(f"  {name}: {out['status']} delta {out['pooled_delta_pct']:+.2f}% "
                  f"({out['n_folds_positive']}/{out['n_valid_folds']}) "
                  f"feats={out['n_features']} [{out['elapsed_s']}s]", flush=True)
        else:
            print(f"  {name}: {out['status']} Brier {out['pooled_lgb_brier']:.4f} "
                  f"AUC {out['pooled_lgb_auc']:.4f} ({out['brier_delta_pct']:+.2f}%) "
                  f"[{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)
    print(f"  ships: {[k for k,v in results.items() if v=='SHIP']}", flush=True)


if __name__ == "__main__":
    main()
