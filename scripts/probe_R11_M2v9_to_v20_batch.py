"""probe_R11_M2v9_to_v20_batch.py — 12-variant game-level model sweep.

Runs all in one Python process (parallelizable internally is overkill for
~12s LGB trainings each). Outputs one results JSON per variant.

Variants:
  M2v9  home_pts_expanded             (continuous regression)
  M2v10 away_pts_expanded             (continuous regression)
  M2v11 total_O220 binary             (over/under 220 — heavy under)
  M2v12 total_O230 binary             (over/under 230 — mid)
  M2v13 spread_AH3 binary             (home covers -3)
  M2v14 spread_AH7 binary             (home covers -7)
  M2v15 home_q1 regression            (NEW SURFACE: first-quarter total)
  M2v16 home_q4 regression            (NEW SURFACE: final-quarter total)
  M2v17 h1_total regression           (NEW SURFACE: first-half total)
  M2v18 spread_AH5 binary             (home covers -5)
  M2v19 spread_AH10 binary            (home covers -10)
  M2v20 home_minus_away_q4 regression (NEW SURFACE: Q4-only margin)
"""
from __future__ import annotations
import json, os, sys, time
from typing import Dict, List
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
    "iso_matchup_edge",
    "home_pnr_ppp", "away_pnr_ppp",
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
            "h1_total": hq[0]+hq[1]+aq[0]+aq[1],
            "h2_total": hq[2]+hq[3]+aq[2]+aq[3],
            "home_q1_plus_away_q1": hq[0]+aq[0],
            "home_q4_plus_away_q4": hq[3]+aq[3],
            "q4_margin": (hq[3] - aq[3]),
        })
    return pd.DataFrame(rows)


def wf_regression(merged: pd.DataFrame, label_col: str, naive_pred: np.ndarray,
                  feat_cols: List[str], probe_name: str, baseline_pp: float):
    import lightgbm as lgb
    y = merged[label_col].astype(float).values
    n = len(merged)
    fold_size = n // 4
    folds = []
    all_act, all_lgb, all_naive = [], [], []
    for fi in range(4):
        ts = fi * fold_size
        te = (fi + 1) * fold_size if fi < 3 else n
        tr = list(range(0, ts))
        ti = list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20:
            continue
        X_tr = merged[feat_cols].iloc[tr].values
        X_te = merged[feat_cols].iloc[ti].values
        m = lgb.LGBMRegressor(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, min_child_samples=20,
            random_state=42, n_jobs=2, verbose=-1)
        m.fit(X_tr, y[tr])
        pred = m.predict(X_te)
        lgb_mae = float(np.mean(np.abs(pred - y[ti])))
        nv = naive_pred[ti]
        naive_mae = float(np.mean(np.abs(nv - y[ti])))
        delta = lgb_mae - naive_mae
        delta_pct = delta / naive_mae * 100
        folds.append({"fold": fi, "n_train": len(tr), "n_test": len(ti),
                      "naive_mae": round(naive_mae, 4), "lgb_mae": round(lgb_mae, 4),
                      "delta": round(delta, 4), "delta_pct": round(delta_pct, 2)})
        all_act.extend(y[ti].tolist())
        all_lgb.extend(pred.tolist())
        all_naive.extend(nv.tolist())
    p_naive = float(np.mean(np.abs(np.array(all_naive) - np.array(all_act))))
    p_lgb = float(np.mean(np.abs(np.array(all_lgb) - np.array(all_act))))
    delta_pct = (p_lgb - p_naive) / p_naive * 100
    n_valid = len(folds)
    n_pos = sum(1 for f in folds if f["delta"] < 0)
    wf_ok = (n_valid >= 3) and (n_pos == n_valid)
    gate_5pct = delta_pct <= -5.0
    ship = wf_ok and gate_5pct
    out = {
        "probe": probe_name,
        "kind": "regression",
        "label": label_col,
        "status": "SHIP" if ship else "REJECT",
        "ship_reason": f"WF {n_pos}/{n_valid} {'pass' if wf_ok else 'fail'}, delta {delta_pct:+.2f}% {'pass' if gate_5pct else 'fail'} (gate -5%)",
        "n_games": int(len(merged)),
        "n_features": len(feat_cols),
        "pooled_naive_mae": round(p_naive, 4),
        "pooled_lgb_mae": round(p_lgb, 4),
        "pooled_delta_pct": round(delta_pct, 2),
        "n_folds_positive": n_pos,
        "n_valid_folds": n_valid,
        "fold_results": folds,
    }
    return out


