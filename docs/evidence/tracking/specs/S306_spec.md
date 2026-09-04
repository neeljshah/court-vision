GAP S306 | sport mlb | worktree aXX | log cx_s306_s106_requote_test
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: codex test audit (docs/research/codex_test_audit_2026-09-04.md section A): scripts/platformkit/eval_gate/s106_requote.py is
  named by four landed rows (S106, S121, S137, S143) and has zero direct importer tests -- the most-depended-on
  untested module in the harness. This row adds the per-file test only; the module is byte-identical.
PREMISE (step 0): print grep evidence of 0 direct importer tests and the four landed rows naming the module.
CHANGE (step 1): additive tests/platformkit/eval_gate/test_s106_requote.py on fixtures: a matched seq=2 tick
  becomes `game#2`; an unmatched tick stays seq=1; the input row count is unchanged; the before-CI reproduces
  before any correction; include a literal `#` cluster and an unmatched tick.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames);
  engines and every existing module byte-identical unless the CHANGE names the file (SHA-256 printed).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the four behaviours asserted with exact fixture values
  before        = 0 direct importer tests for s106_requote.py
  bar           = 4/4 asserted; module SHA-256 unchanged; row count identity asserted
  n             = 4 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns the test file
  must not move = s106_requote.py byte-identical; stored bars and series; nothing charged
NON-TAUTOLOGY: a behaviour absent today is recorded as a FINDING (xfail with reason), never skipped silently.
EVIDENCE: docs/evidence/harness/S306_s106_requote_test_2026-09-04.md + JSON.
TEST: exactly tests/platformkit/eval_gate/test_s106_requote.py; run only that file.
REPORT: the 4-row table, module SHA-256, test line, SHA. No push. NEVER PARK.
