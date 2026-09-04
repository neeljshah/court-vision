# S271 attempt 2b preregistration: box-score quantile producer

## Scope and machine

This preregistration binds the additive S271 calibration measurement specified
in `docs/evidence/tracking/specs/S271_spec.md` and
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q. The full fit
runs only in the `a18` pod scratch worktree via `C:/Users/neelj/bin/pod_run`,
because the evaluator fit exceeded local CPU time. The pod scratch run does not
deploy to the production tree. No path under `data/`, a register, or a ledger
is written.

## Inputs, game ids, and held-out block

The target-label inputs are:

- `data/cache/pts_q50_oof_int95.parquet`, target `target_pts`.
- `data/cache/reb_q50_oof_int95.parquet`, target `target_reb`.
- `data/cache/ast_q50_oof_int95.parquet`, target `target_ast`.

The as-of-safe game-id join uses only `PLAYER_ID` plus `GAME_DATE` from
`data/cache/cv_fix/leaguegamelog_regular_season.parquet` and
`data/cache/cv_fix/leaguegamelog_playoffs.parquet`; it does not use the scored
target. Duplicate player/date game-log keys fail closed. The held-out period is
`2025-10-01 <= date < 2026-06-01`; all evaluator train states precede its first
scored game. Features are prior count, mean, standard deviation, last value,
and days since prior game, each from only the player's strictly earlier target
dates. Duplicate player/date source rows fail closed.

## Fixed evaluator and model

`scripts/platformkit/eval_gate/cpcv_engine.py` is imported unchanged and its
restored HEAD SHA-256 is recorded by the run. The additive
`scripts/platformkit/eval_gate/quantile_walkforward.py` imports the unchanged
`walkforward.py` timestamp ordering, vintage assertion, redaction, matchup
embargo, and team purge. It receives all states, retains only pre-held-out
purged train states, supplies outcome-redacted held-out views to its callback,
then returns the only records that may be scored.

For each PTS, REB, and AST, the callback fits three per-stat
`GradientBoostingRegressor` quantile-loss models with alpha 0.10, 0.50, and
0.90; random_state 271; n_estimators 80; learning_rate 0.05; max_depth 2;
min_samples_leaf 20; and min_samples_split 40. Predictions are monotonized by
sorting each row's three quantiles. The evaluator applies a symmetric nonzero
one-day embargo before the callback consumes train states.

## Fixed metric, denominator, and artifacts

The metric on every evaluator-output held-out row is interval coverage
`mean(q10 <= target <= q90)` against nominal 0.80 and q50 pinball
`mean(max(0.5*(target-q50), -0.5*(target-q50)))`, per stat. No row is filtered
on q50 error or interval outcome. The denominator is every held-out source row
for that stat. The percentile bootstrap uses exact NBA game_id clusters, seed
271, and 2,000 replicates.

The acceptance bar is byte-for-byte: coverage and pinball reported per stat
with a game-clustered 95 pct CI, n >= 30 game clusters; a test asserts 0 rows
where any feature's source date is at or after the scored row's date.

The pod run writes only new `_attempt2b` memo, JSON summary, and scored sample
parquet under `docs/evidence/harness/`. The sample archives game_id, timestamp,
target, q10/q50/q90, coverage indicator, pinball loss, feature-source date,
and features so all reported game-clustered metrics are reproducible.

## Checks before full fit

Before full pod scoring, a local 200-player route run prints its non-claim
counts and calibration values. The focused test checks the LF-normalized file
seal, strict feature purge, synthetic three-row coverage arithmetic, and that
the scorer consumes evaluator output. The full run prints input censuses,
progress each 500 held-out players, RSS before/after, and wall time.

SEAL_SHA256: a613951b134a47a6c6e1bf7d3c17331e3e2b1c09eab584a75c415a185cfd71e9
