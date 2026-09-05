GAP G290 | sport wnba | worktree a3 | log g290_footpoint_offset_axis_decomposition
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO GPU, NO DECODE, NO DISK GUARD, NO HOLD RULE. START
IMMEDIATELY.** Both inputs are committed and already in your worktree:
  - `docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv`
    -- hand-located player feet in image pixels, keyed by `source_frame`.
  - `docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json`
    -- retained detector footpoints (`foot_x_px`, `foot_y_px`) on the same frames.
  - `scripts/platformkit/tracking/verifier_footpoint_analyses.py` -- **REUSE `load_located()`,
    `load_detections()` and the `CROP_HALF_W/CROP_HALF_H` constants. Do not redefine the box.**

**READ FIRST:** the G285b, G286, G287 and G288 memos and their ledger rows, and
`verifier_footpoint_analyses.py` in full.

**WHY THIS ROW EXISTS -- A SINGLE NUMBER IS DOING TOO MUCH WORK.**
The verifier measured that of 112 detector footpoints on frames with located feet, **79 (0.705) have a
located player foot inside G273's 512x640 box, and among those the MEDIAN DISTANCE TO THE NEAREST LOCATED
FOOT IS 172.36 px.** That single scalar is currently the programme's whole account of localisation error,
and **it cannot distinguish two completely different defects:**
  - **VERTICAL error** -- the detection is on the RIGHT person but the footpoint sits at the hip, the head,
    or below the feet. At 1080p a standing player is on the order of one to two hundred pixels tall, so
    **a 172 px offset is roughly one body**. That is a **footpoint-derivation or box-extent** defect and it
    needs no retraining.
  - **HORIZONTAL error** -- the detection is on a DIFFERENT object or a different person. That is a
    **detector** defect and it does need retraining.
**Nobody has separated them. The distance is unsigned and axis-blind.**

THE QUESTION: **is the 172 px offset predominantly vertical, predominantly horizontal, or isotropic -- and
does the vertical component have a consistent SIGN?**

METHOD:
  1. **REPRODUCE THE PAIRING EXACTLY FIRST.** Using the committed harness, reproduce **n = 112, in_box =
     79 (0.705), no_player 0.295, median 172.36 px** and paste that check. **If you cannot reproduce it,
     STOP and report that as the finding.** Pair each detector footpoint with the NEAREST located foot
     inside the box, exactly as `footpoint_player_split()` does.
  2. **FOR EVERY IN-BOX PAIR RECORD THE SIGNED COMPONENTS**: `dx = detection_x - located_x` and
     `dy = detection_y - located_y`, in image pixels, **with image y increasing DOWNWARD -- state that
     convention explicitly in the memo**, because the sign is the entire result.
  3. **REPORT, FOR |dx| AND |dy| SEPARATELY**: median, inter-quartile range, and the share of total squared
     offset each axis contributes (they sum to 1 -- print the sum). **Report the median |dy| / |dx| ratio.**
  4. **REPORT THE SIGN OF dy**: the count and fraction of pairs where the detector footpoint is BELOW the
     located foot (greater y) versus ABOVE it, with a **binomial test against 0.5** -- report the nominal
     two-sided p and **say it is nominal with no multiplicity correction**. **A strong one-sided bias means
     a systematic footpoint rule, not random error. A balanced split means it is not systematic.** Do the
     same for `dx` against 0.5 as a control -- **a horizontal bias would be surprising and must be
     flagged, not explained away.**
  5. **ANSWER IN ONE SENTENCE WITH NUMBERS: is the offset predominantly vertical, predominantly
     horizontal, or isotropic?** **Predominantly vertical with a consistent sign relocates the defect from
     the detector to the footpoint derivation. Isotropic or horizontal keeps it on the detector. BOTH ARE
     FULL SUCCESSES and I want whichever is true stated bluntly.**
  6. **DO NOT CONVERT dy INTO FEET.** `local_pixel_to_feet` in the G267 artifact maps the GROUND PLANE. **A
     vertical image offset from a player's feet toward the head is NOT a ground-plane displacement, and
     pushing it through a court homography would produce a meaningless number.** **State that you did not
     do it and why.** Report every offset in PIXELS.
  7. **REPORT THE OFFSET AGAINST IMAGE `foot_y_px`** -- median |dy| by `foot_y_px` tercile, with the
     ELIGIBLE denominator (in-box pairs falling in that tercile) in every cell. **Name the denominator,
     never the sample size.** Apparent player size shrinks with distance from a courtside camera, so **if
     the offset is a body-scale effect it should SHRINK toward small `foot_y_px`; if it is constant in
     pixels it is not body-scale.** Say which you observe. **With 79 pairs the terciles are small: state
     the per-cell denominators and do NOT claim a trend that a handful of pairs cannot support.**
  8. **THE 33 OUT-OF-BOX FOOTPOINTS ARE NOT IN THIS ANALYSIS AND MUST BE NAMED AS EXCLUDED**, with their
     count and fraction, in the verdict line.
  9. **Propose NO filter, threshold, gate, footpoint rule change, re-projection, retrain or production
     change. Do NOT touch `src/`. Do NOT move any bar.**

