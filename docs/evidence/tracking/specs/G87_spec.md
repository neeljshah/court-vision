GAP G87 | sport basketball | worktree a2 | log cx_g87_paint_gate_perspective
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. Cheap, decisive, and it either confirms a precise mechanism or
falsifies a confident one.
THE CLAIM TO TEST, derived from the code by the cross-sport analysis and with its arithmetic already
verified by the orchestrator: `domains/basketball/tracking/line_calibration.py:198` gates on
`parallel < 1.8 or orthogonal < 1.6`, where `_parallel_score(a,b)` is `|dir_a . dir_b|` and
`_orthogonal_score` is `1 - |dir_a . dir_b|`, both on IMAGE-SPACE directions. Those are affine
quantities that perspective destroys. The arithmetic:
  - parallel >= 1.8 demands each pair sit within **25.8 deg of image-parallel**
  - orthogonal >= 1.6 demands within **11.5 deg of image-perpendicular**
  - a true paint with a baseline-to-lane IMAGE angle of 70 deg scores orthogonal 1.32 -> REJECTED
  - at 60 deg it scores 1.00 -> REJECTED
  - a screen-aligned graphic or border scores the theoretical maximum 2.00 + 2.00 -> PASSES
So the gate is predicted to REJECT the true paint under ordinary broadcast perspective while
PREFERRING non-court structure. One threshold pair would then explain both G75 symptoms at once:
23 of 30 held-out frames emitting nothing, and every emitted quad following graphics and borders.
THE TEST -- on real geometry, not arithmetic:
  (a) On >= 12 frames the G76-AUDITED labelling calls PAINT_SOLVABLE, hand-mark the FOUR TRUE PAINT
      LINES (baseline, free-throw line, both lane sides) as image line segments. This is hand truth,
      independent of any detector.
  (b) Feed exactly those four true lines into `assign_paint_roles` and record whether each frame
      passes or is rejected, and at WHICH gate (parallel or orthogonal) and with what score.
  (c) Report the measured image-space baseline-to-lane angle per frame alongside the scores, so the
      reader can see the predicted relationship directly rather than taking it on trust.
  (d) If any frame passes, say so plainly -- a partial pass rate falsifies the strong form of the
      claim and is exactly as valuable as a confirmation.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = fraction of frames whose TRUE four paint lines are rejected by the gate, and the
                  gate that rejected them
  before        = predicted from arithmetic, never measured on real geometry
  bar           = THERE IS NO PASS BAR. Success is the measured pass/reject split with per-frame
                  angles and scores. Confirming the prediction and falsifying it are equally good
                  outcomes; what is not acceptable is repeating the arithmetic without the test.
  n             = >= 12 frames; state the per-clip counts and the seed
  eye check     = MANDATORY, and it IS the input here: the four true lines are hand-marked from the
                  picture. Commit the marked renders so a verifier can check your truth, not just
                  your arithmetic.
  must not move = line_calibration.py, every threshold, the coordinate contract, and the producer.
                  This row MEASURES an existing gate. It does not fix it.
IF THE PREDICTION CONFIRMS, state the implication precisely and stop there: the fix is a
perspective-invariant hypothesis test rather than a tuned threshold, and choosing one is a separate
adjudicated row. Do NOT retune 1.8 and 1.6 -- any image-space angle threshold has the same defect,
and a tuned one would simply move which perspectives fail.
CONTEXT: this is a SECOND and INDEPENDENT blocker alongside G84, which measured that all four paint
lines are present among the detector's candidates in 0 of 33 human-solvable frames. Both must move
before the paint route works, and knowing whether this one is real changes what G86 should build.
DURABILITY (A7): commit the hand-marked lines, the per-frame scores and the renders under
docs/evidence/tracking/g87_paint_gate/ BEFORE reporting.
FOOTAGE: basketball is POD-ONLY; the G68 contact sheets exist under
docs/evidence/tracking/g68_paint_census/contact_sheets/. Read-only frame work on the pod is fine.
EVIDENCE: docs/evidence/tracking/g87_paint_gate_perspective_2026-09-0X.md with the per-frame table
of angle, parallel score, orthogonal score and verdict, the marked renders, an explicit
confirm-or-falsify statement, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: read-only. No scp, no deploy, never kill anything -- another session has live processes there
and three tennis re-tracks of mine are running.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a2,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
