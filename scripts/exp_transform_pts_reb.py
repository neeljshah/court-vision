"""exp_transform_pts_reb.py — A1 experiment: target-transform / retransformation-bias fix.

Tests whether Jensen/retransformation bias from the production sqrt-huber (PTS) and
log1p (REB) target transforms is responsible for the flat-fan slope<1 pattern, and
whether a corrected inversion (Duan smearing or additive bias correction) or an
alternative transform (identity) reduces OOF MAE vs the production baseline.

Variants tested per stat:
  PTS: identity, sqrt+smear, sqrt+additive, log1p+smear, log1p+additive
  REB: identity, sqrt+smear, sqrt+additive, log1p+smear, log1p+additive

Learner: XGB depth-4 ~600 trees + LightGBM, early-stopped on the va slice,
         blended by NNLS on va preds. Smearing/bias correction fit on TRAIN ONLY
         (per-fold, leak-free).

Usage:
    python scripts/exp_transform_pts_reb.py [--stat pts|reb|both] [--quick]
    --quick: single fold only (smoke-test)
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Tuple, Dict, Optional
import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts._pts_oof_harness import (
    build_folds, feature_matrix, targets, recency_weights,
    load_base, score_and_report,
)

# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------

def _fwd_sqrt(y: np.ndarray) -> np.ndarray:
    return np.sqrt(np.maximum(y, 0.0))

def _fwd_log1p(y: np.ndarray) -> np.ndarray:
    return np.log1p(np.maximum(y, 0.0))

def _fwd_identity(y: np.ndarray) -> np.ndarray:
    return y.copy()

def _inv_sqrt(z: np.ndarray) -> np.ndarray:
    return z ** 2

def _inv_log1p(z: np.ndarray) -> np.ndarray:
    return np.expm1(z)

def _inv_identity(z: np.ndarray) -> np.ndarray:
    return z.copy()


TRANSFORMS = {
    "identity": (_fwd_identity, _inv_identity),
    "sqrt":     (_fwd_sqrt,     _inv_sqrt),
    "log1p":    (_fwd_log1p,    _inv_log1p),
}


def _duan_smear(y_tr_raw: np.ndarray, preds_tr_z: np.ndarray,
                inv_fn) -> float:
    """Multiplicative Duan smearing factor fit on train only.
    s = mean(y_raw) / mean(inv(pred_z_tr))
    Applied to holdout: pred_raw = inv(pred_z_ho) * s
    """
    inv_tr = inv_fn(preds_tr_z)
    denom = np.mean(inv_tr)
    if abs(denom) < 1e-9:
        return 1.0
    return float(np.mean(y_tr_raw) / denom)


def _additive_bias(y_tr_raw: np.ndarray, preds_tr_z: np.ndarray,
                   inv_fn) -> float:
    """Additive bias correction fit on train only.
    c = mean(y_raw - inv(pred_z_tr))
    Applied to holdout: pred_raw = inv(pred_z_ho) + c
    """
    inv_tr = inv_fn(preds_tr_z)
    return float(np.mean(y_tr_raw - inv_tr))


# ---------------------------------------------------------------------------
# Learner
# ---------------------------------------------------------------------------

def _train_blend(X_tr: np.ndarray, y_tr_z: np.ndarray, sw: np.ndarray,
                 X_va: np.ndarray, y_va_z: np.ndarray,
                 X_ho: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Train XGB + LGB on transformed target, blend by NNLS on va, return
    (preds_tr_z, preds_va_z, preds_ho_z)."""
    import xgboost as xgb
    import lightgbm as lgb
    from scipy.optimize import nnls

    # XGBoost
    xm = xgb.XGBRegressor(
        n_estimators=600,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        early_stopping_rounds=30,
        tree_method="hist",
        device="cpu",
        verbosity=0,
    )
    xm.fit(
        X_tr, y_tr_z,
        sample_weight=sw,
        eval_set=[(X_va, y_va_z)],
        verbose=False,
    )
    xgb_tr = xm.predict(X_tr)
    xgb_va = xm.predict(X_va)
    xgb_ho = xm.predict(X_ho)

    # LightGBM
    lm = lgb.LGBMRegressor(
        n_estimators=600,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_samples=20,
        early_stopping_rounds=30,
        verbosity=-1,
    )
    lm.fit(
        X_tr, y_tr_z,
        sample_weight=sw,
        eval_set=[(X_va, y_va_z)],
        callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)],
    )
    lgb_tr = lm.predict(X_tr)
    lgb_va = lm.predict(X_va)
    lgb_ho = lm.predict(X_ho)

    # NNLS blend on va
    Va_stack = np.column_stack([xgb_va, lgb_va])
    coeffs, _ = nnls(Va_stack, y_va_z)
    if coeffs.sum() < 1e-9:
        coeffs = np.array([0.5, 0.5])
    else:
        coeffs = coeffs / coeffs.sum()

    blend_tr = coeffs[0] * xgb_tr + coeffs[1] * lgb_tr
    blend_va = coeffs[0] * xgb_va + coeffs[1] * lgb_va
    blend_ho = coeffs[0] * xgb_ho + coeffs[1] * lgb_ho

    return blend_tr, blend_va, blend_ho


