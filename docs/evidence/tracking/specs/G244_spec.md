GAP G244 | sport wnba | worktree a5 | log g244_homography_validity_signal
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**THIS ROW NEEDS LITTLE OR NO POD.** G242's 89 overlays and its full per-sample diagnostics are already
committed in master. **Prefer working from the committed artifacts.** If you do use the pod, check first,
do NOT interrupt a running row, and say in your memo that you checked and when you began.

**WHY THIS ROW EXISTS -- G242 REMOVED THE GROUND FROM UNDER EVERY "IT HELD" CLAIM THIS PROGRAMME HAS
MADE.**
G242 sampled a whole game at stride 2000 and matched 89 frames directly against the G233d seed.
**G222's acceptance rule accepted 89 of 89 -- 1.000000.** The lane then opened all 89 overlays and found
the accepted set contained **52 normal court views, 29 tight player/bench/crowd views, 6 replay/overhead
views and 2 graphic/partial views.** Frame 8000 is **the other hoop end**, where the projected court
plainly does not land on the visible paint, and it passed. Its conclusion, which I accept: **"the
acceptance rule is not a geometry-validity rule."**

**This means inlier counts, inlier ratio and RMS residual have NEVER been shown to indicate that a
projected court is correct.** G233d's 1,200-frame hold and whatever G241b reports rest on their RENDERS
alone. That is a real but expensive form of evidence: a human must look at every frame.

THE QUESTION: **does ANY available match diagnostic separate a visibly-correct court from a visibly-wrong
one, on G242's 89 frames?**

**WHY THE ANSWER MATTERS EITHER WAY.** If some diagnostic separates them, the programme gets its first
automatic validity signal and long runs stop needing an eye on every frame. **If nothing separates them,
that is the more important result:** it says the matcher is blind to correctness, every horizon claim is
render-bound, and validity needs a different instrument entirely.

METHOD:
  1. **RE-LABEL THE 89 OVERLAYS BLIND, ON VALIDITY, BEFORE LOOKING AT ANY DIAGNOSTIC.** Record for each
     frame exactly one of **VALID** (the projected court lands on the painted court), **INVALID** (it
     visibly does not), or **CANNOT JUDGE** (no painted geometry is visible -- a close-up, a graphic, a
     crowd shot). **Judge on INDEPENDENT geometry -- arc, free-throw circle, sideline, baseline -- NEVER
     on the four fitted corners.** **Do not read G242's inventory, the inlier counts, or the RMS until
     your labels are written and committed.** Say in the memo that you did this in that order.
  2. **VALIDITY IS NOT SCENE TYPE, and conflating them is the trap.** Frame 8000 is a perfectly normal
     court view AND an invalid map. Record the scene type separately and **cross-tabulate the two.**
  3. **Measure your agreement with G242's single-labeller inventory** where the two are comparable, and
     report it. A row resting on eye labels must measure their agreement, not assume it.
  4. **Join your labels to the committed diagnostics** in
     `g242_seed_reacquisition_whole_game_artifact/per_sample_table.csv` -- matched features, inliers,
     inlier ratio, RMS reprojection residual, and anything else it carries.
  5. **Report each diagnostic's distribution BY CLASS (min/median/p90/max and n), and state the OVERLAP
     explicitly** -- how many VALID frames fall inside the INVALID range and vice versa. **The overlap is
     the answer; a difference in medians is not.**
  6. **DO NOT FIT A THRESHOLD AND THEN REPORT ITS ACCURACY ON THESE SAME 89 FRAMES.** That is in-sample
     overfitting and it would be a false positive for the programme. If a clean separation exists, **say
     so, give the exact overlap count, and label it IN-SAMPLE ONLY, requiring out-of-sample confirmation
     on a clip this row did not touch.** Do not propose a production threshold.
  7. **Also test the cheap geometric sanity checks the matrix itself allows**, since they cost nothing and
     are not thresholds on match quality: is the projected court convex, is its area plausible, are its
     corners ordered consistently, does it invert or fold? **Report whether any of these separates the
     classes**, with the same overlap discipline.
  8. **If nothing separates, say so plainly and do not soften it.** "No available diagnostic distinguishes
     a correct court from a wrong one on these 89 frames" is a complete and valuable result.

**DISK GUARD:** if you touch the pod at all, `df` is NON-AUTHORITATIVE -- **`dd conv=fsync` probe before
writing and record `du -sm /workspace/nba-ai-system/data` (baseline ~32,940 MB of 50,000).** This row
should add almost nothing; **do NOT re-commit G242's 12.4 MB artifact.** Delete every temporary artifact
and report bytes freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** 89 frames from ONE clip, ONE seed, ONE arena, sampled at a
wide stride, and **one labeller -- you.** G140's p90 label repeatability is 11.39 px and
eye-label reliability in this programme has never cleared 80 pct blind agreement on any of four measured
criteria,
so **report your own agreement with G242 rather than presenting your labels as ground truth.**
**CANNOT JUDGE is a real and expected class** -- 29 of G242's frames were tight views with no court
visible -- and it must not be silently merged into either other class. A separation found here would be
in-sample and would NOT establish a usable gate.

ACCEPTANCE RULE:
  metric        = the blind VALID/INVALID/CANNOT JUDGE counts; agreement with G242's inventory; each
                  diagnostic's distribution by class with the explicit overlap count; the same for the
                  geometric sanity checks; and a plain statement of whether anything separates
  before       = G242 showed G222's acceptance rule accepts 89/89 including replays, graphics and the
                 wrong hoop end; no diagnostic has ever been shown to indicate court correctness
  bar          = NO pass bar. **"Nothing separates them" is a FULL SUCCESS and is the more consequential
                 outcome** -- it would make every horizon claim render-bound and redirect the programme to
                 a different validity instrument. **"Diagnostic X separates them with zero overlap" is the
                 other full success**, reported IN-SAMPLE ONLY. Do not fit a threshold to these frames and
                 report its accuracy on them, and do not propose a production change.
  n            = 89 frames, 1 clip, 1 seed, 1 labeller -- state this denominator in the verdict line
  eye check    = the blind validity labels ARE the measurement
  must not move = every threshold, bar and verdict, G222's matcher settings, the court model, the
                  coordinate contract, the harness, the label files, `src/` and `domains/` (READ and
                  IMPORT ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g244_homography_validity_signal_2026-09-04.md with the blind labels as a
committed table, the ordering statement, the agreement with G242, the per-class distributions with
overlaps, the geometric sanity-check results, the plain separation verdict, any disk-guard probe, bytes
freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO** -- G242
committed a memo without one. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
