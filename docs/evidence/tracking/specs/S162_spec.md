GAP S162 | sport all | worktree a12 | log cx_s162_manifest_worktree_glob
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0): scripts/platformkit/ops/factory_source_manifest.py:76 passes an ABSOLUTE pattern to
Path.glob, which raises NotImplementedError ("Non-relative patterns are unsupported") whenever the repo root is
not the process cwd -- measured: tests/platformkit/ops/test_factory_source_manifest.py = 5 passed in the main
repo, 3 passed / 2 failed in every codex worktree (S76 verifier). Re-measure both here: run the test file in this
worktree (expect 2 failures) and record the traceback line.
LIMIT (step 1): n/a (CONSTRUCT).
CHANGE (step 2): key the glob on a repo-root Path with a RELATIVE pattern (e.g. root.glob("data/**/x") or
Path(root, sub).glob(pattern)) so it works from any cwd; nothing else changes; every printed line, the
required() set and the --check-pod / --ship output byte-identical (diff the --pod-path-only output before and
after in the main repo, 61 sources).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = test_factory_source_manifest.py passed / 5, in the worktree AND in the main repo
  before        = worktree 3/5 (2 NotImplementedError), main repo 5/5
  bar           = 5/5 in both; --pod-path-only output byte-identical (61 lines) in the main repo
  n             = 5 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = the verifier runs the file in both trees and diffs the output
  must not move = the required-source set (61), the sidecars, pod_bootstrap_check probes, every threshold
NON-TAUTOLOGY: the same 5 tests run unmodified; no test skipped or rewritten.
EVIDENCE: docs/evidence/harness/S162_manifest_worktree_glob_2026-09-04.md -- before/after runs verbatim, the
output diff (empty), NOT VERIFIED list. ASCII only. Calibration language only.
TEST: no new test file needed (the 5 existing tests are the construct); run only that file, in both trees.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
