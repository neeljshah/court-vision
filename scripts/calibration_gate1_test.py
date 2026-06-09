"""calibration_gate1_test.py — does the covariate calibration beat Vegas, or just MAE?

Trains the GBM calibration LEAK-FREE on pre-2025-26 data only, applies it to the
whole 2025-26 season, then grades BOTH the raw OOF and the calibrated prediction
against real DK/FD/MGM closing lines (same harness as run_gate1_full_analysis),
unfiltered and through the shipped Iter-57 filter stack.

If calibrated ROI > base ROI vs real Vegas, the calibration is a real betting win.
If MAE drops but ROI doesn't move, it's MAE-only (betting-irrelevant). No prod model.
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

FRAME = _ROOT / "data" / "cache" / "calibration_frame.parquet"
COVS = ["pred", "l10_min", "rest_days", "is_b2b", "is_home", "opp_pace",
        "opp_def", "month", "days_into_season"]
CUT = "2025-10-01"


def train_calibrators():
    """Per-stat GBM trained on pre-2025-26; returns {stat: (booster, )} + cal map."""
    df = pd.read_parquet(FRAME).dropna(subset=COVS)
    tr = df[df["date"] < CUT]
    te = df[df["date"] >= CUT].copy()
    cal_map = {}  # (pid, date, stat) -> calibrated pred
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        s_tr = tr[tr["stat"] == stat]; s_te = te[te["stat"] == stat]
        if len(s_tr) < 500 or len(s_te) == 0:
            continue
        params = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
                  "subsample": 0.8, "colsample_bytree": 0.8, "device": "cuda",
                  "tree_method": "hist"}
        try:
            bst = xgb.train(params, xgb.DMatrix(s_tr[COVS], label=s_tr["actual"]),
                            num_boost_round=400)
        except Exception:
            params["device"] = "cpu"
            bst = xgb.train(params, xgb.DMatrix(s_tr[COVS], label=s_tr["actual"]),
                            num_boost_round=400)
        preds = bst.predict(xgb.DMatrix(s_te[COVS]))
        for r, p in zip(s_te.itertuples(index=False), preds):
            cal_map[(int(r.player_id), r.date, stat)] = float(p)
    return cal_map


def aggregate(bets, predkey, filtered):
    by = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0})
    n = w = 0; pnl = 0.0
    for b in bets:
        pred = b.get(predkey)
        if pred is None:
            continue
        line = b["line"]; stat = b["stat"]
        if filtered:
            if abs(pred - line) < edge_threshold_for(stat):
                continue
            direction = "over" if pred > line else "under"
            if direction not in allowed_directions_for(stat):
                continue
            if is_line_excluded(stat, line) or is_direction_line_excluded(stat, direction, line):
                continue
        res = settle(b, pred)
        if res is None:
            continue
        _o, won, p = res
        n += 1; w += int(won); pnl += p
        a = by[stat]; a["n"] += 1; a["w"] += int(won); a["pnl"] += p
    return {"n": n, "beat": w / n * 100 if n else 0, "roi": pnl / (n * 100) * 100 if n else 0,
            "per": {s: {"n": v["n"], "roi": v["pnl"]/(v["n"]*100)*100 if v["n"] else 0,
                        "beat": v["w"]/v["n"]*100 if v["n"] else 0} for s, v in by.items()}}


def main():
    print("training leak-free calibrators (pre-2025-26)...")
    cal = train_calibrators()
    bets = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    for b in bets:
        b["pred_cal"] = cal.get((b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["stat"]))
    n_cal = sum(1 for b in bets if b.get("pred_cal") is not None)
    print(f"  {len(bets):,} real-Vegas bets; {n_cal:,} have a calibrated pred\n")

    # SELECTIVE: calibrate ONLY where the model loses to Vegas (PTS, FG3M);
    # keep the raw prediction on stats where divergence is the edge (AST, REB).
    CALIBRATE = {"pts", "fg3m"}
    for b in bets:
        b["pred_sel"] = (b.get("pred_cal") if b["stat"] in CALIBRATE
                         else b.get("pred_oof"))

    for label, filt in (("UNFILTERED (bet every edge)", False),
                        ("FILTERED (shipped Iter-57 stack)", True)):
        rb = aggregate(bets, "pred_oof", filt)
        rc = aggregate(bets, "pred_cal", filt)
        rs = aggregate(bets, "pred_sel", filt)
        print("=" * 60)
        print(label)
        print(f"  BASE OOF        n={rb['n']:,}  beat={rb['beat']:.2f}%  ROI={rb['roi']:+.2f}%")
        print(f"  CALIBRATE-ALL   n={rc['n']:,}  beat={rc['beat']:.2f}%  ROI={rc['roi']:+.2f}%")
        print(f"  SELECTIVE(pts,fg3m) n={rs['n']:,}  beat={rs['beat']:.2f}%  ROI={rs['roi']:+.2f}%")
        for s in ("pts", "reb", "ast", "fg3m"):
            pb = rb["per"].get(s, {}); pc = rc["per"].get(s, {})
            if pb.get("n"):
                print(f"    {s:<5} base ROI={pb['roi']:+6.2f}%  | cal ROI={pc.get('roi',0):+6.2f}%")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
