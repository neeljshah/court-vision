GAP G356 | sport all (basketball fixtures first) | worktree a3 | log cx_g356_full_section_gate_execution

**HARNESS ROW, SUCCESSOR TO G353 (PARTIAL -- BAR NOT MET 2026-09-08). Codex PREPARES, a finisher MEASURES.**
`src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/tracking/`
beside `image_space_gates.py` (G353), `tracking_schema.py` and `tracking_harness.py`. NEVER write
`data/registry/`, never flip a flag, never move a gate threshold, never edit the accepted coordinate-space
sets, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL (conda `basketball_ai`; batched reads) with READ-ONLY pod fetches of full
tracking tables into local scratch (never under the repo; never write on the pod; never touch the daemon
pid 1596016 or the guards; the pod corpus rotates, so a vanished table is reported ABSENT).

**WHY THIS ROW EXISTS.** G353 (7d9edaaf1) showed the image-space path reaches real pod tables and detects
all three identifiable planted defects at 1.0, but on the 30 G348 fixtures 7 of 15 gates false-reject the
UNCHANGED arm above the 0.05 bar and `insufficient_data` rejects 30 of 30 because every G348 fixture is a
2 s window below the harness's 30-frame floor (`MIN_FRAMES_FOR_METRICS`). G353 also found that real
production tables carry NO `frame_width` / `frame_height` (0 of 653 live tables), NO `cls` column, and the
ball embedded as `ball_x2d` / `ball_y2d` on player rows, so the finisher needed a scratch-only translation
layer to feed the harness at all. Two questions must be answered before any gate can grade a producer
change (G333, G352, G354): (a) is the false rejection a FIXTURE-DURATION artifact or a real gate
miscalibration on production output; (b) the production-schema translation must be committed and tested,
never scratch.

**PREMISE (step 0, BINDING before-condition):** cite `MIN_FRAMES_FOR_METRICS` (file:line) and show every G348
fixture has fewer rows than it (n per window from the landed fixtures.csv / gates.csv); list >= 6 FULL
sections from >= 4 games (G346 LIVE, >= 300 evaluated frames each) available on the pod with byte size and
sha256. **If fewer than 6 such sections exist, the premise is FALSE: STOP, write the memo, commit, report
PREMISE FALSE.**

METHOD:
  1. **PRODUCTION-SCHEMA ADAPTER (`production_schema_adapter.py`, <= 200 lines, additive).** Maps a
     production table (`x_position` / `y_position`, no `cls`, embedded `ball_x2d` / `ball_y2d`, no frame
     size) into the harness's normalised frame (`cls`, `frame`, `track_id`, `x`, `y`): one derived ball row
     per frame when the embedded ball is finite, stamped `ball_source=embedded`; frame size from a SEALED
     rule: the sidecar when present, else the G353 estimator (`x_position / x_norm`) stamped
     `frame_size_source=estimated`, else `frame_size_source=absent` and every size-dependent gate
     NOT_APPLICABLE with reason `frame_size_absent` (never a silent estimate). Every output row keeps
     `scorable=False`. Tests: synthetic production table round-trip; the absent-x_norm case; a valid zero
     coordinate survives; existing columns never renamed.
  2. **FULL-SECTION FIXTURES (sealed in the prereg by path + sha256 + rows).** >= 6 full sections, >= 4
     games (the G348 games plus at least 2 more), G346 LIVE. Arms: A0 unchanged; A1_FROZEN, A2_ID_MERGE,
     A5_BALL_SHIFT planted on the FULL section by the G348 constructors; A3 / A4 UNIDENTIFIABLE by
     construction (reported, never counted).
  3. **GATE EXECUTION with duration dependence.** Per gate x arm reached / evaluated / rejected with n on
     the full sections AND on sealed sub-windows of 2 s, 10 s and 30 s cut from the same sections (same
     start rule for every section): A0 false rejection per gate per duration with Wilson 95 pct intervals;
     detection per identifiable defect per duration.
  4. **DIAGNOSIS per gate** whose A0 false rejection exceeds 0.05 on FULL sections: the measured statistic
     distribution (median, p90 with n) against the sealed threshold, classified THRESHOLD_MISCALIBRATED
     (live footage genuinely beyond the threshold) or PRODUCTION_SCHEMA_ARTIFACT (e.g. per-player rows,
     no per-frame row, embedded ball) or DURATION_ARTIFACT (passes at full length, fails on sub-windows);
     no threshold moves in this row; a reseal PROPOSAL per gate in the memo only.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** six sections are a screening; an estimated frame size is
weaker evidence than a sidecar (nothing certifies coordinates, G330); image-space gates are necessary,
never sufficient; the pod corpus rotates.

ACCEPTANCE RULE:
  metric        = premise (floor citation, per-fixture rows, the sealed section list); adapter tests; the
                  gate x arm x duration table with n and intervals; the diagnosis table
  before        = G353: 7 of 15 gates false-reject A0 above 0.05 on 2 s windows; insufficient_data 30/30;
                  translation scratch-only
  bar           = adapter tests pass; >= 6 full sections from >= 4 games; every gate reports A0 false
                  rejection at 4 durations with intervals; detection >= 0.80 per identifiable defect on
                  full sections; every gate above 0.05 on full sections carries a diagnosis with n; 0
                  threshold moves; 0 src edits; every output row scorable=False
  n             = >= 6 sections x 4 arms x 4 durations x every gate
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every flag, every gate threshold, the accepted-space
                  sets, every landed artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** naming the gate, arm, duration or section that
                  could not run.
EVIDENCE: `docs/evidence/tracking/g356_full_section_gate_execution_2026-09-08.md` (<= 60 lines; VERDICT
line 1; tables; NOT VERIFIED; wall time; SHA-256s) + `.../g356_full_section_gate_execution_2026-09-08/gates.csv`,
`duration.csv`, `diagnosis.csv` (integer cells zero-padded; shares as ADDITIVE per-mille columns; never
rename or remove a column). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only). **Do NOT
edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g356_production_schema_adapter.py` plus `tests/platformkit/test_g353_image_space_gates.py`
(once landed), each alone. **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the adapter rules, the frame-size
rule, the section list rule, the durations, the diagnosis classes), the adapter, the tests and the memo
skeleton, and exits with the line `agent: PREPARED FOR FINISHER` plus the exact fetch and run commands; it
must NOT run the real sections (Q1). Absent fixtures or `data/registry` in the worktree are reported,
never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
