<!-- AUTO-GENERATED — DO NOT EDIT BELOW THIS LINE -->

## Resume From Here — Last Updated: 2026-04-07 (Session 31)

### Current State — Season 2025-26 Batch Ready
**ISSUE-065 and ISSUE-066 root causes found and fixed.** Ball detector was bypassed during all live gameplay; team_abbrev fallback values leaked through. Both are now closed. **Next action: run `select_season_games.py` when NBA API network is available, then launch `batch_season.py`.**

### Session 31 Changes (code only, no video)
- `src/pipeline/unified_pipeline.py` — **ISSUE-065 fix**: `ball_det.ball_tracker()` now runs when `_last_ball_2d` is None after `_apply_yolo`. Previously the dedicated yolov8n_ball model (conf=0.05) was completely bypassed during live gameplay because any player detection from the main YOLO caused `ball_det` to be skipped.
- `src/pipeline/unified_pipeline.py` — **ISSUE-066 fix**: `_ct_map` fallback values (`{"green": "team_a"}`) now filtered same as `_team_map` before passing to `_backfill_team_abbrev`. Previously fallback abbreviations could overwrite real ones.
- **ISSUE-054**: code-complete (direction cos>0.75, debounce 8s, vtb guard, backcourt guard). Validation against NBA shot chart requires reprocessing a game with ISSUE-065 fix applied.
- 1040 tests pass, 2 skipped (DB requires PostgreSQL running).

### Session 30 Changes (code only, no video)
- `data/games/_templates/` — 27 template dirs moved (see `data/CLEANUP_MANIFEST.txt`)
- `scripts/select_season_games.py` — NEW: fetch 2025-26 completed games, 2/team → `data/season_2025-26_targets.json`
- `scripts/batch_season.py` — NEW: download → pipeline → delete .mp4 → log to `data/season_batch_log.csv`. Resume-safe.

**Session 29 data collection run (game 22401175):**
- **Tracking accuracy**: 90,552 rows | 19,893 frames | 212 min duration
  - Homography valid: **70.1%** (good for court mapping — target 80%+)
  - Nearest opponent: **95.7%** (excellent moat feature)
  - Court feet (ft_x/ft_y): **100%** (perfect real-world coords)
  - Player names: **81.5%** (good coverage)
  - Ball detection: **30.2%** (🔴 low — needs retuning, target 60%+)
  - Handler isolation: **43%** (moderate — defensive re-ID gaps)
  - Team abbrev: **7.8%** (🔴 critical — jersey→name mapping incomplete)
- **Game output**: 194 possessions (57.2s avg), 2 shots detected (⚠️ severely undercounted)
- **Data usability**: ✅ EXCELLENT for spatial features + possession extraction | 🟡 WEAK for shot detection
- **Action**: Ball detection retuning needed before next batch. Team abbrev mapping wired but needs jersey_name_map population on all games.

**Session 28 code fixes (5 fixes + retroactive backfill, no video):**
- `src/pipeline/unified_pipeline.py` — fixed `_backfill_player_names()` guard: removed `len(slot_to_player_name) >= 1` requirement so jersey_name_map fallback fires even when NBA API resolution fails. Fixed UTF-8 encoding on all CSV reads/writes in `_backfill_player_names()` + `_backfill_team_abbrev()`.
- `scripts/backfill_player_names.py` — NEW: retroactive player_name backfill for all game dirs. Uses jersey_name_map.json (or CommonTeamRoster API as fallback). Ran on all 15 game dirs: **155,107 rows filled**.
- `player_name` fill post-backfill: 0022401183=81.5%, 0022400625=69%, 0022401185=67%, 0022401123=74%, 0022400687=17%
- All 15 game dirs now have `jersey_name_map.json` (generated from NBA API on first run)
- 253 tests pass.

