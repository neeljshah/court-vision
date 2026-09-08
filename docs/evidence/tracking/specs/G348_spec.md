GAP G348 | sport basketball | worktree a15 | log cx_g348_gate_execution_valid_fixtures

**HARNESS-POWER ROW (astra midday review 2026-09-08, item B; follows G343 CLOSED AT LIMIT). Codex PREPARES,
a finisher MEASURES.** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/`. NEVER write `data/registry/`, never flip a flag, never fabricate a
calibration sidecar to make a gate run, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** the fixture search on the pod (read-only: `/workspace/nba-ai-system/data/tracking/`
and the daemon outputs; scratch under `/workspace/wt/<wt>/`; never touch the daemon pid 1596016 or the
guards); the gate runs LOCALLY on copied windows (CPU; batch reads; check free RAM first).

**WHY THIS ROW EXISTS.** G343 measured that the harness's coordinate contract rejects 100 pct of every
window, corrupted or not, because no `court_calibration.json` sidecar exists in the local mirror, so all 13
downstream metric gates have NEVER executed on a real table and their power against frozen trajectories,
id merges, scale / translate and mirror is unmeasured. Astra: split input-contract outcomes from metric
applicability, count per-gate reached / evaluated / rejected, run an UNCHANGED positive control, and
recover AUTHENTIC producer sidecars where they exist (the pod route writes calibration sidecars for some
clips; G330 found 18/199 runs not on the fallback panorama); never fabricate a valid calibration.

**PREMISE (step 0, BINDING before-condition):** census the pod tracking outputs for calibration sidecars
(`court_calibration.json` or the schema's equivalent; `file:line` of the writer in the route) and any
image-px table with a declared court transform: n clips with a sidecar, n without, n frozen (G346 list).
**If zero authentic sidecars exist anywhere, the premise for court-coordinate gates is FALSE: STOP that
part, and still run the image-space gates (liveness / trajectory checks) on their declared inputs as the
row's remaining scope -- say so.**

METHOD:
  1. **FIXTURES (sealed).** >= 30 non-frozen 2 s windows from >= 3 games (stratified by game; include the 2
     WNBA tables), each with its authentic sidecar when one exists; a positive control = the unchanged
     window; contract-valid corrupted twins for each planted defect (frozen trajectory, same-team id merge,
     scale 0.9 + translate 5 pct, mirror, ball shift) constructed so the coordinate contract still PASSES
     (the corruption lives inside valid coordinates).
  2. **PER-GATE DENOMINATORS (`g348_gate_execution.py`, <= 250 lines).** For every gate the harness applies
     (import the harness's functions; never re-implement): reached / evaluated / rejected counts per arm,
     with the reason class; the unchanged arm's false-rejection share; per planted defect the detection
     share with a Wilson 95 pct interval.
  3. **BAR (prereg it):** every advertised metric gate executes on the unchanged valid fixture (evaluated
     n > 0); per applicable planted defect detection >= 0.80 and unchanged-window false rejection <= 0.05;
     defects the available observations cannot identify (global mirror / scale without independent
     structure) are marked UNIDENTIFIABLE, not counted as power; contract refusal is never counted as
     detection.
  4. **TESTS.** A synthetic valid fixture reaches every gate; a contract-invalid twin is recorded as
     REFUSED (not detected); the denominators sum.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** this is a harness screening bar, not coordinate-quality
certification (that stays blocked until G334 / G342 and independent geometric checks exist); sidecars are
authentic producer output, whose own validity is unproven (G330).

ACCEPTANCE RULE:
  metric        = the sidecar census; the fixture list with digests; the per-gate reached / evaluated /
                  rejected table per arm with n; per-defect detection with intervals; the unchanged-arm
                  false-rejection share; tests
  before        = no metric gate has executed on a real table (G343)
  bar           = every gate evaluates (n > 0) on the unchanged valid fixtures; detection and false-rejection
                  reported per defect with intervals (met or not, as sealed); UNIDENTIFIABLE defects named;
                  0 fabricated sidecars; 0 src edits
  n             = >= 30 windows from >= 3 games x every arm x every gate
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every gate threshold, every flag, the pod daemon and
                  guards, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **MEASURED** with the power table if every gate executed; **PARTIAL** naming the gate or
                  arm that could not run and why.
EVIDENCE: `docs/evidence/tracking/g348_gate_execution_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables;
NOT VERIFIED; wall time; SHA-256s) + `.../g348_gate_execution_2026-09-08/fixtures.csv`, `gates.csv`,
`detection.csv` (integer cells zero-padded; shares as per-mille integers in ADDITIVE columns beside any
sealed float column -- never rename or remove a column). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME
COMMIT** (append only). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g348_gate_execution.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: fixture rule, defects, bar), the module,
the tests and the memo skeleton, and exits with the line `agent: PREPARED FOR FINISHER` plus the exact
commands; it must NOT run the pod census or the windows itself (Q1). Absent sidecars or `data/registry` in
the worktree are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
