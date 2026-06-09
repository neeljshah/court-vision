"""ast_subsegment_audit.py -- under the shipped ast_high policy (AST, calibrated,
edge >= 0.75) is there a hidden weak sub-segment to drop?

Slices the AST bets by line bucket, home/away, b2b, rest_days bucket,
days_into_season half. For each slice, reports ROI in BOTH temporal halves.
A slice qualifies as 'drop' only if it is negative in BOTH halves AND has n
>= 20 in each half (so we don't drop random noise).

This is the same robustness bar that picked the 0.75 threshold in
bet_policy_sweep.py: a slice must FAIL in both halves to be retired.
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
AST_THR = 0.75


def _cal_pred(b, booster, frame_idx):
    base = b["pred_oof"]
    cov_row = frame_idx.get((b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["stat"]))
    if booster is None or cov_row is None:
        return base
    row = pd.DataFrame([{"pred": base, **cov_row}])
    try:
        cal = float(booster.predict(xgb.DMatrix(row[COVS]))[0])
    except Exception:
        return base
    # AST blend = 0.0 in the shipped policy -> stays raw
    return base


def _line_bucket(line: float) -> str:
    if line <= 3.5:
        return "low(<=3.5)"
    if line <= 5.5:
        return "mid(3.5-5.5)"
    if line <= 7.5:
        return "high(5.5-7.5)"
    return "very_high(>7.5)"


def _rest_bucket(r):
    try:
        r = int(r)
    except Exception:
        return "unk"
    if r <= 1:
        return "b2b"
    if r == 2:
        return "rest2"
    if r == 3:
        return "rest3"
    return "rest4+"


def _audit(early, late, predfn, slicer, label):
    """Report ROI per slice in each half. Mark as 'DROP candidate' iff both
    halves negative AND n>=20 each."""
    print(f"\n-- by {label} --")
    print(f"  {'slice':<18} {'ear n':>6} {'ear ROI':>8}   {'lat n':>6} {'lat ROI':>8}   verdict")
    slice_groups: dict[str, dict[str, list]] = defaultdict(
        lambda: {"early": [], "late": []})
    for half, bets in (("early", early), ("late", late)):
        for b in bets:
            if b["stat"] != "ast":
                continue
            pred = predfn(b)
            if abs(pred - b["line"]) < AST_THR:
                continue
            slice_groups[slicer(b)][half].append((b, pred))
    rows = []
    for slc in sorted(slice_groups):
        def _roi(items):
            n = w = 0; pl = 0.0
            for b, p in items:
                res = settle(b, p)
                if res is None:
                    continue
                n += 1; w += int(res[1]); pl += res[2]
            return n, (pl / (n * 100) * 100 if n else 0.0), w
        ne, re_, _ = _roi(slice_groups[slc]["early"])
        nl, rl, _ = _roi(slice_groups[slc]["late"])
        verdict = ""
        if ne >= 20 and nl >= 20 and re_ < 0 and rl < 0:
            verdict = " <-- DROP candidate (negative both halves)"
        elif ne >= 20 and nl >= 20 and re_ > 0 and rl > 0:
            verdict = " (robust positive)"
        print(f"  {slc:<18} {ne:>6,d} {re_:+7.2f}%   {nl:>6,d} {rl:+7.2f}%{verdict}")
        rows.append((slc, ne, re_, nl, rl))
    return rows


def main():
    frame = pd.read_parquet(FRAME).dropna(subset=["opp_pace", "opp_def"])
    raw = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    bets = sorted(raw, key=lambda b: b["gdate"])
    mid = bets[len(bets) // 2]["gdate"]
    early = [b for b in bets if b["gdate"] < mid]
    late = [b for b in bets if b["gdate"] >= mid]
    print(f"early n={len(early):,}   late n={len(late):,}   AST threshold = {AST_THR}")

    # train a tiny dummy booster (AST blend=0 means it's never used; we keep the
    # plumbing parallel to bet_policy_sweep so the predfn signature matches)
    predfn = lambda b: _cal_pred(b, None, {})  # noqa: E731

    # slice the bets various ways
    _audit(early, late, predfn,
           lambda b: _line_bucket(b["line"]), "line bucket")
    _audit(early, late, predfn,
           lambda b: "home" if b.get("is_home") else "away" if "is_home" in b else "unk",
           "venue (from frame would be better; benashkar lacks is_home)")
    _audit(early, late, predfn,
           lambda b: _rest_bucket(b.get("rest_days", -1)), "rest days bucket")
    _audit(early, late, predfn,
           lambda b: b.get("book", "unk"), "book")
    _audit(early, late, predfn,
           lambda b: b["gdate"].strftime("%Y-%m"), "year-month")
    return 0


if __name__ == "__main__":
    sys.exit(main())
