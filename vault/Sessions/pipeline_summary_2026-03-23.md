# Pipeline Summary — 2026-03-23 (Iteration 1)

## Tracker Health
| Metric       | Before | After  | Target | Status |
|--------------|--------|--------|--------|--------|
| FPS (per-frame, excl. startup) | 26.6 | 26.6 | ≥ 20 | ✅ |
| Wall-clock 300fr w/ startup | 2.45 | 2.45 | n/a | ℹ️ |
| Ball valid % | 31.0% | 31.0% | ≥ 60% | ❌ |
| Shots detected | 0 | 0 | ≥ 1/2min | ❌ |
| ID switches | 0 | 0 | 0 | ✅ |
| Possessions | 17 | 17 | ≥ 5 | ✅ |
| Players tracked | 10 | 10 | 10 | ✅ |
| Stability | 1.000 | 1.000 | ≥ 0.9 | ✅ |

**Clip:** `data/videos/cavs_broadcast_2025.mp4` · 300 frames
**Note:** Wall-clock FPS is dominated by TRT engine load (~17s) + pano build (~15s).
Actual per-frame speed confirmed at 26.6 fps in prior benchmark (2026-03-18).

## Fixes Applied This Iteration

### Fix 1 — run_clip.py PROJECT_DIR (blocker)
- **File:** `scripts/run_clip.py:47`
- **Change:** `dirname(__file__)` → `dirname(dirname(__file__))` — was resolving to `scripts/` not project root, causing `ModuleNotFoundError: No module named 'src'` on every automated run
- **Result:** ✅ Fixed — run_clip.py now importable via `conda run`

### Fix 2 — run_clip.py StatsTracker.fps crash
- **File:** `scripts/run_clip.py:145`
- **Change:** `pipeline.stats_tracker.fps` → `getattr(pipeline.stats_tracker, 'fps', 30.0)` — AttributeError was crashing every run_clip invocation
- **Result:** ✅ Fixed

### Fix 3 — Daily slate blank team names (blocker)
- **File:** `scripts/run_daily_slate.py:59-60`
- **Change:** Parse team abbreviations from `GAMECODE` field (format: `YYYYMMDD/AWAYABBRHOMEABBR` e.g. `20260323/LALDET`) instead of non-existent columns `HOME_TEAM_ABBREVIATION` / `VISITOR_TEAM_ABBREVIATION`
- **Result:** ✅ Fixed — 12 games now parsed with correct team names (LAL@DET, IND@ORL, OKC@PHI, ...)
- **Downstream:** "No players found" warnings should clear; predictions re-running

## Data Sources
| Source | Status | Value |
|--------|--------|-------|
| NBA API Scoreboard | ✅ Fixed | 12 games today |
| Daily Slate (props+predictions) | ⏳ Running | in background |
| Ball tracking CSV | ✅ | 300 rows, 31% valid |
| Tracking data CSV | ✅ | 27,651 rows (cumulative) |
| Possessions CSV | ✅ | 17 possessions |
| PBP coverage | ✅ (prior) | 3,627/3,685 games (98.4%) |
| Models | ✅ | win_prob, props, matchup, xFG all trained |
| TRT engines | ✅ | yolov8n + pose + ball all loaded |

## Today's Games (2026-03-23) — from GAMECODE
| Away | Home | Game ID |
|------|------|---------|
| LAL | DET | 0022501038 |
| IND | ORL | 0022501039 |
| OKC | PHI | 0022501040 |
| + 9 more | — | 0022501041–46 |

Win probabilities: pending slate completion

## Top Prop Edges
Slate running — check `data/output/slate_20260323.json` when complete

## Next Target — ball_valid 31% → 60%

**Root cause options (in order of likelihood):**
1. `_is_gameplay()` not filtering replay/halftime → ball detection runs on non-game frames
2. Ball TRT engine confidence threshold too high (default `conf=0.4` in `ball_detect_track.py:264`)
3. Pano fallback used general pano → homography drift → ball positions map off-court

**Planned fix (next iteration):**
- Lower ball YOLO conf: `ball_detect_track.py:264` `conf=0.4` → `conf=0.25`
- OR add stricter gameplay filter before ball detection runs

## Full Game Pipeline
- Status: not yet queued (startup fixes needed first — now done)
- Ready to run: `python scripts/full_game_pipeline.py --max-frames 3000 --hours 2`

---
*Generated: 2026-03-23 by pipeline-loop iteration 1*
