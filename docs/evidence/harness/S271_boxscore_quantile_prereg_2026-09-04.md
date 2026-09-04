# S271 preregistration: box-score quantile producer

## Scope

This preregistration binds the local, additive S271 quantile calibration
measurement specified in `docs/evidence/tracking/specs/S271_spec.md` and
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q. The run uses
the local `track-a18` worktree only. It does not write under `data/`, touch a
register or ledger, deploy, or modify existing model artifacts.

## Inputs and held-out period

The only target-label inputs are opened separately:

- `data/cache/pts_q50_oof_int95.parquet`, target `target_pts`.
- `data/cache/reb_q50_oof_int95.parquet`, target `target_reb`.
- `data/cache/ast_q50_oof_int95.parquet`, target `target_ast`.

The held-out 2025-26 period is `2025-10-01 <= date < 2026-06-01`. Rows before
that period train each stat/quantile model; held-out rows are never used to
fit it. A row's features are prior count, prior mean, prior standard deviation,
prior last value, and days since prior game, each built from only that player's
strictly earlier target dates. Duplicate player/date input rows fail closed.

## Fixed model and shared evaluation protocol

For each of PTS, REB, and AST, fit `GradientBoostingRegressor` quantile-loss
models at alpha 0.10, 0.50, and 0.90 with random_state 271, n_estimators 80,
learning_rate 0.05, max_depth 2, min_samples_leaf 20, and min_samples_split
40. Quantiles are monotonized by sorting the three predictions per row.

The held-out predictions are passed through
`scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` with n_groups=2,
n_test_groups=1, and embargo_days=1. This is the shared evaluator's symmetric,
nonzero calendar-day embargo; its imported vintage assertion requires every
feature availability timestamp to precede its score timestamp. Models are
fitted only from the pre-held-out period, before every held-out score.

## Fixed metrics and denominator

For every held-out scored row, report empirical interval coverage
`mean(q10 <= target <= q90)` against nominal 0.80 and q50 pinball loss
`mean(max(0.5*(target-q50), -0.5*(target-q50)))`, separately for PTS, REB,
and AST. No row is filtered on q50 error or interval outcome. The denominator
is every held-out source row for the stat. The source lacks game_id, so a
calendar-date cluster contains every held-out player-game row on that date;
the game-date clustered 95 percent interval is the percentile bootstrap over
these clusters (seed 271, 2000 replicates). At least 30 date clusters are
required.

## Required artifacts and checks

The run writes the dated S271 memo, summary JSON, held-out sample parquet, and
per-game-date scored-record archive under `docs/evidence/harness/`. The sample
includes target, three quantiles, the strict feature-source date, and every
feature for independent coverage, pinball, and purge reproduction. The focused
test uses a small fixture to assert zero non-strict feature source dates and a
known three-row coverage calculation; it also normalizes CRLF to LF while
checking this file's seal.

SEAL_SHA256: 49058380e65a769345a4a93310170d1abedd10350132de489706b7edb5d809d9
