SUPERSESSION: this file supersedes `docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md` after the verifier's corrections in `docs/evidence/harness/S309_VERIFY_2026-09-07.md` (gate order, retained aliases, fold membership + isotonic X/y archived, retained tail ECE published). The frozen attempt-2 memo is restored to its prior committed blob `c87bb1da8f39488ee5864e96f51e65955aa8462f` and is RETAINED UNCHANGED as prior dated evidence; it is not edited by this correction.

VERDICT: SCREEN ONLY -- the candidate is BEHIND on BOTH designs. Forward-only all-tick Brier improvement -0.000078450154, 95 pct CI [-0.000136780928, -0.000028628302]; CPCV all-tick improvement -0.000031583337, 95 pct CI [-0.000059550789, -0.000005652876]; design delta (forward minus CPCV) +0.000529854625, 95 pct CI [-0.000034107543, +0.001139144397], which INCLUDES ZERO, so DESIGN-SENSITIVE is False. This is a calibration screen. Nothing is promoted, nothing is charged, no monetary or advantage claim is made, and this memo is NOT VERIFIED.

# S309 canonical in-game loss audit -- attempt 2 (corrected re-run)

Attempt 1 (`e6384a12f`) was REJECTED. Attempt 2 candidate `eb6af5982` was also REJECTED, on four
ACCEPTANCE findings recorded in `docs/evidence/harness/S309_VERIFY_2026-09-07.md`. This memo
reports the CORRECTED attempt-2 re-run, scored once on the pod on 2026-09-07 from the sealed
attempt-2 preregistration plus a sealed supplement. No promotion, no feature flag, no register
write, no shared-ledger write, no source-store write.

## What the verifier rejected, and what this re-run changed

| verifier finding | candidate `eb6af5982` | this re-run |
|---|---|---|
| ACCEPTANCE: replay order | `_historical` and the S272 replay asserts ran AFTER `_score` | `_historical` and all three replay asserts run BEFORE `_score` and before any source store is read; a replay error above 1e-12 raises `NOT REPRODUCED` and the run stops (`scripts/platformkit/s309_canonical_loss_audit.py:195-199`) |
| B2: dropped aliases | the paired archive dropped `p_baseline` / `p_candidate`; the fold archive dropped the attempt-1 fold fields | the paired archive RETAINS `p_baseline` and `p_candidate` as aliases of the forward (deployment headline) arm beside the new per-arm columns; every fold record RETAINS all 15 attempt-1 fold fields (`s309_canonical_loss_audit.py:251-253`, `s309_design_evaluators.py:167-192`) |
| ACCEPTANCE: fold archive | no train/test membership, no fitted isotonic parameters | each fold archives its EXACT train and test game-id membership for both designs plus the fitted isotonic thresholds and values (X, y) for both tails, in `..._fold_members.parquet` (`s309_design_evaluators.py:167-201, s309_canonical_loss_audit.py:245-250`) |
| ACCEPTANCE: retained tail ECE | absent from the summary and the memo | the RETAINED S272 tail ECE change is replayed from the S272 paired losses and published in the summary JSON and in the table below (`s309_canonical_loss_audit.py:152-172`) |

## Preregistration, supplement and order (Q1)

Preregistration `docs/evidence/harness/S309_canonical_loss_audit_2026-09-07b_preregistration.md`,
seal `cd9e157abc95c2e699228069bfa40292621fc26f6e48fa0352b3d992e5f69cad`, recomputed over the
committed bytes above the seal line after normalizing CRLF to LF: MATCH. It is BYTE-IDENTICAL to
the attempt-2 seal (file SHA-256 `bbd30338c706faeec7106875bf2275b97d44817c78e0a63e0dc3f48256f8defd`)
and was committed alone in `bf7a14de8` before any metric.

Supplement `docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c_supplement.md`, seal
`b6d7bc237d9863838a852c82929fc107185d3263924bddb15070c2c8be19d6a7`, committed ALONE in
`24eb96561` BEFORE the code commit `d10bb756b` and before the re-run. It amends exactly one
preregistration clause -- the artifact stem moves from `2026-09-07b` to `2026-09-07c`, because the
`2026-09-07b` artifacts are already committed in `eb6af5982` and BAN2 forbids rewriting an
existing artifact. NO estimator, estimand, denominator, sign convention, seed, bootstrap count,
embargo, purge, grain or bar changed. The route verifies BOTH seals before it computes anything.