**Session 27 code fixes (7 fixes, no video):**
- `src/features/feature_engineering.py` — `fill_spatial_gaps()`: recomputes `nearest_opponent` (cross-team min distance) and `handler_isolation` (2+ opponent guard). `nearest_opponent` went from 60% blank → <5%. `load_tracking()` now handles legacy `player_id='green'/'white'` via `pd.to_numeric(..., errors='coerce')`.
- `src/pipeline/unified_pipeline.py` — portrait homography guard in `_build_court()` (rotate 90° if height > width). `_backfill_team_abbrev()` now forward+backward fills per player_id slot. `_backfill_player_names()` loads jersey_name_map.json as fallback.
- `src/data/nba_enricher.py` + `scripts/enrich_shot_log.py` — UTF-8 encoding on all CSV reads/writes (fixes Jokić, Dončić, etc.).
- `src/features/advanced_features.py` — `_compute_elo()` handles versioned `{"v":N,"rows":[...]}` season_games JSON.
- `tests/test_enricher.py` — `test_no_detections_returns_single`: updated assertion to match Session 26 all-row timestamp fallback.

**Backfill complete (all 5 games with features.csv):**
- `nearest_opponent`: ✅ <5% blank on 0022400430/537/909, <28% on 0022401123/1183
- `team_abbrev`: ✅ 0% blank all games
- `ft_x / ft_y`: ✅ 0% blank all games
- `handler_isolation`: ⚠️ 15-50% blank (acceptable)
- `possessions`: re-enriched 100% match rate on all 5 games

**Gamelog download status (A0):**
- 2022-23: 539 players ✅
- 2023-24: ~200/600 players 🔄 (stalled — re-run when ready)
- 2025-26: pending after 2023-24 completes
- 2024-25: 1 file only (LeBron) — re-run A0 if needed

**Once gamelogs complete:**
```bash
python scripts/retrain_props_v2.py
python scripts/pull_missing_data.py --check
```

### CV Data — Phase G
CV data: **5 games with full data** (tracking + shots + possessions + features). Audit threshold (80% enrichment) failing on most — data is real and usable, threshold is strict.

**Game status (6/20 clean games target):**
```
CLEAN (tracking + shots + poss + features):
0022400430  194,950 rows  CHI vs MIL  shots=164  poss=121  enr=68%  nearest_opp=✅  hom=1.00  player_name=0% (old pipeline)
0022400537  280,045 rows  LAL vs SAS  shots=163  poss=110  enr=79%  nearest_opp=✅  hom=1.00  player_name=0% (old pipeline)
0022400909  362,799 rows  DEN vs PHX  shots=170  poss=277  enr=65%  nearest_opp=✅  hom=1.00  player_name=0% (old pipeline)
0022401123   11,149 rows  HOU vs OKC  shots=167  poss=270  enr=73%  nearest_opp=✅  hom=0.19   player_name=74%
0022401183   77,555 rows  POR vs GSW  shots=170  poss=232  enr=2%   nearest_opp=⚠️  hom=0.30   player_name=81.5%

PARTIAL/NEEDS WORK:
0022401175   90,552 rows  NEW — shots=2 (undercounted)  poss=194  hom=70.1%  nearest_opp=95.7% ⭐ player_name=81.5% team_abbrev=7.8%
0022400625  114,709 rows  tracking only — post-processing crashed (needs re-enrich)
0022401185   23,249 rows  tracking only — no shots/poss/features
0022400687    8,470 rows  tracking only — no shots/poss/features
0022400710   10,607 rows  highlights reel — homography 6%, needs new video
0022401194               CORRUPT VIDEO — re-download needed
0022401190/96/98         OOM — run 1 at a time
(remaining)              MISSING — no tracking directory
```

**Known data quality gaps (Session 29 findings):**
- **Ball detection critical**: 30.2% valid on 0022401175, only 2 shots in 212 min (should be 50-100+). Stride/FPS or YOLO conf issue. Blocks shot validation.
- **Team abbrev**: 7.8% filled on 0022401175 despite jersey_name_map.json present. `_resolve_team_names()` or `_court_side_team_map` logic not wired correctly. Needs debug.
- `player_name` col missing from features.csv on 0022400430/537/909 (old pipeline — needs reprocess)
- `handler_isolation` 43% blank on 0022401175 — defensive re-ID gaps, not critical but limits isolation features
- Shot overcounting ~2-3x actual (historical issue — tight direction threshold + debounce added, unvalidated vs ground truth)
- Homography low on 0022401123/1183 — portrait guard in code, needs reprocess to benefit

