"""probe_R12_batch5_quality_opp.py — opponent-strength + home/road splits.

Adds on top of R12 B4 (112 features):
  - opp_def_adj_ortg / opp_off_adj_drtg per team (weighted by opponent strength)
  - L10_home_split_ortg / L10_road_split_ortg per team (split by venue)
  - win_quality_elo (avg Elo of teams beaten in L10)
  - cumulative_season_pace_diff_vs_prior (current season pace vs prior season)
"""
from __future__ import annotations
import json, os, time
from collections import defaultdict
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


def add_quality_features(merged: pd.DataFrame) -> pd.DataFrame:
    """For each team, compute features that depend on OPPONENT strength,
    home/road splits, and Elo-weighted wins.

    Per-team chronological history:
      th[team] = list of dicts with: date, opp_def_rtg, opp_off_rtg, opp_elo,
                                     pts_for, pts_against, is_home, won
    """
    merged = merged.reset_index(drop=True).copy()
    th = defaultdict(list)

    n = len(merged)
    LEAGUE_AVG_DEF = 113.0  # rough NBA league avg def_rtg

    # Output arrays
    out_cols = ["opp_def_adj_ortg", "opp_off_adj_drtg",
                "l10_home_ortg", "l10_road_ortg",
                "l10_home_drtg", "l10_road_drtg",
                "win_quality_elo", "n_wins_in_l10"]
    home_arrs = {k: np.zeros(n) for k in out_cols}
    away_arrs = {k: np.zeros(n) for k in out_cols}

    for idx in range(n):
        row = merged.iloc[idx]
        h, a = str(row["home_team"]), str(row["away_team"])

        # Compute features from priors for both teams
        for team_id, arr, is_home_in_current in [(h, home_arrs, True), (a, away_arrs, False)]:
            hist = th[team_id]
            if not hist:
                continue
            recent = hist[-10:]  # L10
            # opp_def_adj_ortg = mean(pts_for * (opp_def_rtg / league_avg))
            adj_ortg = np.mean([g["pts_for"] * (g.get("opp_def_rtg", LEAGUE_AVG_DEF) / LEAGUE_AVG_DEF)
                                for g in recent])
            adj_drtg = np.mean([g["pts_against"] * (g.get("opp_off_rtg", LEAGUE_AVG_DEF) / LEAGUE_AVG_DEF)
                                for g in recent])
            # Home/road splits within L10
            home_games = [g for g in recent if g["is_home"]]
            road_games = [g for g in recent if not g["is_home"]]
            arr["opp_def_adj_ortg"][idx] = adj_ortg
            arr["opp_off_adj_drtg"][idx] = adj_drtg
            arr["l10_home_ortg"][idx] = np.mean([g["pts_for"] for g in home_games]) if home_games else adj_ortg
            arr["l10_road_ortg"][idx] = np.mean([g["pts_for"] for g in road_games]) if road_games else adj_ortg
            arr["l10_home_drtg"][idx] = np.mean([g["pts_against"] for g in home_games]) if home_games else adj_drtg
            arr["l10_road_drtg"][idx] = np.mean([g["pts_against"] for g in road_games]) if road_games else adj_drtg
            # Win quality: avg Elo of teams beaten in L10
            wins = [g for g in recent if g["won"]]
            if wins:
                arr["win_quality_elo"][idx] = np.mean([g.get("opp_elo", 1500.0) for g in wins])
            else:
                arr["win_quality_elo"][idx] = 1500.0
            arr["n_wins_in_l10"][idx] = len(wins)

        # Update history for both teams with this game's outcome
        th[h].append({
            "date": row["game_date"],
            "pts_for": row["home_score"], "pts_against": row["away_score"],
            "is_home": True,
            "opp_def_rtg": row.get("away_def_rtg", LEAGUE_AVG_DEF) or LEAGUE_AVG_DEF,
            "opp_off_rtg": row.get("away_off_rtg", LEAGUE_AVG_DEF) or LEAGUE_AVG_DEF,
            "opp_elo": row.get("away_elo", 1500.0) or 1500.0,
            "won": bool(row["score_diff"] > 0),
        })
        th[a].append({
            "date": row["game_date"],
            "pts_for": row["away_score"], "pts_against": row["home_score"],
            "is_home": False,
            "opp_def_rtg": row.get("home_def_rtg", LEAGUE_AVG_DEF) or LEAGUE_AVG_DEF,
            "opp_off_rtg": row.get("home_off_rtg", LEAGUE_AVG_DEF) or LEAGUE_AVG_DEF,
            "opp_elo": row.get("home_elo", 1500.0) or 1500.0,
            "won": bool(row["score_diff"] < 0),
        })

    for k in out_cols:
        merged[f"home_{k}"] = home_arrs[k]
        merged[f"away_{k}"] = away_arrs[k]
        merged[f"{k}_diff"] = home_arrs[k] - away_arrs[k]
    return merged


