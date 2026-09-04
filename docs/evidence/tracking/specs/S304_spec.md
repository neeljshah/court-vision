GAP S304 | sport all | worktree aXX | log cx_s304_s108_features_asof_guards
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: codex test audit (docs/research/codex_test_audit_2026-09-04.md section A): scripts/platformkit/eval_gate/s108_features.py
  (named by S114 and S180) has zero direct importer tests, and it is the as-of feature joiner whose failure modes
  are leaks (a same-game column read, a duplicate-key source). This row adds the guard tests.
PREMISE (step 0): print grep evidence of 0 direct importer tests and the four public behaviours (file:line).
CHANGE (step 1): additive tests/platformkit/eval_gate/test_s108_features.py on fixtures: (a) a same-game column
  name is refused before any value is read; (b) a duplicate-key source is refused whole; (c) with two tables the
  first wins and the second fills gaps; (d) a missing value adds the indicator column. Plant one outcome-equal
  column and one legitimate as-of column; assert the plant is refused and the as-of column passes.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames);
  engines and every existing module byte-identical unless the CHANGE names the file (SHA-256 printed).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = four behaviours asserted (pass/fail each); the planted outcome-equal column refused
  before        = 0 direct importer tests for s108_features.py
  bar           = 4/4 behaviours asserted with exact fixture values; plant refused; as-of column accepted
  n             = 4 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns the test file
  must not move = s108_features.py byte-identical (SHA-256 printed); partition seed / SPINE; nothing charged
NON-TAUTOLOGY: if a behaviour is NOT implemented today, the test records it as a FINDING (xfail with reason),
  never a silent skip; the memo lists it as a NEW GAP.
EVIDENCE: docs/evidence/harness/S304_s108_features_asof_guards_2026-09-04.md + JSON.
TEST: exactly tests/platformkit/eval_gate/test_s108_features.py; run only that file.
REPORT: the 4-row table, module SHA-256, test line, SHA. No push. NEVER PARK.