S293 `4a41c436e3650cfad1517d1987a27d09d5a00122` remains an ancestor of this branch, so the ORDER
clause still holds. The `2026-09-07`, `2026-09-07b`, S272 and S280 artifacts are untouched.

## Sign convention

Every improvement number is `baseline loss - candidate loss`: POSITIVE means the candidate is
better, NEGATIVE means the candidate is worse. The candidate is the S272 low/high-tail isotonic
recalibration; the baseline is the S272 logistic recalibration. The design delta is
`forward-only loss - CPCV loss`: POSITIVE means the CPCV loss is lower. The retained tail ECE
change is `candidate ECE - incumbent ECE`: NEGATIVE means the candidate's tail reliability gap is
smaller. The frozen comparison bar is +0.004 and was not changed.

## Replay-FIRST stop gate (the corrected order)

`_historical()` runs first, then three asserts, then `_s280_replay()`, and only then are the
source parquets opened and `_score` called. A replay error above 1e-12 stops the run with
`NOT REPRODUCED` and nothing is scored. The focused test
`test_s272_replay_is_a_stop_gate_ahead_of_scoring` proves the order by making the replay fail and
making both `pd.read_parquet` and `_score` raise: the run dies on the assert, so neither is
reached.

| replay | value | bar | result |
|---|---:|---|---|
| S272 historical baseline Brier | 0.073316945557 | -- | reproduced |
| S272 historical candidate Brier | 0.073353613895 | -- | reproduced |
| S272 baseline replay error | 0.0 | <= 1e-12 | PASS |
| S272 candidate replay error | 0.0 | <= 1e-12 | PASS |
| RETAINED S272 candidate improvement | -0.000036668338 | matches the spec's retained -0.000037 | reproduced |
| RETAINED S272 tail ECE, incumbent | 0.001493409875 | -- | reproduced |
| RETAINED S272 tail ECE, candidate | 0.001244584782 | -- | reproduced |
| **RETAINED S272 tail ECE change (candidate minus incumbent)** | **-0.000248825093** | matches the spec's retained -0.000248 | reproduced |
| S272 tail ECE replay error | 0.0 | <= 1e-12 | PASS |
| S280 tick-weighted minus equal-game delta | -0.000130557034 | -- | matches the spec premise 0.000130557 |

The tail ECE numbers are recomputed from the 308,756 `tail_tick` rows of the S272 paired-loss CSV
(1,590 games) with the same 10-bin ECE the route uses elsewhere, and reproduce the S272 summary
JSON to 1.8e-17. They are a RELIABILITY diagnostic, not a label: the DESIGN-SENSITIVE label is
read only off the preregistered primary paired Brier interval.

## Forward-only scoring (headline, deployment design)

Denominator: all 465,249 checkpoint ticks in 1,593 game clusters. No tick was dropped and no
outcome-based exclusion was applied. `positive_clock` (194,095) and `zero_clock` (271,154)
partition the 465,249 exactly. `unknown_status` is the terminal-like table, `period >= 4 and
game_clock_s == 0`: 244,183 ticks, matching the spec premise; its status is UNKNOWN because
receipt and final timestamps do not exist in these stores.

| table | ticks | games | baseline Brier | candidate Brier | improvement | 95 pct CI | candidate MDE |
|---|---:|---:|---:|---:|---:|---|---:|
| all | 465249 | 1593 | 0.073906391099 | 0.073984841253 | -0.000078450154 | [-0.000136780928, -0.000028628302] | 0.000053709961 |
| positive_clock | 194095 | 1593 | 0.152767880040 | 0.152914344242 | -0.000146464203 | [-0.000260383669, -0.000051682426] | 0.000105565618 |
| zero_clock | 271154 | 1593 | 0.017456474462 | 0.017486239416 | -0.000029764954 | [-0.000055830571, -0.000007305431] | 0.000024428895 |
| unknown_status | 244183 | 1592 | 0.000850316745 | 0.000846393758 | 0.000003922986 | [-0.000000906755, 0.000010221193] | 0.000005685285 |

Reading: on all ticks the tail-isotonic candidate is WORSE than the logistic baseline by
0.000078450154 Brier and the interval excludes zero, so the direction is resolved. The magnitude
is roughly two orders below the frozen +0.004 bar; the bar is not met in either direction. The
same negative direction holds on both clock partitions. On the terminal-like table the interval
spans zero, so that table is a null. Ratio bootstrap on game sums and counts, seed 901, 10,000
replicates.

