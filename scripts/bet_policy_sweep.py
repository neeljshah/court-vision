"""bet_policy_sweep.py -- find the per-stat edge thresholds that are robust on
BOTH temporal halves under the calibrated REB+AST(+FG3M) policy.

Builds on scripts/betting_policy_validation.py. That harness proved REB+AST
without filters is held-out +3.82%; this one sweeps the edge threshold per
stat and keeps only the threshold whose ROI is positive in BOTH the early
and late halves -- the same robustness bar that ruled out AST-only.

Why this matters
----------------
scripts/run_gate1_full_analysis already showed REB is positive at edge>=1.0
(+5.46%) and edge>=1.5 (+9.08%) over the full 2025-26 sample. But the shipped
CV_BET_POLICY=reb_ast is a stat ALLOWLIST -- it doesn't enforce per-stat
margin thresholds. Adding those thresholds is one of the cheapest ways to lift
ROI, but only if the threshold itself doesn't overfit to a single half.

Policy options compared on the held-out late half (mid-of-2025-26 split):
  base   : raw pred, bet every edge
  cal    : calibrated point-blend (the shipped per-stat weights), bet every edge
  cal+t  : cal + per-stat edge >= threshold(stat); thresholds swept
The winner is the (stat -> threshold) map whose late-half ROI is positive AND
whose early-half ROI is also positive at the SAME thresholds.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import xgboost as xgb

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import (  # noqa: E402
    load_benashkar_bets, attach_actuals_and_l10, attach_oof, settle)

FRAME = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
COVS = ["pred", "l3_min", "l5_min", "l10_min", "std_min", "prev_min", "min_trend",
        "rest_days", "is_b2b", "is_home", "opp_pace", "opp_def",
        "vac_min", "vac_pts", "n_out", "l5_pts_pm", "l5_reb_pm",
        "month", "days_into_season"]
BLEND = {"pts": 1.0, "reb": 0.5, "fg3m": 0.5, "ast": 0.0}
THR_GRID = (0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)


def train_calmap(early_df: pd.DataFrame):
    cm: dict[tuple, float] = {}
    for stat in ("pts", "reb", "fg3m", "ast"):
        s_tr = early_df[early_df["stat"] == stat].dropna(subset=COVS + ["actual"])
        if len(s_tr) < 500:
            continue
        p = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
             "subsample": 0.8, "colsample_bytree": 0.8,
             "device": "cuda", "tree_method": "hist"}
        try:
            b = xgb.train(p, xgb.DMatrix(s_tr[COVS], label=s_tr["actual"]),
                          num_boost_round=450)
        except xgb.core.XGBoostError:
            p["device"] = "cpu"
            b = xgb.train(p, xgb.DMatrix(s_tr[COVS], label=s_tr["actual"]),
                          num_boost_round=450)
        s_te = early_df[early_df["stat"] == stat]  # used for join, not for eval here
        # Will fold both halves below; just train and predict on demand.
        cm[(stat, "model")] = b
    return cm


def _cal_pred(b, model_cache, frame_idx):
    base = b["pred_oof"]
    booster = model_cache.get((b["stat"], "model"))
    cov_row = frame_idx.get((b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["stat"]))
    if booster is None or cov_row is None:
        return base
    row = pd.DataFrame([{"pred": base, **cov_row}])
    try:
        cal = float(booster.predict(xgb.DMatrix(row[COVS]))[0])
    except Exception:
        return base
    a = BLEND.get(b["stat"], 0.0)
    return a * cal + (1 - a) * base


def per_stat_roi(bets, predfn, stats=None, thresholds=None):
    """ROI per stat with optional per-stat edge thresholds (stat -> min |pred-line|)."""
    per = defaultdict(lambda: [0, 0, 0.0])  # n, w, pnl
    for b in bets:
        if stats and b["stat"] not in stats:
            continue
        pred = predfn(b)
        if thresholds is not None:
            thr = thresholds.get(b["stat"], 0.0)
            if abs(pred - b["line"]) < thr:
                continue
        res = settle(b, pred)
        if res is None:
            continue
        per[b["stat"]][0] += 1
        per[b["stat"]][1] += int(res[1])
        per[b["stat"]][2] += res[2]
    return {s: (n, w, pl / (n * 100) * 100 if n else 0.0)
            for s, (n, w, pl) in per.items()}


def total(rows):
    n = sum(v[0] for v in rows.values())
    pl = sum(v[2] * v[0] / 100 * 100 for v in rows.values())  # pl already in %, restore $
    # simpler: per_stat_roi gives ROI%, so reconstruct dollars: pnl_dollars = roi*n
    n2 = w2 = 0; dollars = 0.0
    for (st, (n, w, r)) in rows.items():
        n2 += n; w2 += w; dollars += r * n  # r is %, n is count, sum gives summed %-points
    return n2, (dollars / n2 if n2 else 0.0), w2


def main():
    frame = pd.read_parquet(FRAME).dropna(subset=["opp_pace", "opp_def"])
    raw = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    bets = sorted(raw, key=lambda b: b["gdate"])
    mid = bets[len(bets) // 2]["gdate"]
    early = [b for b in bets if b["gdate"] < mid]
    late = [b for b in bets if b["gdate"] >= mid]
    print(f"early n={len(early):,}   late n={len(late):,}")

    # train calibrator on early-half ONLY
    early_df = frame[frame["date"] < mid.strftime("%Y-%m-%d")]
    cm = train_calmap(early_df)
    # cache covariate rows once for fast lookup
    frame_idx: dict[tuple, dict] = {}
    for r in frame.itertuples(index=False):
        frame_idx[(int(r.player_id), r.date, r.stat)] = {c: getattr(r, c) for c in COVS}
    predfn = lambda b: _cal_pred(b, cm, frame_idx)  # noqa: E731

    # ---- Headline: per-stat ROI under various stat allowlists, no threshold
    print("\n== Baseline (calibrated, NO threshold) ==")
    for label, sts in (("ALL", None),
                       ("REB+AST", {"reb", "ast"}),
                       ("REB+AST+FG3M", {"reb", "ast", "fg3m"})):
        ear = per_stat_roi(early, predfn, stats=sts)
        lat = per_stat_roi(late, predfn, stats=sts)
        ne, re_, _ = total(ear); nl, rl, _ = total(lat)
        print(f"  {label:<14} early n={ne:,}  ROI={re_:+.2f}%   "
              f"late n={nl:,}  ROI={rl:+.2f}%")

    # ---- Per-stat threshold sweep: pick the threshold that is positive in BOTH
    # halves and maximises late-half ROI on REB and AST (the two policy stats).
    print("\n== Per-stat threshold sweep (calibrated; positive-in-BOTH bar) ==")
    best: dict[str, tuple[float, int, float, int, float]] = {}
    for stat in ("ast", "reb", "fg3m", "pts"):
        print(f"\n  -- {stat.upper()} --")
        print(f"  {'thr':>4}  {'ear n':>6} {'ear ROI':>8}   {'lat n':>6} {'lat ROI':>8}   robust?")
        cand_robust = None
        for thr in THR_GRID:
            ear = per_stat_roi(early, predfn, stats={stat},
                               thresholds={stat: thr}).get(stat, (0, 0, 0))
            lat = per_stat_roi(late, predfn, stats={stat},
                               thresholds={stat: thr}).get(stat, (0, 0, 0))
            robust = ear[2] > 0 and lat[2] > 0 and ear[0] >= 50 and lat[0] >= 50
            tag = " <-- robust" if robust else ""
            print(f"  {thr:>4.2f}  {ear[0]:>6,d} {ear[2]:+7.2f}%   "
                  f"{lat[0]:>6,d} {lat[2]:+7.2f}%{tag}")
            if robust:
                if cand_robust is None or lat[2] > cand_robust[4]:
                    cand_robust = (thr, ear[0], ear[2], lat[0], lat[2])
        if cand_robust:
            best[stat] = cand_robust

    print("\n== Best per-stat threshold (positive in BOTH halves, max late ROI) ==")
    for stat, (thr, ne, re_, nl, rl) in best.items():
        print(f"  {stat.upper():<5} thr={thr:.2f}   early n={ne:,} ROI={re_:+.2f}%   "
              f"late n={nl:,} ROI={rl:+.2f}%")

    # ---- Combined book under the policy (winning stats with their best thresholds)
    if best:
        thresholds = {s: v[0] for s, v in best.items() if s in ("reb", "ast", "fg3m")}
        stats = set(thresholds)
        print(f"\n== AUTO COMBINED: stats={sorted(stats)} thresholds={thresholds} ==")
        ear = per_stat_roi(early, predfn, stats=stats, thresholds=thresholds)
        lat = per_stat_roi(late, predfn, stats=stats, thresholds=thresholds)
        ne, re_, _ = total(ear); nl, rl, _ = total(lat)
        print(f"  early n={ne:,}  ROI={re_:+.2f}%      late n={nl:,}  ROI={rl:+.2f}%")
        for st in sorted(stats):
            if st in lat:
                n, w, r = lat[st]
                print(f"    late {st:5} n={n:5,d}  win={w/n*100:.1f}%  ROI={r:+.2f}%")

    # ---- Hand-crafted candidate combinations to compare directly
    print("\n== Candidate combined policies ==")
    candidates = [
        ("AST thr=0.75",
         {"ast"}, {"ast": 0.75}),
        ("AST thr=0.75 + FG3M thr=1.25",
         {"ast", "fg3m"}, {"ast": 0.75, "fg3m": 1.25}),
        ("REB no-thr + AST thr=0.75",
         {"reb", "ast"}, {"reb": 0.0, "ast": 0.75}),
        ("REB no-thr + AST thr=0.75 + FG3M thr=1.25",
         {"reb", "ast", "fg3m"}, {"reb": 0.0, "ast": 0.75, "fg3m": 1.25}),
        ("REB+AST unthrottled (currently shipped reb_ast)",
         {"reb", "ast"}, {}),
    ]
    print(f"  {'policy':<48} {'ear n':>6} {'ear ROI':>8}   {'lat n':>6} {'lat ROI':>8}   robust?")
    for label, sts, thr in candidates:
        ear = per_stat_roi(early, predfn, stats=sts, thresholds=thr or None)
        lat = per_stat_roi(late, predfn, stats=sts, thresholds=thr or None)
        ne, re_, _ = total(ear); nl, rl, _ = total(lat)
        rob = " <-- robust" if (re_ > 0 and rl > 0) else ""
        print(f"  {label:<48} {ne:>6,d} {re_:+7.2f}%   {nl:>6,d} {rl:+7.2f}%{rob}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
