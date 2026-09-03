GAP G192b | sport ncaa_basketball / wnba | worktree a6 | log g192b_score_existing_homography
**MEASUREMENT ONLY. Change NO code.** No bar, threshold, gate, solver constant, coordinate contract
or verdict. `src/` is HUMAN-GATED: you may READ it and CALL it, never edit it.

**S1 MACHINE: RUN ON THE POD.** The solver may invoke LoFTR/SIFT and load models; the local box is
16 GB with other lanes live and two RAM guards have fired today. The pod has an RTX 3090 and 24 GB.
The inputs are 17 small JPEGs, so this is cheap either way -- run it on the pod anyway.

**HISTORY: G192 (this row's first dispatch) was FALSIFIED on the orchestrator's own bad premise --
it asserted all decodes were 640x360, which described 1 of 17 frames. That is corrected above. Do not
re-stop on resolution; it is now stated correctly. See `g192_score_existing_homography_2026-09-03.md`.**

**S3 DEPENDENCY.** This row is step 2 of the sequencing adjudicated in
`docs/evidence/tracking/G_ADJUDICATION_fable_review_2026-09-03.md`. Read that file first. It
established, and the orchestrator re-verified by reading the code:
  - `scripts/run_clip.py:580-585` states in its own comment that persisted `ft_x/ft_y` are the image
    fraction **affinely rescaled**, "NOT a homography, even though a per-clip one is solved in memory
    and discarded."
  - The solver exists at `src/pipeline/unified_pipeline.py:330, 708, 1034` (`detect_court_homography`,
    SIFT or LoFTR, with a static `Rectify1.npy` fallback) and the projection at
    `src/tracking/advanced_tracker.py:1425`.
  - **So basketball's coordinate-contract failure may be PLUMBING, not a calibration gap.** Nobody has
    ever measured whether the solved homography is any good. That is this row, and only this row.

**DO NOT propose or build a learned keypoint model.** G31 (`RESULTS_LEDGER.md:55`) already tried one
and it is CLOSED AT LIMIT: PCK@7px 0.077 and 0.035, median error 17.4 px, and "Frames solved by the
model AND NOT by the classical: ZERO on both folds." Any row proposing a learned calibrator must cite
G31 and explain what is different. This row is not that row.

PREMISES, VERIFIED BY THE ORCHESTRATOR BEFORE DISPATCH (S2). Re-confirm cheaply; if any is false,
STOP and report FALSIFIED:
  - `docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv` holds **68 target rows**
    over **17 distinct frames** across 11 clips, columns `audit_id, clip, source_frame, slot, role,
    x_px, y_px, image_width, image_height, annotation_pass, source_decode, status`.
  - Every target's `source_decode` JPEG EXISTS: 68 of 68 resolve under
    `docs/evidence/tracking/g140_corner_targets/`. **This matters** -- most of the 11 source VIDEOS
    were deleted (G183), so the committed decodes are the only surviving input. Use them; do not go
    looking for the videos.
  - **RESOLUTION IS MIXED. The first dispatch got this wrong and the lane correctly STOPPED.**
    Recounted over the whole file by both the lane and the orchestrator:
      1920x1080 -> 48 targets over 12 frames
      1280x720  -> 16 targets over 4 frames
      640x360   ->  4 targets over 1 frame
    **CSV `image_width`/`image_height` AGREE with the native JPEG dimensions for all 17 frames --
    zero mismatches.** So every frame's labels are already in ITS OWN native pixel space.
  - **SCORE EACH FRAME AT ITS NATIVE RESOLUTION. Do NOT resize, do NOT rescale labels, do NOT pool
    across resolutions without saying so.** Report the pooled figures AND a per-resolution
    breakdown, because a 640x360 frame and a 1920x1080 frame are not comparable error scales:
    the same physical mis-registration is 3x more pixels at 1080p. If you pool, state the caveat.
  - Roles are paint corners (e.g. `paint_near_baseline_left_corner`).

THE QUESTION: **how far off is the homography the pipeline already solves, measured against G140's 68
targets, and is it inside the label noise floor?**

METHOD:
  1. For each of the 17 frames, call the EXISTING `detect_court_homography` route on its decode.
     Read `docs/evidence/tracking/g119_paint_corner_detector_2026-09-02.md` first -- G119 specifies a
     scoring procedure intended to consume this CSV unchanged. Follow it; if it does not fit, say
     exactly why and what you did instead.
  2. Project each labelled court-model corner through the solved homography and report the pixel
     error against the labelled `x_px, y_px`.
  3. Report per-frame and pooled: median error, p90, and the count of targets inside 11.39 px.

THE FLOOR, and it binds your conclusion:
  - G140's own **p90 label repeatability is 11.39 px**, from a census with **66.7 pct blind
    agreement**. **You cannot claim the solver is better than the labels.** An error at or under
    11.39 px means "indistinguishable from label noise", NOT "accurate".
  - 17 frames is an EVALUATION set, not a training set, and 68 targets is the whole of it. State
    `n = 68 targets over 17 frames (CONSTRUCT, exhaustive)` and name any target you exclude and why.

MANDATORY:
  - **B11 REPEAT:** run the solver **3 times per frame in fresh processes** and report whether the
    homography is stable. The route was measured non-deterministic (G189, n=3 spread 9 pct on the
    full pipeline); whether the SOLVER specifically is stable is unknown and is a finding either way.
  - **A9:** name each input decode's full path and its 640x360 resolution in the memo.
  - **B13/Q9:** store PER-TARGET records (frame, role, labelled px, projected px, error) in the
    artifact, not just summary statistics.
  - **A11 CODE IDENTITY:** record the SHA-256 of `unified_pipeline.py` and `advanced_tracker.py` as
    they exist on the machine you run on. The pod is not a git checkout and its files have drifted
    from master before.
  - Report how many of the 17 frames the solver FAILS to solve at all. That count is as important as
    the error on the ones it solves, and it must not be silently dropped from the denominator (B1).

ACCEPTANCE RULE:
  metric        = per-target reprojection error against the 68 labels; median, p90, count within
                  11.39 px; frames where the solver returned nothing; solver stability over 3 runs
  before        = basketball persists an affine rescale while discarding a solved homography whose
                  quality has never been measured
  bar           = NO pass bar. **"The existing homography is bad" is a FULL SUCCESS** and closes the
                  cheap path, sending the programme to step 3 with that settled. "It is within the
                  label floor" is the other full success and would mean basketball becomes scorable
                  by PERSISTING what is already computed, with no new model.
  n             = 68 targets over 17 frames (CONSTRUCT, exhaustive)
  eye check     = render 5 EVENLY SPACED frames of the 17 with labelled corners and projected corners
                  in distinct colours, and say whether a human would call them the same point
  must not move = every threshold and solver constant, the coordinate contract, every bar and
                  verdict, `src/` (READ ONLY, human-gated), the pod daemon and keeper, the corpus
                  (delete NOTHING -- 10 reader-required sources were already lost, G183)
EVIDENCE: docs/evidence/tracking/g192_score_existing_homography_2026-09-03.md with the per-target
table, the pooled statistics against the 11.39 px floor, the unsolved-frame count, the stability
result, the 5 renders, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness you add under `scripts/platformkit/tracking/`, pasted. NEVER a
full pytest.
POD: read-only apart from running your own bounded measurement there. Never kill, restart or deploy
over the daemon or keeper; do not wait on the daemon.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
