# S824 -- the paper-night scoreboard step crosses its 900 s deadline once the cumulative training history is large (2026-10-15)

Owner: paper-desk-improve scheduled run (T3), 2026-10-15. Row allocated by the paper-desk-morning run (T2) the
same day from nights/2026-10-13.json. PAPER ONLY; calibration language only. Severity P0 by the recurrence rule
(10-13 and 10-14 both KILLED). AMENDMENT 1 (contract tier, 2026-10-15): the cost is quadratic in the cumulative
history (section 1), the deadline is 3,600 s with the tick's night timeout raised to 9,900 s (section 2; AMENDMENT 2 from the adversarial tier: 10,800 collided with the scheduled task's PT3H execution limit), and
the fifth budget pin in test_s485_baseline_contract.py is part of the landing.

## 1. Premise (fresh reads, master 5f4b25aca)

| night | scoreboard step | wall s | training rows passed | free RAM at start | sports |
|---|---|---|---|---|---|
| 2026-10-07 | RAN | 101.2 | none (history_refused config_mismatch) | 4.29 GB | mlb nba |
| 2026-10-08 | RAN | 579.0 | 15,866 (3.9 MB) | 7.17 GB | mlb nba tennis |
| 2026-10-09 | RAN | 659.2 | 16,071 (4.0 MB) | 2.37 GB | mlb nba nfl soccer tennis |
| 2026-10-10 | RAN | 8.7 | 19,596 (4.9 MB) | 2.41 GB | nba ncaaf soccer tennis (no fittable corpus rows) |
| 2026-10-12 | RAN | 65.3 | none (candidate file absent) | 3.23 GB | mlb nba soccer |
| 2026-10-13 | KILLED step_deadline_exceeded | 900.5 | 29,154 (training/2026-10-13.jsonl, 7,196,070 B) | 1.74 GB | mlb nba nfl soccer |
| 2026-10-14 | KILLED step_deadline_exceeded | 900.2 | 29,154 (training/2026-10-14.jsonl: same row count and byte length, different content from line 26,257) | 1.61 GB | mlb nba |

The wall follows the training rows the step is given, not free RAM (10-08 took 579 s at 7.2 GB free; on 10-14
qualification, fill_realism and e ran normal walls at the same 1.3-1.6 GB). Read volume is not it either: the
10-13 step read 993 MB of shards (the retrospective night parses the full D+1 shard) against 450-860 MB on
10-12, at most 2x.

Where the wall goes (sealed code, read only): ingame_scoreboard._models passes every validated training row of
the sport PLUS tonight's ticks to baseline_four_arm.predict_rows (ingame_scoreboard.py:158), whose
walk_forward(states, predict) (eval_gate/walkforward.py:138-149) calls `predict` once for EVERY row passed in
and builds a new train list per row; `predict` filters that list again and fits `logistic(train, test, names)`
for arms B and C (and D on the model subset); only tonight's rows are kept afterwards
(ingame_scoreboard.py:163). Cost is therefore rows x training rows: QUADRATIC in the cumulative history. The
S766 cumulative history (commit B, 10-07) grows the training file every scored day (15.9k rows on 10-08 ->
29.2k on 10-13), so the per-row refit crossed the 900 s deadline on the first two nights with a 29k-row history
and stays over it. Measured: 1,443 s at 29,154 rows (memo section 2); 16k rows took 579-659 s.

Both baseline_four_arm.py and ingame_scoreboard.py are scoreboard identity files pinned by the sealed PREREG
chain (FREEZE in force since commit B 10-07): no fit-path change is possible outside a chain step.

## 2. The change (config only, S779 precedent 9363066a7 and S785 85ffc2be4)

1. scripts/platformkit/execution/paper_night_budget.json: deadline_s.scoreboard "900" -> "3600". Nothing else in
   the budget moves (ceiling_bytes unchanged: the step peaked at 360-387 MB). Quadratic runway: 1,443 s x
   (N / 29,154)^2 reaches 3,600 s at about 46k rows, about four scored nights of growth at the 3-4k rows a scored
   night adds (the file did not grow while the step was killed: 10-13, 10-14 and 10-15 all hold 29,154 rows).
   Honesty (adversarial tier): the 10-08 / 10-09 points (579 / 659 s at 15.9k / 16.1k rows, other sport mixes,
   more free RAM) fit an exponent of about 1.3-1.5, not pure quadratic (which predicts 427 / 438 s; linear 785 /
   796 s), so the quadratic runway (about 46k rows) is the conservative bound; exponent 1.5 gives about 54k rows
   and linear about 73k.
