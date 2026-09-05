GAP G289 | sport wnba | worktree a6 | log g289_implausible_step_decomposition
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO DECODE, NO GPU, NO DISK GUARD, NO HOLD RULE. START
IMMEDIATELY.** Every input is committed and already in your worktree:
  - `docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json`
    -- per-frame retained detections carrying BOTH image coordinates (`foot_x_px`, `foot_y_px`) AND court
    coordinates (`court_x_ft`, `court_y_ft`) for the same point.
  - `scripts/platformkit/tracking/verifier_footpoint_analyses.py` -- the verifier's committed harness.
    **REUSE ITS `steps()` FUNCTION. DO NOT REDEFINE A STEP.**

**READ FIRST:** the G267, G271, G279 and G282 ledger rows; the CORRECTION row withdrawing the bimodal
mechanism; the VERIFIER NOTE row on jump-return; and `verifier_footpoint_analyses.py` in full.

**WHY THIS ROW EXISTS -- THE PROGRAMME'S LARGEST UNEXPLAINED NUMBER.**
**4,090 of 29,973 same-id consecutive-observation steps = 0.136456 imply a court-space speed above
40 ft/s**, which is above human sprint speed; G279 showed **7.6 pct still exceed 60 ft/s**, about 1.47x
Usain Bolt's peak. **Two candidate mechanisms have been tested and BOTH were withdrawn or refuted:**
  - **bimodal track ids** (a single id absorbing detections from two fixed locations): **explains 0.045 of
    implausible steps. Withdrawn as the mechanism.**
  - **alternation** (a jump that comes straight back): **refuted -- 0.876 of large image jumps do NOT
    return within 5 frames.**
**So roughly 95.5 pct of the implausible steps have NO established mechanism.** Identity is measurably the
HEALTHY axis (G281 purity 0.935 at 1 s), so "the tracker swaps players" is not obviously the answer.

**THE HYPOTHESIS THIS ROW TESTS, AND IT HAS NEVER BEEN TESTED: a court-space step can be enormous without
the IMAGE-space step being enormous at all.** The footpoint is mapped to the court by a homography, and a
homography's ft-per-pixel scale **grows without bound toward the horizon**. A footpoint far from the
camera can move a handful of pixels and travel tens of feet on the mapped court. **If that is where the
implausible steps live, the mechanism is PROJECTIVE ILL-CONDITIONING OF THE MAPPING, not tracking failure
-- and those are different defects with different fixes.**

THE QUESTION: **for the 4,090 implausible steps, how do they partition between LARGE IMAGE DISPLACEMENT
and SMALL IMAGE DISPLACEMENT AMPLIFIED BY A HIGH LOCAL SCALE -- and do the shares sum to 1?**

METHOD:
  1. **USE `verifier_footpoint_analyses.steps()` FOR THE STEP DEFINITION -- IMPORT IT, DO NOT REWRITE IT.**
     A step is a consecutive-OBSERVATION same-id pair, NOT a unit frame gap; requiring gap == 1 gives
     26,517 steps and a false 0.111966 against the reference 4,090 / 29,973 = 0.136456. **Reproduce
     0.136456 EXACTLY before you measure anything else and paste that check.** If you cannot reproduce it,
     STOP and report that as the finding.
  2. **For EVERY step compute BOTH displacements**: image displacement in pixels between the two
     footpoints, and court displacement in feet between the two mapped points, plus the frame gap.
  3. **COMPUTE THE EMPIRICAL SECANT SCALE = court_feet / image_pixels for each step.** **CALL IT A SECANT
     SCALE AND SAY WHY: it is the average ft-per-px ALONG the step, NOT the local Jacobian of the
     homography. For a short step the two converge; for a long one they do not. State that limit in those
     words and do not call it a local scale.** Guard the zero-pixel case explicitly and report how many
     steps had image displacement 0 -- those are steps where the mapped point moved with NO image motion
     at all, and that count is itself a result.
  4. **PARTITION ALL 4,090 IMPLAUSIBLE STEPS INTO EXHAUSTIVE, MUTUALLY EXCLUSIVE BUCKETS BY IMAGE
     DISPLACEMENT** -- suggested cuts 0 px, (0, 5], (5, 20], (20, 50], (50, 150], above 150 px, but choose
     and JUSTIFY your own if better. **THE SHARES MUST SUM TO 1.000 AND YOU MUST PRINT THE SUM.** For each
     bucket report: count, share of the 4,090, median secant scale, and median court feet travelled.
  5. **ANSWER THE DECOMPOSITION IN ONE SENTENCE WITH A NUMBER**: what share of the 4,090 moved 20 px or
     less in the image? **A large share means the mechanism is the MAPPING, not the tracking. A small
     share means real image-space jumps and the mapping is exonerated. BOTH ARE FULL SUCCESSES.**
  6. **TEST THE GEOMETRIC SIGNATURE.** If amplification is the mechanism, implausible steps must
     concentrate where ft-per-px is high, which for a court-side broadcast camera means SMALL `foot_y_px`
     (far from the camera). **Report the implausible rate by `foot_y_px` decile, with the ELIGIBLE
     denominator -- steps whose midpoint falls in that decile -- in every cell.** **Name the denominator,
     never the sample size.** **A rate that rises monotonically toward the far end is the signature; a flat
     profile REFUTES amplification and you must say so plainly.**
  7. **CHECK THE FRAME GAP AS A CONFOUND.** A step spanning many frames covers more ground legitimately;
     `steps()` already divides by the gap, but **report the gap distribution for implausible versus
     plausible steps** so a reader can see whether long gaps are over-represented. **If they are, say that
     the speed normalisation may not fully absorb it.**
  8. **EVERY MECHANISM YOU NAME MUST CARRY ITS SHARE OF THE 4,090 IN THE SAME SENTENCE.** **This is the
     standing lesson from the withdrawn bimodal claim: structure without magnitude is not an explanation.**
     **If your buckets leave a large residue with no mechanism, REPORT THE RESIDUE AND ITS SIZE and call it
     unexplained. That is the honest result and it is a full success.**
  9. **Do NOT propose a filter, a threshold, a gate, a re-projection, a retrain or any production change.
     Do NOT touch `src/`. Do NOT move the 40 ft/s bar** -- it is G267/G270's published bar and G279 already
     showed the finding survives moving it to 60.
 10. **The population is DETECTOR-BOX OBSERVATIONS, not authenticated players.** G286/G287 measured that
     only about 0.208 of footpoints sit on a player's feet and 0.181 sit on overlay graphics, so **a step
     is a step between two detector footpoints and may connect two things that are not players at all.**
     **Say that; it is a limit on what any mechanism here can mean.**

