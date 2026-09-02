GAP G119 | sport basketball | worktree a7 | log cx_g119_paint_corner_detector
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This row tests an UNTRIED ROUTE on the one sport where calibration is reachable.
Read docs/evidence/tracking/g111_basketball_reachability_2026-09-02.md, g84_candidate_line_quality
_2026-09-02.md and g87_paint_gate_perspective_2026-09-02.md first.
WHY BASKETBALL AND WHY NOW. Five reachability censuses now exist and basketball is the outlier in
the good direction: **court_feet is geometrically reachable in 147 of 220 seeded frames = 66.8 pct**,
through four visible PAINT-CORNER POINTS. Soccer is 0/100, football never exposes a third
independent direction in 60 frames, baseball is 1/120. So for soccer and football "improve the
detector" is not a lever that exists -- the geometry is not on screen. For basketball it IS on
screen in two thirds of frames, and what fails is finding it:
  - G84: candidate precision 11.22 pct over 1,764 audited candidates, and all four paint lines
    co-present in **0 of 33 frames**.
  - G87: the parallel/orthogonal gate is NOT the culprit -- 11 of 12 true paint lines PASS it.
  - G115 is measuring the missing recall half right now.
THE UNTRIED ROUTE, and it is the point of this row. G111 reaches its four constraints through
CORNERS. The existing stack detects LINE SEGMENTS with `detect_lsd_segments`, groups them with
`candidate_line_group_details`, gates them, and only then intersects them into corners. Every stage
of that chain can lose a corner: a line broken into fragments, a line merged with its neighbour, a
line too short to survive, a line failing the gate. A corner is a LOCAL feature and can be found
directly, without ever recovering the full line. That has never been tried here.
DO THIS, AS A FEASIBILITY MEASUREMENT, NOT A PRODUCTION CHANGE:
  (a) REUSE the G111 sample and its committed labels -- same seed, same 220 frames, and the
      per-frame record of which paint corners are visible. That label set is your ground truth and
      it already exists; do not draw a new sample and do not relabel.
  (b) Implement the SIMPLEST corner proposal that could work, in scripts/platformkit or
      domains/basketball, NOT in the human-gated trees. Do not modify line_calibration.py. A local
      corner response, or an intersection search restricted to a neighbourhood, is the kind of thing
      meant here -- resist building a learned model for a feasibility test.
  (c) MEASURE CORNER-DETECTION RECALL against the G111 visible-corner labels, per corner role, with
      Wilson 95 pct intervals. State the localisation tolerance in pixels BEFORE measuring and
      justify it in one clause; choosing it after seeing the errors is B8 self-fit.
  (d) COMPARE, LIKE FOR LIKE, against what the line route achieves on the SAME frames. If G115 has
      landed its line-recall number by the time you run, cite it; if not, say the comparison is
      pending and report your number alone. Do not restate a line-route number you did not measure.
  (e) ONE SENTENCE: does a corner-first route find materially more of the four constraints than the
      line route, and is it worth a production row.
DO NOT wire this into any producer, do not declare court_feet for any clip, do not change any
threshold, the coordinate contract or the rung ladder, and do not touch line_calibration.py or
anything under src/, kernel/, api/, scripts/team_system/ or intel/.
BE HONEST ABOUT THE CEILING: 66.8 pct is per-frame GEOMETRIC VISIBILITY, not a solved homography. A
perfect corner detector would still only reach the constraint count on those frames, and a solve
must additionally be validated against a held-out real-world distance the way G91 required. Do not
let a good recall number get reported as a solved sport.
ACCEPTANCE RULE:
  metric        = corner-detection recall against the G111 visible-corner labels, per role, with
                  Wilson 95 pct intervals, at a preregistered pixel tolerance
  before        = corner-first route never attempted; line route yields 11.22 pct candidate
                  precision and four lines co-present in 0/33 frames
  bar           = NO pass bar. Success is the tolerance preregistered, recall measured on the reused
                  G111 frames, and the one-sentence verdict. "A corner detector is no better" is a
                  full success and it would send the effort back to the line route or to acquisition.
  n             = the G111 frames with visible corners; state that denominator exactly
  eye check     = REQUIRED. Render detected corners on a sample of frames and look at them. A corner
                  detector that scores well while landing on crowd texture or a logo is the obvious
                  failure mode and only the eye catches it. Commit the renders.
  must not move = the G111 sample, seed and labels, line_calibration.py, every detector parameter in
                  the line route, every harness threshold, the coordinate contract, and the rung
                  ladder
EVIDENCE: docs/evidence/tracking/g119_paint_corner_detector_2026-09-0X.md with the preregistered
tolerance stated first, the recall table by corner role, the comparison or its pending status, the
renders, the ceiling caveat, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g119_corners/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: READ-ONLY, pull clips only. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a7, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
