# S271 attempt 2 preregistration: box-score quantile producer

## Scope

This preregistration binds the local, additive S271 attempt-2 calibration
measurement under `docs/evidence/tracking/specs/S271_spec.md` and
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q. It corrects
the game-cluster and evaluator-fit deficiencies recorded in
`docs/evidence/harness/S271_VERIFY_2026-09-04.md`. The run is local to the
`track-a18` worktree. It does not write under `data/`, touch a register or
ledger, deploy, or modify an existing model artifact.

## Inputs and game identity

The three label inputs are opened separately:

- `data/cache/pts_q50_oof_int95.parquet`, target `target_pts`.
- `data/cache/reb_q50_oof_int95.parquet`, target `target_reb`.
- `data/cache/ast_q50_oof_int95.parquet`, target `target_ast`.

For each held-out row, an exact as-of-safe NBA `GAME_ID` is joined from the
locally available realized box-score logs
`data/cache/cv_fix/leaguegamelog_regular_season.parquet` and
`data/cache/cv_fix/leaguegamelog_playoffs.parquet` on player id, game date,
and the corresponding realized target. The joined `GAME_ID` and its first
date are archived with every scored row. The run fails if any held-out source
row lacks exactly one matching real game id.

## Fixed protocol

The score period is `2025-10-01 <= date < 2026-06-01`. Features use only a
player's strictly earlier target dates. The evaluator receives every source
state, splits it with `cpcv_distribution` using `n_groups=2`,
`n_test_groups=1`, and `embargo_days=1`, and applies a symmetric nonzero
purge and embargo by game first date. Its callback receives the evaluator's
train states, fits only on those states, and predicts its redacted test state.
For the held-out test block, the callback asserts every model-fit state has a
game-first-date before the test state. No precomputed prediction frame may
score a metric.

For each stat, the callback fits per-player gradient-boosted quantile models
at 0.10, 0.50, and 0.90 with random state 271, 80 estimators, learning rate
0.05, max depth 2, minimum leaf 20, and minimum split 40. When a player has
fewer than 40 evaluator train states, its callback uses that player's
train-state empirical quantiles; no test target enters either path. The three
outputs are sorted per test row before evaluator-owned loss calculation.

## Fixed metrics and denominator

Every held-out evaluator record contributes to empirical q10/q90 coverage
against the nominal 0.80 interval and q50 pinball loss. No record is filtered
by interval result or q50 error. The denominator is every held-out scored
source row. The 95 percent percentile bootstrap uses exact `GAME_ID` clusters
(seed 271, 2,000 replicates); at least 30 unique game clusters are required.
The scored archive contains each record's game id, game first date, target,
quantiles, coverage indicator, and q50 loss, so all metrics and intervals can
be recomputed from the artifacts.

## Output and checks

The fresh process writes new 2026-09-04 filenames with `_attempt2` suffix for
the memo, summary, and sample parquet under `docs/evidence/harness/`. It
prints RSS before and after and aborts above 600 MB. The focused test builds a
fixture with a planted future row, proves it cannot enter a prior feature, and
proves the evaluator callback is the sole scorer. The seal test reads this
file, normalizes CRLF to LF, and hashes bytes above this line; it never reads
from Git.

SEAL_SHA256: 2ab90c068ba2c62fe8ace19cc2044bef08baa8322f1a4597456f42d3b5493b07
