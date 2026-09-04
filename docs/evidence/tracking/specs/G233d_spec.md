GAP G233d | sport wnba | worktree a3 | log g233d_seed_gate_validated_frame
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G225 may be running; N=2 is optimal per G200/G216). **Check first, do
NOT interrupt a running row, and say in your memo that you checked and when you began** -- G236b handled
exactly this correctly. The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs,
`inplay_capture_runner` and `foundry_runner` are PERMANENT residents and the load floor.

**READ `docs/evidence/tracking/specs/G233c_spec.md` FIRST. This is the same row with the one thing that
was always missing: a frame whose geometry G196 ACTUALLY VALIDATED.**

**WHY THIS IS THE FIRST FAIR TEST OF THE SEEDED PATH.** Three attempts failed and none of them tested
validated geometry:
  - **G233**: labels from `wnba__wnba_01_1080p` applied to `wnba__wnba_01.mp4` -- different identifiers,
    no `_1080p` file in the corpus, and no frame check. My spec error.
  - **G233b**: `IB-_u4gW3ds__s14__f028171` at its named index 28171 -- the still is not that frame
    (frame-accurate MAD 61.33).
  - **G233c**: the same still at the **correct** index 46154, verified at MAD 1.865680. Clean gate
    FAILURE -- **but G196 never eye-checked that frame.** Its table entry `yes | 0.000e+00 | 0.000e+00`
    is the ROUND-TRIP RESIDUAL, a self-fit that is trivially zero, not an eye-check verdict.
  - **G196 eye-checked only 5 of 17 frames** (indices 0, 4, 8, 12, 16): 3 YES, 2 INDETERMINATE. **All
    three YES frames come from clip identifiers absent from the corpus** -- until now.

**G236b CLOSED THAT GAP.** `wnba__wnba_01_1080p__s01__f001600` -- a G196 **YES**, *"The independently
visible three-point curve lands on the painted court"* -- **appears in `wnba__wnba_01.mp4` at ZERO-BASED
FRAME 19599**, with refined 64x36 grayscale MAD **0.903212** against a full stride-5 scan median of
**40.664062**, a ratio of **0.022212** (G236's reference was 0.036661). Delta **+17,999**.

**THE VERIFIED SEED PARAMETERS:**
  - **Video:** `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` -- **A9: 2,931,985,407
    bytes, 1920x1080, 174,430 frames.**
  - **Seed frame: 19599, ZERO-BASED.** **Decode frame-accurately and say how** -- `ffmpeg -ss` before
    `-i` is NOT frame-exact. G233c used `select=eq(n,index)`; G236b used the same. **Verify your decoded
    frame against G236b's committed best-match image before building anything, exactly as G233c did
    (it reported MAD 1.865680 against G236's).** If they disagree, STOP.
  - **Labels, already at 1920x1080 -- SCALE FACTOR IS 1.0, none needed. State that explicitly**, because
    a wrong scale is the failure mode that cost G233b and G233c. From
    `corner_pixel_targets.csv` for `wnba__wnba_01_1080p__s01__f001600`:
    `paint_near_baseline_left_corner (350,400)`, `paint_near_baseline_right_corner (835,420)`,
    `paint_near_free_throw_left_corner (390,696)`, `paint_near_free_throw_right_corner (990,730)`.
    **Read them from the CSV yourself rather than trusting this transcription, and show what you read.**
  - **Sport `wnba`, so `court_points_for_sport("wnba")` -- the 16-FOOT lane, NOT the NCAA 12-foot one
    G233b/G233c used.** Getting this wrong would silently corrupt the fit.

**HARD GATE, UNCHANGED: RENDER THE PROJECTED COURT ON THE SEED FRAME AND REPORT PASS OR FAIL IN ONE LINE
BEFORE ANYTHING ELSE.** On FAIL, STOP -- no propagation, no projection, no in-court fraction, no
labels-per-hour. **The four labelled corners are FITTED INPUTS and are not evidence; judge the render on
the INDEPENDENT geometry -- the three-point arc, sidelines, centre circle -- exactly as G196 did.**

METHOD (only on a PASS):
  1. Propagate direct-to-seed with **G222's landed harness unchanged**; report drift and matched-feature
     counts versus distance, as G222 did (it held all 1,200 frames tested at a flat 0.259-0.382 px
     reprojection residual **on this very clip**).
  2. Project detected player feet to court feet; report the **fraction inside the 94 x 50 ft court versus
     distance**, with the outside-distance distribution, using **G230's method and vocabulary**.
     **Prefer importing the detector directly** -- `run_clip` emitted zero rows (G211b) and
     `cv2.findHomography` was not reached in a 40-frame probe.
  3. **Render at several distances; state where it comes off the court. Commit every render.**
  4. **Report the horizon in labels-per-hour** with its arithmetic and assumptions.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~32,440 MB of 50,000), STOP and report if it fails.**
Delete every temporary artifact and report bytes freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** this **CONSUMES A HAND LABEL** and is NOT automatic
calibration -- the automatic half remains 0/17. **Plausibility is NECESSARY, NEVER SUFFICIENT**: an
in-court fraction includes officials, bench and spectators, and G239 measured a median of 20 detections
per frame against ten players on court. **G196's YES was a single-labeller eye judgement on a JPEG still,
not ground truth**, and G140's p90 label repeatability is 11.39 px. One clip, one seed.

ACCEPTANCE RULE:
  metric        = the seed-render PASS/FAIL at distance 0, stated FIRST; then, only on PASS, drift and
                  matched features versus distance, the in-court fraction with its outside distribution,
                  the renders, and the labels-per-hour arithmetic
  before       = three seeded attempts failed, none on a G196-validated frame; G236b has now paired one
                 validated still with a corpus video at frame 19599 with decisive separation
  bar          = NO pass bar. **A FAIL here is the most decisive negative available to this programme** --
                 with a validated frame, a verified index, no scale factor and the correct lane width, it
                 would close hand-labelled seeding for basketball on measurement rather than on
                 bookkeeping. **A PASS would be the first basketball court coordinates the programme has
                 ever produced.** Do not tune the seed, do not adjust a label, do not substitute a frame.
  n            = 1 clip, 1 seed, a stated span (EXISTENCE and decay shape)
  eye check    = the seed render is the GATE; the distance renders are the deliverable
  must not move = every threshold, bar and verdict, the court model, the coordinate contract, the
                  harness, the label files, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon
                  and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g233d_seed_gate_validated_frame_2026-09-04.md with the decode method and
its MAD check against G236b's committed frame, the labels as read from the CSV, the explicit scale-1.0
statement, the seed homography, the gate result stated FIRST, any propagation and projection results, all
renders, every disk-guard probe, bytes freed, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
