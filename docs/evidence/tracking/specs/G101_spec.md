GAP G101 | sport soccer | worktree a7 | log cx_g101_soccer_reachable_solve
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This row follows a CLOSED-AT-LIMIT measurement and asks the
only question that measurement leaves open. Read
docs/evidence/tracking/g91_soccer_landmarks_2026-09-02.md first.
WHAT G91 SETTLED. On 100 seeded frames (seed 9102026, 20 frames from each of 20 equal temporal
strata, across all five soccer pod clips, every frame reviewed by eye), the count of VISIBLE
canonical soccer landmarks is:
  >= 3 landmarks   34/100
  >= 4 landmarks    0/100
  >= 5 landmarks    0/100
`MIN_LANDMARKS = 5`, so the existing validated homography stack cannot run on a single frame in the
decision set. G91 correctly stopped rather than building a penalty-box detector that could not have
helped: the geometry is not on screen, so no detector improvement reaches five points.
Note the harder fact inside that result: even FOUR points never co-occur. A planar homography needs
four point correspondences, so soccer court_feet is unreachable from POINT landmarks in this
corpus, at any detector quality. That is a stronger statement than "MIN_LANDMARKS is too high" and
it must not be softened into one.
THE QUESTION: is there a reachable solve for soccer at all, and if so what is it? Answer it as a
measurement and a recommendation, not as an implementation.
  (a) LINES, NOT POINTS. A homography can be fitted from four or more LINE correspondences as well
      as from points, and lines are what a pitch actually shows: touchlines, the halfway line, the
      penalty-box front line, the goal line. G91 counted POINTS. Re-examine its committed 100
      frames and count how many named LINES are visible per frame, using the same frames and the
      same seed so the two censuses are commensurable. Do not draw a new sample.
  (b) Report the >= 4 line share and the >= 3 line share. If four named lines are commonly visible,
      a line-based solve is reachable and that is the recommendation. If they are not, say so.
  (c) THE DEGENERACY THAT WILL BITE, and it must be addressed explicitly: parallel lines give no
      independent constraint for a homography. Two touchlines and the halfway line are a mutually
      parallel or near-parallel family in pitch coordinates. So count not just how many lines are
      visible but how many INDEPENDENT DIRECTIONS they span. Four lines in two directions is not
      four constraints. A recommendation that ignores this would produce a solver that appears to
      converge and returns nonsense.
  (d) THE CENTRE CIRCLE is the one non-linear feature soccer reliably shows, and G91 found the
      3-landmark cases are largely centre-circle cases. A conic gives more constraint than a point.
      Say in one paragraph whether a circle-plus-lines formulation is worth a row, without building
      it.
  (e) GIVE ONE RECOMMENDATION: a named formulation worth attempting, or an honest statement that
      soccer court_feet is not reachable from this corpus and that the corpus is the thing to
      change (wider framing, different sources, tactical-camera footage rather than broadcast).
      The second is a completely acceptable answer and it would redirect real effort.
DO NOT build a solver, do not change MIN_LANDMARKS, do not change MAX_HELDOUT_ERROR_M, do not touch
keypoints.py or geometry.py, and do not declare a coordinate space for any soccer clip. If you find
yourself editing domains/soccer, you have left this row.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-frame count of visible named pitch LINES and of independent line DIRECTIONS,
                  over the same 100 G91 frames
  before        = point landmarks >= 4 in 0/100 frames; line visibility never counted
  bar           = there is NO pass bar. Success is the line census measured on the same frames, the
                  independent-direction count reported alongside it, the degeneracy addressed, and
                  one named recommendation. "Not reachable from this corpus" is a full success.
  n             = the same 100 G91 frames; reuse the committed manifest and say so
  eye check     = REQUIRED. Line visibility is an eye judgement. Reuse or regenerate the G91 renders
                  and commit what you looked at.
  must not move = the G91 sample, seed and manifest, MIN_LANDMARKS, MAX_HELDOUT_ERROR_M,
                  keypoints.py, geometry.py, every threshold, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g101_soccer_reachable_solve_2026-09-0X.md with the line census, the
independent-direction analysis, the degeneracy discussion, the recommendation, and a NOT VERIFIED
list. Commit under docs/evidence/tracking/g101_soccer_lines/ BEFORE reporting (A7).
CAUTION FROM TODAY: a lane writing evidence directly into the MAIN working tree dropped two ledger
rows that another session had appended. Work inside your worktree and commit there; do not write
into the main checkout.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the track daemon and seven footage bridge
lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a7,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
