GAP G141 | sport basketball | worktree a2 | log cx_g141_corner_detector_recall
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This is G119 finally able to run. Read
docs/evidence/tracking/g140_corner_targets_on_g136_2026-09-02.md,
g119_paint_corner_detector_2026-09-02.md and g138_paint_role_assigner_2026-09-02.md first.
THE ROUTE THIS TESTS, and why it is the only one left. Eight rows retired the LINE route for
basketball court_feet, ending with G138: **0 of 84 claimed role assignments correct and only 1 of 84
roles independently available** from the stable groups. A human sees the paint geometry in 46.2 pct
of frames (G136) while the detector makes roles available in about 1.2 pct -- an absence of signal,
not a threshold. The corner route was never tested because it lacked ground truth: G119 refused as
circular (G111 recorded corner ROLES but no pixel targets) and G121 refused because G111's labels
were themselves wrong, which the G126 audit confirmed at 22/45 = 48.9 pct agreement.
GROUND TRUTH NOW EXISTS. G140 labelled **68 pixel targets across 17 G136-qualified frames**, and
measured its own precision first: a blind 15 pct re-label gave **median 10.97 px, p90 11.39 px**
displacement.
PRE-REGISTER THE TOLERANCE FROM THAT FLOOR, BEFORE MEASURING, and justify it in the memo:
  A detector cannot be shown more accurate than the labels scoring it. The p90 label displacement is
  11.39 px, so a match tolerance BELOW roughly 11 px would be measuring label noise rather than
  detector error. State the tolerance you choose, state that it is grounded in G140's measured
  floor, and do not change it after seeing results. For scale, 11.4 px is about 0.8 to 1.2 ft of
  court position depending on how much of the 94 ft court the frame spans -- report the conversion
  for the clips you use rather than assuming one.
DO THIS:
  (a) Implement the SIMPLEST direct corner proposal that could work, in scripts/platformkit or
      domains/basketball -- NOT in line_calibration.py and NOT under src/, kernel/, api/,
      scripts/team_system/ or intel/. A local corner response or a neighbourhood intersection search
      is the intent. Do not build anything learned for a feasibility test.
  (b) MEASURE corner-detection recall against G140's 68 targets, per corner ROLE, with Wilson 95 pct
      intervals, at the preregistered tolerance. Report the denominator exactly.
  (c) MEASURE PRECISION TOO: of the corners the detector proposes, what share land on a real target.
      A detector that blankets the frame with candidates would score well on recall alone, and the
      line route already produced one number (11.22 pct candidate precision) that looked survivable
      until precision was read beside it.
  (d) COMPARE LIKE FOR LIKE against the line route's availability. G138 measured 1 of 84 roles
      available. State your equivalent -- of the 68 targets, how many does the corner route make
      available -- so the two routes can be judged on the same quantity.
  (e) ONE SENTENCE: does a corner-first route make materially more of the four constraints available
      than the line route, and is it worth a production row.
BE HONEST ABOUT THE CEILING and write it in the memo: 17 frames and 68 targets is a small sample,
G136's 46.2 pct qualifying rate carries its own 66.7 pct label-agreement caveat, and a good recall
here is NOT a solved sport. It would mean the constraints are recoverable, which is the step before
a solve, and G135's external-validation requirement still stands after that.
DO NOT declare court_feet for any clip, change any threshold, the coordinate contract or the rung
ladder, or touch line_calibration.py.
ACCEPTANCE RULE:
  metric        = corner-detection recall per role against G140's 68 targets with Wilson 95 pct
                  intervals at the preregistered tolerance, AND proposal precision, AND the
                  available-constraint count comparable to G138's 1 of 84
  before        = corner route never measured; line route 1 of 84 roles available, 0 of 84 correct
  bar           = NO pass bar. Success is the tolerance preregistered from G140's floor, recall and
                  precision both measured, and the like-for-like comparison stated. A result no
                  better than the line route is a full success and would close basketball entirely,
                  which is worth knowing.
  n             = 68 targets across 17 frames; state the per-role denominators
  eye check     = REQUIRED. Render proposed corners against the targets on at least 5 frames and
                  look. A detector scoring well while landing on crowd texture or a logo is the
                  failure mode, and only the eye catches it beside the precision number.
  must not move = G140's targets and its measured displacement, the G136 census, line_calibration.py,
                  every detector and grouping parameter, every threshold, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g141_corner_detector_recall_2026-09-0X.md with the tolerance and its
justification stated FIRST, the recall and precision tables, the like-for-like comparison, the
renders, the ceiling caveat, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g141_corner_recall/ BEFORE reporting (A7).
CAUTION: another session commits into the main checkout concurrently. Work in your worktree and
commit with explicit pathspecs only.
TEST: exactly one new per-file test; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the track daemon is live and seven bridge
lane workers run under scripts/platformkit/bridge_keeper.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
