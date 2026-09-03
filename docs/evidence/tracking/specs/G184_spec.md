GAP G184 | sport tennis | worktree a5 | log cx_g184_corner_detector_defect
**DIAGNOSIS ONLY. Change NO production code.** No bar, no threshold, no gate, no solver constant, no
coordinate contract, no verdict. If you find yourself editing a value in `domains/tennis/tracking/`
to make a frame pass, STOP -- that is an automatic REJECT under B10/Q3 and it forced a retraction in
this program already.

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read in full. Self-check section B before
reporting. Q8 premise-first is the whole first phase of this job.

WHY (landed, do not re-derive):
  - **G182** (`g182_calibration_unavailable_cause_2026-09-03.md`): exhaustive funnel over 28,773
    decoded frames of the pod clip. The wall is `detect_court_corners` -- 26,113/28,773 = 90.755 pct
    reach corner detection and return nothing. Every headline was recomputed by the orchestrator from
    the committed per-frame artifact and reproduces exactly.
  - **G182b** (`g182b_demo_clip_replication_2026-09-03.md`): a second independent run on a different
    clip found the same wall, and its evenly sampled frame 149 is a wide broadcast view with the
    COMPLETE doubles rectangle -- all four doubles corners visible and unoccluded, every baseline,
    sideline, service line and the net crisply rendered. `detect_court_corners` returned `None`.
    The orchestrator viewed that render directly and confirms the description.
  - So: the wall is replicated and certain; the CAUSE is not. G182's "unrecoverable on this footage"
    is WITHDRAWN. An unmeasured share of the 90.755 pct is a detector limitation, not a footage one.

THE QUESTION, and it is the only one: **on a frame that plainly carries the four corners, WHICH gate
inside the corner path rejects it, and what is the measured value against that gate's threshold?**

The frame is committed: `docs/evidence/tracking/g182b_funnel/frame_00149_enough_corners.jpg`. It is a
RENDER with burned-in overlays, so prefer decoding frame 149 from `docs/evidence/demo/tennis.mp4`
directly; if you use the render, say so and treat the overlay as an uncontrolled difference.

METHOD:
  (a) Quote the full chain from `detect_court_corners` down through line selection into
      `solve_corners`, and enumerate EVERY explicit return-None / reject gate with its threshold.
  (b) Instrument READ-ONLY, in your measurement process only, and record the value each gate saw on
      this frame. Never edit the module under test. The value at the failing gate is the deliverable.
  (c) Report the FIRST gate that rejects, with its measured value and its threshold side by side.
  (d) Then widen: run the same instrumentation over ALL 150 frames of the demo clip and over an
      evenly spaced sample of at least 200 of G182's 26,113 corner-loss frames on the pod clip.
      Report the DISTRIBUTION of first-failing gate. That distribution is what turns G182b's n=1
      existence proof into a rate.

MANDATORY:
  - **A3 even sampling** on any subset; state positions and resulting frame indices. A head slice is
    an automatic reject under B7 -- one G182 run already sampled frames 0/37/74/112/149 and that is
    exactly the pattern to avoid.
  - **Name the ELIGIBLE denominator on every row**, never the sample size.
  - A per-file test for any harness you add under `scripts/platformkit/tracking/`.
  - **Store PER-FRAME records in your artifact, not just aggregates.** G182b's artifact holds only
    aggregated counts and therefore could NOT be independently recomputed by the verifier; G182's
    per-frame records could. Do not repeat that.
  - Distinguish "the detector is imperfect" from "the detector is broken". If the first-failing gate
    is the same one on nearly every frame, say so plainly; if it is spread across gates, say that.

ACCEPTANCE RULE:
  metric        = the first-failing gate and its measured-vs-threshold value on frame 149; then the
                  distribution of first-failing gate over the two sampled populations
  before        = the wall is located at corner detection but its cause is unknown; one frame is
                  known to fail with full geometry present
  bar           = NO pass bar. Success is naming the gate and producing the distribution.
                  "The gate is X and it rejects because the input genuinely lacks Y" is a FULL
                  SUCCESS. So is "no single gate dominates".
  n             = 1 frame for the located gate (existence); >= 350 frames for the distribution
  eye check     = render the 5 evenly spaced frames whose first-failing gate is the MODAL one and
                  say whether a human sees the four corners in each
  must not move = every threshold and constant in domains/tennis/, the coordinate contract, every
                  bar, every verdict, src/ (human-gated), the pod daemon
EVIDENCE: docs/evidence/tracking/g184_corner_detector_defect_2026-09-03.md with the quoted gate chain,
the frame-149 measured-vs-threshold row, the distribution table with eligible denominators, the eye
check, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: your new per-file test, pasted. NEVER a full pytest.
POD: READ-ONLY and BATCHED. Never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
