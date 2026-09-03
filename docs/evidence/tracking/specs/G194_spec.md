GAP G194 | sport wnba | worktree a6 | log g194_which_M1_does_the_pipeline_use
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ, IMPORT and wrap it IN
YOUR OWN MEASUREMENT PROCESS only. Edit nothing, deploy nothing into the pod checkout (B5).

**S1 MACHINE: RUN ON THE POD.** RTX 3090, 24 GB. The local box is 16 GB with other lanes live.

**S3 DEPENDENCY.** G192b (ACCEPT, landed): `detect_court_homography` returned `None` on **17 of 17**
G140-labelled frames across **0 of 51** calls -- frames selected for paint-corner visibility. So the
direct solver solves nothing on the best available basketball frames.

THE CONTRADICTION THIS ROW RESOLVES. `scripts/run_clip.py:581` states in its own comment that a
per-clip homography "is solved in memory and discarded". G192b shows the solver returning nothing.
**Both cannot be comfortably true.**

PREMISES, VERIFIED BY THE ORCHESTRATOR BEFORE DISPATCH (S2) -- quoted, re-confirm cheaply:
  - `src/tracking/court_detector.py:7` -- the module docstring says it is "Used by
    `unified_pipeline._build_court()` to replace the static Rectify1.npy".
  - `src/tracking/court_detector.py:206` -- on failure it prints
    `[court_detector] detection failed - fallback to Rectify1.npy`.
  - `src/pipeline/unified_pipeline.py:885-887` -- a comment marked IMPORTANT states that M1
    (Rectify1.npy) "is calibrated for the Short4Mosaicing panorama (3698x500px)" and that "a
    per-video broadcast frame (1280x660) would break M1 because M1 maps pano-coordinate-space -> 2D
    court; using a different pano invalidates" it.
  - `unified_pipeline.py:708` assigns `self.map_2d, self.M1 = self._build_court(...)`, and
    `:698-702` maintains M1 recovery state including `_M1_raw_clip` and `_M1_failed_attempts`.

**THE HYPOTHESIS, stated so you can falsify it rather than confirm it:** on basketball broadcast
clips the detector fails, the pipeline falls back to `Rectify1.npy`, and that fallback matrix is
documented by the code itself as invalid for a per-video broadcast frame. If true, basketball's
court projection has never rested on a valid per-clip homography, which would also explain why
persisted `ft_x/ft_y` is an affine rescale and why G189 observed survivor coordinates outside the
frame (x1 = 2979 on a 1920-wide frame; y1 = -35).
**If the evidence says otherwise, report that.** "The detector succeeds inside the full pipeline even
though it failed on the G140 stills" is a FULL SUCCESS and an important correction to G192b.

METHOD:
  1. Instrument in your measurement process only: wrap `_build_court` and `detect_court_homography`
     to record, per invocation, whether a matrix was returned and by WHICH branch (fresh solve,
     recovery, or `Rectify1.npy` fallback). G182's wrap-in-process pattern is the sanctioned one.
  2. Run the bounded route once on the pod:
     `python3 scripts/run_clip.py --video data/footage_corpus/wnba__wnba_01.mp4 --frames 1200
      --no-show --skip-features --data-dir <fresh>`
  3. Report: which branch supplied the M1 actually used; how many fresh-solve attempts were made and
     how many succeeded; whether `Rectify1.npy` was loaded; and the final M1 matrix values.
  4. **Then answer the load-bearing question:** is the M1 used for projection the SAME matrix as
     `Rectify1.npy`? Compare element-wise and say so plainly. If it is, the fallback fired and the
     code's own IMPORTANT comment says that matrix does not apply to this footage.
  5. Also record whether `_M1_failed_attempts` ever incremented and what `_M1_raw_clip` held.

**A9:** `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes,
1920x1080, 174,430 frames. NOT the 1280x720 `g130_recensus/` derivative.
**A11:** record the SHA-256 of `unified_pipeline.py`, `court_detector.py` and `advanced_tracker.py`
as they exist on the pod.
**B11:** the route is non-deterministic (G189). Run the instrumented route **3 times** and report
whether the BRANCH TAKEN is stable, even if the row counts are not. Branch stability is the claim
here, not row counts.
**B13/Q9:** store per-invocation records in the artifact, not a summary verdict.

ACCEPTANCE RULE:
  metric        = which branch supplied M1, per run; fresh-solve attempt and success counts; whether
                  the used M1 equals `Rectify1.npy` element-wise
  before        = the solver returns None on 17/17 stills, while run_clip.py:581 claims a per-clip
                  homography is solved and discarded; the pipeline's actual branch is unknown
  bar           = NO pass bar. Either answer is a full success. **Do not conclude the fallback is
                  wrong for this footage from the code comment alone** -- report what the code says
                  AND what you measured, and keep them separate.
  n             = 3 instrumented runs of one clip (EXISTENCE and branch stability)
  eye check     = if and only if a matrix is used, render 2 evenly spaced frames with the court model
                  projected through it and say whether the lines land on the painted court
  must not move = every threshold, the coordinate contract, every bar and verdict, `src/` (READ
                  ONLY), the pod daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g194_which_M1_2026-09-03.md with the per-run branch table, the
matrix comparison, the code hashes, any renders, and a NOT VERIFIED list. Commit BEFORE reporting.
TEST: a per-file test for any harness added under `scripts/platformkit/tracking/`, pasted. NEVER a
full pytest.
POD: run there; never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
