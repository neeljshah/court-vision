GAP G91 | sport soccer | worktree a7 | log cx_g91_soccer_landmarks
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This is the CALIBRATION lever, the single thing standing
between soccer and a court_feet rung. Read docs/evidence/tracking/CALIBRATION_STRATEGY_2026-09-02.md
section 1.1 first.
THE ARITHMETIC BLOCKER, verified by the orchestrator in the code, not inferred:
  - domains/soccer/tracking/keypoints.py:59-77 `detect()` returns exactly ONE key: `center_circle`.
  - domains/soccer/tracking/geometry.py:14 `MIN_LANDMARKS = 5`, enforced at geometry.py:163.
  1 < 5, on every frame, forever. So `_validated_homography` can NEVER return a homography for
  soccer, and every soccer clip is pinned at image_px BY CONSTRUCTION rather than by image quality.
  That is why 15 of 25 soccer pod reports are contract-only rejections (G47).
  The whole downstream stack -- solve_homography, leave-one-out validation at MAX_HELDOUT_ERROR_M
  = 2.0 m, the temporal calibrator with its 9-update warmup -- is already BUILT and unreachable.
  This row supplies the missing input, not a new stack. Do not build a second solver.
STEP 1, MEASURE BEFORE YOU BUILD (this half is worth landing even if step 2 fails): on a seeded
sample of >= 100 frames drawn across ALL five soccer pod clips, hand-label how many of the
`CANONICAL_LANDMARKS["soccer"]` points are actually VISIBLE in the frame. Report the distribution:
what share of frames have >= 5 visible, >= 4, >= 3. If broadcast soccer framing simply does not put
five canonical landmarks on screen very often, then MIN_LANDMARKS = 5 is the wrong gate for the
sport and that is a finding worth more than a detector -- report it and STOP at step 1. State the
seed and commit the labels. A wide-pitch view share of 0.65 [0.594, 0.702] is already measured
(g34_soccer_view_share_2026-09-02.md); your number is about LANDMARKS, not view width, so do not
reuse it.
STEP 2, only if step 1 shows >= 5 landmarks are commonly visible: extend `keypoints.py` to detect
the penalty-box family. The penalty box is the right target because it is NON-PERIODIC and its
four corners have DISTINCT roles (goal line, 16.5 m front line, two side lines), so a solve keyed
on it cannot silently flip end-for-end the way a symmetric feature can. Name every landmark you
emit with the same key as CANONICAL_LANDMARKS["soccer"] -- a positional or index-ordered corner is
exactly the "position-ordered corners" the existing docstring refuses, and it is how a homography
comes out mirrored while every internal check passes.
THE ACCEPTANCE BAR IS EXTERNAL, NOT SELF-CONSISTENT (contract B8): leave-one-out reprojection at
2.0 m is a self-fit check and is NOT sufficient on its own. Additionally measure a KNOWN REAL-WORLD
DISTANCE that was NOT used in the solve and report its error in metres -- for example solve on the
penalty box and then measure the centre-circle radius (9.15 m) or the halfway-line length, or solve
on four corners and check the fifth. One clause of honest caveat: real pitches vary a few metres
around the 105x68 the module hardcodes, so an absolute error under roughly 1 m is not distinguishable
from pitch variation and must not be claimed as better than that.
DO NOT: change MIN_LANDMARKS, change MAX_HELDOUT_ERROR_M, change the coordinate contract, promote
any clip to court_feet in this row, or touch any harness threshold. Emitting landmarks is this
row. Whether soccer rows may DECLARE court_feet is a separate adjudicated decision and it needs the
external error number this row produces before it can be made.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = (a) share of frames with >= 5 visible canonical landmarks, and if step 2 runs,
                  (b) share of frames where detect() returns >= 5 NAMED landmarks, and
                  (c) held-out real-world distance error in metres
  before        = detect() returns 1 landmark on 100 pct of frames; homography solvable on 0 pct
  bar           = there is NO pass bar on (a) -- it is the measurement. If step 2 runs, success is
                  (b) > 0 pct with (c) reported honestly, whatever it is. A large (c) is a real and
                  publishable result: it says broadcast soccer does not support a 2 m solve yet.
  n             = >= 100 seeded frames across all five clips; state the seed and per-clip counts
  eye check     = REQUIRED. Render the detected landmarks onto the frame and look at them. A
                  landmark set that scores well and sits on the wrong lines is the failure mode
                  here, and only the eye catches it. Commit the renders.
  must not move = MIN_LANDMARKS, MAX_HELDOUT_ERROR_M, the coordinate contract, every harness
                  threshold, and every existing verdict
EVIDENCE: docs/evidence/tracking/g91_soccer_landmarks_2026-09-0X.md with the visibility distribution,
the seed, the detector result if built, the external distance error, the renders, and a NOT
VERIFIED list. Commit labels and renders under docs/evidence/tracking/g91_soccer_landmarks/ BEFORE
reporting (A7).
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: READ-ONLY, pull clips only. Never kill anything -- the tracking daemon and seven footage bridge
lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a7,
no push. Report the sha.
SHARED MODULE: none. keypoints.py is soccer-only and is not under the token.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
