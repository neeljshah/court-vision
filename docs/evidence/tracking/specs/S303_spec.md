GAP S303 | sport all | worktree aXX | log cx_s303_prereg_committed_object_seals
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: codex test audit (the orchestrator-held codex test audit (local-only; NOT a lane input) section D):
  persisted-artifact seal tests
  read the
  COMMITTED object; they hash a working FILE (raw or normalized) or `git hash-object` of the current file, so a
  dirty working copy passes. The landing recipe (S261 attempt 2d, worktree a13 commit ccb10fe9f) is: `git show
  HEAD:<prereg>` primary; normalized FILE bytes only after `git cat-file -e HEAD:<prereg>` proves absence.
PREMISE: enumerate all 15 audit rows, then name the exact 8 tracked-file hashing tests and 6 unique tracked
  prereg/spec paths; do not call either set 10.
CHANGE (step 1): additive tests/platformkit/test_prereg_committed_object_seals.py: for each of the 6 named prereg
  paths read `git show HEAD:<path>`, normalize nothing, hash the bytes above the seal line, compare to the embedded
  seal; a temporary git repo fixture commits a prereg, dirties the working FILE, and requires the committed bytes
  to be the ones checked; the fallback path is exercised on an uncommitted prereg. Existing tests untouched.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames);
  engines and every existing module byte-identical unless the CHANGE names the file (SHA-256 printed).
WHERE: local construct only. POD: n/a; above 500 MB use ~/bin/pod_run <aN> --fetch <outputs> -- <command>.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = committed-object seal match for 6 unique paths and all 8 tracked-file hashing tests; temp-repo
                  dirty-file and fallback cases.
  before        = 0/8 tracked-file hashing tests use committed-object primary (audit table).
  bar           = 6/6 unique paths match and 8/8 tests use committed bytes; dirty-file and fallback cases pass.
  sign          = improvement = baseline loss minus candidate loss; positive = candidate better; compared with
                  the frozen +0.004 bar.
  n             = 6 (CONSTRUCT: every unique tracked prereg/spec path named explicitly).
  eye check     = n/a (S-row); reproduction = verifier reruns the test file and one git show by hand
  must not move = every prereg artifact and existing seal test byte-identical; nothing charged
NON-TAUTOLOGY: a mismatching committed seal is a FINDING (list it); the test never rewrites a seal.
EVIDENCE: docs/evidence/harness/S303_prereg_committed_object_seals_2026-09-04.md + JSON.
TEST: exactly tests/platformkit/test_prereg_committed_object_seals.py; run only that file.
REPORT: the 8-test/6-path table, dirty/fallback lines, test line, SHA. No push. NEVER PARK.
