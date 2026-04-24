---
phase: "16"
plan: "04"
subsystem: api
tags: [websocket, live-win-probability, fastapi, lstm]
dependency_graph:
  requires: ["16-02"]
  provides: ["WebSocket /ws/win-prob/{game_id}", "upgraded /win-prob HTTP endpoint"]
  affects: ["api/main.py"]
tech_stack:
  added: [WebSocket, WebSocketDisconnect, asyncio]
  patterns: [lazy-import-guard, engine-per-connection, try/except fallback chain]
key_files:
  modified: ["api/main.py"]
decisions:
  - "WebSocket endpoint instantiates a fresh LiveWinProbInference engine per connection (stateless, cheap since LSTM is small)"
  - "/win-prob HTTP endpoint falls back to XGBoost baseline when _LIVE_INFERENCE_AVAILABLE=False"
  - "asyncio + logging added to main.py stdlib imports; log variable replaces raw print for WebSocket error path"
metrics:
  duration_minutes: 3
  completed_date: "2026-04-24"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 1
---

# Phase 16 Plan 04: WebSocket Win-Prob API Endpoint Summary

**One-liner:** WebSocket `/ws/win-prob/{game_id}` streams LSTM win probability per possession with <500ms target latency; `/win-prob` HTTP endpoint upgraded to use LiveWinProbInference with XGBoost fallback.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | WebSocket endpoint + /win-prob upgrade | 7528d74b | api/main.py |

## What Was Built

**WebSocket endpoint** (`/ws/win-prob/{game_id}`):
- Accepts connection, instantiates `LiveWinProbInference` engine via `load_inference_engine(device="cpu")`
- Loops `receive_json` → `engine.update(game_dict, possession_idx)` → `send_json`
- Handles `WebSocketDisconnect` cleanly; sends error JSON on unexpected exceptions
- Guarded by `_LIVE_INFERENCE_AVAILABLE` — sends error message and closes if module not importable

**HTTP endpoint upgrade** (`GET /win-prob/{game_id}`):
- When `_LIVE_INFERENCE_AVAILABLE`: builds minimal `game_dict` from query params, calls `engine.update()`, returns `win_prob_home`, `source`, `confidence`, `inference_ms`, `confidence_interval`
- Fallback: original XGBoost `_load_win_prob().predict()` path with `source="xgboost_baseline"`

**Imports added to api/main.py:**
- `asyncio`, `logging`, `log = logging.getLogger(__name__)`
- `from fastapi import FastAPI, WebSocket, WebSocketDisconnect`
- Lazy try/except block: `from src.prediction.live_win_probability import load_inference_engine, LiveWinProbInference`

## Verification

```
['/predictions/win', '/stitch/ws/realtime', '/win-prob/{game_id}', '/ws/win-prob/{game_id}']
```
Both routes registered. Syntax OK. Phase 13 tests: 5/5 passed.

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- api/main.py modified and committed (7528d74b)
- /ws/win-prob/{game_id} appears in app.routes
- /win-prob/{game_id} upgraded with LiveWinProbInference path
- test_phase13.py: 5 passed, 0 failures