2. docs/operations/paper_desk_config.json: timeouts_s.night 7200 -> 9900. The six step deadlines now sum to
   8,700 s (900 + 1,200 + 300 + 3,600 + 900 + 1,800); with the S755 admission wait (up to 600 s,
   paper_night_admission.py WAIT_TOTAL_S) and about 600 s of headroom the worst case stays under the tick's night
   subprocess timeout (paper_desk_tick.py: the validator requires at least 7,200). The installed task
   CourtVisionPaperDesk has ExecutionTimeLimit PT3H (docs/operations/install_paper_desk_task.ps1:93) counted from
   TASK start (captures, heartbeats and the schedule step run before the night), so the night timeout must stay
   clearly under 10,800 s or Task Scheduler stops the tick before its own timed_out record is written: 9,900 leaves
   900 s. Observed nights total about 2,700 s; the raise only removes the tail case where every step runs to its
   deadline. Side effect (adversarial tier): scripts/platformkit/ops/slo_status.py derives the SLI1 due time from
   timeouts_s.night, so a night counts as due at D+1 08:50Z instead of 08:05Z; no test pins the live value.
paper_night reads the budget at run time and the tick reads its config every run, so the next night (10-15 at
06:05Z 10-16) runs under both; no daemon restart, no capture touched.

Test pins (each the S779 shape: the new value normalised back before the byte or dict comparison):
test_c12 (test_registry_scorer_e_night_capacity.py), test_c9_base_hash_and_c12_e_artifact
(test_paper_night_deferral.py), the proposal context lines (test_s558_round4.py), LF_BUDGET_HASH
(test_s526_admission_need.py), the budget branch of test_frozen_module_bytes_and_inputs_tests
(tests/platformkit/ops/test_s485_baseline_contract.py lines 202-213: hidden today behind that test's
pre-existing fill_realism.py failure, which S819 clears -- emulated green on the branch), and CONFIG_SHA
(tests/platformkit/ops/test_s709_desk_root.py: re-pinned to the new config; the prior pin f4ab7466 already
failed on master since the 10-10 tennis-removal commit 0666dbc99, which did not re-pin it).

## 3. Acceptance

(a) The measured wall of the 10-13 scoreboard argv re-run from a code tree with the 10-13 / 10-14 shards and the
10-13 training file hard-linked (scratch output, nothing live written): 1,443.3 s (memo section 2); the deadline
exceeds it with the runway stated above.
(b) Each pin red before its update and green after; master's test_c12 copied beside the branch budget fails.
    Known gap: test_s558_round4 normalises 3600 back to 900, so it does not catch a plain revert to 900; the
    other three budget pins do.
(c) The files that read the live budget or the live tick config green one per process (section 5).
(d) First live check: nights/2026-10-15.json scoreboard RAN with a receipt docs/evidence/forward/scoreboard/
2026-10-15.json and the night's status no longer PARTIAL for that reason; the wall is informative (expected
about 1,400-1,800 s), not a pass condition; nothing else in the night record changes shape.

## 4. Non-goals / follow-up

- No fit-path change (sealed). The real fix is rowed as S825: `predict`'s train set depends only on the fold
  (first[gid].date()) and the 3-day embargo and `logistic` fits on train only, so one fit per (fold, arm)
  would be output-identical; but the O(N^2) train-list build inside walk_forward and `predict`'s own per-call
  filter remain after a fit cache, and the predictions for history rows are computed and discarded, so the gain
  must be MEASURED (the cProfile pass this row did not run). Identity change for the next chain step (seal day),
  never a night-side patch.
- No per-sport skip budget, no history truncation (the cumulative lookback is the sealed S766 policy).
- The 10-13 and 10-14 nights stay PARTIAL with no scoreboard unless S712's revision queue re-runs them; a
  by-hand rerun of a night step is not done by this lane (tick-owned).

## 5. Tests (one process per file)

tests/platformkit/execution/test_registry_scorer_e_night_capacity.py, test_paper_night_deferral.py,
test_paper_night_deferral_r1.py, test_paper_night_inputs.py, test_paper_night_qualification_isolation.py,
test_live_shadow_fit.py, test_s558_round4.py, test_schedule_revise_e2e.py, test_s526_admission_need.py,
test_paper_night_deadline.py, test_paper_night_deadline_1b.py, test_paper_night_deadline_1c.py;
tests/platformkit/ops/test_s485_baseline_contract.py (its fill_realism.py failure pre-exists on master),
test_night_ram_census.py, test_s709_desk_root.py, test_paper_desk_runtime.py, test_paper_desk_amendment.py,
test_paper_desk_issue_offday.py, test_paper_desk_legacy_nights.py, test_paper_desk_s520_night.py,
test_paper_desk_s520_schedule.py.

## 6. Tiers

Two Opus tiers (CONTRACT: VERIFIER_CONTRACT A/B/Q + this spec; ADVERSARIAL: probes and mutations); codex sol if
the 2,500 MB gate passes. Contract tier round 1: ACCEPT WITH CORRECTIONS (C1 fifth pin, C2 10-14 file, C3
quadratic cost, C4 runway, C5 night timeout) -- all applied in AMENDMENT 1. Adversarial tier round 1: ACCEPT WITH
CORRECTIONS (C1 a parametrize case swallowed by a comment, C2 the PT3H task limit -> night timeout 9,900; optional
C3 runway exponent, C4 slo_status due time, C5 the s558 pin gap) -- all applied in AMENDMENT 2.
