GAP G322 | sport all | worktree a21 | log cx_g322_oversized_boxes
**CENSUS + TRACE + SEALED-SHEET ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and
IMPORT only. Build in `scripts/platformkit/tracking/`. If the filter belongs in `src/`, the
deliverable is a PROPOSED diff under `docs/research/organization-sprint/`, NOT an edit.**
CONTRACT: `docs/evidence/tracking/VERIFIER_CONTRACT.md` -- read it; self-check every line of section
B (and A9 / A11 / B11 / S1 / S4) before reporting.

**WHERE THIS ROW RUNS (per step):** step 0-2 and 4 are **LOCAL** -- arithmetic over pod
`tracking_data.csv` files fetched READ-ONLY by `scp` into the lane scratchpad, **never into `data/`
in the repo** -- plus a read-only source read of `src/`. Step 3 extracts frames **ON THE POD** with
`ffmpeg` into `/tmp/g322/` and `scp`s them out; the panels are rendered **LOCAL and HEADLESS** (PIL,
never `cv2.imshow`). No GPU, no GPU lease, no `pod_run`, no write anywhere under
`/workspace/nba-ai-system`. **A 16-worker `track_daemon` is running: NEVER stop, signal, kill or
otherwise interfere with it or its stage, and treat the pod tree as mutating under the read.**

**WHY THIS ROW EXISTS.** G315's screen measured, as a control that FAILED to discriminate, that a
bbox taller than half the frame height covers **0.2187 of all steps in `ncaa_basketball_mRkuGgeECak`
(1080p) and 0.2395 in `wnba_05` (720p)** (`g315_same_id_step_screen_2026-09-07.md`, landed
396731480). A box that tall cannot be one standing player, so for those rows the bbox bottom-centre
is not a player's feet -- and the bottom-centre is exactly what the tracker projects through the
homography (`src/tracking/advanced_tracker.py:1411`). Every footpoint-derived quantity built on
those rows -- court position, spacing, distance-to-ball, G315's own step -- is then measuring a box,
not a person. G315 measured this on 2 of 3 games over STEPS; nobody has measured it over
OBSERVATIONS, on the rest of the corpus, or at any other resolution, and nobody has traced where
such a box enters.

**PREMISE (step 0, BINDING before-condition):** re-measure the two G315 games from the pod tables
and **PRINT, per game: rows, `frame_h` used and its source, and the share of rows with
`bbox_y2 - bbox_y1 > 0.5 * frame_h`.** **If that share is below 0.10 on BOTH games, the premise is
FALSIFIED: STOP, write the memo, commit, report PREMISE FALSE** -- a valid result that earns its own
register row (Q8).

METHOD:
  1. **CENSUS OVER EVERY COMPLETED GAME, NOT A SAMPLE.** Take a snapshot of
     `/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`, record its SHA-256 and line
     count, and enumerate **every** row with `status == "tracked"` and a non-empty
     `tracking_data.csv`. Per game print: `rows` (= player observations), `source_resolution`,
     `frame_h`, and the share with `box_h > 0.5 * frame_h` plus the secondary cuts `> 0.33` and
     `> 0.25`, **each with its own n**; then the same three shares aggregated per source resolution
     with n per cell. **STATE WHICH `frame_h` YOU USED** -- the ledger's `source_height` or the
     table's own `source_height` column -- **print both and print any game where they disagree**
     (S4: name the field, not just the count). Report `max(bbox_y2)` per game against `frame_h`:
     a bottom edge past the frame is evidence the boxes are not in the space you assumed.
     Record the SHA-256 and byte size of every table read (A9/A11). Any game whose table is empty,
     header-only or unreadable is listed by name as EXCLUDED with the reason -- never dropped
     silently (B1).
  2. **PRODUCER TRACE, READ-ONLY**, naming an exact `file:line` for each of: the detector call and
     its `imgsz` / `conf` / class list; the TOPCUT crop that defines the frame the detector sees;
     any NMS or class-merge setting; **any box clamp or size filter, or the explicit absence of
     one**; the PAD applied before the box is written; and the footpoint derivation with its
     fallback. State plainly whether the oversized box is (a) emitted that way by the detector,
     (b) grown after detection, or (c) an artefact of a coordinate-space mismatch between the
     written box and the `frame_h` the census divides by. **(c) is a REAL possible outcome and
     would make this a units defect, not a detector one** -- say which, with the numbers.
  3. **SEALED CONTACT-SHEET CHECK.** The selection rule, the panel count and the classification
     rubric are written into the PREREG and committed ALONE **before the first frame is cut and
     before any panel is viewed**. Rule: **20 oversized boxes, STRATIFIED over games and over
     box-height deciles -- never the top tail only** (A3/B7). Classes, fixed now:
     `crowd / bench-or-courtside / broadcast-graphic / two-or-more-players / one-player-close-to-camera
     / other`. Frames cut on the pod with `ffmpeg` into `/tmp/g322/`, panels rendered headless with
     the box drawn. The rater is **a declared MODEL rater (Claude Opus 5, `claude-opus-5[1m]`)**,
     and G315 measured that two model raters agreed on only **14/30** of its panels, so **REPORT
     COUNTS PER CLASS, NEVER A RATE, and name human labels as the limit.**
  4. **VERDICT AND PROPOSAL. PREMISE HOLDS iff at least one game's `> 0.5` share is `>= 0.10`.**
     Name the ENTRY POINT only if step 2 pins it with numbers; if it does not, say NOT PINNED.
     Write a PROPOSED diff under `docs/research/organization-sprint/` **only if the sheet shows
     `>= 15/20` panels classified as something other than one-player-close-to-camera**; otherwise
     propose nothing. **APPLY NOTHING to `src/` either way.**

