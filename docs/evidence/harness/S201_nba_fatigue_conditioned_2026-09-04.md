# S201 - NBA fatigue conditioned forms: CLOSED AT LIMIT

Row: `docs/evidence/tracking/specs/S201_spec.md` (S201).

Verdict: **CLOSED AT LIMIT.**

## Limit check

Before fitting any conditioned form, S201 requires reproduction of the three
S92 improvements from these archive files:

* `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv`
* `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_rated.csv`

Neither file exists in this worktree. A bounded filename check of the one
allowed store, `data/cache/eval_gate`, found no S92 or `lineup_dynamic`
archive file. Therefore the fixed 79,554-tick / 661-cluster ALL denominator
and the S92 losses cannot be re-measured. No archive rows were read.

The unavailable columns required for the limit reproduction are
`loss_incumbent`, `loss_fatigue_min`, `loss_fatigue_share`,
`loss_unit_onoff`, `cluster_id`, and the row/date fields required to establish
the fixed denominator and folds. Because the files are absent, no individual
column can be identified as the failing column; the entire required archive is
unavailable.

## Consequence

S201 step 1 requires the archive to reproduce to maximum absolute difference
at most `1e-9` before any new form is fit. That check cannot run, so the
conditioned `fatigue_min` by period, remaining time, and absolute margin forms
were not fit. No new module, test, CSV, JSON, or paired-loss differential
series was created. The S92 archive was not changed.

No metric, confidence interval, effective sample size, or candidate verdict is
reported. `data/cache/eval_gate/backtest_fwer.jsonl` was not opened, no ledger
was read or written, no register was changed, and no feature flag was changed.
The specified S201 per-file test was not created or run because the archive
limit stopped the work before S201 step 2.

## Verifier-contract self-check

This is an unscored limit closure. It does not assert a result without a
reconstructible paired-loss archive (Q9), does not move the `+0.004` bar
(B10/Q3), and makes no calibration performance claim (Q6). The excluded
dead-clock population remains unmeasured; no rows were selectively removed
(B1). No deployment or external action occurred (B5).

## NOT VERIFIED

* The S92 ALL and RATED archive contents, including the three reported S92
  improvements, are not verified in this worktree.
* The three fixed S201 conditioned forms are not screened.
* The S201 per-tick differential archive cannot be produced without the S92
  source archive.