Every one of these numbers is BIT-IDENTICAL to the rejected attempt-2 candidate `eb6af5982`. That
is the expected result: the four corrections are gate-ORDER and ARCHIVE changes, and the
supplement changed no estimator. The route hash changed (below) but the estimates did not.

## CPCV secondary scoring (labelled robustness companion)

| table | ticks | games | baseline Brier | candidate Brier | improvement | 95 pct CI | candidate MDE |
|---|---:|---:|---:|---:|---:|---|---:|
| all | 465249 | 1593 | 0.073423403292 | 0.073454986628 | -0.000031583337 | [-0.000059550789, -0.000005652876] | 0.000027119933 |
| positive_clock | 194095 | 1593 | 0.151788443540 | 0.151843624043 | -0.000055180502 | [-0.000109920177, -0.000006032116] | 0.000052250331 |
| zero_clock | 271154 | 1593 | 0.017328850059 | 0.017343542287 | -0.000014692227 | [-0.000028092050, -0.000002990586] | 0.000012510381 |
| unknown_status | 244183 | 1592 | 0.000861527540 | 0.000863918691 | -0.000002391150 | [-0.000008463056, 0.000001527381] | 0.000005144534 |

The candidate is BEHIND on the CPCV design too, on every table except the terminal-like one,
whose interval spans zero. Nothing here is a promotion and nothing is a monetary quantity.

## Named secondary diagnostics (they set no label)

| table | forward improvement | forward candidate log loss | forward candidate 10-bin ECE |
|---|---:|---:|---:|
| all | -0.000078450154 | 0.222624002 | 0.006105968 |
| positive_clock | -0.000146464203 | 0.459446166 | 0.013511882 |
| zero_clock | -0.000029764954 | 0.053104105 | 0.002721509 |
| unknown_status | 0.000003922986 | 0.003450113 | 0.001481479 |

| table | CPCV improvement | CPCV candidate log loss | CPCV candidate 10-bin ECE |
|---|---:|---:|---:|
| all | -0.000031583337 | 0.220456401 | 0.004191956 |
| positive_clock | -0.000055180502 | 0.454831515 | 0.009736413 |
| zero_clock | -0.000014692227 | 0.052688129 | 0.001777022 |
| unknown_status | -0.000002391150 | 0.003591182 | 0.001403858 |

## Design comparison (the absorbed S299 arm)

Primary design delta, forward-only minus CPCV, on candidate loss: **+0.000529854625**, 95 pct CI
[-0.000034107543, +0.001139144397]. The interval INCLUDES ZERO, so **DESIGN-SENSITIVE is False**.
The point estimate says the CPCV loss is lower, which is the expected direction for a design whose
train set straddles the test block on both sides, but at this sample the preregistered primary
interval cannot separate the two designs. That is an honest null on the design question.

The two arms are NOT the same series. They differ on 215,072 of 465,249 ticks, with a maximum
absolute candidate-probability difference of 0.720733267701 and a mean absolute difference of
0.014350587816 over the differing ticks. The remaining 250,177 ticks agree EXACTLY because both
arms' tail isotonic saturates to 0.0 or 1.0 there (236,416 of those 250,177 are clock-zero ticks,
where the market is already at an extreme). That saturation is a property of the data, not of the
code path, and it is stated here so it is not mistaken for the attempt-1 aliasing.

## Fold archive: exact membership and refittable candidate parameters

`..._folds.json` carries 1,297 fold records (1,269 forward fits, 28 CPCV fits) with 25 fields,
which is a strict SUPERSET of the attempt-1 fold schema. All 15 attempt-1 field names are retained
as aliases: `fold_date`, `min_test_date`, `max_train_date`, `train_games`, `test_games`,
`test_ticks`, `forward_only`, `cpcv_group`, `purge`, `embargo_days`, `fallback_market`, `coef`,
`intercept`, `low_points`, `high_points`. Every forward fold satisfies
`max_train_settle < first_test_state_ts`, checked over all 1,269 rows. Two forward fits fall back
to the raw market probability because no settled prior data existed.

`..._fold_members.parquet` (1,297 rows) carries the parts that would have made the JSON roughly 30
MB: per fold, the EXACT train and test game-id membership and the fitted isotonic thresholds and
values for both tails.

