GAP G343 | sport basketball | worktree aX | log cx_g343_evidence_attack_test

**ATTACK TEST ON THE EVIDENCE PIPELINE (measurement row; local; codex PREPARES, a finisher MEASURES).**
`src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/tracking/`.
NEVER write `data/registry/`, never flip a flag, never claim an edge, never touch
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. No video, no GPU, no pod: cached tables only.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; print the interpreter line). Inputs: the local
tracking mirror `data/tracking/<game_id>/tracking_data.csv` + `ball_tracking.csv` (G335 counted 358 clips
locally) plus the two committed WNBA tables. Never copy a table into the repo; commit only the derived
per-window CSVs (<= 5 MB each).

**WHY THIS ROW EXISTS.** Astra's 2026-09-08 review named the program's biggest risk: autonomous
optimisation can produce SELF-CONSISTENT WRONG tracks while the shared evidence grades its own errors.
The cheapest falsification is to corrupt cached tracking windows in known ways and ask whether the
harness gates that exist today (coordinate contract, oob, jump_p95, coverage, evaluated_frames, the G325
wholly-off-frame rule, the held-position / liveness defect, ball detected share) reject them. A gate that
passes a frozen trajectory or a mirrored court has no power, and every bar built on it is decorative.
The output of this row is a POWER TABLE, not a pass.

**PREMISE (step 0, BINDING before-condition):** list every gate the harness applies to a tracking table
(`file:line`, input columns, threshold, what it rejects) from `scripts/platformkit/tracking_harness.py`
and its metric modules. PRINT the table. **If the harness already carries an injected-corruption
self-test that reports per-corruption rejection with n, the premise is FALSE: STOP, write the memo,
commit, report PREMISE FALSE.**

METHOD:
  1. **WINDOWS (sealed).** 24 clips chosen by a sealed rule (sorted game_id, every k-th to span leagues and
     resolutions; k in the prereg), one 2 s window each at a sealed offset (frames 600-659 at the table's
     fps; if the clip is shorter, the last 60 frames -- say which). Freeze the window list + SHA-256 of each
     source table in the prereg BEFORE any corruption is run.
  2. **ARMS (`scripts/platformkit/tracking/g343_attack_test.py`, <= 250 lines), applied to a COPY of the
     window's rows in the table's native coordinate space (image px for the current mirror; say so):**
     A0 unchanged; A1 frozen trajectories (every id holds its frame-600 position for the window); A2
     same-team id merge (the two ids with the most rows are rewritten to one id); A3 ball time shift (the
     ball table is shifted by +30 frames); A4 scale/translate (x, y scaled by 0.9 about the frame centre,
     then translated by 5 pct of the frame width); A5 mirror (x -> width - x). Each arm changes ONE thing.
  3. **GATES.** Run every premise-table gate on every arm x window through the harness's own functions
     (import them; never re-implement a gate). Record per gate: PASS / REJECT / NOT_APPLICABLE (with the
     reason, e.g. coordinate contract stops before metric gates on image_px tables -- expected for most of
     the mirror; that outcome is itself a finding).
  4. **POWER TABLE.** Per corruption arm: rejection share over the 24 windows per gate and over ALL gates
     (any reject), with n; A0 acceptance share. For every corruption that any-gate rejects on < 0.50 of the
     windows, name the gate that would detect it (one line each; these become register candidates).
  5. **TESTS.** On a synthetic 3-id, 60-frame construct: each corruption changes exactly the intended
     columns (assert row counts, ids and the untouched columns are byte-identical); the A0 arm is byte-
     identical to the input.
  6. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** corruptions in image px cannot express court shrink or
mirror ambiguity as geometry (no validated calibration exists -- G334); 24 windows are a screening; a gate
that rejects a corruption is not proof it rejects real errors; passing this test cannot prove semantic
correctness.

ACCEPTANCE RULE:
  metric        = the premise gate table; the sealed window list with digests; the power table (6 arms x 24
                  windows x every gate) with n; the named missing gates; tests
  before        = no per-corruption power measurement exists for any harness gate
  bar           = every cell of the power table is filled (PASS / REJECT / NOT_APPLICABLE with reason);
                  the A0 arm is byte-identical (test); every under-detected corruption (< 0.50) has a
                  named missing gate; 0 gates re-implemented (imports only)
  n             = 24 windows x 6 arms x every gate
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every gate threshold, every flag, every committed
                  artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **MEASURED** with the power table (this row has no pass bar on rejection); **PARTIAL**
                  with the arm or gate that could not run and why.
EVIDENCE: `docs/evidence/tracking/g343_evidence_attack_test_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g343_evidence_attack_test_2026-09-08/power.csv` and
`windows.csv` (integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT**
(one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g343_attack_test.py`, alone. **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the window rule, the offset, the six
arms, the gate list), the module, the test and the memo skeleton, and exits `PREPARED FOR FINISHER`
listing the exact commands; it must NOT run the 24 windows itself (Q1). A missing `data/registry` or an
absent local mirror in the worktree is reported, never a stop (the finisher supplies the mirror path).
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
