---
phase: 16-tier-6-models-live-win-probability
plan: "01"
subsystem: tests
tags: [tdd, stubs, live-win-probability, prop-pricing]
dependency_graph:
  requires: []
  provides:
    - tests/test_live_win_probability.py (7 stubs)
    - tests/test_prop_pricing.py (2 stubs)
    - tests/conftest.py sample_game_dict/sample_possession_sequence/mock_xgb_model fixtures
  affects:
    - plans 02-05 (all reference these test functions in verify commands)
tech_stack:
  added: []
  patterns:
    - pytest.mark.skipif(not _IMPORT_OK) for ImportError-safe stubs
    - pytestmark module-level skip with per-test @pytest.mark.skip for double guard
key_files:
  created:
    - tests/test_live_win_probability.py
    - tests/test_prop_pricing.py
  modified:
    - tests/conftest.py
decisions:
  - "Double-guard pattern: pytestmark skipif + per-test @skip ensures both 'module not found' and 'stub not implemented' cases are handled"
  - "sample_possession_sequence as separate fixture (not inlined in sample_game_dict) allows independent use by feature extraction tests"
metrics:
  duration_seconds: 83
  completed_date: "2026-04-24"
  tasks_completed: 3
  tasks_total: 3
  files_created: 2
  files_modified: 1
---

# Phase 16 Plan 01: Wave-0 Test Stubs Summary

**One-liner:** 9 pytest stubs (7 LSTM win-prob + 2 prop pricing) with 3 shared conftest fixtures — all skip on import, zero errors, downstream verify targets ready.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Add Phase 16 fixtures to conftest.py | c1ac1778 | tests/conftest.py |
| 2 | Create test_live_win_probability.py stubs | 8b44cf42 | tests/test_live_win_probability.py |
| 3 | Create test_prop_pricing.py stubs | d9adf1de | tests/test_prop_pricing.py |

## What Was Built

**tests/conftest.py** — 3 new fixtures appended (existing fixtures untouched):
- `sample_possession_sequence` — 12 dicts with home_pts/away_pts/time_remaining_s/spacing_index, scores increment realistically, time decrements from 2400s
- `sample_game_dict` — wraps possession sequence with team off/def ratings, home_lineup_net_rtg, outcome
- `mock_xgb_model` — `_MockXGB` class with `.predict()` returning `np.array([0.6])`, no XGBoost import required

**tests/test_live_win_probability.py** — 7 stubs:
- `test_lstm_trains` — output shape (1,3,1) check
- `test_auc` — val_auc >= 0.0 in metrics dict
- `test_features` — 5 finite floats from extract_possession_features
- `test_inference_latency` — inference_ms < 500ms on CPU
- `test_fallback_xgb` — source == 'xgb_fallback' when lstm_model=None
- `test_calibration_brier` — Brier < 0.25 after calibration
- `test_sparse_features` — missing spacing_index defaults to 3.5m league avg

**tests/test_prop_pricing.py** — 2 stubs:
- `test_roi` — backtest() returns dict with float 'roi'
- `test_distribution` — get_distribution() returns mean/std/p10/p50/p90 as floats

## Verification Results

```
9 tests collected, 9 skipped, 0 errors
(pytest tests/test_live_win_probability.py tests/test_prop_pricing.py -v)
```

All skip via `pytestmark = pytest.mark.skipif(not _IMPORT_OK, ...)` guard. Each test also carries individual `@pytest.mark.skip(reason="stub — implement after *.py exists")` for clarity.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- tests/test_live_win_probability.py: exists, 131 lines, 7 tests collected
- tests/test_prop_pricing.py: exists, 49 lines, 2 tests collected
- tests/conftest.py: modified, sample_game_dict/sample_possession_sequence/mock_xgb_model present
- Commits: c1ac1778, 8b44cf42, d9adf1de — all exist in git log