# B3 features (reused)
def add_b3_features(merged: pd.DataFrame) -> pd.DataFrame:
    m = merged.copy()
    away_def = m["away_def_rtg"].replace(0, np.nan).fillna(110.0)
    home_def = m["home_def_rtg"].replace(0, np.nan).fillna(110.0)
    m["home_off_to_away_def"] = m["home_off_rtg"] / away_def
    m["away_off_to_home_def"] = m["away_off_rtg"] / home_def
    m["off_def_ratio_diff"] = m["home_off_to_away_def"] - m["away_off_to_home_def"]
    away_def_l10 = m["away_def_rtg_L10"].replace(0, np.nan).fillna(110.0)
    home_def_l10 = m["home_def_rtg_L10"].replace(0, np.nan).fillna(110.0)
    m["home_off_L10_to_away_def_L10"] = m["home_off_rtg_L10"] / away_def_l10
    m["away_off_L10_to_home_def_L10"] = m["away_off_rtg_L10"] / home_def_l10
    m["home_pace_adj_score"] = m["home_off_rtg"] * m["home_pace"] / 100.0
    m["away_pace_adj_score"] = m["away_off_rtg"] * m["away_pace"] / 100.0
    m["pace_adj_total"] = m["home_pace_adj_score"] + m["away_pace_adj_score"]
    m["pace_adj_diff"] = m["home_pace_adj_score"] - m["away_pace_adj_score"]
    m["home_pace_adj_score_L10"] = m["home_off_rtg_L10"] * m["home_pace"] / 100.0
    m["away_pace_adj_score_L10"] = m["away_off_rtg_L10"] * m["away_pace"] / 100.0
    if "season" not in m.columns:
        m["season"] = m["game_date"].astype(str).str[:7]
    for col in ["home_net_rtg","away_net_rtg","home_off_rtg","away_off_rtg",
                "home_def_rtg","away_def_rtg"]:
        if col in m.columns:
            grp = m.groupby("season")[col]
            mu = grp.transform("mean")
            sd = grp.transform("std").replace(0, np.nan).fillna(1.0)
            m[f"{col}_zsea"] = (m[col] - mu) / sd
    home_fav = (m["net_rtg_diff"] > 5).astype(int)
    home_b2b = m["home_back_to_back"].astype(int)
    home_warm = (m["home_last5_wins"] >= 3).astype(int)
    m["trap_home_signals"] = home_fav * home_b2b
    m["trap_home_overconf"] = home_fav * home_warm
    m["trap_away_motivated"] = ((m["net_rtg_diff"] < -3) & (m["away_last5_wins"] >= 3)).astype(int)
    m["trap_combo"] = m["trap_home_signals"] + m["trap_home_overconf"] + m["trap_away_motivated"]
    return m


def add_recency_features(merged: pd.DataFrame) -> pd.DataFrame:
    """B4 recency: exp_ortg, exp_drtg, l5, l3_vs_l20 z, per team + diffs."""
    merged = merged.reset_index(drop=True).copy()
    th = defaultdict(list)
    n = len(merged)
    HALFLIFE = 4.0
    LAMBDA = math.log(2) / HALFLIFE

    out_keys = ["exp_ortg","exp_drtg","l5_pts_for","l5_pts_against",
                "l3_vs_l20_pts","l3_vs_l20_def"]
    home_arrs = {k: np.zeros(n) for k in out_keys}
    away_arrs = {k: np.zeros(n) for k in out_keys}

    def _f(hist):
        if not hist: return None
        n_h = len(hist)
        pts_for = np.array([h[1] for h in hist])
        pts_aga = np.array([h[2] for h in hist])
        w = np.exp(-LAMBDA * np.arange(n_h)[::-1]); w /= w.sum()
        exp_for = float(np.sum(w * pts_for))
        exp_aga = float(np.sum(w * pts_aga))
        l5_for = float(np.mean(pts_for[-5:]))
        l5_aga = float(np.mean(pts_aga[-5:]))
        l3_for = float(np.mean(pts_for[-3:])) if n_h >= 3 else l5_for
        l3_aga = float(np.mean(pts_aga[-3:])) if n_h >= 3 else l5_aga
        l20_for = float(np.mean(pts_for[-20:])) if n_h >= 20 else float(np.mean(pts_for))
        l20_aga = float(np.mean(pts_aga[-20:])) if n_h >= 20 else float(np.mean(pts_aga))
        l20_std_for = float(np.std(pts_for[-20:])) if n_h >= 20 else float(np.std(pts_for) + 1e-6)
        l20_std_aga = float(np.std(pts_aga[-20:])) if n_h >= 20 else float(np.std(pts_aga) + 1e-6)
        return {"exp_ortg":exp_for, "exp_drtg":exp_aga,
                "l5_pts_for":l5_for, "l5_pts_against":l5_aga,
                "l3_vs_l20_pts":(l3_for - l20_for)/max(l20_std_for, 1e-6),
                "l3_vs_l20_def":(l3_aga - l20_aga)/max(l20_std_aga, 1e-6)}

    for idx in range(n):
        row = merged.iloc[idx]
        h, a = str(row["home_team"]), str(row["away_team"])
        hf, af = _f(th[h]), _f(th[a])
        if hf:
            for k, v in hf.items(): home_arrs[k][idx] = v
        if af:
            for k, v in af.items(): away_arrs[k][idx] = v
        th[h].append((row["game_date"], row["home_score"], row["away_score"]))
        th[a].append((row["game_date"], row["away_score"], row["home_score"]))

    for k in out_keys:
        merged[f"home_{k}"] = home_arrs[k]
        merged[f"away_{k}"] = away_arrs[k]
        merged[f"{k}_diff"] = home_arrs[k] - away_arrs[k]
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


