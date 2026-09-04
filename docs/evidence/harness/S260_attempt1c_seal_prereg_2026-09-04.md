# S260 Attempt 1c Seal-Correction Preregistration

## Scope and premise

This preregistration governs the seal correction pass for the fixed naive MLB
calibration series previously archived by S244. The premise check is source
inspection only: the recovered
`scripts/platformkit/mlb_batter_pitcher_line_dist.py` constructs its own
date-cluster loop in `score_naive_clusters` and does not call
`walk_forward` or `cpcv_evaluate`.

The immutable, read-only corpus is
`data/frontend/prop_history_corpus_mlb.jsonl`. It is expected to contain
3,000 parseable settled rows in 777 date clusters. Every row remains in the
denominator. The 48 cold-start rows retain the named point-mass distribution
at 0.0. No market arm, candidate registration, or charged trial is involved,
so a registry ledger and launch K are not applicable.

## Frozen forecasting and loss protocol

The only arm is `naive_own_trailing_empirical`. For a scored row, its samples
are all prior observations for the same player with date strictly earlier than
`score_date - 3 calendar days`. Every score date is one chronological fold.
The fold must apply exact same-date purge and a nonzero symmetric three-day
calendar embargo: every retained training date has absolute calendar distance
greater than three days from the scored date. The evaluator route must be
`scripts/platformkit/eval_gate/walkforward.py:walk_forward` or
`scripts/platformkit/eval_gate/cpcv_engine.py:cpcv_evaluate`, not a new local
fold loop.

For samples x_1 through x_m and realized value y, CRPS is
`mean(abs(x_i-y)) - 0.5 * mean(abs(x_i-x_j))`. At q = 0.10, 0.50, and 0.90,
use the lower nearest-rank empirical quantile and ordinary pinball loss. Mean
each row loss within each date cluster, then take the unweighted mean across
all 777 clusters.

## Fixed comparison and acceptance

The archived custom-loop calibration values are CRPS
0.5098297809224259 and pinball q10/q50/q90
0.08655308369594088 / 0.37323931073931077 / 0.2013804110232682. A conformant
route must reproduce each value to maximum absolute difference 1e-9 across
all 777 clusters and 3,000 rows, with zero rows dropped.

Before measuring, inspect the shared evaluator interface. It must accept an
empirical sample distribution or an explicit scoring callback that can emit
CRPS and all three pinball quantities while preserving the evaluator's purge
and symmetric embargo. If it cannot, the only permitted verdict is CLOSED AT
LIMIT. The memo must name the exact interface incompatibility and the smallest
additive shared-evaluator capability that would permit the run. In that case,
do not claim a contract-route metric and do not regenerate replacement CSVs.

## Planned artifacts and checks

If the interface is compatible, write new S260-named row and cluster CSVs and
the S260 memo under `docs/evidence/harness/`; the source archive remains
unchanged. The row test will independently compare the four contract-route
macro losses to the archived custom-loop values at 1e-9. If the interface is
incompatible, the row test will instead reproduce the typed callback limitation
without accessing corpus data. In either case run only that test and
`tests/platformkit/test_loc_rail_scope.py`, one at a time.
Seal SHA-256: 1A340E5D209B3F5A4AADB237008D0B994CC71F6061821DDF5B144A8BCAED9B77
