# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

## [Unreleased]

## [0.13.5] - 2026-04-21

### Added
- Ingest system P1-P6 complete: SQLite work queue, yt-dlp fetcher, parallel processing workers, quality backfill, status dashboard, B2 sync
- `ingest_preflight.sh` + `launch_single_3090_pod.sh` for single-GPU pod runs
- CalibrationLayer: `win_prob()` + `train_win_prob()` methods
- 7 prop models registered (pts/reb/ast/fg3m/blk/tov/stl) with live API serving

### Changed
- `unified_pipeline.py`: fixed max_frames stride bug — `gameplay_frames` (decoded) vs `max_frames` (source units) mismatch caused 60fps games to never stop
- `fetch_games.py`: archive.org fallback (Pass 2.5), android player client for YouTube bot bypass, highlights `min_dur` raised to 1800s, PREFLIGHT retry loop reads `phase_g_processed.txt` at startup to skip already-done game IDs
- `_VRAM_FLUSH_INTERVAL` set to 3000 (was 100) — flushing every 100 frames caused GPU syncs stalling CPU stages ~10×

### Fixed
- H1: memory + connection hygiene for 3090 pod
- H2: cross-filesystem rename + symlink safety
- H3: parallel worker isolation + retry on claim race
- H4: pod preflight script
- H5: final verification + runbook update

### Measured (walk-forward temporal-CV holdout, source `data/models/model_registry.json`)
- Props R²: pts=0.41, reb=0.38, ast=0.36, fg3m=0.29, tov=0.22, stl=0.18, blk=0.16
- CV games ingested: 29 usable (9 CLEAN + 20 PARTIAL) of 75 attempted (target: 80 CLEAN)

### Projected (gated on paper-trading gate ≥50 settled bets — _not yet measured_)
- CLV +14 bps/bet vs Pinnacle Shin-devigged close — backtested edge model
- Realized ROI +3.8% on 1u-Kelly-fractional — dependent on fill prices and book limits
- No live bets placed; paper-trading harness in flight (Phase 3)

[0.13.5]: https://github.com/neeljshah/court-vision/releases/tag/v0.13.5
