GAP G215 | sport wnba | worktree a5 | log g215_temporal_homography_propagation
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ and IMPORT only. Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: RUN ON THE POD.** You need real video frames. **DISK GUARD, BINDING** -- the pod hit
`Disk quota exceeded` tonight and `df` is NON-AUTHORITATIVE (it reports the whole cluster filesystem
against a 50 GB volume cap). **Before writing anything, do a small real write test (`dd` a few MB,
then remove it) and record `du -sm /workspace/nba-ai-system/data`. If it fails, STOP and report.**
Extract only the frames you need, keep them small, and **delete every temporary artifact at the end,
reporting bytes freed.** Never kill, restart or deploy over the daemon or keeper. Delete no corpus
source.

**WHY THIS ROW EXISTS -- five rows have exhausted the per-frame approach and this reframes it.**
  - **G210b**: with an untruncated search, real search 0/17; **ORACLE control 1/17 at ~28.8 px median**.
    **Because the oracle assumes PERFECT line selection, a better line detector cannot lift this much.
    The ceiling is the difficulty of a four-point homography at 12 px on a single frame.**
  - **G205** 0/17 (22/68 recall, ~1,928 proposals/frame), **G208** M-LSD 0/17 (2/68, 15.59/frame),
    **G214** reproduced M-LSD exactly on the pod, **G141** 0/68. The route is thoroughly measured.
  - **G196**: a homography from four HAND-LABELLED corners projects correctly, with the three-point arc
    landing OUT-OF-SAMPLE. **Geometry is recoverable from a good frame.**
  - **G207**: `coordinate_contract` is the first failure on **29 of 32** pod rows. **Calibration gates
    91 pct of the entire ledger**, so this is not one sport's depth problem.

**THE REFRAME: every row so far solved calibration PER FRAME on 17 isolated stills. Broadcast systems
do not do that.** A camera pans and zooms smoothly, so a clip needs **one** good calibration plus
frame-to-frame propagation. **We do not need to solve every frame. We need one frame per clip and a
propagation that holds.**

THE QUESTION: **starting from a known-good calibration, how far does frame-to-frame homography
propagation stay valid on a real broadcast clip, and what breaks it?**

METHOD:
  1. Take a clip with a G140-labelled frame (`wnba__wnba_01.mp4` is the reference; A9: 2,931,985,407
     bytes, 1920x1080, 174,430 frames). **Build the seed homography from the four HAND-LABELLED
     corners exactly as G196 did** -- reuse its `court_points_for_sport` so the court model and the
     league lane width (NCAA 12 ft vs WNBA 16 ft) are identical and the two rows compare.
  2. Extract a contiguous run of frames forward from the seed frame. **State the stride and the run
     length up front.** A few hundred frames is enough; do not decode the whole clip.
  3. Propagate the homography frame to frame by estimating inter-frame motion from image content
     (feature matching or optical flow -- **state which, and why**), composing it onto the seed. **Use
     no labels beyond the seed frame.**
  4. **Report drift as a function of distance from the seed**, not a single number: at intervals,
     project the court model through the propagated homography and measure how far the projected paint
     corners have moved from where a fresh composition would put them, plus any reprojection residual
     your method exposes. **Name the ELIGIBLE DENOMINATOR as the frames you actually propagated
     through.**
  5. **EYE CHECK IS THE DELIVERABLE HERE**, because there is no per-frame ground truth beyond the seed:
     render the projected court at the seed and at several increasing distances, and state plainly at
     what distance a human can see it come off the painted court. Commit those renders.
  6. **Report what breaks it.** Shot cuts, replays, heavy zoom, crowd-only frames -- say which occur in
     your run and what each does to the propagation. **A propagation that survives 50 frames and dies
     at a shot cut is a USEFUL result** and tells us the unit of work is a camera shot, not a clip.

**HONEST LIMITATIONS you must state rather than discover:**
  - **There is no ground truth after the seed frame.** Drift measured against a composition is
    SELF-CONSISTENCY, not accuracy; the renders are what carry the accuracy claim, and they are
    single-labeller eye judgements. Do not present a small numeric drift as proof of correctness.
  - The seed uses hand labels, so this row measures PROPAGATION only. It does **not** show we can
    obtain the seed automatically -- G210b's oracle says roughly 1 frame in 17 is solvable even with
    perfect lines, and that remains the open half of the problem.
  - The route is non-deterministic (G189/G195/G198), but this row does not run the route; say so.

ACCEPTANCE RULE:
  metric        = drift versus distance from the seed, over the frames actually propagated; the
                  distance at which the eye check fails; the causes of failure that occurred
  before       = calibration is solved per-frame or not at all; the per-frame ceiling is 1/17 with a
                  perfect line oracle; propagation has never been measured
  bar           = NO pass bar. **"Propagation dies within N frames" is a FULL SUCCESS** and would say
                  per-shot re-calibration is mandatory, which is a design answer. **"It holds across
                  hundreds of frames" is the other full success** and would mean one solved frame per
                  camera shot is enough, changing what the detection problem has to deliver. Do not
                  tune to make it look better.
  n            = one seeded run on one clip (EXISTENCE and decay shape, not a rate across clips)
  eye check    = the renders described above -- this is the deliverable
  must not move = every threshold, bar and verdict, the court model, the coordinate contract, `src/`
                  (READ ONLY), the pod daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g215_temporal_homography_propagation_2026-09-03.md with the seed
construction, the drift-versus-distance table, the renders, the failure causes, bytes freed on
cleanup, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for the propagation harness, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
