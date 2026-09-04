GAP G233b | sport ncaa_basketball | worktree a3 | log g233b_seeded_court_coordinates_matched_clip
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. Build
in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G232 and G235 may be running; N=2 is the measured optimal schedule per
G200/G216). **Check first and say in your memo that you checked and when you began.** The `track_daemon`,
`keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT
residents and the load floor -- never wait for them, never kill or restart them.

**WHY THIS ROW EXISTS -- G233 FAILED ON A PREMISE ERROR IN MY SPEC, NOT ON THE PHYSICS.** G233 seeded
from G140 labels recorded against clip identifier **`wnba__wnba_01_1080p`** and applied them to
**`wnba__wnba_01.mp4`**. Those are different clip identifiers and **no `_1080p` file exists in the pod
corpus at all**, so the homography was fitted on one clip's frame and applied to another's. Its eye check
duly showed the court model off the painted floor **at distance zero**, giving a useful horizon of zero
frames. **That result says nothing about whether seeded calibration works, and must not be cited as if
it did.**

**THIS ROW USES A PAIRING THE ORCHESTRATOR HAS VERIFIED END TO END.** Of the eleven clips carrying G140
labels, **exactly one has an identifier that exactly matches a pod corpus file**:

  - **Video:** `/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4`
    -- `ffprobe` on the pod reports **width=1920, height=1080, nb_frames=205444, avg_frame_rate=30000/1001**.
  - **Labelled frame:** `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171`, **source_frame
    28171** (well inside 205,444).
  - **Label coordinates, recorded at image_width=640, image_height=360:**
    `paint_near_baseline_left_corner (38,223)`, `paint_near_baseline_right_corner (39,289)`,
    `paint_near_free_throw_left_corner (274,224)`, `paint_near_free_throw_right_corner (273,282)`.
  - **SCALE, AND THIS IS THE TRAP THAT JUST COST A ROW: the labels are at 640x360 and the video is
    1920x1080, so every label coordinate must be multiplied by exactly 3** (1920/640 = 3.0 and
    1080/360 = 3.0). Scaled, they are `(114,669)`, `(117,867)`, `(822,672)`, `(819,846)`. **State the
    scale factor you applied and show the scaled values.**
  - **SPORT: this is NCAA, so use `court_points_for_sport("ncaa_basketball")` -- the 12 ft lane, NOT
    WNBA's 16 ft.** Using the wrong lane width would silently corrupt the fit.

**HARD GATE, AND IT IS THE LESSON OF G233: VALIDATE THE SEED AT DISTANCE ZERO BEFORE PROPAGATING
ANYTHING.**
  **Render the projected court model onto the seed frame itself and look at it. If it does not land on
  the painted court at distance 0, STOP and report that** -- do not propagate, do not project
  detections, do not compute an in-court fraction. **G233 spent a whole run and 1,201 decoded frames
  before its eye check revealed the seed was wrong. One render, first, would have caught it.**

METHOD:
  1. Decode the seed frame. **Confirm you have source frame 28171 specifically** -- `ffmpeg -ss` before
     `-i` fast-seeks to the nearest keyframe and is NOT frame-exact, so use a frame-accurate method and
     **say which**. Report the decoded frame's dimensions.
  2. Build the seed homography from the four scaled corners via **G196's unchanged `court_points_for_sport`
     and solve**, for sport `ncaa_basketball`. Report the matrix.
  3. **THE GATE: render the projected court on the seed frame and judge it.** Commit that render.
     **Report PASS or FAIL in one line before anything else.** If FAIL, stop and report -- that would
     mean even an identifier-matched clip does not seed, which is a major and useful finding.
  4. Only if the gate passes: propagate direct-to-seed using **G222's landed harness unchanged**
     (`scripts/platformkit/tracking/g222_direct_to_seed_propagation.py`) over a stated span, and report
     drift/reprojection and matched-feature counts versus distance, as G222 did.
  5. Project detected player feet to court feet and report the **fraction inside the 94 x 50 ft court
     versus distance from the seed**, with the distance-outside distribution, using **G230's method and
     vocabulary** so the numbers are commensurable. **Prefer importing and calling the detector directly:
     G211b showed `run_clip --frames 1200` emitted ZERO rows, and G234/G234-COMPLETE showed all nine
     basketball route failures are a `_build_court` crash.**
  6. **Render at several distances and state where it comes off the court.** Commit the renders.
  7. **Report the horizon in labels-per-hour** with the arithmetic and assumptions.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE on this pod. **`dd conv=fsync` probe before writing,
record `du -sm /workspace/nba-ai-system/data` (baseline ~31,840 MB of 50,000), STOP and report if it
fails.** Delete every temporary artifact and report bytes freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** **this CONSUMES A HAND LABEL and is NOT automatic
calibration** -- the automatic half remains 0/17 and this row does not change it. **Plausibility is
NECESSARY, NEVER SUFFICIENT**: an in-court fraction includes spectators, officials and lower-third
detections, exactly as G233 correctly warned, so it is descriptive and never an accuracy claim. One
clip, one seed, one camera. G222's 1,200-frame horizon was measured on IMAGE features on a different
clip; **do not assume it transfers.** The labels are single-source eye labels with an 11.39 px p90
repeatability (G140).

ACCEPTANCE RULE:
  metric        = the seed-render PASS/FAIL at distance 0, stated first; then, only if PASS, drift and
                  matched features versus distance, the in-court fraction versus distance with its
                  outside-distance distribution, the renders, and the labels-per-hour arithmetic
  before       = G233 could not test seeded basketball calibration because its seed and its video were
                 different clips; the question is entirely open, and no basketball court coordinate has
                 ever been produced
  bar          = NO pass bar. **A seed-gate FAIL on an identifier-matched clip is a FULL SUCCESS** and
                 would be a major negative worth knowing immediately. **A PASS followed by a measured
                 horizon would be the first basketball court coordinates in the programme.** Do not tune
                 the seed, do not adjust label coordinates beyond the stated 3x scale, and do not
                 substitute another clip.
  n            = 1 clip, 1 seed, a stated span (EXISTENCE and decay shape, not a rate)
  eye check    = the seed render is the GATE; the distance renders are the deliverable
  must not move = every threshold, bar and verdict, the court model, the coordinate contract, the
                  harness, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the
                  corpus, the legacy tables
EVIDENCE: docs/evidence/tracking/g233b_seeded_court_coordinates_matched_clip_2026-09-04.md with the
scale factor and scaled coordinates, the frame-accurate decode method, the seed homography, the
seed-render gate result stated first, the drift and in-court tables if reached, all renders, every
disk-guard probe, bytes freed, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
