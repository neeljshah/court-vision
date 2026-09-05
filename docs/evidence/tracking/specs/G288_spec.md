GAP G288 | sport wnba | worktree a5 | log g288_describe_graphic_and_floor_crops
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO DECODE, NO DISK GUARD, NO HOLD RULE. START IMMEDIATELY.**
The pod is saturated by six peer worktrees. Committed inputs, already here:
  - G273's 72 crops: `docs/evidence/tracking/g273_detector_precision_blind_sample_artifact/blind_renders/`
  - G287's verdicts: `docs/evidence/tracking/g287_unconditioned_footpoint_content_artifact/blind_verdicts.csv`
    (columns `order, blind_filename, category, detail`)

**READ THE G287 MEMO, THE G287-CORRECTS-G286-FRAMING ROW AND THE G286-SPATIAL-CHECK ROW FIRST.**

**WHY THIS ROW EXISTS -- A ONE-WORD GAP IS BLOCKING A MECHANISM CLAIM.**
G287 classified **13 / 72 = 0.181** of unconditioned footpoints as **"(d) broadcast graphic or score
ticker"** and **17 / 72 = 0.236** as **"(c) bare court or floor"**. **Its `detail` free-text column was
required only for category (f), so all 13 (d) rows and all 17 (c) rows are blank.**

**That single missing description is what stops the mechanism being stated.** A spatial histogram of all
30,071 committed detections found the **classic overlay regions essentially empty** -- top band
25/30,071 and bottom band 19/30,071, both 0.001 -- which suggests **"graphic" means COURT-SURFACE
DECORATION (painted sponsor logos, centre-circle artwork, floor branding) rather than overlay furniture.**
**That is a hypothesis in two landed documents and it is unresolved.** **Thirty crops, already rendered
and committed, can settle it.**

THE QUESTION: **what are the "graphic" and "bare floor" crops actually showing?**

METHOD:
  1. **SELECT EXACTLY THE CROPS G287 LABELLED (c) OR (d)** -- 17 and 13 by its committed verdicts. **State
     both counts and confirm they match; report yours if they differ.** **Do not re-render or re-crop**;
     use the committed JPEGs.
  2. **THIS IS A DESCRIPTIVE REFINEMENT OF TWO EXISTING CATEGORIES, NOT A RE-CLASSIFICATION.** **Do NOT
     change any G287 verdict.** If a crop looks mis-categorised, **record that in free text and leave the
     verdict alone** -- report it as a label-stability observation, do not silently correct it.
  3. **FOR EACH (d) CROP, record which of these the centre cross sits on**, plus one free-text line:
     **(d1) an OVERLAY graphic drawn over the picture** -- score bug, lower-third ticker, transition wipe;
     **(d2) COURT-SURFACE decoration** -- painted logo, sponsor branding, centre-circle art, painted
     lettering on the floor;
     **(d3) a PHYSICAL object at courtside** -- signage board, LED perimeter hoarding, banner;
     **(d4) CANNOT TELL which.**
  4. **FOR EACH (c) CROP, record which of these the centre cross sits on**, plus one free-text line:
     **(c1) PLAIN unmarked court surface; (c2) a PAINTED COURT LINE or arc; (c3) painted floor decoration
     that is not a line; (c4) floor OUTSIDE the court of play; (c5) CANNOT TELL.**
  5. **FREE TEXT IS MANDATORY ON EVERY ROW**, one short line each. **The graphics category only exists at
     all because G286 carried a free-text field**; that is the whole reason this row is possible.
  6. **REPORT BOTH BREAKDOWNS AND ANSWER IN ONE SENTENCE: is the "graphic" category overlay furniture, or
     court-surface decoration, or mixed?** **If (d1) dominates, my spatial-histogram reasoning was wrong
     and I want that said plainly.** **If (d2) or (d3) dominates, the mechanism sentence in the ledger,
     the synthesis and the evidence packet should read "court decoration or courtside signage" and I will
     change all three.**
  7. **ALSO SAY whether (c2) is a material share** -- footpoints landing on painted court lines would
     connect this to the separate finding that court decoration is one of the measured causes stopping
     calibration from generalising.
  8. **Do NOT re-detect, re-render, re-sample, or touch `src/`.** Propose no filter, threshold or retrain,
     and do not move any bar.

**LIMITS to state:** 30 crops from ONE shot of ONE clip, ONE labeller, **the same labeller as G273 and
G287**, so this is descriptive refinement and carries no independent validation. **A footpoint is a
POINT** -- this row says what is at it, never what a bounding box contained. **Per G278 the span is
measurably friendlier than the clip (0.836 against 0.656, p = 0.0078): NOT clip-wide.** The population is
detector-box observations, not authenticated players.

ACCEPTANCE RULE:
  metric        = the selected 17 and 13 crops confirmed against G287's committed verdicts; the (d1)-(d4)
                  and (c1)-(c5) breakdowns with counts; mandatory free text on every row; the
                  one-sentence answer on what "graphic" means; and the (c2) painted-line share
  before        = 0.181 of unconditioned footpoints are "graphic or ticker" and 0.236 "bare floor", with
                  every detail field blank, so the mechanism cannot be stated
  bar           = **NO pass bar.** **(d1)-dominant refutes my spatial reasoning and I want it stated
                  plainly. (d2) or (d3)-dominant confirms it and changes three landed documents. A large
                  (d4) or (c5) means the crops cannot answer it, which is also a full success.**
  n             = 30 crops, 1 clip, 1 shot, 1 labeller -- name every denominator in the verdict line
  eye check     = the description IS the measurement; it is coarse and categorical at full crop
                  resolution, not a geometric judgement
  must not move = G287's committed verdicts and categories, G273's crops and verdicts, G286's counts,
                  every threshold and verdict, `src/` and `domains/`
EVIDENCE: `docs/evidence/tracking/g288_describe_graphic_and_floor_crops_2026-09-04.md` with both
breakdowns, every free-text line, the one-sentence answer, any label-stability observations recorded under
step 2, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.**
TEST: one per-file test for any harness added, pasted. **NEVER a full pytest.**
COMMIT: explicit pathspec, no push, report the sha. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