**HONEST LIMITATIONS to state, not discover:** **THIS RESULT IS CONDITIONED ON A PLAYER BEING IN THE BOX
AND DOES NOT TRANSFER TO THE UNCONDITIONED QUESTION** -- 0.295 of footpoints have no located player in the
box at all and they are excluded here; **an earlier row generalised a paired result to the unpaired
population and it had to be corrected in four documents, so state the conditioning in the verdict line
itself.** The located feet are **ONE labeller's hand locations, not ground truth**, and the same labeller
produced the verdicts this programme's other rows rest on. **The nearest-foot pairing can itself be wrong**
-- when two players stand close, the nearest located foot may not belong to the person the detector fired
on; **say that the pairing is an assumption and note how many pairs had a second located foot within the
box.** ONE clip, ONE span, ONE draw of a NON-DETERMINISTIC route (G241: 808 of 1,201 records differed).
**Per G278 the span is measurably friendlier than the clip (0.836 against 0.656, p = 0.0078), so nothing
here may be quoted clip-wide.** **The population is detector-box observations, not authenticated players.**

ACCEPTANCE RULE:
  metric        = the reproduced 112 / 79 / 0.705 / 172.36 px check; signed `dx` and `dy` per in-box pair;
                  per-axis median, IQR and squared-offset share summing to a printed 1.000; the median
                  |dy|/|dx| ratio; the dy and dx sign splits with binomial nominal p; the one-sentence
                  axis answer; the |dy| by `foot_y_px` tercile table with eligible denominators; the count
                  of pairs with a second located foot in the box; and the named excluded 33
  before        = a single unsigned axis-blind median of 172.36 px over 79 in-box pairs, which cannot
                  distinguish a footpoint-derivation defect from a detector defect
  bar           = **NO pass bar.** **Predominantly vertical with a consistent sign relocates the defect to
                  the footpoint rule. Isotropic or horizontal keeps it on the detector. A split too noisy
                  to call at n = 79 is an honest result. ALL are full successes.**
  n             = 112 footpoints on frames with located feet, 79 in-box pairs, 33 excluded, 1 clip, 1 span,
                  1 labeller, 1 draw -- name every denominator in the verdict line and say the result is
                  CONDITIONED on a player being in the box
  eye check     = NONE. This is arithmetic on two committed coordinate sets. There is no new visual
                  judgement and no ground truth. **Say that rather than implying validation.**
  must not move = G285b's located feet and its counts; G273's crop geometry and verdicts; G267's retained
                  records and span; G286-G288's counts; `verifier_footpoint_analyses.py`'s definitions;
                  every threshold and verdict; `src/` and `domains/` (READ and IMPORT ONLY)
EVIDENCE: `docs/evidence/tracking/g290_footpoint_offset_axis_decomposition_2026-09-04.md` with the
reproduction check, the per-axis table, the sign tests, the tercile table with denominators, the
one-sentence answer, the pairing-ambiguity count, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN
THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for the harness, pasted -- **pin the 79-pair reproduction and pin the sign
convention (a detection BELOW a located foot gives positive `dy`).** **NEVER a full pytest.** **If a commit
grows an allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
