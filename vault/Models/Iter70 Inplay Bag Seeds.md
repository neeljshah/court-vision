# Iter 70 — Inplay Bag-of-5-Seeds Ensemble

**Date:** 2026-05-28
**Probe script:** `scripts/iter70_inplay_bagseeds.py`
**Results JSON:** `data/cache/iter70_inplay_bagseeds_results.json`

## Hypothesis

Single-seed LGB trees at small leaf counts (`num_leaves=15` from Iter 68 v6_hp
winners) are noisy. A 5-seed mean (arithmetic average of `predict_proba`)
reduces variance with no overfit cost. Cheap, no-feature-additions improvement.

## Method

- Mirror Iter 68 data pipeline (linescores + season_games + quarter_features).
- Iter 68 v6_hp winning HPs per snapshot:
  - endQ1: `lr=0.03 nl=15 mcs=40`
  - endQ2: `lr=0.03 nl=15 mcs=40`
  - endQ3: `lr=0.03 nl=15 mcs=10`
- 5 seeds: `{42, 7, 13, 23, 99}`.
- 4-fold expanding-window walk-forward (60% minimum train, equal-size test
  folds). Per fold, train 5 LGB models then average their probabilities.
- Compare bag-of-5 fold Brier to **single-seed v6_hp fold Brier**
  (from `iter68_inplay_hpsweep_results.json` → winner.fold_briers).

## Ship gate

- Bag-mean Brier ≤ single-seed v6_hp Brier on ≥3/4 folds, AND
- Mean Brier delta ≤ -0.001.

## Results (per-fold bag vs v6_hp)

| Snap   | v6_hp mean | Bag5 mean | Mean Δ   | Folds improved | Ship |
|--------|-----------:|----------:|---------:|---------------:|:----:|
| endQ1  | 0.2120     | 0.2122    | +0.0002  | 2/4            | no   |
| endQ2  | 0.1771     | 0.1760    | -0.0010  | 4/4            | YES  |
| endQ3  | 0.1250     | 0.1253    | +0.0003  | 1/4            | no   |

### Per-fold detail

**endQ1**: f0 -0.0007 ✓, f1 +0.0003 ✗, f2 +0.0017 ✗, f3 -0.0005 ✓
**endQ2**: f0 -0.0007 ✓, f1 -0.0006 ✓, f2 -0.0009 ✓, f3 -0.0019 ✓
**endQ3**: f0 -0.0010 ✓, f1 +0.0013 ✗, f2 +0.0004 ✗, f3 +0.0006 ✗

## Decision

**SHIP endQ2 only.** Save 5 seeded retrained-on-full-data .lgb files:

- `inplay_winprob_endq2_v7_bag5_seed{0..4}.lgb` (+ `_meta.json` each)

endQ1 and endQ3 fail the ship gate — bag variance reduction is real on endQ2
but does not help endQ1/endQ3 single-seed v6_hp at the chosen seeds. The
per-seed Brier spread is small (~0.0005–0.0040 across seeds on most folds),
confirming the underlying signal at v6_hp HPs is already low-variance.

## pkl integrity checks

All 5 saved endQ2 seed files passed:
`booster.num_feature() = 9 == len(meta["feature_cols"]) = 9` for every seed.

## Notes

- Production `_v6_hp.lgb`, `_v6_hp_meta.json`, base `.lgb`, base `_meta.json`,
  and `inplay_isotonic_*.joblib` were not touched.
- Inference path needs a wiring step (separate iter) to load all 5 seed files
  and average. For now, the artifacts exist as drop-in candidates.
- Lesson: bagging-by-seed helps when single-seed variance dominates — endQ2
  has the most categorical-cardinality noise (`q2_delta` adds another path
  through the same `nl=15` tree budget), so seed-noise reduction helps most
  there. endQ1 (8 features, low capacity ceiling) and endQ3 (13 features,
  high-information regime) are already near their irreducible-noise floor.