| archived per fold | total across the 1,297 folds |
|---|---:|
| `train_game_ids` (exact train membership) | 1,050,025 ids |
| `test_game_ids` (exact test membership) | 12,744 ids |
| `isotonic_low_x` / `isotonic_low_y` points | 29,317 pairs |
| `isotonic_high_x` / `isotonic_high_y` points | 34,007 pairs |

Together with `coef` and `intercept` in the folds JSON, this is enough to refit and re-predict any
fold's candidate without re-running the route. The focused test
`test_every_fold_archives_membership_tails_and_the_attempt1_aliases` does exactly that: it refits
`fit_calibrator` on a fold's archived train ids and asserts the recovered logistic coefficient and
intercept and BOTH isotonic threshold/value arrays match the archive, and that no fold's train set
intersects its own test set.

## Paired archive: retained aliases

`..._paired_losses.parquet` columns, in order:
`state_key, game_id, state_ts, home, away, game_date, period, game_clock_s, outcome_home_win,`
`p_baseline, p_candidate, p_forward_baseline, p_forward_candidate, p_cpcv_baseline,`
`p_cpcv_candidate, loss_forward_baseline, loss_forward_candidate, loss_cpcv_baseline,`
`loss_cpcv_candidate, evaluator_records`.

This is a strict superset of the attempt-1 paired columns. `p_baseline` and `p_candidate` are the
retained attempt-1 names and are verified equal, element by element, to `p_forward_baseline` and
`p_forward_candidate` (the forward arm is the deployment headline, which is what those names meant
in attempt 1).

## Embargo and purge provenance

| property | forward-only arm | CPCV arm |
|---|---|---|
| evaluator | `scripts.platformkit.eval_gate.walkforward.walk_forward` | `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` |
| records returned | 1593 (one per game cluster) | 11151 (7 paths per cluster) |
| distinct fits | 1269 | 28 (one per path) |
| same-team purge | 48 hours (shared) | 48 hours (shared, symmetric) |
| same-matchup embargo | 3 days (shared) | 3 days (shared, symmetric) |
| calendar embargo | forward-only, none added | 1 day, SYMMETRIC on both sides of every test block |
| extra train rule | settled strictly before the test state timestamp | none: straddling is the design under test |
| strict redaction | True | True |
| S301 duplicate-state-key guard | True | True |
| train-set size range | 0 to 1592 states | 1130 to 1210 states |

CPCV design: 8 groups, 2 test groups, 28 paths, so every game is a test row on exactly 7 paths and
its CPCV probability is the mean over those paths. Per-path test-cluster counts range from 370 to
442 games.

GRAIN, declared in the preregistration before scoring: the shared evaluators build each test row's
train set with a per-state loop that is quadratic in the number of states, so they are driven at
game-cluster grain -- one evaluator state per game (1,593), each emitting one out-of-fold
probability for every tick of its test game. The scored series is therefore one prediction per
tick per design, `state_key` is unique over all 465,249 rows, and the tick series agrees with each
evaluator's own returned records to 2.22e-16 (bar 1e-9).

## Canonical source accounting (the absorbed S300 arm)

Denominator: 8,092,183 moneyline rows out of 8,399,632 rows in `nba_price_series.parquet`. Every
source row is retained in the accounting artifact with all original columns plus aliases, and
carries exactly one reason. The accounting and keys parquets are BYTE-IDENTICAL to attempt 2's
(SHA-256 `297586e2...` and `581c332b...`): this arm was not touched by the corrections.

| accounting reason | rows |
|---|---:|
| CANONICAL | 4917502 |
| EXACT_DUPLICATE_TICK | 1417673 |
| UNPARSEABLE_EVENT | 1642063 |
| COMPLEMENT_UNUSED_HOME_PRESENT | 114945 |
| total | 8092183 |

Canonical branch split: DIRECT_HOME 4,896,419 and COMPLEMENT_AWAY 21,083.

| added bar | value | result |
|---|---:|---|
| duplicate canonical keys | 0 | PASS |
| unaccounted source rows | 0 | PASS |
| Polymarket games joined | 1593 / 1593 | PASS |
| probability replay max abs error | 0.0 (bar <= 1e-12) | PASS |
| `polymarket_probability_replay_max_abs_error` (retained alias) | 0.0 (bar <= 1e-12) | PASS |
| cross-venue overlapping games | 40 | REPORTED, not closed at limit (bar was "closed below 30") |

