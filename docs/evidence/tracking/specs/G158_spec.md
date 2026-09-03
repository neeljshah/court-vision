GAP G158 | sport all | worktree a7 | log cx_g158_the_other_359
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7 and Q8; self-check
section B before reporting. This is a LOCAL MEASUREMENT that resolves an open tension. Move nothing.

THE TENSION, and it is a real one that two landed rows created between them.

G154 censused all 361 surviving local tracking tables and found the first blocker for **359 of them
(99.4460 pct of the eligible denominator) is "other"** -- which in G109's and G142's vocabulary means
a missing coordinate declaration. Exactly 1 reaches the gate and 1 is a coordinate-contract rejection.

G152 traced the declaration path at HEAD and found the `court_feet` stamp is applied
**UNCONDITIONALLY**: three conditions, none geometric, and `_stamp()` populates every provenance
column even in its `if result.empty` branch (`scripts/platformkit/coordinate_provenance.py:32-48`).

Those two statements cannot both describe the same producer. If the stamp is unconditional, a table
written by this code CANNOT lack a declaration. So the 359 either predate the stamp, or came from a
different writer, or the census is classifying something other than what it thinks.

THE ORCHESTRATOR'S HYPOTHESIS, offered so you can falsify it rather than confirm it: the 359 are
LEGACY tables written before coordinate provenance stamping existed. **Do not assume this. Test it.**
A hypothesis that survives an honest attempt to kill it is worth something; one that is merely
restated is worth nothing.

DO THIS:
  (a) Take the 359 "other" tables. Report their date range, their column sets (how many distinct
      header shapes are there?), and which sports they belong to. Group them and give counts. State
      the ELIGIBLE DENOMINATOR for every share.
  (b) Date the stamping code. When did `coordinate_provenance.py` and the `stamp_court_space_rows`
      call in the adapter enter the repository? Use git history, quote the commits. Compare that date
      against the tables' dates. Say whether the timeline supports the hypothesis, contradicts it, or
      cannot decide.
  (c) Look for a SECOND writer. Grep every path that writes a `tracking_data.csv` and say which of
      them stamp provenance and which do not. `scripts/run_clip.py` is a different producer from
      `scripts/platformkit/adapter_run.py` -- establish what each one writes. If an unstamped writer
      is still live today, that is a much more important finding than the legacy explanation and it
      changes what a re-track will yield.
  (d) Answer the question that actually matters for the rebuild: **are any of the 359 cheaply
      recoverable?** A table that has real geometry columns but no declaration might be re-stampable
      without re-tracking. A table with no geometry at all is not. Report how many fall into each
      case, from the columns actually present, and be clear that "re-stampable" is a statement about
      the file, not a licence to re-stamp anything. DO NOT modify a single table.
  (e) Hand-verify 5 tables, sampled EVENLY across the 359 rather than from the head (A3, B7). Show
      each one's header line and your classification of it.

DO NOT re-stamp, repair, delete or rewrite any table. DO NOT change coordinate_provenance.py, the
adapters, the census script, the eligibility definition, any threshold, or any verdict.

ACCEPTANCE RULE:
  metric        = the 359 grouped by date, sport and header shape; the stamping code's entry date
                  from git; the writer inventory with stamped/unstamped marked; the recoverable count
  before        = 359 tables classified only as "other"; the tension with G152 unresolved
  bar           = NO pass bar. Success is the tension resolved in one direction with evidence, or
                  named unresolved with the specific thing that would resolve it. Falsifying the
                  orchestrator's hypothesis is a BETTER result than confirming it.
  n             = all 359 (CONSTRUCT, exhaustive -- state that the enumeration is complete)
  eye check     = REQUIRED: the 5 evenly-sampled hand verifications in (e), headers shown
  must not move = every tracking table, coordinate_provenance.py, every adapter, the eligibility
                  definition, every threshold, and every verdict
EVIDENCE: docs/evidence/tracking/g158_the_other_359_2026-09-03.md with the grouping tables, the git
dates quoted, the writer inventory, the recoverable count, the 5 hand checks, and a NOT VERIFIED
list. Commit under docs/evidence/tracking/g158_other/ BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: DO NOT TOUCH -- LOCAL ONLY. Never kill anything.
COMMIT: explicit pathspec only, in a7, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