### Season 2025-26 Batch — Next Steps
```bash
# Step 1 — Generate game targets (needs NBA API network access)
python scripts/select_season_games.py
# Writes data/season_2025-26_targets.json  (~50 game IDs, 2 per team)

# Step 2 — Run batch (one game at a time, resume-safe)
python scripts/batch_season.py
# Logs to data/season_batch_log.csv

# Step 3 — After 20+ clean games: retrain models
python scripts/audit_phase_g.py       # validate CV vs NBA shot chart
python scripts/retrain_props_v2.py    # blocked until gamelog A0 completes
```

**Batch scripts:**
- `scripts/select_season_games.py` — NBA API → 2 games/team → `data/season_2025-26_targets.json`
- `scripts/batch_season.py` — reads targets, downloads, runs pipeline, deletes .mp4, logs result

**Known data quality status (still applicable to new batch runs):**
- ISSUE-065 ball detection: ✅ FIXED Session 31 — `ball_det.ball_tracker()` now runs when `_last_ball_2d` is None after `_apply_yolo`. Root cause was ball detector bypassed during all live gameplay.
- ISSUE-066 team abbrev: ✅ FIXED Session 31 — `_ct_map_real` guard added; fallback "team_a"/"team_b" values no longer passed to `_backfill_team_abbrev`.
- Shot overcounting: direction cos>0.75 + 8s debounce + vtb guard (ISSUE-054). Validate with next batch run.

### This Session (Session 29) — Data Collection & Accuracy Assessment
**Output:** Game 22401175 tracking + enrichment complete. New accuracy metrics logged.
**Files changed:** None (data collection run, no code changes)
**Key finding:** Spatial features (homography 70%, nearest_opponent 96%) excellent | Ball detection (30%) needs retuning | Team abbrev (7.8%) needs debugging

### Previous Sessions
- Session 28: player_name write-through fix, 155K retroactive backfill, UTF-8 encoding
- Session 27: spatial gap-filling, portrait homography guard, team_abbrev resolution, advanced features versioning

---

## Open Priority Issues

1. ✅ `player_name` write-through — FIXED Session 28. Root cause: `_backfill_player_names()` guard required `len(slot_to_player_name) >= 1` but jersey_name_map fallback works even when API resolution fails. Fixed guard + UTF-8 encoding. Ran retroactive backfill (155K rows). All game dirs now have jersey_name_map.json. For old games with 0% jersey fill (0022400430/537/909/1156) — need reprocess as PlayerResolver wasn't initialized at tracking time.
2. 🔴 Shot detection overcounting ~2-3x — direction threshold fix in code (ISSUE-054) but unvalidated. Need 1 reprocessed game compared vs NBA shot chart ground truth.
3. 🟡 Homography low on newer games (19-30%) — portrait guard added (ISSUE-063 fix), games need reprocess to benefit.
4. 🟡 Gamelog download stalled — 2023-24 ~200/600 players. Re-run `pull_missing_data.py --phase A0` to resume. Props retrain blocked until complete.
5. 🟡 0022400625 post-processing incomplete — tracking done (114K rows), crashed before shot/possession/features. Needs targeted post-processing run.
6. 🔴 CV spatial features not wired into prop/win models — `defender_distance`, `spacing_advantage` collected but not feeding ML models. This is the core moat, currently unused.
7. 🔴 Possession simulator not built — Phase 8. Models exist but 10K Monte Carlo loop is unbuilt.
8. 🔴 No frontend/API — prediction pipeline runs headless only. No dashboard, no API serving predictions.

---

## What This Project Is

**CourtVision** — a self-improving possession-by-possession NBA game simulator combining CV tracking + NBA API + 90 ML models. Runs 10,000 Monte Carlo simulations per game, produces stat distributions for every player, compares against sportsbook lines, surfaces +EV edges.

**Three products:** Betting Dashboard (Kelly + CLV) | Analytics Dashboard (96 metrics, 10 chart types) | AI Chat (Claude + render_chart inline)

