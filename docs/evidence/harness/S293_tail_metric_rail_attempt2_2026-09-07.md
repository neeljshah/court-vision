# S293 tail metric rail -- attempt 2

## Verdict

NOT VALIDATED. This row implements and reproduces calibration metrics; it fits no
candidate and accepts none. Attempt 1 (`df0f033f67fdd4a9ac6e5b615adf2be6995c89bc`)
was REJECTED by `docs/evidence/harness/S293_VERIFY_2026-09-07.md`; this attempt
applies that memo's four CORRECTIONS and rescores.

Preregistration: `docs/evidence/harness/S293_tail_metric_rail_prereg_attempt2_2026-09-07.md`
LF-normalized seal: `d8dcfa628f3d0abbaeb2f6486c3b9a08392678a7a226c5313baa873230665e9d`

Commit order, Q1: the preregistration was committed ALONE at `8ee332ec0`
("S293 attempt 2: preregistration sealed (Q1)"), its committed bytes were
re-hashed from `git show HEAD:<path>` and matched the embedded seal, and only
then were the code and test committed at `3b69f6c46`. Both commits precede the
pod job. The attempt-1 preregistration is left untouched.

## Corrections applied

| Verifier finding | Fix |
|---|---|
| Trailing-team reliability computed in the leading-team frame | `cpcv_tail_metrics.py:105-112` now returns the home team's own `p`/`y` when the home margin is negative and `1-p` / `1-y` otherwise |
| Comeback reliability cells scored at n = 19, 20, 6, 25/27 | `cpcv_tail_metrics.py:69-92` SUPPRESSES any cell with `0 < n < 30`: the declared bin still publishes its exact count and is flagged `suppressed_below_min_n`, with null scored fields |
| Relative `--output-dir` crashed at `relative_to(ROOT)` | `s293_tail_metric_replay.py:107` resolves the directory and `:39-45` falls back to the absolute posix path when it lies outside the repo |
| Replay rewrote the 2026-09-04 memo | `_memo()` is deleted; the replay emits only the two new dated artifacts and writes no memo. This memo is authored by hand |
| Stale engine hashes / unreproduced comeback count | Attempt-2 preregistration freezes the CURRENT hashes and the reproduced count, with the delta explained below |

SUPPRESS, not merge, was chosen because the specification requires every declared
bin to be published and merging would silently change the frozen 10-bin grid.

## Premise correction to the specification's comeback count

The specification's VERSION 2026-09-07 clause quotes 133,319 ticks / 1,113 games
(`outcome_home_win` split 77,516 / 55,803) for a mask it defines with
`period <= 4`. The mask AS WRITTEN measures 133,184 ticks / 1,111 games, split
77,381 / 55,803. The difference is not a corpus difference: dropping only the
period cap admits overtime periods 5-6, for which
`(4 - period) * 720 + game_clock_s` is always at or below 720, and reproduces the
quoted figures exactly.

```text
133,184 + 135 = 133,319 ticks
  1,111 +   2 =   1,113 games
 77,381 + 135 =  77,516 outcome_home_win = 1
 55,803 +   0 =  55,803 outcome_home_win = 0
```

The 135 excluded overtime ticks (2 games, all ending in a home win) are published
in the summary as `ot_ticks_excluded_by_period_cap`,
`ot_games_excluded_by_period_cap` and `ot_excluded_outcome_home_win_ticks`. The
mask, the frozen `+0.004` comparison bar and the `-0.0005` tolerance are all
unchanged; only the specification's quoted count is corrected.

## Reproduction: replay against S272

The unchanged S272 route regenerated every tick through its CPCV prediction path
with a symmetric one-day embargo and shared team/matchup purge. Per-tick losses
are REGENERATED, never replayed off the mixed-grain archive: the 310,349-row
archive (1,593 `all_game` + 308,756 `tail_tick`) is opened, asserted, and refused
as mixed grain by the sibling helper.

Corpus scored: 465,249 ticks, all of them unique `game_id`/`ts` keys, across
1,593 games and two nonconstant split groups. Folds: 2024-25 with 198,344 ticks /
656 games (market fallback, zero prior-season training games) and 2025-26 with
266,905 ticks / 937 games (656 training games). Tail: 308,756 ticks / 1,590
games.

| replayed quantity | S293 attempt 2 | S272 summary | abs delta |
|---|---:|---:|---:|
| all-tick candidate Brier | 0.073353613894633171 | 0.073353613894633171 | 0.000e+00 |
| all-tick recal_null Brier | 0.073316945556600524 | 0.073316945556600524 | 0.000e+00 |
| tail candidate Brier | 0.006840435259547864 | 0.006840435259547861 | 2.602e-18 |
| tail recal_null Brier | 0.006785181571841887 | 0.006785181571841887 | 0.000e+00 |
| tail candidate ECE | 0.001244584782360570 | 0.001244584782360570 | 0.000e+00 |
| tail recal_null ECE | 0.001493409874920180 | 0.001493409874920181 | 1.084e-18 |

