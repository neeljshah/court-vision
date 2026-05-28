# Iter 67 — Inplay Dual-Stage Calibration (Platt + Isotonic)

**Status:** REVERT (no snapshot ships)
**Date:** 2026-05-28
**Depends on:** [[Iter62 Inplay Isotonic Calibration]] (commit eb0f8315)

## Hypothesis
Pure isotonic ([[Iter62 Inplay Isotonic Calibration]]) over-corrects on small
tail bins (n=10-40) for endQ2/Q3, producing only marginal Brier wins (-0.0017,
-0.0011) that don't clear the ship gate. A Platt sigmoid first (de-noises with
a parametric monotone fit) then isotonic on top (corrects residual non-linearity)
should preserve monotonicity AND smooth the tails.

## Method
For each snapshot (endQ1/Q2/Q3) and each WF fold:
- Train fresh LGBM model on prior data (same 4-fold expanding split as Iter 62).
- For folds 1-3: fit calibrators on the accumulated OOS preds from prior folds.
  - **iso:** IsotonicRegression(out_of_bounds='clip') on raw -> labels (Iter-62 method).
  - **dual:** LogisticRegression(C=1.0, lbfgs) on raw logit -> labels (Platt),
    then IsotonicRegression(out_of_bounds='clip') on Platt(raw) -> labels.
- Per-fold Brier: raw / iso / dual.

## Result (mean Brier across cal folds 1+2+3)

| Snapshot | raw    | iso    | dual   | delta dual vs best | folds improved |
|----------|--------|--------|--------|---------------------|-----------------|
| endQ1    | 0.2228 | 0.2160 | 0.2160 | +0.0000             | 1/3             |
| endQ2    | 0.1884 | 0.1868 | 0.1868 | -0.0000             | 2/3             |
| endQ3    | 0.1414 | 0.1403 | 0.1403 | -0.0000             | 1/3             |

Aggregate mean delta_dual_vs_best across snapshots: **-0.0000** (no movement).

## Ship gate
- Required: dual beats best-of-(raw, iso) by >= 0.001 mean Brier AND >=2/3 cal folds improve.
- All 3 snapshots: dual is mathematically identical to iso to 4 decimals (deltas at e-5 scale).
- **All REVERT.**

## Why it failed (root cause)
Isotonic regression is the most flexible monotone calibrator possible (any
monotone non-decreasing step function). Composing a strictly-monotone Platt
sigmoid in front and re-fitting isotonic on the warped scale produces the
**exact same final mapping** as fitting isotonic on raw. Both reduce to "find
the monotone step function that best matches OOS labels"; the Platt prefix is
just a re-parameterization isotonic can absorb.

Where Platt+iso DOES differ from pure iso is when the second stage is **also
parametric** (e.g. Platt -> Platt, or beta calibration) — that gives the
parametric prior a chance to dominate noisy tails. Pure-isotonic second stage
inherits all of iso's small-n tail volatility.

## Conclusion
Dual-stage **Platt -> isotonic** is mathematically equivalent to pure isotonic
on OOS calibration data. To meaningfully improve over Iter 62, future work
should try:
1. **Platt -> Platt** (parametric second stage smooths tails).
2. **Beta calibration** (3-parameter, naturally damps extremes).
3. **Bin-pooling isotonic** with min_samples_per_bin>=N to suppress small-tail flips.

## Files
- `scripts/iter67_inplay_dual_calibration.py`
- `data/models/inplay_dualcal_endq{1,2,3}.joblib` (saved for reference; do not wire)
- `data/cache/iter67_inplay_dualcal_results.json`
