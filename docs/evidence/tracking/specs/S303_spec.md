GAP S303 | sport all | worktree aXX | log cx_s303_prereg_committed_object_seals
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: codex test audit (docs/research/codex_test_audit_2026-09-04.md section D): 0/10 persisted-artifact seal tests read the
  COMMITTED object; they hash a working FILE (raw or normalized) or `git hash-object` of the current file, so a
  dirty working copy passes. The landing recipe (S261 attempt 2d, worktree a13 commit ccb10fe9f) is: `git show
  HEAD:<prereg>` primary; normalized FILE bytes only after `git cat-file -e HEAD:<prereg>` proves absence.
PREMISE (step 0): print the 10 seal tests and their current source (FILE / hash-object / HEAD) as the audit table.
CHANGE (step 1): additive tests/platformkit/test_prereg_committed_object_seals.py: for each of the 10 named prereg
  paths read `git show HEAD:<path>`, normalize nothing, hash the bytes above the seal line, compare to the embedded
  seal; a temporary git repo fixture commits a prereg, dirties the working FILE, and requires the committed bytes
  to be the ones checked; the fallback path is exercised on an uncommitted prereg. Existing tests untouched.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames);
  engines and every existing module byte-identical unless the CHANGE names the file (SHA-256 printed).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per prereg path: committed-object seal match (10 rows); temp-repo dirty-file case; fallback case
  before        = 0/10 committed-object primary (audit table)
  bar           = 10/10 committed seals match; dirty-file case reads committed bytes; fallback used only after
                  cat-file absence; a prereg whose committed seal does NOT match is reported, not skipped
  n             = 10 (CONSTRUCT: every persisted-artifact seal test enumerated)
  eye check     = n/a (S-row); reproduction = verifier reruns the test file and one git show by hand
  must not move = every prereg artifact and existing seal test byte-identical; nothing charged
NON-TAUTOLOGY: a mismatching committed seal is a FINDING (list it); the test never rewrites a seal.
EVIDENCE: docs/evidence/harness/S303_prereg_committed_object_seals_2026-09-04.md + JSON.
TEST: exactly tests/platformkit/test_prereg_committed_object_seals.py; run only that file.
REPORT: the 10-row table, dirty/fallback lines, test line, SHA. No push. NEVER PARK.
