GAP G135 | sport basketball | worktree a3 | log cx_g135_end_to_end_solve
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This is the END-TO-END test the whole basketball chain has been building toward.
Read docs/evidence/tracking/g134_grouping_stability_2026-09-02.md first.
THE CHAIN, and why this row is now worth running. Six preregistered rows, four of them REJECTS:
  - G115 baseline recall 25/68 = 36.76 pct (reproduced twice; pipeline deterministic).
  - G120 fragment merge 24/68 REJECT. G123 CLAHE 23/68 REJECT, recovering 0 of 17 targets.
  - G129 traced the losses and found both were REPLACEMENTS, not additions.
  - G132 union 28/68, REJECT at 24/25 baseline survival -- not additive.
  - G134 measured grouping directly: of 25 baseline-matched groups, 14 survived and 11 were
    ABSORBED, including the exact line G132 lost. With stable grouping plus the union, recall is
    **30/68 = 44.12 pct at 12.59 pct paired precision and 25/25 survival**. ACCEPT.
Implied all-four-line co-occurrence rises from 1.83 pct to **3.79 pct**, taking expected all-four
frames in 33 from 0.60 to 1.25. So for the first time a solvable frame is plausible rather than
arithmetically hopeless.
THE QUESTION, and it is the only one that matters now: on a frame where all four paint lines ARE
detected, does a homography actually solve, and is it CORRECT?
  (a) FIND the frames. Under G134's stable grouping plus union, identify every frame in the 30
      frozen G84 frames where all four paint roles are matched. State how many there are. If it is
      zero, report that plainly and stop -- 3.79 pct over 33 frames predicts about one, so zero is
      entirely possible and is a legitimate outcome that says the sample is too small rather than
      that the method failed.
  (b) SOLVE on each such frame, using the EXISTING correspondence machinery rather than a new
      solver. domains/basketball/tracking/line_calibration.py already fits an image-to-court
      homography from declared line correspondences; use it read-only as a library. Do NOT modify
      it.
  (c) VALIDATE EXTERNALLY, and this is the part that decides the row. A reprojection residual over
      the same lines used to solve is SELF-FIT and proves nothing (contract B8). Measure a KNOWN
      REAL-WORLD DISTANCE that was NOT used in the solve and report its error in FEET -- the
      three-point arc radius, the centre-circle radius, the free-throw-line-to-baseline distance of
      19 ft, or the lane width of 16 ft, whichever is visible and was not a solve input. State
      which quantity you used and why it is independent.
  (d) STATE THE HONEST CAVEAT about court dimensions. NCAA and WNBA courts differ from each other in
      three-point distance, so name the court standard you assumed per clip and say what error that
      assumption alone could contribute. An absolute error smaller than that assumption is not
      distinguishable from it and must not be claimed as accuracy.
  (e) DO NOT declare court_feet for any clip, do not promote any table, do not write a coordinate
      space, and do not change the rung ladder. A single validated solve on one frame is NOT a
      calibrated clip; it is evidence that calibration is reachable. Say so explicitly in the memo
      so nobody downstream over-reads it.
WHAT A GOOD OUTCOME LOOKS LIKE, in either direction: a solve with a held-out error of a few feet
would be the first evidence in this repo that basketball court_feet is achievable end to end. A
solve that converges but is wildly wrong, or one that does not converge, is equally valuable and
would say the four-line requirement is necessary but not sufficient. Both are full successes.
Reporting a small residual on the solve lines themselves and calling it validation is the one
failure mode.
ACCEPTANCE RULE:
  metric        = number of all-four-line frames under G134 grouping; and per frame, the held-out
                  real-world distance error in feet
  before        = no basketball frame has ever been solved; co-occurrence 3.79 pct implies about one
                  such frame in the 33-frame sample
  bar           = NO pass bar on the error. Success is the frame count reported, and for each frame
                  either a solve with an EXTERNAL error or an honest statement that it did not
                  converge. Zero qualifying frames is a full success.
  n             = the 30 frozen G84 frames; state the qualifying count exactly
  eye check     = REQUIRED. Render the solved court model reprojected onto the frame and look at it.
                  A homography with a small numeric error that visibly lies across the wrong lines
                  is the failure mode here, and only the eye catches it. Commit the renders.
  must not move = line_calibration.py, the frozen protocol at 98b7d6974, the G84 sample and seed,
                  the G115 labels, every detector and grouping parameter, every harness threshold,
                  the coordinate contract, and the rung ladder
EVIDENCE: docs/evidence/tracking/g135_end_to_end_solve_2026-09-0X.md with the qualifying frame count
first, the external validation quantity and why it is independent, the per-frame error in feet, the
court-standard caveat, the reprojection renders, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g135_solve/ BEFORE reporting (A7).
CAUTION: another session commits into the main checkout concurrently. Work in your worktree, commit
with explicit pathspecs only.
TEST: exactly one new per-file test; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a3, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
