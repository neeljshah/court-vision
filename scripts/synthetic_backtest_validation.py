"""synthetic_backtest_validation.py — sanity-check the closing-line backtest math.

Cycle 44 shipped scripts/backtest_vs_closing_lines.py. We've never had real
closing lines, so the harness has never been exercised at scale. This script
validates the SAME EV/Kelly/settle math on the prop_pergame holdout slice
with synthetic closing lines derived from each player-game's L5 average +
a small "sharpness" bias (mirroring cycle-30 smart-line logic).

Expected: at threshold-edge=+0.5 the ROI should be roughly +20-30% to
match the betting_backtest_smart_line.py result. Big deviations → math
divergence between this validator and the cycle-44 harness.

Performance: loads each stat's q10/q50/q90 + production model ONCE then
vectorized-predicts the full holdout (n≈20k). The previous per-row version
re-loaded the model on every call (140k disk hits, >30 min). This rewrite
finishes in <30s.

Run:
    python scripts/synthetic_backtest_validation.py --threshold-edge 0.5
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from collections import defaultdict
from math import erf, sqrt
from typing import Optional

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _USE_Q50_STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    _MODEL_DIR, _META_WEIGHTS_FILENAME,
    build_pergame_dataset, feature_columns,
    _load_q50_model, load_pergame_model,
)
from src.prediction.prop_quantiles import load_quantile_models, _inverse as _qinv  # noqa: E402
from src.prediction.quantile_calibration import apply as apply_quant_cal  # noqa: E402
import json


def _american_payout(odds: int, stake: float = 1.0) -> float:
    if odds >= 100:
        return stake * odds / 100.0
    return stake * 100.0 / abs(odds)


def _kelly(prob: float, odds: int) -> float:
    if prob is None or prob <= 0 or prob >= 1:
        return 0.0
    b = (odds / 100.0) if odds >= 100 else (100.0 / abs(odds))
    f = (prob * (b + 1) - 1) / b
    return max(0.0, min(f, 0.25))


def _settle(side: str, line: float, actual: float, odds: int,
            stake: float = 1.0) -> float:
    if actual == line:
        return 0.0
    won = (actual > line) if side == "OVER" else (actual < line)
    return _american_payout(odds, stake) if won else -stake


def _inv_pp(stat: str, v: np.ndarray) -> np.ndarray:
    if stat in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return v


def _bulk_predict_pred(stat: str, X: np.ndarray) -> Optional[np.ndarray]:
    """Mirror predict_pergame dispatch: q50 for _USE_Q50_STATS, else NNLS blend."""
    if stat in _USE_Q50_STATS:
        m = _load_q50_model(stat, _MODEL_DIR)
        if m is None:
            return None
        return _inv_pp(stat, m.predict(X))
    models = load_pergame_model(stat, _MODEL_DIR)
    if not models:
        return None
    parts = []
    for entry in models:
        if isinstance(entry, tuple):
            scaler, m = entry
            parts.append(m.predict(scaler.transform(X)))
        else:
            parts.append(entry.predict(X))
    parts = [_inv_pp(stat, p) for p in parts]
    wmap_path = os.path.join(_MODEL_DIR, _META_WEIGHTS_FILENAME)
    try:
        with open(wmap_path, encoding="utf-8") as f:
            wmap = json.load(f)
    except Exception:
        wmap = {}
    w = wmap.get(stat) or {}
    if len(parts) == 3:
        blend = (float(w.get("w_xgb", 1/3)) * parts[0]
                 + float(w.get("w_lgb", 1/3)) * parts[1]
                 + float(w.get("w_mlp", 1/3)) * parts[2])
    else:
        blend = np.mean(np.column_stack(parts), axis=1)
    return np.clip(blend, 0.0, None)


def _bulk_predict_quantiles(stat: str, X: np.ndarray):
    """Returns (q10_arr, q50_arr, q90_arr) calibrated, or None if any model missing."""
    models = load_quantile_models(stat, _MODEL_DIR)
    if not models or 0.1 not in models or 0.5 not in models or 0.9 not in models:
        return None
    q10 = _qinv(stat, models[0.1].predict(X))
    q50 = _qinv(stat, models[0.5].predict(X))
    q90 = _qinv(stat, models[0.9].predict(X))
    # Apply per-stat calibration row-wise. apply() returns (cal_q10, cal_q90).
    q10_c = np.empty_like(q10); q90_c = np.empty_like(q90)
    for i in range(len(q10)):
        cq10, cq90 = apply_quant_cal(stat, float(q10[i]), float(q50[i]), float(q90[i]))
        q10_c[i] = cq10; q90_c[i] = cq90
    return q10_c, q50, q90_c


def _hit_prob_normal_vec(pred, line, q10, q90, side):
    sigma = np.maximum(1e-6, (q90 - q10) / 2.5631)
    z = (line - pred) / sigma
    p_under = 0.5 * (1.0 + np.vectorize(lambda x: erf(x / sqrt(2)))(z))
    return 1.0 - p_under if side == "OVER" else p_under


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold-edge", type=float, default=0.0,
                    help="Only bet when |edge| > threshold (stat units). Default 0.")
    ap.add_argument("--bias", type=float, default=0.0,
                    help="Bias coefficient: line = L5 * (1 + bias). Cycle-30 smart-line ~0. "
                         "Defaults 0 (pure L5).")
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--kelly", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n={n} holdout={len(holdout)} ({time.time()-t0:.1f}s)\n", flush=True)

    per_stat = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0,
                                    "stake": 0.0})
    n_bets = 0; n_wins = 0; pnl = 0.0; stake_total = 0.0
    bankroll = args.bankroll; peak = bankroll; max_dd = 0.0

    for stat in STATS:
        ts = time.time()
        pred = _bulk_predict_pred(stat, X)
        qres = _bulk_predict_quantiles(stat, X)
        if pred is None or qres is None:
            print(f"  [{stat}] models missing, skipping")
            continue
        q10, _q50, q90 = qres
        actual = np.array([float(r.get(f"target_{stat}", 0.0) or 0.0)
                           for r in holdout], dtype=float)
        l5 = np.array([float(r.get(f"l5_{stat}", 0.0) or 0.0)
                       for r in holdout], dtype=float)
        line = l5 * (1.0 + args.bias)
        # Only rows with positive L5 contribute (no synthetic line otherwise).
        valid = l5 > 0.0
        edge = pred - line
        thresh = abs(edge) >= args.threshold_edge
        candidate = valid & thresh
        # Decide side per row (vectorized)
        side_over = (edge > 0) & candidate
        side_under = (edge < 0) & candidate
        odds = -110
        payout = _american_payout(odds, 1.0)
        prob_over = _hit_prob_normal_vec(pred, line, q10, q90, "OVER")
        prob_under = 1.0 - prob_over
        ev_over = prob_over * payout - (1.0 - prob_over) * 1.0
        ev_under = prob_under * payout - (1.0 - prob_under) * 1.0
        bet_over = side_over & (ev_over > 0)
        bet_under = side_under & (ev_under > 0)

        # Materialize bets row by row (Kelly compounding can't be vectorized).
        stat_count = 0
        for i in range(len(holdout)):
            if bet_over[i]:
                prob = float(prob_over[i]); side = "OVER"
            elif bet_under[i]:
                prob = float(prob_under[i]); side = "UNDER"
            else:
                continue
            if args.kelly:
                kf = _kelly(prob, odds)
                stake = round(kf * bankroll, 2)
                if stake <= 0:
                    continue
            else:
                stake = 1.0
            p = _settle(side, float(line[i]), float(actual[i]), odds, stake)
            pnl += p; stake_total += stake; n_bets += 1; stat_count += 1
            if p > 0: n_wins += 1
            bankroll += p
            peak = max(peak, bankroll); max_dd = max(max_dd, peak - bankroll)
            ps = per_stat[stat]
            ps["n"] += 1; ps["wins"] += int(p > 0)
            ps["pnl"] += p; ps["stake"] += stake
        print(f"  [{stat}] {stat_count} bets in {time.time()-ts:.1f}s", flush=True)

    if n_bets == 0:
        print("\nNo bets passed --threshold-edge / EV filter.")
        return 0
    roi = 100.0 * pnl / stake_total
    win_pct = 100.0 * n_wins / n_bets
    selectivity = 100.0 * n_bets / (len(holdout) * len(STATS))
    print(f"\n== Synthetic backtest validation (L5 * (1+{args.bias}), threshold {args.threshold_edge}) ==")
    print(f"Holdout: {len(holdout)} game-rows  |  Bets placed: {n_bets}  |  "
          f"Selectivity: {selectivity:.2f}%")
    print(f"Won: {n_wins}/{n_bets} = {win_pct:.1f}%  |  ROI: {roi:+.2f}%  |  "
          f"Max DD: -${max_dd:.2f}")
    print(f"Total P&L: ${pnl:+.2f}  |  Final bankroll: ${bankroll:.2f}")
    print("\nPer-stat breakdown:")
    for stat in STATS:
        ps = per_stat.get(stat)
        if not ps or ps["n"] == 0:
            continue
        hr = 100.0 * ps["wins"] / ps["n"]
        sr = 100.0 * ps["pnl"] / ps["stake"] if ps["stake"] else 0.0
        print(f"  {stat.upper():4s} bets={ps['n']:5d} hit={hr:5.1f}%  "
              f"roi={sr:+6.2f}%  pnl={ps['pnl']:+.2f}")
    print(f"\nTotal runtime: {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
