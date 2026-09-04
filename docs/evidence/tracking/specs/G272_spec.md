GAP G272 | sport wnba | worktree a5 | log g272_box_jump_visual_classification
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` is HUMAN-GATED.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (N=2 is optimal). **Check first, do NOT interrupt a running row, and
EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G267, G269, G270 AND G271 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- THE DIAGNOSTIC CHAIN IS COMPLETE EXCEPT FOR THE CAUSE, AND G271 WAS RIGHT TO
REFUSE TO GUESS IT.**
Five rows established: calibration is fine (5 px median); association cannot repair the implausibility
(G269 -- constraining only fragmented tracks 98 to 139 ids); it is not off-court projection (G270 -- 61.3
pct of impossible steps are fully on court); it is not a few bad tracks (G271 -- 79 of 98 ids affected);
and **the boxes genuinely jump -- 1,454 of 2,507 on-court impossible steps carry image displacement above
83 px in ONE frame.**

**G271 explicitly declined to allocate a cause:** detection motion, association, wrong-person or duplicate
boxes, map error and real movement all remain live. **The only way to settle it is to look at the frames**,
and there is now a specific, bounded thing to look at.

**WHY AN EYE CHECK IS APPROPRIATE HERE, HAVING SPENT THIS PROGRAMME LIMITING THEM.** G257 measured the eye
gate at **20 px** and G260 showed no hand-built signal beats it -- **but that was for judging sub-pixel
court-overlay geometry.** *"Is the box on the same person in both frames?"* is a **coarse categorical
judgement**, not a geometric one, and it is exactly what human vision is reliable at. **Say this
distinction in the memo** rather than importing the 20 px limit where it does not apply.

THE QUESTION: **when a box jumps more than 83 px in one frame on the same id, what actually happened?**

METHOD:
  1. **Reuse G267's retained boxes and span** (frames 19599-23399, G233d's map). **Do not re-detect** --
     G241 established the detector is non-deterministic. **Reproduce G271's 1,454 box-jump count first and
     confirm it matches**; say so if it does not.
  2. **SAMPLE THE BOX-JUMP STEPS EVENLY, NOT A HEAD SLICE.** Take a stated sample -- **at least 40** --
     spread across the span and across distinct ids, and **say how you sampled.** Report how many distinct
     ids the sample covers.
  3. **RENDER EACH SAMPLED STEP AS A BEFORE/AFTER PAIR** at full resolution: the frame before and the frame
     after, **each with that id's box drawn**, side by side, with the image displacement and court speed
     annotated. Keep them small enough to commit and large enough to judge, and **say how you resolved that
     tension.**
  4. **CLASSIFY EACH BLIND, IN RANDOMISED ORDER, AND COMMIT THE ORDER AND VERDICTS BEFORE UN-BLINDING**,
     as G255, G257 and G260 did. Categories, fixed here so none is invented after seeing results:
     **(a) SAME PERSON, box tracked a genuinely fast real movement;
     (b) DIFFERENT PERSON -- the id moved to another body;
     (c) NOT A PERSON in one or both frames -- crowd, bench, official, scoreboard, duplicate or artifact;
     (d) OCCLUDED / CANNOT JUDGE.**
  5. **REPORT THE COUNTS AND THE FRACTION IN EACH CATEGORY, with (d) kept separate and never merged.**
     **That distribution is the deliverable** and it is the first direct evidence of what the defect
     physically is.
  6. **STATE THE CONSEQUENCE PLAINLY.** If (b) dominates, the defect is identity association and the fix
     is a tracker problem. If (c) dominates, the defect is that non-people are being detected and tracked
     at all, and the fix is upstream of association entirely. **If (a) is substantial, part of the 10.5 pct
     is not an error and my "physically impossible" framing needs qualifying** -- say so directly.
  7. **Do NOT propose a production change, filter, gate or threshold; do NOT touch `src/`; do NOT
     re-associate or re-detect.**
  8. **The population is detector boxes, not authenticated players** (G225: 19 boxes, 2 visibly on-court
     people). **Name the denominator; never say "players" unqualified.**

**DISK GUARD, CORRECTED SCOPE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** (last about
**36,400 MB**, roughly 13.6 GB free). **`dd conv=fsync` probe before writing, STOP and report if it
fails.** **Renders are the bulk here -- keep them modest and report committed bytes.** **Do NOT delete any
corpus source or the two abandoned partials in the bridge directory.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one shot, one arena, **one labeller**, one draw of
a non-deterministic detector. **A sample of 40+ from 1,454 is a sample** -- give its size and spread and do
not present category fractions as exact. **Category (b) cannot be proven without identity ground truth,
which does not exist anywhere in this programme** -- it is a single-labeller visual judgement that two
crops show different people, which is coarse but not infallible. Eye-label reliability here has never
cleared 80 pct blind agreement on four measured criteria, though those criteria were geometric rather than
categorical.

ACCEPTANCE RULE:
  metric        = the reproduced 1,454 box-jump count; the sample size, spread and id coverage; the
                  committed randomised order and blind verdicts with the ordering statement; the counts and
                  fractions in categories (a)-(d) with (d) separate; and a plain statement of the
                  consequence for where the defect lives
  before       = the chain shows boxes jump 83+ px on 58 pct of on-court impossible steps, systemically
                 across 79 of 98 ids, but G271 correctly refused to allocate a cause
  bar          = NO pass bar. **Every distribution is a full success** -- (b)-dominant makes it a tracker
                 identity problem, (c)-dominant moves it upstream of association entirely, and a
                 substantial (a) would require me to qualify the "physically impossible" framing I have
                 already reported. Do not merge (d) into another category to sharpen the result.
  n            = 1 clip, 1 shot, the sample size and id coverage you state, 1 labeller -- name every
                 denominator in the verdict line, and name the box population, not "players"
  eye check    = the blind before/after classification IS the measurement, and it is a categorical
                 judgement, not the geometric one G257 bounded at 20 px
  must not move = every threshold, bar and verdict, G233d's published map, G267's retained boxes and span,
                  the court model, the coordinate contract, `src/` and `domains/` (READ and IMPORT ONLY),
                  the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g272_box_jump_visual_classification_2026-09-04.md with the reproduced
count, the sampling description, the committed blind order and verdicts, every before/after render, the
category distribution, the consequence statement, every disk-guard probe with the `du -sm /workspace`
figure, bytes freed and committed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME
COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
