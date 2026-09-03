GAP G196 | sport ncaa_basketball / wnba | worktree a6 | log g196_homography_from_labelled_corners
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ and IMPORT only.
This row does not touch the pipeline at all -- it works from committed labels and committed JPEGs.

**S1 MACHINE: either, and say which.** This is 17 small JPEGs and a 4-point homography solve per
frame; no video decode, no model inference. If you use the pod, fine; if local, it is cheap enough
not to matter. **State where you ran it.** Do NOT launch the `run_clip.py` route.

**S3 DEPENDENCY.** Three landed rows:
  - **G192b**: the existing Hough solver returns `None` on **17 of 17** of these very frames.
  - **G194**: the pipeline therefore falls back to `Rectify1.npy`, and the orchestrator's eye check
    on the committed render shows that projection is **DEGENERATE** -- the court model collapses to a
    single diagonal line across the crowd.
  - **G136**: four-corner geometry is visible in **46.2 pct** of basketball frames (at 66.7 pct
    labeller agreement).

THE QUESTION, and it decides where basketball effort goes next:
**Is the court geometry RECOVERABLE from these frames at all?** If a homography built from
HAND-LABELLED corner points yields a sensible court projection, the ceiling is DETECTION and a
detector is worth building. If even hand-labelled points cannot, something deeper is wrong -- the
court model, the role semantics, or the conditioning -- and building a detector would be wasted.

PREMISES, VERIFIED BY THE ORCHESTRATOR OVER THE WHOLE SET (S2):
  - `docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv` holds 68 rows, all
    `status = target`.
  - **Every one of the 17 frames carries all FOUR distinct roles**: `paint_near_baseline_left_corner`,
    `paint_near_baseline_right_corner`, `paint_near_free_throw_left_corner`,
    `paint_near_free_throw_right_corner` (17 each). Confirmed by counting the whole file.
  - All 68 `source_decode` JPEGs exist. Resolutions are MIXED: 12 frames at 1920x1080, 4 at 1280x720,
    1 at 640x360, and CSV dimensions equal native JPEG dimensions for every frame.
  - The 17 frames span NCAA and WNBA clips.

METHOD:
  1. **State the court model you use and justify it per league.** The four labelled points are the
     paint rectangle corners. You need their real-world coordinates. NCAA and WNBA paint dimensions
     must be stated explicitly with a source, and if they differ you must handle the two leagues
     separately rather than assuming one model. **If you cannot establish the dimensions
     confidently, STOP and say so** -- a wrong court model would silently produce a wrong homography
     and a misleading answer.
  2. Per frame, compute the homography from the 4 labelled image points to the 4 court-model points
     (`cv2.getPerspectiveTransform`, or `findHomography` with exactly 4 points -- note RANSAC is
     meaningless at the minimum, so do not use it and say why).
  3. **Project the full court model back onto the image through the inverse and RENDER it.** For 5
     EVENLY SPACED frames of the 17, state whether a human sees the projected lines landing on the
     painted court: baseline, sideline, free-throw line, three-point arc, centre circle where visible.
  4. Report a numeric sanity check per frame: project the 4 labelled points through the homography and
     back, and report the round-trip residual. **This is a conditioning check, NOT an accuracy claim**
     -- with exactly 4 points the fit is exact by construction and a small residual proves nothing
     about correctness. Say that plainly rather than presenting it as evidence of quality.

**THE HONEST LIMITATION, which you must state rather than discover:** 4 points is the EXACT minimum.
There is no redundancy, no residual to inspect, and no outlier rejection possible. G140's own p90
label repeatability is **11.39 px**, so label noise propagates directly into the matrix. A homography
that looks right in the render is evidence the geometry is recoverable; it is NOT evidence the
labels are accurate enough for production.

**A9:** name each JPEG's full path and native resolution.
**B13:** store per-frame records (the 4 image points, the 4 court points, the 3x3 matrix, the
round-trip residual) in the artifact.

ACCEPTANCE RULE:
  metric        = per-frame homography solved or not; the 5 eye-check verdicts; per-frame round-trip
                  residual as a conditioning check only
  before        = the Hough solver returns nothing on these frames and the static fallback is
                  degenerate; whether the geometry is recoverable AT ALL is unknown
  bar           = NO pass bar. **"The projection lands on the court" means the ceiling is DETECTION.
                  "It does not even from hand labels" means the court model or role semantics are
                  wrong and a detector would be wasted effort.** Both are full successes and the
                  second is more valuable, because it would stop a large investment.
  n             = 17 frames (CONSTRUCT, exhaustive); 5 evenly spaced for the eye check
  eye check     = the 5 renders described above -- this is the deliverable, not the residuals
  must not move = every threshold, bar, verdict, the coordinate contract, `src/` (READ ONLY), the pod
                  daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g196_homography_from_labelled_corners_2026-09-03.md with the court
model and its justification, the per-frame table, the 5 renders, the eye-check verdicts, and a NOT
VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for your harness under `scripts/platformkit/tracking/`, pasted. NEVER a full
pytest.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
