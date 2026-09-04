# S265 attempt 1b preregistration: incumbent conformal band sample

## Scope

This preregistration covers one local, additive SAMPLE-SCALE STATIC conformal
calibration measurement for the S123 NBA `ladder_base` incumbent. It reports
held-out empirical grouped coverage at nominal 0.90 and 0.80 and mean interval
half-width, using a deterministic whole-game subsample of the S86 checkpoint
source. This is a sample measurement, not a full-source measurement.

## Binding source and fixed sample

The source is `data/cache/inplay_odds/nba_checkpoints_full.parquet`. Before
scoring, a streaming `game_id`-only scan of `s86.CHECKPOINTS` measured 465249
ticks / 1593 games. Sort game identifiers, draw their order with
`numpy.random.default_rng(258104).permutation`, and retain each complete game
when adding all of its ticks keeps the total at most 80000. No game is partly
retained. This binding selection is 79919 ticks / 269 games, with seed 258104.

## Fixed protocol

- Grouped cells are `P1`, `P2`, `P3`, `P4`, `OT`, and `ALL`.
- `COVERAGE_MIN_GROUP=400`, `COVERAGE_MAX_GROUPS=50`, and the two-group
  minimum are unchanged.
- Nominal coverage levels are 0.90 and 0.80.
- The S86/S101 design is five expanding game-first-date folds, game-disjoint
  purge, and a symmetric nonzero one-day embargo. Calibration is fit only on
  each TRAIN fold and applied only to its held-out fold.
- Every cell with fewer than 400 sample ticks is reported as `ABSENT_BECAUSE`;
  no such cell is dropped or pooled as a substitute.
- The S101 regression replays the retained
  `data/cache/eval_gate/s101_aci_coverage_2026-09-03_ticks.csv.gz` STATIC
  screen through the shared evaluator and compares all 24 market/model,
  nominal, and grouped-cell coverages against
  `data/cache/eval_gate/s101_aci_coverage_2026-09-03.json` at absolute
  tolerance 1e-9. It never uses its own output as that reference.

## Execution boundary

The scorer reads one store at a time, makes no full-source `load_ticks` call,
and runs locally only. RSS is printed before and after scoring; execution
aborts if peak RSS is at or above 600 MB. The paired-loss archive records
sample membership plus per-game losses and grouped coverage units so the
reported cells are reproducible. No pod transfer, deployment, feature-flag,
register, or ledger action is in scope.

SEAL_SHA256: 17aa1f6cdee9207aa83fd8addcefb58931ade103fb464b72d5068a6a74f451f8
