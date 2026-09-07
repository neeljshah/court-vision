GAP G296a | sport wnba | worktree a10 | log g296a_locate_pass_a
**PASS B HAS ALREADY LANDED (`3eeef35cf`) AND ITS OUTPUT IS IN THIS REPO AT
`docs/evidence/tracking/g296b_located_players_artifact/`. DO NOT OPEN IT, DO NOT LIST IT, DO NOT READ
`g296b_located_players_2026-09-04.md`, AND DO NOT LOOK AT ITS FRAMES.** Your independence from it is the
entire asset this row builds; reading it destroys the row and there is no way to undo that. **The verifier
merges the two passes; you never see pass B.**
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**YOU ARE ONE OF TWO INDEPENDENT LOCATORS RUNNING THE SAME SPEC ON THE SAME FRAMES.** Pass A runs on
`gpt-5.6-terra` in a10; pass B runs on `gpt-6-astra` in a12. **DO NOT look for, read, or wait for the
other pass's output. Do NOT read `g285b_locate_then_match_recall_artifact/located_feet.csv` before you
have committed your own locations** -- it is a prior locator's answer sheet for a different frame set and
seeing it would destroy your independence. **Say in your memo which pass you are and that you did not read
the other.** The verifier merges the two passes and measures their agreement; **your independence IS the
asset being built.**

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP) -- AMENDED 2026-09-07: THIS ROW IS NOW FULLY LOCAL.**
  - **THE POD IS NOT USED AND MUST NOT BE USED.** Attempt 1 died mid-extract against a pre-reallocation pod
    address (`pod_run_local_stderr.txt`: "Connection to 213.192.2.123 closed by remote host", rc=1). That
    address is dead and `~/bin/pod_run` has not been re-pointed. **Do NOT call `pod_run`, do NOT ssh
    anywhere, do NOT scp, and do NOT write an ssh override.**
  - **FRAME EXTRACTION IS LOCAL**, from `data/videos/bridge/wnba_01.f137.mp4` -- see step 1 for the exact
    identity checks, which are BINDING.
  - **THE LOCATION WORK IS LOCAL**, on the frames you just extracted.
  - **GATE: none.** No pod, no GPU, no shared resource. Decoding is CPU-only and reads one local file.
  - **DISK GUARD: none needed.** You write 24 JPEGs under `docs/evidence/`. **Download nothing, delete
    nothing, and do not touch any file under `data/` -- it is read-only to you and gitignored.**
  - **HEADLESS ONLY.** Never `cv2.imshow`; write images to disk and read them back.

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
  1. **EXTRACT EXACTLY THESE 24 FRAMES, CLIP-WIDE, FROM THE LOCAL FILE
     `data/videos/bridge/wnba_01.f137.mp4`: frame index `round(i * 174429 / 23)` for `i = 0..23`.**
     **Print the list you extracted and confirm it matches that formula.** **State the exact ffmpeg command
     and confirm the frames are full 1920x1080 native, NOT cropped and NOT resized.**
     **BINDING IDENTITY CHECK BEFORE YOU EXTRACT ANYTHING -- run `ffprobe` and report all four values
     verbatim; if ANY of them differs, STOP and report SOURCE MISMATCH rather than extracting:**
     **width 1920, height 1080, avg_frame_rate 30/1, duration 5814.333333 s (= 174,430 frames at 30 fps).**
     Measured on 2026-09-07: 2,841,750,689 bytes, sha256
     `f2421bc24e5cbb28f41fa79f9ea755b2eeff4daebd48dc5496cc97e5617cf9d3`.
     **HONESTY NOTE YOU MUST CARRY INTO THE MEMO, NOT DISCOVER:** the original spec named the POD file
     `wnba__wnba_01.mp4` (2,796 MB, sha256 beginning `f361ad7a32ccc6d98ae8e98e`). **The local file's sha256
     does NOT match that prefix.** It has the same resolution, frame rate and frame count, and the most
     likely reason is that the local copy is the video-only DASH stream while the pod file was the muxed
     version -- **but that is a HYPOTHESIS, not a verified fact, and you must state it as one.** **Whether
     frame index N is the same picture in both files is therefore NOT established here; establishing it is
     the VERIFIER's job at merge time, because it requires looking at pass B and you may not.** **Say all
     of this plainly in your memo and put it in the NOT VERIFIED list.**
     **DO NOT USE `data/footage_corpus/g130_recensus/wnba__wnba_01_1080p.mp4`** -- measured on 2026-09-07 it
     is 308,078,882 bytes and only **18,060 frames (600.067 s)**, so 22 of the 24 required indices do not
     exist in it. **A silent short read there would produce a set that looks right and is not.**
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
     `docs/evidence/tracking/g296a_located_players_artifact/located_players.csv` with the
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
EVIDENCE: `docs/evidence/tracking/g296a_located_players_2026-09-07.md` with the frame list and
formula check, the ffmpeg command, the schema confirmation, per-frame summary, confidence counts, the
pre-join commit sha, the ffprobe identity check verbatim, and a NOT VERIFIED list that names the sha256
mismatch against the pod file. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO, by APPENDING
one line -- NEVER rewrite that file.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted -- **pin the 24 frame indices against the formula and
pin the exact CSV headers.** **NEVER a full pytest.** **If a commit grows an allowlisted file, raise its
entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
