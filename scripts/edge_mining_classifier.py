"""Edge-mining analysis (b): calibrated P(bet-wins) CLASSIFIER, anti-overfit.

Train on MAIN EARLY half only. Predict bet-win prob. Bet the high-confidence
picks on the HELD-OUT MAIN LATE half. Then re-grade the FROZEN model on the
2024-25 SEASON corpus and the diff-scrape 2025-26 corpus. If the classifier's
edge vanishes cross-season, it is overfit -> say so.

Features per bet (all leak-free, known pregame):
  edge=pred-line, abs_edge, pred, line, stat one-hot, line_bucket,
  l10_min, rest_days, is_home, opp_pace(stale-2024-25 proxy), opp_def_rtg,
  bet_over flag.
Label = won (at actual odds). Bet side already = sign(pred-line).

Reports ROI of (i) all classifier-selected bets and (ii) top-confidence decile,
on the held-out late half AND each external corpus. |odds|>=100 already applied.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_BETS = _ROOT / "data" / "cache" / "edge_mining_bets.parquet"
_OUT = _ROOT / "data" / "cache" / "edge_mining_classifier.json"

MAIN, SEASON, DIFFSCR = "benashkar_2526", "oddsapi_2425", "oddsapi_2526reg"
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def featurize(df):
    df = df.copy()
    X = pd.DataFrame(index=df.index)
    X["edge"] = df["edge"]
    X["abs_edge"] = df["abs_edge"]
    X["pred"] = df["pred"]
    X["line"] = df["line"]
    X["l10_min"] = df["l10_min"].fillna(df["l10_min"].median())
    X["rest_days"] = df["rest_days"].fillna(2)
    X["is_home"] = df["is_home"].fillna(0.5)
    X["opp_pace"] = df["opp_pace"].fillna(df["opp_pace"].median())
    X["opp_def_rtg"] = df["opp_def_rtg"].fillna(df["opp_def_rtg"].median())
    X["bet_over"] = df["bet_over"].astype(float)
    for s in STATS:
        X[f"stat_{s}"] = (df["stat"] == s).astype(float)
    return X


def roi(sub):
    n = len(sub)
    if n == 0:
        return {"n": 0, "roi": np.nan, "win": np.nan}
    return {"n": int(n), "roi": round(float(sub["pnl"].mean()), 2),
            "win": round(float(sub["won"].mean() * 100), 1)}


def grade_selected(df, p, thresh):
    sel = df[p >= thresh]
    return roi(sel)


def main():
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        HAVE_GBM = True
    except Exception:
        HAVE_GBM = False

    bt = pd.read_parquet(_BETS)
    main = bt[bt.corpus == MAIN].copy().sort_values("gd").reset_index(drop=True)
    season = bt[bt.corpus == SEASON].copy()
    diffscr = bt[bt.corpus == DIFFSCR].copy()

    cut = pd.to_datetime(main["gd"]).quantile(0.5)
    dts = pd.to_datetime(main["gd"])
    early = main[dts <= cut].copy()
    late = main[dts > cut].copy()

    Xe, ye = featurize(early), early["won"].values
    Xl = featurize(late)
    Xs = featurize(season)
    Xd = featurize(diffscr)

    report = {"meta": {"early_n": len(early), "late_n": len(late),
                       "season_n": len(season), "diffscr_n": len(diffscr),
                       "feature_cols": list(Xe.columns)}}

    for name, build in [("logistic", "lr"), ("gbm", "gbm")]:
        if build == "gbm" and not HAVE_GBM:
            continue
        if build == "lr":
            sc = StandardScaler().fit(Xe.values)
            clf = LogisticRegression(max_iter=2000, C=0.5)
            clf.fit(sc.transform(Xe.values), ye)
            pe = clf.predict_proba(sc.transform(Xe.values))[:, 1]
            pl = clf.predict_proba(sc.transform(Xl.values))[:, 1]
            ps = clf.predict_proba(sc.transform(Xs.values))[:, 1]
            pd_ = clf.predict_proba(sc.transform(Xd.values))[:, 1]
        else:
            clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200,
                                                 learning_rate=0.05,
                                                 min_samples_leaf=60,
                                                 l2_regularization=1.0)
            clf.fit(Xe.values, ye)
            pe = clf.predict_proba(Xe.values)[:, 1]
            pl = clf.predict_proba(Xl.values)[:, 1]
            ps = clf.predict_proba(Xs.values)[:, 1]
            pd_ = clf.predict_proba(Xd.values)[:, 1]

        res = {}
        # in-sample sanity (early)
        res["early_insample_all_p>0.5"] = grade_selected(early, pe, 0.5)
        # held-out late: a few confidence thresholds
        for th in [0.5, 0.52, 0.55]:
            res[f"late_p>={th}"] = grade_selected(late, pl, th)
        # top decile by confidence on late
        if len(late):
            q90 = np.quantile(pl, 0.90)
            res["late_top10pct"] = grade_selected(late, pl, q90)
            q75 = np.quantile(pl, 0.75)
            res["late_top25pct"] = grade_selected(late, pl, q75)
        # FROZEN cross-season + diff-scrape at the same 0.52 conf
        res["season2425_p>=0.52"] = grade_selected(season, ps, 0.52)
        res["season2425_p>=0.55"] = grade_selected(season, ps, 0.55)
        res["diffscr2526_p>=0.52"] = grade_selected(diffscr, pd_, 0.52)
        # FROZEN cross-season top quartile (using late's threshold for fairness)
        if len(late):
            res["season2425_top25pct_lateq"] = grade_selected(season, ps, q75)
            res["diffscr2526_top25pct_lateq"] = grade_selected(diffscr, pd_, q75)
        report[name] = res

        print(f"\n=== {name.upper()} classifier ===")
        print(f"  early in-sample (p>0.5): {res['early_insample_all_p>0.5']}")
        print(f"  HELD-OUT late p>=0.52  : {res['late_p>=0.52']}")
        print(f"  HELD-OUT late p>=0.55  : {res['late_p>=0.55']}")
        print(f"  HELD-OUT late top10%   : {res['late_top10pct']}")
        print(f"  HELD-OUT late top25%   : {res['late_top25pct']}")
        print(f"  FROZEN season2425 p>=.52: {res['season2425_p>=0.52']}")
        print(f"  FROZEN season2425 p>=.55: {res['season2425_p>=0.55']}")
        print(f"  FROZEN diffscr   p>=.52 : {res['diffscr2526_p>=0.52']}")
        print(f"  FROZEN season2425 top25%: {res['season2425_top25pct_lateq']}")
        print(f"  FROZEN diffscr   top25% : {res['diffscr2526_top25pct_lateq']}")

        # What does the model lean on? (does it just learn 'bet AST'?)
        if build == "lr":
            coefs = sorted(zip(Xe.columns, clf.coef_[0]), key=lambda kv: -abs(kv[1]))
            report[name + "_coefs"] = {k: round(float(v), 3) for k, v in coefs}
            print("  top coefs:", [(k, round(float(v), 2)) for k, v in coefs[:6]])
        # fraction of selected late picks that are AST
        if len(late):
            sel = late[pl >= q75]
            if len(sel):
                frac_ast = (sel["stat"] == "ast").mean()
                report[name + "_late_top25_ast_frac"] = round(float(frac_ast), 3)
                print(f"  late top25% picks that are AST: {frac_ast*100:.0f}%")

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(_OUT, "w"), indent=2, default=str)
    print(f"\nsaved -> {_OUT.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
