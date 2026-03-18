---
phase: quick
plan: 1
subsystem: cv-tracker
tags: [ball-tracking, nba-api, benchmarks, quality]
dependency_graph:
  requires: []
  provides: [build_live_mask, ball_valid_live_metric, vision_fallback]
  affects: [src/data/nba_enricher.py, src/pipeline/unified_pipeline.py, _bench_run.py, tests/test_hardening.py]
tech_stack:
  added: []
  patterns: [frame-mask-from-pbp, vision-based-suspension, live-dead-split-metrics]
key_files:
  created: []
  modified:
    - src/data/nba_enricher.py
    - src/pipeline/unified_pipeline.py
    - _bench_run.py
    - tests/test_hardening.py
decisions:
  - "build_live_mask uses bulk PBP cache (pbp_{game_id}.json) not per-period cache to avoid NBA API calls"
  - "Vision fallback threshold 20 frames chosen to catch short warmup/ad breaks without false positives during brief ball-tracking gaps"
  - "Live radius 5s / dead gap 30s from PBP events — matches replay duration heuristic"
  - "_SHOT_CLOCK_ABSENT_THRESHOLD guard (sc_ever_seen) preserved so vision fallback only fires when OCR never detected a clock"
metrics:
  duration: "~15 minutes"
  completed: "2026-03-18"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 4
  tests_added: 8
---

# Phase Quick Plan 1: Ball Valid 80% — NBA API Live Mask + Guard Summary

One-liner: PBP-derived live/dead frame mask, Guard 2/3 `not _bbox_from_hough` verification, vision-based non-live fallback, and split bench metrics for honest ball_valid_pct reporting.

## What Was Built

### Task 1 — Guard 2/3 verification + results dict (commit cf7126c)

Verified `not _bbox_from_hough` is present in Guard 2's elif condition in `ball_detect_track.py`. This prevents Guard 2 from firing on valid Hough re-detections (the bos_mia regression root cause: CSRT tracked a crowd object, Hough independently re-detected the real ball 250px away, Guard 2 discarded the valid Hough detection as a "jump").

Guard 3 already correctly skips orange check for fresh Hough/template detections. Both `jump_resets` and `suspended_frames` are returned in the results dict from `run()`.

### Task 2 — build_live_mask() + vision-based fallback (commit 60a58c2)

**build_live_mask(game_id, video_fps=30.0)** added to `src/data/nba_enricher.py`:
- Reads `data/nba/pbp_{game_id}.json` (bulk NBA API raw format, already cached)
- Converts PCTIMESTRING game clock to absolute frame index: `frame = (period-1)*720 + (720 - remaining_sec)) * fps`
- Marks ±5s windows around live-play events (EVENTMSGTYPE 1-6) as "live"
- Marks >30s gaps between live events as "dead_ball"
- Everything else is "unknown" — caller uses `mask.get(frame_idx, "unknown")`
- Returns `{}` if no cache file found (safe fallback)

**Vision-based fallback** added to `src/pipeline/unified_pipeline.py`:
- `self._no_ball_vision_streak: int = 0` added to `__init__`
- Increments when `_last_ball_2d is None and not _ball_track_suspended`, resets when ball found
- After OCR section: if `not _sc_ever_seen and not _ball_track_suspended and _no_ball_vision_streak >= 20 and len(yolo_results) < 8` → set `_ball_track_suspended = True`
- This catches warmup/ad break/halftime on clips where ScoreboardOCR cannot read the broadcast font

### Task 3 — bench updates + 8 new tests (commit 0105ad1)

`_bench_run.py`:
- `--frames` default changed 300 → 3600 (2 minutes of gameplay at 30fps)
- `evaluate_layers()`: when `game_id` is present, calls `build_live_mask()` and computes `ball_valid_live` / `ball_valid_dead` / `live_frames` / `dead_frames` on the L2_Ball layer
- `build_summary()`: surfaces `ball_valid_live` and `ball_valid_dead` into the summary dict
- Print block: shows live/dead split when `game_id` is provided

`tests/test_hardening.py` — 8 new tests in 3 classes:
- `TestBuildLiveMask`: real cache returns valid values, missing game returns `{}`, type is always dict
- `TestVisionFallback`: `_no_ball_vision_streak` present in `__init__` source
- `TestBenchDefaultFrames`: `default=3600` present, `ball_valid_live`/`ball_valid_dead` present in bench source

## Commits

| Commit | Message |
|--------|---------|
| cf7126c | fix(ball_track): orange CSRT guard + suspension threshold + jump_resets counter |
| 60a58c2 | feat(ball_track): build_live_mask in nba_enricher + vision-based non-live fallback |
| 0105ad1 | feat(ball_track): build_live_mask, live/dead bench split, 3600 default, vision fallback |

## Deviations from Plan

None — plan executed exactly as written.

Guard 2/3 were already correct (prior session had already applied the `not _bbox_from_hough` fix and results dict additions). Task 1 confirmed the in-flight state and committed the modified files.

## Must-Haves Verification

| Truth | Status |
|-------|--------|
| Tests in test_hardening.py and test_phase2.py remain green | PASS — 150 passed, 2 skipped |
| Guard 2 skip for fresh Hough detections is in place | PASS — `not _bbox_from_hough` in Guard 2 elif (line 361) |
| build_live_mask() exists in nba_enricher.py | PASS — importable and callable |
| _bench_run.py default --frames is 3600 | PASS — `default=3600` confirmed |
| Vision-based non-live fallback fires when _sc_ever_seen is False and ball absent 20+ frames with <8 persons | PASS — code present and tested |
| _bench_run.py reports ball_valid_live and ball_valid_dead when game_id is provided | PASS — in evaluate_layers() and build_summary() |

## Self-Check: PASSED

All files exist and all commits are present in git log.
