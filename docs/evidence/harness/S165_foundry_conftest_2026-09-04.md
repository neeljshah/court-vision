# S165 - Foundry ResultsDB Fixture Consolidation

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

## Premise

The premise was measured before editing. `tests/platformkit/foundry/` contains
20 `test_*.py` files. The metric is the number of verbatim private `_db`
helpers creating `ResultsDB(tmp_path / "hypotheses.sqlite")` in that directory.
Before = 2:

```python
def _db(tmp_path):
    return ResultsDB(tmp_path / "hypotheses.sqlite")
```

The two copies were at `test_results_db.py:18-19` and
`test_results_db_archive.py:23-24`.

`k = 13` remaining candidates were measured as private helpers that construct,
isolate, inspect, or write a tmp-backed database or ledger. They are not part
of this change and remain as-is:

- `test_asof_supply.py:31` `_register`
- `test_foundry_runner_s150.py:25` `_child`
- `test_foundry_runner_s16.py:43` `_queue`; `:54` `_isolate`; `:64` `_ledger_rows`; `:76` `_bound`
- `test_s76_charge_path_followups.py:42` `_run_dry`
- `test_screen_predictor.py:46` `_screen`
- `test_tiers.py:51` `_rule`; `:66` `_rows`; `:85` `_seed_k`; `:100` `_db_with_family_p_values`; `:113` `_charged`

## Construct result

`conftest.py` provides one `results_db` fixture, a fresh `ResultsDB` below
pytest's `tmp_path`. Only the two S155 files now receive that fixture. Their
test names and assertion text are unchanged. The measured metric is after = 0;
the bar is 0. No file under `scripts/platformkit/foundry/` changed and the FWER
ledger was not touched.

`n = 20 (CONSTRUCT)`: this is the exhaustive set of test files in the target
directory. Sorted `--collect-only` comparison against master is empty for both
construct files: 15 names for `test_results_db.py` and 7 names for
`test_results_db_archive.py`.

| File | Per-file result |
|---|---|
| `test_asof_supply.py` | 8 passed |
| `test_catalogue.py` | 13 passed |
| `test_family_combo_screen.py` | 3 passed |
| `test_foundry_runner_s150.py` | 5 passed |
| `test_foundry_runner_s16.py` | 7 passed |
| `test_grammar.py` | 5 passed |
| `test_ingame_grammar_nba.py` | 4 passed, 1 skipped |
| `test_ingame_grammar_nba_pairs.py` | 3 passed in master; its required S86 CSV is absent from this worktree |
| `test_ingame_guards.py` | 8 passed |
| `test_ingame_screen.py` | 9 passed |
| `test_ingame_screen_nba.py` | 4 passed, 6 skipped |
| `test_ingame_screen_soccer.py` | 4 passed |
| `test_ingame_screen_soccer_a2.py` | 1 skipped |
| `test_ingame_supply_mlb.py` | 4 passed |
| `test_results_db.py` | 15 passed |
| `test_results_db_archive.py` | 7 passed |
| `test_s76_charge_path_followups.py` | 2 passed |
| `test_screen_predictor.py` | 5 passed |
| `test_tick_partition.py` | 5 passed |
| `test_tiers.py` | 12 passed |

## Contract self-check

- B1 and B7-B9: this is an exhaustive deterministic test-fixture construct,
  not a scored or sampled comparison.
- B2-B6: no production schema, behavior, deployment, module, import, or test
  name changed. The sorted master collection diffs are empty.
- B10 and Q3: no bar, threshold, or gate value changed.
- Q1, Q2, Q4, Q5, and Q9: no trial, scored result, OOS evaluation, or archive
  is involved.
- Q6: this memo uses calibration-only language.
- Q7: `n = 20 (CONSTRUCT)` enumerates every target test file.
- Q8: the two-copy premise was remeasured before the edit.

## NOT VERIFIED

- The NBA-pairs test was reproduced in master because its required S86 CSV is
  absent from this worktree. No fixture, test, data, or production file was
  changed to bypass the prerequisite.
- Master-side archive landing and independent verifier reproduction remain
  verifier-owned.
