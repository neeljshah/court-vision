# S309 attempt-2 supplement: gate-order and archive corrections (no estimator change)

This supplement is sealed BEFORE the re-run it governs and is committed ALONE, ahead of any code
or artifact commit. It amends exactly one clause of the sealed attempt-2 preregistration
`docs/evidence/harness/S309_canonical_loss_audit_2026-09-07b_preregistration.md`
(seal `cd9e157abc95c2e699228069bfa40292621fc26f6e48fa0352b3d992e5f69cad`), which stays
byte-identical and remains the governing document for every estimand.

## What does NOT change

No estimator, estimand, denominator, sign convention, seed, bootstrap count, embargo, purge,
grain or bar changes. The candidate is still the frozen S272 low/high-tail isotonic
recalibration and the baseline is still the S272 logistic recalibration. The comparison bar is
still +0.004 and is not moved. The ratio bootstrap is still seed 901 over 10,000 replicates on
game sums and counts. The primary DESIGN-SENSITIVE label is still read only off the
preregistered forward-minus-CPCV paired Brier interval. The headline numbers are therefore
expected to reproduce the attempt-2 memo to the printed digits; any difference is a defect to
report, not a result to keep.

## The one amended clause

The preregistration says attempt 2 "writes only new `2026-09-07b` filenames". Those artifacts
are now committed in `eb6af5982`, and the spec's BAN2 forbids rewriting an existing artifact, so
the corrected re-run writes the new stem `S309_canonical_loss_audit_2026-09-07c`. The
`2026-09-07`, `2026-09-07b`, S272 and S280 artifacts all stay untouched.

## The four corrections this re-run carries

Filed by the verifier against candidate `eb6af5982`:

1. Gate order. `_historical` and the S272 replay asserts run BEFORE `_score` and before any
   source store is read, so a replay error above 1e-12 stops the run with NOT REPRODUCED.
2. Retained aliases. The paired archive retains `p_baseline` and `p_candidate` (the forward,
   deployment-headline arm) beside the new per-arm columns, and every fold record retains the
   attempt-1 field names `fold_date`, `min_test_date`, `max_train_date`, `train_games`,
   `test_games`, `test_ticks`, `forward_only` and `cpcv_group` beside the new ones.
3. Fold recomputability. Each fold archives its exact train and test game-id membership for both
   designs, plus the fitted isotonic thresholds and values (X, y) for the low and the high tail.
4. The RETAINED S272 tail ECE change is replayed from the S272 paired losses and published in
   both the summary JSON and the memo, with its sign convention stated.

Nothing here is a promotion, a feature flag, a registry write or a monetary quantity. The route
verifies this seal alongside the preregistration seal before it computes anything.

Seal SHA-256: b6d7bc237d9863838a852c82929fc107185d3263924bddb15070c2c8be19d6a7
