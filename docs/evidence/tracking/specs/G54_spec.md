GAP G54 | sport all | worktree a7 | log cx_g54_evidence_durability
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. Cheap, process-level, and it has already cost two lanes a full run.
PREMISE (step 0, reproduce it): evidence that lives ONLY under /tmp on the pod is destroyed by a
pod reallocation, and it blocked two lanes in one session. G25b could not reproduce the G25
containment premise because /tmp/t3b_reemit was gone and the replacement tables lacked
frame_width/frame_height. The G26/G38 oob linkage could not be tested because the tennis tables
carrying oob had been overwritten. The state record warned that /tmp does not survive a stop, but
nothing ENFORCES it. Confirm both cases from RESULTS_LEDGER.md (2026-09-02) and
TRACKING_PROGRAM_STATE_2026-09-02 section 7 before proceeding.
LIMIT (step 1): every lane spec already says heavy compute writes to /tmp, and NOTHING says the
artifact a later verifier will need must be copied out. So the guidance is individually correct
and collectively lossy: each lane obeys it and the evidence still disappears. No amount of care
inside a single lane fixes a rule that is missing from the template.
CHANGE (step 2), all cheap, all process-level. Three edits:
  (a) docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md gains a REQUIRED line: any artifact a verifier
      must reproduce a number FROM is copied under docs/evidence/ before the lane reports. Name the
      cheap form (a summary json and the sampled rows), and say explicitly that a directory of
      renders may stay local while the numbers behind them must not.
  (b) VERIFIER_CONTRACT.md gains a check that the evidence paths a memo NAMES still EXIST at
      verification time, and that a missing path is a NOT VALIDATED verdict rather than a silent
      pass. Add it in the style of the existing section A duties and give it the next free number;
      do not renumber anything that exists.
  (c) Record the second, separate lesson explicitly: a table written for one purpose may be MISSING
      COLUMNS a later lane needs (frame_width/frame_height here), so a lane that re-emits tables
      preserves the FULL column set rather than the subset it happens to use.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = whether the two historical failures would have been PREVENTED by the new rules
  before        = 2 lanes blocked in one session by destroyed or column-stripped artifacts
  bar           = walk BOTH historical cases against your new text and show, quoting the specific
                  clause, that each would have been caught. A rule that does not catch the case
                  that motivated it is not a fix. If a clause does not catch its case, rewrite the
                  clause, do not reinterpret the case.
  n             = the 2 known cases, plus a scan of the memos landed since 2026-09-01 reporting how
                  many name at least one evidence path under /tmp (state the denominator)
  eye check     = n/a (a documentation change). Reproduction = the two walked cases in the memo.
  must not move = every harness threshold, every existing contract clause number, and the meaning
                  of the existing verdicts. You are APPENDING rules, not restating old ones.
SCOPE DISCIPLINE: do NOT write a sweeper that copies /tmp outputs automatically in this row. That
is a real idea and it is a DIFFERENT row -- name it in the memo and let the orchestrator allocate
an id. Lanes never invent gap ids.
EVIDENCE: docs/evidence/tracking/g54_evidence_durability_2026-09-0X.md with both reproduced cases,
the exact text added to each of the two documents, the two walked-through preventions, the /tmp
path scan with its denominator, and a NOT VERIFIED list.
TEST: no code expected. If you add any, exactly one per-file test; run only that file.
POD: read-only if at all. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a7,
no push. Report the sha.
SHARED MODULE: none. The contract and the template are tracked documents, not modules.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
