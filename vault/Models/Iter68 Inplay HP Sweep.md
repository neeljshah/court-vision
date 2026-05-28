# Iter 68 — Inplay HP Sweep (per-snapshot)

**Date:** 2026-05-28
**Status:** SHIP (all 3 snapshots)
**Variant:** `_v6_hp` (alternative for Iter 71 meta-blend; existing `.lgb` files untouched)

## Hypothesis
Production HPs (lr=0.05, num_leaves=31, min_child_samples=20) are global —
never snapshot-tuned. endQ1 has the noisiest signal — tighter regularization
may help endQ1 specifically.

## Grid (27 combos per snapshot)
- `learning_rate ∈ {0.03, 0.05, 0.08}`
- `num_leaves ∈ {15, 31, 63}`
- `min_child_samples ∈ {10, 20, 40}`
- All other HPs frozen at existing meta values. `random_state=42`.

## Method
- Same 4-fold expanding-window WF as `oos_validate_inplay_2026_05_27.py`.
- Same feature matrix (linescores + season_games + quarter_features parquet).
- 324 fold-trainings total (27 × 3 × 4). Elapsed: 40 s.

## Ship gate
- ≥3/4 folds improved AND mean Brier delta ≤ -0.002 vs prod baseline.

## Result — ALL 3 SNAPSHOTS SHIP

| Snap  | Baseline | Winner Brier | Delta    | Folds | HP                            |
|-------|---------:|-------------:|---------:|------:|-------------------------------|
| endQ1 |   0.2221 |       0.2120 |  -0.0101 |   4/4 | lr=0.03 nl=15 mcs=40          |
| endQ2 |   0.1860 |       0.1771 |  -0.0089 |   3/4 | lr=0.03 nl=15 mcs=40          |
| endQ3 |   0.1354 |       0.1250 |  -0.0104 |   4/4 | lr=0.03 nl=15 mcs=10          |

## Key finding
**lr=0.03 + num_leaves=15 dominates every snapshot.** The production model is
over-fit on tree complexity — 31 leaves is too many for an 8-13 feature space
with ~3700 rows. Tighter trees + slower learning rate gain ~5-8% Brier across
the board.

The 0.05/31/20 (production) combo:
- endQ1: delta +0.0000 (2/4 folds improved) — at the noise floor.
- endQ2: delta +0.0000 (2/4) — same.
- endQ3: delta -0.0000 (1/4) — same.

This validates the OOS validator's measurement: production really is sitting
at exactly the trained Brier and the noisier configurations (lr=0.08 / nl=63)
get progressively worse, while tighter configurations gain consistently.

## Artifacts (NEW — production .lgb files UNTOUCHED)
- `data/models/inplay_winprob_endq1_v6_hp.lgb` + `_meta.json` — 8 features, integrity OK
- `data/models/inplay_winprob_endq2_v6_hp.lgb` + `_meta.json` — 9 features, integrity OK
- `data/models/inplay_winprob_endq3_v6_hp.lgb` + `_meta.json` — 13 features, integrity OK
- `data/cache/iter68_inplay_hpsweep_results.json` — full grid + per-fold detail
- `scripts/iter68_inplay_hp_sweep.py` — runner

## PKL integrity
All three saved boosters round-trip: reloaded `lgb.Booster(model_file=…)`,
verified `booster.num_feature()` matches `meta["n_features_in_"]`.

## Next
Iter 71 meta-blend should pick this `_v6_hp` variant alongside the production
`.lgb` and any isotonic-calibrated variants from Iter 62. A simple convex-
combination or stacked logistic on OOS predictions would be the obvious move.
