# S258 attempt 1d preregistration: incumbent conformal band sample

## Scope

This preregistration covers one local, additive SAMPLE-SCALE STATIC conformal
calibration measurement for the S123 NBA incumbent series. It evaluates
`apply_incumbent` with public labels `e4` and `ladder_base`, using a
deterministic whole-game subsample from the full S86 checkpoint source. The
result will report held-out empirical grouped coverage at nominal 0.90 and
0.80, plus mean interval half-width, for every phase and overall cell.

## Binding source and deterministic sample

The source is `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2,829,826
bytes; Parquet tabular input, no pixel resolution). It is opened only through
`scripts.platformkit.eval_gate.s86_nba_every_tick.load_ticks` with
`s86.CHECKPOINTS`; `market_prob` maps to `market`. The premise measurement is
465249 ticks / 1593 games.

The sample seed is `258104`. Sort source game identifiers, draw their order
with `numpy.random.default_rng(258104).permutation`, and retain each complete
game in that order when adding all of its ticks keeps the total at most 80000.
No game is partially retained. This deterministic rule yields 269 complete
games / 79919 ticks. This scale is chosen for a local scorer memory ceiling of
600 MB; the evaluator records its measured peak RSS. It is a sample-scale
measurement, not a full-source result.

## Fixed protocol

- Keep S101 values unchanged: `COVERAGE_MIN_GROUP=400`,
  `COVERAGE_MAX_GROUPS=50`, two minimum groups, and nominal levels 0.90 and
  0.80.
- Use the S86 five-fold game-first-date walk-forward design through the shared
  evaluator. Every fold asserts game purge and a symmetric nonzero one-day
  embargo before STATIC train-only calibration is applied to held-out ticks.
- A cell with fewer than 400 ticks is emitted with its count and
  `ABSENT_BECAUSE`; it is never dropped or replaced by a pooled result.
- Archive the sample membership, fold identifiers, grouped held-out
  frequencies, bounds, coverage flags, counts, game identifiers, and
  timestamps so the coverage and widths can be recomputed from the artifact.
- Re-run S101 unchanged, using its SCREEN archive only for this regression,
  and require every STATIC market/model grouped coverage value to match the
  committed S101 JSON to absolute tolerance `1e-9`.

## Execution boundary and reporting

This trial runs locally only. No module, preregistration, sample, or artifact
will be copied to a pod before ACCEPT. Existing pod-derived S258 files are
superseded and excluded from evidence for this row. The JSON and memo will
use new `_sample` filenames and name inputs, code identities, denominators,
cells, absent cells, worst coverage, widest intervals, and explicit items not
verified. This is a descriptive calibration SCREEN: no deployment, feature
flag, register, or ledger write is in scope.
SEAL_SHA256: 3c36c78bc78e5e372c87170831d388af87bd2eb1fad734ddf7ca69868c89f87a
