GAP G45 | sport tennis | worktree a4 | log cx_g45_ball_projection_guard
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report.
PREMISE (step 0, reproduce it): `ball_rows` projects a detected pixel through the GROUND-PLANE
homography with no plane check and no bound. So an off-plane pixel maps toward infinity, and a
pixel BEYOND THE VANISHING LINE produces a SIGN FLIP. Measured: tennis_02 through tennis_05 each
carry 34-70 rows below **-1,000 ft**, with individual values reaching 106,853 ft and transitions of
126,001 and 760,419 ft, against a court length of 78 ft. Clips whose vanishing row is OFF-SCREEN
(-240, -109) reach only 185 and 201 ft, which is the control that makes the mechanism concrete.
Reproduce the per-clip counts of rows below -1,000 ft and the vanishing-row positions from
g39_ball_projection_diagnosis_2026-09-02.md before changing anything.
THE HONEST FRAMING, and do not lose it: a tennis ball is genuinely OFF the ground plane most of the
time. Projecting it as if it were on the floor is wrong even when the detection IS a ball. So this
row does NOT make ball court-coordinates correct. It makes them stop being absurd, and it makes the
absurdity visible instead of silent. Say that plainly in the memo; do not let this be read as
"ball projection fixed".
RELATIONSHIP TO G44, state it at the top: G39 established the tennis ball detections are largely
NOT BALLS (12 of 12 rendered candidates contained no ball). G65 is producing the label set to
measure that properly. This row is therefore about the PROJECTION being unsound independently of
whether the input is a ball. Both must hold before any ball-derived quantity is trusted.
CHANGE (step 1): add a guard, not a model. The guard must:
  (a) Reject or flag a pixel that lies beyond the vanishing line of the current homography, because
      its projection is not merely inaccurate but sign-flipped. Compute the vanishing line from the
      homography itself -- do NOT hard-code a per-clip row, which would be a tautology (B7).
  (b) Bound the output to a stated physically-possible envelope and record WHY a row was rejected,
      never silently drop it. A silently dropped row is how G25 lost its containment evidence.
  (c) Be ADDITIVE with respect to the harness: `passed`, every threshold and every existing field
      keep their exact meaning. G43 already adjudicated that ball_in_bounds_pct does NOT gate, and
      that stands.
  (d) Preserve the coordinate contract: rows still declare their coordinate space, and a rejected
      row must not silently change rung.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = count and fraction of ball rows outside a physically-possible envelope, per clip
  before        = 34-70 rows per clip below -1,000 ft on tennis_02-05; max 106,853 ft
  bar           = zero rows below -1,000 ft and zero above a stated upper bound on the same clips,
                  with every rejection carrying a reason, AND no change to any player row, any
                  verdict, or any threshold. Report the row count before and after: a large drop is
                  expected and is the point, but you must state it, because a drop in rows can be a
                  fix or a regression and only the reason column distinguishes them.
  n             = all four clips, every ball row; state counts
  eye check     = MANDATORY on >= 8 frames whose ball row is newly rejected. Render and LOOK: is the
                  detection beyond the vanishing line, off-plane, or simply not a ball? Say which.
                  If most are "not a ball", that is a G44/G65 finding and you should report it.
  must not move = every harness threshold, `passed`, the G43 adjudication, player projection, the
                  solver, and the camera lock
NON-TAUTOLOGY: do not measure success as "no rows outside the envelope" when the guard's own rule
IS the envelope -- that is circular and automatic (B1). Report the underlying distribution of
projected values before and after, so a reader sees what was removed rather than only that a
constraint now holds.
DURABILITY (A7): commit the before/after per-clip distributions and the renders under
docs/evidence/tracking/g45_renders/ BEFORE reporting.
FOOTAGE: local worktree links data/footage_corpus; the full corpus is on the pod and listed in
docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md. Read-only frame work on the pod is fine.
EVIDENCE: docs/evidence/tracking/g45_ball_projection_guard_2026-09-0X.md with the reproduced
premise, the guard's rule stated in one sentence, before/after distributions, the renders, the
honest framing above, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: no deploy, no scp, no daemon restart, never kill anything. The verifier lands code on the pod.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a4,
no push. Report the sha.
SHARED MODULE: none expected. If you find yourself editing tracking_harness.py, STOP.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
