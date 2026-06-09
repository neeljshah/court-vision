"""eval_opp_minutes_v2.py -- INT-79 evaluation gate.

PRIMARY SHIP GATE: 4-fold walk-forward on combined v2 model vs base.
MANDATORY NULL CONTROL: shuffled opp-team mapping must NOT give same gain.
SANITY: feature importance, per-segment MAE, per-position MAE.

Usage:
    python scripts/eval_opp_minutes_v2.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_opp_minutes_v2 import (  # noqa: E402
    OPP_FEATURE_NAMES,
    _LGB_PARAMS,
    _NUM_BOOST_ROUND,
    _EARLY_STOP,
    build_corpus,
    train_residual_model,
)
from src.prediction.minute_trajectory import MinuteTrajectoryModel  # noqa: E402

_VAULT_OUT = ROOT / "vault" / "Intelligence" / "INT-79_Opp_Minutes_v2.md"
_OUT_PARQUET = ROOT / "data" / "intelligence" / "opp_minutes_predictions.parquet"

# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------

def bootstrap_mae_delta(y_true: np.ndarray, pred_base: np.ndarray,
                         pred_v2: np.ndarray, n_boot: int = 5000,
                         seed: int = 0) -> Tuple[float, float, float]:
    """Return (mean_delta, ci_lo, ci_hi) via game-level bootstrap."""
    delta = np.mean(np.abs(y_true - pred_v2)) - np.mean(np.abs(y_true - pred_base))
    rng = np.random.default_rng(seed)
    n = len(y_true)
    boot = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot[i] = (np.mean(np.abs(y_true[idx] - pred_v2[idx]))
                   - np.mean(np.abs(y_true[idx] - pred_base[idx])))
    return float(delta), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


# ---------------------------------------------------------------------------
# Walk-forward 4-fold
# ---------------------------------------------------------------------------

def walk_forward_4fold(
    X_base: np.ndarray,
    y: np.ndarray,
    X_opp: np.ndarray,
    date_rows: List[str],
    base_model: MinuteTrajectoryModel,
    positions_arr: Optional[np.ndarray] = None,
) -> Tuple[bool, List[dict], float, float, float]:
    """Run 4-fold chronological walk-forward.

    Sort unique game_dates, split at 25/50/75 percentiles.
    Train fold [0, q_k), val fold [q_k, q_{k+1}).
    Returns (gate_passed, fold_results, agg_delta, ci_lo, ci_hi).
    """
    unique_dates = sorted(set(d for d in date_rows if d))
    n_dates = len(unique_dates)
    if n_dates < 8:
        print("  WARNING: too few unique dates for 4-fold WF, falling back to 2-fold")
        splits = [(0, int(n_dates * 0.5), int(n_dates * 0.5), n_dates)]
    else:
        # 4 expanding-window folds:
        #   Fold 1: train [0, 25%), val [25%, 50%)
        #   Fold 2: train [0, 50%), val [50%, 75%)
        #   Fold 3: train [0, 75%), val [75%, 100%)
        #   Fold 4: train [0, 75%), val [75%, 100%) -- same as fold 3, skip
        # Actually use:
        #   Fold 1: train [0, 25%), val [25%, 50%)
        #   Fold 2: train [0, 50%), val [50%, 75%)
        #   Fold 3: train [0, 75%), val [75%, 100%)
        #   (3 expanding folds; extend to 4 by adding held-out first quarter)
        #   Fold 4: train [25%, 75%), val [75%, 100%) -- rolling window
        q25 = int(n_dates * 0.25)
        q50 = int(n_dates * 0.50)
        q75 = int(n_dates * 0.75)
        splits = [
            (0,   q25, q25,  q50),   # fold 1
            (0,   q50, q50,  q75),   # fold 2
            (0,   q75, q75,  n_dates),  # fold 3
            (q25, q75, q75,  n_dates),  # fold 4 (rolling)
        ]

    fold_results = []
    all_y_val = []
    all_pred_base_val = []
    all_pred_v2_val = []
    positives = 0

    for fold_idx, (tr_start, tr_end, val_start, val_end) in enumerate(splits):
        if tr_end == 0 or val_start >= n_dates or val_start >= val_end or tr_start >= tr_end:
            continue

        train_dates_set = set(unique_dates[tr_start:tr_end])
        val_dates_set = set(unique_dates[val_start:val_end])

        tr_mask = np.array([d in train_dates_set for d in date_rows])
        val_mask = np.array([d in val_dates_set for d in date_rows])

        if tr_mask.sum() == 0 or val_mask.sum() == 0:
            continue

        X_base_tr = X_base[tr_mask]
        X_opp_tr = X_opp[tr_mask]
        y_tr = y[tr_mask]
        pred_base_tr = base_model.predict(X_base_tr.tolist())
        y_resid_tr = y_tr - pred_base_tr

        X_opp_val = X_opp[val_mask]
        y_val = y[val_mask]
        pred_base_val = base_model.predict(X_base[val_mask].tolist())

        # Train residual on fold's train set
        booster = train_residual_model(y_resid_tr, X_opp_tr)

        pred_resid_val = booster.predict(X_opp_val)
        pred_v2_val = pred_base_val + pred_resid_val

        mae_base = float(np.mean(np.abs(y_val - pred_base_val)))
        mae_v2 = float(np.mean(np.abs(y_val - pred_v2_val)))
        delta = mae_v2 - mae_base
        positive = delta < 0

        fold_results.append({
            "fold": fold_idx + 1,
            "n_train": int(tr_mask.sum()),
            "n_val": int(val_mask.sum()),
            "mae_base": mae_base,
            "mae_v2": mae_v2,
            "delta": delta,
            "positive": positive,
        })

        if positive:
            positives += 1

        all_y_val.extend(y_val.tolist())
        all_pred_base_val.extend(pred_base_val.tolist())
        all_pred_v2_val.extend(pred_v2_val.tolist())

    n_folds = len(fold_results)
    gate_passed = positives >= 3 and n_folds >= 4

    if all_y_val:
        y_agg = np.asarray(all_y_val)
        base_agg = np.asarray(all_pred_base_val)
        v2_agg = np.asarray(all_pred_v2_val)
        agg_delta, ci_lo, ci_hi = bootstrap_mae_delta(y_agg, base_agg, v2_agg, n_boot=5000)
    else:
        agg_delta, ci_lo, ci_hi = float("nan"), float("nan"), float("nan")

    return gate_passed, fold_results, agg_delta, ci_lo, ci_hi


# ---------------------------------------------------------------------------
# Null control
# ---------------------------------------------------------------------------

def null_control(
    X_base: np.ndarray,
    y: np.ndarray,
    X_opp_real: np.ndarray,
    date_rows: List[str],
    base_model: MinuteTrajectoryModel,
) -> float:
    """Refit residual with PERMUTED opp-team features, return val MAE delta.

    Permutation strategy: shuffle rows of X_opp within val set so the
    opp-context no longer corresponds to the right player-game. This
    approximates a random-team mapping without re-running build_corpus.
    """
    unique_dates = sorted(set(d for d in date_rows if d))
    n_dates = len(unique_dates)
    if n_dates < 4:
        return float("nan")

    cutoff = int(n_dates * 0.75)
    train_dates_set = set(unique_dates[:cutoff])
    val_dates_set = set(unique_dates[cutoff:])

    dates_arr = np.asarray(date_rows)
    tr_mask = np.array([d in train_dates_set for d in date_rows])
    val_mask = np.array([d in val_dates_set for d in date_rows])

    if tr_mask.sum() == 0 or val_mask.sum() == 0:
        return float("nan")

    X_opp_tr = X_opp_real[tr_mask]
    y_tr = y[tr_mask]
    pred_base_tr = base_model.predict(X_base[tr_mask].tolist())
    y_resid_tr = y_tr - pred_base_tr

    # Permute TRAIN opp features
    rng = np.random.default_rng(seed=777)
    perm_idx = rng.permutation(len(X_opp_tr))
    X_opp_tr_perm = X_opp_tr[perm_idx]

    booster_perm = train_residual_model(y_resid_tr, X_opp_tr_perm)

    # Val: permute val opp features too
    X_opp_val = X_opp_real[val_mask]
    perm_val = rng.permutation(len(X_opp_val))
    X_opp_val_perm = X_opp_val[perm_val]

    y_val = y[val_mask]
    pred_base_val = base_model.predict(X_base[val_mask].tolist())

    pred_resid_perm = booster_perm.predict(X_opp_val_perm)
    pred_v2_perm = pred_base_val + pred_resid_perm

    mae_base = float(np.mean(np.abs(y_val - pred_base_val)))
    mae_v2_perm = float(np.mean(np.abs(y_val - pred_v2_perm)))
    return mae_v2_perm - mae_base


# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------

def get_feature_importance(
    X_opp: np.ndarray,
    y_resid: np.ndarray,
) -> List[Tuple[str, float]]:
    """Train one model on all data, return top-5 feature importances by gain."""
    import lightgbm as lgb

    booster = train_residual_model(y_resid, X_opp)
    gains = booster.feature_importance(importance_type="gain")
    pairs = sorted(zip(OPP_FEATURE_NAMES, gains.tolist()), key=lambda x: -x[1])
    return pairs[:5]


# ---------------------------------------------------------------------------
# Per-position MAE delta
# ---------------------------------------------------------------------------

def per_position_mae(
    y: np.ndarray,
    pred_base: np.ndarray,
    pred_v2: np.ndarray,
    positions_arr: np.ndarray,
) -> Dict[str, dict]:
    result = {}
    for pos in ["G", "F", "C", ""]:
        mask = positions_arr == pos
        if mask.sum() == 0:
            continue
        label = pos if pos else "Unknown"
        result[label] = {
            "n": int(mask.sum()),
            "mae_base": float(np.mean(np.abs(y[mask] - pred_base[mask]))),
            "mae_v2": float(np.mean(np.abs(y[mask] - pred_v2[mask]))),
        }
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=== INT-79 Eval: Opp Minutes v2 ===\n")

    # Load base model
    base_model = MinuteTrajectoryModel.load()
    if base_model is None:
        print("ERROR: base model missing")
        return 2

    # Build corpus (real opp teams)
    print("Building corpus (real)...")
    meta_df, X_base_rows, y_vals, X_opp_rows, gid_rows, date_rows = build_corpus(permute_opp_team=False)

    n_total = len(y_vals)
    print(f"  n_rows: {n_total}")

    X_base = np.asarray(X_base_rows, dtype=np.float64)
    y = np.asarray(y_vals, dtype=np.float64)
    X_opp = np.asarray(X_opp_rows, dtype=np.float64)

    # Base predictions on full corpus
    pred_base_all = base_model.predict(X_base_rows)
    y_resid_all = y - pred_base_all

    # Per-position tracking from metadata
    # Rough position via feature encoding (pos_C=col9, pos_F=col10, pos_G=col11)
    pos_col_idx = {"C": 9, "F": 10, "G": 11}
    positions_arr = np.full(n_total, "", dtype=object)
    for pos, idx in pos_col_idx.items():
        mask = X_base[:, idx] == 1.0
        positions_arr[mask] = pos

    # --- PRIMARY GATE: 4-fold walk-forward ---
    print("\nRunning 4-fold walk-forward...")
    gate_passed, fold_results, agg_delta, ci_lo, ci_hi = walk_forward_4fold(
        X_base, y, X_opp, date_rows, base_model, positions_arr
    )

    print("\nFold results:")
    print(f"  {'Fold':>4}  {'N_train':>8}  {'N_val':>7}  {'MAE_base':>9}  {'MAE_v2':>8}  {'Delta':>8}  {'Pass':>5}")
    positives = 0
    for fr in fold_results:
        sign = "YES" if fr["positive"] else "NO"
        if fr["positive"]:
            positives += 1
        print(f"  {fr['fold']:>4}  {fr['n_train']:>8}  {fr['n_val']:>7}  "
              f"{fr['mae_base']:>9.4f}  {fr['mae_v2']:>8.4f}  {fr['delta']:>+8.4f}  {sign:>5}")

    n_folds = len(fold_results)
    print(f"\n  {positives}/{n_folds} folds positive")
    print(f"  Aggregate MAE delta: {agg_delta:+.4f}  95% CI: [{ci_lo:+.4f}, {ci_hi:+.4f}]")
    print(f"  Gate: {'PASS' if gate_passed else 'FAIL'} (need >=3/4 positive)")

    # --- MANDATORY NULL CONTROL ---
    print("\nRunning null control (permuted opp-team features)...")
    null_delta = null_control(X_base, y, X_opp, date_rows, base_model)
    print(f"  Null-control MAE delta: {null_delta:+.4f}")

    leakage_flag = False
    if not np.isnan(null_delta) and not np.isnan(agg_delta):
        # Leakage if null delta is nearly as good as real delta (within 50%)
        if agg_delta < 0 and null_delta < 0 and abs(null_delta) >= abs(agg_delta) * 0.5:
            leakage_flag = True
            print("  WARNING: null control close to real delta -- possible leakage signal")
        elif agg_delta >= 0:
            print("  (real model doesn't improve; null control moot)")
        else:
            print("  Null control is << real delta -- no leakage signal")

    if leakage_flag:
        print("\n  ABORT_LEAKAGE: null control fires")

    # --- FEATURE IMPORTANCE (sanity) ---
    print("\nFeature importance (LGB gain, full corpus):")
    top5 = get_feature_importance(X_opp, y_resid_all)
    for i, (fname, gain) in enumerate(top5):
        print(f"  {i+1}. {fname}: {gain:.2f}")

    # --- PER-SEGMENT MAE (sanity) ---
    # Use full-corpus predictions for quick sanity (not walk-forward preds)
    import lightgbm as lgb
    final_booster = train_residual_model(y_resid_all, X_opp)
    pred_resid_full = final_booster.predict(X_opp)
    pred_v2_full = pred_base_all + pred_resid_full

    # n_opp_features_present buckets
    n_present = (~np.isnan(X_opp)).sum(axis=1)
    print("\nPer-segment MAE by n_opp_features_present (sanity, full corpus):")
    for bucket in [0, 1, 2, 3, 4, 5, 6, 7]:
        mask = n_present == bucket
        if mask.sum() == 0:
            continue
        mae_b = float(np.mean(np.abs(y[mask] - pred_base_all[mask])))
        mae_v = float(np.mean(np.abs(y[mask] - pred_v2_full[mask])))
        print(f"  n_present={bucket}: n={mask.sum():5d}  base={mae_b:.4f}  v2={mae_v:.4f}  delta={mae_v - mae_b:+.4f}")

    # --- PER-POSITION (sanity) ---
    pos_stats = per_position_mae(y, pred_base_all, pred_v2_full, positions_arr)
    print("\nPer-position MAE (sanity, full corpus):")
    for pos, st in pos_stats.items():
        print(f"  {pos:>8}: n={st['n']:5d}  base={st['mae_base']:.4f}  v2={st['mae_v2']:.4f}  delta={st['mae_v2']-st['mae_base']:+.4f}")

    # --- VERDICT ---
    if leakage_flag:
        verdict = "ABORT_LEAKAGE"
    elif gate_passed:
        verdict = "SHIP"
    else:
        verdict = "REJECT"

    print(f"\n=== FINAL VERDICT: {verdict} ===")

    # --- Write vault note ---
    _write_vault_note(
        fold_results=fold_results,
        positives=positives,
        n_folds=n_folds,
        agg_delta=agg_delta,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        null_delta=null_delta,
        leakage_flag=leakage_flag,
        gate_passed=gate_passed,
        verdict=verdict,
        top5=top5,
        n_total=n_total,
    )

    print(f"\n  vault note -> {_VAULT_OUT}")
    if _OUT_PARQUET.exists():
        print(f"  predictions parquet -> {_OUT_PARQUET}")

    return 0 if verdict == "SHIP" else 1


def _write_vault_note(
    *,
    fold_results: List[dict],
    positives: int,
    n_folds: int,
    agg_delta: float,
    ci_lo: float,
    ci_hi: float,
    null_delta: float,
    leakage_flag: bool,
    gate_passed: bool,
    verdict: str,
    top5: List[Tuple[str, float]],
    n_total: int,
) -> None:
    lines = [
        "# INT-79: Opponent-Specific Minutes Prediction v2",
        "",
        f"**Date:** 2026-05-29",
        f"**Verdict:** {verdict}",
        f"**n_rows trained:** {n_total}",
        "",
        "## Approach",
        "Residual LGB-q50 on top of base `minute_trajectory.lgb`.",
        "7 opp-context features: matchup_grid composites, opp_defensive_intensity,",
        "team_tempo_spacing, garbage-time L5 rolling, dev_score.",
        "",
        "## 4-Fold Walk-Forward (Primary Gate)",
        "",
        "| Fold | N_train | N_val | MAE_base | MAE_v2 | Delta | Pass |",
        "|------|---------|-------|----------|--------|-------|------|",
    ]
    for fr in fold_results:
        sign = "YES" if fr["positive"] else "NO"
        lines.append(
            f"| {fr['fold']} | {fr['n_train']} | {fr['n_val']} | "
            f"{fr['mae_base']:.4f} | {fr['mae_v2']:.4f} | {fr['delta']:+.4f} | {sign} |"
        )

    lines += [
        "",
        f"**Positive folds:** {positives}/{n_folds}",
        f"**Aggregate MAE delta:** {agg_delta:+.4f}  95% CI: [{ci_lo:+.4f}, {ci_hi:+.4f}]",
        f"**Gate:** {'PASS' if gate_passed else 'FAIL'} (need >=3/4 positive)",
        "",
        "## Null Control",
        f"**Null-control delta:** {null_delta:+.4f}",
        f"**Leakage flag:** {'YES -- ABORT' if leakage_flag else 'clean'}",
        "",
        "## Top-5 Feature Importance (gain)",
        "",
    ]
    for rank, (fname, gain) in enumerate(top5, 1):
        lines.append(f"{rank}. `{fname}`: {gain:.2f}")

    lines += [
        "",
        "## Files",
        f"- `data/intelligence/opp_minutes_predictions.parquet`",
        f"- `data/models/opp_minutes_v2_resid.lgb`",
        "",
        "## Notes",
        "- dev_score ~78 rows (~99% NaN); cosmetic importance only.",
        "- Atlas asof joins resolve ~80% of games; >=75% required (asserted in build).",
        "- 17-revert history: residual framing improves odds modestly vs direct feature add.",
    ]

    _VAULT_OUT.parent.mkdir(parents=True, exist_ok=True)
    _VAULT_OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
