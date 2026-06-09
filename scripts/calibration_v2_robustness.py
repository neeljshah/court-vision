"""calibration_v2_robustness.py — validate the per-stat blend policy on a 2ND
independent real-line source.

The blend policy {pts:1.0, reb:0.5, ast:0.0, fg3m:1.0} was SELECTED on the benashkar
DK/FD/MGM closes. Honest test: does it also improve ROI on a DIFFERENT real-line
corpus (eval_2025_26_combined.csv)? Trains v2 calibrators leak-free on pre-2025-26,
predicts all 2025-26, then grades base vs policy on BOTH sources. If it holds on the
held-out source, the policy is real, not benashkar-overfit. No production model.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import xgboost as xgb

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import (  # noqa: E402
    load_benashkar_bets, attach_actuals_and_l10, attach_oof, settle, _build_name_to_pid)

FRAME = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
EVAL = _ROOT / "data" / "cache" / "eval_2025_26_combined.csv"
CUT = "2025-10-01"
COVS = ["pred", "l3_min", "l5_min", "l10_min", "std_min", "prev_min", "min_trend",
        "rest_days", "is_b2b", "is_home", "opp_pace", "opp_def",
        "vac_min", "vac_pts", "n_out", "l5_pts_pm", "l5_reb_pm",
        "month", "days_into_season"]
POLICY = {"pts": 1.0, "reb": 0.5, "ast": 0.0, "fg3m": 1.0,
          "stl": 1.0, "blk": 1.0, "tov": 1.0}  # selected on benashkar


def build_calmap():
    df = pd.read_parquet(FRAME).dropna(subset=["opp_pace", "opp_def"])
    tr = df[df["date"] < CUT]; te = df[df["date"] >= CUT]
    calmap = {}
    for stat in POLICY:
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
        for r, v in zip(s_te.itertuples(index=False), b.predict(xgb.DMatrix(s_te[COVS]))):
            calmap[(int(r.player_id), r.date, stat)] = float(v)
    return calmap


def policy_pred(base, cal, stat):
    if cal is None:
        return base
    a = POLICY.get(stat, 0.0)
    return a * cal + (1 - a) * base


def grade(bets, calmap, use_policy):
    n = w = 0; pnl = 0.0
    per = defaultdict(lambda: [0, 0.0])
    for b in bets:
        base = b["pred"]
        cal = calmap.get((b["pid"], b["date"], b["stat"]))
        pred = policy_pred(base, cal, b["stat"]) if use_policy else base
        res = settle({"line": b["line"], "actual": b["actual"],
                      "over_odds": b["over_odds"], "under_odds": b["under_odds"]}, pred)
        if res is None:
            continue
        _o, won, p = res
        n += 1; w += int(won); pnl += p
        per[b["stat"]][0] += 1; per[b["stat"]][1] += p
    return (n, pnl / (n * 100) * 100 if n else 0,
            {s: (c, pl / (c * 100) * 100 if c else 0) for s, (c, pl) in per.items()})


def benashkar_bets():
    raw = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    return [{"pid": b["pid"], "date": b["gdate"].strftime("%Y-%m-%d"), "stat": b["stat"],
             "line": b["line"], "actual": b["actual"], "over_odds": b["over_odds"],
             "under_odds": b["under_odds"], "pred": b["pred_oof"]} for b in raw]


def eval_combined_bets():
    n2p = _build_name_to_pid()
    oof = pd.read_parquet(_ROOT / "data" / "cache" / "pregame_oof.parquet")
    oof["date"] = oof["game_date"].astype(str).str[:10]
    oofmap = {(int(r.player_id), r.date, r.stat): float(r.oof_pred)
              for r in oof.itertuples(index=False)}
    out = []
    for r in csv.DictReader(open(EVAL, encoding="utf-8")):
        try:
            pid = n2p.get((r["player"] or "").strip().lower())
            if pid is None:
                continue
            stat = r["stat"].strip().lower()
            base = oofmap.get((pid, r["date"].strip(), stat))
            if base is None:
                continue
            out.append({"pid": pid, "date": r["date"].strip(), "stat": stat,
                        "line": float(r["closing_line"]), "actual": float(r["actual_value"]),
                        "over_odds": float(r["over_odds"]), "under_odds": float(r["under_odds"]),
                        "pred": base})
        except (ValueError, KeyError, TypeError):
            continue
    return out


def main():
    print("training v2 calibrators leak-free + predicting 2025-26...")
    calmap = build_calmap()
    for name, bets in (("BENASHKAR (policy SELECTED here)", benashkar_bets()),
                       ("EVAL_COMBINED (HELD-OUT source)", eval_combined_bets())):
        nb, rb, perb = grade(bets, calmap, use_policy=False)
        npc, rc, perc = grade(bets, calmap, use_policy=True)
        print("\n" + "=" * 60)
        print(f"{name}")
        print(f"  BASE          n={nb:,}  ROI={rb:+.2f}%")
        print(f"  BLEND POLICY  n={npc:,}  ROI={rc:+.2f}%   (delta {rc-rb:+.2f}pp)")
        for s in ("pts", "reb", "ast", "fg3m"):
            if perb.get(s):
                print(f"    {s:<5} base={perb[s][1]:+6.2f}%  policy={perc.get(s,(0,0))[1]:+6.2f}%  (a={POLICY[s]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