## Inputs (absolute path, bytes, SHA-256, rows, columns, first ids)

Absolute paths are given for this worktree, `C:\Users\neelj\nba-track-a15`. The summary JSON's
`absolute_path` field records the POD scratch path the route actually opened, which is
`/workspace/wt/a15/jobs/20260907212659_399482_14011/<same relative path>`; the bytes and SHA-256
are identical on both sides because the ship is a byte-preserving tar.

| absolute path | rows | cols | bytes | sha256 | first 3 ids |
|---|---:|---:|---:|---|---|
| `C:\Users\neelj\nba-track-a15\data\cache\inplay_odds\nba_checkpoints_full.parquet` | 465249 | -- | 2829826 | 5ea6498d88bf7548395c700c7239641dcbd1d641bdaddb5a6b63fcf0ea8909e5 | 401704627, 401704627, 401704627 (`game_id`) |
| `C:\Users\neelj\nba-track-a15\data\cache\inplay_odds\nba_price_series.parquet` | 8399632 | -- | 25140428 | 3db7d0444d800cfe487ab48c4780a9283b3a621511e0b259975a4339b970bd5b | KXNBAGAME-26APR26BOSPHI, x3 identical (`event_key`) |
| `C:\Users\neelj\nba-track-a15\data\domains\basketball_nba\espn_nba_game_bridge.parquet` | 1299 | -- | 46002 | e0e0ab68d6882bf77987dca2890a1896376ffe18d8e46d11656338a7ec037f4f | 0022500001, 0022500002, 0022500004 (`game_id`) |
| `C:\Users\neelj\nba-track-a15\docs\evidence\harness\S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv` | 310349 | 15 | 39159272 | 77eebaa5e82d81d6a428874b937939353e15af21b6270b84f83691489297eeed | 401703370, 401703371, 401703372 (`game_id`) |
| `C:\Users\neelj\nba-track-a15\docs\evidence\harness\S272_ingame_tail_recal_screen_2026-09-04_summary.json` | -- | -- | 5290 | 1892f277dc7b55683792b7ac2491e8faf5b06ab20ad1f7b6f3ef087b0be70914 | -- (JSON, not a table) |
| `C:\Users\neelj\nba-track-a15\docs\evidence\harness\S280_ingame_cross_venue_disagreement_2026-09-04_ticks.csv` | 8828 | 12 | 1545580 | d4a54b48b01870add669f37621d2cb87833f0c60fa6ed1de96de252ce7c80dd8 | 401869406, 401869406, 401869406 (`game_id`) |

Full column lists for the two CSV inputs the verifier asked for:

- S272 paired losses: `record_type, game_id, season, game_date, split_id, n_ticks,`
  `loss_candidate_sum, loss_incumbent_sum, n_train_games, ts, outcome_home_win, candidate,`
  `incumbent, loss_candidate, loss_incumbent`.
- S280 ticks: `split_id, game_id, state_ts, checkpoint_ts, kalshi_ts, outcome, p_recal_null,`
  `p_augmented, n_evaluator_records, loss_recal_null, loss_augmented, metric_augmented_minus_null`.

The full `columns` list for all six inputs is also archived verbatim in the summary JSON under
`inputs[].columns`, `historical.input.columns` and `s280.input.columns`.

## Evidence filename mapping (verifier NEW GAP)

The spec's EVIDENCE line names `S309_canonical_loss_audit_2026-09-04.md` plus its JSON, keys,
folds, paired losses and hashes. No `2026-09-04` S309 artifact was ever written by this row. The
mapping from the spec's names to the files that exist is:

| spec EVIDENCE name | attempt 1 | attempt 2 (rejected) | this corrected re-run |
|---|---|---|---|
| `S309_canonical_loss_audit_2026-09-04.md` | `..._2026-09-07.md` | `..._attempt2_2026-09-07.md` | this file (same name, regenerated) |
| its JSON | `..._2026-09-07.json` | `..._2026-09-07b.json` | `..._2026-09-07c.json` |
| its keys | `..._2026-09-07_keys.parquet` | `..._2026-09-07b_keys.parquet` | `..._2026-09-07c_keys.parquet` |
| its folds | `..._2026-09-07_folds.json` | `..._2026-09-07b_folds.json` | `..._2026-09-07c_folds.json` plus `..._2026-09-07c_fold_members.parquet` |
| its paired losses | `..._2026-09-07_paired_losses.parquet` | `..._2026-09-07b_paired_losses.parquet` | `..._2026-09-07c_paired_losses.parquet` |
| its hashes | `..._2026-09-07_hashes.json` | `..._2026-09-07b_hashes.json` | `..._2026-09-07c_hashes.json` |

