# Codex spec template for tracking gaps
Copy this template into each codex spec artifact; fill in the placeholders and run through the ACCEPTANCE RULE validation before dispatching. Max 40 lines.

---

GAP <GID> | sport <sport> | worktree a<N> | log cx_<gid>_<slug>
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check
against every line of section B before you report.
PREMISE (step 0): <the one measurement that proves the gap is real today>. If
falsified, STOP, write the memo, commit, report FALSIFIED -- a valid result
that earns its own register row.
LIMIT (step 1): <the measurement that bounds what is achievable>. If the limit
is below the acceptance bar, STOP and report CLOSED AT LIMIT. Do not fix.
CHANGE (step 2): <the smallest change>. Additive only: new columns, new opt-in
modes, new files. Renaming or removing an existing field, column or status
value is an automatic reject -- if unavoidable, keep the old name as an alias
in the same commit and name every reader you checked.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = <name + exact denominator: decoded frames/rows/segments>
  before        = <measured today, with n>
  bar           = <the number "after" must beat; fixed now, never moved>
  n             = <>= 30>
  eye check     = <k renders EVENLY SPACED over the decision set, no head slice>
  must not move = <thresholds/files that must be byte-identical after>
NON-TAUTOLOGY: state which rows the metric covers and which are excluded. If
excluding the failing rows is what makes the number good, the metric is
circular -- say so and report REJECT yourself.
EVIDENCE: docs/evidence/tracking/<gid>_<slug>_2026-09-02.md -- before/after
table, n, denominator, render tally, and a "NOT VERIFIED" list.
TEST: exactly one new per-file test; run only that file.
POD: heavy compute only; own nohup setsid nice job, unique /tmp log, never
kill anything, no git on the pod, and NO scp of any module until the verifier
accepts. Report the files you would deploy; do not deploy them.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha.
NEVER PARK: poll your own jobs in a blocking loop; never end waiting.