def wf_binary(merged: pd.DataFrame, label_col: str, naive_pred: np.ndarray,
              feat_cols: List[str], probe_name: str, label_desc: str):
    import lightgbm as lgb
    from sklearn.metrics import brier_score_loss, accuracy_score, roc_auc_score
    y = merged[label_col].astype(int).values
    n = len(merged)
    fold_size = n // 4
    folds = []
    all_act, all_lgb, all_naive = [], [], []
    for fi in range(4):
        ts = fi * fold_size
        te = (fi + 1) * fold_size if fi < 3 else n
        tr = list(range(0, ts))
        ti = list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20:
            continue
        X_tr = merged[feat_cols].iloc[tr].values
        X_te = merged[feat_cols].iloc[ti].values
        c = lgb.LGBMClassifier(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, min_child_samples=20,
            random_state=42, n_jobs=2, verbose=-1)
        c.fit(X_tr, y[tr])
        pred = c.predict_proba(X_te)[:, 1]
        lgb_brier = float(brier_score_loss(y[ti], pred))
        lgb_acc = float(accuracy_score(y[ti], (pred >= 0.5).astype(int)))
        try:
            lgb_auc = float(roc_auc_score(y[ti], pred))
        except Exception:
            lgb_auc = float("nan")
        nv = naive_pred[ti]
        n_brier = float(brier_score_loss(y[ti], nv))
        n_acc = float(accuracy_score(y[ti], (nv >= 0.5).astype(int)))
        folds.append({"fold": fi, "n_train": len(tr), "n_test": len(ti),
                      "naive_brier": round(n_brier, 5), "lgb_brier": round(lgb_brier, 5),
                      "lgb_acc": round(lgb_acc, 4), "lgb_auc": round(lgb_auc, 4)})
        all_act.extend(y[ti].tolist())
        all_lgb.extend(pred.tolist())
        all_naive.extend(nv.tolist())
    p_naive_brier = float(brier_score_loss(all_act, all_naive))
    p_lgb_brier = float(brier_score_loss(all_act, all_lgb))
    p_lgb_acc = float(accuracy_score(all_act, [1 if p >= 0.5 else 0 for p in all_lgb]))
    try:
        p_lgb_auc = float(roc_auc_score(all_act, all_lgb))
    except Exception:
        p_lgb_auc = float("nan")
    brier_delta_pct = (p_lgb_brier - p_naive_brier) / p_naive_brier * 100
    n_valid = len(folds)
    # Relaxed gates: Brier delta <= -5% OR AUC >= 0.60
    gate_brier = p_lgb_brier <= p_naive_brier * 0.95
    gate_auc = p_lgb_auc >= 0.60
    ship = (gate_brier or gate_auc) and n_valid >= 3
    out = {
        "probe": probe_name,
        "kind": "binary",
        "label": label_col,
        "label_desc": label_desc,
        "status": "SHIP" if ship else "REJECT",
        "ship_reason": (f"Brier {p_lgb_brier:.4f} delta {brier_delta_pct:+.2f}% "
                       f"{'pass' if gate_brier else 'fail'}; "
                       f"AUC {p_lgb_auc:.4f} {'pass' if gate_auc else 'fail'} (>=0.60)"),
        "n_games": int(len(merged)),
        "pos_rate": float(np.mean(y)),
        "pooled_naive_brier": round(p_naive_brier, 5),
        "pooled_lgb_brier": round(p_lgb_brier, 5),
        "pooled_lgb_acc": round(p_lgb_acc, 5),
        "pooled_lgb_auc": round(p_lgb_auc, 5),
        "brier_delta_pct": round(brier_delta_pct, 3),
        "n_valid_folds": n_valid,
        "fold_results": folds,
    }
    return out


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("BATCH PROBE R11 M2v9-M2v20 — 12 game-level variants", flush=True)
    print("=" * 70, flush=True)

    print("\n[load] season_games + linescores ...", flush=True)
    sg = load_season_games()
    ls = load_linescores()
    print(f"  season_games {len(sg)} rows, linescores {len(ls)} rows", flush=True)
    merged = sg.merge(ls, on="game_id", how="inner")
    for col in ["home_off_rtg", "away_off_rtg", "home_pace", "away_pace"]:
        merged = merged[merged[col] > 0]
    merged = merged.sort_values("game_date").reset_index(drop=True)
    print(f"  after filter, sorted: {len(merged)} games", flush=True)
    avail = [c for c in FEAT_COLS if c in merged.columns]
    merged[avail] = merged[avail].fillna(0.0)
    print(f"  features: {len(avail)}/{len(FEAT_COLS)}", flush=True)

    # Derive binary labels and naive baselines for each variant
    merged["over_220"] = (merged["total_pts_box"] > 220).astype(int)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)
    merged["home_cover_AH5"] = (merged["score_diff"] + 5 > 0).astype(int)
    merged["home_cover_AH7"] = (merged["score_diff"] + 7 > 0).astype(int)
    merged["home_cover_AH10"] = (merged["score_diff"] + 10 > 0).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values

    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    results = {}

    variants = [
        # (probe_name, kind, label_col, naive_fn, label_desc)
        ("R11_M2v9_home_pts_expanded", "reg", "home_score", "home_score", "home team total"),
        ("R11_M2v10_away_pts_expanded", "reg", "away_score", "away_score", "away team total"),
        ("R11_M2v11_total_O220", "bin", "over_220", "over_220", "P(total > 220)"),
        ("R11_M2v12_total_O230", "bin", "over_230", "over_230", "P(total > 230)"),
        ("R11_M2v13_spread_AH3", "bin", "home_cover_AH3", "home_cover_AH3", "P(home covers -3)"),
        ("R11_M2v14_spread_AH7", "bin", "home_cover_AH7", "home_cover_AH7", "P(home covers -7)"),
        ("R11_M2v15_home_q1", "reg", "home_q1", "home_q1", "home Q1 score"),
        ("R11_M2v16_home_q4", "reg", "home_q4", "home_q4", "home Q4 score"),
        ("R11_M2v17_h1_total", "reg", "h1_total", "h1_total", "first-half total"),
        ("R11_M2v18_spread_AH5", "bin", "home_cover_AH5", "home_cover_AH5", "P(home covers -5)"),
        ("R11_M2v19_spread_AH10", "bin", "home_cover_AH10", "home_cover_AH10", "P(home covers -10)"),
        ("R11_M2v20_q4_margin", "reg", "q4_margin", "q4_margin", "Q4-only margin"),
    ]

    for probe_name, kind, label, naive_col, label_desc in variants:
        t_v = time.time()
        if kind == "reg":
            naive = naive_l5_mean(naive_col)
            out = wf_regression(merged, label, naive, avail, probe_name, 0.0)
        else:
            naive = naive_l5_prop(naive_col)
            out = wf_binary(merged, label, naive, avail, probe_name, label_desc)
        out["elapsed_s"] = round(time.time() - t_v, 1)
        outp = os.path.join(DATA_CACHE, f"{probe_name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[probe_name] = out["status"]
        if out["kind"] == "regression":
            print(f"  {probe_name}: {out['status']} delta {out['pooled_delta_pct']:+.2f}% "
                  f"({out['n_folds_positive']}/{out['n_valid_folds']} folds) [{out['elapsed_s']}s]",
                  flush=True)
        else:
            print(f"  {probe_name}: {out['status']} Brier {out['pooled_lgb_brier']:.4f} "
                  f"AUC {out['pooled_lgb_auc']:.4f} (delta {out['brier_delta_pct']:+.2f}%) "
                  f"[{out['elapsed_s']}s]", flush=True)

    n_ship = sum(1 for s in results.values() if s == "SHIP")
    n_rej = sum(1 for s in results.values() if s == "REJECT")
    print(f"\n[done] {n_ship} SHIPS, {n_rej} REJECTS in {time.time()-t0:.1f}s", flush=True)
    print(f"  ships: {[k for k,v in results.items() if v=='SHIP']}", flush=True)


if __name__ == "__main__":
    main()
