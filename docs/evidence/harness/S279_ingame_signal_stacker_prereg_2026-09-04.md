# S279 preregistration: NBA in-game AS-OF-safe signal stacker

## Scope frozen before scoring

This run uses `data/cache/inplay_odds/nba_checkpoints_full.parquet` as the
complete 465,249-tick NBA in-game corpus. Its incumbent is an out-of-fold
global logistic recalibration of `market_prob`; the candidate starts at that
incumbent and may add only columns obtained from the 49 rows whose
`label == "AS-OF SAFE"` in
`docs/evidence/harness/S223_intel_pool_asof_census_2026-09-04.json`.

The source enumeration is exhaustive by construction: all four rows whose
S223 `category` is `atlas` and all 45 whose category is `intelligence` are
attempted. A store is eligible only if its declared player/team grain can be
matched to an identity present in a tick and its declared temporal column is
strictly before that tick's `game_date`. No row is removed when an attempt
cannot produce a feature: its prediction is the incumbent prediction and the
store and tick counts are retained in the join manifest.

## Fixed evaluation

Each tick is one evaluator state, identified by the stable key
`game_id|ts|source_row`. The shared
`scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` route uses two
chronological groups, one test group, its symmetric one-day embargo and its
existing purge. Fits are cached only by the complete ordered train-state key.
The candidate fit is logistic on the incumbent logit plus every eligible
joined column, with an L2 penalty toward the recalibrated-null coefficient.
The finite penalty path is `[0.01, 0.1, 1.0, 10.0, 100.0]`; the final
maximum-shrinkage point is the recalibrated-null prediction exactly. A penalty
is selected only from training states; no test outcome, test feature fitting,
or later game enters its selection.

The metric is `Brier(recal_null) - Brier(stacker)`, so positive values favor
the stacker. The frozen bar is `+0.004`; the full game-clustered paired-loss
95 percent interval is reported. The all-tick denominator is fixed at every
input tick, including fallback ticks. The run is calibration measurement only.

## Fixed outputs

The run writes the dated summary JSON, per-signal weights CSV, and all-tick
paired-loss CSV named by S279. The summary records source byte sizes, code
hash, selected path, joined and fallback counts, and every source's join
status. The focused fixture test asserts that maximum shrinkage exactly
reproduces the recalibrated-null prediction.

Seal SHA-256: be8beb5ba9f50ebab84d967a6db625467962186f9651df30bf727fc0b8309961
