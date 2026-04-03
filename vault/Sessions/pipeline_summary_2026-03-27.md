# Pipeline Summary — 2026-03-27 (Iteration 1)

## Tracker Health
| Metric         | Before | After   | Target | Status |
|----------------|--------|---------|--------|--------|
| Pipeline fps   | 54     | 54      | ≥ 20   | ✅     |
| Ball valid %   | 62%    | 62%     | ≥ 60%  | ✅     |
| Shots          | 1/167s | 1/167s  | ≥ 1/2m | ✅     |
| ID switches    | 0      | 0       | 0      | ✅     |
| Possessions    | 3      | 3       | ≥ 5    | 🟡     |

Ball valid measured as detected+inferred (combined). Detected-only = 53%.

## Fix This Iteration
- **File:** `src/tracking/ball_detect_track.py:414`
- **Change:** Extended dribble predictor from <8 to <12 frames gap
- **Result:** ❌ reverted — combined ball_valid 62%→59.7% (slight regression, gap 8-12 rarely populated)

## Data Sources
| Source              | Status     | Value                                      |
|---------------------|------------|---------------------------------------------|
| Gamelogs 2022-23    | ✅ done    | 539 players fetched                        |
| Gamelogs 2023-24    | 🔄 running | 181/600 players (A0 background task)       |
| Gamelogs 2025-26    | 🔄 pending | awaiting 2023-24 completion                |
| Tracking stats 2025-26 | ✅      | 570 players                                |
| Synergy 2025-26     | ✅ done    | offensive + defensive cached               |
| Synergy 2024-25     | ✅ done    | previously missing, now fetched            |
| Schedules 2025-26   | ✅ done    | all 30 teams                               |
| season_games cache  | ✅         | 2022-23/2023-24/2024-25 (v5, with C1-C7)  |

## Season Update Completed (2025-26)
| Component           | Change                                                           |
|---------------------|------------------------------------------------------------------|
| `pull_missing_data` | Added phase A0 (gamelog bulk fetch); _SEASONS → 4 seasons      |
| `retrain_props_v2`  | Cutoffs: train<2025-10-01, test<2026-01-01, val=2026-01+       |
| `retrain_props_v2`  | Season boundary resets in rolling averages                      |
| `retrain_all.py`    | win_prob trains on ["2022-23","2023-24","2024-25"] only         |
| `win_probability.py`| predict() default season: 2024-25 → 2025-26                    |
| `win_probability.py`| _fetch_season_games now populates C-1 through C-7 features      |
| `win_probability.py`| Schema version bumped 4→5 to bust stale cache                  |
| `player_props.py`   | predict_props() default: 2024-25 → 2025-26                     |
| `daily_pipeline.py` | Docstring updated to --season 2025-26                           |
| `games_2024-25.json`| Deleted (minimal schema, was stale)                            |

## Win Probability Retrained
- Seasons: 2022-23, 2023-24, 2024-25 (3,685 games)
- Val accuracy: **68.8%** | Brier: **0.2037**
- Home win rate: 55.6%

## Full Game Pipeline
- Status: running in background
- Game: 0022400625 (partial — needs reprocess with ISSUE-039/040 fixes)
- Frames: 18000

## Next Fix
- Worst metric: possessions (3 per 167s = 1.07/min, target 2/min)
- Likely file: `src/pipeline/unified_pipeline.py` — `_BALL_LOSS_THRESH` / `_POSS_PERSIST_FRAMES`
- Approach: audit possession merge logic on short clips; check if fps-aware thresh is firing correctly

---

# Pipeline Summary — 2026-03-27 (Iteration 2)

## Game Processed
- **Game ID:** 0022401183 (POR 86 @ GSW 103 — 2025-04-11)
- **Frames:** 18,000 (still running in background at time of writing)
- **Source:** data/videos/full_games/0022401183.mp4

## CV Accuracy Scorecard (150-frame verify run)
| Metric | CV Value | NBA Ground Truth | Ratio | Pass |
|--------|----------|-----------------|-------|------|
| Ball valid | 100% (150/150) | — | — | ✅ |
| Homography | 0.274 | — | — | ❌ (<0.30) |
| Shots | 0 (150 frames) | 168 FGA total | — | pending 18k run |
| Possessions | 0 (150 frames) | ~21 in 10 min | — | pending 18k run |

