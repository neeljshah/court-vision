# S285 preregistration v2: event-proximity audit of the S265 static band

## Scope

This preregistration covers one additive, sample-scale calibration audit of the
unchanged S265 S123 `ladder_base` STATIC conformal band. It does not build or
fit a covariate-conditioned band. It reports empirical grouped coverage and
mean half-width for near-event, settled, and pooled bins, plus game-clustered
95 pct confidence intervals and the fixed signed interactions.

This v2 preregistration supersedes the unscored earlier S285 preregistration:
its event-row convention is stated unambiguously below. No S285 bin was scored
before this v2 seal.

## Binding source, sample, and premise

The only raw input is
`C:/Users/neelj/nba-track-a14/data/cache/inplay_odds/nba_checkpoints_full.parquet`,
2,829,826 bytes, Parquet tabular data; pixel resolution is not applicable.
Reload S265's sealed complete-game sample through
`scripts/platformkit/eval_gate/s265_incumbent_conformal_band_sample.py` using
its fixed seed 258104 and limit 80000. The binding sample contains 79,919
ticks from 269 games.

Within each game, order ticks by `(ts, stable source row)`. At a tick, derive
`ticks_since_last_score_change` from its score and prior ticks only: compare
its `(score_home, score_away)` with the immediately prior tick, record zero
when it changes, otherwise record the number of ticks since the last such
change; the first tick of every game is zero. The implementation must prove
that planting a score change only in a future tick leaves every prior derived
value unchanged. No later tick may backfill an earlier value.

Before any bin is scored, compute the distribution over the whole sealed
sample and fix the boundaries at its p50 and p90. The binding measurement is
p50=13 and p90=136: near-event is `<= 13`, settled is `> 136`, and the named
middle exclusion is `14..136`. Every held-out scored tick receives exactly one
of these labels. The boundaries are never re-fit after a metric is seen.

## Fixed scoring protocol

- Produce the unchanged static bands with S265's shared S101 walk-forward
  route: five expanding game-first-date folds, game-disjoint purge, and the
  symmetric nonzero one-day embargo asserted for every fold. S101 calibrates
  only TRAIN fold data and applies the STATIC band only to its held-out ticks.
- Use S101 `grouped_coverage` unchanged for each bin and pooled set at nominal
  0.90 and 0.80. Its fixed `COVERAGE_MIN_GROUP=400`,
  `COVERAGE_MAX_GROUPS=50`, and two-group minimum are retained exactly.
- Every evaluator state is one held-out tick with stable key
  `game:source_row`; no game-level state stands in for its ticks. The archived
  differential contains only evaluator records, including game, state key,
  timestamp, fold, nominal, bin, probability, label, and static interval.
- Estimate each 95 pct confidence interval by 2,000 deterministic game
  cluster bootstrap resamples (seed 2850904), resampling complete games with
  replacement inside each reported bin. Recompute S101 grouped coverage and
  mean half-width for every resample. The coverage interaction is settled
  minus near-event; the descriptive half-width interaction is near-event
  minus settled. Take the 2.5th and 97.5th bootstrap percentiles.
- Print separate game-cluster counts for near-event and settled. A scored bin
  with fewer than 30 game clusters is reported `ABSENT_BECAUSE` and cannot
  satisfy the signal condition.

## Fixed decision rule and execution boundary

The metric is S265's static-band empirical coverage and half-width in the
near-event, settled, and pooled bins, each with a game-clustered 95 pct CI,
plus the two signed interactions with their own CIs. The coverage gap is
settled coverage minus near-event coverage; positive means near-event
undercoverage. Report `SIGNAL` only when that gap is greater than 0.05 and its
CI lower bound is above zero; otherwise report `NULL`. The half-width
interaction is descriptive.

This is an uncharged calibration measurement: it reads no ledger or register,
has no K field, and performs no ledger write. The source is opened one store
at a time. S265 measured 449,515,520 bytes peak RSS, below the 500 MB pod
threshold, so this sample-scale run is expected locally; it prints RSS and
aborts at the unchanged 600 MB limit. No data write, pod transfer, deployment,
feature-flag action, S123 change, S265/S276 artifact rewrite, or other corpus
is in scope.

SEAL_SHA256: b5accd1d3e1f80877e1d44a699838501363726958d6a68cb090d89f14d5a76c7