def wf_reg(merged, label, naive_pred, fc, name):
    y = merged[label].astype(float).values
    n = len(merged); fs = n // 4
    folds, aa, al, an = [], [], [], []
    for fi in range(4):
        ts = fi * fs; te = (fi + 1) * fs if fi < 3 else n
        tr, ti = list(range(0, ts)), list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20: continue
        X_tr = merged[fc].iloc[tr].values; X_te = merged[fc].iloc[ti].values
        l, x = _fit_ens_reg(X_tr, y[tr])
        pred = 0.5*l.predict(X_te) + 0.5*x.predict(X_te)
        nv = naive_pred[ti]
        lm = float(np.mean(np.abs(pred - y[ti])))
        nm = float(np.mean(np.abs(nv - y[ti])))
        d = lm - nm; dp = d / nm * 100
        folds.append({"fold":fi,"naive_mae":round(nm,4),"lgb_mae":round(lm,4),
                      "delta":round(d,4),"delta_pct":round(dp,2)})
        aa.extend(y[ti].tolist()); al.extend(pred.tolist()); an.extend(nv.tolist())
    pn = float(np.mean(np.abs(np.array(an)-np.array(aa))))
    pl = float(np.mean(np.abs(np.array(al)-np.array(aa))))
    dp = (pl-pn)/pn*100
    nv = len(folds); np_ = sum(1 for f in folds if f["delta"] < 0)
    ship = (nv >= 3) and (np_ == nv) and (dp <= -5.0)
    return {"probe":name,"kind":"regression","label":label,"n_features":len(fc),
            "status":"SHIP" if ship else "REJECT",
            "ship_reason":f"WF {np_}/{nv}, delta {dp:+.2f}%",
            "pooled_naive_mae":round(pn,4),"pooled_lgb_mae":round(pl,4),
            "pooled_delta_pct":round(dp,2),
            "n_folds_positive":np_,"n_valid_folds":nv,"fold_results":folds}


