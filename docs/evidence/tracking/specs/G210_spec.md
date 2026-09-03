GAP G210 | sport ncaa_basketball / wnba | worktree a6 | log g210_court_model_fit_to_lines
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: LOCAL, and NO POD.** 17 small JPEGs, classical geometry, no learned weights, no
downloads, no build toolchain. G203 is measuring byte identity on the pod and must not be disturbed.
**This row needs nothing that G208's environmental exclusions blocked** -- that is deliberate.

**S3 DEPENDENCY -- this row exists because of a PATTERN across two landed negatives, not one.**
  - **G205**: classical LSD line intersections -> **0/17 all-four frames, 22/68 corner recall,
    ~1,928 proposals per frame.**
  - **G208**: M-LSD -> **0/17 all-four frames, 2/68 recall, 15.59 proposals per frame.**
  - **Read together: one buries the corners in unusable noise, the other is selective and finds
    almost nothing. Neither is a tuning problem.** A generic line or corner primitive has no way to
    know which intersection is a PAINT corner.
  - **But G205's 22/68 says the LINES ARE THERE.**
  - **G196**: a homography from four hand-labelled corners projects correctly, three-point arc landing
    out-of-sample. Geometry is recoverable; identification is the bottleneck.
  - **G141**: naive local-response corners, 0/68. Do not repeat that shape of approach.
  - **G31**: closed a LEARNED, TRAINED calibration path AT LIMIT for tennis. **This row trains
    NOTHING and fits classically**, so it does not reopen G31.

THE REFRAME, and the question: **stop trying to identify individual corners. Fit the whole COURT MODEL
to the detected line SEGMENTS.** A global fit consumes every line, needs no single corner named, and is
the framing the published broadcast-calibration work uses. **Does fitting the court model to lines beat
0 of 17?**

**LICENCE NOTE, and it is why this row is classical:** PnLCalib is **GPL-2.0**. **Do NOT read, port,
vendor or consult its source.** Implement the fit from the geometry, not from a GPL reference.

METHOD:
  1. **State the court model per league and justify it.** NCAA uses a **12-ft** lane, WNBA a
     **16-ft** lane (rule-book cited in G196). **A single model silently corrupts one league** -- the
     17 frames span both, so you must handle them separately and say which frame is which and how you
     decided.
  2. Detect line segments per frame. **Reuse G205's detector path** so the input is the same line set
     that scored 22/68, and say so; do not introduce a new primitive here -- that would confound the
     reframe with a detector change.
  3. **Fit the court model to the segments globally.** Hypothesise correspondences between detected
     segments and named model lines (baseline, sideline, free-throw line, lane lines), solve the
     homography, and score each hypothesis by **line support** -- how much detected line length the
     projected model explains -- not by corner distance. Search robustly; state the search and its
     bounds. Cap the work: a bounded hypothesis count, stated up front, with the same configuration
     for all 17 frames and **no per-frame tuning**.
  4. **THE LABELS ARE HELD OUT.** G140's four hand-labelled corners per frame are for SCORING ONLY.
     **They must not enter the fit, seed it, filter hypotheses, or select a winner.** State explicitly
     in the memo how you enforced that. **If a label touches the fit, the row is void** -- that is the
     leak this programme has retracted results over before.
  5. Score with **G205's `score_frame`**, unchanged, so the numbers are directly comparable to G205
     and G208.

**HONEST LIMITATIONS you must state rather than discover:** G140's p90 label repeatability is
**11.39 px**, so the 12 px threshold sits at the label noise floor and a pass shows the fit lands in
roughly the right place, not that it is production-accurate. And 17 frames is a small, non-random
construct selected for corner visibility, so **a success here is a lower bound on difficulty, not
evidence of robustness on arbitrary footage.**

ACCEPTANCE RULE:
  metric        = frames where all four labelled roles are within 12 px of the FITTED model's
                  corresponding points, over 17; per-corner error distribution; line-support score per
                  frame; and the per-frame fit/no-fit outcome
  before        = G205 0/17 with 22/68 recall at ~1,928 proposals/frame; G208 0/17 with 2/68 at 15.6
                  proposals/frame; no global model fit has ever been attempted on these frames
  bar           = **>= 1 of 17.** **"Global model fitting also gives 0 of 17" is a FULL SUCCESS** and
                  is the most valuable outcome available, because taken with G141, G205 and G208 it
                  would say the classical route cannot identify this court from lines and would
                  redirect the programme to labelling or to a court-specific learned model with a
                  named justification against G31. Do not tune, do not lower the bar, do not let a
                  label leak in to rescue the row.
  n             = 17 frames (CONSTRUCT, exhaustive), both leagues handled separately
  eye check     = render the fitted court model over 5 evenly spaced frames and say whether a human
                  sees the lines land on the painted court -- the same check G196 used, so the two are
                  directly comparable. Render even if the score is 0.
  must not move = every threshold, every bar and verdict, the 12 px protocol, G205's scorer contract,
                  the coordinate contract, `src/` (READ ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g210_court_model_fit_to_lines_2026-09-03.md with the per-league court
model and its source, the per-frame table, the hypothesis search and its bounds, **an explicit
statement of how the labels were held out of the fit**, the 5 renders, the 11.39 px label floor, and a
NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for the fitting harness, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
