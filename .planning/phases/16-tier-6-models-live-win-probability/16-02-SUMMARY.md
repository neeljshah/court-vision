---
phase: 16-tier-6-models-live-win-probability
plan: "02"
subsystem: prediction
tags: [lstm, win-probability, live-inference, xgboost-fallback, tier-6]
dependency_graph:
  requires: ["16-01"]
  provides: ["live_win_probability.py", "live_win_prob_metrics.json", "live_win_prob_lstm.pt"]
  affects: ["src/prediction/", "data/models/"]
tech_stack:
  added: [torch.nn.LSTM, sklearn.isotonic.IsotonicRegression]
  patterns: [stateful-inference, temporal-sequence-modelling, graceful-fallback]
key_files:
  created:
    - src/prediction/live_win_probability.py
    - data/models/live_win_prob_metrics.json
    - data/models/live_win_prob_lstm.pt
  modified:
    - tests/test_live_win_probability.py
decisions:
  - "Test signatures govern parameter names: input_dim/hidden_dim (not input_size/hidden_size)"
  - "extract_possession_features takes optional possession_idx; defaults to last possession"
  - "train_lstm_win_prob returns metrics dict directly (not tuple) to match test contract"
  - "xgb_fallback (not xgb_model) as LiveWinProbInference param to match test fixture"
  - "test_auc and test_calibration_brier kept as stubs (skipped) per plan — deferred to Plan 05"
metrics:
  duration_seconds: 588
  completed_date: "2026-04-24"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 1
---

# Phase 16 Plan 02: LSTM Live Win Probability Summary

**One-liner:** 2-layer LSTM (hidden_dim=64) + XGBoost fallback for possession-by-possession live win probability with spacing_index graceful degradation.

## What Was Built

### src/prediction/live_win_probability.py (283 LOC)

**`extract_possession_features(game_dict, possession_idx=None)`**
- Extracts 5 normalised floats from the last (or specified) possession
- Features: score_margin/10, time_remaining/2400, (spacing_index - 3.5)/1.5, momentum_score/5, lineup_net_rtg/5
- spacing_index absent → defaults to league avg 3.5 (no crash)

**`LiveWinProbLSTM(input_dim, hidden_dim, num_layers)`**
- 2-layer LSTM (batch_first=True, dropout=0.2) + FC head: Linear→ReLU→Dropout→Linear→Sigmoid
- Forward: (batch, seq_len, input_dim) → (batch, seq_len, 1) with all values in [0,1]

**`train_lstm_win_prob(game_sequences, epochs, ...)`**
- Temporal train/val split (no shuffle), mini-batch padding, Adam lr=1e-3, BCELoss, gradient clip=1.0
- Returns metrics dict: {val_auc, val_brier, epochs, n_games}
- Saves model to data/models/live_win_prob_lstm.pt
- Saves metrics to data/models/live_win_prob_metrics.json

**`LiveWinProbInference`**
- Stateful: possession_history accumulates across update() calls
- LSTM path: source='lstm', confidence=0.85
- Fallback path (lstm_model=None): source='xgb_fallback', confidence=0.65
- Error path: source='error', confidence=0.0, win_prob_home=0.5
- inference_ms < 500ms on CPU

**`calibrate_win_prob(predictions, outcomes)`**
- Isotonic regression calibration helper

**`load_inference_engine(device)`**
- Loads trained LSTM from disk if available, else returns XGBoost-only engine

## Test Results

| Test | Result |
|------|--------|
| test_lstm_trains | PASSED |
| test_features | PASSED |
| test_sparse_features | PASSED |
| test_inference_latency | PASSED |
| test_fallback_xgb | PASSED |
| test_auc | SKIPPED (stub — deferred to Plan 05) |
| test_calibration_brier | SKIPPED (stub — deferred to Plan 05) |

**5/7 tests pass** — matches success criteria exactly.

## Artifacts

- `data/models/live_win_prob_metrics.json` — {val_auc: 1.0, val_brier: 0.247, epochs: 10, n_games: 15}
- `data/models/live_win_prob_lstm.pt` — trained model state dict (synthetic 15-game seed)

## Deviations from Plan

### Auto-fixed: Test signature mismatch (Rule 1)

**Found during:** Task 1 analysis
**Issue:** Plan spec used `input_size`/`hidden_size` and `xgb_model` parameter names, but existing test stubs used `input_dim`/`hidden_dim` and `xgb_fallback`. Plan also specified `extract_possession_features(game_dict, idx)` as required, but test calls it as `extract_possession_features(game_dict)` with no idx. `train_lstm_win_prob` tests expected a dict return (not a tuple).
**Fix:** Implemented all signatures to match the test file (tests are authoritative contracts). Made possession_idx optional, defaulting to last possession.
**Files modified:** src/prediction/live_win_probability.py

## Self-Check: PASSED

| Item | Status |
|------|--------|
| src/prediction/live_win_probability.py | FOUND |
| data/models/live_win_prob_metrics.json | FOUND |
| data/models/live_win_prob_lstm.pt | FOUND |
| Commit 533ed0b9 (Task 1) | FOUND |
| Commit 10c7090f (Task 2) | FOUND |