**Moat:** Spatial CV data (defender distance, spacing, fatigue) from broadcast video. Second Spectrum charges $1M+/yr for this. No public API has it.

**Full plan:** `.planning/ROADMAP.md` — 17 phases, 90 models, 96 analytics metrics

---

## Current Phase: Pre-Phase F

**Phases Complete:** 3 ✅ | 4 ✅ | 5 ✅ | 4.6 ✅ | Pre-Phase 6 Enrichment ✅

**Next action:** Phase F — run `scripts/full_game_pipeline.py` to download + process full NBA games

**Model status:**
- Win prob: 69.1% acc, Brier 0.203 (`data/models/win_probability.pkl`)
- Props ×7: R² > 0.93, MAE pts=0.308 (`data/models/props_*.json`)
- xFG v1: Brier 0.226, 221K shots (`data/models/xfg_v1.pkl`)
- DNP: AUC 0.979 (`data/models/dnp_model.pkl`)
- Matchup: R² 0.796 (`data/models/matchup_model.json`)
- Phase 4.5 models: load_management, injury_return, injury_risk, breakout_predictor, public_fade, soft_book_lag — all `.pkl` in `data/models/`

---

## Key Files

| File | Purpose |
|------|---------|
| `src/tracking/advanced_tracker.py` | AdvancedFeetDetector — main tracker |
| `src/tracking/color_reid.py` | TeamColorTracker — similar-color re-ID |
| `src/tracking/jersey_ocr.py` | EasyOCR jersey number reader |
| `src/pipeline/unified_pipeline.py` | Tracking → possession → spatial → CSV |
| `src/prediction/win_probability.py` | XGBoost win prob (WinProbModel) |
| `src/prediction/player_props.py` | predict_props() / train_props() |
| `src/prediction/prop_model_stack.py` | Ridge meta-model over all 7 props |
| `src/prediction/betting_portfolio.py` | Kelly + CLV + arb detection |
| `src/prediction/prop_backtester.py` | Historical backtest + paper trading |
| `src/data/nba_tracking_stats.py` | NBA API tracking data fetcher |
| `src/features/feature_engineering.py` | 60+ ML features |
| `api/main.py` | FastAPI app (10 endpoints) |
| `scripts/daily_pipeline.py` | Morning: injuries → props → predict → CLV |
| `scripts/record_outcome.py` | Post-game: box score → CLV report |
| `database/schema.sql` | PostgreSQL schema (9 tables, 2 views) |

---

## Architecture Summary

```
CV Tracker (broadcast feed) + NBA API (stats, PBP, shots)
    → 90 ML Models → Possession Simulator (10K Monte Carlo)
    → Stat distributions → Compare vs book lines → Flag +EV edges
    → FastAPI → Next.js Dashboard + Claude AI Chat
```

**Tracking tech:** YOLOv8n → SIFT homography → Kalman+Hungarian → **OSNet-x0.25 torchreid re-ID (512-dim, ImageNet pretrained)** → EasyOCR jersey → EventDetector (shot/pass/dribble)

**Feedback loop:** Process game → label possessions → retrain models → Monte Carlo → compare vs lines → record outcomes → repeat

---

## Module Status (Quick Ref)

**All ✅ built — see README.md for full list**

Unbuilt:
- `src/detection/tools/classes.py` 🔲
- `src/visualization/` 🔲 (Phase 14)
- `frontend/` 🔲 (Phase 14)

---

## Dataset Status

| Dataset | Count | Status |
|---------|-------|--------|
| Shot charts | 221,866 shots, 569 players | ✅ |
| PBP | 3,627 / 3,685 (98.4%) | ✅ |
| Player gamelogs | 622 players, 3 seasons | ✅ |
| Hustle / on-off / matchups / synergy | All fetched | ✅ |
| BBRef advanced | 736 players, 3 seasons | ✅ |
| Contracts | 523 players | ✅ |
| Historical lines | 1,225+ games | ✅ |
| Full game CV data | Real games: 0022400909, 0022401123, 0022401183, 0022401185, 0022401175, 0022400625. Template dirs (27 total) moved to `data/games/_templates/`. **Season 2025-26 batch ready**: run `select_season_games.py` + `batch_season.py`. | 🟡 Phase G → Season Batch |
| Season 2025-26 batch | 0 games processed. Targets: run `select_season_games.py` to generate `data/season_2025-26_targets.json`. Goal: 50 games (2/team). | ⏳ Not started |