# ---------------------------------------------------------------------------
# Per-variant OOF loop
# ---------------------------------------------------------------------------

def run_variant(stat: str, transform_name: str, correction: str,
                rows: list, folds: list,
                quick: bool = False) -> List[dict]:
    """Run one (transform, correction) variant and return recs list for score_and_report."""
    fwd_fn, inv_fn = TRANSFORMS[transform_name]
    target_key = f"target_{stat}"

    recs: List[dict] = []
    fold_iter = folds[:1] if quick else folds

    for fi, tr_end, va_end, te_end in fold_iter:
        tr = rows[:tr_end]
        va = rows[tr_end:va_end]
        ho = rows[va_end:te_end]

        X_tr, _ = feature_matrix(tr, stat)
        X_va, _ = feature_matrix(va, stat)
        X_ho, _ = feature_matrix(ho, stat)

        y_tr = targets(tr, target_key)
        y_va = targets(va, target_key)

        sw = recency_weights(rows, tr_end)

        # Forward transform
        y_tr_z = fwd_fn(y_tr)
        y_va_z = fwd_fn(y_va)

        # Train blend (in transformed space)
        preds_tr_z, _preds_va_z, preds_ho_z = _train_blend(
            X_tr, y_tr_z, sw, X_va, y_va_z, X_ho
        )

        # Invert to raw space — fit correction on train only
        if correction == "smear":
            factor = _duan_smear(y_tr, preds_tr_z, inv_fn)
            preds_ho_raw = inv_fn(preds_ho_z) * factor
        elif correction == "additive":
            bias = _additive_bias(y_tr, preds_tr_z, inv_fn)
            preds_ho_raw = inv_fn(preds_ho_z) + bias
        elif correction == "none":
            preds_ho_raw = inv_fn(preds_ho_z)
        else:
            raise ValueError(f"Unknown correction: {correction}")

        # Clip to non-negative (stats can't be negative)
        preds_ho_raw = np.maximum(preds_ho_raw, 0.0)

        for r, p in zip(ho, preds_ho_raw):
            recs.append({
                "game_id":   str(r.get("date", ""))[:10],  # use date as unique game_id proxy
                "player_id": int(r.get("player_id", 0)),
                "fold":      fi,
                "pred":      float(p),
            })

    return recs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_stat(stat: str, quick: bool = False) -> Dict:
    """Run all variants for one stat, pick the best, print summary."""
    print(f"\n{'='*70}")
    print(f"  STAT: {stat.upper()}  (quick={quick})")
    print(f"{'='*70}")

    rows, folds = build_folds(stat=stat)
    base = load_base(stat)
    # game_id is blank in the cached baseline — use game_date as join key instead
    # (game_date + player_id + fold is verified unique in the base)
    base = base.copy()
    base["game_id"] = base["game_date"].astype(str).str[:10]

    # Confirm baseline MAE
    import pandas as pd
    mae_base_global = float((base["oof_pred_base"] - base["actual"]).abs().mean())
    print(f"  Baseline cached MAE: {mae_base_global:.4f}")

    # Variant catalogue
    # PTS production transform = sqrt; REB production = log1p
    # We test identity, sqrt+{smear,additive}, log1p+{smear,additive}
    # For identity, "correction=none" is the only sensible option
    variant_specs = [
        ("identity", "none"),
        ("sqrt",     "smear"),
        ("sqrt",     "additive"),
        ("log1p",    "smear"),
        ("log1p",    "additive"),
    ]
    # REB also gets sqrt (production is log1p; sqrt is alternative)
    if stat == "reb":
        variant_specs.append(("sqrt", "none"))   # raw sqrt inversion (no correction)

    results: List[Dict] = []

    for transform_name, correction in variant_specs:
        label = f"{stat}:A1_{transform_name}_{correction}"
        print(f"\n--- Variant: {label} ---")
        try:
            recs = run_variant(stat, transform_name, correction, rows, folds, quick=quick)
            res = score_and_report(recs, base, rows, label=label)
            res["variant"] = f"{transform_name}+{correction}"
            results.append(res)
        except Exception as exc:
            import traceback
            print(f"  VARIANT FAILED: {exc}")
            traceback.print_exc()
            results.append({
                "variant": f"{transform_name}+{correction}",
                "mae_new": float("inf"),
                "mae_base": mae_base_global,
                "delta": float("inf"),
                "pct": float("inf"),
                "pass": False,
                "label": label,
            })

    # Summary table
    print(f"\n{'='*70}")
    print(f"  VARIANT TABLE -- {stat.upper()}")
    print(f"  {'Variant':<25}  {'MAE base':>10}  {'MAE new':>10}  {'Delta':>10}  {'D pct':>8}  {'GATE'}")
    print(f"  {'-'*25}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*6}")
    for r in sorted(results, key=lambda x: x.get("mae_new", float("inf"))):
        mb = r.get("mae_base", float("nan"))
        mn = r.get("mae_new", float("nan"))
        dl = r.get("delta", float("nan"))
        pc = r.get("pct", float("nan"))
        gate = "PASS" if r.get("pass", False) else "FAIL"
        print(f"  {r['variant']:<25}  {mb:>10.4f}  {mn:>10.4f}  {dl:>+10.4f}  {pc:>+7.2f}  {gate}")

    # Best variant
    passing = [r for r in results if r.get("pass", False)]
    if passing:
        best = min(passing, key=lambda x: x.get("mae_new", float("inf")))
        print(f"\n  BEST VARIANT ({stat}): {best['variant']}")
        print(f"  MAE base={best['mae_base']:.4f}  new={best['mae_new']:.4f}  "
              f"delta={best['delta']:+.4f} ({best['pct']:+.2f}%)")
        print(f"  SHIP: {stat.upper()} A1_{best['variant']} — MAE improves by "
              f"{abs(best['pct']):.2f}% vs production baseline.")
    else:
        best = min(results, key=lambda x: x.get("mae_new", float("inf")))
        print(f"\n  BEST VARIANT (non-passing) ({stat}): {best['variant']} "
              f"MAE={best.get('mae_new', float('nan')):.4f}")
        print(f"  REJECT: {stat.upper()} — NO variant beats base MAE={mae_base_global:.4f}. "
              f"Retransformation bias is NOT the cause of the flat fan, or learner "
              f"strength doesn't compensate for smearing noise. Production baseline wins.")

    return {"stat": stat, "results": results, "best": best, "passing": len(passing) > 0}


