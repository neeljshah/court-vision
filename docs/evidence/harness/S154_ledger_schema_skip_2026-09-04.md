# S154 -- absent real ledger must not read as a pass (test_ledger_schema_s13.py)

Date 2026-09-04 | register row S154 | mirrors S153 (test_family_bars.py) | lane: worktree
C:\Users\neelj\nba-track-a16 (branch track-a16, master base), Codex down, executed directly.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q, self-checked below.

## STEP 0 -- PREMISE (Q8), re-measured, CONFIRMED

Before this change, `ledger_copy` (test_ledger_schema_s13.py:23-30) did:

    if not REAL_LEDGER.is_file():
        pytest.skip("real ledger absent (data/ is gitignored): %s" % REAL_LEDGER)

The condition is FILE EXISTENCE only -- it does not call `worktree_marker`, so it
cannot distinguish a worktree (where `data/cache/eval_gate` is never junctioned,
by design) from a main-repo checkout with a missing/deleted ledger. Premise is
NOT falsified; the fix proceeds.

Measured this session, worktree `C:/Users/neelj/nba-track-a16`:

- `worktree_marker.is_worktree_checkout()` -> `True` (`.git` is a file here).
- `data/cache/eval_gate/` is absent in this worktree (never junctioned, expected).
- Controlled construct: `t.ledger_copy.__wrapped__` (the pre-change fixture body)
  called directly with `REAL_LEDGER` monkeypatched to a path that does not exist,
  under both labelled modes -- since the pre-change code has no mode branch at
  all, both calls hit the identical unconditional `pytest.skip`:

  ```
  is_worktree_checkout() in this checkout -> True
  ('worktree-like (is_worktree_checkout True today)', 'SKIP: real ledger absent (data/ is gitignored): ...definitely_missing_ledger_xyz\backtest_fwer.jsonl')
  ('main-repo-like (hypothetical, current fixture has no branch on it)', 'SKIP: real ledger absent (data/ is gitignored): ...definitely_missing_ledger_xyz\backtest_fwer.jsonl')
  ```

  Script: scratch `s154_premise_check.py` (not committed -- a throwaway repro,
  reproduction command below re-derives the same fact from the shipped tests).
- `python -m pytest scripts/platformkit/eval_gate/test_ledger_schema_s13.py -q -p no:cacheprovider`
  in the worktree, BEFORE the change: `1 passed, 5 skipped in 2.02s` (the 5 tests
  that use `ledger_copy` all skip; the one test that does not use the fixture,
  `test_next_k_family_counts_aliased_rows_s89`, has its own separate
  `if not path.exists(): return` and passes trivially -- untouched by this row).

## CHANGE (smallest that holds)

`ledger_copy`'s body is unchanged in shape; the check moves into a new module
function `_require_real_ledger(path=REAL_LEDGER)` so the same two-mode branch
S153 shipped for `worktree_marker` is reused, not reimplemented:

    def _require_real_ledger(path=REAL_LEDGER) -> None:
        if path.is_file():
            return
        if worktree_marker.is_worktree_checkout():
            pytest.skip("real ledger absent (worktree checkout, ...): %s" % path)
        pytest.fail(f"charge ledger absent in the main repo: {path}")

`ledger_copy` now calls `_require_real_ledger()` in place of the old bare
`if not REAL_LEDGER.is_file(): pytest.skip(...)`. No new module -- `worktree_marker`
is imported and reused exactly as S153 shipped it. Nothing else in the fixture
(the `shutil.copyfile` line, the return value) changed.

## TESTS (both modes, 2 new + the 6 pre-existing)

Two new tests appended to the same file, mirroring test_family_bars.py:315-330:

- `test_a_worktree_checkout_skips_when_ledger_absent(monkeypatch, tmp_path)` --
  sets `FOUNDRY_WORKTREE=1`, asserts `is_worktree_checkout() is True`, and that
  `_require_real_ledger(<absent tmp_path file>)` raises `pytest.skip.Exception`.