**HONEST LIMITATIONS to state, not discover:** a share is not a defect rate -- an oversized box may
be a correct detection of a player genuinely close to the camera, and this row cannot tell the two
apart without labels. 20 panels rated by one model rater is a SCREEN for whether a labelling effort
is worth mounting, not a measurement of content. Image space only (`coordinate_space = image_px`):
no court, foot, metre or registration claim. The census counts numbers in a CSV; only the 20 panels
touch an image. The frame-index mapping used to cut frames is an INFERENCE (G198 is open against
it). The pod tree is mutating under the read. Most censused games are `passed = false`.

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-game share of player observations with `box_h > 0.5 * frame_h`, denominator =
                  that game's own row count in its `tracking_data.csv`; plus the `> 0.33` and
                  `> 0.25` cuts and the per-resolution aggregate, each with its own n
  before        = G315: 0.2187 `ncaa_basketball_mRkuGgeECak` / 0.2395 `wnba_05` / 0.0000
                  `ncaa_basketball_sRtHQbywiTE`, over STEPS on 3 games; over OBSERVATIONS, across
                  the rest of the corpus, and at 360p: NEVER MEASURED. Entry point: NOT TRACED.
  bar           = the census covers EVERY `status == "tracked"` game with a non-empty table in the
                  named ledger snapshot with n printed per cell and every exclusion named; the trace
                  names a `file:line` for the detector call, the TOPCUT crop, the size filter (or
                  its absence), the PAD and the footpoint derivation, and states (a)/(b)/(c); the 20
                  panels come from the sealed stratified rule and are classified under the rubric
                  sealed before viewing; the verdict follows the `>= 0.10` rule mechanically
  n             = every tracked game in the snapshot (CONSTRUCT: enumerated, not sampled)
  eye check     = 20 panels, stratified over games and box-height deciles, no head slice, no top
                  tail. **These 20 are an EYE CHECK, not a sampled metric: counts only, no rate is
                  computed from them and none may be quoted.**
  must not move = `data/tracking/` and everything else on the pod (READ ONLY); the running
                  `track_daemon`; `src/`, `domains/`, `api/`, `kernel/`, `intel/`;
                  `scripts/platformkit/tracking_harness.py`; `data/registry/`; every threshold,
                  every feature flag, every historical ledger row; the 0.5 / 0.33 / 0.25 cuts and
                  the 0.10 and 15/20 bars above, which are FIXED NOW and never moved;
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` (the orchestrator owns it)
NON-TAUTOLOGY: the census covers every row of every enumerated table and excludes none; games are
excluded only for an empty or unreadable table and each is named. If excluding rows is what makes a
number good, the metric is circular -- say so and report REJECT yourself.
EVIDENCE: `docs/evidence/tracking/g322_oversized_boxes_2026-09-07.md` (<= 60 lines, line 1 = the
verdict) with the per-game and per-resolution census table, n per cell, the `file:line` trace, the
panel counts per class, a **NOT VERIFIED** list, time spent, and the SHA-256 of every artifact. The
census CSV is committed beside it; **<= 3 contact sheets, <= 500 KB each.** **ADD ONE
RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append).
TEST: `tests/platformkit/test_g322_oversized_boxes.py` -- a SYNTHETIC construct pinning the
`box_h`, the three cuts, the share arithmetic and the decile-stratified selection against
hand-computed values. **n = 1 (CONSTRUCT).** Run that ONE file, plus
`tests/platformkit/test_loc_rail_scope.py` (A12). **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. `<= 300` LOC per file. Prereg sealed as its OWN commit
first, before the first measurement. No push from the worktree. **NEVER PARK.**

## VERSION 2026-09-07 (attempt 1: census + producer trace + sealed 20-panel sheet)
Written by the orchestrator against the G322 row of the `G322-G323 allocation register` block of
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. S2 premise check done by the author before
dispatch: the pod ledger snapshot read on 2026-09-07 carries 92 rows, 69 `tracked` and 23 `thin`,
across three source resolutions (1920x1080, 1280x720, 640x360), so the census set is the whole
ledger and not the 3 G315 games; `tracking_data.csv` carries `bbox_x1..bbox_y2` and its own
`source_height` column, so the census needs no join. Attempt 1 of 2.
