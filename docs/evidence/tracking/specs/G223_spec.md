GAP G223 | sport ncaa_basketball / wnba | worktree a5 | log g223_line_error_structure
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: RUN LOCALLY. Do NOT use the pod.** Everything is committed: the 17 frames under
`docs/evidence/tracking/g130_recensus/source_decodes/`, the labels at
`docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv`, and G217's artifact at
`docs/evidence/tracking/g217_oracle_error_decomposition_artifact/`.

**WHY THIS ROW EXISTS -- G217 REOPENED CALIBRATION AND THIS IS THE FIRST QUESTION IT RAISES.** G217
established (and the orchestrator re-verified in master) that the fitter and court model contribute
**zero** error: exact lines through the labelled corners give 17/17 at 0.000000 px through the same
unchanged `solve_line_pairs` and G205 `score_frame`. **All of the oracle's 28.841316 px median
max-corner error is DETECTED LINE GEOMETRY.** The selected detected lines miss the two labelled corners
they should pass through by **median 10.234792 px, max 59.693249 px** over 68 role-frame selections.
**So detection accuracy is the live lever. This row asks what SHAPE that 10.23 px error has, because
different shapes have completely different fixes.**

**A PREMISE THE ORCHESTRATOR ALREADY MEASURED FROM G217's `per_frame.csv`, so do not re-derive it:
oracle max-corner error does NOT track source resolution.** Median by resolution is **28.600 px at
1920x1080 (n=12), 32.699 px at 1280x720 (n=4), 26.693 px at 640x360 (n=1)** -- flat -- and **the single
frame that passes is 720p at 6.745 px, not a 1080p frame.** **HONEST POWER LIMIT, state it: with a
12/4/1 split this construct cannot detect a modest resolution effect, so read this as "no effect is
visible here", NOT as "resolution does not matter".** It does not contradict
`tennis_resolution_controlled_2026-09-01.md`, which measured how many frames REACH the five-line gate
(detection recall) -- a different quantity from the residual geometry of lines already detected and
perfectly selected.

THE QUESTION: **is the 10.23 px selected-line error a systematic BIAS or random SCATTER, and is it an
ANGLE error or an OFFSET error?**

**WHY THE DISTINCTION DECIDES THE NEXT MOVE:**
  - **A consistent signed OFFSET** would point at an edge-versus-centreline effect: a painted court line
    has real width and is several pixels wide in image space, so a detector that locks to one painted
    EDGE rather than the line's centre produces a systematic shift. **That is correctable by a
    deterministic refinement and needs no new detector.**
  - **An ANGLE error** compounds with distance along the line, so corner error would grow with distance
    from the segment support. **That points at grouping or fitting -- for example collinear segments
    merged with slightly inconsistent orientation.**
  - **Random scatter with no structure** would say the fix really is a better detector, which is
    expensive and is what G214 wrongly foreclosed. **All three outcomes are full successes.**

METHOD:
  1. **Reuse G217's harness and the oracle's own selection unchanged**, so every number stays
     commensurable with G210b, G214 and G217. Reproduce G217's median 10.234792 px and max 59.693249 px
     first as a control. **If you cannot reproduce them, STOP and report that.**
  2. **Recompute the point-line distances as SIGNED values**, not absolute. For each selected line and
     each of its two labelled corners, record the signed perpendicular distance with a consistently
     defined normal direction. **State exactly how you fixed the sign convention** -- an inconsistent
     convention would manufacture a fake bias and is the main way this row could go wrong.
  3. **Test for bias per role.** For each of the four roles (`near_baseline`, `near_free_throw`,
     `lane_left`, `lane_right`), report the mean signed distance, its spread, and how many of the 17 are
     positive. **A role whose signed errors are consistently one-signed is a BIAS; one that straddles
     zero is SCATTER.** Report each role separately -- G217 already showed the roles differ, with
     `lane_left` worst at 13.91 px median and `lane_right` carrying the 59.69 px maximum.
  4. **Decompose ANGLE versus OFFSET.** For each selected line, compare its orientation with the
     orientation of the exact line through the two labelled corners, and report the angular difference
     in degrees alongside the perpendicular offset at the corner midpoint. **Say which of the two
     dominates, with numbers.**
  5. **Relate the structure to the corner error.** The score is a CORNER error and corners are line
     INTERSECTIONS, so a small angle error on two nearly parallel lines can produce a large corner
     error. **Report whether the frames with the largest corner errors are the ones with the largest
     angle errors or the ones whose line pairs meet at the shallowest angle.** That distinction matters:
     a shallow intersection is geometrically ill-conditioned and no detector improvement fixes it.
  6. **Do NOT build a corrected detector or apply any refinement.** If the evidence points at a specific
     deterministic fix, **describe it and state the error reduction it would predict**, as a proposal
     for a future row. This row characterises an error; it does not chase a better number.

**HONEST LIMITATIONS to state, not discover:** 17 frames and 68 selections is a small exhaustive
construct, not a rate. G140's p90 label repeatability is **11.39 px**, and the median selected-line
error of 10.23 px is BELOW that floor -- **so a large part of the measured "error" may be label noise,
and you must say so plainly and avoid attributing structure to noise.** A bias detected at a magnitude
near the label floor is weak evidence; say how strong yours is. The labels are single-source eye labels
with no second labeller.

ACCEPTANCE RULE:
  metric        = signed point-line distance per role (mean, spread, sign count over 17); angular
                  difference versus perpendicular offset per selected line, with a statement of which
                  dominates; the relation between corner error, angle error and intersection
                  conditioning
  before        = the selected-line error is known only in ABSOLUTE terms -- median 10.234792 px, max
                  59.693249 px -- with no knowledge of whether it is bias or scatter, angle or offset
  bar           = NO pass bar. **"The error is unstructured scatter at the label-noise floor" is a FULL
                  SUCCESS** and would say the cheap deterministic fixes are unavailable. So is finding a
                  clean bias. **Do not manufacture structure, and do not claim a bias you cannot
                  separate from the 11.39 px label floor.**
  n             = 68 role-frame selections over 17 frames (CONSTRUCT, exhaustive)
  eye check     = for the 3 frames with the largest corner error, render the selected detected line, the
                  exact label-derived line, and the two labelled corners together; commit them
  must not move = every threshold, the 12 px protocol, G205's scorer contract, `solve_line_pairs`, the
                  oracle's selection rule, the court model, the coordinate contract, every bar and
                  verdict, `src/` (READ ONLY), the pod (DO NOT USE IT), the corpus
EVIDENCE: docs/evidence/tracking/g223_line_error_structure_2026-09-04.md with the reproduction control,
the sign-convention statement, the per-role signed table, the angle-versus-offset decomposition, the
conditioning analysis, the renders, an explicit treatment of the 11.39 px label floor, any proposal
clearly marked as a future row, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