def wf_bin(merged, label, naive_pred, fc, name, desc):
    from sklearn.metrics import brier_score_loss, accuracy_score, roc_auc_score
    y = merged[label].astype(int).values
    n = len(merged); fs = n // 4
    folds, aa, al, an = [], [], [], []
    for fi in range(4):
        ts = fi * fs; te = (fi + 1) * fs if fi < 3 else n
        tr, ti = list(range(0, ts)), list(range(ts, te))
        if len(tr) < 50 or len(ti) < 20: continue
        X_tr = merged[fc].iloc[tr].values; X_te = merged[fc].iloc[ti].values
        l, x = _fit_ens_clf(X_tr, y[tr])
        pred = 0.5*l.predict_proba(X_te)[:,1] + 0.5*x.predict_proba(X_te)[:,1]
        nv = naive_pred[ti]
        folds.append({"fold":fi,"naive_brier":round(brier_score_loss(y[ti],nv),5),
                      "lgb_brier":round(brier_score_loss(y[ti],pred),5)})
        aa.extend(y[ti].tolist()); al.extend(pred.tolist()); an.extend(nv.tolist())
    pnb = float(brier_score_loss(aa, an)); plb = float(brier_score_loss(aa, al))
    try: plu = float(roc_auc_score(aa, al))
    except: plu = float("nan")
    bdp = (plb-pnb)/pnb*100
    nv_ = len(folds)
    ship = ((plb <= pnb*0.95) or (plu >= 0.60)) and nv_ >= 3
    return {"probe":name,"kind":"binary","label":label,"label_desc":desc,
            "n_features":len(fc),
            "status":"SHIP" if ship else "REJECT",
            "ship_reason":f"Brier {plb:.4f} ({bdp:+.2f}%); AUC {plu:.4f}",
            "n_games":int(len(merged)),"pos_rate":float(np.mean(y)),
            "pooled_lgb_brier":round(plb,5),"pooled_naive_brier":round(pnb,5),
            "pooled_lgb_auc":round(plu,5),"brier_delta_pct":round(bdp,3),
            "n_valid_folds":nv_,"fold_results":folds}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-5 — opp-strength + home/road splits + win quality", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    print("[2] adding B3 features (cross + pace + z + trap) ...", flush=True)
    merged = add_b3_features(merged)
    print("[3] adding B4 recency features ...", flush=True)
    merged = add_recency_features(merged)
    print("[4] adding B5 quality+opp features ...", flush=True)
    merged = add_quality_features(merged)

    base = [c for c in FEAT_COLS_BASE if c in merged.columns]
    B3_COLS = ["home_off_to_away_def","away_off_to_home_def","off_def_ratio_diff",
               "home_off_L10_to_away_def_L10","away_off_L10_to_home_def_L10",
               "home_pace_adj_score","away_pace_adj_score","pace_adj_total",
               "pace_adj_diff","home_pace_adj_score_L10","away_pace_adj_score_L10",
               "trap_home_signals","trap_home_overconf","trap_away_motivated","trap_combo"]
    Z_COLS = [c for c in merged.columns if c.endswith("_zsea")]
    B4_COLS = []
    for prefix in ["home_","away_"]:
        for k in ["exp_ortg","exp_drtg","l5_pts_for","l5_pts_against",
                 "l3_vs_l20_pts","l3_vs_l20_def"]:
            B4_COLS.append(f"{prefix}{k}")
    for k in ["exp_ortg","exp_drtg","l5_pts_for","l5_pts_against",
              "l3_vs_l20_pts","l3_vs_l20_def"]:
        B4_COLS.append(f"{k}_diff")
    B5_COLS = []
    for prefix in ["home_","away_"]:
        for k in ["opp_def_adj_ortg","opp_off_adj_drtg","l10_home_ortg",
                  "l10_road_ortg","l10_home_drtg","l10_road_drtg",
                  "win_quality_elo","n_wins_in_l10"]:
            B5_COLS.append(f"{prefix}{k}")
    for k in ["opp_def_adj_ortg","opp_off_adj_drtg","l10_home_ortg","l10_road_ortg",
              "l10_home_drtg","l10_road_drtg","win_quality_elo","n_wins_in_l10"]:
        B5_COLS.append(f"{k}_diff")

    avail_b4 = base + B3_COLS + Z_COLS + B4_COLS
    avail_b5 = avail_b4 + B5_COLS

    for cols in [avail_b4, avail_b5]:
        cols_present = [c for c in cols if c in merged.columns]
        merged[cols_present] = merged[cols_present].fillna(0.0)

    avail_b4 = [c for c in avail_b4 if c in merged.columns]
    avail_b5 = [c for c in avail_b5 if c in merged.columns]
    print(f"  feat sets: b4={len(avail_b4)} (baseline), b5={len(avail_b5)} (with quality+opp)", flush=True)

    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values
    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    variants = [
        ("R12_B5_total_with_quality",    "reg", "total_pts_box", avail_b5, None),
        ("R12_B5_spread_with_quality",   "reg", "score_diff",    avail_b5, None),
        ("R12_B5_home_pts_quality",      "reg", "home_score",    avail_b5, None),
        ("R12_B5_away_pts_quality",      "reg", "away_score",    avail_b5, None),
        ("R12_B5_O230_quality",          "bin", "over_230",      avail_b5, "P(total > 230)"),
        ("R12_B5_AH3_quality",           "bin", "home_cover_AH3",avail_b5, "P(home covers -3)"),
    ]

    results = {}
    for name, kind, label, fc, desc in variants:
        t_v = time.time()
        if kind == "reg":
            out = wf_reg(merged, label, naive_l5_mean(label), fc, name)
        else:
            out = wf_bin(merged, label, naive_l5_prop(label), fc, name, desc)
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