The `2026-09-04` label in the spec is a date this row never ran on. This lane did not edit the
spec; aligning the spec's EVIDENCE line to the dates that exist is an orchestrator action for the
next spec VERSION.

## Code identity (A11)

Route `scripts/platformkit/s309_canonical_loss_audit.py` SHA-256
`1eba553b9982a529ec9afa4304d0feb2008404c31c95d5f9e737a470e755b93e` (it changed from attempt 2's
`67128d59...` because of the four corrections). Shared
`scripts/platformkit/eval_gate/walkforward.py`
`c8a9b5b0f0f7c84dc5fdb0c7a4a27e0f7f2040f99326ef5376cde011df27bc2e` and
`scripts/platformkit/eval_gate/cpcv_engine.py`
`5accfbe490031acb084a8e4375a082b00d842cf4011a76c6d27dfc2c7db614a5` -- both UNCHANGED from attempt
2 and unmodified by this row. These are the raw bytes shipped to the pod.

## Test result

Per-file only, run in the worktree `C:\Users\neelj\nba-track-a15`:

| file | command | result |
|---|---|---|
| tests/platformkit/test_s309_canonical_loss_audit.py | `python -m pytest <file> -q -p no:cacheprovider` | 5 passed |
| tests/platformkit/test_s309_design_evaluators.py | `python -m pytest <file> -q -p no:cacheprovider` | 3 passed |
| tests/platformkit/test_loc_rail_scope.py | `python -m pytest <file> -q -p no:cacheprovider` | 1 passed |

Total 9 passed, 0 failed, 0 skipped (attempt 2 had 6). The three ADDED tests:

1. `test_s272_replay_is_a_stop_gate_ahead_of_scoring` -- makes the S272 replay fail and makes both
   `pd.read_parquet` and `_score` raise, then asserts the run dies on `NOT REPRODUCED`. If the
   gate were still ordered after `_score`, this test would raise the sentinel instead and fail.
2. `test_retained_s272_values_replay_including_the_tail_ece_change` -- asserts all three replay
   errors are <= 1e-12 and that the retained candidate improvement and the retained tail ECE
   change reproduce the spec's retained values.
3. `test_every_fold_archives_membership_tails_and_the_attempt1_aliases` -- asserts the fold archive
   schema is a superset of the attempt-1 fold fields, that every fold's train/test id counts agree
   with its own tick counts, that no fold trains on one of its own test games, and that refitting
   `fit_calibrator` on a fold's archived train ids recovers that fold's archived logistic
   coefficient, intercept and both isotonic threshold/value arrays.

No LOC allowlist entry was raised: `s309_canonical_loss_audit.py` is 275 lines and
`s309_design_evaluators.py` is 281, both under the 300-line rail, so A12 does not apply. The test
files are 94 and 119 lines.

## Pod run, wall and RSS

Compute-only scratch job under `/workspace/wt/a15` via `C:/Users/neelj/bin/pod_run a15`, run
EXACTLY ONCE for this correction. The deployed tree `/workspace/nba-ai-system` was never written;
`data/registry`, `backtest_fwer.jsonl` and `hypotheses*.sqlite` never reached the pod; no pod
process was stopped or restarted.

- Job `20260907212659_399482_14011`, log
  `/workspace/wt/a15/jobs/20260907212659_399482_14011/pod_run.log`
- Log tail:
  `S309 verdict=SCREEN_ONLY all_improvement=-0.000078450154 design_delta=0.000529854625 fits=1269/28 rss_bytes=7710310400`
  followed by `POD_RUN_DONE job=20260907212659_399482_14011 rc=0`, then seven `FETCHED` lines.
- Route RSS reported by the route itself: 7,710,310,400 bytes (7.71 GB), up from attempt 2's 6.87
  GB because of the fold membership and isotonic archive. This is why the preregistration routed
  this to the pod rather than the laptop.
