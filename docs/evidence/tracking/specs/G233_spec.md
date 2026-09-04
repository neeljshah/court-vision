GAP G233 | sport wnba | worktree a3 | log g233_basketball_seeded_court_coordinates
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ and IMPORT only.
`domains/` is READ and IMPORT only. Build in `scripts/platformkit/tracking/`.

**HELD UNTIL THE POD IS FREE OF MEASUREMENT ROWS.** **Check first and say in your memo that you checked
and when you began.** The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs,
`inplay_capture_runner` and `foundry_runner` are PERMANENT residents and the load floor -- never wait for
them, never kill or restart them. Harness and test preparation may proceed immediately.

**WHY THIS ROW EXISTS -- IT IS THE PAYOFF OF TONIGHT'S CALIBRATION WORK, AND IT WOULD PRODUCE THE FIRST
BASKETBALL COURT COORDINATES THE PROGRAMME HAS EVER HAD.**
  - **G196**: four HAND-LABELLED paint corners give a homography whose three-point arc lands correctly
    OUT-OF-SAMPLE. A seed works.
  - **G222 (landed tonight)**: chained propagation is unusable past ~50 frames (drift 10.876 px at 50,
    38.472 at 100, 187.772 at 300), but **DIRECT-TO-SEED matching held across ALL 1,200 frames tested**
    with reprojection RMS flat at **0.259 -> 0.361 px** and matched features declining only 1,279 -> 646
    with **no overlap cliff.** Its harness is landed at
    `scripts/platformkit/tracking/g222_direct_to_seed_propagation.py`.
  - **Automatic anchors remain 0/17** (G210b, G214), and tonight G223, G224, G227 and G229 closed every
    in-repo classical route. **So a hand-labelled seed is the only calibration path we know works, and
    G222 made its arithmetic survivable: roughly 90 labels per hour of 30 fps footage instead of 2,000.**
  - **G207-BASKETBALL-GAP**: basketball has never been scored, and separately emits no
    `coordinate_space`. **This row does NOT try to fix that** -- G226/G226b/G226c own the adapter. This
    row asks only whether correct COURT COORDINATES are obtainable at all.

THE QUESTION: **seeded from one hand-labelled frame and propagated direct-to-seed, do basketball player
detections project to physically sensible court positions, and over how many frames?**

METHOD:
  1. **Reuse G222's landed harness and G196's seed construction UNCHANGED.** The seed is the labelled
     frame `wnba__wnba_01_1080p__s01__f001600` (source frame 1600) on
     `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` (2,931,985,407 bytes, 1920x1080,
     174,430 frames), with `court_points_for_sport("wnba")` -- **the WNBA 16 ft lane, not the NCAA 12 ft
     one.** State the seed homography you obtained.
  2. **Obtain player detections for a stated span of frames forward from the seed.** You may import and
     call the detector directly rather than running the whole route -- **and given G211b, prefer that:
     `run_clip.py --frames 1200 --no-show --skip-features` processed 1,380 source frames, made 400
     detector calls and emitted ZERO tracking rows, exiting 3 after Stage 1.** **If you use the route
     and it emits nothing, do not retry it three times -- switch to calling the detector directly and
     say you did.**
  3. **Project detected player FEET to court feet through the propagated homography** and report, at
     several distances from the seed: how many detections projected, and **what fraction landed inside
     the 94 x 50 ft court**. **Use G230's method and vocabulary so the numbers are commensurable with
     the tennis audit**, including the distance-outside distribution rather than a bare in/out count.
  4. **This is the same plausibility test G230 applied to tennis, and it is NECESSARY, NEVER SUFFICIENT
     -- say so.** A player projected inside the court may still be in the wrong place. **Do not claim
     accuracy; claim only that positions are or are not physically sensible.**
  5. **EYE CHECK IS THE DELIVERABLE**, exactly as in G215 and G222: render the projected court model and
     the projected player positions onto frames at several distances from the seed, and state plainly at
     what distance it comes off the painted court. Commit the renders.
  6. **Report the horizon in labels-per-hour**, with the arithmetic and its assumptions, for whatever
     horizon you actually observed. **If it dies far sooner than G222's 1,200 frames because player
     detections are noisier than image features, that is a FULL SUCCESS and an important correction to
     the G222 arithmetic I published.**
  7. **Do NOT deploy anything to the pod, do NOT modify the adapter, do NOT write into any tracking
     directory the harness reads, and do NOT propose a `src/` or `domains/` change.** This row measures
     whether the geometry works; wiring it into production is a separate decision.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE on this pod (it reports the whole cluster filesystem
against a 50 GB volume cap, which caused a `Disk quota exceeded` incident). **`dd conv=fsync` write probe
before writing, record `du -sm /workspace/nba-ai-system/data` (baseline ~31,600 MB of 50,000), STOP and
report if it fails.** Delete every temporary artifact and report bytes freed. Delete no corpus source.

**HONEST LIMITATIONS you must state rather than discover:** **this CONSUMES A HAND LABEL and is therefore
NOT automatic calibration** -- the automatic half remains 0/17 and this row does not change it. One clip,
one seed, one camera: an EXISTENCE result and a decay shape, not a rate. G222's horizon was measured on
IMAGE FEATURES; projecting player detections adds detector error on top, so **the useful horizon here may
be shorter and you must not assume G222's 1,200 transfers.** No ground truth exists for player positions,
so the renders carry the accuracy claim and they are single-labeller eye judgements. The route is
non-deterministic (G190/G195/G198/G203); say whether you ran it at all.

ACCEPTANCE RULE:
  metric        = fraction of projected player detections inside the 94 x 50 ft court versus distance
                  from the seed, with the distance-outside distribution; the observed horizon; the
                  renders; and the labels-per-hour arithmetic
  before        = basketball has NO court coordinates of any kind; automatic anchors are 0/17 and every
                  in-repo classical route closed tonight; G222 showed direct-to-seed propagation of
                  IMAGE geometry holds 1,200 frames, but nothing has been projected through it
  bar           = NO pass bar. **"Seeded projection puts players sensibly on court for N frames" would be
                  the first basketball court coordinates in the programme. "It does not work, because X"
                  is equally a full success** and would close the last open calibration path, which is a
                  decision worth having. Do not tune, and do not present plausibility as accuracy.
  n             = 1 clip, 1 seed, a stated span (EXISTENCE and decay shape, not a rate)
  eye check     = the renders described above -- this is the deliverable
  must not move = every threshold, bar and verdict, the court model, the coordinate contract, the
                  harness, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the
                  corpus, the adapter, any tracking directory the harness reads
EVIDENCE: docs/evidence/tracking/g233_basketball_seeded_court_coordinates_2026-09-04.md with the seed
homography, the in-court fraction versus distance, the distance-outside distribution, the renders, the
labels-per-hour arithmetic, every disk-guard probe, bytes freed, an explicit statement that this consumes
a hand label and that plausibility is not accuracy, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
