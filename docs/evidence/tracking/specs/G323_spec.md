GAP G323 | sport all | worktree a20 | log cx_g323_nonplayer_boxes
**SEALED BLIND CENSUS + GATE-TRACE ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ
and IMPORT only. Build in `scripts/platformkit/tracking/`. If a gate belongs in `src/`, the
deliverable is a PROPOSED gate under `docs/research/organization-sprint/`, NOT an edit.**
CONTRACT: `docs/evidence/tracking/VERIFIER_CONTRACT.md` -- read it; self-check every line of section
B (and A3 / A9 / A11 / B7 / B11 / S1 / S4) before reporting.

**WHERE THIS ROW RUNS (per step):** steps 0-1 and 4-6 are **LOCAL** -- arithmetic over the pod
`tracking_data.csv` files fetched READ-ONLY by `scp`/`tar` into the lane scratchpad, **never into
`data/` in the repo** -- plus a read-only source read and a CPU-only `import` of `src/`. Step 2
extracts frames **ON THE POD** with `ffmpeg` into `/tmp/g323/` and `scp`s them out; crops, context
tiles and contact sheets are rendered **LOCAL and HEADLESS** (PIL, never `cv2.imshow`). No GPU, no
GPU lease, no `pod_run`, no write anywhere under `/workspace/nba-ai-system`. **A multi-worker
`track_daemon` is running: NEVER stop, signal, kill or otherwise interfere with it or its stage,
and treat the pod tree as mutating under the read.**

**WHY THIS ROW EXISTS.** G315's 30-panel screen had BOTH of its model raters independently name
crowd, bench, graphic or off-frame content inside boxes the tracker had written as PLAYER
observations, on 12 of 30 panels. G322 then rated 20 oversized boxes and found 9 of 20 in its sealed
NON_SINGLE_PLAYER set, plus 3 more it had sealed as `other` -- a sideline reporter, an in-arena
host, courtside spectators, a scorer's-table barrier and one television commercial. Both of those
were screens of the OVERSIZED tail only. Nobody has asked the question over the WHOLE box-size
range, in more than one region of the image, with more than one rater, or against the gates that are
supposed to stop it. Every non-player box that reaches `tracking_data.csv` becomes a player
observation with a footpoint, a team, a court zone and a distance-to-ball.

**PREMISE (step 0, BINDING before-condition, Q8).** The row asserts two gates exist. Re-measure
BOTH before sampling anything, and print the result:
  (i) TEAM-COLOUR GATE: name the `file:line` that can REJECT a detection on colour and print the
      three HSV ranges it uses at a stated frame brightness.
  (ii) COURT-REGION GATE: `grep -n` for a court mask in `src/pipeline/unified_pipeline.py`. **The
      author's own S2 check found NO `court_mask` there**; the only region reject in the route is
      the map-bounds test on the projected footpoint. Print what you find and NAME the real gate.
**If NEITHER a colour reject nor a region reject exists anywhere in the write route, the premise is
FALSIFIED: STOP, write the memo, commit, report PREMISE FALSE.** If they exist but sit somewhere
other than where the row says, that is a CORRECTED premise, not a falsified one -- say so and go on.

**SURVIVORSHIP, DECLARED UP FRONT (B1).** Every row in `tracking_data.csv` was WRITTEN, so it
already passed every gate in the write route. The gate-rejection count on this sample is therefore
**0 by construction and is NOT the measurement**. Step 5 is a REPRODUCTION check: re-run the gate
function standalone on each crop and confirm it returns the same PASS, then say WHY it passes --
which range matched, with what margin. A gate that passes crowd is the finding; a gate that rejects
a row the tracker wrote would be a reproduction failure and must be reported as one.