- Wall: dispatched 21:26:57 CDT, finished and fetched by 22:47 CDT. The route process itself ran
  about 57 minutes (02:48 to 03:45 UTC). About 9 minutes of the total was `pod_run`'s own
  `du -sm /workspace` preflight, which is slow while the 16-worker tracking daemon shares the box.
- Pod state at dispatch: `/workspace` 38,608 MB of 50,000; `/workspace/wt` 18,123 MB, above the 3
  GB threshold `pod_run` warns on. This lane deleted nothing; the tracking session should be
  pinged, per `pod_run`'s own message.

## Artifact hashes (all recomputed locally after the fetch; all MATCH)

| artifact | bytes | sha256 |
|---|---:|---|
| S309_canonical_loss_audit_2026-09-07c.json | 12938 | 89f29559ac05bd25b855603ab55117ddfbbaf6e24a26f8600cc64701f1178f08 |
| S309_canonical_loss_audit_2026-09-07c_accounting.parquet | 25918089 | 297586e2fa98e733d50f7abce36b95cdc488b0f3e59792cb766e55edb7b47d68 |
| S309_canonical_loss_audit_2026-09-07c_fold_members.parquet | 1011071 | cfe86e5d205414ebe898ec9f8f527bc97cb8540a01b889748c1dea8c8451ec48 |
| S309_canonical_loss_audit_2026-09-07c_folds.json | 1077851 | 6093fd34aa9bbba4c2648679488a54a88ea7a1c1a2cdca050552c17a6635ed39 |
| S309_canonical_loss_audit_2026-09-07c_keys.parquet | 18774245 | 581c332b893b426dc13bb3a8f1f27a8a37aaf1010cb31f90ed2fc9de5b08f41d |
| S309_canonical_loss_audit_2026-09-07c_paired_losses.parquet | 12164504 | 37fcde209fa9d6ae96ed24f858463fce4a4b898a69d31167e0b8a0e52254cea2 |
| S309_canonical_loss_audit_2026-09-07c_supplement.md | 2842 | 59294032c7b420362d744f9239ab17ad41aed5cdd3ce171d10386533292e8bf7 |

`S309_canonical_loss_audit_2026-09-07c_hashes.json` (885 bytes) is the manifest above; it does not
contain its own hash, and it contains no entry for this memo. The route emits no memo, so nothing
here can carry a stale hash of a rewritten file.

## Spec alignment notes (verifier NEW GAPs, not fixed here -- spec is orchestrator-owned)

(a) `docs/evidence/tracking/specs/S309_spec.md:27` names `S309_canonical_loss_audit_2026-09-04.md`
as the EVIDENCE filename; the artifacts that exist are dated 2026-09-07, 2026-09-07b and
2026-09-07c. The mapping from the spec's names to the files that exist is the "Evidence filename
mapping" table above; it is unchanged from the corrected re-run and is kept here rather than
resolved, since editing the spec is not this lane's action. The next spec VERSION should align the
EVIDENCE line to the dates that exist.

