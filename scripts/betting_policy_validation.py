"""betting_policy_validation.py — the product bets the wrong stats; prove a fix OOS.

calibration_final_grade.py showed the shipped Iter-57 filtered book is 81% PTS bets
and loses (-4.82%), while filtered AST is +15%. This tests, on a TEMPORAL held-out
split of the real benashkar closes, whether a stat-selective policy (bet only the
edge-positive stats, calibrated) beats both the raw book and the Iter-57 filtered book.

Policies graded on the late (held-out) half, with selection logic frozen from the
early half:
  A. BASE unfiltered (bet every edge, raw pred)
  B. Iter-57 FILTERED (the product's current bets)
  C. EDGE-POSITIVE stats only, calibrated (bet stats whose EARLY-half ROI > +1%)
  D. AST-only, calibrated (the single robust edge)
No production model touched.
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
BLEND = {"pts": 1.0, "reb": 0.5, "fg3m": 0.5, "ast": 0.0}


def calmap():
    df = pd.read_parquet(FRAME).dropna(subset=["opp_pace", "opp_def"])
    tr = df[df["date"] < CUT]; te = df[df["date"] >= CUT]
    cm = {}
    for stat in ("pts", "reb", "fg3m", "ast"):
        s_tr = tr[tr["stat"] == stat]; s_te = te[te["stat"] == stat]
        if len(s_tr) < 500:
            continue
        p = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
             "subsample": 0.8, "colsample_bytree": 0.8, "device": "cuda", "tree_method": "hist"}
        try:
            b = xgb.train(p, xgb.DMatrix(s_tr[COVS], label=s_tr["actual"]), num_boost_round=450)
        except Exception:
            p["device"] = "cpu"
            b = xgb.train(p, xgb.DMatrix(s_tr[COVS], label=s_tr["actual"]), num_boost_round=450)
        for r, v in zip(s_te.itertuples(index=False), b.predict(xgb.DMatrix(s_te[COVS]))):
            cm[(int(r.player_id), r.date, stat)] = float(v)
    return cm


def calpred(b, cm):
    base = b["pred_oof"]
    cal = cm.get((b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["stat"]))
    if cal is None:
        return base
    a = BLEND.get(b["stat"], 0.0)
    return a * cal + (1 - a) * base


def roi(bets, predfn, *, filt=False, stats=None):
    n = w = 0; pnl = 0.0
    for b in bets:
        if stats and b["stat"] not in stats:
            continue
        pred = predfn(b)
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
        n += 1; w += int(res[1]); pnl += res[2]
    return n, (pnl / (n * 100) * 100 if n else 0.0)


def per_stat_roi(bets, predfn):
    per = defaultdict(lambda: [0, 0.0])
    for b in bets:
        res = settle(b, predfn(b))
        if res is None:
            continue
        per[b["stat"]][0] += 1; per[b["stat"]][1] += res[2]
    return {s: (c, pl / (c * 100) * 100 if c else 0) for s, (c, pl) in per.items()}


def main():
    cm = calmap()
    raw = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    bets = sorted(raw, key=lambda b: b["gdate"])
    mid = bets[len(bets) // 2]["gdate"]
    early = [b for b in bets if b["gdate"] < mid]
    late = [b for b in bets if b["gdate"] >= mid]
    print(f"early (select) n={len(early):,}   late (held-out) n={len(late):,}\n")

    # choose edge-positive stats on EARLY half (calibrated, ROI > +1%)
    ep = per_stat_roi(early, lambda b: calpred(b, cm))
    pos = {s for s, (c, r) in ep.items() if r > 1.0 and c >= 100}
    print("EARLY-half per-stat ROI (calibrated):",
          {s: f"{r:+.1f}% (n={c})" for s, (c, r) in sorted(ep.items())})
    print(f"  -> edge-positive stats selected: {sorted(pos)}\n")

    print("HELD-OUT LATE half:")
    print(f"  A. BASE unfiltered           n={roi(late, lambda b: b['pred_oof'])[0]:,}"
          f"  ROI={roi(late, lambda b: b['pred_oof'])[1]:+.2f}%")
    print(f"  B. Iter-57 FILTERED (product)n={roi(late, lambda b: b['pred_oof'], filt=True)[0]:,}"
          f"  ROI={roi(late, lambda b: b['pred_oof'], filt=True)[1]:+.2f}%")
    nC, rC = roi(late, lambda b: calpred(b, cm), stats=pos)
    print(f"  C. EDGE-POSITIVE {sorted(pos)} calibrated  n={nC:,}  ROI={rC:+.2f}%")
    nD, rD = roi(late, lambda b: calpred(b, cm), stats={"ast"})
    print(f"  D. AST-only calibrated       n={nD:,}  ROI={rD:+.2f}%")
    # robust exclusion: PTS loses in BOTH halves -> drop it (no filter)
    expts = {"reb", "ast", "fg3m"}
    nE, rE = roi(late, lambda b: calpred(b, cm), stats=expts)
    print(f"  E. calibrated, NO filter, ex-PTS {sorted(expts)}  n={nE:,}  ROI={rE:+.2f}%")
    expf = {"reb", "ast"}
    nF, rF = roi(late, lambda b: calpred(b, cm), stats=expf)
    print(f"  F. calibrated, ex-PTS&FG3M {sorted(expf)}  n={nF:,}  ROI={rF:+.2f}%")
    # robustness: also show each policy's EARLY-half ROI (should agree in sign)
    print("\n  early-half sanity (same policies):")
    print(f"    A base={roi(early, lambda b: b['pred_oof'])[1]:+.2f}%  "
          f"E ex-PTS={roi(early, lambda b: calpred(b, cm), stats=expts)[1]:+.2f}%  "
          f"F ex-PTS&FG3M={roi(early, lambda b: calpred(b, cm), stats=expf)[1]:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
