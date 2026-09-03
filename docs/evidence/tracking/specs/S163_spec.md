GAP S163 | sport all | worktree a13 | log cx_s163_loc_rail_scope
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0): tests/platformkit/test_s140_loc_rail.py enforces the 300-LOC rail on 3 named modules only;
family_combo_screen.py reached 301 LOC in S76 attempt 2 and was caught by a verifier, not by a test. Measure
today: for every scripts/platformkit/**/*.py (excluding tests), the line count; list every file over 300 with
its count (this is the BEFORE); the register says spec DATA modules are exempt (~600-750 lines) -- identify
which of the over-cap files are DATA modules (mostly literal tables / frozen specs) and which are code.
LIMIT (step 1): n/a (CONSTRUCT over the enumerated files).
CHANGE (step 2): widen the rail test to enumerate every scripts/platformkit/**/*.py; an explicit ALLOWLIST dict
{path: current_loc} for the files over 300 today (DATA modules and legacy code alike, each with a one-line
reason), and the assertion: any file over 300 must be on the allowlist and must not EXCEED its allowlisted
count (so nothing grows), any file not on the list must be <= 300. No module is edited by this lane.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = files over 300 LOC not covered by the allowlist / files enumerated
  before        = the measured list (n over cap of N files), rail covering 3 modules
  bar           = 0 uncovered; the rail covers N files; the allowlist reasons present; test passes in <= 5 s
  n             = N (CONSTRUCT, every scripts/platformkit/**/*.py enumerated)
  eye check     = n/a (S-row); reproduction = the verifier recounts with wc -l and diffs against the allowlist
  must not move = every module (0 code edits), every threshold, the 3 original assertions kept
NON-TAUTOLOGY: the allowlist freezes today's counts; it cannot be used to let a file grow.
EVIDENCE: docs/evidence/harness/S163_loc_rail_scope_2026-09-04.md -- the over-cap table (path, LOC, DATA or
code, reason), N, NOT VERIFIED list. ASCII only. Calibration language only.
TEST: the widened tests/platformkit/test_s140_loc_rail.py is the one test; run only that file.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
