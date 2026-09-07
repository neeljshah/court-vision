GAP G314 | sport all | worktree aXX | log g314_ball_inferred_coords
**TRACE + CONSTRUCT ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT
only. Build in `scripts/platformkit/`. If the cause sits in `src/`, the deliverable is a PROPOSED
diff file under `docs/research/organization-sprint/`, NOT an edit, and the row STOPS there.**

**WHERE THIS ROW RUNS:** LOCAL. The premise reads pod `tracking_data.csv` files fetched READ-ONLY
by `scp` into a scratchpad -- **never into `data/` in the repo.** **NEVER stop, signal or interfere
with `track_daemon`.** No GPU, no GPU lease.

**WHY THIS ROW EXISTS.** G309 measured that `ball_valid_share` -- rows with a finite `ball_x2d` AND
`ball_y2d`, over `ball_rows` -- equals `ball_detected / ball_rows` **exactly, in all 15 games**.
The 0-311 `ball_inferred` rows per game (311 in `wnba_05`, 273 in `wnba_02`, 54 in
`ncaa_basketball_mRkuGgeECak`, 0 in seven games) therefore carry **NO coordinate at all**: the
inferred flag is set and the position it is supposed to carry is missing. An inference that emits a
label without a value is worse than no inference -- a downstream reader that trusts the flag reads
a state that has no position in it, and every ball-possession or ball-proximity feature built on
`ball_inferred` is reading a hole.

**PREMISE (step 0, BINDING before-condition):** on **2** censused games with a nonzero
`ball_inferred` count (`wnba_05` = 311 and `wnba_02` = 273 at census time), fetch the pod
`tracking_data.csv` and **PRINT, per game: `ball_rows`, `ball_detected`, `ball_inferred`, and the
count of `ball_inferred` rows carrying a finite `ball_x2d` AND `ball_y2d`.** **If that last count
is not 0 on both games, the premise is FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **TRACE WHERE INFERRED ROWS ARE EMITTED**, read-only: `scripts/run_clip.py` and the ball path
     in `src/pipeline/unified_pipeline.py` / `src/tracking/`. **Name the emitting site as
     `file:line`** and state whether the coordinate is (a) never computed, (b) computed and then
     dropped before the writer, or (c) computed and written to a column the census does not read.
     **(c) is a REAL possible outcome and would make this a naming defect, not a data one** -- say
     which of the three it is, with the evidence.
  2. **CONSTRUCT TEST** in `scripts/platformkit/` on synthetic ball observations with a gap: show
     that the emitted inferred row carries the flag and no finite coordinate pair.
  3. **FIX IN THE SAFE AREA OR PROPOSE.** If the defect is confined to `scripts/platformkit/`, fix
     it there. If it sits in `src/`, write
     `docs/research/organization-sprint/PROPOSED-<name>-2026-09-07.md` and **apply NOTHING.**
  4. **CHANGE NOTHING ELSE.** No threshold, no production default, no register edit, no adoption.

**HONEST LIMITATIONS to state, not discover:** **a coordinate is not a correct coordinate.** Making
the inferred rows carry a position says nothing about whether that position is where the ball was;
this row measures neither recall, precision, accuracy nor registration, and says so in those words.
Image space only (`coordinate_space = image_px`): no court, foot, metre or registration claim. All
13 adjudicated games are `passed = false`. The census counted flags in a CSV and did not decode one
frame of video, so **no ball position here has ever been checked against an image.**

ACCEPTANCE RULE:
  metric        = the four printed per-game counts on 2 games; the emitting site as `file:line`;
                  the (a)/(b)/(c) determination; the construct result
  before        = `ball_valid_share == ball_detected / ball_rows` in 15/15 census games, so 0 of the
                  inferred rows carries a coordinate; the cause NOT traced (G309 says so)
  bar           = the emitting site is named with a `file:line`, the construct reproduces the
                  flag-without-coordinate row, and either a PROPOSED diff exists or the fix is
                  demonstrably confined to `scripts/platformkit/`
  n             = 2 pod games (premise) + 1 synthetic construct
  eye check     = NONE. No frames, no renders, no labels. Say that rather than implying validation.
  must not move = `data/tracking/` on the pod (READ ONLY); the running `track_daemon`; `src/`,
                  `domains/`, `api/`, `kernel/`, `intel/`; `tracking_harness.py`; every threshold
EVIDENCE: `docs/evidence/tracking/g314_ball_inferred_coords_2026-09-07.md` (<= 60 lines) with the
per-game counts, the `file:line`, the construct result, the proposed-diff path if any, and a **NOT
VERIFIED** list. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append). **Do NOT
edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: `tests/platformkit/test_g314_ball_inferred_coords.py` -- the construct of step 2.
**n = 1 (CONSTRUCT).** Run that ONE file. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first. **NEVER PARK.**
