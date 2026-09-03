GAP S154 | sport all | worktree a16 | log cx_s154_ledger_schema_skip
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it; self-check
against every line of section B before you report. S-row: eye check = n/a.
PREMISE (step 0): scripts/platformkit/eval_gate/test_ledger_schema_s13.py ledger_copy fixture
(:23-30) does `if not REAL_LEDGER.is_file(): pytest.skip(...)` -- an absent
data/cache/eval_gate/backtest_fwer.jsonl in the MAIN repo reads as a pass (every test in the
file skips). S153 fixed the identical defect in test_family_bars.py:32-39 with
scripts/platformkit/eval_gate/worktree_marker.is_worktree_checkout(). Measure: monkeypatch
REAL_LEDGER to a missing tmp path in the main repo and record that every test SKIPS today.
LIMIT (step 1): n/a (CONSTRUCT).
CHANGE (step 2): in ledger_copy, skip ONLY when worktree_marker.is_worktree_checkout(); otherwise
pytest.fail(f"charge ledger absent in the main repo: {REAL_LEDGER}"). Reuse worktree_marker; no
new module. Add two tests to the SAME file mirroring test_family_bars.py:315-330 (worktree ->
skip; main repo absent -> fail). Nothing else changes.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = ledger_copy behaviour with REAL_LEDGER absent, over the 2 marker modes
  before        = SKIP in both modes (n = 2 CONSTRUCT)
  bar           = worktree mode -> pytest.skip; main-repo mode -> pytest.fail; 2/2
  n             = 2 (CONSTRUCT); plus every pre-existing test in the file still PASSES with
                  the real ledger present (count before = count after, 0 skipped)
  eye check     = n/a (S-row); reproduction = verifier runs
                  `python -m pytest scripts/platformkit/eval_gate/test_ledger_schema_s13.py -q -p no:cacheprovider`
                  in the MAIN repo (all pass, 0 skipped) and in the worktree (ledger absent -> skips)
  must not move = scripts/platformkit/eval_gate/ledger.py, backtest_runner.py, worktree_marker.py,
                  data/cache/eval_gate/backtest_fwer.jsonl (byte-identical; read once per case, never written)
NON-TAUTOLOGY: the metric covers the fixture that every test in the file depends on; no test is
excluded. The FWER ledger is never opened for writing; 18 charges stay 18.
EVIDENCE: docs/evidence/harness/S154_ledger_schema_skip_2026-09-04.md -- before/after table,
the two pytest outputs verbatim, a NOT VERIFIED list. Calibration language only.
TEST: only `python -m pytest scripts/platformkit/eval_gate/test_ledger_schema_s13.py -q -p no:cacheprovider`
(in the worktree the ledger is absent, so expect skips there; the pass count is the verifier's).
COMMIT: explicit pathspec (the test file + the memo), in the worktree, no push. Report the sha.
NEVER PARK: finish with the report and SHA line.
