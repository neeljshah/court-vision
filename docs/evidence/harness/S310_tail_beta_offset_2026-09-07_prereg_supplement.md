# S310 preregistration supplement: feasible evaluator grain

Amends `docs/evidence/harness/S310_tail_beta_offset_2026-09-07_prereg.md`
(seal `0b7ed9caa1bdb0e08b34fbf81fd19a7266cd00c2f6f86f1cdca4b5ba8cefafbd`) in exactly the
three ways listed below. Every other clause of that preregistration stands unchanged.
Sealed before the amended harness was run and before any amended result was produced.

## Why the original grain is not runnable

Measured on the pod job and reproduced locally; full numbers in
`docs/evidence/harness/S310_pod_job_triage_2026-09-07.md`.

The mandated shared route `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` calls
`_blocked_indices` once per split, and that function costs O(test_rows x ticks_per_date):
for each test row it inserts the index list of three calendar dates into the blocked set.
This corpus has 465249 ticks over only 302 distinct game dates, a median 1405 ticks per
date, so the term is quadratic in corpus size. Phase-instrumented local runs on game
subsamples give 27.63 s of `_blocked_indices` at 46523 rows and 102.87 s at 94240 rows,
an exponent of 1.86, and a remainder exponent of 1.25. Extrapolated to the full 465249
rows: about 3981 s of single-core CPU, of which about 2006 s is the purge.

The pod container has a `cpu.max` quota of 27.2 cores and is saturated by the tracking
fleet (load average 40 to 70; one simulator at 11.6 cores and ten tracking jobs at about
13 cores combined). A single-threaded harness measurably receives 0.125 of one core. The
original job ran 4 h 46 m, consumed 38 m of CPU, wrote no artifact, and projected a
further 3.8 h. The budget is 3 h.

The purge lives in the shared evaluator, which is frozen and shared across rows, so it is
not the thing to change. The only admissible lever is the number of states presented to it.

## Amendment 1: evaluator grain

The preregistration says "exactly one evaluator state per input tick". It is replaced by:

Exactly one evaluator state per `(game_id, period, floor(game_clock_s / 30))` cell, taking
the earliest source row in that cell by original parquet row index. The rule is
deterministic, is computed before any model is fit, and reads no outcome, no probability
and no terminal-status field. The stable state key remains `game_id:ts:row_index` and
still points at a real source row. The game id remains the cluster id.

Effect: 465249 source rows become 117964 evaluator states. All 1593 game clusters are
retained.

Composition of what is dropped, stated plainly because the original preregistration
promised that no row would be excluded on terminal status:

- The 271154 zero-clock rows fall to 1381 kept states. They are repeated polls of an
  already settled market at an identical `(period, clock)` coordinate: they occupy 5874
  `(game_id, period)` cells, 2346 of which carry a single distinct `market_prob`. Most are
  dropped not by a terminal-status test but because they share a 30 s bucket with an
  in-play row that has a lower row index.
- In-play rows fall from 194095 to 116583 states, at a mean 1.66 source rows per cell and
  a mean within-cell `market_prob` standard deviation of 0.00455.

The global Brier guard is therefore computed over a population that is no longer 58 percent
settled terminal snapshots. This is a change of denominator and is reported as such; no
claim is made here about which direction it moves the guard.

## Amendment 2: single evaluator pass

Baseline and candidate probabilities are produced by one `cpcv_evaluate` pass instead of
two. The two passes differ only in the final `_apply_candidate` step and their baseline
arms recompute byte-identical values from identical splits, purges and train sets. The
baseline probability is now captured inside the predictor callback and the candidate is
derived from it in the same call. Splits, purge, embargo, train-set construction, fitted
baselines, fitted residuals and every archived quantity are unchanged.

## Amendment 3: progress instrumentation

The harness prints a scored-state counter and elapsed seconds to stderr. This is
observability only and touches no computed value.

## Remeasured binding premise on the amended grain

- Raw `market_prob` band 0.01 to 0.05: 4420 states, 570 game clusters, 26 positive-outcome
  clusters. Original tick grain: 9226, 649, 29.
- Raw `market_prob` band 0.95 to 0.99: 6515 states, 742 game clusters.
- Both exceed the 30-cluster floor. The bootstrap resamples game clusters, so interval
  width is set by cluster count, which is retained at 570 and 742.

## Projected against budget

| design | single-core CPU | wall at the measured 0.125-core pod share |
|---|---:|---:|
| original: full tick grain, two passes | about 3981 s | about 8.8 h |
| full tick grain, single pass | about 1991 s | about 4.4 h |
| amended: 30 s grain, single pass | about 257 s | about 34 m |

Budget 3 h. Only the amended design fits, and it fits with margin.

## Unchanged by this supplement

Estimand, primary and guard metrics, epsilon 1e-15, the frozen tail bins, the ridge, the
nested inner OOF construction, the acceptance bar, the seed 905, the 10000 bootstraps, the
sign convention, the shared route, the shared purge, the symmetric one-day embargo, the
Holm rule, the frozen 0.004 global bar, the S272 references, and the ban on deploy, flag,
registry, ledger and source-store writes.

Seal-SHA256-LF: 4f9898cf09f46f91253286ba2ccd8047813b46fbd920bf6ad81b4740dc10a904
