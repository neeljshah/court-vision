GAP G158b | sport all | worktree a7 | log cx_g158b_other_359_availability
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A3, A7 and Q8; self-check
section B before reporting. Attempt 2 at the BLOCKED half of G158. Move nothing.

WHAT ALREADY LANDED, and must not be redone. G158 (landed at 88e7e6211) established the producer
question and **falsified the orchestrator's legacy hypothesis**: the 359 undeclared tables are not old
files predating the stamp. 358 of 359 (99.7214 pct) are basketball, and
`src/pipeline/unified_pipeline.py:_checkpoint_csv` is a live, separate, UNSTAMPED writer that imports
no provenance helper and is reached by `scripts/process_game.py`, `scripts/full_game_pipeline.py` and
the module CLI. `scripts/run_clip.py` wraps it and attempts a LATE `stamp_image_space_rows` only when
every provenance column is absent, inside a `try/except` that logs `stamp skipped`. **Accept all of
that. Do not re-derive it.**

WHY ATTEMPT 1 COULD NOT FINISH, and check this before anything else (Q8). The worktree's tracking
store was a STALE REAL DIRECTORY holding 1 table while the main repo held 423, so the lane read 0 of
359 and honestly reported the dates, header shapes, geometry columns and hand checks as unmeasured.
`scripts/platformkit/tracking/worktree_data_links.py` was fixed to replace an empty stub and warn
loudly about a non-empty one, and the junction was repaired. **Count the tables you can actually see
FIRST and say the number.** If it is not in the hundreds, stop and report that the provisioning is
still broken rather than measuring a stale store.

MEASURE, local only:
  (a) The 359 grouped by file modification date, by sport routing label, and by distinct header shape.
      How many distinct header shapes are there? Name each shape and its count. State the ELIGIBLE
      DENOMINATOR and take every share over it.
  (b) Date the unstamped writer against the tables. Quote from git history when `_checkpoint_csv`'s
      current field list was last changed and when `coordinate_provenance.py` entered the repo.
      Do the table dates cluster before or after those? Say whether the timeline is consistent with a
      single live unstamped writer, with a mix of live and legacy, or is undecidable.
  (c) THE QUESTION THAT MATTERS FOR THE REBUILD: how many of the 359 carry REAL GEOMETRY COLUMNS
      despite having no declaration -- that is, columns that would let a table be re-stamped without
      re-tracking -- and how many carry no geometry at all? Report both counts from the columns
      actually present. Be explicit that "re-stampable" is a statement about the file and NOT a
      licence to re-stamp: DO NOT modify a single table.
  (d) Cross-check against today's live production. The daemon routes wnba, basketball,
      ncaa_basketball and nba through `run_clip.py`. If any basketball table produced TODAY is
      available to you, report whether its late stamp succeeded or was skipped. If none is available
      locally, say so and do not reach for the pod.
  (e) Hand-verify 5 tables sampled EVENLY across the 359, never from the head (A3, B7). Show each
      header line and your classification.

DO NOT re-stamp, repair, delete or rewrite any table. DO NOT change `src/` (human-gated),
coordinate_provenance.py, run_clip.py, the census script, the eligibility definition, any threshold,
or any verdict.

ACCEPTANCE RULE:
  metric        = the 359 grouped by date, sport and header shape with counts; the git dating; the
                  re-stampable versus no-geometry split; the 5 hand checks
  before        = attempt 1 read 0 of 359 through a stale store; all of the above unmeasured
  bar           = NO pass bar. Success is the grouping measured against a store you have verified you
                  can see. "Still not visible" is a valid result if you say so instead of measuring a
                  stale directory.
  n             = all 359 (CONSTRUCT, exhaustive -- state that the enumeration is complete)
  eye check     = REQUIRED: the 5 evenly-sampled hand verifications, headers shown
  must not move = every tracking table, `src/`, coordinate_provenance.py, run_clip.py, the
                  eligibility definition, every threshold, and every verdict
EVIDENCE: docs/evidence/tracking/g158b_other_359_availability_2026-09-03.md with the grouping tables,
the git dates quoted, the re-stampable split, the 5 hand checks, and a NOT VERIFIED list. Raw grouping
under docs/evidence/tracking/g158b_availability/. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: DO NOT TOUCH -- LOCAL ONLY. Never kill anything.
COMMIT: explicit pathspec only, in a7, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
