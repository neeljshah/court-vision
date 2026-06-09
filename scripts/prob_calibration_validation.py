"""prob_calibration_validation.py -- does P(actual>line) calibration beat the
existing point calibrator?

The shipped pregame calibrator nudges the point mean toward the conditional
mean. That helps where the model loses (PTS) and hurts where it wins (AST is
served raw on purpose). But what decides a bet is the *probability* the actual
beats the line, not how close the point estimate is to the line; a probability
calibrator should let us bet at higher-conviction (P > 0.55) instead of at
arbitrary edge thresholds.

Methodology (matches betting_policy_validation.py exactly):
  * Load the real DK/FD/MGM closing-line bets for 2025-26 (load_benashkar_bets).
  * Temporal split by game_date: EARLY half -> calibrator training; LATE half ->
    held-out grading.
  * Train per-stat XGBoost CLASSIFIER on the early half:
      target  = int(actual > line)
      inputs  = pred, line, pred-line, plus the same covariates the point
                calibrator uses.
  * Predict P(actual > line) on the late half.
  * Bet OVER when P > P_BET_HI, UNDER when P < P_BET_LO; settle at the actual
    posted odds and grade ROI.
  * Compare to: BASE unfiltered (bet every edge>0), the shipped point
    calibrator's per-stat blend policy, and the REB+AST stat policy.

Strict no-look-ahead: calibrators only see early-half rows.
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

FRAME = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
COVS_BASE = ["l3_min", "l5_min", "l10_min", "std_min", "prev_min", "min_trend",
             "rest_days", "is_b2b", "is_home", "opp_pace", "opp_def",
             "vac_min", "vac_pts", "n_out", "l5_pts_pm", "l5_reb_pm",
             "month", "days_into_season"]
POINT_BLEND = {"pts": 1.0, "reb": 0.5, "fg3m": 0.5, "ast": 0.0}

# Bet only when the calibrated probability clears these.
P_BET_HI = 0.55  # over
P_BET_LO = 0.45  # under


def _join_covariates(bets, frame):
    """Mutates bets to add covariates from the calibration frame.

    Returns the bets that had a covariate row available (rest dropped)."""
    idx: dict[tuple, dict] = {}
    for r in frame.itertuples(index=False):
        idx[(int(r.player_id), r.date, r.stat)] = {c: getattr(r, c) for c in COVS_BASE}
    out = []
    for b in bets:
        key = (b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["stat"])
        row = idx.get(key)
        if row is None:
            continue
        b.update(row)
        out.append(b)
    return out


def train_point_calibrators(early_df: pd.DataFrame) -> dict:
    """Replicate the shipped point calibrator's per-stat XGBoost (regression on
    actual) so we can compare apples to apples on this same split."""
    out: dict[str, xgb.Booster] = {}
    feats = ["pred"] + COVS_BASE
    for stat in ("pts", "reb", "fg3m", "ast"):
        s_tr = early_df[early_df["stat"] == stat].dropna(subset=COVS_BASE + ["pred", "actual"])
        if len(s_tr) < 500:
            continue
        p = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
             "subsample": 0.8, "colsample_bytree": 0.8,
             "device": "cuda", "tree_method": "hist"}
        try:
            b = xgb.train(p, xgb.DMatrix(s_tr[feats], label=s_tr["actual"]),
                          num_boost_round=450)
        except xgb.core.XGBoostError:
            p["device"] = "cpu"
            b = xgb.train(p, xgb.DMatrix(s_tr[feats], label=s_tr["actual"]),
                          num_boost_round=450)
        out[stat] = b
    return out


def train_prob_calibrators(early_bets: list) -> dict:
    """Train per-stat P(actual>line) classifiers on the early-half bets."""
    out: dict[str, xgb.Booster] = {}
    feats = ["pred", "line", "edge"] + COVS_BASE
    for stat in ("pts", "reb", "fg3m", "ast"):
        rows = [b for b in early_bets if b["stat"] == stat
                and all(b.get(c) is not None for c in COVS_BASE)]
        if len(rows) < 300:
            continue
        df = pd.DataFrame([{
            "pred": b["pred_oof"], "line": b["line"],
            "edge": b["pred_oof"] - b["line"],
            **{c: b[c] for c in COVS_BASE},
            "y": int(b["actual"] > b["line"]),
        } for b in rows])
        p = {"objective": "binary:logistic", "max_depth": 4, "eta": 0.05,
             "subsample": 0.8, "colsample_bytree": 0.8,
             "eval_metric": "logloss",
             "device": "cuda", "tree_method": "hist"}
        try:
            b = xgb.train(p, xgb.DMatrix(df[feats], label=df["y"]),
                          num_boost_round=300)
        except xgb.core.XGBoostError:
            p["device"] = "cpu"
            b = xgb.train(p, xgb.DMatrix(df[feats], label=df["y"]),
                          num_boost_round=300)
        out[stat] = b
        print(f"  prob_cal[{stat}]: n_tr={len(rows):,}  base_rate={df['y'].mean():.3f}")
    return out


def _payout_won(odds, won):
    """Match scripts/run_gate1_full_analysis._payout — returns pnl in dollars
    on a $100 stake, so ROI = pnl / (n * 100) * 100 = pnl / n (in %)."""
    if not won:
        return -100.0
    if odds < 0:
        return 100.0 / abs(odds) * 100.0
    return odds / 100.0 * 100.0


def grade_point_blend(bets, point_models: dict):
    """ROI when serving (a*calibrated + (1-a)*base) and betting every nonzero edge."""
    feats = ["pred"] + COVS_BASE
    n = w = 0; pnl = 0.0
    by_stat = defaultdict(lambda: [0, 0, 0.0])
    for b in bets:
        a = POINT_BLEND.get(b["stat"], 0.0)
        base = b["pred_oof"]
        if a > 0 and b["stat"] in point_models:
            row = pd.DataFrame([{"pred": base, **{c: b[c] for c in COVS_BASE}}])
            try:
                cal = float(point_models[b["stat"]].predict(xgb.DMatrix(row[feats]))[0])
            except Exception:
                cal = base
            pred = a * cal + (1 - a) * base
        else:
            pred = base
        res = settle(b, pred)
        if res is None:
            continue
        n += 1
        w += int(res[1])
        pnl += res[2]
        by_stat[b["stat"]][0] += 1
        by_stat[b["stat"]][1] += int(res[1])
        by_stat[b["stat"]][2] += res[2]
    roi = pnl / (n * 100) * 100 if n else 0.0
    return n, roi, w, {s: (c, win, pl / (c * 100) * 100 if c else 0)
                       for s, (c, win, pl) in by_stat.items()}


def grade_prob(bets, prob_models: dict, p_hi=P_BET_HI, p_lo=P_BET_LO):
    """ROI when betting only where the prob calibrator's P(over) clears p_hi/p_lo."""
    feats = ["pred", "line", "edge"] + COVS_BASE
    n = w = 0; pnl = 0.0
    by_stat = defaultdict(lambda: [0, 0, 0.0])
    for b in bets:
        if b["stat"] not in prob_models:
            continue
        if any(b.get(c) is None for c in COVS_BASE):
            continue
        row = pd.DataFrame([{"pred": b["pred_oof"], "line": b["line"],
                             "edge": b["pred_oof"] - b["line"],
                             **{c: b[c] for c in COVS_BASE}}])
        try:
            p_over = float(prob_models[b["stat"]].predict(
                xgb.DMatrix(row[feats]))[0])
        except Exception:
            continue
        if p_lo < p_over < p_hi:
            continue
        bet_over = p_over >= p_hi
        actual = b["actual"]; line = b["line"]
        if abs(actual - line) < 1e-9:
            continue  # push
        won = (bet_over and actual > line) or (not bet_over and actual < line)
        odds = b["over_odds"] if bet_over else b["under_odds"]
        pay = _payout_won(odds, won)
        n += 1; w += int(won); pnl += pay
        by_stat[b["stat"]][0] += 1
        by_stat[b["stat"]][1] += int(won)
        by_stat[b["stat"]][2] += pay
    roi = pnl / (n * 100) * 100 if n else 0.0
    return n, roi, w, {s: (c, win, pl / (c * 100) * 100 if c else 0)
                       for s, (c, win, pl) in by_stat.items()}


