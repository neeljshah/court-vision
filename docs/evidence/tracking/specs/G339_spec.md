GAP G339 | sport basketball | worktree a13 | log cx_g339_ball_table_consumers

**TRACE + CENSUS ROW (local, read-only code; codex-friendly).** `src/`, `kernel/`, `api/` and `intel/`
are READ and IMPORT only. Build in `scripts/platformkit/tracking/`. NEVER write `data/registry/`, never
flip a flag, never claim an edge, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL only. No pod, no GPU, no video. Inputs: the committed repo, the two
committed WNBA ball tables under the G314/G320 artifacts, and the G335 attempt-2 memo
(`docs/evidence/tracking/g335_ball_detection_coverage_2026-09-08.md` once landed; if absent, the
orchestrator's copy is quoted in this spec: pod census 2026-09-08 = 10/485 clips with zero
detected-ball rows, median detected share per frame 0.8667). Print the interpreter line.

**WHY THIS ROW EXISTS.** G29 (2026-09-02) recorded that 95.4 pct of pod tracking tables contain zero
rows with `cls == "ball"`; G335 attempt 2 (2026-09-08) found the tables carry NO `cls` column and that
the ball IS detected in the per-clip `data/tracking/<game_id>/ball_tracking.csv` (`detected == 1` on a
median 0.8667 of frames). So the question is no longer detection; it is CONSUMPTION: which downstream
readers (possession Monte Carlo `src/sim/`, features `src/features/feature_engineering.py`, events /
`EventDetector` in `src/pipeline/unified_pipeline.py`, the daemon adjudication `scripts/platformkit/
track_daemon_done.py`, the harness `tracking_harness.py`, the intelligence layer) read
`ball_tracking.csv`, which expect ball rows inside `tracking_data.csv`, and which never see the ball at
all. If the sim never reads the file, the ball is detected and unused -- a one-row fix with large
downstream value.

**PREMISE (step 0, BINDING before-condition):** grep the repo for every reader of `ball_tracking.csv`,
`ball_x2d`, `ball_y2d`, `ball_inferred`, `cls`, `"ball"` under `src/`, `scripts/`, `kernel/`,
`domains/`, `api/`, `intel/` (exhaustive; list `file:line`). PRINT the table. **If the possession sim
and the feature layer both already read `ball_tracking.csv` (or an equivalent joined table) at the
call site, the premise is FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **CONSUMER CENSUS.** For each reader found: what file/columns it reads, whether it expects ball
     rows in `tracking_data.csv` (a `cls`/`class`/`label == ball` filter), whether it joins on frame,
     whether it is on the daemon route, the sim path, or a test only. Classify: READS_BALL_TABLE /
     EXPECTS_INLINE_BALL_ROWS / BALL_BLIND / TEST_ONLY. n per class.
  2. **WRITER CONTRACT.** Cite where `ball_tracking.csv` is written and its schema
     (`unified_pipeline.py` ~:1985-1991 per G320) and whether `tracking_data.csv` ever receives ball
     rows (grep the writer for a ball class in the player table). State the contract in one table.
  3. **THE JOIN (harness).** `scripts/platformkit/tracking/ball_join.py` (<= 200 lines): read a clip's
     `tracking_data.csv` + `ball_tracking.csv`, emit a per-frame joined view (frame, players, ball
     detected/inferred/coords, nearest player and distance in px), with a `--report` that prints frames
     with ball, frames without, nearest-player distance distribution (n). Run it on the two committed
     WNBA tables and report. One per-file test on a synthetic pair.
  4. **CONSUMER FIX PROPOSAL.** For the first BALL_BLIND consumer on the sim path, write the <= 10-line
     PROPOSED change (under `docs/research/organization-sprint/G339_PROPOSED_ball_join_consumer.md`,
     gitignored -- carry its sha256 in the memo; src edits are user-authorized but this row PROPOSES
     because the consumer's expected schema must be confirmed by its owner row first) that feeds the
     joined ball columns to that consumer, and state which downstream numbers it would change.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** a grep census can miss dynamic readers (say so); the
joined view on two tables is a screening; "detected" is the detector's flag, not a verified ball.

ACCEPTANCE RULE:
  metric        = the reader table with `file:line` and class (n per class); the writer contract table;
                  the join harness + test + its report on the two tables; the PROPOSED consumer change
  before        = the sim/feature/event consumers' ball inputs are undocumented; G29's zero-ball claim
                  stands uncorrected in the intelligence layer
  bar           = every grep hit is classified (none skipped); the join reproduces the two tables'
                  detected counts (n); the PROPOSED change names a concrete consumer and column
  n             = every reader hit (exhaustive; Q7); 2 tables (screening)
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every flag, every committed artifact,
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g339_ball_table_consumers_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g339_ball_table_consumers_2026-09-08/readers.csv` and
`join_report.csv` (integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME
COMMIT** (one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g339_ball_join.py`, alone. **NEVER a full pytest.** Every new file <= 300
lines. A missing `data/registry` in the worktree is expected (local-only; never write it).
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
