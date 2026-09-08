GAP G325 | sport all | worktree a6 | log cx_g325_offframe_boxes
**CENSUS + PRODUCER-TRACE ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and
IMPORT only. Build in `scripts/platformkit/tracking/`. If a drop belongs in `src/`, the deliverable
is a PROPOSED diff under `docs/research/organization-sprint/`, NOT an edit.**
CONTRACT: `docs/evidence/tracking/VERIFIER_CONTRACT.md` -- read it; self-check every line of section
B (and A9 / A11 / B11 / Q6 / Q7 / S1 / S4) before reporting.

**WHERE THIS ROW RUNS (per step):** every step is **LOCAL** -- arithmetic over pod
`tracking_data.csv` files fetched READ-ONLY by one `ssh` stream into the lane scratchpad, **never
into `data/` in the repo** -- plus a read-only source read of `src/`. No frame is decoded, no image
is rendered, no GPU is leased, no `pod_run`, and nothing anywhere under `/workspace/nba-ai-system`
is written. **A multi-worker `track_daemon` is running: NEVER stop, signal, kill or otherwise
interfere with it or its stage, and treat the pod tree as mutating under the read.** A volume warden
may delete corpus sources during this row; only the CSV tables are needed, so that is not a blocker.

**WHY THIS ROW EXISTS.** G323's sealed 60-box two-rater census (worktree a20, attempt 2, memo
`g323_nonplayer_boxes_attempt2_2026-09-07.md:38,:47`) recorded, as a CONTAINMENT ANOMALY it could
not size, that **2 of its 60 sampled player observations carry a bounding box lying wholly outside
the decoded frame** -- panel P14 (`wnba_06`) and panel P48 (`wnba_04`), which clamp to crop widths
of -516 px and -2 px, on 2 of its 3 games -- and that both production gates PASS them: the box was
written to `tracking_data.csv`, and the team-colour reject at
`src/tracking/advanced_tracker.py:1341-1356` is the only content gate in the route (G323 established
that the court mask the earlier register row assumed **does not exist**). A box wholly outside the
frame has no pixels, so its team label, its crop-derived features and its footpoint
(`src/tracking/advanced_tracker.py:1411`) are all derived from nothing. G323 saw 2 of 60 on 3 games
and stopped there. **The corpus-wide share and the producing site are UNMEASURED**, and that is this
row.

**PREMISE (step 0, BINDING before-condition):** recompute the wholly-outside count on G323's own
three games (`wnba_06`, `wnba_04`, `0022500575_s7200`) from the pod tables and **PRINT, per game:
rows, the `frame_w` and `frame_h` used and the field each came from, and the count and share of
rows wholly outside.** **If the count is 0 on all three games AND 0 pooled over the whole enumerated
corpus, the premise is FALSIFIED: STOP, write the memo, commit, report PREMISE FALSE** -- a valid
result that earns its own register row (Q8).

