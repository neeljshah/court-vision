GAP G296 | sport wnba | worktrees a10 (pass A) and a12 (pass B) | logs g296a_locate_pass_a / g296b_locate_pass_b
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**YOU ARE ONE OF TWO INDEPENDENT LOCATORS RUNNING THE SAME SPEC ON THE SAME FRAMES.** Pass A runs on
`gpt-5.6-terra` in a10; pass B runs on `gpt-6-astra` in a12. **DO NOT look for, read, or wait for the
other pass's output. Do NOT read `g285b_locate_then_match_recall_artifact/located_feet.csv` before you
have committed your own locations** -- it is a prior locator's answer sheet for a different frame set and
seeing it would destroy your independence. **Say in your memo which pass you are and that you did not read
the other.** The verifier merges the two passes and measures their agreement; **your independence IS the
asset being built.**

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **FRAME EXTRACTION IS ON THE POD** -- the source video is there. Use **`~/bin/pod_run <your aN>
    --ship <harness> --fetch <the extracted frames and manifest> -- <cmd>`**.
  - **THE LOCATION WORK IS LOCAL**, on frames fetched back.
  - **GATE: CPU DECODE, NOT THE GPU.** Other rows hold the GPU. **Gate on the `dd conv=fsync` probe on
    `/workspace` and load15 below `nproc` -- NOT a lane count and NOT `nvidia-smi`.** **Do NOT hold for a
    free lane; do NOT interrupt a running row.** Report the gate measurement you used.
  - **DISK GUARD:** `du -sm /workspace` is a MooseFS NETWORK walk -- **empty output means UNKNOWN, NEVER
    0, and NEVER stop on UNKNOWN.** **The only stopping condition is a FAILED `dd conv=fsync` probe on the
    pod.** You extract 24 JPEGs. **Download nothing. Delete no corpus source and neither bridge partial.**

**WHY THIS ROW EXISTS -- EVERY RECALL QUESTION IN THE PROGRAMME IS UNDERPOWERED, AND THE ONE GROUND-TRUTH
SET IT HAS WAS BUILT BY A SINGLE RATER.**
The existing hand-located set is **143 foot observations on 15 frames**, all from ONE locator and all
inside the studied span. Recall against it is **3/143 = 0.021 at 25 px, 7/143 = 0.049 at 50 px and
17/143 = 0.119 at 100 px** (G285b). **With 17 matches in total, ANY split of that set -- by image
position, by player size, by time -- has about five matches per cell and cannot support a trend.** That is
why the "is recall worse for distant players" question has never been asked: **it would be underpowered
before it started.**
**And G291 has just measured what a single model rater is worth on a MUCH EASIER task**: two raters
judging four categories on identical crops agreed at Cohen's kappa **0.283**, with one rater never using a
category the other used in a fifth of cases. **A ground-truth set built by one rater would repeat that
mistake at the foundation of everything built on top of it.**
**Two further limits this row is designed to fix:** the existing set is confined to frames 19599-23399,
and **G278 measured that span to be friendlier than its own clip (0.836 against 0.656 court-bearing,
p = 0.0078)**, so nothing built on it may be quoted clip-wide.

THE QUESTION: **build a two-rater, clip-wide, agreement-measured set of hand-located player feet.**