(b) `docs/evidence/tracking/specs/S309_spec.md:17` ("CHANGE: ... one state per tick with real
game/team ids") reads as one evaluator state per tick. The shared evaluators instead run at
GAME-CLUSTER grain -- one evaluator state per game (1,593), each emitting one out-of-fold
probability for every tick of its test game -- as declared BEFORE scoring in the sealed
preregistration `docs/evidence/harness/S309_canonical_loss_audit_2026-09-07b_preregistration.md:84-86`
and reaffirmed as an unchanged clause in the sealed supplement
`docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c_supplement.md:12` ("No estimator,
estimand, denominator, sign convention, seed, bootstrap count, embargo, purge, grain or bar
changes"). The scored series is still one prediction per tick per design (`state_key` unique over
all 465,249 rows; see the GRAIN paragraph above), so the acceptance-rule denominators are met; the
gap is the spec's wording of the per-state grain against the per-tick output grain, and the
requirement or the route should be aligned in the next spec VERSION.

(c) Master carries neither `tests/platformkit/test_s309_canonical_loss_audit.py` nor
`tests/platformkit/test_s309_design_evaluators.py` today, so contract A1's baseline-command check
cannot run there. Both files exist only on this branch (`track-a15`) and must be added to master
as part of the S309 landing commit, alongside the corrected route and evaluators.

## Proposed ledger row (appended by the lander, not the lane)

Spec line 31 bans a shared-ledger write from this row (`docs/evidence/tracking/specs/S309_spec.md:31`:
"never write ... shared-ledger writes"). Fix 2b appended the row below directly to
`docs/evidence/RESULTS_LEDGER_SYSTEM.md:544`; that append has been reverted from the worktree by
this correction. The row text is preserved here so the orchestrator/lander can add it to the
shared ledger if and when that is the correct action, rather than a lane appending it itself:

```
2026-09-07 | nba in-game calibration | S309 | attempt-2 corrected re-run (replay-first stop gate, retained p_baseline/p_candidate + attempt-1 fold aliases, exact fold train/test membership + fitted isotonic X/y, retained S272 tail ECE change -0.000248825093 published): forward all-tick Brier improvement -0.000078450154 CI [-0.000136780928, -0.000028628302] on 465249 ticks/1593 games; CPCV -0.000031583337; design delta +0.000529854625 CI [-0.000034107543, +0.001139144397] DESIGN-SENSITIVE False | SCREEN ONLY, NOT VERIFIED (lane self-report; codex-verify dispatched) | d10bb756b
```

## NOT VERIFIED

- **This memo has not been verified.** It is the lane's own report of a corrected re-run whose
  predecessor was REJECTED. A `codex-verify` dispatch follows this commit; until that returns,
  nothing here is verified by anyone but the lane.
- **The design question is a NULL, not a resolution.** The primary design interval
  [-0.000034107543, +0.001139144397] includes zero, so DESIGN-SENSITIVE is False. The point
  estimate favours the CPCV design but this run cannot separate the two designs at n = 1,593
  clusters.
- **The evaluators are driven at game-cluster grain, not tick grain.** One evaluator state per
  game, not per tick, because the shared routes are quadratic per state and 465,249 states is not
  runnable through them. Each call emits one out-of-fold probability per tick of its test game and
  the tick series reproduces the evaluators' own records to 2.2e-16, but a reader who expects
  465,249 evaluator states will not find them. This was declared in the preregistration before
  scoring; see "Spec alignment notes" (b) above.
- **The forward arm extra settle rule is this row's, not the shared route's.** `walk_forward`
  orders states by game start; dropping train games not settled before the test timestamp is an
  additional restriction applied inside this row's predictor. It is strictly tighter, not looser.
- **The archived isotonic (X, y) points are the fitted interpolation knots, not a re-run.** They
  let a reader refit and re-predict any fold, and one fold is checked that way in the focused
  test, but no independent party has yet refit all 1,297 folds from the archive.
- **The cross-venue arm is REPORTED, not closed.** 40 overlapping games is at or above the bar of
  30, so the preregistered "CLOSED AT LIMIT below 30 games" clause does not apply and no
  cross-venue conclusion is drawn here.
- **Terminal status is UNKNOWN.** Receipt and final timestamps do not exist in these stores, so the
  244,183 period >= 4 / clock-zero ticks are labelled UNKNOWN rather than terminal. No
  outcome-based exclusion was used to make them look clean.
- **The Kalshi ticker team order is an assumption.** The parser reads `KXNBAGAME-<date><AAAHHH>` as
  away-then-home, mirroring the Polymarket slug convention. No independent source confirms that
  order for Kalshi tickers, and 40 games is the entire Kalshi overlap, so a swap would change only
  that arm.
- **The spec's EVIDENCE line still names `2026-09-04` filenames.** The mapping to the files that
  actually exist is tabulated above and restated in "Spec alignment notes" (a). This lane did not
  edit the spec; the next spec VERSION should align it.
- **Master carries neither S309 test file**, so the contract A1 baseline command cannot run on
  master today. Both focused test files exist only on this branch and will arrive on master with
  the landing; see "Spec alignment notes" (c). The verifier filed this and the landing must add
  them.
- **The shared-ledger row is proposed, not written.** Spec line 31 bans a shared-ledger write from
  this row. Fix 2b's append to `docs/evidence/RESULTS_LEDGER_SYSTEM.md:544` has been reverted; the
  row text is preserved above under "Proposed ledger row" for the orchestrator/lander to apply.
- **No promotion, no second corpus.** This is a calibration screen on one corpus. Nothing here is a
  deployment decision, the +0.004 bar was neither met nor moved, and no monetary or advantage
  claim is made anywhere in this memo.
