GAP G152b | sport tennis | worktree a6 | log cx_g152b_declaration_rates
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7 and Q8; self-check
section B before reporting. This is attempt 2 at the MEASUREMENT half of G152. Move nothing.

WHAT ALREADY LANDED, and what you must NOT redo. G152 attempt 1 (landed at de378837c) traced the
declaration path exhaustively and found exactly three conditions, none of them geometric: the video
opens (`domains/tennis/tracking/adapter.py:204-206`), `process_video` reaches its post-loop return
(`adapter.py:257-260`), and the sport key is `tennis` (`scripts/platformkit/coordinate_provenance.py:57-68`,
tennis mapped to COURT_FEET at 20-25). `_stamp()` populates every provenance column even in its
`if result.empty` branch. **Read that memo, accept the trace, and do not re-derive it.**

WHY ATTEMPT 1 COULD NOT FINISH. Its four clip metrics came back "not measurable" because
`data/videos/reference/` was absent from the worktree -- a junction that
`scripts/platformkit/tracking/worktree_data_links.py` did not provision, fixed at 8eccc4415. The
clips were in the main repo the whole time. **Verify the reference-clip directory is visible in this
worktree before you conclude anything about availability** (Q8: re-measure the premise first). If it
is still absent, say so and stop -- do not substitute a different clip and do not synthesise frames.

MEASURE, on the local reference tennis clip:
  (a) The decoded-frame count of the clip. State how you obtained it.
  (b) Run the adapter on it. Report rows emitted, distinct frames, and the value of
      `coordinate_space` and `calibration` across the rows.
  (c) The declaration rate over ALL decoded frames, and separately over RALLY frames only. G34
      measured tennis rally share at 41.7 pct (125/300, Wilson [0.362, 0.473]) on a DIFFERENT clip --
      do not import that number as this clip's rally share; classify this clip's own frames and say
      how you classified them. If you cannot classify rally view on this clip, report the all-frames
      rate and say the rally rate is unmeasured rather than guessing.
  (d) THE QUESTION THE TRACE OPENED, and the reason this attempt matters more than attempt 1. If the
      stamp is unconditional, then a table can declare `court_feet` while carrying NO recovered
      geometry. So report, separately from the declaration rate, the share of rows whose
      `calibration_provenance` is `solved` and whose `raw_projected_x_ft`/`raw_projected_y_ft` are
      populated. That is the honest geometry rate, and it is NOT the same quantity as the
      declaration rate. Say plainly whether the two differ on this clip and by how much.
  (e) G142 reported 8 tables declaring `court_feet` and 5 declaring nothing. If the stamp is
      unconditional at HEAD, those 5 cannot have come from this path. Look for the explanation in the
      code or in the committed G142 census and state it, or state honestly that you could not resolve
      it. "Unresolved, and here is what would resolve it" is a full success.

DO NOT change the adapter, the solver, the harness, coordinate_provenance.py, the coordinate
contract, any threshold, or any verdict. Do not relax a condition. Do not write a durable tracking
table into the shared store -- write under a scratch game id you name in the memo.

ACCEPTANCE RULE:
  metric        = decoded-frame count; rows and distinct frames emitted; declaration rate over all
                  decoded frames and over rally frames; the SEPARATE solved-geometry row share
  before        = all four unmeasured; the declaration/geometry distinction unquantified
  bar           = NO pass bar. Success is the rates measured on a real clip and the declaration rate
                  reported separately from the geometry rate.
  n             = >= 1 local reference tennis clip, with its decoded frame count stated (CONSTRUCT)
  eye check     = REQUIRED on 5 frames. Pick frames where a row was emitted but
                  `calibration_provenance` is not `solved`, if any exist; otherwise 5 frames where no
                  row was emitted. Render and commit them, and say what the eye sees in each.
  must not move = the tennis adapter, the solver, coordinate_provenance.py, tracking_harness.py, the
                  coordinate contract, every threshold, and every verdict
EVIDENCE: docs/evidence/tracking/g152b_declaration_rates_2026-09-03.md with the rate table, the
geometry-versus-declaration comparison, the five renders under
docs/evidence/tracking/g152b_rates/, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: DO NOT TOUCH -- LOCAL ONLY. A daemon is running there and must not be raced. Never kill anything.
COMMIT: explicit pathspec only, in a6, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