Maximum replay delta 2.602085e-18, against the preregistered 1e-12 requirement.
The module asserts this internally and would have raised otherwise.

## Metrics

Sign convention: improvement = baseline (recal_null) loss minus candidate loss;
positive means the candidate carries the lower loss. The frozen Brier comparison
bar is `+0.004` and is neither charged nor moved.

| metric | candidate | recal_null | improvement |
|---|---:|---:|---:|
| all-tick Brier | 0.073353613894633171 | 0.073316945556600524 | -0.000036668338032638 |
| tail Brier | 0.006840435259547864 | 0.006785181571841887 | -0.000055253687705977 |
| tail ECE | 0.001244584782360570 | 0.001493409874920180 | +0.000248825092559610 |
| tail log loss | 0.030833806300609553 | 0.028761870222461097 | -0.002071936078148454 |

The candidate is BEHIND recal_null on tail log loss and on Brier; tail ECE has a
lower point estimate; no AHEAD is classified. All-tick log loss (candidate 0.221012755499419800, recal_null
0.219637744063081790) is stored as an implementation diagnostic; per the
specification no all-tick log-loss comparison claim is made.

No interval was preregistered or computed for the tail log-loss improvement, so
none is claimed; the figure above is a point estimate.

### Epsilon and endpoint accounting

Epsilon is 1e-15. Nothing is excluded and nothing is silently dropped.

| arm | n | zero-probability rows | one-probability rows | clipped rows | excluded rows |
|---|---:|---:|---:|---:|---:|
| candidate | 465,249 | 62,154 | 80,162 | 142,316 | 0 |
| recal_null | 465,249 | 0 | 0 | 0 | 0 |

Named sensitivity, NOT the headline and not a re-scored metric: 18 tail rows
across 2 games are saturated at 0 or 1 in the direction opposite the outcome and
carry 621.70 of the 9,520.12 total tail candidate log loss, or 6.53 per cent.
Removing them still leaves the candidate BEHIND (tail log-loss improvement
-0.000365626298771), so the verdict does not depend on them. The headline row of
the table above excludes nothing.

OT periods 5-6: 14,765 ticks. Zero-clock ticks: 271,154.

## S289 diagnostic: favorite-longshot fine bins (frozen mask)

Every declared bin is published, including the two where recal_null is worse.
All six carry n well above 30; none is suppressed.

| bin | ticks / games | recal_null log loss | market log loss | recal_null gap | market gap |
|---|---:|---:|---:|---:|---:|
| [0.01,0.05) | 9,226 / 649 | 0.108935350460834 | 0.109064231604745 | 0.006470141952717 | 0.004081942336874 |
| [0.05,0.10) | 8,982 / 691 | 0.261167621122677 | 0.261923312933974 | 0.004348377544154 | 0.000239144956580 |
| [0.10,0.20) | 15,778 / 826 | 0.468033294804994 | 0.469461864991162 | 0.019818448650576 | 0.025861801242236 |
| [0.80,0.90) | 23,912 / 1,005 | 0.452100455173979 | 0.452417312322612 | 0.015170230012502 | 0.018535170625627 |
| [0.90,0.95) | 13,123 / 871 | 0.251914078110729 | 0.251267723457134 | 0.008520477420082 | 0.005711079783586 |
| [0.95,0.99) | 12,624 / 827 | 0.127493601362987 | 0.126642126705553 | 0.001947681034294 | 0.000232176806084 |

`gap` is the absolute difference between the empirical outcome rate and the mean
probability. recal_null carries the lower log loss in four bins and the higher in
two ([0.90,0.95) and [0.95,0.99)); both are published.

## S291 diagnostic: comeback states in the TRAILING-team frame

Mask, fixed before scoring by margin and clock alone:
`period <= 4 and abs(margin) >= 12 and remaining_s <= 720`, giving 133,184 ticks
across 1,111 games, `remaining_s` spanning 0 to 720, of which 55,871 ticks have
the home team trailing. States where the trailing team LOST are reported, not
removed: 434 trailing-side wins against 132,750 trailing-side losses. Attempt 1
reported these reversed (132,750 / 434) because it published the leading team's
frame.

Whole-mask log loss in the trailing frame: market 0.016139711921026808,
recal_null 0.016235344240117180.

