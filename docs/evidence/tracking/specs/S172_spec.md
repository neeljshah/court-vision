GAP S172 | sport all | worktree a10 | log cx_s172_absent_evidence_outside_eval_gate
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0): S153/S154/S156 routed every absent-evidence escape INSIDE scripts/platformkit/eval_gate through
scripts/platformkit/eval_gate/worktree_marker.is_worktree_checkout() (skip in a worktree, fail in the main repo).
The S156 verifier counted ~25 same-shape escapes OUTSIDE eval_gate (combo/, ingame/, intel_validation/, vault_feed/,
improve/, signals/, data_frontier/, interaction_factory/, pod_sprint/, top-level test_clv_*), and the S165 verifier
added tests/platformkit/foundry/test_ingame_grammar_nba_pairs.py (hard-depends on a gitignored CSV). Measure first:
grep every test file under scripts/platformkit and tests/platformkit for `pytest.skip(` / `return` guarded by a
path-exists check on a data/ or docs/evidence path; list file:line and the guarded path; count = N (the BEFORE).
LIMIT (step 1): n/a (CONSTRUCT over the enumerated escapes).
CHANGE (step 2): route each enumerated escape through the marker helper (skip only under is_worktree_checkout(),
pytest.fail naming the path otherwise) using the S156 pattern; no module edits; no assertion text changes; the
existing count of tests per file unchanged when the evidence is present. Where a file needs the pattern more than
twice, one private _require_<x>(path) helper per file.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = escapes routed through the marker / N enumerated
  before        = 0 / N
  bar           = N / N; for every touched file the main-repo run (evidence present) shows count-before ==
                  count-after with 0 new skips (the lane cannot run that here: state it as NOT VERIFIED and give
                  the exact per-file commands); in the worktree every touched file shows skips only, 0 failures
  n             = N (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = the verifier runs 5 of the touched files in the main repo
  must not move = every module under scripts/platformkit, the FWER ledger (never touched)
NON-TAUTOLOGY: the enumeration covers both test trees; no escape is left out because it was hard.
EVIDENCE: docs/evidence/harness/S172_absent_evidence_outside_eval_gate_2026-09-04.md -- the file:line table,
before/after counts per file, the main-repo commands, NOT VERIFIED list. ASCII only. Calibration language only.
TEST: no new test file; run each touched file once, one file per command, never a directory.
COMMIT: explicit pathspec in the worktree, no push; never touch the register or the ledger. Report the sha.
NEVER PARK; finish with the report + SHA.
