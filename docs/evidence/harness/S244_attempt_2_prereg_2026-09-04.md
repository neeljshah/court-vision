# S244 Attempt 2 Preregistration

## Scope

This preregistration governs only the naive, non-market calibration evaluation
for `data/frontend/prop_history_corpus_mlb.jsonl`. The prior complete census
recorded 3,000 parseable settled rows, 0 non-null `market_prob` rows, and 777
date clusters. Therefore this attempt will not score or describe a market arm.
The fixed success condition is a naive-only table on all 777 date clusters.

## Fixed arm and source

The sole arm is `naive_own_trailing_empirical`. For every settled corpus row,
its forecast is the empirical distribution of that `prop_player`'s prior
`realized_stat` observations in the same immutable corpus. The scorer orders
records by `ts` date and uses only observations at least four calendar days
before the scored date. This is an as-of, own-history distribution for the
selected `strikeouts` stat family. If a player has no eligible own history, the
fixed cold-start empirical distribution is the one-point value `0.0`; that
fallback is recorded per row and counted in the evidence.

## Fixed losses and denominator

For each row with empirical samples `x_1..x_m` and observed value `y`, CRPS is
`mean(abs(x_i-y)) - 0.5*mean(abs(x_i-x_j))`. For q in 0.10, 0.50, and 0.90,
the forecast quantile is the lower nearest-rank empirical quantile and pinball
loss is `max(q*(y-yhat), (q-1)*(y-yhat))`.

The unit reported in the loss table is a date cluster: first take the mean of
each row loss within that date, then take the unweighted mean of the 777 date
cluster losses. The named row denominator is all 3,000 parsed settled corpus
rows; no price-null, duplicate, or cold-start row is excluded.

## Fold, purge, and embargo scheme

Each distinct score date is one chronological walk-forward fold. Its train
series is every earlier same-player row outside the symmetric three-calendar-day
window centered on that score date. The past-only rule means the accepted train
dates are strictly before `score_date - 3 days`; the symmetric assertion also
checks every retained train date has absolute date distance greater than three
days from every row scored in the fold. Thus purge is exact same-date removal
and embargo is nonzero three days on both sides of each scored fold.

`scripts/platformkit/eval_gate/walkforward_embargo_prereg.py` is absent, and
the available `cpcv_evaluate` accepts only binary walk-forward-shaped states.
The additive S244 helper will therefore implement this fixed distribution
callback and assertion without changing any shared evaluator module.

## Outputs and verification

The scorer will write an additive per-cluster CSV under `docs/evidence/harness/`
with cluster date, row denominator, cold-start count, and all four naive losses.
The S244 memo will receive an ATTEMPT 2 section with the before/after table,
the full loss table, and an explicit NOT VERIFIED list. One per-file test will
recompute one archived cluster CRPS and one archived q10 pinball value. No
ledger is charged because this is a naive-only, non-market baseline with no
candidate registry arm.

Seal SHA-256: 76F24D16D406B5D44DDA14D533C441A2D07DFA1B11C873F9C0B3C07C6F79315B
