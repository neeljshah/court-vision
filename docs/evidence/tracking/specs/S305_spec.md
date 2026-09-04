GAP S305 | sport all | worktree aXX | log cx_s305_master_failing_tests_repair
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: codex test audit (the orchestrator-held codex test audit (local-only; NOT a lane input) section B): two
  tests fail identically on
  master. (1)
  scripts/platformkit/eval_gate/test_calibration_report.py: 9 passed / 1 failed -- `assert report[key] ==
  landed[key]` with ece_after 0.024842541854003943 vs the frozen S05 artifact 0.039002202208806645; classified a
  REAL REGRESSION: S212 replaced the legacy global `_oof_per_regime` path while promising the default unchanged.
  (2) scripts/platformkit/answers/test_calibration_scoreboard_regex.py: 3 passed / 1 failed -- literal
  `assert result["improved_ece"] == 0.024842541854003943` while the resolver reads the tracked artifact value
  0.039002202208806645; classified a STALE FIXTURE.
PREMISE (step 0): reproduce both failures once (the answers file via ~/bin/pod_run <aN> -- python -m pytest
  <file> -q -p no:cacheprovider; it exceeds local RAM); quote the failing assertions.
CHANGE: copy 6226fb042^:calibration_report.py::_oof_per_regime verbatim and install it under the new alias
  _legacy_oof_per_regime.
  Call `_legacy_oof_per_regime(...) if key_source == "global" else oof_per_regime(...)`; never rewrite S05.
  (2) in the answers test load `Path(result["source_artifact"])` and assert `result["improved_ece"] ==
  artifact["ece_after"]` (tracked-file authority, no drifting scalar). Both files named; nothing else changes.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames);
  engines and every existing module byte-identical unless the CHANGE names the file (SHA-256 printed).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the two test files' pass counts before/after; the global-key ece_after value after the fix
  before        = 9/10 and 3/4 passing on master (verifier memos S275, S259 confirm identical master failures)
  bar           = 10/10 and 4/4 pass (answers file via pod_run); global-key ece_after equals the frozen S05
                  artifact 0.039002202208806645 exactly; every other key_source output byte-identical to before
  n             = 2 test files (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns both files (answers via pod_run) and diffs the
                  non-global outputs before/after
  must not move = the frozen S05 artifact; every other test file; every threshold; nothing charged
NON-TAUTOLOGY: the fix restores the legacy path for key_source == "global" ONLY; the S212 route stays the
  default for every other key_source and its outputs are proven unchanged.
EVIDENCE: docs/evidence/harness/S305_master_failing_tests_repair_2026-09-04.md + JSON.
TEST: add exactly tests/platformkit/eval_gate/test_s305_master_failing_tests_repair.py; also run the two repaired
  regression files one at a time.
REPORT: before/after counts, the ece_after value, unchanged-output diff, SHA. No push. NEVER PARK.
