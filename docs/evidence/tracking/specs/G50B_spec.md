GAP G50B | sport all | worktree a9 | log cx_g50b_null_degenerate_metrics
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including the NEW A7 clause;
self-check every line of section B before you report. This implements an ADJUDICATED decision.
Do not re-open the decision; implement it.
THE ADJUDICATION (orchestrator, 2026-09-02, recorded in the G50 register row): the harness
publishes coverage_pct = 1.0 on tables with almost no data -- tennis_09 at 4 rows over 2 distinct
frames, tennis_07 at 8 rows over 4 frames, and 10 of 184 tables have fewer than 30 frames. The
question asked was whether such a report should be WITHHELD rather than flagged. The ruling:
  - Do NOT withhold the report. Withholding destroys information.
  - Do NOT change `passed`. Moving it would flip historical verdicts on 10 tables, and moving a
    gate is a separate adjudication that has not been made.
  - DO emit the n-dependent metrics as NULL on NEWLY WRITTEN reports when insufficient_data is
    true, keeping the flag and every other field exactly as they are.
The reasoning, so you implement the intent and not just the letter: the failure mode is a person
quoting 1.0 from a two-frame table. A null cannot be misquoted that way; a flag sitting beside a
plausible-looking number can be, and was, ignored.
PREMISE (step 0, reproduce it): confirm that MIN_FRAMES_FOR_METRICS is 30 and that the
insufficient_data flag already lands in scripts/platformkit/tracking_harness.py and gates nothing.
Confirm the 10-of-184 count, or report what you actually measure and against which glob. NOTE, and
this matters: these reports live on the POD, not in the local worktree -- a previous lane declared
a premise falsified after searching locally and finding a small unrepresentative subset. Measured
on the pod 2026-09-02: 201 reports carry jump_p95. Read the pod (read-only) for any denominator.
CHANGE (step 1): decide and STATE which fields are n-dependent, then null exactly those when
insufficient_data is true. At minimum coverage_pct and the jump quantiles are n-dependent; a field
like row count is NOT, and must keep its value. List your classification in the memo field by
field, with a one-clause reason each. Do not null a field you cannot justify.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = whether a degenerate report can still publish a misleading metric value
  before        = a 2-frame table publishes coverage_pct = 1.0
  bar           = on a newly written report with n_frames < 30, every n-dependent field is null,
                  insufficient_data is true, every non-n-dependent field is unchanged, and `passed`
                  is byte-identical to what it was before this change
  n             = >= 4 constructed reports: n_frames just below 30, just above 30, exactly 30, and
                  a degenerate 2-frame case; PLUS a replay over >= 10 existing tables proving no
                  historical verdict flips
  eye check     = n/a (a schema change). Reproduction = a before/after report block in the memo.
  must not move = `passed`, every harness threshold, MIN_FRAMES_FOR_METRICS itself, every field
                  name, and every historical verdict. If ANY verdict flips, that is a REJECT and
                  you report it rather than adjusting the fixture.
NON-TAUTOLOGY: prove `passed` is independent of the new nulls by asserting it on a fixture where
the nulls appear, not by reading the code and asserting it in prose (B8).
BACKWARD COMPATIBILITY: grep every reader of these reports before you change the shape (A5/B2).
A reader that does arithmetic on coverage_pct will now meet a null. Report what each reader does
and whether it breaks. If a reader breaks, say so -- do NOT silently make it tolerate nulls as
part of this row.
EVIDENCE: docs/evidence/tracking/g50b_null_degenerate_metrics_2026-09-0X.md with the reproduced
premise, the field-by-field classification, the before/after report block, the reader survey, the
no-verdict-flip result, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: read-only for denominators. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a9,
no push. Report the sha.
SHARED MODULE: tracking_harness.py is under the token. Take it in docs/evidence/SHARED_MODULE_TOKEN.md
(edit that file alone, commit it alone, push -- the push is the lock) and PUSH the release too when
you report. A lane earlier today pushed its acquire and left the release unpushed, which looks to
everyone else like the token is still held.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
