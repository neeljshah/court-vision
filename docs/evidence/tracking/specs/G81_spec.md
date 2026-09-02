GAP G81 | sport all | worktree a3 | log cx_g81_null_coverage_readers
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A bug fix with a known reproduction.
THE DEFECT: the G50 remediation made `coverage_pct` nullable on degenerate reports, and two readers
call `float()` on it with no None check, so they raise TypeError on a report the harness now legally
emits. Named by the gate audit and reproduced there on a 5-frame table:
  - `bridge_infill.py:99`
  - `tracklet_merge.py:234-235`
This is contract B2 -- an unchecked reader after a schema change -- and it is a direct consequence of
an orchestrator ruling that ordered the nulling. The G50B spec DID require a reader survey and the
lane's survey missed these two, so the instruction was right and the execution incomplete. That is
worth stating in the memo, because the lesson is about how a reader survey should be done, not about
whether to do one.
FIRST, REPRODUCE both TypeErrors on a degenerate report and paste the tracebacks. Do not fix what
you have not reproduced.
FIX: make both readers handle a null coverage explicitly.
  (a) Do NOT revert the nulling. It is correct -- a plausible-looking number on a 2-frame table is
      what gets misquoted, and an explicit null cannot be.
  (b) Do NOT silently substitute 0.0 or 1.0 for a null. A null means "not measurable", and coercing
      it to a number reintroduces exactly the misreading the nulling prevents. Decide and STATE what
      each reader should do with an unmeasurable coverage -- skip the row, propagate the null, or
      refuse -- and justify each choice in one clause.
  (c) A degenerate report now also carries `verdict=INSUFFICIENT_DATA` (G80). Say whether each
      reader should key off that verdict rather than off the null, which may be the cleaner test.
COMPLETE THE SURVEY THE FIRST ONE MISSED: grep for EVERY consumer of the nulled fields, which are
coverage_pct, det_per_frame, median_track_len, ball_valid_pct, ball_in_bounds_pct, jump_p95,
oob_pct, zero_step_share, median_step_distance, distinct_position_ratio, stationary_track_share,
liveness_verdict and jump_p95_ft_per_s. Report the full consumer list with a verdict per consumer:
safe, or needs the same fix. Two were found by an audit rather than by the survey, so assume the
list is longer than you expect until you have looked.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = number of readers that raise on a degenerate report
  before        = at least 2, reproduced (bridge_infill.py:99, tracklet_merge.py:234-235)
  bar           = 0 raising readers, AND a complete enumerated consumer list with a per-consumer
                  verdict, AND no change to behaviour on a report with adequate data
  n             = every consumer of the thirteen nulled fields; state the count you found
  eye check     = n/a (a reader-contract fix). Reproduction = both tracebacks before, and the same
                  inputs passing after.
  must not move = the nulling itself, every threshold, every verdict, and every value on an
                  adequate-data report
EVIDENCE: docs/evidence/tracking/g81_null_coverage_readers_2026-09-0X.md with both reproduced
tracebacks, the per-reader decision and its justification, the complete consumer survey, and a
NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: no deploy. The verifier lands code on the pod.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a3,
no push. Report the sha.
SHARED MODULE: if a fix reaches tracking_harness.py take the token and PUSH the release. Prefer to
change only the READERS, which is where the defect is.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
