GAP G88 | sport all | worktree a5 | log cx_g88_jump_statistic_impl
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This IMPLEMENTS an adjudicated decision. Implement it; do not
re-open it and do not extend it.
THE ADJUDICATION (orchestrator, 2026-09-02, in the G82 register row): replace `jump_p95` with a
MODAL-STRIDE-ADJACENT `jump_max`, retaining every existing bar. Accepted because G82 measured the
full verdict impact as **0 PASS->FAIL and 0 FAIL->PASS** -- a pure sensitivity gain with no trade.
Read docs/evidence/tracking/g82_jump_statistic_limit_2026-09-02.md first.
WHAT G82 MEASURED, and why both halves of the change are needed:
  - On real basketball, **16 of 16 oversized steps sit ABOVE p95** -- every one invisible -- at a
    real prevalence of 0.0455 pct. The synthetic sweep found jump_p95 only trips at 6 pct
    prevalence, so reality is roughly 130x below the point where a p95 notices anything. A
    percentile excludes the tail it exists to catch, by construction.
  - **4,812 of 35,188** basketball row-diffs (13.7 pct) span MORE than the 3-frame stride. Those are
    not steps at all; `groupby.diff()` differences consecutive ROWS, not consecutive FRAMES, so a
    gap of 200 frames is currently differenced as though it were one step.
IMPLEMENT both halves:
  (a) Restrict differencing to MODAL-STRIDE-ADJACENT row pairs. State how you determine the modal
      stride per table and what happens when a table has no clear mode.
  (b) Use a MAX rather than a p95 over those pairs.
  (c) Retain every existing bar unchanged. This row changes the STATISTIC, not the threshold.
  (d) Keep the field naming honest: if the reported number is no longer a p95, it must not be called
      `jump_p95`. Decide whether to add a new field and deprecate the old, or rename with readers
      updated, and say which and why -- there are readers, so grep them (A5/B2).
THE GATING CONDITION: **RE-MEASURE the verdict impact on your implementation.** Do NOT inherit
G82's 0/0 -- that was measured on a proposal, not on this code. Report PASS->FAIL and FAIL->PASS
counts over >= 10 existing reports. If it is no longer 0/0, that is a REJECT: report it and hand it
back for adjudication rather than adjusting anything to make it fit.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = verdict impact (PASS->FAIL, FAIL->PASS) plus sensitivity on a constructed
                  teleport case
  before        = jump_p95 blind to 16 of 16 real oversized steps; 13.7 pct of diffs span a gap
  bar           = re-measured verdict impact of 0/0, AND the new statistic detects a constructed
                  40-ft teleport at a prevalence well below the 6 pct where p95 trips, AND no
                  existing bar moves
  n             = >= 10 existing reports replayed, plus constructed teleport cases at several
                  prevalences
  eye check     = n/a (a statistic change). Reproduction = before/after values on the same tables.
  must not move = the 8.0 ft bar and every other threshold, every verdict, and the coordinate
                  contract
NOTE: G83 is separately routing `sampling_interval_s`, after which a ft/s form becomes possible. Do
NOT wait for it and do NOT build the speed form here -- feet is the right unit today, and a speed
bar is a threshold change needing its own adjudication.
EVIDENCE: docs/evidence/tracking/g88_jump_statistic_impl_2026-09-0X.md with the re-measured verdict
impact, the sensitivity result, the naming decision and its reader survey, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: no deploy. The verifier lands code on the pod.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a5,
no push except the token. Report the sha.
SHARED MODULE: tracking_harness.py is under the token. Take it in
docs/evidence/SHARED_MODULE_TOKEN.md and PUSH THE RELEASE when you report.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