**HONEST LIMITATIONS to state, not discover:** ONE clip, ONE span (frames 19599-23399), **ONE draw of a
NON-DETERMINISTIC research route** (G241: 808 of 1,201 records differed), so **the 4,090 is one
realisation** -- G282 reproduced the RATE at 0.136978 against 0.136456 on an independent draw, so the rate
is stable even though the individual steps are not. **Per G278 the span is measurably friendlier than the
clip (0.836 against 0.656 court-bearing, p = 0.0078), so nothing here may be quoted clip-wide.** **This row
observes the geometry of a committed mapping; it CANNOT say the homography is wrong, only whether it is
ill-conditioned where the implausible steps live.** **It has no ground truth of any kind -- there is no
verified player position anywhere in it.**

ACCEPTANCE RULE:
  metric        = the reproduced 0.136456 check; the per-step image and court displacements; the
                  zero-pixel count; the exhaustive image-displacement partition of all 4,090 with shares
                  summing to a printed 1.000, plus median secant scale and median court feet per bucket;
                  the one-sentence decomposition answer with its number; the implausible rate by
                  `foot_y_px` decile with eligible denominators; and the gap distributions
  before        = 4,090 / 29,973 = 0.136456 implausible steps with NO established mechanism for about
                  95.5 pct of them; bimodality accounts for 0.045 and alternation is refuted
  bar           = **NO pass bar.** **"Most implausible steps are small image moves amplified by the
                  mapping" relocates the defect from tracking to projection. "Most are genuinely large
                  image jumps" exonerates the mapping and leaves the tracking question open. A flat
                  y-decile profile REFUTES amplification. A large unexplained residue is an honest result.
                  ALL of these are full successes and I want whichever is true stated bluntly.**
  n             = 29,973 steps, 4,090 implausible, 1 clip, 1 span, 1 draw -- name every denominator in the
                  verdict line and name the detector-box population
  eye check     = NONE. This row is arithmetic on committed coordinates; there is no visual judgement and
                  no ground truth in it. **Say that rather than implying validation.**
  must not move = the 40 ft/s bar; `steps()` and its definition; G267's retained records and span; G279's,
                  G281's, G282's and G286-G288's counts and verdicts; every threshold and verdict; `src/`
                  and `domains/` (READ and IMPORT ONLY)
EVIDENCE: `docs/evidence/tracking/g289_implausible_step_decomposition_2026-09-04.md` with the reproduction
check, the full partition table, the y-decile table with denominators, the gap distributions, the
one-sentence answer, the size of any unexplained residue, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for the harness, pasted -- **pin the reproduction of 0.136456 and pin that the
partition shares sum to 1.** **NEVER a full pytest.** **If a commit grows an allowlisted file, raise its
entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