Every declared reliability cell is listed. A cell with `0 < n < 30` publishes its
count only; `n = 0` is an empty declared bin, not a suppression.

| bin | market n | market mean p | market empirical | market log loss | recal_null n | recal_null mean p | recal_null empirical | recal_null log loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| [0.00,0.10) | 131,886 | 0.002897176349271 | 0.002449084815674 | 0.010813049798038 | 131,580 | 0.002909383233035 | 0.002393980848153 | 0.010573439634445 |
| [0.10,0.20) | 722 | 0.140852493074792 | 0.137119113573407 | 0.405113882682733 | 1,013 | 0.132542966758871 | 0.098716683119447 | 0.325390789829045 |
| [0.20,0.30) | 121 | 0.237690082644628 | 0.090909090909091 | 0.384926967762416 | 136 | 0.241158719136670 | 0.132352941176471 | 0.444187618658882 |
| [0.30,0.40) | 70 | 0.367607142857143 | 0.014285714285714 | 0.469751096586284 | 71 | 0.368395768054502 | 0.014084507042254 | 0.470172575828183 |
| [0.40,0.50) | 302 | 0.465110927152318 | 0.000000000000000 | 0.626504494495077 | 310 | 0.469573239384057 | 0.000000000000000 | 0.634819427119385 |
| [0.50,0.60) | 38 | 0.517763157894737 | 0.000000000000000 | 0.729889097932150 | 29 | SUPPRESSED n<30 | SUPPRESSED n<30 | SUPPRESSED n<30 |
| [0.60,0.70) | 6 | SUPPRESSED n<30 | SUPPRESSED n<30 | SUPPRESSED n<30 | 6 | SUPPRESSED n<30 | SUPPRESSED n<30 | SUPPRESSED n<30 |
| [0.70,0.80) | 20 | SUPPRESSED n<30 | SUPPRESSED n<30 | SUPPRESSED n<30 | 20 | SUPPRESSED n<30 | SUPPRESSED n<30 | SUPPRESSED n<30 |
| [0.80,0.90) | 0 | empty bin | empty bin | empty bin | 0 | empty bin | empty bin | empty bin |
| [0.90,1.00] | 19 | SUPPRESSED n<30 | SUPPRESSED n<30 | SUPPRESSED n<30 | 19 | SUPPRESSED n<30 | SUPPRESSED n<30 | SUPPRESSED n<30 |

Suppressed cells, with counts, are: market [0.60,0.70) n=6, [0.70,0.80) n=20,
[0.90,1.00] n=19; recal_null [0.50,0.60) n=29, [0.60,0.70) n=6, [0.70,0.80)
n=20, [0.90,1.00] n=19. Nothing was dropped and nothing was merged. Both arms
show the same qualitative shape: below 0.10 the trailing side is very slightly
over-forecast, and between 0.30 and 0.50 both arms forecast far above an
empirical rate of essentially zero.

## Retained comparison bar, published as a comparison result

The all-ticks S272 Brier improvement bootstrap interval reproduces exactly:
`[-0.000070422974932106, -0.000008368211469821]`. Its lower bound,
-0.000070422974932106, lies above the preregistered `-0.0005` tolerance
(one eighth of the frozen `+0.004` bar). This is published as a COMPARISON
RESULT only. S293 neither passes nor fails on it, and it creates no acceptance
condition; the `+0.004` bar is untouched.

## Machine and artifacts

Scored once on the pod, in a fresh per-job scratch root; no deployed tree and no
data tree was written.

- job `s293_attempt2_run1`, root `/workspace/wt/a14/jobs/s293_attempt2_run1`
- log tail: `S293 verdict=NOT_VALIDATED rss_before=197840896 rss_after=837103616`
  then `POD_RUN_DONE job=s293_attempt2_run1 rc=0`
- RSS 197,840,896 bytes before, 837,103,616 bytes after
- source identities remeasured before AND after the run and identical to the
  sealed preregistration: cpcv_engine `5accfbe4...c9d2`, walkforward
  `c8a9b5b0...bc2e`, s272_ingame_tail_recal `83f86f6a...ca30`,
  ingame_incumbent_nba `476ed9fd...08ed`

Artifacts, SHA-256 of the fetched bytes:

| path | bytes | SHA-256 |
|---|---:|---|
| `docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07_summary.json` | 14,663 | `7714ea02d95e64828ea9617ad740c3cea393d87a989ffaec45724c39d3860da3` |
| `docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07_paired_losses.csv.gz` | 7,071,878 | `e557986b768db703f8e62f96e9aac1c280b3a3707760faa7192a1c3d898eeef0` |

