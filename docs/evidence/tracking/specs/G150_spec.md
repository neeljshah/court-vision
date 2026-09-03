GAP G150 | sport tennis | worktree a2 | log cx_g150_local_denominator_reach
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7 and Q8; self-check
section B before reporting. This is a MEASUREMENT. Move nothing.

PREMISE TO RE-MEASURE FIRST (Q8). The orchestrator measured on 2026-09-03 that 361 tracking tables
survive under local `data/tracking/` and that ZERO of them are jump-gate eligible. Re-measure that
count yourself before anything else and report the number you actually get. If it is different, say
so plainly -- a falsified premise is a VALID result and the row still finishes.

WHY THIS ROW EXISTS. G147 stopped at its own stop condition: the coverage-bar adjudication needs a
two-column current-versus-corrected comparison, and it could not be computed because no gate-eligible
table carried an auditable decoded-frame denominator. G147-CORR then established that the block is a
PRODUCER GAP, not a matter of waiting. The pod that held those tables has since died. So the question
this row answers is narrow and answerable entirely from local files: **of the tracking tables that
survive locally, how many carry an auditable decoded-frame denominator, and for those, what is the
current-versus-corrected coverage?**

MEASURE, DO NOT FIX:
  (a) Enumerate every local table under `data/tracking/*/tracking_data.csv`. Report the count and
      how you counted. The ELIGIBLE denominator, not the raw table count, is what every share below
      is taken over -- name it explicitly in the memo (see the eligible-denominator rule).
  (b) For each table, determine whether a decoded-frame denominator is RECOVERABLE: from a persisted
      decode manifest, from a ledger row, from a sibling artefact, or from a local video file that
      still exists. Classify every table into exactly one bucket and report the bucket counts.
  (c) For every table where it IS recoverable, compute both numbers side by side: coverage as the
      harness computes it today, and coverage against the decoded-frame denominator. Report the
      ratio. G147 reproduced a 2.5x-4.9x inflation on four tennis clips; state whether your tables
      agree, disagree, or cannot say.
  (d) If the recoverable count is ZERO, that is a FULL SUCCESS and the correct headline. Say it
      plainly and state what would have to be produced for the comparison to become computable. Do
      not manufacture a denominator by estimation, by frame-count proxy, or by re-decoding a video
      that is not the one the table came from.
  (e) Cross-check exactly 3 tables by hand against their raw CSV so the census is not trusting its
      own parser. Show the hand arithmetic.

DO NOT change the harness, the 0.90 coverage bar, any threshold, the coordinate contract, or any
verdict. Do not re-track anything. Do not touch the pod at all -- this row is LOCAL ONLY.

ACCEPTANCE RULE:
  metric        = local table count; per-bucket recoverability counts; for recoverable tables, the
                  current and corrected coverage pair and their ratio
  before        = 361 local tables claimed, 0 eligible claimed, recoverability entirely unmeasured
  bar           = NO pass bar. Success is the buckets measured and the premise re-checked. "Zero
                  tables carry a recoverable denominator" is a full success and closes the row.
  n             = every local table (CONSTRUCT, exhaustive -- state the enumeration is complete)
  eye check     = REQUIRED: the 3 hand cross-checks in (e), with their arithmetic shown
  must not move = tracking_harness.py, the 0.90 bar, every threshold, the coordinate contract, the
                  eligibility definition, and every existing verdict
EVIDENCE: docs/evidence/tracking/g150_local_denominator_reach_2026-09-03.md plus a per-table CSV under
docs/evidence/tracking/g150_denominator/. Commit BEFORE reporting (A7). Include a NOT VERIFIED list.
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: DO NOT TOUCH. Never kill anything anywhere.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
