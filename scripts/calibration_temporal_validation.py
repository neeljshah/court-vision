"""calibration_temporal_validation.py — does the per-stat blend policy generalize?

Avoids the eval_combined join bug by splitting the well-joined benashkar bets
TEMPORALLY: choose each stat's blend weight a on the EARLY half, then measure ROI on
the LATE (held-out) half with that frozen policy vs base. If the policy still beats
base on data it was not tuned on, the calibration is real, not curve-fit. Leak-free
calibrators (trained pre-2025-26). No production model.
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

CUT = "2025-10-01"
if "v1" in sys.argv:  # validate the SHIPPED simple-covariate calibrators
    FRAME = _ROOT / "data" / "cache" / "calibration_frame.parquet"
    COVS = ["pred", "l10_min", "rest_days", "is_b2b", "is_home", "opp_pace",
            "opp_def", "month", "days_into_season"]
else:
    FRAME = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
    COVS = ["pred", "l3_min", "l5_min", "l10_min", "std_min", "prev_min", "min_trend",
            "rest_days", "is_b2b", "is_home", "opp_pace", "opp_def",
            "vac_min", "vac_pts", "n_out", "l5_pts_pm", "l5_reb_pm",
            "month", "days_into_season"]
ALPHAS = (0.0, 0.25, 0.5, 0.75, 1.0)


def build_calmap():
    df = pd.read_parquet(FRAME).dropna(subset=["opp_pace", "opp_def"])
    tr = df[df["date"] < CUT]; te = df[df["date"] >= CUT]
    cal = {}
    for stat in ("pts", "reb", "ast", "fg3m"):
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
            cal[(int(r.player_id), r.date, stat)] = float(v)
    return cal


def roi(bets, alpha_for):
    n = 0; pnl = 0.0
    for b in bets:
        a = alpha_for(b["stat"])
        cal = b.get("cal")
        pred = (a * cal + (1 - a) * b["pred"]) if cal is not None else b["pred"]
        res = settle(b, pred)
        if res is None:
            continue
        n += 1; pnl += res[2]
    return n, (pnl / (n * 100) * 100 if n else 0.0)


def main():
    cal = build_calmap()
    raw = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    bets = [{"pid": b["pid"], "date": b["gdate"].strftime("%Y-%m-%d"), "stat": b["stat"],
             "line": b["line"], "actual": b["actual"], "over_odds": b["over_odds"],
             "under_odds": b["under_odds"], "pred": b["pred_oof"],
             "cal": cal.get((b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["stat"]))}
            for b in raw]
    bets.sort(key=lambda b: b["date"])
    mid = bets[len(bets) // 2]["date"]
    early = [b for b in bets if b["date"] < mid]
    late = [b for b in bets if b["date"] >= mid]
    print(f"early (tune) n={len(early):,} (<{mid})   late (held-out) n={len(late):,} (>={mid})\n")

    # choose best alpha per stat on EARLY half
    chosen = {}
    print("per-stat alpha sweep on EARLY half (ROI):")
    for stat in ("pts", "reb", "ast", "fg3m"):
        sb = [b for b in early if b["stat"] == stat]
        rs = [roi(sb, lambda s, a=a: a)[1] for a in ALPHAS]
        chosen[stat] = ALPHAS[int(np.argmax(rs))]
        print(f"  {stat:<5} " + " ".join(f"a{a}={r:+.1f}" for a, r in zip(ALPHAS, rs))
              + f"   -> chosen a={chosen[stat]}")

    af = lambda s: chosen.get(s, 0.0)
    nb, rb = roi(late, lambda s: 0.0)
    npc, rc = roi(late, af)
    print(f"\nHELD-OUT LATE half:")
    print(f"  BASE          n={nb:,}  ROI={rb:+.2f}%")
    print(f"  FROZEN POLICY n={npc:,}  ROI={rc:+.2f}%  (delta {rc-rb:+.2f}pp)  policy={chosen}")
    # also a principled fixed policy (pts full, ast raw, reb/fg3m half) as a robustness anchor
    fixed = {"pts": 1.0, "ast": 0.0, "reb": 0.5, "fg3m": 0.5}
    _n, rf = roi(late, lambda s: fixed.get(s, 0.0))
    print(f"  PRINCIPLED    n={_n:,}  ROI={rf:+.2f}%  (delta {rf-rb:+.2f}pp)  policy={fixed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
