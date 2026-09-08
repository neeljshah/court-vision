GAP G354 | sport basketball | worktree aX | log cx_g354_ball_px_producer_fields

**PRODUCER-FIX ROW (from G351 DONE 2026-09-08; the user's 2026-09-08 authorization to apply PROPOSED src diffs
and deploy the producer applies). Codex PREPARES (never touches `src/`); an Opus finisher APPLIES the diff in
the worktree's `src/`, smokes it, DEPLOYS it with the G333 recipe and VERIFIES fresh post-deploy clips.**
`kernel/`, `api/` and `intel/` stay READ only. Build in `scripts/platformkit/tracking/`. NEVER write
`data/registry/`, never flip a flag, never restart the pod daemon (pid 1596016) or the guards, never write
under `/workspace/nba-ai-system` except the authorized producer deploy (atomic mv of the two producer files),
never delete footage, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHY THIS ROW EXISTS.** G351 measured that on 214 of 356 local clips the ball table (`ball_x2d`, `ball_y2d`)
is written in COURT-MAP units (`src/tracking/ball_detect_track.py` projects the ball centre through
`M1 @ (M @ ball_center)`) while the player table's `bbox_x1..y2` are RAW TOPCUT-crop pixels
(`src/pipeline/unified_pipeline.py`, single row-build site). Every image-space ball / player join (G339, G344,
G349) is therefore wrong by construction, and the reader-side rescale helps 2 of 3 G349 windows and hurts 1.
The honest fix is at the producer: emit the ball's raw pixel centre ADDITIVELY beside the existing fields.

**PREMISE (step 0, BINDING before-condition):** in the worktree, `git apply --check` of the landed PROPOSED
diff (`docs/research/organization-sprint/G351_PROPOSED_ball_scale.md`, gitignored, sha256 recorded in the
G351 memo; if absent locally, reconstruct the <= 10-line diff from the G351 memo's writer trace) against
`src/tracking/ball_detect_track.py` / `src/pipeline/unified_pipeline.py`; cite the writer lines; PRINT the
current ball-table header from one local clip. **If the producer already writes `ball_x2d_px` /
`ball_y2d_px` (or any pixel-frame ball field), the premise is FALSE: STOP, write the memo, commit, report
PREMISE FALSE.**

METHOD:
  1. **THE DIFF (additive, <= 20 lines of src).** BOTH ball writers are covered: the dedicated route
     (`ball_detect_track.py` `last_2d_pos` at ~:908-911 / :956, consumed at `unified_pipeline.py` ~:1945-1950 and
     written at ~:1988-1989) AND the second writer at `unified_pipeline.py` ~:3081-3093 (a YOLO ball bbox
     projected through the same `M1 @ (M @ ...)`; the G351 lander found the candidate memo omitted it).
     New ball-table columns `ball_x2d_px`, `ball_y2d_px` = the
     detector's pixel centre in the SAME frame as the player `bbox_*` (the TOPCUT-cropped image the boxes
     are built in; if the detector input is resized, apply the inverse resize and say so with file:line);
     the existing columns are untouched (names, order, semantics). The two G351 verifier NEW GAPS are
     BINDING: the pixel fields are cleared to an explicit empty value on every frame WITHOUT a detection
     (never stale from the previous frame) and a valid zero component is written as `0`, never blank.
  2. **TESTS (`tests/platformkit/test_g354_ball_px_fields.py`)** on a synthetic frame sequence: (a) the px
     fields equal the detector centre; (b) a frame without a detection writes the empty value, not the
     previous frame's values; (c) a detection at x=0 writes `0`; (d) the pre-existing columns are
     byte-identical to a run without the diff (golden comparison on the synthetic sequence).
  3. **LOCAL SMOKE.** `scripts/run_clip.py` headless (`--no-show`) on one local 130 s section with the
     patched producer: both fields present, ball px range within the player px range (ratio <= 1.5 on
     both axes, the G351 rule), n frames with a detection.
  4. **DEPLOY (user-authorized 2026-09-08; G333 recipe).** Ship the patched `src/tracking/
     ball_detect_track.py` (and `unified_pipeline.py` only if the diff touches it) LF-normalised to the pod
     via scp to a scratch path and an ATOMIC `mv` into `/workspace/nba-ai-system/...`; record sha256 before
     and after, the UTC timestamp, and `git -C /workspace/nba-ai-system status --short` for the two files;
     NO daemon restart (G333 verified workers import the module per clip); never touch the guards.
  5. **POST-DEPLOY VERIFICATION.** Wait for >= 3 fresh ledger entries (`track_daemon_ledger.jsonl`) with a
     timestamp AFTER the deploy; per fresh clip read the ball table HEADER + per-axis p1 / p99 of
     `ball_x2d_px` vs the player `bbox_*` range (metadata / batched reads only; nothing copied into the
     repo); the G351 ratio rule per clip; then the G344 60 px radius re-join on those clips: frames with a
     player within radius using the px fields vs using the old fields (n both). Clips tracked BEFORE the
     deploy timestamp never count.
  6. CHANGE NOTHING ELSE. No consumer wiring (G344 / G349 re-runs are their own attempt-2 rows).

**HONEST LIMITATIONS to state, not discover:** a px field fixes the unit, not ball detection coverage (G335)
or ownership (G344); three fresh clips are a smoke, not a census; pre-deploy clips keep the old semantics
and the ledger date is the only epoch marker (record it).

ACCEPTANCE RULE:
  metric        = the premise output; the diff (file:line); the four tests; the local smoke table; the
                  deploy record (sha256 before / after, timestamp); the post-deploy per-clip table with n;
                  the re-join before / after with n
  before        = ball table court-map, player table px on 214 of 356 clips; no pixel ball field exists
  bar           = diff <= 20 src lines, additive (old columns byte-identical on the golden run); 4/4 tests;
                  smoke ratio <= 1.5 both axes; deploy recorded with matching sha256s; >= 3 fresh post-deploy
                  clips each with both fields present and ratio <= 1.5 on both axes; existing tests
                  `tests/platformkit/test_g333_producer_diffs.py` and `test_g351_ball_scale_census.py` pass
                  unchanged; 0 daemon restarts; 0 flag flips
  n             = 1 smoke clip; >= 3 fresh pod clips; every frame of each
  eye check     = NONE. Say that.
  must not move = `data/`, `data/registry/`, every flag, the daemon and guards, every existing ball-table
                  column, every landed artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** naming what could not run (e.g. the pod produced
                  fewer than 3 fresh clips in the window; say the window).
EVIDENCE: `docs/evidence/tracking/g354_ball_px_producer_fields_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g354_ball_px_producer_fields_2026-09-08/smoke.csv`,
`deploy.csv`, `postdeploy.csv`, `rejoin.csv` (integer cells zero-padded; shares as ADDITIVE per-mille
columns). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g354_ball_px_fields.py`, `tests/platformkit/test_g333_producer_diffs.py`,
`tests/platformkit/test_g351_ball_scale_census.py`, each alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the field definitions, the empty
value, the ratio rule, the >= 3 fresh-clip rule, the deploy recipe), the diff as a PATCH FILE under
`docs/evidence/tracking/g354_ball_px_producer_fields_2026-09-08/ball_px.patch` (it must NOT apply it to
`src/`), the tests, the verification module (`g354_postdeploy_check.py`, <= 200 lines) and the memo
skeleton, and exits with the line `agent: PREPARED FOR FINISHER` plus the exact commands; the Opus finisher
applies, smokes, deploys and verifies (Q1). An absent local mirror or `data/registry` in the worktree is
reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
