GAP G224 | sport ncaa_basketball / wnba | worktree a3 | log g224_tophat_line_evidence_transfer
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. `domains/tennis/`
and `domains/basketball/` are READ and IMPORT only for this row -- **import their functions, do not edit
them.** Build in `scripts/platformkit/tracking/`.

**S1 MACHINE: RUN LOCALLY. Do NOT use the pod** -- G211 is measuring per-frame cost there and any load
corrupts it. Everything needed is committed: the 17 frames under
`docs/evidence/tracking/g130_recensus/source_decodes/`, the labels at
`docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv`, and G217's artifact.

**WHY THIS ROW EXISTS -- WE HAVE BEEN MEASURING BASKETBALL CALIBRATION ON RAW LSD WHILE A MEASURED-BETTER
LINE-EVIDENCE METHOD HAS BEEN SITTING IN THIS REPO, IN THE TENNIS PATH, THE WHOLE TIME.**

**The orchestrator read both paths and this is the comparison, verified in master:**
  - **Basketball, `domains/basketball/tracking/line_calibration.py:78`, in full:**
    `detected = cv2.createLineSegmentDetector().detect(gray)[0]`
    **Raw LSD straight onto the grayscale frame. No preprocessing, no morphology, no shadow handling.**
    **Every basketball calibration row to date -- G141, G205, G208, G210, G210b, G214, G217 -- rests on
    this line evidence.**
  - **Tennis, `domains/tennis/tracking/court_lines.py:91-92`:**
    `kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))`
    `mask = cv2.inRange(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel), contrast, 255)`
    a **white top-hat**, plus role assignment by **projective cross ratios** (`cross_ratio` at :46-56).
  - **That module's own docstring says the top-hat was a MEASURED fix to exactly the failure mode
    basketball still has**: an absolute brightness mask *"never contained a court line lying in the hard
    shadow that covers half of many main-camera frames, so the right doubles sideline and the near
    baseline vanished from Hough entirely"*, whereas a top-hat keeps *"thin and brighter than its
    surroundings, which a line is in sun or shade, and removes shirts and banners, which are not thin"*.
    It cites `docs/evidence/tracking/tennis_vertical_lever_2026-09-01` and records measured parameter
    choices (kernel 11 beat 15; contrast 45 and 60 for different brightness regimes).

**WHY NOW: G217 (landed tonight) established that this is exactly the lever.** The fitter and court model
contribute **zero** error -- exact lines through the labelled corners give 17/17 at 0.000000 px through
the same unchanged `solve_line_pairs` and `score_frame`. **All of the oracle's 28.841316 px median
max-corner error is DETECTED LINE GEOMETRY**, with the selected detected lines missing the labelled
corners they should pass through by **median 10.234792 px, max 59.693249 px** over 68 selections.
**G217's conclusion was that detection accuracy is the live lever. This row tests the best in-repo
candidate for pulling it.**

THE QUESTION: **does top-hat line evidence reduce the detected-line geometry error on basketball frames,
and does it move the real search off 0/17?**

