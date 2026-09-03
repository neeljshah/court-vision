GAP S170 | sport all | worktree a12 | log cx_s170_worktree_test_and_ess_contract
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0), two verifier findings from 2026-09-04, measure both first:
  (a) tests/platformkit/ops/test_private_helpers_tracked.py asserts a non-empty precondition (some untracked
      scripts/**/_*.py must exist) and therefore fails 1/1 in any clean codex worktree while passing in the main
      repo. Run it here (expect the failure) and in the main repo C:/Users/neelj/nba-ai-system read-only
      (expect pass); quote the assert.
  (b) scripts/platformkit/ingame/gap_effective_n.effective_sample_size RAISES ValueError on empty input
      (_require_columns) and has no empty-input contract, while ingame_baseline_lock.py:133 returns a 3-key
      fallback {n_games, n_eff, n_eff_bound_ok} that is a subset of the function's 6-key return (n_ticks, rho,
      design_effect absent). Quote both.
LIMIT (step 1): n/a (CONSTRUCT).
CHANGE (step 2): (a) make the precondition explicit: when no untracked helper exists the test SKIPS with the
worktree marker (scripts/platformkit/eval_gate/worktree_marker.is_worktree_checkout()) and FAILS in the main
repo naming the path, mirroring the S154/S156 pattern; (b) give effective_sample_size an explicit empty-input
return -- the full 6-key dict with n_ticks 0, n_games 0, rho 0.0, design_effect 1.0, n_eff 0.0,
n_eff_bound_ok True -- behind a keyword `empty_ok=False` that defaults to the OLD raising behaviour (additive),
and make the baseline_lock fallback call it with empty_ok=True so ONE shape exists; every existing caller
unchanged; one construct test for the empty path.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = (a) test_private_helpers_tracked: worktree -> skip, main repo -> pass or fail-with-path;
                  (b) empty-input shapes in the tree
  before        = (a) fails in a worktree; (b) 2 shapes (raise vs 3-key subset)
  bar           = (a) 2/2 modes correct; (b) 1 shape (the 6-key dict) with the default still raising; every
                  existing test importing gap_effective_n or ingame_baseline_lock still passes, one file at a time
  n             = 2 + 2 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = the verifier runs the two files in both trees
  must not move = every numeric constant in gap_effective_n.py, every threshold, the FWER ledger
NON-TAUTOLOGY: the default behaviour is unchanged; only the explicit opt-in adds the empty return.
EVIDENCE: docs/evidence/harness/S170_worktree_test_and_ess_contract_2026-09-04.md -- before/after quotes, test
table, NOT VERIFIED list. ASCII only. Calibration language only.
TEST: one new per-file test for (b); run it plus test_private_helpers_tracked.py, tests/platformkit/ingame/
test_gap_effective_n.py, test_gap_effective_n_bound.py, scripts/platformkit/ingame/test_ingame_baseline_lock.py,
one file per command.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
