GAP G358 | sport all (basketball fixtures first) | worktree aX | log cx_g358_full_section_gate_execution_v2

**HARNESS ROW, SUCCESSOR TO G356 (PREMISE FALSE 2026-09-08: the >= 300 evaluated-frame floor the G356 spec
set was wrong-scaled for the daemon's stride; only 2 G346 LIVE sections cleared it). Codex PREPARES, a
finisher MEASURES.** Same purpose as G356: a COMMITTED production-schema adapter and gate execution on
FULL sections (not 2 s windows) with duration dependence and a per-gate diagnosis. `src/`, `kernel/`,
`api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/tracking/` beside
`image_space_gates.py` and `g353_production_translation.py` (landed G353), `tracking_schema.py` and
`tracking_harness.py`. NEVER write `data/registry/`, never flip a flag, never move a gate threshold, never
edit the accepted coordinate-space sets, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL (conda `basketball_ai`; batched reads) with READ-ONLY pod fetches of full
tracking tables into local scratch outside the repo (never write on the pod; never touch the daemon pid
1596016 or the guards; the corpus rotates: a vanished table is ABSENT). Every python run is `python -m
scripts.platformkit....` from the worktree root (direct-path runs resolve `scripts` to the MAIN repo).

**WHY THIS ROW EXISTS.** G353 (landed 3b6a24ecd): the image-space path reaches real pod tables and detects
frozen / id-merge / ball-shift at 1.0, but 9 of 11 evaluated gates false-reject the UNCHANGED arm above
0.05 on 2 s windows, `insufficient_data` rejects 30 of 30 (2 s windows are under the 30-frame floor at
`tracking_harness.py:65`), real tables carry no frame size (0 of 653), no `cls`, and the ball embedded on
player rows. G356 asked for full sections with >= 300 evaluated frames and found 2: the daemon evaluates
130 s sections at a stride that yields roughly 180 evaluated frames, so the floor, not the corpus, was
wrong. This row uses the corpus's actual full-section length.

**PREMISE (step 0, BINDING before-condition):** from the landed G346 sealed LIVE list and the pod ledger
(read-only), list the G346 LIVE sections whose tracking table has >= 150 evaluated frames (the daemon's
full-section length at its stride; print the distribution of evaluated frames per section: min, p10,
median, p90, max, n) across >= 4 games; the G354 post-epoch px-field clips are eligible too. **If fewer
than 6 such sections across >= 4 games exist, the premise is FALSE: STOP, write the memo with the
distribution, commit, report PREMISE FALSE.**

METHOD:
  1. **PRODUCTION-SCHEMA ADAPTER (`production_schema_adapter.py`, <= 200 lines, additive).** Promote the
     landed G353 scratch translation into the committed adapter: production table (`x_position` /
     `y_position`, no `cls`, embedded `ball_x2d` / `ball_y2d`, and, on post-epoch clips, `ball_x2d_px` /
     `ball_y2d_px`) -> normalised frame (`cls`, `frame`, `track_id`, `x`, `y`); one derived ball row per
     frame when the embedded ball is finite, stamped `ball_source=embedded_px` when the px fields exist
     else `embedded_court`; frame size from a SEALED rule: sidecar when present, else the G353 estimator
     (`x_position / x_norm`) stamped `frame_size_source=estimated`, else `absent` with every
     size-dependent gate NOT_APPLICABLE (reason `frame_size_absent`); every output row `scorable=False`.
     Tests: synthetic round-trip; absent x_norm; a valid zero survives; px vs court source stamping;
     existing columns never renamed.
  2. **FULL-SECTION FIXTURES (sealed in the prereg by path + sha256 + rows).** >= 6 sections, >= 4 games,
     G346 LIVE, >= 150 evaluated frames each. Arms: A0 unchanged; A1_FROZEN, A2_ID_MERGE, A5_BALL_SHIFT
     planted on the FULL section by the landed G348 constructors; A3 / A4 UNIDENTIFIABLE by construction.
  3. **GATE EXECUTION with duration dependence.** Per gate x arm reached / evaluated / rejected with n on
     the full sections AND on sealed sub-windows of 2 s, 10 s and 30 s cut from the same sections (same
     start rule): A0 false rejection per gate per duration with Wilson 95 pct intervals; detection per
     identifiable defect per duration.
  4. **DIAGNOSIS per gate** whose A0 false rejection exceeds 0.05 on FULL sections: the statistic
     distribution (median, p90, n) against the sealed threshold, classified THRESHOLD_MISCALIBRATED /
     PRODUCTION_SCHEMA_ARTIFACT / DURATION_ARTIFACT; no threshold moves; a reseal PROPOSAL per gate in the
     memo only.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** six sections are a screening; an estimated frame size is
weaker than a sidecar (G330); image-space gates are necessary, never sufficient; the corpus rotates; the
150-frame floor is the corpus's own full length, not a validity threshold.

ACCEPTANCE RULE:
  metric        = premise (distribution of evaluated frames, the sealed section list); adapter tests; the
                  gate x arm x duration table with n and intervals; the diagnosis table
  before        = G353: 9 of 11 evaluated gates false-reject A0 above 0.05 on 2 s windows;
                  insufficient_data 30/30; translation scratch-only; G356 premise false on a wrong floor
  bar           = adapter tests pass; >= 6 full sections from >= 4 games; every gate reports A0 false
                  rejection at 4 durations with intervals; detection >= 0.80 per identifiable defect on
                  full sections; every gate above 0.05 on full sections carries a diagnosis with n; 0
                  threshold moves; 0 src edits; every output row scorable=False
  n             = >= 6 sections x 4 arms x 4 durations x every gate
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every flag, every gate threshold, the accepted-space
                  sets, every landed artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** naming the gate, arm, duration or section that
                  could not run; **PREMISE FALSE** with the distribution.
EVIDENCE: `docs/evidence/tracking/g358_full_section_gate_execution_v2_2026-09-08.md` (<= 60 lines; VERDICT
line 1; tables; NOT VERIFIED; wall time; SHA-256s) + `.../g358_full_section_gate_execution_v2_2026-09-08/gates.csv`,
`duration.csv`, `diagnosis.csv`, `frames_distribution.csv` (integer cells zero-padded; shares as ADDITIVE
per-mille columns; never rename or remove a column). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT**
(append only). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g358_production_schema_adapter.py` plus `tests/platformkit/test_g353_image_space_gates.py`
and `tests/platformkit/test_g353_production_translation.py`, each alone. **NEVER a full pytest.** Every new
file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the adapter rules, the frame-size
rule, the 150-frame section rule, the durations, the diagnosis classes), the adapter, the tests and the
memo skeleton with the exact fetch and run commands in `python -m` form, and exits with the line
`agent: PREPARED FOR FINISHER`; it must NOT run the real sections (Q1). Absent fixtures or `data/registry`
in the worktree are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
