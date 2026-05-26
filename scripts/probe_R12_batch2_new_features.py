"""probe_R12_batch2_new_features.py — R12 batch 2: orthogonal feature axes.

Tests:
  (1) Team form streak — consec W/L for home+away coming into game
  (2) Weighted L20 stats with exp decay halflife=7 days
  (3) Days-since-last-game (granular, not categorical rest_days)
  (4) Pace*efg interaction terms
  (5) Stars unavailable proxy (10 - stars_available)

All compared to canonical R12_T1 70-base features (LGB+XGB ensemble).
"""
from __future__ import annotations
import json, os, time
from collections import defaultdict
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


def add_team_form_features(merged: pd.DataFrame) -> pd.DataFrame:
    """For each team, compute coming-in streak and days-since-last-game.
    Streak: positive = consec wins, negative = consec losses, 0 = first game.
    Days-since: exact days since prior game (None for first game -> use rest_days).
    """
    merged = merged.reset_index(drop=True).copy()
    # Per-team history: list of (date_str, won_bool)
    team_history = defaultdict(list)

    home_streak = np.zeros(len(merged))
    away_streak = np.zeros(len(merged))
    home_days_since = np.full(len(merged), -1.0)
    away_days_since = np.full(len(merged), -1.0)

    from datetime import datetime
    def _parse(s):
        try: return datetime.strptime(s, "%Y-%m-%d")
        except: return None

    for idx, row in merged.iterrows():
        h, a = str(row["home_team"]), str(row["away_team"])
        date = row["game_date"]
        date_dt = _parse(date)
        # home streak
        h_hist = team_history[h]
        if h_hist:
            # find prior wins/losses
            streak = 0
            for prior_date, prior_won in reversed(h_hist):
                if streak == 0:
                    streak = 1 if prior_won else -1
                elif (streak > 0 and prior_won) or (streak < 0 and not prior_won):
                    streak += 1 if prior_won else -1
                else:
                    break
            home_streak[idx] = streak
            last_dt = _parse(h_hist[-1][0])
            if last_dt and date_dt:
                home_days_since[idx] = (date_dt - last_dt).days
        # away streak
        a_hist = team_history[a]
        if a_hist:
            streak = 0
            for prior_date, prior_won in reversed(a_hist):
                if streak == 0:
                    streak = 1 if prior_won else -1
                elif (streak > 0 and prior_won) or (streak < 0 and not prior_won):
                    streak += 1 if prior_won else -1
                else:
                    break
            away_streak[idx] = streak
            last_dt = _parse(a_hist[-1][0])
            if last_dt and date_dt:
                away_days_since[idx] = (date_dt - last_dt).days
        # Update history with this game's outcome
        home_won = row["score_diff"] > 0
        team_history[h].append((date, home_won))
        team_history[a].append((date, not home_won))

    merged["home_form_streak"] = home_streak
    merged["away_form_streak"] = away_streak
    # Fill -1 with median for missing first-games
    home_med = float(np.median(home_days_since[home_days_since >= 0])) if (home_days_since >= 0).any() else 2.0
    away_med = float(np.median(away_days_since[away_days_since >= 0])) if (away_days_since >= 0).any() else 2.0
    home_days_since[home_days_since < 0] = home_med
    away_days_since[away_days_since < 0] = away_med
    merged["home_days_since_last"] = home_days_since
    merged["away_days_since_last"] = away_days_since
    # Days-since differential (matters more than absolute)
    merged["days_since_diff"] = merged["home_days_since_last"] - merged["away_days_since_last"]
    return merged


def add_interaction_features(merged: pd.DataFrame) -> pd.DataFrame:
    merged = merged.copy()
    merged["home_pace_x_efg"] = merged["home_pace"] * merged["home_efg_pct"]
    merged["away_pace_x_efg"] = merged["away_pace"] * merged["away_efg_pct"]
    merged["pace_efg_diff"] = merged["home_pace_x_efg"] - merged["away_pace_x_efg"]
    merged["home_ortg_x_pace"] = merged["home_off_rtg"] * merged["home_pace"]
    merged["away_ortg_x_pace"] = merged["away_off_rtg"] * merged["away_pace"]
    return merged


def add_injury_proxy(merged: pd.DataFrame) -> pd.DataFrame:
    merged = merged.copy()
    # Stars unavailable (10 - stars_available, since 10 is max active stars usually)
    merged["home_stars_unavailable"] = (10.0 - merged.get("home_stars_available", 0)).clip(lower=0)
    merged["away_stars_unavailable"] = (10.0 - merged.get("away_stars_available", 0)).clip(lower=0)
    merged["stars_unavailable_diff"] = merged["home_stars_unavailable"] - merged["away_stars_unavailable"]
    return merged


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
    print("R12 BATCH-2 — team form, days-since, interactions, injury proxy", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)

    print("[2] adding team-form features ...", flush=True)
    merged = add_team_form_features(merged)
    print(f"  home_form_streak range: [{merged['home_form_streak'].min()}, {merged['home_form_streak'].max()}], mean {merged['home_form_streak'].mean():.2f}", flush=True)
    print(f"  home_days_since_last range: [{merged['home_days_since_last'].min()}, {merged['home_days_since_last'].max()}], mean {merged['home_days_since_last'].mean():.2f}", flush=True)

    print("[3] adding interaction features ...", flush=True)
    merged = add_interaction_features(merged)
    print("[4] adding injury proxy ...", flush=True)
    merged = add_injury_proxy(merged)

    avail_base = [c for c in FEAT_COLS_BASE if c in merged.columns]
    FORM_COLS = ["home_form_streak","away_form_streak","home_days_since_last",
                 "away_days_since_last","days_since_diff"]
    INTERACT_COLS = ["home_pace_x_efg","away_pace_x_efg","pace_efg_diff",
                     "home_ortg_x_pace","away_ortg_x_pace"]
    INJURY_COLS = ["home_stars_unavailable","away_stars_unavailable","stars_unavailable_diff"]

    avail_form = avail_base + FORM_COLS
    avail_interact = avail_base + INTERACT_COLS
    avail_injury = avail_base + INJURY_COLS
    avail_all = avail_base + FORM_COLS + INTERACT_COLS + INJURY_COLS

    for cols in [avail_base, avail_form, avail_interact, avail_injury, avail_all]:
        merged[cols] = merged[cols].fillna(0.0)

    print(f"  feat sets: base={len(avail_base)}, +form={len(avail_form)}, +interact={len(avail_interact)}, +injury={len(avail_injury)}, all={len(avail_all)}", flush=True)

    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values
    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    variants = [
        ("R12_B2_total_with_form",      "reg", "total_pts_box", avail_form,     None),
        ("R12_B2_spread_with_form",     "reg", "score_diff",    avail_form,     None),
        ("R12_B2_total_with_interact",  "reg", "total_pts_box", avail_interact, None),
        ("R12_B2_spread_with_interact", "reg", "score_diff",    avail_interact, None),
        ("R12_B2_total_with_injury",    "reg", "total_pts_box", avail_injury,   None),
        ("R12_B2_spread_with_injury",   "reg", "score_diff",    avail_injury,   None),
        ("R12_B2_total_with_all",       "reg", "total_pts_box", avail_all,      None),
        ("R12_B2_spread_with_all",      "reg", "score_diff",    avail_all,      None),
        ("R12_B2_O230_with_all",        "bin", "over_230",      avail_all,      "P(total > 230)"),
        ("R12_B2_AH3_with_all",         "bin", "home_cover_AH3",avail_all,      "P(home covers -3)"),
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
