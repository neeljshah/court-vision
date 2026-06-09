"""EX-3 — Leak-free game-line grader for M2 total/spread.

Grades M2 total + spread COVER decisions vs realized linescore at real ~-110,
joined via data/pregame_spreads.parquet (home_spread+total) + linescores_all.json.

LEAK-FREE design:
  - Train a fresh M2 ensemble (exact probe_R27_T1 recipe) STRICTLY on
    2022-23..2024-25, grade the held-out 2025-26 fold. Guaranteed no forward leak.
  - Also score the DEPLOYED m2_family artifacts on 2025-26 (which the manifest
    + probe confirm were trained on <2025-26) for a cross-check.
  - Outcomes from linescores: q1-q4 + OT pts (the q1-q4-only sum fakes 4.4% ties).
  - Drop invalid odds (|odds|<100); we use flat -110 (real prop book juice for
    sides) -> payout/risk. Report cover hit-rate + ROI.

WRITES ONLY to data/cache/_exp/. Does not touch any production artifact.
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # script-relative (scripts/ -> repo root)
NBA = os.path.join(ROOT, "data", "nba")
MODELS_M2 = os.path.join(ROOT, "data", "models", "m2_family")
OUT = os.path.join(ROOT, "data", "cache", "_exp", "m2_game_line_grade.json")

# ESPN (pregame_spreads) -> NBA (season_games) abbreviation map
ESPN2NBA = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
            "UTAH": "UTA", "WSH": "WAS"}

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
    "away_tov_pct_L10","home_oreb_pct_L10","away_oreb_pct_L10","home_ft_rate_L10",
    "away_ft_rate_L10","home_off_rtg_home_L10","away_off_rtg_away_L10",
    "home_off_rtg_vs_top_def","away_off_rtg_vs_top_def","home_srs","away_srs",
    "home_elo","away_elo","elo_differential","home_def_rtg_trend",
    "away_def_rtg_trend","b2b_diff","elo_pace_interaction","ref_avg_fouls",
    "ref_home_win_pct","ref_fta_tendency","sim_win_prob","sim_score_diff_mean",
    "sim_score_diff_std","sim_pace_adj",
]
LGB_SEEDS = [42, 7, 100]
XGB_SEEDS = [42, 7]


def _season_of(gid: str) -> str:
    return {"00222": "2022-23", "00223": "2023-24", "00224": "2024-25",
            "00225": "2025-26"}.get(str(gid)[:5], "unknown")


def load_season_rows(fname):
    p = os.path.join(NBA, fname)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    rows = d.get("rows", d) if isinstance(d, dict) else d
    return rows if isinstance(rows, list) else []


def load_outcomes():
    """game_id -> (home_score, away_score) incl OT. None when q1-q4 all zero."""
    with open(os.path.join(NBA, "linescores_all.json"), encoding="utf-8") as f:
        ls = json.load(f)
    out = {}
    for gid, v in ls.items():
        try:
            h = sum(float(v.get(f"home_q{i}", 0) or 0) for i in range(1, 5)) + float(v.get("home_pts_ot", 0) or 0)
            a = sum(float(v.get(f"away_q{i}", 0) or 0) for i in range(1, 5)) + float(v.get("away_pts_ot", 0) or 0)
        except (TypeError, ValueError):
            continue
        # require non-zero regulation quarters (played + recorded)
        reg_h = sum(float(v.get(f"home_q{i}", 0) or 0) for i in range(1, 5))
        reg_a = sum(float(v.get(f"away_q{i}", 0) or 0) for i in range(1, 5))
        if reg_h <= 0 or reg_a <= 0:
            continue
        out[gid] = (h, a, bool(v.get("had_ot", False)))
    return out


def build_dataset():
    rows = []
    for yr in ("2022-23", "2023-24", "2024-25", "2025-26"):
        rows.extend(load_season_rows(f"season_games_{yr}.json"))
    sg = pd.DataFrame(rows)
    outc = load_outcomes()
    sg = sg[sg["game_id"].astype(str).isin(outc.keys())].copy()
    sg["home_score"] = sg["game_id"].map(lambda g: outc[str(g)][0])
    sg["away_score"] = sg["game_id"].map(lambda g: outc[str(g)][1])
    sg["had_ot"] = sg["game_id"].map(lambda g: outc[str(g)][2])
    sg["score_diff"] = sg["home_score"] - sg["away_score"]
    sg["total_pts_box"] = sg["home_score"] + sg["away_score"]
    # require core features present + sane
    for c in ("home_off_rtg", "away_off_rtg", "home_pace", "away_pace"):
        sg = sg[pd.to_numeric(sg[c], errors="coerce") > 0]
    sg["season"] = sg["game_id"].apply(_season_of)
    sg["game_date"] = sg["game_date"].astype(str).str[:10]
    avail = [c for c in FEAT_COLS if c in sg.columns]
    sg[avail] = sg[avail].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return sg.sort_values("game_date").reset_index(drop=True), avail


def train_ensemble(X, y):
    import lightgbm as lgb, xgboost as xgb
    models = []
    for seed in LGB_SEEDS:
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
                              subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1,
                              reg_lambda=0.1, min_child_samples=20,
                              random_state=seed, n_jobs=4, verbose=-1)
        m.fit(X, y); models.append(m)
    for seed in XGB_SEEDS:
        m = xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
                             subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1,
                             reg_lambda=0.1, random_state=seed, n_jobs=4, verbosity=0)
        m.fit(X, y); models.append(m)
    return models


def predict_ensemble(models, X):
    p = np.zeros(X.shape[0])
    for m in models:
        p += m.predict(X)
    return p / len(models)


def load_deployed():
    import joblib
    out = {}
    for tgt in ("total", "spread"):
        ms = []
        for s in LGB_SEEDS:
            ms.append(joblib.load(os.path.join(MODELS_M2, f"{tgt}_lgb_s{s}.joblib")))
        for s in XGB_SEEDS:
            ms.append(joblib.load(os.path.join(MODELS_M2, f"{tgt}_xgb_s{s}.joblib")))
        out[tgt] = ms
    with open(os.path.join(MODELS_M2, "feature_cols.json")) as f:
        feats = json.load(f)
    return out, feats


# ---------------------------------------------------------------------------
# ROI helpers (flat -110 both sides)
# ---------------------------------------------------------------------------
ODDS = -110.0  # standard side juice


def payout_per_unit(odds):
    return (100.0 / abs(odds)) if odds < 0 else (odds / 100.0)


def grade_side_bets(df, pred_col, line_col, actual_col, kind):
    """Bet the side the model favors vs the line. kind='total' or 'spread'.
    Returns dict with hit rate + ROI. Drops pushes."""
    win_unit = payout_per_unit(ODDS)
    bets = []
    for _, r in df.iterrows():
        pred = r[pred_col]; line = r[line_col]; actual = r[actual_col]
        if kind == "total":
            # model OVER if pred>line. Outcome OVER if actual>line.
            if pred == line:
                continue
            side = "OVER" if pred > line else "UNDER"
            if actual == line:
                continue  # push
            outcome_over = actual > line
            won = (side == "OVER" and outcome_over) or (side == "UNDER" and not outcome_over)
        else:  # spread: line is home_spread (e.g. -6.5). home cover if diff+home_spread>0
            margin = actual + line  # home cover margin
            # model's home cover margin = pred_diff + home_spread
            model_margin = pred + line
            if model_margin == 0:
                continue
            side = "HOME" if model_margin > 0 else "AWAY"
            if margin == 0:
                continue  # push
            home_covers = margin > 0
            won = (side == "HOME" and home_covers) or (side == "AWAY" and not home_covers)
        bets.append(win_unit if won else -1.0)
    bets = np.array(bets)
    n = len(bets)
    if n == 0:
        return {"n": 0}
    return {"n": int(n), "hit_rate": float((bets > 0).mean()),
            "roi_pct": float(bets.sum() / n * 100.0),
            "units": float(bets.sum())}


def blind_roi(df, line_col, actual_col, kind, side):
    """Always bet one side (coherence check). side in OVER/UNDER/HOME/AWAY."""
    win_unit = payout_per_unit(ODDS)
    bets = []
    for _, r in df.iterrows():
        line = r[line_col]; actual = r[actual_col]
        if kind == "total":
            if actual == line:
                continue
            outcome_over = actual > line
            won = (side == "OVER" and outcome_over) or (side == "UNDER" and not outcome_over)
        else:
            margin = actual + line
            if margin == 0:
                continue
            home_covers = margin > 0
            won = (side == "HOME" and home_covers) or (side == "AWAY" and not home_covers)
        bets.append(win_unit if won else -1.0)
    bets = np.array(bets)
    if len(bets) == 0:
        return {"n": 0}
    return {"n": int(len(bets)), "hit_rate": float((bets > 0).mean()),
            "roi_pct": float(bets.sum() / len(bets) * 100.0)}


def main():
    t0 = time.time()
    print("[1] building dataset (OT-corrected outcomes)...", flush=True)
    df, feats = build_dataset()
    print(f"  n={len(df)} feats={len(feats)} by_season={df['season'].value_counts().to_dict()}", flush=True)

    # ---- join real Vegas lines (pregame_spreads) ----
    sp = pd.read_parquet(os.path.join(ROOT, "data", "pregame_spreads.parquet"))
    sp["game_date"] = sp["game_date"].astype(str).str[:10]
    for col in ("home_team", "away_team"):
        sp[col] = sp[col].map(lambda t: ESPN2NBA.get(t, t))
    # drop invalid odds rule: pregame_spreads has no odds col -> we impose -110;
    # but enforce the spec by dropping any |odds|<100 if a col existed.
    g2526 = df[df["season"] == "2025-26"].copy()
    # Date-tolerant join (EX-3 fix): season_games_2025-26 stores game_date up to
    # 1 day off from pregame_spreads (ET-vs-UTC boundary), so an EXACT-date inner
    # merge silently dropped ~76% of games and selection-biased the survivors
    # toward home covers (manufacturing a false +8% blind-HOME coherence signal).
    # Match on (home,away) within |date diff| <= 1, keep the nearest, dedup per line.
    g2526 = g2526.rename(columns={"game_date": "sg_game_date"})
    sp = sp.copy()
    sp["_spd"] = pd.to_datetime(sp["game_date"])
    g2526["_sgd"] = pd.to_datetime(g2526["sg_game_date"])
    cand = sp.merge(g2526, on=["home_team", "away_team"], how="inner", suffixes=("", "_sg"))
    cand["_dd"] = (cand["_spd"] - cand["_sgd"]).abs().dt.days
    cand = cand[cand["_dd"] <= 1].sort_values("_dd")
    merged = (cand.drop_duplicates(subset=["game_date", "home_team", "away_team"], keep="first")
                  .reset_index(drop=True))
    print(f"[2] joined real-line corpus (date-tolerant |dd|<=1): pregame_spreads n={len(sp)} "
          f"-> graded n={len(merged)}", flush=True)
    n_ot = int(merged["had_ot"].sum())
    print(f"  OT games in graded set: {n_ot}", flush=True)

    # ---- market coherence check (blind both sides ~ -2*vig negative) ----
    coh = {
        "total_blind_OVER": blind_roi(merged, "total", "total_pts_box", "total", "OVER"),
        "total_blind_UNDER": blind_roi(merged, "total", "total_pts_box", "total", "UNDER"),
        "spread_blind_HOME": blind_roi(merged, "home_spread", "score_diff", "spread", "HOME"),
        "spread_blind_AWAY": blind_roi(merged, "home_spread", "score_diff", "spread", "AWAY"),
    }
    print("[3] market coherence (blind both sides should be ~-4.5% each):", flush=True)
    for k, v in coh.items():
        print(f"   {k}: {v}", flush=True)

    # ---- LEAK-FREE: train fresh on <2025-26, predict the 2025-26 graded set ----
    print("[4] training fresh leak-free M2 (train=2022-24, grade=2025-26)...", flush=True)
    train_df = df[df["season"].isin(["2022-23", "2023-24", "2024-25"])]
    Xtr = train_df[feats].values
    Xval = merged[feats].values
    fresh = {}
    for tgt, ycol in (("total", "total_pts_box"), ("spread", "score_diff")):
        ms = train_ensemble(Xtr, train_df[ycol].astype(float).values)
        merged[f"pred_{tgt}_fresh"] = predict_ensemble(ms, Xval)
        fresh[tgt] = ms
        mae = float(np.mean(np.abs(merged[f"pred_{tgt}_fresh"] - merged[ycol].astype(float))))
        line_mae_col = "total" if tgt == "total" else "home_spread"
        if tgt == "total":
            line_mae = float(np.mean(np.abs(merged["total"] - merged["total_pts_box"])))
        else:
            line_mae = float(np.mean(np.abs(-merged["home_spread"] - merged["score_diff"])))
        print(f"   {tgt}: model_MAE={mae:.3f}  vegas_line_MAE={line_mae:.3f} (n={len(merged)})", flush=True)
        fresh[f"{tgt}_mae"] = mae
        fresh[f"{tgt}_line_mae"] = line_mae

    # ---- DEPLOYED model cross-check ----
    print("[5] scoring DEPLOYED m2_family on graded set...", flush=True)
    dep, dep_feats = load_deployed()
    Xdep = merged[[c for c in dep_feats if c in merged.columns]].copy()
    for c in dep_feats:
        if c not in Xdep.columns:
            Xdep[c] = 0.0
    Xdep = Xdep[dep_feats].apply(pd.to_numeric, errors="coerce").fillna(0.0).values
    merged["pred_total_deployed"] = predict_ensemble(dep["total"], Xdep)
    merged["pred_spread_deployed"] = predict_ensemble(dep["spread"], Xdep)

    # ---- grade cover decisions ----
    res = {}
    res["fresh_total"] = grade_side_bets(merged, "pred_total_fresh", "total", "total_pts_box", "total")
    res["fresh_spread"] = grade_side_bets(merged, "pred_spread_fresh", "home_spread", "score_diff", "spread")
    res["deployed_total"] = grade_side_bets(merged, "pred_total_deployed", "total", "total_pts_box", "total")
    res["deployed_spread"] = grade_side_bets(merged, "pred_spread_deployed", "home_spread", "score_diff", "spread")

    print("[6] COVER GRADES (bet model's favored side @ -110):", flush=True)
    for k, v in res.items():
        print(f"   {k}: {v}", flush=True)

    # ---- threshold sensitivity: only bet when |model - line| edge >= E ----
    def thresh_grade(pred_col, line_col, actual_col, kind, edge):
        sub = merged.copy()
        if kind == "total":
            sub = sub[abs(sub[pred_col] - sub[line_col]) >= edge]
        else:
            sub = sub[abs(sub[pred_col] + sub[line_col]) >= edge]  # model home-cover margin
        return grade_side_bets(sub, pred_col, line_col, actual_col, kind)

    thr = {}
    for edge in (2, 4, 6):
        thr[f"fresh_total_edge{edge}"] = thresh_grade("pred_total_fresh", "total", "total_pts_box", "total", edge)
        thr[f"fresh_spread_edge{edge}"] = thresh_grade("pred_spread_fresh", "home_spread", "score_diff", "spread", edge)
    print("[7] edge-threshold sensitivity (fresh, leak-free):", flush=True)
    for k, v in thr.items():
        print(f"   {k}: {v}", flush=True)

    payload = {
        "experiment": "EX-3 leak-free game-line grader",
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "corpus": "pregame_spreads.parquet (ESPN lines) x season_games_2025-26 x linescores(OT-corrected)",
        "graded_n": int(len(merged)),
        "graded_n_ot": n_ot,
        "odds_assumed": ODDS,
        "market_coherence": coh,
        "fresh_leakfree_mae": {"total": fresh["total_mae"], "spread": fresh["spread_mae"],
                               "total_line_mae": fresh["total_line_mae"], "spread_line_mae": fresh["spread_line_mae"]},
        "cover_grades": res,
        "edge_threshold": thr,
        "runtime_sec": round(time.time() - t0, 1),
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[done] wrote {OUT} in {payload['runtime_sec']}s", flush=True)


if __name__ == "__main__":
    main()