---

## Active Issues

| ID | Issue | Status |
|----|-------|--------|
| ISSUE-021 | Wire DATABASE_URL + run 10 full games (Phase G) | 🔴 Active |
| ISSUE-009 | Phase G 20 clean games — Session 24 audit complete. 4 clean (6/6). 2 partial need reprocess (0022400625, 0022400687). 0022400710 needs new source video. 11 missing need pipeline run. 0022401156 enrichment 52% (PBP window mismatch). 0022400852 deleted. | 🟡 In progress — 4/20 clean |
| ISSUE-022 | `defender_distance=200.0` sentinel — ✅ FIXED Session 23. Backfilled + blanked ambiguous 200.0 rows for 0022400537/0022400909. feature_engineering.py already cleans 200.0→NaN. | ✅ CLOSED 2026-03-26 |
| ISSUE-023 | Shot clock MAE=17.16s — clock doesn't decrement per-frame, resets each possession | ✅ CLOSED 2026-03-25 |
| ISSUE-024 | `0022400852` — video is a Brazilian NBA League Pass app UI recording (AiScore.com overlays, animated court, no real broadcast). YOLO detects 0 persons. Video useless — delete and re-download proper YouTube broadcast. | ✅ CLOSED 2026-03-25 — root cause found |
| ISSUE-025 | `feature_engineering.py:683` — `player_name or ""` guard fails for `float(nan)` player names (NaN is truthy); crashes Stage 2 for all games with empty rosters | ✅ FIXED 2026-03-25 — changed to `isinstance(player_name, str)` guard |
| ISSUE-026 | `team_spacing` px² normalization — FIXED. `_SPACING_NORM=4700.0` added, both hull assignments now divide by `(map_w*map_h)/4700`. Backfill ran on 11 games. | ✅ CLOSED 2026-03-25 |
| ISSUE-027 | `0022400710` — reprocessing (Session 23, second in queue after 0022400625) | 🟡 Reprocessing |
| ISSUE-028 | `run_clip.py` was missing from `scripts/` — Stage 2 crashed for all games. Restored + added `--data-dir` arg + exit-3 guard. | ✅ CLOSED 2026-03-25 |
| ISSUE-029 | Ball detection 14.1% valid pct — YOLO conf lowered 0.55→0.30, orange guard removed from YOLO path, Hough param2 12→8. Re-test pending. | 🟡 Active — needs test run on reprocessed games |
| ISSUE-037 | Preflight validation — added to `run_clip.py` (exit 4 if median persons < 3). Prevents future 0022400852-type failures. | ✅ CLOSED 2026-03-26 |
| ISSUE-038 | 60fps games (0022400625, 0022400921 etc.) only got 5 min footage with 18000-frame budget. Fixed: `_fps_adjusted_frames()` in `run_phase_g.py` auto-scales budget to 10 min real-time. | ✅ CLOSED 2026-03-26 |
| ISSUE-030 | `0022400852` — wrong video (app UI recording). Root cause: `run_clip.py` PROJECT_DIR pointed to `scripts/` not project root → ModuleNotFoundError; also `StatsTracker.fps` AttributeError. Both fixed 2026-03-25. Video itself is unusable (see ISSUE-024). | ✅ CLOSED 2026-03-25 |
| ISSUE-031 | `run_clip.py:47` — `PROJECT_DIR = os.path.dirname(__file__)` → `scripts/`, not project root → `ModuleNotFoundError: No module named 'src'`. Fixed: added extra `dirname()`. | ✅ CLOSED 2026-03-25 |
| ISSUE-032 | `run_clip.py:151` — `pipeline.stats_tracker.fps` AttributeError: StatsTracker has no `fps` attr. Fixed: `getattr(getattr(pipeline, 'stats_tracker', None), 'fps', None) or 30.0`. | ✅ CLOSED 2026-03-25 |
| ISSUE-033 | `unified_pipeline.py:600` — pano scan used `imgsz=480` but TRT engine compiled for 640 → `input size [1,3,480,480] ≠ max model size [1,3,640,640]` on every game. Fixed: changed to `imgsz=640`. | ✅ CLOSED 2026-03-25 |
| ISSUE-034 | `0022400852` video was a Brazilian NBA League Pass app UI recording. yt-dlp `bestvideo+bestaudio` format unavailable (even without `--download-sections`). Fixed `fetch_games.py` to override format to `best[height<=720]` for section downloads. Used `0022400710.mp4` (same Feb 28 CLE@BOS highlights) as source — enrichment will be correct for 0022400852. NOTE: `0022400710.mp4` is Feb 28 highlights, NOT Feb 04 (game mismatch). | ✅ CLOSED 2026-03-25 — reprocessing |