- `test_a_missing_ledger_in_the_main_repo_fails_instead_of_skipping(monkeypatch, tmp_path)`
  -- monkeypatches `worktree_marker.is_worktree_checkout` to return `False`, and
  asserts `_require_real_ledger(<absent tmp_path file>)` raises
  `pytest.fail.Exception` matching `"charge ledger absent"`. This is the S154 bar.

Reproduction command (A2 -- the verifier re-runs this, no number is quoted
without it):

    python -m pytest scripts/platformkit/eval_gate/test_ledger_schema_s13.py -q -p no:cacheprovider

Output, this session, IN THE WORKTREE, AFTER the change:

    ...                                                                   [100%]
    3 passed, 5 skipped in 1.89s

The 5 skips are unchanged from before (same 5 tests, same reason: worktree mode,
ledger genuinely absent by design). The 2 new tests pass (`1 passed` -> `3 passed`);
`test_next_k_family_counts_aliased_rows_s89` is the third and is untouched.

## NON-TAUTOLOGY

The metric covers the one fixture every ledger_copy-consuming test in the file
depends on; no test is excluded. `data/cache/eval_gate/backtest_fwer.jsonl` is
read at most once per case and never opened for writing here -- the 18-row
charge ledger (S153's count) is untouched, `must not move` files unchanged.

## READ-ONLY / SCOPE

Only `scripts/platformkit/eval_gate/test_ledger_schema_s13.py` was edited (33
lines changed, file now 130 LOC). `ledger.py`, `backtest_runner.py`,
`worktree_marker.py` untouched (grep confirms `worktree_marker` gained one new
importer, this file). `data/cache/eval_gate/backtest_fwer.jsonl` was never
opened anywhere in this session -- per the lane's own scope, it was not looked
for in the main repo. No pod contact, no push, no flag flipped ON, nothing under
`src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/`.

## SELF-CHECK -- section B and section Q

- B1 not applicable (no metric excludes rows). B2 ADDITIVE: `ledger_copy`'s
  public behaviour (skip when absent, copy+return when present) is unchanged
  for every existing caller; only the previously-unreachable "absent in the
  main repo" branch gains a new, louder outcome.
- **B3 FALL-THROUGH LOSS is the defect being fixed**: absent evidence read as a
  pass in every context; it now fails loudly outside the one context (a
  worktree) where the absence is structural.
- B4 no re-claim path. B5 no deploy. B6 no module moved or retired -- reused
  `worktree_marker`, no orphaned import.
- B7/A3 not applicable (no sampling, no render). B8, B9 not applicable.
- B10 / Q3 no bar or threshold moved -- the 5 pre-existing tests' assertions and
  the ledger's own content are byte-identical before and after.
- Q1, Q2, Q4, Q5, Q9 not applicable: nothing scored, no trial charged, no K
  read, no OOS comparison, no paired-loss differential.
- Q6 calibration language only; no dollar, ROI, profit or edge word appears; no
  retracted figure (+18.38, 0.119, +54, 78.11, 8.94, 54.57) appears anywhere.
- Q7 `n = 2 (CONSTRUCT)` -- worktree-skip and main-repo-fail are the only two
  reachable modes for `_require_real_ledger`, both exercised by name.
- Q8 premise re-measured above and CONFIRMED, not falsified.
- A5 reader sweep: `_require_real_ledger` is a new name with the one caller
  (`ledger_copy`) and the two new tests; no other file imports it (grep across
  `scripts/`).

## NOT VERIFIED

- The main-repo FAIL path was exercised only via the monkeypatched
  `is_worktree_checkout -> False` construct test, not by an actual run against
  a genuinely-missing ledger in `C:\Users\neelj\nba-ai-system`. Per this lane's
  scope the real ledger was never looked for or touched in the main repo; A1
  (re-run in MASTER) is the verifier's own check, not this lane's.
  `docs/evidence/tracking/VERIFIER_CONTRACT.md` A1 covers this.
- "count before = count after, 0 skipped, with the real ledger present" (the
  acceptance rule's second `n` clause) was not measured here -- this worktree
  structurally lacks `data/cache/eval_gate/`, so all 5 ledger_copy tests skip
  both before and after this change by design, not by the code path this
  change touches. The verifier reproduces this clause in master.
- No render/eye check: S-row, n/a per contract Q7/A3.
