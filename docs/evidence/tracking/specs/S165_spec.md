GAP S165 | sport all | worktree a17 | log cx_s165_foundry_conftest
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0): tests/platformkit/foundry/ has no conftest.py; after the S155 split the 2-line `_db` helper is
duplicated in test_results_db.py and test_results_db_archive.py, and other files in that directory define their
own sqlite/tmp fixtures. Measure: count the test files in tests/platformkit/foundry/ (N), how many define a
private db/tmp-ledger helper (k, list them with line numbers), and the two `_db` copies verbatim.
LIMIT (step 1): n/a.
CHANGE (step 2): add tests/platformkit/foundry/conftest.py with ONE shared fixture (a fresh ResultsDB in
tmp_path) and, for the two S155 files only, replace the duplicated `_db` with the fixture; every other file is
LEFT AS IS (report them as candidates). No assertion text changes; test names unchanged; no module change.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = copies of the `_db` helper across tests/platformkit/foundry/
  before        = 2 (measured)
  bar           = 0 (one conftest fixture); test_results_db.py 15 passed and test_results_db_archive.py 7 passed,
                  names identical to master by sorted --collect-only diff; every other file in the directory
                  still passes when run one file at a time (list the counts)
  n             = N files (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier runs the two files + 3 other files in the directory
  must not move = scripts/platformkit/foundry/** (0 module edits), the FWER ledger (never touched)
NON-TAUTOLOGY: the collect-only name diff proves nothing was dropped.
EVIDENCE: docs/evidence/harness/S165_foundry_conftest_2026-09-04.md -- N, k, the candidate list, test table,
NOT VERIFIED list. ASCII only. Calibration language only.
TEST: no new test file; the two S155 files are the construct; run each file separately, never the directory.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
