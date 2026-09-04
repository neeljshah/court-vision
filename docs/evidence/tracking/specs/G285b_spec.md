GAP G285b | sport wnba | worktree a5 | log g285b_locate_then_match_recall
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO DECODE, NO DISK GUARD, NO HOLD RULE. START IMMEDIATELY.**
Committed inputs:
  - frames: `docs/evidence/tracking/g278_census_stratified_followup_artifact/part_a/frames/` (61 JPEGs,
    each 1920x1080)
  - G284's sealed per-frame visible-player counts:
    `docs/evidence/tracking/g284_detector_recall_bound_artifact/per_frame_join.csv`
  - G267 footpoints: `g267_court_space_physical_plausibility_artifact/g267_measurement.json`

**READ THE G285 MEMO AND THE G285-NOT-ACCEPTED LEDGER ROW FIRST. THIS SPEC IS SHORT ON PURPOSE.**

**WHY THIS RE-ISSUE EXISTS -- MY RENDER DESIGN BROKE G285, NOT THE LANE'S EXECUTION.**
G285 asked a labeller to decide, on a **whole 1920x1080 frame**, whether a 7-pixel dot lay **within 25
source pixels** of a player's feet. **25 px is 1.3 pct of frame width.** It returned
**4 / 524 = 0.0076 recall** and **360 / 365 = 0.9863 unmatched markers**, which cannot sit beside G273's
sealed blind **0.208 NOT A PERSON** rate. **The task was near-impossible at that scale and every failure
mode of it biases toward UNMATCHED.** G285's protocol was exemplary; the number is a methods artifact.

**THE FIX: NEVER ASK A HUMAN "IS THIS DOT ON THAT PERSON". SPLIT THE JOB.**

THE QUESTION: **for each visible on-court player, is there a detector footpoint at their feet?**

METHOD:
  1. **PICK 15 FRAMES** from G284's 54 judgeable frames, evenly spaced across the span. **State which and
     how.** Fifteen keeps the locating work tractable; it is a deliberate scope cut, not a head slice.
  2. **PASS A -- LOCATE, WITH NO MARKERS AND NO DETECTION DATA SHOWN.** Split each frame into
     **full-resolution tiles** (a 3x2 or 4x3 grid, your choice -- **state it, and state the overlap you
     use so a player on a seam is not lost or double-counted**). For every visibly on-court player,
     **record the pixel coordinates of their feet** in source-image space. **Nothing about detections may
     be visible during this pass.** **Commit the coordinates and the tiling in their own commit BEFORE
     touching any detector record.**
  3. **PASS B -- MATCH BY ARITHMETIC, NOT BY EYE.** Match located feet to G270-on-court G267 footpoints
     within a radius you **state before running it**. **No human judges any match.** Report the matching
     rule, and report results at **three radii (say 25, 50 and 100 px)** so a reader can see the
     sensitivity instead of trusting one cut point -- **but nominate ONE radius as primary before you
     compute anything.**
  4. **REPORT: matched players / located players = RECALL**, with a 95 pct Wilson interval, at the primary
     radius and at the other two. Also report **footpoints matching no located player**, separately.
  5. **CROSS-CHECK AGAINST THE SEALED COUNTS.** Compare your located-player count per frame with G284's
     sealed visible-player count for the same frame. **They should be close. If they differ materially,
     say so and treat it as a finding about count reproducibility, not as licence to adjust either.**
  6. **COMPARE AGAINST G284's 0.416 UPPER BOUND AND G285's REJECTED 0.0076** in one sentence each.
     **If this row lands near 0.416 or above, it confirms the bound and confirms G285 was a scale
     artifact. If it lands near 0.0076, then G285 was right and my rejection of it was wrong -- say that
     plainly.**
  7. **Do NOT re-detect, do NOT touch `src/`, propose no filter, threshold, gate or retrain, and do NOT
     tune the radius after seeing results** (contract B10).

**LIMITS to state:** 15 frames of ONE shot of ONE clip, ONE labeller. **Occluded players remain invisible
to labeller and detector alike, so the denominator is still "visible" players and recall stays inflated
relative to true recall.** **Per G278 the span is measurably friendlier than the clip (0.836 against
0.656, p = 0.0078): NOT clip-wide.** G267's detections are ONE non-deterministic draw. **A footpoint is
not a box.** **Located coordinates are a human estimate of where feet are, so the match radius absorbs
both detector error and locating error** -- that is why the sensitivity curve in step 3 matters. The
population is detector-box observations, not authenticated players.

ACCEPTANCE RULE:
  metric        = the 15 frames and how chosen; the tiling and overlap; the committed located
                  coordinates; the primary radius declared before computing; recall with a Wilson
                  interval at three radii; unmatched-footpoint counts; the per-frame comparison against
                  G284's sealed counts; and the two one-sentence comparisons in step 6
  before        = recall is unmeasured: G284 bounds it at 0.416 with no per-person matching, and G285's
                  0.0076 was rejected as a judgement-scale artifact
  bar           = **NO pass bar.** **A recall near or below 0.416 confirms detection as the dominant
                  defect on both axes.** **A recall well above 0.416 breaks a G284 assumption and is the
                  more interesting outcome.** **A result near 0.0076 would mean my rejection of G285 was
                  wrong, and I want that stated bluntly.** Do not tune, do not re-count, do not move a
                  bar.
  n             = 1 clip, 1 shot, 15 frames, the located-player count you state, 1 labeller -- name every
                  denominator in the verdict line
  eye check     = **Pass A locating IS the eye measurement; Pass B involves no eye judgement at all.**
                  Say that distinction -- it is the whole point of the re-issue.
  must not move = G284's sealed counts, G273's counts, G267's records, G270's on-court definition,
                  G278's frames, every threshold and verdict, `src/` and `domains/`, the corpus
EVIDENCE: `docs/evidence/tracking/g285b_locate_then_match_recall_2026-09-04.md` with the frame selection,
tiling, committed coordinates, radius declaration, recall at three radii, unmatched footpoints, the
sealed-count cross-check, the comparisons, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE
SAME COMMIT AS THE MEMO.**
TEST: one per-file test for any harness added, pasted. **NEVER a full pytest.**
COMMIT: explicit pathspec, no push, report the sha. **Commit Pass A coordinates before Pass B runs; make
EVERY commit before you finish.** ASCII stdout. **NEVER PARK.**