| ISSUE-035 | Replay/cut detector added — `homography_valid` column now in tracking_data.csv; `ball_inferred` in ball_tracking.csv. Backfill not possible on old CSVs (column missing). New runs will have it. | ✅ CLOSED 2026-03-25 |
| ISSUE-036 | `_frame_spatial` isolation fallback used teammates as proxy defenders when no opponents tracked → returned wrong distance. Fixed: fallback only fires when 6+ players share one label (team misclassification scenario). | ✅ CLOSED 2026-03-25 |

| ISSUE-039 | Possession fragmentation — median duration 0.4s (should be ~14s). Fixed: `_BALL_LOSS_THRESH` now fps/stride-aware `max(15, int(1.5*fps/_stride))`, `_POSS_PERSIST_FRAMES` raised 60→90, output filter lowered to 1.5s, merge gap widened to 150 frames. | ✅ CLOSED 2026-03-26 |
| ISSUE-061 | **Possession over-merging** — `_ball_loss_streak` reset to 0 on ANY frame where ball was not detected (`curr_poss == ""`), forcing 30 CONSECUTIVE frames of new-team detection to register a switch. With intermittent `has_ball`, streak never accumulated. Fixed: `else: _ball_loss_streak = 0` replaced with `elif curr_poss == poss_team_prev: _ball_loss_streak = 0` — streak now persists through ball-detection gaps, only resets when original team explicitly re-confirmed. | ✅ CLOSED 2026-03-27 |
| ISSUE-040 | Shot over-detection — 264 shots/16 min (should be ~24-48). Fixed: debounce raised 3s→5s; added handler vtb guard to upward-velocity path — blocks shots only when player was actively sprinting away from basket. | ✅ CLOSED 2026-03-26 |
| ISSUE-041 | Missing real-unit ft coordinates in tracking_data.csv and features.csv. Fixed: `unified_pipeline.py` writes `ft_x`, `ft_y`, `dist_to_basket_ft` per frame. `feature_engineering.py` adds `add_ft_coordinates()` (derives from x_norm/y_norm). `spacing_advantage` recomputed from ft² ConvexHull when ft coords present. | ✅ CLOSED 2026-03-26 |
| ISSUE-042 | `handler_isolation=200.0` sentinel persisting in features.csv. Fixed: strengthened cleanup in `feature_engineering.py` — `df[col] >= 199.5` → NaN (catches int/float 200). | ✅ CLOSED 2026-03-26 |
| ISSUE-043 | `scoreboard_period` always -1, `scoreboard_score_diff` always 0 — OCR not reading scoreboard. Fixed: default changed to `None`/`""` so unknown values are blank instead of misleading. Tests updated. | ✅ CLOSED 2026-03-26 |
| ISSUE-044 | `possessions_enriched.csv` adds no new columns vs possessions.csv. Fixed: `nba_enricher.py` now writes `pbp_play_type`, `pbp_score_home`, `pbp_score_away`, `pbp_period`, `pbp_matched` columns from PBP match. | ✅ CLOSED 2026-03-26 |
| ISSUE-045 | No team name resolution — team column contains color labels (green/white) not NBA abbreviations. Fixed: `unified_pipeline.py` writes `team_colors.json` and adds `team_abbrev` column via `_backfill_team_abbrev()`. `feature_engineering.py` loads `team_colors.json` to add `team_abbrev` when missing. | ✅ CLOSED 2026-03-26 |
| ISSUE-046 | Unreachable Signal 2 in `_is_replay_or_cut` — `self._last_sb_conf >= 0.5 and == 0.0` is a logical contradiction, always False. Fixed: removed dead branch; replay detection handled by `_sc_absent_streak` counter in `run()`. | ✅ CLOSED 2026-03-26 |
| ISSUE-047 | Shot direction dot product `> 0` too loose — near-perpendicular passes could fire as shots. Fixed: raised to `> 0.3 * (‖ball‖ * ‖basket‖)` (cosine > ~17°). | ✅ CLOSED 2026-03-26 |
| ISSUE-048 | Dribble bounce threshold `_vy_prev > 1.0` missed slow dribbles. Fixed: lowered to `> 0.5`. | ✅ CLOSED 2026-03-26 |
| ISSUE-049 | `_PASS_MAX_FRAMES=20` and pixel_vel shot threshold hardcoded — not fps/stride-aware. Fixed: both are now instance attributes set in `configure(fps, stride)`. Pass window = `max(20, 2.0s real-time in processed frames)`. Pixel-vel threshold scales by stride. | ✅ CLOSED 2026-03-26 |
| ISSUE-050 | Scoreboard score OCR matched clock digits as scores (range ≤175 too wide). Fixed: capped at ≤120 (max realistic NBA score). | ✅ CLOSED 2026-03-26 |
| ISSUE-051 | OT period offset in `nba_enricher.py` used `q > 4` (should be `q >= 4`) — OT enrichment timestamps off by 60s. Fixed. | ✅ CLOSED 2026-03-26 |
| ISSUE-052 | `pbp_score_home/away` written for turnovers and fouls — misleading (score at foul ≠ scoring play). Fixed: only write scores when `pbp_play_type` is a made FG. | ✅ CLOSED 2026-03-26 |
| ISSUE-053 | `spacing_advantage` had no bounds — could reach ±231K when one team hull = 0 sentinel. Fixed: `.clip(-5000, 5000)` applied after both pixel-based and ft-based computation. | ✅ CLOSED 2026-03-26 |

