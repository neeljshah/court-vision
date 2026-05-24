"""validate_adjustment.py — empirical MAE-delta test for a proposed adjustment.

This script answers the question every cycle proposing a feature transform
or post-prediction scaling should answer BEFORE shipping:

    "Does this adjustment actually improve holdout MAE, or am I shipping
     a plausible-sounding heuristic that does nothing (or harms)?"

It loads the same 80/20 chronological holdout that prop_pergame uses,
runs the production-dispatch prediction path per stat (cycle 48 logic),
applies a user-supplied adjustment function, and reports the MAE delta.

Limitations (honest):
- WE DON'T HAVE HISTORICAL LINEUP-STATUS DATA per game. Rotowire scraping
  started cycle 61, so cycle 66/67 scale-by-status CAN'T be empirically
  validated against past games — only forward-validated as data accumulates.
- WHAT WE CAN VALIDATE: adjustments derivable from existing dataset
  features (prev_min, l5_min, opp_def_*, etc.) OR constant-factor scalings.
  The 'minute-ratio proxy' built-in tests scale-by-status by using
  prev_min/l10_min as a proxy for "tonight's reduced role".

Built-in adjustment functions (importable):
- no_op                          # control / sanity check (should report 0 delta)
- scale_constant(factor)         # global scale
- scale_by_min_ratio(low, mid, high, factor_low, factor_mid)
                                  # the cycle-66/67-analog proxy

Run:
    python scripts/validate_adjustment.py                   # no-op baseline check
    python scripts/validate_adjustment.py --adjust min_ratio
    python scripts/validate_adjustment.py --adjust constant --factor 0.95
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from typing import Callable, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _USE_Q50_STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    _MODEL_DIR, _META_WEIGHTS_FILENAME,
    apply_garbage_time_haircut,
    build_pergame_dataset, feature_columns,
    _load_q50_model, load_pergame_model,
)


# ── adjustment functions ─────────────────────────────────────────────────────
#
# Each takes a single (predictions_array, holdout_rows, stat) and returns
# adjusted_predictions_array of the same length. They DO NOT touch feature
# rows because the production prediction path is what we want to test —
# we adjust the OUTPUTS post-prediction here.

AdjustFn = Callable[[np.ndarray, List[dict], str], np.ndarray]


def no_op(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
    """Control. Returns predictions unchanged. Validator MAE delta must be 0."""
    return pred.copy()


def make_scale_constant(factor: float) -> AdjustFn:
    """Scale every prediction by a constant factor (sanity check / baseline shift)."""
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        return np.clip(pred * factor, 0.0, None)
    return fn


def make_pull_to_l5(weight: float = 0.3) -> AdjustFn:
    """Cycle 81 probe. Pull each prediction toward the player's L5 average:
        adjusted = (1 - weight) * pred + weight * l5_<stat>
    Hypothesis: model overshoots; pulling toward player baseline reduces MAE.
    """
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        l5_key = f"l5_{stat}"
        out = pred.copy()
        for i, r in enumerate(rows):
            l5 = r.get(l5_key)
            if l5 is None:
                continue
            try:
                l5f = float(l5)
            except (TypeError, ValueError):
                continue
            out[i] = (1.0 - weight) * pred[i] + weight * l5f
        return np.clip(out, 0.0, None)
    return fn


def make_pull_to_l10(weight: float = 0.3) -> AdjustFn:
    """Cycle 81 probe. L10 variant of pull_to_l5 — less noisy player baseline."""
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        l10_key = f"l10_{stat}"
        out = pred.copy()
        for i, r in enumerate(rows):
            l10 = r.get(l10_key)
            if l10 is None:
                continue
            try:
                l10f = float(l10)
            except (TypeError, ValueError):
                continue
            out[i] = (1.0 - weight) * pred[i] + weight * l10f
        return np.clip(out, 0.0, None)
    return fn


def make_pull_l10_when_low_pred(weight: float = 0.3, threshold: float = 8.0) -> AdjustFn:
    """Cycle 84 probe. Strata showed low-prediction players have higher
    RELATIVE error (3.55 MAE at pred<8 is ~45% relative; 6.35 at pred>22 is ~30%).
    Hypothesis: low-prediction players are inconsistent — pulling them toward
    their L10 average should be more stable than the model's point estimate.
    Test: only apply pull when pred < threshold.
    """
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        l10_key = f"l10_{stat}"
        out = pred.copy()
        for i, r in enumerate(rows):
            if pred[i] >= threshold:
                continue
            l10 = r.get(l10_key)
            if l10 is None:
                continue
            try:
                l10f = float(l10)
            except (TypeError, ValueError):
                continue
            out[i] = (1.0 - weight) * pred[i] + weight * l10f
        return np.clip(out, 0.0, None)
    return fn


def make_b2b_penalty(factor: float = 0.96) -> AdjustFn:
    """Back-to-back games typically see reduced player output (fatigue).

    Cycle 82 fix: uses `is_b2b` field — the cycle-81 attempt checked
    non-existent `home_back_to_back` / `away_back_to_back` fields and the
    adjustment never fired. The dataset has PER-PLAYER rest (rest_days,
    days_since_last_game, is_b2b), NOT per-team home/away rest.
    """
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        out = pred.copy()
        for i, r in enumerate(rows):
            try:
                b2b = float(r.get("is_b2b", 0) or 0)
            except (TypeError, ValueError):
                continue
            if b2b >= 0.5:
                out[i] = pred[i] * factor
        return np.clip(out, 0.0, None)
    return fn


def make_scale_by_min_ratio(
    low_thr: float = 0.5,
    mid_thr: float = 0.9,
    factor_low: float = 0.50,
    factor_mid: float = 0.85,
) -> AdjustFn:
    """Cycle-66/67 analog. Uses prev_min / l10_min as a proxy for tonight's role.

    Note: prev_min is the PREVIOUS game's minutes, not tonight's. So this is
    only a forward-looking proxy if the previous game was the most recent
    indicator of usage. Imperfect but the closest dataset proxy.

    Buckets:
        ratio < low_thr  -> "limited / bench-ish" -> factor_low (default 0.50)
        ratio < mid_thr  -> "questionable-ish"    -> factor_mid (default 0.85)
        otherwise        -> "starter"             -> 1.00 (no scaling)

    Default thresholds correspond loosely to cycle-66 scale-by-status buckets.
    """
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        out = pred.copy()
        for i, r in enumerate(rows):
            try:
                prev_m = float(r.get("prev_min", 0.0) or 0.0)
                l10_m = float(r.get("l10_min", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if l10_m <= 0:
                continue
            ratio = prev_m / l10_m
            if ratio < low_thr:
                out[i] = pred[i] * factor_low
            elif ratio < mid_thr:
                out[i] = pred[i] * factor_mid
            # else: no scaling
        return np.clip(out, 0.0, None)
    return fn


# ── production-path bulk predict (mirrors cycle 48 verify_production_mae) ────

def _inv_pp(stat: str, v: np.ndarray) -> np.ndarray:
    if stat in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return v


def _bulk_predict(stat: str, X: np.ndarray) -> Optional[np.ndarray]:
    """Production dispatch: q50 model for _USE_Q50_STATS, NNLS blend else."""
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


def validate(adjust_fn: AdjustFn,
             holdout: List[dict],
             X: np.ndarray,
             stats: List[str] = STATS) -> Dict[str, Dict[str, float]]:
    """Run baseline + adjusted MAE per stat; return per-stat result dict.

    For each stat:
      baseline_mae    = MAE of production prediction vs target
      adjusted_mae    = MAE of adjust_fn(production prediction) vs target
      delta_mae       = adjusted - baseline (negative = improvement)
      n               = rows considered (excludes rows with NaN target)

    Cycle 97a (loop 5): the production prediction path now applies the T1-A
    garbage-time haircut (apply_garbage_time_haircut) after the q50/blend
    dispatch. Mirroring it here keeps the no-op baseline numerically aligned
    with cycle-96a anchors (PTS 4.6104 etc.) — without it the validator
    reported the pre-haircut blend MAE (PTS 4.6221) and any probe layered
    ON TOP of the haircut would be measured against the wrong baseline.
    """
    spreads = [r.get("home_spread") for r in holdout]
    results: Dict[str, Dict[str, float]] = {}
    for stat in stats:
        # BUG fixed: previous `r.get(...) or np.nan` evaluated `0.0 or nan`
        # as nan because Python treats 0.0 as falsy. That excluded every
        # game where a player had 0 BLK / 0 STL / etc — the most-common
        # case — and inflated MAE for sparse stats (BLK went 0.44 -> 1.19).
        y_true = np.array([
            np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
            for r in holdout
        ], dtype=float)
        mask = ~np.isnan(y_true)
        pred = _bulk_predict(stat, X)
        if pred is None:
            results[stat] = {"baseline_mae": float("nan"),
                              "adjusted_mae": float("nan"),
                              "delta_mae": float("nan"),
                              "n": 0}
            continue
        # Cycle 97a — vectorised mirror of predict_pergame's haircut step.
        pred = np.array([apply_garbage_time_haircut(float(p), stat, hs)
                         for p, hs in zip(pred, spreads)], dtype=float)
        adj = adjust_fn(pred, holdout, stat)
        bm = float(np.mean(np.abs(pred[mask] - y_true[mask])))
        am = float(np.mean(np.abs(adj[mask] - y_true[mask])))
        results[stat] = {
            "baseline_mae": bm,
            "adjusted_mae": am,
            "delta_mae":    am - bm,
            "n":            int(mask.sum()),
        }
    return results


def print_report(name: str, results: Dict[str, Dict[str, float]]) -> None:
    print(f"\n== {name} ==")
    print(f"{'stat':<5} {'n':>6} {'base_mae':>10} {'adj_mae':>10} {'delta':>10}  verdict")
    print("-" * 60)
    total_delta = 0.0
    n_improved = 0
    for stat in STATS:
        r = results.get(stat)
        if r is None or r["n"] == 0:
            print(f"{stat:<5} (no data)")
            continue
        if np.isnan(r["delta_mae"]):
            print(f"{stat:<5} (model missing)")
            continue
        verdict = "BETTER" if r["delta_mae"] < -0.001 else (
                   "worse" if r["delta_mae"] > 0.001 else "flat")
        if r["delta_mae"] < -0.001:
            n_improved += 1
        total_delta += r["delta_mae"]
        print(f"{stat:<5} {r['n']:>6d} {r['baseline_mae']:>10.4f} "
              f"{r['adjusted_mae']:>10.4f} {r['delta_mae']:>+10.4f}  {verdict}")
    print("-" * 60)
    print(f"  Stats improved: {n_improved}/7   Sum delta: {total_delta:+.4f}")
    if n_improved >= 4 and total_delta < 0:
        print("  VERDICT: improvement signal present — consider shipping with this adjustment.")
    elif n_improved <= 2 or total_delta > 0:
        print("  VERDICT: no empirical improvement — do not ship this adjustment.")
    else:
        print("  VERDICT: mixed — investigate further before shipping.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adjust", choices=["none", "constant", "min_ratio",
                                          "pull_l5", "pull_l10", "b2b",
                                          "pull_l10_low"],
                    default="none")
    ap.add_argument("--threshold", type=float, default=8.0,
                    help="pull_l10_low: apply only when pred < threshold (default 8.0)")
    ap.add_argument("--factor", type=float, default=0.95)
    ap.add_argument("--factor-low", type=float, default=0.50,
                    help="min_ratio: scale for ratio < low_thr (default 0.50)")
    ap.add_argument("--factor-mid", type=float, default=0.85,
                    help="min_ratio: scale for low_thr <= ratio < mid_thr (default 0.85)")
    ap.add_argument("--weight", type=float, default=0.3,
                    help="pull_l5/pull_l10: blending weight (default 0.3)")
    args = ap.parse_args()

    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n={n} holdout={len(holdout)} features={len(cols)}\n", flush=True)

    if args.adjust == "none":
        fn = no_op
        name = "Baseline / no-op (sanity check — delta must be 0.0000)"
    elif args.adjust == "constant":
        fn = make_scale_constant(args.factor)
        name = f"Constant scale {args.factor:.3f}"
    elif args.adjust == "min_ratio":
        fn = make_scale_by_min_ratio(factor_low=args.factor_low,
                                       factor_mid=args.factor_mid)
        name = (f"Min-ratio scaling — prev_min/l10_min<0.5 -> *{args.factor_low:.2f}, "
                f"<0.9 -> *{args.factor_mid:.2f}")
    elif args.adjust == "pull_l5":
        fn = make_pull_to_l5(weight=args.weight)
        name = f"Pull to L5 — pred = {1-args.weight:.2f}*pred + {args.weight:.2f}*l5"
    elif args.adjust == "pull_l10":
        fn = make_pull_to_l10(weight=args.weight)
        name = f"Pull to L10 — pred = {1-args.weight:.2f}*pred + {args.weight:.2f}*l10"
    elif args.adjust == "b2b":
        fn = make_b2b_penalty(factor=args.factor)
        name = f"B2B penalty — back_to_back game * {args.factor:.3f}"
    elif args.adjust == "pull_l10_low":
        fn = make_pull_l10_when_low_pred(weight=args.weight,
                                            threshold=args.threshold)
        name = (f"Pull to L10 ONLY when pred < {args.threshold} "
                f"(weight {args.weight:.2f}) — strata-informed magnitude probe")

    results = validate(fn, holdout, X)
    print_report(name, results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