METHOD:
  1. **SAMPLE, seeded rule sealed in the PREREG before any frame is cut.** Three games, one per
     source resolution, taken as the **nearest-rank median `share_gt50` game of that resolution in
     the G322 census** (`rank = ceil(0.5 * n)`, ties by `game_id` ascending). The author's own
     computation over the G322 census gives `wnba_06` (1920x1080, rank 4 of 7, 0.0862),
     `wnba_04` (1280x720, rank 7 of 13, 0.0643) and `0022500575_s7200` (640x360, rank 26 of 51,
     0.1878); **recompute it and report any disagreement rather than copying it.** Note in the memo
     that G322's own panel picks differ (`bos_mia_playoffs`, `0022500594_s7200`) -- a different
     median convention, not a contradiction.
     **60 boxes over 6 cells x 10 = 3 box-height terciles x 2 image regions.** Terciles are of
     `ratio = (bbox_y2 - bbox_y1) / (source_height - 60)` at each game's OWN 1/3 and 2/3
     percentiles; region is UPPER when `(bbox_y1 + bbox_y2) / 2 < 0.5 * (source_height - 60)` and
     LOWER otherwise, both in the tracker's POST-TOPCUT space (`TOPCUT = 60`,
     `src/tracking/video_handler.py:11`). **Selection inside a cell: order that cell's rows by
     `sha256("G323|" + game_id + "|" + frame + "|" + player_id)` and take the hash-lowest unused row
     from each game in turn, round-robin over the three games, until the cell holds 10** -- so a
     cell is 4/3/3 across games, a shortfall passes to the next game in order AND IS NAMED, and the
     draw is **never the top tail and never a head slice** (A3/B7). Print n per cell per game.
  2. **RENDER.** One panel per box: the crop plus a context tile (the whole frame with the box
     drawn), headless PIL. Draw BOTH readings as G322 did -- the post-TOPCUT box (`y + 60`) and the
     no-offset box -- so the rendering assumption is visible instead of asserted. **<= 4 contact
     sheets, <= 500 KB each**, panels labelled with an opaque panel id only.
  3. **BLIND RATING BY TWO MODEL RATERS.** Categories, FIXED NOW and stated before any panel is
     viewed: `player_on_court` / `player_bench_or_courtside` / `crowd` / `referee_or_staff` /
     `broadcast_graphic` / `off_frame_or_empty` / `two_or_more_players` / `unreadable`. Exactly one
     per panel. **NON_PLAYER = crowd + referee_or_staff + broadcast_graphic + off_frame_or_empty +
     player_bench_or_courtside** (sealed; `two_or_more_players` is NOT in it).
     Rater A = **Claude Opus 5 (`claude-opus-5[1m]`), declared**; its labels are committed BEFORE
     rater B is dispatched. Rater B = a **codex lane (`gpt-5.6-sol`)** in worktree a20, log
     `cx_r323_rateB.log`, whose prompt carries the sheets, the panel ids and the category list and
     **never rater A's labels**. The lane cannot commit: land its sheet with
     `python /c/Users/neelj/bin/lane_commit.py a20 G323 "<msg>"` and check `--stat` for swept
     directories. Report **raw agreement and Cohen's kappa with its asymptotic standard error**,
     both preregistered, plus the full confusion counts over the categories actually used.
     **HUMAN LABELS ARE THE LIMIT AND MUST BE NAMED AS SUCH**: G315 measured two model raters
     agreeing on only 14 of 30 panels, so no content claim here is a ground truth.
  4. **PER-GAME SHARE.** Per game and per cell, the count of NON_PLAYER panels by each rater and by
     both-agreed, with n. **Counts, and a share whose denominator is the 60 rated panels -- never a
     share extrapolated to the game's own rows**, which were not rated.
  5. **GATE CHECK, read-only.** Re-run the team-colour gate standalone on each of the 60 crops:
     `_adaptive_colors(frame)` from `src/tracking/player_detection.py` on the extracted frame, then
     the same `cv2.inRange` over the upper 70 pct of the crop and the same argmax, **on the UNPADDED
     crop** (`PAD = 15` per border is added by the writer after the gate sees the box, so subtract
     it back and clamp) -- CPU only, no YOLO, no GPU. Report per rated category: how many the gate
     passes, which range matched, and the matched-pixel count. If the region gate cannot be re-run
     standalone because it needs a per-game homography built at run time, **say NOT RE-RUNNABLE and
     pin it by trace instead** -- do not simulate it and do not omit it.
  6. **VERDICT, applied mechanically.** **PREMISE HOLDS iff EITHER rater marks `>= 10 / 60` panels
     NON_PLAYER.** **GATE MISSING iff the gates reject `< 50 pct` of the both-rater-agreed
     NON_PLAYER boxes** -- then write the PROPOSED gate under `docs/research/organization-sprint/`,
     stating what it would reject, what it would cost, and what it CANNOT see. Otherwise GATES
     SUFFICIENT. **APPLY NOTHING to `src/` either way.**