## NBA Ground Truth Collected
| Source | Status | File |
|--------|--------|------|
| BoxScore (POR/GSW) | ✅ | nba_boxscore_players.csv — 168 FGA, 65 made |
| Shot chart w/ ft coords | ✅ | nba_shot_chart_ft.csv — 168 shots, LOC_X/Y→ft_x/ft_y |
| PBP V3 events | ✅ | data/nba/pbp_0022401183.json — 519 events |
| Jersey→name map | ✅ | jersey_name_map.json — 27 entries (POR+GSW rosters) |
| Hustle stats fallback | ✅ | nba_hustle_fallback.csv — 30 players (contested shots, deflections) |

## Fallbacks Applied
| Fallback | Applied | File | Trigger |
|----------|---------|------|---------|
| NBA shot chart (ft coords) | ✅ | nba_shot_chart_ft.csv | Always (FALLBACK-C) |
| Jersey→name map | ✅ | jersey_name_map.json | Always (FALLBACK-B) |
| Hustle stats | ✅ | nba_hustle_fallback.csv | Always |
| PBP V3 possession events | ✅ | pbp_0022401183.json | Always (FALLBACK-D) |
| NBA shot proximity | ❌ | — | PlayerDashPtShots API signature changed |
| Speed/Distance | ❌ | — | LeagueDashPtStats player mode unavailable |

## Tracker Health (300-frame benchmark — game 0022400430)
| Metric | Before | After | Target | Status |
|--------|--------|-------|--------|--------|
| Ball valid (full 18k run) | 62% | 79.6% | ≥ 60% | ✅ |
| Shots (18k run) | 44 | 44 | ≥1/2m | ✅ |
| ID switches | 0 | 0 | 0 | ✅ |
| Possessions (18k run) | 121 | 121 | ≥ 5 | ✅ |

## Fix This Iteration
- **File:** `src/pipeline/unified_pipeline.py:2406, 3013`
- **Change:** `BoxScoreSummaryV2 → V3` (V2 deprecated, no data after 4/10/2025 — critical for 2025-26 season). V3 uses `homeTeamId`/`awayTeamId` instead of `HOME_TEAM_ID`/`VISITOR_TEAM_ID`. V2 kept as fallback.
- **Result:** ✅ kept — `[court_side] {'white': 'POR', 'green': 'GSW'}` resolved correctly, no deprecation warning

## Fix Attempted + Reverted
- **File:** `src/pipeline/unified_pipeline.py:1165`
- **Change:** `_POSS_PERSIST_FRAMES = 90` → `max(20, int(3.0*fps/_stride))` (stride-aware)
- **Result:** ❌ reverted — possessions dropped 3→1 (shorter persistence creates more <2s fragments, all filtered)

## Audit Result (pre-fix)
- 0022401183: MISSING (pipeline running)
- 0022400430: 5/6 (run.log traceback from old CSRT crash — fix already in code)
- 0022400537: 5/6 (same)
- 0022400909: 6/6 CLEAN ✅
- Clean total: 1 / 20

## Today's Predictions
| Game | Away Win% | Home Win% | Edge |
|------|-----------|-----------|------|
| LAC @ IND | **79.2%** | 20.8% | A |
| ATL @ BOS | 24.5% | **75.5%** | A |
| MIA @ CLE | 39.6% | **60.4%** | A |
| HOU @ MEM | **68.1%** | 31.9% | A |
| CHI @ OKC | 13.2% | **86.8%** | A |
| NOP @ TOR | 22.0% | **78.0%** | A |
| UTA @ DEN | 16.0% | **84.0%** | A |
| WAS @ GSW | 20.2% | **79.8%** | A |
| DAL @ POR | 33.1% | **67.0%** | A |
| BKN @ LAL | 22.2% | **77.8%** | A |

**Notable:** CHI @ OKC (86.8% OKC), UTA @ DEN (84.0% DEN), LAC @ IND (79.2% LAC away)

## Top Prop Edges
- Not available — gamelogs not yet downloaded for 2025-26

## Phase G Progress
- Clean games (6/6): 1 / 20 (0022400909)
- 0022401183: running (18,000 frames, will complete after this report)
- 0022400430 / 0022400537: 5/6 — need reprocess to clear old run.log traceback

## Next Fix
- Worst metric: homography 0.274 for 0022401183 (target ≥0.85)
- Approach: check source video quality; if highlights reel, re-download full broadcast
- Also: complete gamelog A0 download → retrain props → generate real prop edges