The paired-loss artifact holds 465,249 rows, 465,249 unique `game_id`/`ts` keys,
1,593 games and both split groups, with the evaluator fields `p_model`,
`p_close`, `y`, `split_id`, `n_train` retained and only additive loss columns
beside them. It is 7.07 MB, below the 50 MB threshold, so it is committed as-is.

The summary's `paired_losses` string records the output path as Git Bash rewrote
it (see NEW GAPS); the artifact content is unaffected and its hash is above.

## Tests

`python -m pytest tests/platformkit/test_s293_tail_metric_rail.py -q -p no:cacheprovider`
-> 5 passed in 2.27s (re-measured at landing). The file grew from 2 tests to 5:

- `test_s293_prereg_and_one_archived_game_tail_log_losses_are_finite` -- seal
  check plus one archived game's finite tail log losses.
- `test_s293_direct_endpoints_mixed_grain_and_trailing_ot_fixture` -- direct loss
  arithmetic, endpoint counts, mixed-grain refusal.
- `test_s293_trailing_side_uses_the_trailing_team_frame` -- NEW. Home-trailing
  row keeps its own `p`/`y`; away-trailing row takes the complement; a third row
  is an unsuccessful trailing state that must survive as outcome 0. Also asserts
  the non-finite-margin refusal.
- `test_s293_reliability_cells_below_thirty_publish_n_but_no_score` -- NEW. A
  40-row cell scores, a 6-row cell publishes `n = 6` with null scored fields and
  `suppressed_below_min_n` true, and an empty bin publishes `n = 0` unflagged.
- `test_s293_comeback_excludes_ot_period_from_n_ticks_but_counts_it_separately`
  -- NEW in fix 2b (test line 61). The `_comeback` period-cap fixture: periods
  1-3 cannot enter the comeback mask, the period-4 row does, and the period-5
  (OT) row lands only in the period-cap exclusion counters.

## Contract self-check

- B1: every one of the 465,249 regenerated ticks is scored and every declared bin
  published; the 18-row sensitivity is labelled as such and changes no headline.
- B2: evaluator fields are retained; only new loss columns and the
  `suppressed_below_min_n` flag are added, and no external reader exists.
- B5: the sole measurement ran in a fresh pod scratch job root; nothing was
  deployed before verification.
- B7: masks are declared, not head slices.
- B10: the `+0.004` bar and the `-0.0005` tolerance are byte-identical to the
  specification.
- Q1: the preregistration was sealed and committed alone before any metric.
- Q2: no trial is charged; no ledger or register file was opened.
- Q3: no bar or threshold moved.
- Q4: the S272 CPCV route, purge and one-day symmetric embargo are unchanged, and
  the replay agrees to 2.6e-18.
- Q6: calibration language only.
- Q7: every scored cell has n >= 30; smaller cells publish counts only.
- Q8: the source identities and the comeback-mask premise were remeasured before
  scoring, and the specification's quoted count is corrected above.
- Q9: the per-tick paired-loss differential is archived with cluster id,
  timestamp and both arms' probabilities.

## NOT VERIFIED

- Pod repeatability beyond this single recorded run. The route is deterministic
  but a second run was not made.
- No confidence interval for the tail log-loss improvement; none was
  preregistered.
- No candidate fit, and no calibration acceptance under the frozen comparison
  bar. This row measures only.
- Independent verifier reproduction in the landing worktree.
- The attempt-1 artifacts committed at `df0f033f6` are left in place and are NOT
  re-verified here; this memo supersedes them.

## NEW GAPS

- Git Bash rewrote the absolute `--output-dir /workspace/...` argument into
  `C:/Program Files/Git/workspace/...` before it left the Windows side, so the
  pod wrote both artifacts under that prefix inside the job root and pod_run's
  `--fetch` missed them. They were copied to the declared path on the pod and
  fetched with matching SHA-256; the scoring was not repeated. Any pod command
  taking an absolute remote path needs `MSYS_NO_PATHCONV=1`.
- `/c/Users/neelj/bin/pod_run` was rewritten by another lane while this lane was
  invoking it; two invocations died on bash syntax errors from reading a
  half-written file, and neither reached the pod. This run used a byte-stable
  snapshot of the launcher (SHA-256
  `29472b27fc275d49c4ca0eaaaeb179038d0f2a5c5b0958041ffb523fce17c0c6`) taken after
  three identical reads. The shared launcher needs an atomic rename on update.
- The new launcher gives every job a fresh root, so read-only inputs such as the
  39 MB S272 archive are re-shipped on every invocation.
- `/workspace/wt` is at 8,541 MB, above the launcher's 3 GB warning threshold.
  Not cleaned by this lane.