def grade_base(bets):
    n = w = 0; pnl = 0.0
    for b in bets:
        res = settle(b, b["pred_oof"])
        if res is None:
            continue
        n += 1; w += int(res[1]); pnl += res[2]
    return n, (pnl / (n * 100) * 100 if n else 0.0), w


def grade_hybrid(bets, prob_models, point_models, p_hi, p_lo,
                 prob_stats=("pts", "reb"), raw_stats=("ast", "fg3m")):
    """Hybrid policy: use prob_cal gate on prob_stats, base-direction (with the
    point-blend) on raw_stats. Mirrors the per-stat 'calibrate only where you
    lose' principle that already governs the point calibrator."""
    point_feats = ["pred"] + COVS_BASE
    prob_feats = ["pred", "line", "edge"] + COVS_BASE
    n = w = 0; pnl = 0.0
    by_stat = defaultdict(lambda: [0, 0, 0.0])
    for b in bets:
        if any(b.get(c) is None for c in COVS_BASE):
            continue
        stat = b["stat"]
        line = b["line"]; actual = b["actual"]
        if abs(actual - line) < 1e-9:
            continue
        cov_row = {c: b[c] for c in COVS_BASE}
        if stat in prob_stats and stat in prob_models:
            row = pd.DataFrame([{"pred": b["pred_oof"], "line": line,
                                 "edge": b["pred_oof"] - line, **cov_row}])
            try:
                p_over = float(prob_models[stat].predict(
                    xgb.DMatrix(row[prob_feats]))[0])
            except Exception:
                continue
            if p_lo < p_over < p_hi:
                continue
            bet_over = p_over >= p_hi
        elif stat in raw_stats:
            # point-blend on the winning stats — same as shipped per-stat blend
            base = b["pred_oof"]
            a = POINT_BLEND.get(stat, 0.0)
            if a > 0 and stat in point_models:
                row = pd.DataFrame([{"pred": base, **cov_row}])
                try:
                    cal = float(point_models[stat].predict(xgb.DMatrix(row[point_feats]))[0])
                except Exception:
                    cal = base
                pred = a * cal + (1 - a) * base
            else:
                pred = base
            if abs(pred - line) < 1e-9:
                continue
            bet_over = pred > line
        else:
            continue
        won = (bet_over and actual > line) or (not bet_over and actual < line)
        odds = b["over_odds"] if bet_over else b["under_odds"]
        pay = _payout_won(odds, won)
        n += 1; w += int(won); pnl += pay
        by_stat[stat][0] += 1
        by_stat[stat][1] += int(won)
        by_stat[stat][2] += pay
    roi = pnl / (n * 100) * 100 if n else 0.0
    return n, roi, w, {s: (c, win, pl / (c * 100) * 100 if c else 0)
                       for s, (c, win, pl) in by_stat.items()}


