GAP G280 | sport basketball | worktree a5 or a6 (whichever frees) | log g280_amateur_footage_trackability
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** You may
IMPORT and RUN them; you may not EDIT them. Build any new harness in `scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **ALL OF IT IS ON THE POD.** The clip and the GPU are both there. Use
    **`~/bin/pod_run <aN> --ship <harness> --fetch <the tracking CSVs, the crops and the summaries> --
    <cmd>`**, which copies this worktree's code tree to `/workspace/wt/<aN>`, runs under nohup, and
    fetches the listed paths back. **It never writes the deployed tree.**
  - **The disk guard belongs INSIDE the `pod_run` command.** A missing `/workspace` in the local checkout
    is NOT a disk failure; it means the step belongs in `pod_run`.

**HOLD RULE -- COUNT DISTINCT LANE WORKTREES, NOT PYTHON PIDs.** One lane routinely shows TWO python PIDs
sharing one `cwd` (G274 verified this for `/workspace/wt/a17`). **Reduce to the SET of distinct
`/workspace/wt/a*` directories and compare THAT to 2.** Exclude your own process, your checker and its
parent. **Report the SET you observed.** **This row needs the GPU, so it MUST hold for a free lane. Do NOT
interrupt a running row.**

**READ THE LANDED G273 AND G277 MEMOS FIRST, AND USE G277's NORMALISATION FORMULA UNCHANGED.**

**WHY THIS ROW EXISTS -- THE STATED GOAL IS "ANY GAME, ANY SPORT, ANY VIDEO", AND THE ONE AMATEUR CLIP WE
HAVE HAS NEVER BEEN TRACKED AT ALL.**
Every tracking measurement in this programme is on professional broadcast footage. The corpus holds
**exactly one amateur clip**, verified on the pod 2026-09-04:
`basketball__amateur_jh3fnwMi7dM.mp4`, **24,523,745 bytes, 1280x720, 30 fps, 120.10 s, 3,729 frames.**
**A search of the tracking store found no run for it.** The amateur calibration chain established that
this class of footage **cannot be calibrated** (camera framing, occlusion, court decoration), so
court-space measurement is closed here. **But nobody has asked the prior question: does the tracker
produce anything usable on it in IMAGE space, where no map is needed?**

THE QUESTION: **on amateur footage, does the tracker detect and follow people at all, and how does its
image-space profile compare with the 42 broadcast runs?**

METHOD:
  1. **RUN THE EXISTING TRACKER THREE TIMES, UNCHANGED.** Import and run the production route as the
     landed runs did; **change no parameter, no threshold and no weight.** **Three independent runs,
     because G241 established the detector is non-deterministic (808 of 1,201 records differed on an exact
     re-run), and a single draw would be indistinguishable from noise.** **Emit the same
     `tracking_data.csv` schema the landed runs use** (`frame, track_id, cls, x, y, coordinate_space,
     observation, calibration, source_fps, source_height, source_duration`) so the result is directly
     comparable. **Report the exact route and its sha256, and state that `calibration` is `none` and the
     space is `image_px`.**
  2. **REPORT RUN-TO-RUN VARIABILITY FIRST, BEFORE ANY COMPARISON.** Across the three runs give detection
     count, distinct `track_id` count, and the speed quantiles below. **If the three runs disagree
     substantially, that variability is the headline finding and every later number must be quoted as a
     range, not a point.** **Do not average away a disagreement.**
  3. **COMPUTE THE IMAGE-SPACE PROFILE WITH G277's FORMULA, UNCHANGED**, on consecutive-frame same-
     `track_id` steps: `speed = sqrt(dx^2 + dy^2) / source_height * source_fps`, in **frame-heights per
     second**. **This clip is 720-high and 30 fps while much of the corpus is 1080-high and some is
     59.94 fps -- raw pixels are NOT comparable, which is exactly why the normalisation exists.** Report
     median, p90, p99, p99.9 and max, plus distinct track count, median and p90 track length in **frames
     AND seconds**, and the fraction of tracks shorter than 5 frames.
  4. **PLACE THE AMATEUR CLIP AMONG THE 42 BROADCAST RUNS** on each statistic -- rank or percentile,
     using G277's committed per-run table if it has landed, and saying so if it has not. **Answer in one
     plain sentence whether amateur footage tracks like broadcast footage or not.**
  5. **PART B -- MEASURE DETECTOR PRECISION ON THIS FOOTAGE, blind, exactly as G273 did.** Sample **at
     least 60 retained detections UNIFORMLY across the clip and across frames, conditioned on nothing**
     -- not on speed, not on jumps, not on anything downstream. **Render each as a footpoint-centred crop
     at full resolution, no box drawn or inferred.** **Classify blind in a randomised order, committing
     the order and verdicts in their own commit BEFORE un-blinding**, using **G273's four categories
     unchanged: (a) PLAYER on the court of play; (b) PERSON, not a player in play; (c) NOT A PERSON;
     (d) CANNOT JUDGE.** **Keep (d) separate.** **Do not redefine a category** -- comparability with
     G273's broadcast figures is the entire point.
  6. **COMPARE PART B AGAINST G273's BROADCAST BASELINE with a two-proportion test**: G273 measured
     **43/72 = 0.597 PLAYER and 15/72 = 0.208 NOT A PERSON** on broadcast. Report pooled p, SE, z and the
     **nominal** two-sided p for the (a) rate and for the (c) rate. **Overlapping confidence intervals are
     NOT a test -- do not reason from interval overlap.** **State that the p is nominal with no correction
     for the many comparisons in this programme.**
  7. **Do NOT propose a production change, filter, gate, threshold or retrain; do NOT touch `src/`.**
     G269 showed how easily a filter fakes an improvement.
  8. **The population is detector boxes, not authenticated players**, and `cls=player` is the DETECTOR'S
     label, not a verified identity. **Name every denominator; never say "players" unqualified.**
  9. **Make NO court-space, calibration or positional claim.** There is no map for this clip and none can
     be fitted; **image space is the whole scope of this row.**

**DISK GUARD, POD SIDE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** -- about
**38,727 MB at 2026-09-04 13:36**, roughly **11.3 GB free** against the 50 GB quota, and **a peer session
writes under `/workspace/wt`.** **Re-measure yourself.** **`dd conv=fsync` probe before writing, STOP and
report if it fails ON THE POD.** **Three tracking runs plus 60+ crops are the bulk -- keep crops modest,
and report committed bytes.** **Do NOT delete any corpus source, and do NOT delete the two abandoned
bridge partials (`baseball__npb_05.mp4.part` 2.4 GB, `football__football_m8UWuQoflJo.mp4.part` 4.7 GB):
they are resumable acquisitions and the football one is the only football footage in the programme.**
Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** **ONE amateur clip, 120 seconds, ONE camera, ONE labeller.**
**This cannot support any claim about amateur footage as a class** -- it is a single instance, and the
memo must say so in those words. Three runs bound the detector's non-determinism on THIS clip only.
**A footpoint-centred crop is not the detector's box.** **Image-space displacement conflates player
motion, CAMERA motion and tracking error and they cannot be separated without a map** -- so a larger tail
here is NOT by itself evidence of worse tracking; amateur camerawork may simply move more. **Say that
prominently.** Nothing here validates identity anywhere.

ACCEPTANCE RULE:
  metric        = the three runs with their detection and track counts and the run-to-run variability
                  statement; the normalised speed and track-length profile with G277's formula; the
                  placement among the 42 broadcast runs with a one-sentence answer; Part B's committed
                  blind order, four counts and fractions with (d) separate; and the two-proportion tests
                  against G273's 0.597 and 0.208 with nominal p values
  before        = every tracking measurement in the programme is on professional broadcast footage, and
                  the corpus's single amateur clip has never been tracked at all
  bar           = **NO pass bar.** **"The tracker produces nothing usable on amateur footage" is a FULL
                  SUCCESS and a major finding** for the any-video goal. **"It tracks about as well as
                  broadcast" is equally valuable and would be the first evidence the goal is reachable.**
                  **"The three runs disagree too much to say" is ALSO a full success.** Do not tune, do
                  not filter, do not retrain, do not move a threshold.
  n             = 1 amateur clip, 3,729 frames, 3 runs, the detection and step counts you state, 60+
                  blind-classified detections, 1 labeller -- **name every denominator in the verdict
                  line, and name the detector-box population**
  eye check     = Part B's blind classification IS a measurement; it is a COARSE categorical judgement,
                  not the sub-pixel geometric one G257 bounded at 20 px. **Say that distinction.**
  must not move = every threshold, bar and verdict, G273's counts and sealed order, G277's normalisation
                  formula and per-run table, G267's retained records, the court model, the coordinate
                  contract, `src/` and `domains/` (READ and IMPORT ONLY -- run them, never edit them),
                  the pod daemon and keeper, the corpus, the bridge partials
EVIDENCE: docs/evidence/tracking/g280_amateur_footage_trackability_2026-09-04.md with the three runs and
their variability, the normalised profile, the placement among the broadcast runs, Part B's committed
blind order and verdicts and crops, the two-proportion tests, every disk-guard probe with the
`du -sm /workspace` figure, bytes freed and committed, and a NOT VERIFIED list. **The per-run summary must
be committed as a machine-readable file.** **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.**
Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
