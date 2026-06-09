"""calibration_final_grade.py — the headline number for the SHIPPED config.

Trains the v2 calibrators leak-free (pre-2025-26), applies the shipped per-stat
blend policy {pts:1.0, reb:0.5, fg3m:0.5, ast:0.0}, and grades base vs policy on the
real benashkar DK/FD/MGM closes, BOTH unfiltered (bet every edge) and through the
shipped Iter-57 filter stack (what the product actually bets). No production model.
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
from src.prediction.bet_thresholds import (  # noqa: E402
    edge_threshold_for, allowed_directions_for, is_line_excluded,
    is_direction_line_excluded)

FRAME = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
CUT = "2025-10-01"
COVS = ["pred", "l3_min", "l5_min", "l10_min", "std_min", "prev_min", "min_trend",
        "rest_days", "is_b2b", "is_home", "opp_pace", "opp_def",
        "vac_min", "vac_pts", "n_out", "l5_pts_pm", "l5_reb_pm",
        "month", "days_into_season"]
POLICY = {"pts": 1.0, "reb": 0.5, "fg3m": 0.5, "ast": 0.0}


def calmap():
    df = pd.read_parquet(FRAME).dropna(subset=["opp_pace", "opp_def"])
    tr = df[df["date"] < CUT]; te = df[df["date"] >= CUT]
    cm = {}
    for stat in ("pts", "reb", "fg3m", "ast"):
        s_tr = tr[tr["stat"] == stat]; s_te = te[te["stat"] == stat]
        if len(s_tr) < 500:
            continue
        p = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
             "subsample": 0.8, "colsample_bytree": 0.8, "device": "cuda",
             "tree_method": "hist"}
        try:
            b = xgb.train(p, xgb.DMatrix(s_tr[COVS], label=s_tr["actual"]), num_boost_round=450)
        except Exception:
            p["device"] = "cpu"
            b = xgb.train(p, xgb.DMatrix(s_tr[COVS], label=s_tr["actual"]), num_boost_round=450)
        for r, v in zip(s_te.itertuples(index=False), b.predict(xgb.DMatrix(s_te[COVS]))):
            cm[(int(r.player_id), r.date, stat)] = float(v)
    return cm


def grade(bets, cm, use_policy, filt):
    n = w = 0; pnl = 0.0; per = defaultdict(lambda: [0, 0.0])
    for b in bets:
        base = b["pred_oof"]
        cal = cm.get((b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["stat"]))
        if use_policy and cal is not None:
            a = POLICY.get(b["stat"], 0.0)
            pred = a * cal + (1 - a) * base
        else:
            pred = base
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
    cm = calmap()
    bets = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    for label, filt in (("UNFILTERED (bet every edge)", False),
                        ("FILTERED Iter-57 (what the product bets)", True)):
        nb, beb, rb, pb = grade(bets, cm, False, filt)
        nc, bec, rc, pc = grade(bets, cm, True, filt)
        print("=" * 60, f"\n{label}")
        print(f"  BASE    n={nb:,} beat={beb:.2f}% ROI={rb:+.2f}%")
        print(f"  SHIPPED n={nc:,} beat={bec:.2f}% ROI={rc:+.2f}%  (delta {rc-rb:+.2f}pp)")
        for s in ("pts", "reb", "ast", "fg3m"):
            if pb.get(s):
                print(f"    {s:<5} base n={pb[s][0]:>4,d} ROI={pb[s][1]:+6.2f}%  | "
                      f"shipped n={pc.get(s,(0,0))[0]:>4,d} ROI={pc.get(s,(0,0))[1]:+6.2f}%")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
