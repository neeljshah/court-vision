GAP G351 | sport basketball | worktree a7 | log cx_g351_ball_coordinate_scale

**PRODUCER-DEFECT CENSUS ROW (from G349; codex-friendly, local, read-only code).** `src/`, `kernel/`, `api/`
and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/tracking/`. NEVER write `data/registry/`,
never flip a flag, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. No video, no GPU, no pod.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; per-clip batch reads; check free RAM first).
Inputs: the local tracking mirror `data/tracking/<game_id>/tracking_data.csv` + `ball_tracking.csv` (~360
clips) and the 2 committed WNBA tables; the writers in `src/pipeline/unified_pipeline.py` (ball table
~:1985-1991 per G320; player rows at the single row-build site per G325/G333) and `src/tracking/
ball_detect_track.py` (:791-816, :908-956 per G320).

**WHY THIS ROW EXISTS.** G349 (2026-09-08) located where the ball evidence dies: on 26 windows the ball is
inside the sealed 60 px (720p-scaled) radius of ANY player box on 8 of 1,560 frames, and 3 of 26 windows
(0022500630, 0022500906, 0022500799) carry `ball_x2d` values 2-30x outside the player x range -- a
per-window-inconsistent SCALE ANOMALY between the ball table and the player table. If the ball tracker
emits coordinates in a different frame (the 640 detector input, a TOPCUT crop -- G303 found the route feeds
[1,3,352,640] of a TOPCUT crop -- or a resized panorama) for some clips, every ball-player join in image
space is wrong by construction, and G344 / G349's decorative-ball result is a unit defect, not a signal
absence.

**PREMISE (step 0, BINDING before-condition):** across every local clip, per clip: the ball table's x / y
range (p1, p99) vs the player table's x / y range (p1, p99), `source_height` / `source_width` if present in
either table, and the ratio of the ranges. PRINT the per-clip table and the share of clips whose ball
range exceeds the player range by > 1.5x on either axis (n). **If that share is 0 (every clip consistent),
the premise is FALSE: STOP, write the memo, commit, report PREMISE FALSE (and say the G349 anomaly was
window-local).**

METHOD:
  1. **WRITER TRACE.** Cite `file:line` for every coordinate transform between detection and the two
     writers: the detector input size, the TOPCUT crop, any resize / letterbox / panorama mapping, and the
     scale factors applied to player boxes vs ball points (if they differ, name the line).
  2. **CENSUS (`g351_ball_scale_census.py`, <= 200 lines).** Per clip: the axis ratios, the inferred ball
     coordinate frame (original / detector / crop / panorama) by nearest match to known sizes, resolution,
     league, and the daemon code version if a sidecar records it; table with n per inferred frame.
  3. **A CORRECTION PROPOSAL (not applied):** if the writer trace names a missing rescale, a <= 10-line
     PROPOSED diff under `docs/research/organization-sprint/G351_PROPOSED_ball_scale.md` (gitignored; sha256
     in the memo) plus the exact reader-side rescale that G349 / G344 would apply to LANDED tables (so
     existing artifacts can be re-joined without re-tracking). src edits are user-authorized for this
     program but this row PROPOSES because the writer's contract must be confirmed by a rerun.
  4. **RE-JOIN CHECK.** Apply the inferred rescale to the 3 anomalous G349 windows and the 8-frame radius
     survival: report frames within radius before / after (n) -- a screening of whether the unit defect
     explains G349's result.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** a range ratio is a screening for scale, not proof; clips
tracked before and after G333's deployment may differ (record the ledger date per clip); the correction is
proposed, not applied.

ACCEPTANCE RULE:
  metric        = the per-clip range table (n clips, n anomalous); the writer trace with file:line; the
                  inferred-frame table with n; the PROPOSED correction; the re-join check with n
  before        = the ball / player coordinate frames are undocumented; G349 found a 3/26 anomaly
  bar           = every clip classified (no skips); the writer trace names the transform lines; the re-join
                  check reports before / after n on the 3 windows; 0 src edits
  n             = every local clip; the 3 anomalous windows; every writer transform line
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every flag, every landed artifact,
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds (a null re-join is a valid result); **PARTIAL** naming what
                  could not run.
EVIDENCE: `docs/evidence/tracking/g351_ball_coordinate_scale_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g351_ball_coordinate_scale_2026-09-08/ranges.csv`,
`rejoin.csv` (integer cells zero-padded; shares as ADDITIVE per-mille columns). **ADD ONE RESULTS_LEDGER.md
ROW IN THE SAME COMMIT** (append only). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g351_ball_scale_census.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the ratio rule, the known frame
sizes), the census module, the test and the memo skeleton, and exits with the line `agent: PREPARED FOR
FINISHER` plus the exact commands; it must NOT run the census on the mirror itself (Q1). A missing local
mirror or `data/registry` in the worktree is reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