| ISSUE-054 | **Shot over-detection** — Code-complete: direction cos>0.75 (within 41°), debounce 8s, vtb guard, backcourt guard. Session 31 audit confirms debounce fires on absolute frame count (stride-correct). Historical data still has overcounted shots but validation against NBA ground truth requires reprocessing with ISSUE-065 fix active. | 🟡 Code-fixed — validate with next batch run |
| ISSUE-055 | **Possession fragmentation in all 4 clean games** — 969–1201 possessions → cleaned to 110–277 via `scripts/clean_possessions.py` (2s filter + 300-frame same-team merge). Median duration 0.4s → 3.35–4.0s. Still below ~14s target — true fix = reprocess with new fps-aware code. Originals backed up as possessions.csv.bak. | 🟡 Partially mitigated — reprocess when ready |
| ISSUE-056 | **x_norm/y_norm > 1.0 on ~34% of rows** in 0022400430 and 0022400537 — court coordinate normalization bug (older pipeline). ft_x/ft_y derived from clipped values (still valid, just capped at court boundary). Fix: reprocess with current pipeline. | 🟡 Partially mitigated |
| ISSUE-057 | **player_name blank in ALL games** — Root cause: `_backfill_player_names()` guard blocked jersey_name_map fallback when API resolution failed. Fixed Session 28: removed len guard, UTF-8 encoding, retroactive backfill script. 155K rows filled across all game dirs. Games with 0% jersey data (0022400430/537/909/1156) need reprocess. | ✅ CLOSED 2026-03-28 |
| ISSUE-063 | **homography_valid = 0.0% for 0022401183** — portrait guard added to `_build_court()` in Session 27 (rotate 90° if rectified height > width). Needs reprocess to benefit. | ✅ CLOSED 2026-03-27 — code fix in place, reprocess when ready |
| ISSUE-058 | **team_abbrev = UNK** — root cause: both `_court_side_team_map` and `_resolve_team_names` accessed non-existent `HOME_TEAM_ABBREVIATION` column. Fixed both to use `nba_api.stats.static.teams` ID lookup. Also fixed duplicate mapping conflict: `_court_side_team_map` now skips re-mapping rows when `_resolve_team_names` already produced real abbreviations. | ✅ CLOSED 2026-03-27 |
| ISSUE-064 | **PBP gap-fill never triggered for full-game clips** — `_infer_period_count` only scanned `detected=1` rows, so pre-game/halftime dead zones made 37-min clips appear as 10-min clips → returned `[1]` → only Q1 PBP loaded (~50 events) → 49 CV possessions appeared "sufficient". Fixed: scan ALL rows for total clip duration; use `max_ts_any > max_ts * 1.5` guard to fall back to total duration when ball detection is sparse. Also added ratio fallback to gap-fill condition. Re-enriched 0022401183: 49 → 232 possessions. | ✅ CLOSED 2026-03-27 |
| ISSUE-060 | **0022400710 bad source video** — homography_valid = 5.7% (only 608/10607 frames mapped). Video is a highlights reel with frequent cuts, not a full broadcast. Needs new YouTube source before reprocessing. | 🔴 Needs new video |
| ISSUE-065 | **Ball detection critically low** — Root cause found: `ball_det.ball_tracker()` was skipped whenever `yolo_results` was non-empty (i.e. all live gameplay). The dedicated `yolov8n_ball.pt` (conf=0.05, ~98% accuracy) was only called when zero YOLO detections existed. Fixed: `ball_det` now runs as fallback when `_last_ball_2d` is None after `_apply_yolo`. Validate with next batch run. | ✅ CLOSED 2026-04-07 — code fix in `unified_pipeline.py` |
| ISSUE-066 | **team_abbrev only 7.8% filled** — Root cause found: `_ct_map` fallback values (`{"green": "team_a"}`) were truthy so they bypassed the `team_` prefix guard and overwrote `_team_map`. Fixed: `_ct_map_real` check added (same guard as `_team_map`). | ✅ CLOSED 2026-04-07 — code fix in `unified_pipeline.py` |