METHOD:
  1. **Reproduce the RAW-LSD baseline first, unchanged**, through G210b's existing path: real search
     0/17, detected-line oracle 1/17 at 28.841316 px, and the selected-line distances at median
     10.234792 px / max 59.693249 px. **If you cannot reproduce these, STOP and report that.**
  2. **Change EXACTLY ONE THING: the line evidence.** Substitute a top-hat-derived mask for the raw
     grayscale input to line detection, in your own harness, then feed the result through the **SAME
     unchanged grouping, `solve_line_pairs`, and G205 `score_frame` with `TOLERANCE_PX = 12.0`.** Any
     other change voids the comparison. **Do not touch the oracle's selection rule, the court model, or
     any threshold in the scorer.**
  3. **Report both arms side by side on all four measures**: real-search frames-with-all-four-within-12px
     over 17; oracle frames over 17; median and max selected-line distance over 68; and **proposals per
     frame**. **Proposals per frame is a first-class result, not a footnote** -- G205 produced ~1,928
     proposals/frame, which no homography solver can consume however good recall gets, so **a variant
     with better recall and unusable precision is a NEGATIVE result and must be reported as one.**
  4. **State the parameters you used and where they came from.** Tennis measured kernel 11 and contrast
     45/60 **on 720p tennis footage**. **Our 17 frames are MIXED resolution -- 12 at 1920x1080, 4 at
     1280x720, 1 at 640x360 -- and a morphological kernel is a fixed pixel size, so it does not mean the
     same thing at different resolutions. Say how you handled that.** **Try at most a small, declared
     set of parameter values and declare it BEFORE seeing results.** **Do NOT tune per frame** -- one
     fixed configuration across all 17, exactly as G205/G208/G214 required. Per-frame tuning would make
     the number incomparable to every prior row and is the main way this row could produce a fake win.
  5. **Say plainly whether the transfer holds, and be sceptical.** A tennis court is a uniform surface
     with high-contrast white lines; a basketball court is wood, with sponsor logos, painted key fill,
     and many non-court markings that are also "thin and brighter than their surroundings". **A
     plausible outcome is that top-hat raises proposal counts on basketball without improving geometry.**
     Report that if it happens.
  6. **Do NOT change any production module, and do NOT propose a `src/` or `domains/` edit in this row.**
     If the evidence supports a transfer, say so and let a later row own the change.

**EXPLICITLY OUT OF SCOPE, and do not drift into it:** `domains/tennis/tracking/camera_lock.py`
implements drift-checked homography REUSE across cut-bounded segments
(`LOCK_MIN_FRESH_SOLVES = 3`, `DRIFT_CEILING_720P_PX = 5.0`) -- that is the anchor-plus-propagation
architecture G215 and G222 are about, and it is a separate transfer question with its own id. Likewise
tennis's **cross-ratio role assignment** is a second, separable idea. **This row isolates LINE EVIDENCE
only.** Changing two things at once would leave us unable to attribute either.

**HONEST LIMITATIONS to state, not discover:** 17 frames is a small exhaustive construct and the same one
every calibration row has used, so this measures those frames, not a rate. G140's p90 label repeatability
is **11.39 px**, so the 12 px threshold sits at the label-noise floor and the baseline median line error
of 10.23 px is already BELOW it -- **a modest improvement cannot be distinguished from label noise, and
you must say so rather than claiming a small win.** The tennis parameters were measured on different
footage, a different surface and a different resolution.

ACCEPTANCE RULE:
  metric        = raw-LSD baseline versus top-hat arm on: real-search all-four over 17; oracle all-four
                  over 17; median and max selected-line distance over 68 selections; and proposals per
                  frame -- one fixed configuration, declared in advance
  before        = every basketball calibration row rests on raw `createLineSegmentDetector` on grayscale;
                  the tennis top-hat evidence method has never been tried on basketball frames; G217
                  attributes the entire oracle error to detected line geometry
  bar           = NO pass bar. **"Top-hat does not improve basketball line geometry" is a FULL SUCCESS**
                  and retires the cheapest remaining in-repo option, which is worth knowing before anyone
                  funds a learned detector. Do not tune per frame, do not add a variant after seeing
                  results, and do not report an improvement you cannot separate from the 11.39 px label
                  floor.
  n             = 17 frames (CONSTRUCT, exhaustive) x 4 roles = 68 selections, per arm
  eye check     = for 3 frames, render the raw-LSD evidence and the top-hat evidence side by side with
                  the labelled corners overlaid; commit them
  must not move = every threshold, `TOLERANCE_PX`, the 12 px protocol, G205's scorer contract,
                  `solve_line_pairs`, the oracle's selection rule, the court model, the coordinate
                  contract, every bar and verdict, `src/` (READ ONLY), `domains/` (READ and IMPORT
                  ONLY -- no edits), the pod (DO NOT USE IT), the corpus
EVIDENCE: docs/evidence/tracking/g224_tophat_line_evidence_transfer_2026-09-04.md with the baseline
reproduction, the declared-in-advance parameter set, the two-arm table on all four measures, proposals
per frame, the renders, an explicit treatment of the 11.39 px label floor and the mixed-resolution
kernel issue, a plain verdict on whether the transfer holds, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