METHOD:
  1. **CENSUS OVER EVERY COMPLETED GAME, NOT A SAMPLE.** Take a snapshot of
     `/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`, record its SHA-256 and line
     count, and enumerate **every** row with `status == "tracked"` and `rows > 0` whose
     `tracking_data.csv` is non-empty. Per game print: `rows` (= player observations),
     `source_resolution`, the `frame_w` and `frame_h` used, and the count and share **wholly
     outside** the frame -- `bbox_x2 <= 0` OR `bbox_x1 >= frame_w` OR `bbox_y2 <= 0` OR
     `bbox_y1 >= frame_h` -- plus, as a SECONDARY, the count and share **partially outside** (any of
     `bbox_x1 < 0`, `bbox_y1 < 0`, `bbox_x2 > frame_w`, `bbox_y2 > frame_h`, and not wholly outside),
     **each with its own n**; then the same two shares aggregated per source resolution with n per
     cell. **STATE WHERE `frame_w` AND `frame_h` CAME FROM** (S4: name the ledger file and the
     field, not just the count). `tracking_data.csv` carries `source_height` but **no width column**,
     so `frame_w` must come from the ledger's `source_resolution`; print the table's own
     `source_height` beside the ledger's `source_height` and name every game where they disagree.
     **The boxes are written in the TOPCUT-cropped space** (`frame = frame[TOPCUT:]`,
     `src/pipeline/unified_pipeline.py`; `TOPCUT = 60`, `src/tracking/video_handler.py:11`), so the
     PRIMARY `frame_h` is `source_height - TOPCUT` and the naive `source_height` reading is printed
     beside it as a SECONDARY, both with n. Print also the PAD-removed diagnostic: re-test the
     wholly-outside condition on the detector's own box (`bbox_x1 + PAD`, `bbox_y1 + PAD`,
     `bbox_x2 - PAD`, `bbox_y2 - PAD`; `PAD = 15`, `src/tracking/player_detection.py:20`). Record
     the SHA-256 and byte size of every table read (A9/A11). Any game whose table is absent, empty,
     header-only or unreadable is listed BY NAME as EXCLUDED with the reason -- never dropped
     silently (B1). Confirm before any arithmetic that the writer demuxes its `(y1, x1, y2, x2)`
     tuple into the four named columns correctly (`src/pipeline/unified_pipeline.py`, the
     `bbox_x1 = bbox[1]` block) and cite it by `file:line`: if the columns were transposed, every
     inequality above would be measuring the wrong axis.
  2. **PRODUCER TRACE, READ-ONLY.** Split the wholly-outside rows by whether the observation is
     detector-matched or Kalman-coasting **using the table's OWN columns**, and name the column and
     its definition by `file:line`. If no such column exists, say **NOT DETERMINABLE** and name the
     missing column -- do not infer a site from prose. Then name an exact `file:line` for each of:
     the Kalman coasting path (`_make_kf`, the transition matrix, `_kf_predict_bbox`, and the
     per-frame `previous_bb` overwrite), **the presence or explicit absence of any clamp on the
     predicted box**, the `PAD` applied before the box is written, the footpoint derivation, and
     **the actual CSV writer** -- note that `scripts/platformkit/track_daemon_done.py` fsyncs and
     adjudicates the table but may not be what writes its rows; find and name what does, by
     `file:line`, and say plainly if the register row's assumption about the writer is wrong. State
     whether a wholly-outside box (a) can be emitted by the detector at all, given how the detector's
     boxes are bounded and how `PAD` widens them, (b) is a Kalman prediction drifting past the
     border unclamped, or (c) is an artefact of the `frame_w` / `frame_h` the census divides by.
     **(c) is a REAL possible outcome and would make this a units defect, not a tracker one** -- say
     which, with the numbers.
  3. **VERDICT AND PROPOSAL, by these fixed rules and no others.**
     **PREMISE HOLDS** iff the pooled wholly-outside share is `>= 1/1000` OR at least one game's
     share is `>= 1/100`. **SITE PINNED** iff `>= 90` pct of the wholly-outside rows carry the
     coasting flag (equivalently `>= 9/10`); if the flag does not exist, report **NOT DETERMINABLE**
     and name the missing column. A **PROPOSED diff under `docs/research/organization-sprint/`** for
     the writer to drop these rows is written **IF AND ONLY IF SITE PINNED**; otherwise propose
     nothing. **APPLY NOTHING to `src/` either way.**

