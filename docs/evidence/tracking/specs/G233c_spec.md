GAP G233c | sport ncaa_basketball | worktree a5 | log g233c_seed_gate_reindexed
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. Build
in `scripts/platformkit/tracking/`. **Change NO label file** -- `corner_pixel_targets.csv` and every
still under `g130_recensus/source_decodes/` are READ ONLY.

**HELD UNTIL A POD LANE IS FREE.** **Check first and say in your memo that you checked and when you
began.** The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and
`foundry_runner` are PERMANENT residents and the load floor -- never wait for them, never kill or
restart them.

**READ `docs/evidence/tracking/specs/G233b_spec.md` FIRST. This row is G233b with ONE correction: the
frame index.** Everything else -- the clip, the labels, the 3.0 scale, the NCAA 12-foot lane, the hard
distance-zero render gate -- is inherited unchanged.

**WHY THIS ROW EXISTS -- TWO SEEDED ATTEMPTS FAILED ON PROVENANCE AND THAT IS NOW FIXED.**
  - **G233** paired G140 labels from clip `wnba__wnba_01_1080p` with `wnba__wnba_01.mp4`. Different
    clips; no `_1080p` file exists in the corpus. My spec error.
  - **G233b** used the one identifier-matched clip and still FAILED its seed gate -- the projected court
    ran through the seating and baseline lettering. **Cause: the committed still is not the frame it is
    named for.**
  - **G236 then found it. The still `..._IB-_u4gW3ds__s14__f028171.jpg` is at ZERO-BASED FRAME 46154 of
    `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4`, an index delta of +17,983.** The match is a
    dramatic outlier, not a nearest neighbour: refined 64x36 grayscale MAD **1.944878** against a
    whole-scan median of **53.049913** (ratio 0.0367, far inside the 0.5 separation bar), from a scan of
    **205,444 of 205,444 frames**. Frame-accurate colour MAD is **6.358071 at 46154** versus **61.625894
    at 28171**.

**SO THE GEOMETRY HAS NEVER ACTUALLY BEEN TESTED. G196 says four hand-labelled corners project correctly
with the arc landing out-of-sample; G222 says direct-to-seed propagation holds across all 1,200 frames
tested at a flat 0.26-0.38 px reprojection residual. This row finds out whether that works on a real
basketball clip when the seed is finally pointed at the right frame.**

**THE VERIFIED SEED PARAMETERS:**
  - **Video:** `/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4`
    -- 1920x1080, `nb_frames=205444`, `avg_frame_rate=30000/1001`.
  - **Seed frame: 46154, ZERO-BASED.** **Decode it frame-accurately and say how** -- `ffmpeg -ss` before
    `-i` fast-seeks to a keyframe and is NOT frame-exact. G233b used sequential
    `cv2.VideoCapture.read`; G236 used `ffmpeg select=eq(n,index)`. Either is fine; state which.
  - **Labels, recorded at 640x360, so multiply every coordinate by exactly 3** (1920/640 = 1080/360 =
    3.0): `paint_near_baseline_left_corner (38,223)`, `paint_near_baseline_right_corner (39,289)`,
    `paint_near_free_throw_left_corner (274,224)`, `paint_near_free_throw_right_corner (273,282)`,
    scaling to **(114,669), (117,867), (822,672), (819,846)**. **Show the scaled values you used.**
  - **Sport `ncaa_basketball`, so `court_points_for_sport("ncaa_basketball")` -- the 12-foot lane, NOT
    WNBA's 16-foot.**
  - **Sanity check available to you for free: G236 committed the matched frame image. Compare your
    decoded frame 46154 against it before building anything** -- if they differ, stop.

**HARD GATE, UNCHANGED FROM G233b AND IT IS THE POINT OF THE ROW: RENDER THE PROJECTED COURT ON THE SEED
FRAME AND REPORT PASS OR FAIL IN ONE LINE BEFORE ANYTHING ELSE.** If it does not land on the painted
court at distance 0, STOP -- do not propagate, do not project detections, do not compute an in-court
fraction. **G233b's gate saved a whole propagation run; keep it.**

METHOD (only on a PASS):
  1. Propagate direct-to-seed with **G222's landed harness unchanged**
     (`scripts/platformkit/tracking/g222_direct_to_seed_propagation.py`) over a stated span; report drift
     and matched-feature counts versus distance, as G222 did.
  2. Project detected player feet to court feet and report the **fraction inside the 94 x 50 ft court
     versus distance from the seed**, with the outside-distance distribution, using **G230's method and
     vocabulary**. **Prefer importing the detector directly** -- `run_clip` emits zero rows (G211b) and
     `cv2.findHomography` was never even reached in a 40-frame probe.
  3. **Render at several distances; state where it comes off the court. Commit the renders.**
  4. **Report the horizon in labels-per-hour** with the arithmetic and its assumptions.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~32,330 MB of 50,000), STOP and report if it fails.**
Delete every temporary artifact and report bytes freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** **this CONSUMES A HAND LABEL and is NOT automatic
calibration** -- the automatic half remains 0/17 and this row does not change it. **Plausibility is
NECESSARY, NEVER SUFFICIENT**: an in-court fraction includes officials, bench and spectators, exactly as
G233 warned and G239 showed at a median of 20 detections per frame against ten players. One clip, one
seed, one camera. G222's horizon was measured on IMAGE features on a DIFFERENT clip; do not assume it
transfers. G140's p90 label repeatability is 11.39 px and these are single-source eye labels.

ACCEPTANCE RULE:
  metric        = the seed-render PASS/FAIL at distance 0, stated first; then, only on PASS, drift and
                  matched features versus distance, the in-court fraction with its outside distribution,
                  the renders, and the labels-per-hour arithmetic
  before       = two seeded attempts failed on provenance; the geometry has never been tested on a
                 correctly-indexed basketball seed; no basketball court coordinate has ever been produced
  bar          = NO pass bar. **A gate FAIL at the CORRECT frame is a FULL SUCCESS and a major negative**
                 -- it would say hand-labelled seeding does not work for basketball even when everything
                 lines up, closing the last open calibration path. **A PASS with a measured horizon would
                 be the first basketball court coordinates in the programme.** Do not tune the seed, do
                 not adjust labels beyond the stated 3x scale, do not substitute a clip or a frame.
  n            = 1 clip, 1 seed, a stated span (EXISTENCE and decay shape, not a rate)
  eye check    = the seed render is the GATE; the distance renders are the deliverable
  must not move = every threshold, bar and verdict, the court model, the coordinate contract, the
                  harness, the label files, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon
                  and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g233c_seed_gate_reindexed_2026-09-04.md with the frame-accurate decode
method and its check against G236's committed frame, the scaled coordinates, the seed homography, the
gate result stated FIRST, then any propagation and projection results, all renders, every disk-guard
probe, bytes freed, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
