GAP G205 | sport ncaa_basketball / wnba | worktree a6 | log g205_zero_shot_corner_probe
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build any harness
in `scripts/platformkit/tracking/`.

**S1 MACHINE: LOCAL, and NO POD.** This is 17 small JPEGs and CPU-scale line/corner primitives. The
pod is running G203, which measures byte identity and must not share the machine. **Do not launch the
`run_clip.py` route.** If you believe you need the pod, stop and say why instead.

**S3 DEPENDENCY -- four landed rows, and this row exists because of the gap between two of them.**
  - **G196**: a homography from four HAND-LABELLED paint corners projects correctly on all 17 frames,
    with the three-point arc landing out-of-sample. **So the geometry is recoverable and the ceiling
    is DETECTION.**
  - **G192b**: the existing classical Hough solver returns `None` on **17 of 17** of these very
    frames, across 0 of 51 calls.
  - **G141**: a naive local-response corner detector scored **recall 0/68, precision 0/1,700** at
    12 px. **That closes THAT detector, not every corner method** -- which is exactly what this row
    tests.
  - **G31**: closed a LEARNED calibration path AT LIMIT for tennis (PCK@7px 0.077, zero frames solved
    that the classical did not). **This row is deliberately ZERO-SHOT and trains nothing**, so it does
    not reopen G31; if you find yourself proposing training, stop -- that is a different row that must
    cite G31 and say what is different.

THE QUESTION: **does any licence-clean, zero-shot primitive propose the four paint corners on these
frames at all?** This is the cheapest decisive question in the basketball programme: hours, local, no
labelling, no training, no GPU, no deploy.

PREMISES, VERIFIED BY THE ORCHESTRATOR OVER THE WHOLE SET (S2):
  - `docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv` holds **68 rows, all
    `status = target`**, and **every one of the 17 frames carries all FOUR distinct roles**
    (`paint_near_baseline_left_corner`, `paint_near_baseline_right_corner`,
    `paint_near_free_throw_left_corner`, `paint_near_free_throw_right_corner`), 17 each.
  - All 68 `source_decode` JPEGs exist. Resolutions are **MIXED**: 12 frames at 1920x1080, 4 at
    1280x720, 1 at 640x360, and CSV dimensions equal native JPEG dimensions for every frame. **Handle
    the mixed resolutions explicitly; do not assume 1080p.**
  - The 17 frames span NCAA and WNBA clips.

CANDIDATES -- all must be licence-clean, and **state each licence in the memo**:
  ELSED (Apache-2.0); DeepLSD / HAWP / M-LSD (MIT or Apache code, Wireframe-trained weights);
  KpSFR (MIT, soccer weights, run purely to see whether the architecture proposes anything on a
  court); and classical corner refinement seeded by G134's stable line groups.
  **If a candidate cannot be obtained without a network fetch you cannot make, or its licence is not
  clearly permissive, SKIP it and say so.** A partial candidate list with honest exclusions is a
  correct result. **Do not vendor GPL code into this repo.**

METHOD -- use G141's protocol EXACTLY so the two rows compare:
  1. Per candidate, per frame, produce corner proposals. No per-frame tuning, no per-frame threshold
     picking -- one fixed configuration per candidate across all 17 frames, and state it.
  2. **PRIMARY metric:** frames where **all four labelled roles** are matched within **12 px**.
     Denominator **17** (CONSTRUCT, exhaustive).
  3. **SECONDARY:** per-corner recall over **68**, and precision over the number of proposals, the
     identical protocol to G141.
  4. Report a per-candidate, per-frame table.

**THE HONEST LIMITATION you must state rather than discover:** G140's own p90 label repeatability is
**11.39 px**, so a 12 px match threshold sits essentially AT the label noise floor. That makes this a
GENEROUS bar, not a strict one. A candidate that fails at 12 px has failed comfortably; a candidate
that passes at 12 px has NOT been shown accurate enough for production, only shown to propose
something in the right place. Say this plainly in the memo rather than presenting 12 px as a quality
standard.

ACCEPTANCE RULE:
  metric        = frames with all four roles within 12 px, over 17; plus per-corner recall over 68 and
                  precision over proposals, per candidate
  before        = G141 scored 0/68 recall and 0/1,700 precision with one naive detector; G192b solved
                  0 of 17 frames with the classical Hough path; whether ANY zero-shot primitive
                  proposes these corners is unknown
  bar           = **>= 1 of 17 for any candidate.** **STOP CONDITION: 0 of 17 for EVERY candidate
                  closes the ZERO-SHOT corner route AT LIMIT** -- that is a FULL SUCCESS and saves a
                  large investment. **It does NOT close labelling and must not be written as closing
                  it.** Do not tune, do not lower the bar, do not add a candidate after seeing results
                  to rescue the row.
  n             = 17 frames (CONSTRUCT, exhaustive) x however many candidates you can honestly obtain
  eye check     = for the best-scoring candidate, render proposals against labels on 5 evenly spaced
                  frames and say what a human sees. If every candidate scores 0, render 5 frames of
                  the closest candidate anyway so the failure mode is visible.
  must not move = every threshold, every bar and verdict, the 12 px protocol, the coordinate contract,
                  `src/` (READ ONLY), the pod daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g205_zero_shot_corner_probe_2026-09-03.md with the per-candidate
per-frame table, licences, the fixed configuration used for each candidate, the renders, an explicit
statement of the 11.39 px label floor, honest exclusions, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added under `scripts/platformkit/tracking/`, pasted. NEVER a
full pytest. **If a commit grows an allowlisted file, raise its entry in
`tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12) and run that rail test.**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