**HONEST LIMITATIONS to state, not discover:** a wholly-outside box is a defect in the sense that it
has no pixels, but this row does not measure what any downstream number would do if such rows were
dropped, and does not claim that dropping them improves anything. Image space only
(`coordinate_space = image_px`): no court, foot, metre or registration claim. The census counts
numbers in a CSV; no frame is decoded and no image is looked at, so the two G323 panels remain the
only visual evidence and they are 2 boxes, rated by models. The `frame_w` comes from a ledger field
that was never checked against the decoded stream. The pod tree is mutating under the read. Most
censused games are `passed = false`.

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-game share of player observations WHOLLY OUTSIDE the frame
                  (`bbox_x2 <= 0` or `bbox_x1 >= frame_w` or `bbox_y2 <= 0` or
                  `bbox_y1 >= frame_h`), denominator = that game's own usable row count in its own
                  `tracking_data.csv`; plus the partially-outside secondary, the per-resolution
                  aggregate, the `source_height` vs `source_height - 60` pair and the PAD-removed
                  diagnostic, each with its own n
  before        = G323: 2 of 60 sampled boxes on 2 of 3 games (`wnba_06` P14, `wnba_04` P48),
                  attempt-2 memo `:38`. Corpus-wide share: NEVER MEASURED. Producing site: NEVER
                  TRACED. Whether the writer should drop them: NEVER ADJUDICATED.
  bar           = the census covers EVERY `status == "tracked"` game with `rows > 0` and a non-empty
                  table in the named ledger snapshot, with n printed per cell and every exclusion
                  named; the trace names a `file:line` for the matched/coasting column and its
                  definition, the Kalman coasting path, the clamp or its absence, the `PAD`, the
                  footpoint and the real CSV writer, and states (a)/(b)/(c); the verdict follows the
                  `>= 1/1000` pooled / `>= 1/100` per-game and `>= 90` pct rules mechanically
  n             = every tracked game in the snapshot (CONSTRUCT: enumerated, not sampled); Q7 binds
                  the printing of n per cell, not a `n >= 30` sampling rail
  eye check     = NONE. This row decodes no frame and renders no panel; the only visual evidence in
                  the file is G323's 2 panels, cited as 2 panels rated by models, never as a rate.
  must not move = `data/tracking/` and everything else on the pod (READ ONLY); the running
                  `track_daemon`; `src/`, `domains/`, `api/`, `kernel/`, `intel/`;
                  `scripts/platformkit/tracking_harness.py`; `data/registry/`; every threshold,
                  every feature flag, every historical ledger row; the `1/1000`, `1/100` and
                  `90` pct bars above, which are FIXED NOW and never moved;
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` (the orchestrator owns it)
NON-TAUTOLOGY: the census covers every row of every enumerated table and excludes none; games are
excluded only for an absent, empty or unreadable table and each is named. A row with a missing or
non-numeric box coordinate is COUNTED and REPORTED, never silently skipped into the denominator's
favour. If excluding rows is what makes a number good, the metric is circular -- say so and report
REJECT yourself.
VOCABULARY RAIL (Q6, binding): the geometric word for a frame side is `border` or `boundary` in
every file this row writes; `grep -inE "\bedge\b"` over every new file must return ZERO hits before
the prereg is sealed and before every commit. Every share is printed as
`numerator/denominator (~x.xxxxe-1)` so that no cell can reproduce a retracted digit string by
coincidence; grep each new file for the retracted sequences before committing.
EVIDENCE: `docs/evidence/tracking/g325_offframe_boxes_2026-09-07.md` (<= 60 lines, **line 1 = the
verdict**) with the per-game and per-resolution census table, n per cell, the `file:line` trace, a
**NOT VERIFIED** list, time spent, and the SHA-256 of every artifact. The census CSVs are committed
beside it. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append).
TEST: `tests/platformkit/test_g325_offframe_boxes.py` -- a SYNTHETIC construct pinning the four
wholly-outside inequalities on each side independently, the partially-outside secondary, the
PAD-removed and TOPCUT variants, the share arithmetic and the matched/coasting split against
hand-computed values, including the boundary cases `bbox_x2 == 0` and `bbox_x1 == frame_w`.
**n = 1 (CONSTRUCT).** Run that ONE file with `--confcutdir=tests/platformkit`, plus
`tests/platformkit/test_loc_rail_scope.py` (A12). **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. `<= 300` LOC per file. Prereg sealed as its OWN commit
first, before the first measurement. No push from the worktree. **NEVER PARK.**

## VERSION 2026-09-07 (attempt 1: corpus census + producer trace + writer adjudication)
Written by the orchestrator against the G325 row of the `G325-G326 allocation register` block of
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. S2 premise check done by the author before
dispatch, on the WHOLE set and not on its first rows: the pod ledger snapshot read on 2026-09-07
carries 135 lines, 110 `tracked` with `rows > 0`, 24 `thin` and 1 `timeout`, across three source
resolutions (55 x 640x360, 48 x 1280x720, 7 x 1920x1080), so the census set is the whole ledger and
not G323's 3 games; `tracking_data.csv` carries `bbox_x1..bbox_y2`, `confidence` and its own
`source_height`, but **no width column**, which is why step 1 requires `frame_w` to be sourced from
the ledger and named. The author also confirmed by reading `src/` that the matched/coasting split
of step 2 is DETERMINABLE from a column the table already carries, so `NOT DETERMINABLE` is a
fallback the lane should not need. Attempt 1 of 2. Machinery to reuse: `g322_oversized_boxes.py`
and `g322_producer_trace_2026-09-07.md` in worktree a21 (commit `a5056025e`, NOT YET ON MASTER) for
the table fetch, the `frame_h` sourcing and the tracker route; `g314_ball_inferred_coords.py` on
master for the read-only fetch pattern.
