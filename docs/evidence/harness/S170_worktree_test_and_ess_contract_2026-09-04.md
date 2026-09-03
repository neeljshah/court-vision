# S170 worktree test and ESS contract (2026-09-04)

Spec: `docs/evidence/tracking/specs/S170_spec.md`. Contract self-check: sections
B and Q. This is a two-part CONSTRUCT fix (`n = 2 + 2`); reproduction replaces
an eye check. No numeric constant, threshold, FWER ledger, `data/`, or register
was changed.

## Premise re-check

Both findings were measured before the edit.

- Worktree command: `python -m pytest tests/platformkit/ops/test_private_helpers_tracked.py -q` failed 1/1 with the quoted precondition `assert by_stem, "expected some untracked scripts/**/_*.py (the rule is live)"` and `assert {}`.
- Main repository command, from `C:/Users/neelj/nba-ai-system`: the same one-file test passed, `1 passed in 4.95s`.
- `_require_columns` raised `ValueError("no non-null game/loss rows")` for no usable rows before `effective_sample_size` could return its six fields.
- `ingame_baseline_lock.py` instead used `{"n_games": 0, "n_eff": 0.0, "n_eff_bound_ok": True}` when no pairs existed.

## Before / after

| item | before quote | after quote | status |
|---|---|---|---|
| (a) helper-test precondition | `assert by_stem, "expected some untracked scripts/**/_*.py (the rule is live)"` | worktree: `pytest.skip("worktree checkout: untracked private-helper precondition absent: %s" % helper_glob)`; main: `pytest.fail("main-repo checkout: untracked private-helper precondition absent: %s" % helper_glob)` | FIXED |
| (b) empty ESS contract | `_require_columns(...)` then `ValueError("no non-null game/loss rows")`; baseline fallback had three keys | keyword-only `empty_ok=False`; opt-in returns `n_ticks`, `n_games`, `rho`, `design_effect`, `n_eff`, and `n_eff_bound_ok`; baseline lock calls `effective_sample_size(..., empty_ok=True)` | FIXED |

## Reproduction

All test files were run one file per command.

| command | observed result |
|---|---|
| `python -m pytest tests/platformkit/ops/test_private_helpers_tracked.py -q` in this worktree | `1 skipped in 3.00s` |
| `python -m pytest tests/platformkit/ops/test_private_helpers_tracked.py -q` in `C:/Users/neelj/nba-ai-system` | `1 passed in 4.95s` |
| `python -m pytest tests/platformkit/ingame/test_gap_effective_n.py -q` | `1 passed in 3.20s` |
| `python -m pytest scripts/platformkit/ingame/test_gap_effective_n.py -q` | `3 passed in 3.34s` |
| `python -m pytest tests/platformkit/ingame/test_gap_effective_n_bound.py -q` | `1 passed in 2.08s` |
| `python -m pytest scripts/platformkit/ingame/test_ingame_baseline_lock.py -q` | `3 passed in 5.16s` |
| `python -m pytest tests/platformkit/ingame/test_s166_verifier_housekeeping.py -q` | `1 passed in 1.57s` |

The new construct test enumerates the two ESS cases: default empty input still
raises, while `empty_ok=True` returns exactly the six-key empty summary with
`n_ticks=0`, `n_games=0`, `rho=0.0`, `design_effect=1.0`, `n_eff=0.0`, and
`n_eff_bound_ok=True`.

## NOT VERIFIED

- No model, threshold, FWER ledger, calibration computation, corpus score, or
  calibration decision was changed.
- The post-change helper test cannot exercise the main-repository failure path
  here because its tracked main repository contains untracked helpers and
  correctly passes. The main-repository test result above is the required
  observed mode; its explicit missing-precondition failure branch is source
  checked and will name the full helper glob path.
- No charged or scored comparison applies to this CONSTRUCT row.

## Contract self-check

- B1-B10: no metric denominator, schema removal, absence-as-pass gate, claim
  lifecycle, deployment, module relocation, render sample, independent score
  claim, recycled denominator, or bar changed.
- Q1-Q6 and Q9: no charged or scored comparison was added. Calibration language
  only.
- Q7-Q8: the two worktree modes and two empty-input cases are exhaustively
  enumerated construct cases, and both premises were re-measured before edits.
