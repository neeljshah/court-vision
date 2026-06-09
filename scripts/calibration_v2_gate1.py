"""calibration_v2_gate1.py — does the ENRICHED calibrator beat v1 vs real Vegas?

Trains per-stat calibrators on the v2 covariate set (minutes-shape + vacated-minutes
+ scoring rate) leak-free on pre-2025-26, grades base vs calibrated vs blends against
real DK/FD/MGM closes. Also sweeps the blend weight alpha (pred = a*cal + (1-a)*base)
to find whether partial calibration beats full. No production model touched.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import (  # noqa: E402
    load_benashkar_bets, attach_actuals_and_l10, attach_oof, settle)
from src.prediction.bet_thresholds import (  # noqa: E402
    edge_threshold_for, allowed_directions_for, is_line_excluded,
    is_direction_line_excluded)

FRAME = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
CUT = "2025-10-01"
COVS = ["pred", "l3_min", "l5_min", "l10_min", "std_min", "prev_min", "min_trend",
        "rest_days", "is_b2b", "is_home", "opp_pace", "opp_def",
        "vac_min", "vac_pts", "n_out", "l5_pts_pm", "l5_reb_pm",
        "month", "days_into_season"]


def train_cal():
    df = pd.read_parquet(FRAME).dropna(subset=["opp_pace", "opp_def"])
    tr = df[df["date"] < CUT]; te = df[df["date"] >= CUT]
    cal = {}
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        s_tr = tr[tr["stat"] == stat]; s_te = te[te["stat"] == stat]
        if len(s_tr) < 500 or len(s_te) == 0:
            continue
        p = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
             "subsample": 0.8, "colsample_bytree": 0.8, "device": "cuda",
             "tree_method": "hist"}
        try:
            b = xgb.train(p, xgb.DMatrix(s_tr[COVS], label=s_tr["actual"]), num_boost_round=450)
        except Exception:
            p["device"] = "cpu"
            b = xgb.train(p, xgb.DMatrix(s_tr[COVS], label=s_tr["actual"]), num_boost_round=450)
        pr = b.predict(xgb.DMatrix(s_te[COVS]))
        for r, v in zip(s_te.itertuples(index=False), pr):
            cal[(int(r.player_id), r.date, stat)] = float(v)
    return cal


def roi(bets, predfn, filt):
    n = w = 0; pnl = 0.0; per = defaultdict(lambda: [0, 0.0])
    for b in bets:
        pred = predfn(b)
        if pred is None:
            continue
        line = b["line"]; stat = b["stat"]
        if filt:
            if abs(pred - line) < edge_threshold_for(stat):
                continue
            d = "over" if pred > line else "under"
            if d not in allowed_directions_for(stat) or is_line_excluded(stat, line) \
               or is_direction_line_excluded(stat, d, line):
                continue
        res = settle(b, pred)
        if res is None:
            continue
        _o, won, p = res
        n += 1; w += int(won); pnl += p
        per[stat][0] += 1; per[stat][1] += p
    return (n, w / n * 100 if n else 0, pnl / (n * 100) * 100 if n else 0,
            {s: (c, pl / (c * 100) * 100 if c else 0) for s, (c, pl) in per.items()})


def main():
    print("training enriched (v2) calibrators leak-free...")
    cal = train_cal()
    bets = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    for b in bets:
        b["cal"] = cal.get((b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["stat"]))
    have = sum(1 for b in bets if b["cal"] is not None)
    print(f"  {len(bets):,} bets, {have:,} calibrated\n")

    base = lambda b: b.get("pred_oof")
    full = lambda b: b["cal"] if b.get("cal") is not None else b.get("pred_oof")

    for label, filt in (("UNFILTERED", False), ("FILTERED (Iter-57)", True)):
        nb, beatb, rb, perb = roi(bets, base, filt)
        nc, beatc, rc, perc = roi(bets, full, filt)
        print("=" * 58, f"\n{label}")
        print(f"  BASE        n={nb:,} beat={beatb:.2f}% ROI={rb:+.2f}%")
        print(f"  v2 CAL-ALL  n={nc:,} beat={beatc:.2f}% ROI={rc:+.2f}%")
        for s in ("pts", "reb", "ast", "fg3m"):
            if perb.get(s):
                print(f"    {s:<5} base ROI={perb[s][1]:+6.2f}%  cal ROI={perc.get(s,(0,0))[1]:+6.2f}%")
        print()

    # blend sweep (unfiltered) per stat
    print("=" * 58, "\nBLEND SWEEP (unfiltered ROI) pred = a*cal + (1-a)*base")
    print(f"  {'stat':<5}" + "".join(f"a={a:<6.2f}" for a in (0.0, 0.25, 0.5, 0.75, 1.0)))
    for stat in ("pts", "reb", "ast", "fg3m"):
        sbets = [b for b in bets if b["stat"] == stat and b.get("cal") is not None]
        rs = []
        for a in (0.0, 0.25, 0.5, 0.75, 1.0):
            fn = lambda b, a=a: a * b["cal"] + (1 - a) * b["pred_oof"]
            _n, _be, r, _p = roi(sbets, fn, False)
            rs.append(r)
        best_a = (0.0, 0.25, 0.5, 0.75, 1.0)[int(np.argmax(rs))]
        print(f"  {stat:<5}" + "".join(f"{r:+6.2f}%  " for r in rs) + f"  best a={best_a}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
