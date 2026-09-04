# S263 Preregistration: S88 Preburn Companion

## Scope

This preregistration precedes every S263 scored comparison. The sole source generation binding is `python -m scripts.platformkit.ingame.s88_phase_recal`, run locally in `C:/Users/neelj/nba-track-a15` because the S88 memo's quoted worktree prefix resolves to this worktree. The original memo path is `docs/evidence/harness/S88_phase_recal_2026-09-04.md`; the published paired-loss path is `docs/evidence/harness/s88_phase_recal_2026-09-04.csv`.

## Fixed checks and bars

- Confirm the S88 binding produces 47,104 total ticks across 158 games, `n_burn_in_dates=3`, and 33,920 published post-burn rows; the implied pre-burn count is 13,184.
- Produce only an additive companion CSV, preserving the published CSV byte-for-byte. The union must contain exactly 47,104 rows with zero overlap and zero gap.
- Recompute the post-burn Brier table from the published rows. Required fixed pooled values are incumbent `0.174603`, recal `0.176080`, and market `0.170853`; required fixed per-phase values are `late|leading_big` `+0.031643` and `mid|trailing` `-0.011964`. The maximum absolute reproduction difference is at most `1e-9` against unrounded calculations represented by the source artifact or rerun output.
- Report the corresponding all-row, including-burn-in sensitivity table beside the excluded-burn table. It is descriptive and cannot replace the fixed post-burn table.
- Every probability used for any reconstructed row is produced by the shared evaluator route with purge plus symmetric nonzero embargo. Its callback is the sole producer of scored probabilities. No parameter, threshold, corpus, or bar may be changed after this seal.

## Trial status

This is an uncharged archival-completeness and calibration-reproduction check. No register or ledger is written. The verdict vocabulary is limited to calibration evidence.

Seal SHA-256: 6f8bab53640391f6de1ae2b2b0c3d7946510fc919540733a71bbd59d9bfb3321