METHOD:
  1. **EXTRACT EXACTLY THESE 24 FRAMES, CLIP-WIDE, FROM `wnba__wnba_01.mp4`** (2,796 MB, 1920x1080,
     30 fps, **174,430 frames**, sha256 begins `f361ad7a32ccc6d98ae8e98e`): **frame index
     `round(i * 174429 / 23)` for `i = 0..23`.** **Both passes must use exactly these indices -- print the
     list you extracted and confirm it matches that formula.** **State the exact ffmpeg command and
     confirm the frames are full 1920x1080 native, NOT cropped and NOT resized.**
  2. **FOR EVERY FRAME, LOCATE THE FEET OF EVERY PLAYER YOU JUDGE TO BE A PLAYER ON THE COURT OF PLAY**,
     as an (x, y) image pixel coordinate at the point where that player contacts the floor. **One point
     per player.** **If a player's feet are occluded or out of frame, record the player with
     `feet_visible=false` and NO coordinate -- do NOT guess a position.** **Record officials, coaches,
     bench players and spectators as `role` values, never as players on the court of play.**
  3. **RECORD, FOR EVERY FRAME**: whether court geometry is visible at all, a one-line description of the
     shot (wide, close-up, replay, graphic, crowd, commercial), and the count of players you located.
     **A frame with NO court and NO players is a valid and expected result -- G278 predicts roughly a third
     of clip-wide frames are like that. Record it, do not skip it, and do not substitute another frame.**
  4. **COMMIT YOUR LOCATIONS BEFORE ANY JOIN OR COMPARISON**, in their own commit, and report that sha.
     **Do NOT open any detector output, any prior located-feet file, or any recall figure before that
     commit exists.** **This row produces NO recall number. It builds an input.** **If you compute a
     recall figure you have broken the row.**
  5. **REPORT YOUR OWN UNCERTAINTY per located point** as one of `confident`, `approximate` or `guess`,
     and **report the counts of each.** **A point you would not defend to within about 20 px is
     `approximate` at best.** **Do NOT drop uncertain points; label them.**
  6. **SCHEMA, EXACT, so the two passes merge without interpretation** -- one CSV
     `docs/evidence/tracking/g296<your pass letter>_located_players_artifact/located_players.csv` with the
     header **`source_frame,person_index,role,feet_visible,foot_x_px,foot_y_px,confidence,note`**, plus a
     per-frame CSV `frames.csv` with
     **`source_frame,court_visible,shot_description,players_located`**. **`role` is one of
     `player_on_court`, `official`, `bench_or_coach`, `spectator_or_media`, `other`.** **Every field
     present on every row; empty coordinate fields for `feet_visible=false`.**
  7. **Do NOT run, import or look at any detector. Do NOT touch `src/`. Propose no filter, threshold,
     retrain or production change. Do NOT move any bar. Do NOT edit
     `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.

**HONEST LIMITATIONS to state, not discover:** **YOU ARE A MODEL, NOT A HUMAN, AND THIS IS NOT GROUND
TRUTH IN THE STRICT SENSE.** **Two model locators agreeing measures REPRODUCIBILITY, never CORRECTNESS,
and both can be wrong in the same way.** **Say that in those words.** No human has checked these frames.
**24 frames spread across one clip is a thin, wide sample: it fixes the span-representativeness problem
and does NOT fix the one-clip problem.** **Locating a foot in a 1920x1080 broadcast frame is itself
uncertain at the tens-of-pixels scale for distant players** -- that is what the `confidence` field is for,
and any recall figure later computed from this set inherits it. **The frame indices are deterministic and
were fixed before either pass ran, so neither locator chose its own frames.**

ACCEPTANCE RULE:
  metric        = the 24 extracted frame indices confirmed against the formula; the exact ffmpeg command
                  and a confirmation the frames are native 1920x1080; `located_players.csv` and
                  `frames.csv` in the exact schema; per-frame court-visibility and shot description;
                  confidence counts; the sha of the commit made BEFORE any join; and a statement of which
                  pass you are and that you did not read the other pass or any prior located-feet file
  before        = one ground-truth set of 143 foot observations on 15 frames, from ONE locator, entirely
                  inside a span measured to be friendlier than its own clip -- so every recall split has
                  about five matches per cell and cannot support a trend
  bar           = **NO pass bar. This row builds an INPUT, not a result.** **A frame with no court and no
                  players is a valid row. A high `approximate`/`guess` count is an honest outcome and is
                  more useful than false confidence. Locating fewer players than you expected is a
                  finding, not a failure.**
  n             = 24 frames, clip-wide, 1 locator per pass, 2 passes -- name the denominator in the
                  verdict line and state that this is a MODEL locator, not a human
  eye check     = the location IS the measurement. It is a geometric judgement at full frame resolution,
                  and its precision is bounded by the `confidence` field you record.
  must not move = G285b's located feet and counts; G267's retained records; G273's, G287's, G288's and
                  G291's verdicts; every threshold and verdict; `src/` and `domains/` (READ and IMPORT
                  ONLY); the corpus, every source video, and both bridge partial downloads
EVIDENCE: `docs/evidence/tracking/g296<pass letter>_located_players_2026-09-04.md` with the frame list and
formula check, the ffmpeg command, the schema confirmation, per-frame summary, confidence counts, the
pre-join commit sha, every disk-guard probe verbatim, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md
ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted -- **pin the 24 frame indices against the formula and
pin the exact CSV headers.** **NEVER a full pytest.** **If a commit grows an allowlisted file, raise its
entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
