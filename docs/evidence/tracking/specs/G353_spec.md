GAP G353 | sport all (basketball fixtures first) | worktree a10 | log cx_g353_image_px_gate_reachability

**HARNESS-REACHABILITY ROW (from G348 PARTIAL 2026-09-08; astra suspicion "shared early refusal"). Codex
PREPARES, a finisher MEASURES.** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/` beside the landed harness (`scripts/platformkit/tracking_schema.py`,
`scripts/platformkit/tracking_harness.py`, the G348 module `g348_gate_execution.py` once landed). NEVER write
`data/registry/`, never flip a flag, never edit the accepted coordinate-space sets of the rail, never touch
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL (conda `basketball_ai`; per-window reads; check free RAM first). Inputs: the 30
sha256-verified G348 fixture windows (`docs/evidence/tracking/g348_gate_execution_2026-09-08/fixtures.csv`;
re-fetch read-only from the pod by the paths named there if the local scratch copies are gone; never write
under `/workspace/nba-ai-system`), the G348 planted-defect constructors, the 2 committed WNBA tables.

**WHY THIS ROW EXISTS.** G348 measured that 0 of 607 pod tracking tables carry a `court_calibration.json`
sidecar, that 602 of 607 headers declare `coordinate_space=image_px`, and that the rail
(`tracking_schema.py` `_validate_coordinate_space`, `SPORT_COORDINATE_SPACES` court spaces only) makes
`coordinate_contract` REJECT 30 of 30 real windows (Wilson 95 pct CI 0.8865 to 1.0) so that every one of the
other 17 gates is NOT_APPLICABLE on 100 pct of real pod output. G343 found the same shared early refusal.
The harness has therefore produced ZERO gate measurements on real tracking output since the image_px
declaration was introduced; a producer change (G333, G352) cannot be graded by it. The rail is correct
(pixels are never a scorable game) and stays; this row adds the image-space evaluation path beside it.

**PREMISE (step 0, BINDING before-condition):** classify every gate the harness reports (enumerate them from
`tracking_harness.py`; G348 counted 18 including `coordinate_contract`) as IMAGE-SPACE-COMPUTABLE (needs
only frame, track_id, x, y in pixels and the decoded frame size: frozen liveness, id churn / fragmentation,
detection density, jump p95 in px per s, ball-row presence, in-frame containment) or COURT-ONLY (feet
inside the court, ft per s speeds, homography validity, court-coordinate sanity). PRINT the table with the
`file:line` of each gate. **If fewer than 3 gates are image-space computable, the premise is FALSE: STOP,
write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **ADDITIVE ENTRY POINT (`image_space_gates.py`, <= 250 lines).** `evaluate_image_space(df, sport,
     frame_width, frame_height)` returns the gate statuses of the image-space-computable gates for rows that
     declare `image_px`, with `scorable=False` and `coordinate_space=image_px` stamped on EVERY output row and
     the court-only gates returned as NOT_APPLICABLE with reason `court_space_required`. The landed
     `evaluate()` is NOT modified (its REJECT on image_px is the rail; B2). Thresholds for the image-space
     gates are the LANDED ones where a pixel analogue exists (G346 liveness cues; G336 / G345 fragmentation;
     G48 jump p95 converted to px per s ONLY through the sealed frame size); where no landed threshold
     exists the gate reports its measurement with status MEASURED_NO_BAR, never PASS.
  2. **GATE EXECUTION on the 30 G348 fixtures.** Arms: A0 unchanged; the G348 contract-valid planted defects
     A1_FROZEN, A2_ID_MERGE, A5_BALL_SHIFT (identifiable in pixel space); A3_SCALE_TRANSLATE and A4_MIRROR are
     declared UNIDENTIFIABLE in pixel space by construction (no court) and reported as such, never counted as
     detections. Per gate x arm: reached / evaluated / rejected with n. Detection >= 0.80 per identifiable
     defect; false rejection on A0 <= 0.05 per gate (the sealed G348 bars).
  3. **POD-WIDE REACHABILITY CENSUS (metadata only):** headers + row counts of every pod table (read-only
     listing, the G348 `pod_file_listing.txt` refreshed): how many tables would reach each image-space gate
     (n, per league). No table contents copied into the repo.
  4. **TESTS.** Synthetic image_px table: the frozen / id-merge / ball-shift constructs are detected by the
     image-space path; `evaluate()` still REJECTs the same table (rail unchanged); every output row carries
     `scorable=False`; the existing tracking-schema tests pass unchanged.
  5. CHANGE NOTHING ELSE. No consumer wiring, no src hook, no flag.

**HONEST LIMITATIONS to state, not discover:** an image-space gate passing is necessary, never sufficient,
for court geometry; nothing here certifies coordinates (G330); 30 windows from 4 games are a screening;
pixel thresholds inherit the sealed frame size and are wrong on any table whose `frame_width` /
`frame_height` are absent (report that count).

ACCEPTANCE RULE:
  metric        = the premise classification table with file:line; per gate x arm reached / evaluated /
                  rejected with n on the 30 windows; the detection and false-rejection shares with Wilson
                  CIs; the pod-wide reachability census; tests
  before        = every gate NOT_APPLICABLE on 100 pct of real pod output (G348: coordinate_contract REJECT
                  30/30, all other gates 0 evaluated)
  bar           = >= 3 image-space gates reach EVALUATED on >= 90 pct of A0 windows; A0 false rejection
                  <= 0.05 per gate; detection >= 0.80 on each identifiable planted defect; `evaluate()`
                  behaviour byte-identical on the existing tests; every output row scorable=False; 0 src
                  edits; 0 changes to the accepted-space sets
  n             = 30 windows x 4 arms (A0, A1, A2, A5) x every gate; every pod table in the census
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every flag, `SPORT_COORDINATE_SPACES` and
                  `SPORT_METRIC_LOCAL_SPACES`, every landed artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** naming the gate or arm that could not run.
EVIDENCE: `docs/evidence/tracking/g353_image_px_gate_reachability_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g353_image_px_gate_reachability_2026-09-08/gates.csv`,
`arms.csv`, `census.csv` (integer cells zero-padded; shares as ADDITIVE per-mille columns; never rename or
remove a column). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g353_image_space_gates.py` plus `tests/platformkit/test_g233_basketball_seeded_court_coordinates.py`
and `tests/platformkit/test_g348_gate_execution.py` (once landed), each alone. **NEVER a full pytest.** Every
new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the gate classification, the arms, the
bars, the per-gate thresholds with their landed sources), the module, the tests and the memo skeleton, and
exits with the line `agent: PREPARED FOR FINISHER` plus the exact commands; it must NOT run the fixtures (Q1).
Absent fixtures or `data/registry` in the worktree are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
