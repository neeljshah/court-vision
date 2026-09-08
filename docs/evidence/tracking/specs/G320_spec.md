GAP G320 | sport all | worktree a1 | log cx_g320_ball_inferred_no_coord

**TOOLING + TRACE ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT only --
`src/pipeline/unified_pipeline.py` and `src/tracking/ball_detect_track.py` are HUMAN-GATED (PROPOSED diff
only). Build in `scripts/platformkit/`. NEVER edit a committed evidence hash, a committed evidence artifact,
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`, or any threshold.**

**WHERE THIS ROW RUNS:** LOCAL. The G314 artifact on master holds the exact rows; the pod is READ-ONLY and
only needed if the two WNBA tracking tables are not committed (then `ssh -F ~/.ssh/config.pod pod 'cat ...'`
of `data/tracking/<game>/ball_tracking.csv` for the two games, never a write, never a daemon or guard
interaction; pids 1168432 / 1039858 / 1201700 untouched). No GPU, no video.

**WHY THIS ROW EXISTS.** G314 found 7 of 2,000 sampled ball rows (1 in wnba_05, 6 in wnba_02) carrying
`inferred=1` with `detected=0` and NO coordinate: the dribble predictor flagged a bbox that the writer never
turned into `ball_x2d`/`ball_y2d`. The G314 verifier also flagged that the G314 reader counts a missing
`ball_inferred` header as zero instead of stopping. The cause is unverified; G29 (95.4 pct of pod tables
have zero `cls=="ball"` rows) makes every ball row precious, and an inferred flag without a coordinate is a
row that downstream sims cannot use and that a census silently miscounts.

**PREMISE (step 0, BINDING before-condition):** load the G314 artifact from master (find it:
`git ls-files docs/evidence/tracking | grep -a -i g314`), reproduce the 7 rows by frame id and game (PRINT
them), and confirm each has `inferred=1`, `detected=0` and null/empty `ball_x2d`/`ball_y2d`. **If fewer than
7 such rows exist in the committed artifact, the premise is FALSE (or partially false: report the count
and continue only for the rows that exist).**

METHOD:
  1. **TRACE (read-only, `file:line`).** Follow the writer path from the dribble predictor's inferred bbox
     to the CSV row: `src/tracking/ball_detect_track.py` around :796 (the inferred flag) and
     `src/pipeline/unified_pipeline.py` around :1985-1991 (the row write), plus every branch between that
     can drop or null the coordinate (a None bbox, a clamp that fails, an off-frame prediction, a
     late-binding of `ball_x2d` after the row dict is built). Name the cause in one sentence, and say how
     it would be confirmed (which frame ids, which branch). If the cause cannot be named from code
     alone, say UNATTRIBUTED and list the candidate branches with the evidence for and against each.
  2. **PROPOSED DIFF (local-only, gitignored).** `docs/research/organization-sprint/G320_PROPOSED_ball_inferred_coord.md`
     (<= 40 lines): the 3-10 line producer change that either writes the coordinate the predictor had, or
     writes `inferred=0` when no coordinate exists (state which, and why). Carry its sha256 in the memo.
  3. **READER HARDENING (harness).** The G314 reader under `scripts/platformkit/` must STOP (raise) when the
     `ball_inferred` header is missing, and must count `inferred=1 & no coordinate` as its own class
     (`inferred_no_coord`) rather than folding it into either detected or inferred. Additive: existing
     output fields keep names and meanings (B2); new class fields only. One per-file test: a table missing
     the header raises; a table with the 7-row pattern reports `inferred_no_coord = 7` with n.
  4. **CENSUS.** Run the hardened reader over every committed ball table under `docs/evidence/tracking/**`
     (exhaustive; list them) and report per table: rows, detected, inferred, inferred_no_coord, with n.
     If the two WNBA tables are only on the pod, fetch them read-only and report them separately.
  5. **CHANGE NOTHING ELSE.** No `src/` edit, no threshold, no committed artifact edit, no register edit.

**HONEST LIMITATIONS to state, not discover:** a cause named from code is a hypothesis until a re-run
with the PROPOSED change reproduces the 7 rows with coordinates; this row performs no re-run and measures
no ball recall; a census over committed tables is a census of what was archived, not of the pod fleet.

ACCEPTANCE RULE:
  metric        = the 7 reproduced rows; the trace with `file:line` and the named cause (or UNATTRIBUTED
                  with candidates); the PROPOSED diff sha256; the hardened reader + test; the census table
  before        = 7/2,000 sampled ball rows carry `inferred=1` with no coordinate and no named cause; the
                  G314 reader counts a missing `ball_inferred` header as zero
  bar           = the trace names the producer lines (not guessed); the reader raises on a missing header
                  and reports `inferred_no_coord` with a passing test; every census cell carries n
  n             = the 7 rows (exhaustive); every committed ball table (exhaustive; Q7)
  eye check     = NONE. Say that.
  must not move = `src/`, `domains/`, `api/`, `kernel/`, `intel/`; every committed artifact and hash;
                  `data/`; anything on the pod; the daemon and guards;
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds (cause named or honestly UNATTRIBUTED with candidates);
                  **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g320_ball_inferred_no_coord_2026-09-08.md` (<= 60 lines) with VERDICT on
line 1, the 7 rows, the trace, the census table, a **NOT VERIFIED** list, wall time and the SHA-256s; plus
`docs/evidence/tracking/g320_ball_inferred_no_coord_2026-09-08/census.csv` (integer cells zero-padded to 6
digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g320_ball_inferred_no_coord.py`. Run that ONE file and the existing test file
of the G314 reader module. **NEVER a full pytest.** Every touched file <= 300 lines.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