**HONEST LIMITATIONS to state, not discover:** two model raters are not ground truth and no human
labelled anything. 60 panels out of a corpus of 250,369 observations is a SCREEN, not a rate for any
game. The gate-rejection number is 0 by construction (survivorship, above) and the row's value is
the reproduction and the WHY, not that count. Image space only (`coordinate_space = image_px`): no
court, foot, metre or registration claim. The frame-index mapping used to cut frames is an
INFERENCE and G198 is open against it; a systematic off-by-k would move which people sit inside the
drawn rectangles. `imgsz` and `conf` are read from code defaults, not from a pod run record. The pod
tree mutates under the read and most censused games are `passed = false`. Q6: the geometric word for
a box side is **`border`** in every artifact this lane writes; the standalone word 'edge' appears
nowhere.

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = count of the 60 rated panels in the sealed NON_PLAYER set, per rater, denominator
                  = the 60 rated panels; plus raw agreement and Cohen's kappa (asymptotic SE) over
                  the same 60; plus the per-category gate PASS count, denominator = 60
  before        = G315: 12 of 30 panels named non-player content by both raters, on a same-id step
                  screen. G322: 9 of 20 in its sealed non-single-player set, oversized tail only.
                  Across the box-size range, across image regions, with two raters and a kappa,
                  and against the gates: NEVER MEASURED.
  bar           = the prereg is committed ALONE before the first frame is cut and before the first
                  panel is viewed, and names the sample rule, the seed, the eight categories, the
                  NON_PLAYER set, the agreement statistics and the gate procedure; all 60 panels
                  come from the sealed 6-cell rule with n printed per cell per game and every
                  shortfall named; both raters label all 60 with rater B never seeing rater A's
                  labels; the gate is re-run on all 60 crops or its non-re-runnability is pinned by
                  `file:line`; the two verdicts follow the `>= 10/60` and `< 50 pct` rules
                  mechanically
  n             = 60 rated panels (SAMPLED, >= 30); 6 cells x 10 (CONSTRUCT: cells enumerated)
  eye check     = the 60 panels themselves, drawn by the sealed seeded round-robin over 6 cells and
                  3 games -- no head slice, no top tail, no oversized-only tail
  must not move = `data/tracking/` and everything else on the pod (READ ONLY); the running
                  `track_daemon`; `src/`, `domains/`, `api/`, `kernel/`, `intel/`;
                  `scripts/platformkit/tracking_harness.py`; `data/registry/`; every threshold,
                  every feature flag, every historical ledger row; the eight categories, the
                  NON_PLAYER set, the seed, and the `10/60` and `50 pct` bars above, which are FIXED
                  NOW and never moved; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
NON-TAUTOLOGY: the sample covers all six cells of all three games and excludes no row of any cell;
a game contributes zero to a cell only when it has zero rows there, and every such shortfall is
named. The gate-check denominator is all 60 crops, not the ones that happen to be re-runnable. If
excluding rows is what makes a number good, the metric is circular -- say so and report REJECT.
EVIDENCE: `docs/evidence/tracking/g323_nonplayer_boxes_2026-09-07.md` (<= 60 lines, line 1 = the
verdict) with the 6-cell sample table, both raters' per-category counts, agreement and kappa with
SE, the gate-check table, a **NOT VERIFIED** list, time spent, and the SHA-256 of every artifact.
The sample CSV and both raters' label CSVs are committed beside it. **ADD ONE RESULTS_LEDGER.md ROW
IN THE SAME COMMIT** (one `>>` append). **Cite the G322 census by path and SHA-256 in the prereg;
if G322 is later corrected, this row re-seals.**
TEST: `tests/platformkit/test_g323_nonplayer_boxes.py` -- a SYNTHETIC construct pinning the tercile
and region assignment, the seeded round-robin cell draw with a named shortfall, the raw-agreement
and Cohen's-kappa arithmetic (including its asymptotic SE) against hand-computed values, and the
un-padding of the crop before the gate. **n = 1 (CONSTRUCT).** Run that ONE file, plus
`tests/platformkit/test_loc_rail_scope.py` (A12). **NEVER a full pytest.**
COMMIT: explicit pathspec only, in the worktree, no push. ASCII stdout. `<= 300` LOC per file.
Commit order: prereg ALONE; sample + sheets; rater A labels; rater B labels (via `lane_commit.py`);
agreement + gate check + memo + test + ledger row. **NEVER PARK.**

## VERSION 2026-09-07 (attempt 1: sealed 60-box two-rater blind census + gate reproduction)
Written by the orchestrator against the G323 row of the `G322-G323 allocation register` block of
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. S2 premise checks done by the author before
dispatch, over the WHOLE set and not its first rows: (1) `grep -n "court_mask"
src/pipeline/unified_pipeline.py` returns NOTHING -- the row's "court mask in unified_pipeline.py"
does not exist, and the only region reject in the write route is the projected-footpoint map-bounds
test at `src/tracking/advanced_tracker.py:1429-1431`; the spec is written to CORRECT that premise,
not to inherit it. (2) The colour reject DOES exist, at `src/tracking/advanced_tracker.py:1341-1356`
(`if not team: continue` after an argmax over three `cv2.inRange` masks), and
`src/tracking/player_detection.py` imports only `cv2`, `numpy` and `.utils.plot_tools`, so the gate
is re-runnable standalone on CPU -- verified by the author with an actual import under the
`basketball_ai` conda interpreter, which returned `green [0,44,34]-[179,255,220]`,
`referee [0,0,0]-[255,35,70]`, `white [0,0,155]-[179,25,255]` at brightness 90. (3) All three
median-share sources exist on the pod and probe at the resolutions the census claims:
`wnba__wnba_06.mp4` 430,058,965 B 1920x1080 30/1 28,674 frames; `wnba__wnba_04.mp4` 135,744,701 B
1280x720 30/1 28,819; `nba__0022500575_s7200.mp4` 11,449,336 B 640x360 30000/1001 4,002.
Consumes G322 (worktree a21, commit `a5056025e`, NOT YET LANDED): census
`docs/evidence/tracking/g322_oversized_boxes_census_2026-09-07.csv`, SHA-256
`73bc654a90bd28effeceacd031ecc290633d063edc4bc56c8973574a60dfe4bd`. Attempt 1 of 2.
