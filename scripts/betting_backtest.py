"""betting_backtest.py — synthetic-line backtest for prop predictions.

Loads the current production prop_pergame stack and computes per-stat
predictions on the chronological holdout slice. For each stat, simulates
sportsbook over/under bets at a range of line offsets from the model's
prediction (line = pred - offset). The OFFSET is the model's *claimed
edge*: bet OVER when offset > 0 (model thinks true value is above the
line by `offset`).

Reports per-stat per-offset:
  n_bets               — holdout games where the bet exists
  hit_rate             — fraction won (actual ended on the right side)
  ev_per_unit          — expected value at standard -110 vig (need 52.4%)
  roi                  — return on stake (cumulative profit / total stake)
  break_even_offset    — smallest |offset| where hit_rate >= 52.4%

This is the cycle-30 honest answer to "are these predictions actually
profitable" without real sportsbook lines. With real closing-line data
we'd swap the synthetic line for the actual close.

Run:
    python scripts/betting_backtest.py
    python scripts/betting_backtest.py --offsets 0.5 1.0 1.5 2.0
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS, _USE_Q50_STATS,
    _Q50_LGB_BACKEND_STATS, _load_q50_model,
    build_pergame_dataset, feature_columns, load_pergame_model,
)


def _invert(stat: str, v):
    if stat in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return np.clip(v, 0.0, None)


def _batch_predict(stat: str, X_ho: np.ndarray, model_dir: str) -> np.ndarray:
    """Vectorised prediction for a stat across all holdout rows.

    Dispatches to the same q50 / blend path as predict_pergame BUT
    operates on the full X matrix at once for speed.
    """
    if stat in _USE_Q50_STATS:
        m = _load_q50_model(stat, model_dir)
        if m is None:
            return None
        # predict returns predictions in TRANSFORMED space (log1p / sqrt / raw)
        preds_t = m.predict(X_ho)
        return _invert(stat, preds_t)

    # Legacy 3-way blend (PTS / REB / AST)
    models = load_pergame_model(stat, model_dir)
    if not models:
        return None
    # Load meta weights
    meta_path = os.path.join(model_dir, "meta_weights_pergame.json")
    weights = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            weights = json.load(f).get(stat, {})
    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))

    xgb_pred = lgb_pred = mlp_pred = None
    for m in models:
        if isinstance(m, tuple):
            scaler, mlp_model = m
            Xs = scaler.transform(X_ho)
            mlp_pred = mlp_model.predict(Xs)
            continue
        cls = type(m).__name__.lower()
        if "xgb" in cls and xgb_pred is None:
            xgb_pred = m.predict(X_ho)
        elif "lgb" in cls and lgb_pred is None:
            lgb_pred = m.predict(X_ho)
    # Inverse-transform each base prediction, then NNLS blend on raw scale.
    parts = []
    if xgb_pred is not None: parts.append(w_xgb * _invert(stat, xgb_pred))
    if lgb_pred is not None: parts.append(w_lgb * _invert(stat, lgb_pred))
    if mlp_pred is not None: parts.append(w_mlp * _invert(stat, mlp_pred))
    if not parts:
        return None
    blend = np.sum(parts, axis=0)
    return np.clip(blend, 0.0, None)


def backtest_stat(stat: str, preds: np.ndarray, actuals: np.ndarray,
                  lines: np.ndarray, thresholds) -> dict:
    """For each model-vs-line edge threshold, simulate prop O/U bets.

    `lines` is a per-game realistic line proxy (typically l5_<stat>, the
    player's last-5-game average — books pin O/U lines very close to this).
    The model's claimed EDGE per game = preds - lines. We bet OVER when
    edge > threshold, UNDER when edge < -threshold, and skip when |edge|
    is below the threshold. This is how a sharp bettor uses the model:
    only bet when projection diverges from the line meaningfully.
    """
    result = {"stat": stat, "n_holdout": len(preds), "by_threshold": []}
    edge = preds - lines
    for thresh in thresholds:
        over_mask = edge > thresh
        under_mask = edge < -thresh
        bet_mask = over_mask | under_mask
        # Win condition: when over_mask AND actual > line; when under_mask AND actual < line
        wins = np.where(over_mask, actuals > lines, np.where(under_mask, actuals < lines, False))
        n_bets = int(bet_mask.sum())
        n_wins = int((wins & bet_mask).sum())
        n_over = int(over_mask.sum()); n_under = int(under_mask.sum())
        hr = n_wins / max(n_bets, 1)
        ev_per_unit = 0.909 * hr - 1.0 * (1 - hr) if n_bets else 0.0
        result["by_threshold"].append({
            "edge_threshold": round(thresh, 3),
            "n_bets":         n_bets,
            "n_over":         n_over,
            "n_under":        n_under,
            "hit_rate":       round(hr, 4) if n_bets else None,
            "ev_per_unit":    round(ev_per_unit, 4),
            "roi_pct":        round(ev_per_unit * 100, 2),
            "bet_pct":        round(100 * n_bets / max(len(preds), 1), 2),
        })
    return result


def find_break_even(per_offset_results) -> float:
    """Smallest |offset| where hit_rate >= 52.4% (break-even at -110)."""
    for r in per_offset_results:
        if r["hit_rate"] >= 0.524:
            return r["offset"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresholds", nargs="+", type=float,
                    default=[0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0])
    ap.add_argument("--holdout-frac", type=float, default=0.2)
    args = ap.parse_args()

    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    ho_start = int(n * (1.0 - args.holdout_frac))
    ho_rows = rows[ho_start:]
    print(f"holdout size: {len(ho_rows)} games (last {args.holdout_frac*100:.0f}%)", flush=True)

    X_ho = np.array([[r[c] for c in fc] for r in ho_rows], dtype=float)
    model_dir = os.path.join(PROJECT_DIR, "data", "models")

    all_results = {}
    print("\n== Backtest vs synthetic line = player's L5 average (book proxy) ==")
    print("== Bet OVER if model pred > line + threshold; UNDER if pred < line - threshold ==")
    for stat in STATS:
        preds = _batch_predict(stat, X_ho, model_dir)
        if preds is None:
            print(f"  {stat.upper()}: no production model")
            continue
        actuals = np.array([r[f"target_{stat}"] for r in ho_rows], dtype=float)
        # Line proxy: player's last-5-game average for this stat
        lines = np.array([r.get(f"l5_{stat}", actuals.mean()) for r in ho_rows], dtype=float)
        res = backtest_stat(stat, preds, actuals, lines, args.thresholds)
        all_results[stat] = res
        print(f"\n  --- {stat.upper()} (mean pred={preds.mean():.2f}, mean line(L5)={lines.mean():.2f}, mean actual={actuals.mean():.2f}) ---")
        print(f"    thresh | n_bets | bet% | hit_rate | EV/unit | ROI%")
        for r in res["by_threshold"]:
            beat = " ***" if (r["hit_rate"] or 0) >= 0.524 and r["n_bets"] > 100 else ""
            hr = f"{r['hit_rate']:.4f}" if r["hit_rate"] is not None else "  n/a"
            print(f"    {r['edge_threshold']:+5.2f}  | {r['n_bets']:6d} | {r['bet_pct']:4.1f} | {hr}  | {r['ev_per_unit']:+.4f} | {r['roi_pct']:+5.2f}{beat}")

    out_path = os.path.join(model_dir, "betting_backtest.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n[done] wrote {out_path}")


if __name__ == "__main__":
    main()