def write_audit(all_stats_out: list) -> None:
    """Write docs/_audits/PTS_REB_EXP_TRANSFORM.md."""
    import pandas as pd
    out_dir = os.path.join(_ROOT, "docs", "_audits")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "PTS_REB_EXP_TRANSFORM.md")

    lines: List[str] = []
    lines.append("# PTS / REB Target-Transform Experiment (A1)")
    lines.append("")
    lines.append("**Hypothesis:** Jensen / retransformation bias from production sqrt-huber (PTS)")
    lines.append("and log1p (REB) target transforms compresses the high tail → slope<1 flat fan.")
    lines.append("A corrected inversion (Duan smearing or additive bias correction) or identity")
    lines.append("transform may reduce OOF MAE.")
    lines.append("")
    lines.append("**Harness:** `scripts/_pts_oof_harness.py` — exact same fold geometry and baseline")
    lines.append("as the cached production OOF. Learner: XGB depth-4 + LightGBM NNLS-blended,")
    lines.append("early-stopped on va slice. Smearing/bias fit on TRAIN ONLY (leak-free).")
    lines.append("")

    for stat_out in all_stats_out:
        stat = stat_out["stat"]
        results = stat_out["results"]
        best = stat_out["best"]
        passed = stat_out["passing"]

        lines.append(f"## {stat.upper()}")
        lines.append("")
        lines.append("### Variant Table")
        lines.append("")
        lines.append("| Variant | MAE base | MAE new | Delta | Δ% | GATE |")
        lines.append("|---------|----------|---------|-------|----|------|")

        for r in sorted(results, key=lambda x: x.get("mae_new", float("inf"))):
            mb = r.get("mae_base", float("nan"))
            mn = r.get("mae_new", float("nan"))
            dl = r.get("delta", float("nan"))
            pc = r.get("pct", float("nan"))
            gate = "**PASS**" if r.get("pass", False) else "FAIL"
            lines.append(
                f"| {r['variant']} | {mb:.4f} | {mn:.4f} | {dl:+.4f} | {pc:+.2f}% | {gate} |"
            )

        lines.append("")

        # Per-fold and fan come from the best variant's score_and_report output
        # (already printed to stdout — we note reference here)
        lines.append(f"### Best Variant: `{best['variant']}`")
        lines.append("")
        if passed:
            lines.append(
                f"- Overall MAE: base={best['mae_base']:.4f}  new={best['mae_new']:.4f}  "
                f"delta={best['delta']:+.4f} ({best['pct']:+.2f}%)"
            )
            lines.append(
                f"- Slope / fan / per-fold details printed to stdout during run."
            )
            lines.append("")
            lines.append(
                f"**VERDICT: SHIP** — `{stat.upper()}` A1 `{best['variant']}` beats baseline by "
                f"{abs(best['pct']):.2f}%. Retransformation bias correction is effective."
            )
        else:
            lines.append(
                f"- Best non-passing MAE: {best.get('mae_new', float('nan')):.4f} vs base "
                f"{best.get('mae_base', float('nan')):.4f}"
            )
            lines.append("")
            lines.append(
                f"**VERDICT: REJECT** — No transform variant beats the production baseline "
                f"for `{stat.upper()}`. The flat-fan slope<1 pattern is NOT primarily caused by "
                f"Jensen/retransformation bias, or the learner-level variance from the smearing "
                f"correction exceeds the bias gain. Produce model stands."
            )
        lines.append("")

    lines.append("---")
    lines.append("*Generated by `scripts/exp_transform_pts_reb.py`*")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nAudit written -> {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stat", choices=["pts", "reb", "both"], default="both")
    parser.add_argument("--quick", action="store_true",
                        help="Single fold only (smoke-test)")
    args = parser.parse_args()

    stats_to_run = ["pts", "reb"] if args.stat == "both" else [args.stat]

    all_stats_out = []
    for stat in stats_to_run:
        out = run_stat(stat, quick=args.quick)
        all_stats_out.append(out)

    write_audit(all_stats_out)

    print("\n\n========== FINAL SUMMARY ==========")
    for out in all_stats_out:
        stat = out["stat"]
        best = out["best"]
        passed = out["passing"]
        verdict = "SHIP" if passed else "REJECT"
        print(
            f"  {stat.upper()}: {verdict}  best={best['variant']}"
            f"  MAE base={best.get('mae_base', float('nan')):.4f}"
            f"  new={best.get('mae_new', float('nan')):.4f}"
            f"  delta={best.get('delta', float('nan')):+.4f}"
            f" ({best.get('pct', float('nan')):+.2f}%)"
        )
