GAP G114 | sport tennis | worktree a2 | log cx_g114_tennis_coordinate_declaration
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. A PRODUCER fix in the one sport where it is legitimate. Read
docs/evidence/tracking/g109_eligible_table_census_2026-09-02.md first, especially its Tennis control
section.
WHY THIS IS THE CHEAPEST REAL LEVER IN THE SYSTEM. G109 censused 196 pod tables and found only
**7 reach the jump gate**. First blockers: 131 image_px, 48 missing a coordinate declaration or
schema prerequisite, 7 empty, 2 insufficient, 1 unknown. The 48-bucket has a mechanical ceiling of
+46, but G109 is careful that this is an upper bound needing sport-specific production work, and
that soccer's 25 rows cannot be credited at all because G91 and G101 established soccer court_feet
is unreachable from this corpus.
TENNIS IS THE EXCEPTION AND IT IS SMALL AND CONCRETE. Tennis is the sole sport that reaches
court_feet (G47: 0/15 contract rejections). G109 reports **tennis has 16 tables: 7 eligible and 5
missing a coordinate declaration**. Those 5 have no reachability blocker -- tennis geometry supports
the solve. Repairing them would take the whole system's eligible population from 7 to 12, which is
the difference between "no statistic question can be settled" and a usable denominator. G107 refused
to choose a jump statistic precisely because 6 to 7 eligible tables is too few.
THE QUESTION: why do 5 tennis tables lack a coordinate declaration when 7 sibling tables have one,
and can the producer emit it for them?
  (a) IDENTIFY the 5 by name from the G109 census and confirm each one's blocker independently
      rather than trusting the bucket label. G100 found three "thin" jobs were header-only by
      opening them; do the same here.
  (b) DIAGNOSE the difference. Same sport, same adapter, some declare and some do not. Candidates:
      the calibration step failed or was skipped for those clips; they were produced by an older
      adapter revision before the declaration existed; the clip never reached a view where the
      solve is possible; or the declaration is written to a sidecar that is missing. Determine
      which, per table, from the artefacts -- do not generalise from one.
  (c) REPAIR only what is honestly repairable. If a table lacks the declaration because the solve
      genuinely failed on that footage, it must NOT be given a declaration -- that would be
      fabricating a coordinate space and it is exactly the kind of thing the rung ladder exists to
      prevent. Declaring image_px data to be court_feet would corrupt every number downstream. Say
      plainly which of the 5 are repairable and which are not, and why.
  (d) REPORT the eligible-table count before and after, measured, not projected.
DO NOT change any harness threshold, the coordinate contract, the rung ladder, or any bar. Do not
touch the 131 image_px tables. Do not re-track anything to force a declaration without saying so.
ACCEPTANCE RULE:
  metric        = jump-gate-eligible tennis tables before and after, measured on the pod census
  before        = tennis 16 tables, 7 eligible, 5 missing a coordinate declaration
  bar           = NO pass bar. Success is the 5 diagnosed individually with a per-table repairable
                  verdict and its reason, and the eligible count re-measured. "None are honestly
                  repairable" is a FULL success and it is far better than five fabricated
                  declarations.
  n             = all 5 tables, each opened and confirmed; state the eligible count you measured
                  both before and after
  eye check     = required for any table you judge unrepairable because the footage does not support
                  the solve -- look at a frame and say so. A solve failure asserted from a log is
                  not the same as one confirmed in the pixels.
  must not move = the coordinate contract, the rung ladder, every harness threshold, every verdict,
                  the 131 image_px tables, and the G109 census
EVIDENCE: docs/evidence/tracking/g114_tennis_coordinate_declaration_2026-09-0X.md with the 5 named,
the per-table diagnosis and repairable verdict, the before/after eligible count, any frames you
looked at, and a NOT VERIFIED list. Commit under docs/evidence/tracking/g114_tennis_declare/ BEFORE
reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you change code; run only that file. Never a full pytest.
POD: READ-ONLY for diagnosis. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
SHARED MODULE: if a fix reaches tracking_harness.py or tracking_schema.py take the token in
docs/evidence/SHARED_MODULE_TOKEN.md and push the release. Prefer changing only the tennis adapter.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