def main():
    frame = pd.read_parquet(FRAME).dropna(subset=["opp_pace", "opp_def"])
    raw = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    print(f"loaded {len(raw):,} benashkar bets with pred_oof")
    bets = _join_covariates(raw, frame)
    print(f"  with covariates: {len(bets):,}")
    bets.sort(key=lambda b: b["gdate"])
    mid = bets[len(bets) // 2]["gdate"]
    early = [b for b in bets if b["gdate"] < mid]
    late = [b for b in bets if b["gdate"] >= mid]
    print(f"  early n={len(early):,}  late n={len(late):,}\n")

    # train BOTH calibrators on early half
    print("training POINT calibrators on early half...")
    early_df = frame[frame["date"] < mid.strftime("%Y-%m-%d")]
    point_models = train_point_calibrators(early_df)
    print(f"  trained: {sorted(point_models)}\n")
    print("training PROB calibrators on early half...")
    prob_models = train_prob_calibrators(early)
    print(f"  trained: {sorted(prob_models)}\n")

    print(f"==== HELD-OUT LATE HALF (n={len(late):,}) ====\n")
    nB, rB, wB = grade_base(late)
    print(f"  BASE unfiltered           n={nB:,}  ROI={rB:+.2f}%  win={wB/nB*100:.1f}%")
    nP, rP, wP, byP = grade_point_blend(late, point_models)
    print(f"  POINT-BLEND (shipped)     n={nP:,}  ROI={rP:+.2f}%  win={wP/nP*100:.1f}%")
    for stat in ("pts", "reb", "ast", "fg3m"):
        if stat in byP:
            c, win, r = byP[stat]
            print(f"    {stat:5} n={c:5,d}  win={win/c*100:5.1f}%  ROI={r:+.2f}%")

    for p_hi in (0.52, 0.55, 0.58):
        p_lo = 1 - p_hi
        nQ, rQ, wQ, byQ = grade_prob(late, prob_models, p_hi=p_hi, p_lo=p_lo)
        print(f"  PROB-CAL p>={p_hi}        n={nQ:,}  ROI={rQ:+.2f}%  "
              f"win={(wQ/nQ*100 if nQ else 0):.1f}%")
        for stat in ("pts", "reb", "ast", "fg3m"):
            if stat in byQ:
                c, win, r = byQ[stat]
                print(f"    {stat:5} n={c:5,d}  win={win/c*100:5.1f}%  ROI={r:+.2f}%")
    # hybrid: prob_cal-gate the loser stats, point-blend the winner stats
    print()
    for p_hi in (0.52, 0.55, 0.58):
        p_lo = 1 - p_hi
        nH, rH, wH, byH = grade_hybrid(late, prob_models, point_models,
                                       p_hi=p_hi, p_lo=p_lo)
        print(f"  HYBRID  prob(PTS+REB)@{p_hi} + point-blend(AST+FG3M)  "
              f"n={nH:,}  ROI={rH:+.2f}%  win={(wH/nH*100 if nH else 0):.1f}%")
        for stat in ("pts", "reb", "ast", "fg3m"):
            if stat in byH:
                c, win, r = byH[stat]
                print(f"    {stat:5} n={c:5,d}  win={win/c*100:5.1f}%  ROI={r:+.2f}%")
    # early-half sanity for the hybrid (both halves must agree in sign per principle)
    print("\n  early-half sanity (hybrid p>=0.55):")
    nHe, rHe, _, _ = grade_hybrid(early, prob_models, point_models,
                                  p_hi=0.55, p_lo=0.45)
    print(f"    early hybrid n={nHe:,}  ROI={rHe:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