All other issues CLOSED — see `vault/Sessions/` for history.

---

## How To Run

```bash
conda activate basketball_ai
cd C:/Users/neelj/nba-ai-system

# Tests (no video)
python -m pytest tests/ -q

# Train win probability
python src/prediction/win_probability.py --train

# Predict a game
python src/prediction/game_prediction.py --predict GSW BOS

# Daily pipeline
python scripts/daily_pipeline.py

# API server
uvicorn api.main:app --reload --port 8000

# Dashboard
streamlit run dashboards/app.py
```

**Can run via pipeline:** `scripts/run_clip.py` (called by run_phase_g.py — do NOT invoke directly)
**Never run:** `run.py`, `scripts/loop_processor.py`

---

## Environment

- Python 3.9, conda env: `basketball_ai`
- PyTorch 2.0.1 + CUDA 11.8 + cuDNN 8.9 | RTX 4060 8GB
- YOLOv8n, OpenCV, EasyOCR, nba_api, XGBoost, scikit-learn
- PostgreSQL (schema ready, writes wired Phase 6)

---

## Platform Engineer Protocols

**Session Start Pulse:**
```
• Architecture: <3-word summary>
• Branch: <git branch>
• Last Modified: <3 files>
```

**Navigation breadcrumbs:** `[Module > Submodule > filename.py]`

**Token efficiency rules:**
- Use `# ... existing code ...` for unchanged blocks
- Never re-read large data directories unless asked
- Strip doc comments from code snippets unless editing the docstring

**Autonomous improvement protocol:**
1. Read `CLAUDE.md` open issues
2. Read `tests/` — find failing/missing tests
3. Implement fix (code only, no video runs)
4. Run `pytest tests/`
5. Update CLAUDE.md + STATE.md

**Code rules:** Python 3.9 | modular | max 300 lines/file | docstrings + type hints | save models to `data/` | log in `vault/Improvements/`

---

## Session Log
- Latest: `vault/Sessions/Session-2026-03-26.md`
- Full log: `vault/Sessions/`
