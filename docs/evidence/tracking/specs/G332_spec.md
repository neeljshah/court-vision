GAP G332 | sport all | worktree a1 | log cx_g332_harness_hygiene_0908

**TOOLING ROW (harness hygiene from the 2026-09-08 verifier NEW GAPs). `src/`, `domains/`, `api/`, `kernel/`
and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/` and `tests/platformkit/`. NEVER edit a
committed evidence hash, a committed evidence artifact, a landed memo,
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`, or any threshold.**

**WHERE THIS ROW RUNS:** LOCAL only. No pod, no GPU, no video. Every input is committed bytes on master.

**WHY THIS ROW EXISTS.** Three verified rows landed today with executable holes their verifiers named and
their landings only recorded: (a) G62 -- the `--no-env-sidecar` opt-out has executable byte-parity coverage
for `census_recomputable` only; `g310_instance_key` and `g330_run_attempt2` are inspection-only; (b) G327 --
`verify_snapshot` drops a missing or mismatched game and scoring accepts the reduced set (a rerun could
silently score 80/120 frames), and `read_arm_csv` accepts a wholly mislabelled arm file because no expected
arm is supplied; (c) G319 -- `census_recomputable.py` accepts arbitrary JSON list lengths and count-key
integers without validating the hash/timestamp/chain/projection that `CENSUS_RULE.md:10-14` requires,
silently falls back to all filesystem files after a git-index failure (an untracked artifact can pass as
committed), and applies TXT header subtraction the sealed prereg did not specify. Each is a small,
testable change to landed harness code; none changes a landed number.

**PREMISE (step 0, BINDING before-condition):** demonstrate each hole on a construct BEFORE changing code
and PRINT the result: (a) run `g310_instance_key` and `g330_run_attempt2` entry points with and without the
opt-out on a synthetic input and show no test asserts byte-parity; (b) feed `verify_snapshot` a snapshot
list with one hash altered and show scoring proceeds on the reduced set; feed `read_arm_csv` a batch8 file
saved under the `fp32` name and show it is accepted; (c) feed the census checker a JSON list whose length
matches a count but whose entries carry no sha256/timestamp, and a path present on disk but not in the git
index, and show RECOMPUTABLE is returned. **Any hole that does NOT reproduce is reported CLOSED ALREADY
with the evidence, and the row continues for the rest.**

METHOD:
  1. **(a) OPT-OUT PARITY TESTS.** For each hooked runner, a test that runs the entry point twice on the same
     synthetic input (with and without `--no-env-sidecar`), asserts every output file except
     `environment.json` is byte-identical, and asserts `environment.json` is absent when opted out.
  2. **(b) FATAL SNAPSHOT + EXPECTED ARM.** `verify_snapshot(...)` gains a `fatal: bool = True` keyword
     (default fatal for reruns; the attempt-2 behaviour stays reachable via `fatal=False` with an explicit
     log line) that raises on any missing or mismatched frame with the game and frame id in the message;
     `read_arm_csv(path, expected_arm: str | None = None)` raises when the file's arm cell differs from
     `expected_arm`; `g327_report` passes the arm it expects. Tests for both. Recompute the committed G327
     attempt-2 report from the committed CSVs through the changed reader and assert byte-identity (no
     number moves).
  3. **(c) CENSUS CHECKER RIGOUR.** A snapshot-list entry counts as RECOMPUTABLE only if it carries sha256
     (64 hex), a timestamp, and a row count, and a chain entry references its predecessor's sha256 when
     more than one snapshot exists; otherwise the verdict is `UNVERIFIED_SNAPSHOT` (a new verdict word,
     additive). The filesystem fallback becomes an explicit `--construct-only` flag (default off: a
     git-index failure raises with the git error). TXT artifacts count lines only (no header subtraction)
     unless a `--txt-header` flag is given. Re-run the G319 sweep over the same 13 entries and report the
     verdict deltas per memo with n (the committed `sweep.csv` is frozen; write a new `sweep_g332.csv`).
  4. **CHANGE NOTHING ELSE.** No landed memo, artifact, threshold or register edit; every existing function
     signature stays callable with its old arguments (B2); every touched file <= 300 lines (extract to a
     new module if needed; `test_loc_rail_scope.py` must stay green).

**HONEST LIMITATIONS to state, not discover:** these are guards on harness code, not measurements; the
re-swept verdict deltas describe the checker, not the memos; no rerun of any detector, matcher or sim.

ACCEPTANCE RULE:
  metric        = the premise demonstrations (one print per hole); the tests (parity x2, fatal snapshot,
                  expected arm, snapshot-list rigour, construct-only fallback, TXT rule); the G327 report
                  byte-identity check; the G319 re-sweep delta table with n
  before        = the three holes reproduce on constructs as named by the verifiers
  bar           = every hole that reproduced has a test that fails on the old code and passes on the new;
                  the committed G327 report recomputes byte-identical; 0 landed files edited except the
                  named harness modules and their tests
  n             = the holes (exhaustive: a x2, b x2, c x3); the 13 G319 sweep entries
  eye check     = NONE. Say that.
  must not move = every landed memo, artifact and hash; `src/`, `domains/`, `api/`, `kernel/`, `intel/`;
                  `data/`; the pod; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g332_harness_hygiene_2026-09-08.md` (<= 60 lines) with VERDICT on line 1,
the premise prints, the test list, the byte-identity result, the re-sweep delta table, a **NOT VERIFIED**
list, wall time and the SHA-256s; plus `docs/evidence/tracking/g332_harness_hygiene_2026-09-08/sweep_g332.csv`
(integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>`
append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g332_harness_hygiene.py` plus the existing test file of every touched module
(`test_g62_environment_sidecar.py`, `test_g327_batch_stability.py`, `test_g319_census_recomputable.py`,
`test_g310_instance_key.py`, `test_g330_panorama_identity.py`), each alone. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
