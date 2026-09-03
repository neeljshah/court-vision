# S153 -- missing evidence must not read as a pass (test_family_bars.py)

Date 2026-09-03 | register row S153 | parent S144 | lane: harness fix (main repo, master)
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q, self-checked below.

## STEP 0 -- PREMISE (Q8), re-measured, CONFIRMED

The three guards, as landed by S144, before this change:

| test | guard lines | condition |
|------|-------------|-----------|
| `test_k_family_counts_the_two_historical_mlb_arm_charges` | 183-185 | `if not real.exists(): pytest.skip(...)` |
| `test_the_two_k_counters_agree_on_every_family_of_the_real_ledger` | 259-261 | same |
| `test_the_frozen_39_family_counts_are_unchanged_by_s134` | 279-281 | same |

All three read `data/cache/eval_gate/backtest_fwer.jsonl` and skipped with the
reason "the private charge ledger is absent in this worktree". The condition is
FILE EXISTENCE only -- it does not distinguish a worktree from the main repo, so
the same absence in the main repo (a deleted, moved or unbuilt ledger) reads as a
pass. Premise is therefore NOT falsified; the fix proceeds.

Measured facts, this session, main repo `C:/Users/neelj/nba-ai-system`:

- `data/cache/eval_gate/backtest_fwer.jsonl` EXISTS, 18 rows, 4644 bytes,
  md5 `a4ae7c13995672e478d59770591b83ba`.
- `python -m pytest scripts/platformkit/eval_gate/test_family_bars.py -q`
  -> **20 passed** in 1.68 s, **0 skipped**. All three tests execute here.
- `.git` in the main repo is a **DIRECTORY** (`drwxr-xr-x`).
- In a codex worktree (`.claude/worktrees/agent-a2659481984a5ca9a`) `.git` is a
  **FILE**, 76 bytes ASCII, content
  `gitdir: C:/Users/neelj/nba-ai-system/.git/worktrees/agent-a2659481984a5ca9a`.
- That worktree has **no `data/cache/eval_gate`** (`ls` -> No such file or
  directory); the FWER charge ledger is never junctioned into a worktree.

## CHANGE (smallest that holds)

New helper `scripts/platformkit/eval_gate/worktree_marker.py` (30 LOC):

    is_worktree_checkout(root=None) -> True iff FOUNDRY_WORKTREE=1 is set
    or <repo root>/.git is a FILE (a "gitdir:" pointer) rather than a directory.

It carries an assert-based `__main__` self-check (both branches) -- runs clean.

In `test_family_bars.py` the three duplicated guards are replaced by ONE shared
`require_ledger(path=FWER_LEDGER)` (line 31), so the fix lives where all three
call sites route through rather than in each caller:

- worktree checkout -> `pytest.skip("worktree checkout: <path> is never
  junctioned into a worktree")`;
- main-repo checkout with the ledger absent -> `AssertionError("main-repo
  checkout: the FWER charge ledger is absent: <resolved path>")` -- loud, with
  the path;
- otherwise returns the path and the test runs as before.

Call sites now read `real = require_ledger()` at lines 200, 274, 292. No
assertion, threshold, bar or expected count inside those three tests changed
(B10/Q3): still 18 rows, still `{ingame_arms_mlb: 2, ingame_arms_nba: 1,
soccer_gate: 1}`, still 41 families.

## TESTS (both modes, and the existing 20)

Two new tests in the same file:

- `test_a_worktree_checkout_skips_the_ledger_tests` (line 315) -- sets
  `FOUNDRY_WORKTREE=1` via monkeypatch, asserts `is_worktree_checkout() is True`
  and that `require_ledger` raises `pytest.skip.Exception`.
- `test_a_missing_ledger_in_the_main_repo_fails_instead_of_skipping` (line 323)
  -- monkeypatches the marker to main-repo mode, points `require_ledger` at an
  absent `tmp_path` file, and asserts `pytest.raises(AssertionError, match=
  "charge ledger is absent")`. This is the S153 bar: a FAILURE, not a skip.

Runs, this session, in MASTER (A1):

    python -m pytest scripts/platformkit/eval_gate/test_family_bars.py -q
    -> 22 passed in 1.57s          (the original 20 + the 2 new; 0 skipped)

    FOUNDRY_WORKTREE=1 python -m pytest ... -q -rs
    -> 19 passed, 3 skipped in 1.27s
       SKIPPED [3] ...:39: worktree checkout: data\cache\eval_gate\
       backtest_fwer.jsonl is never junctioned into a worktree

    python scripts/platformkit/eval_gate/worktree_marker.py
    -> worktree_marker self-check OK

The three skips under the marker are exactly the three ledger tests -- the same
three that pass unskipped in the main repo.

## READ-ONLY / SCOPE

`data/cache/eval_gate/backtest_fwer.jsonl` md5 `a4ae7c13995672e478d59770591b83ba`
before and after, 18 rows, never written (the tests' own byte-equality asserts
still stand). `data/registry/` untouched. Nothing under `src/`, `kernel/`,
`api/`, `intel/`, `scripts/team_system/`; `family_bars.py`, `ledger.py` and every
codex worktree untouched. No pod contact, no push, no flag flipped ON.

## SELF-CHECK -- section B and section Q

- B1 not applicable (no metric). B2 ADDITIVE: no name, status or field changed;
  the three tests keep their names and assertions, one new module, two new tests.
- **B3 FALL-THROUGH LOSS is the defect being fixed**: the gate treated ABSENT
  evidence as acceptable. It now passes only in the one environment where absence
  is structural (the worktree), and fails loudly everywhere else.
- B4 no re-claim path. B5 no deploy. B6 no module moved or retired.
- B7/A3 not applicable (no sampling). B8, B9 not applicable.
- B10 / Q3 no bar or threshold moved -- byte-identical expectations.
- Q1, Q2, Q4, Q5, Q9 not applicable: nothing scored, no trial charged, no K read,
  no OOS comparison, no differential.
- Q6 calibration language only; no dollar, ROI, profit or edge language; no
  retracted figure appears.
- Q7 `n = 2 (CONSTRUCT)` -- the two checkout modes are exhaustive for the marker;
  both are exercised.
- Q8 premise re-measured above and CONFIRMED, not falsified.
- A5 reader sweep: `is_worktree_checkout` / `worktree_marker` / `require_ledger`
  are new symbols with no other readers (grep across `scripts/`).

## FOLLOW-UP (not fixed here -- outside this lane's file ownership)

`scripts/platformkit/eval_gate/test_ledger_schema_s13.py:26` skips on the SAME
absent real ledger with the same file-existence-only condition, so it carries the
identical defect and would now be a one-line adoption of `require_ledger` /
`is_worktree_checkout`. Two further skips are on genuinely rebuildable local
artifacts and are a weaker case: `test_calibration_report.py:176` (gate corpus
cache) and `test_tick_informative.py:66` (archived CSV). Filed for a new register
row, not touched by this lane.
