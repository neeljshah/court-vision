# S258 preregistration: incumbent conformal band v2

## Scope

This preregistration covers only the additive STATIC grouped conformal
calibration report for the S123 NBA incumbent series. It evaluates
`apply_incumbent` with the public labels `e4` and `ladder_base` on the full
S86 checkpoint source. The report will print held-out empirical grouped
coverage at nominal 0.90 and 0.80, plus mean interval half-width, for every
phase and overall cell.

## Binding source and before-condition

The source is `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2,829,826
bytes; Parquet tabular input, no pixel resolution). It is loaded only through
`scripts.platformkit.eval_gate.s86_nba_every_tick.load_ticks` with
`s86.CHECKPOINTS`; its `market_prob` field is mapped to `market`. The exact
binding before-condition measured 465249 ticks and 1593 games. The S101 SCREEN
archive remains limited to an unchanged STATIC market/model regression check.

## Fixed protocol

- Keep S101 values unchanged: `COVERAGE_MIN_GROUP=400`,
  `COVERAGE_MAX_GROUPS=50`, two minimum groups, and nominal levels 0.90 and
  0.80.
- Use the S86 five-fold game-first-date walk-forward design through the shared
  evaluator. Every fold asserts game purge and a symmetric nonzero one-day
  embargo before STATIC train-only calibration is applied to held-out ticks.
- A cell with fewer than 400 ticks is emitted with its count and
  `ABSENT_BECAUSE`; it is never dropped or replaced by a pooled result.
- Archive fold identifiers and per-group held-out frequencies, bounds,
  coverage flags, counts, game identifiers, and timestamps so coverage and
  widths can be recomputed from the artifact. The incumbent state is
  reconstructible from the named source and code identities.
- Re-run S101 unchanged and require every STATIC market/model grouped coverage
  value to match the committed S101 JSON to absolute tolerance 1e-9.

## Reporting

The JSON and memo will name every input path, byte size, and tabular resolution
status, the prerequisite seal path and hash, source denominator, code hashes,
all cells, worst-covered cells, and widest intervals. This is calibration
measurement only. No deployment, feature-flag change, register, or ledger
write is in scope.
SEAL_SHA256: 143bb939056ad70ead1fc5c83b0fbd6fd3b9cfd616a2f0b4536db24464172d7a
