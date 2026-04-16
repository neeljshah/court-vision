# Changelog

All notable changes to CourtVision. Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Docs
- Comprehensive documentation and vault update (README, API.md, ML_MODELS.md, tracking_pipeline.md, PRODUCTION_RUNBOOK.md, ARCHITECTURE.md, CHANGELOG.md)
- Updated 10 Obsidian vault files with real metrics, thresholds, and current state

---

## [Phase 13.5] — 2026-04-15

### Docs
- `13a4ba2` Update ARCHITECTURE.md — case-sensitivity fix on Windows
- `684561a` Update CLAUDE.md — 75 trained models, remove SYSTEM_OPTIMIZED.md ref, fix endpoint count
- `43589f2` Update ROADMAP and CLAUDE.md for 100-game readiness

### Refactor
- `5532ebc` Professional cleanup — remove 1.5GB tracked binaries, dead code, stale docs

### Fix (100-game blockers)
- `f904aa5` `/props` fallback to `predict_props` when stack yields empty predictions
- `f198ea0` Sanitize NaN edges in predictions_router JSON response
- `cd5f1ec` Phase G rsync uses SSH key auth or skips gracefully
- `abd4a6d` unified_pipeline writes empty CSVs on failure paths
- `818263f` main.py `/props` uses `stack_predict` (deduplicated with router)
- `243fe36` `/edge` uses win_probability model instead of hardcoded 0.5
- `0d80f83` Backtest gate fails closed on empty data
- `65aa185` Enforce MAX_DRAWDOWN_PCT in `kelly_corr`
- `f49fd7d` stitch_router predict_game signature fix
- `71ec893` Test fixes for prop stack + simulator integration

### Feat (100-game preparation)
- `4ae06c0` Prop correlation matrix for Kelly sizing in betting portfolio
- `66c4279` Wire CV-derived minutes into fatigue model in possession simulator
- `3dca4da` Isotonic calibration layer for prop probabilities (Kelly safety)
- `075f235` Backtest endpoint for prop validation gate
- `d265ece` Dedup processed list by hash and isolate per-game failures (BLOCKER fix)

### Fix (Phase G pre-launch hardening)
- `9502832` Fail loud on live model import errors in possession simulator
- `7302950` P1-6/7/8 remove dead court_zone param, add fallback warning, (path,player) cache key
- `39f0081` P0-5 document `_get_opp_stl_rate` always returns 0.08 (stl_per_poss absent from cache)
- `64706de` P0-4 preflight video existence check logs missing path before worker spawn
- `d394a47` P0-3 `_is_complete` deletes zero-row outputs; `_remove_zero_frame_processed` cleans done log
- `ca741d3` P0-1/P0-2 PossessionSimulator top-level import, `_MODEL_FEATURE_COLS` excludes 4 sim_* (67 vs 71)
- `a364b4c` 10 pre-launch hardening fixes for 100-game RunPod run
- `e9d6986` Write props_v2 metrics sidecar JSON on retrain
- `d279378` Add `--all-missing` flag to post_tracking_enrich.py
- `1296448` Add `data/events/` to rsync pull in watch_and_sync.sh
- `2c6cf5f` Tracking + data backlog sweep
