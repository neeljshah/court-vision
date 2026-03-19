# Data Schema — NBA AI Basketball System

This document describes every data point tracked or collected by the system, what it means, and how it is used in models and analytics.

---

## 1. CV Tracking Output — `tracking_data.csv`

The primary output of the computer vision pipeline. One row per player per frame. ~25,000 rows per game clip.

### Core Columns (36 total)

| Column | Type | Description | ML Use |
|--------|------|-------------|--------|
| `game_id` | str | NBA official game ID (e.g., "0022301234") | Join with NBA API data |
| `frame` | int | Frame index from video start | Time alignment |
| `timestamp` | float | Seconds from video start | Temporal features |
| `player_id` | int | Tracker slot ID (0-9 players, 10 = referee) | Identity linking |
| `team_id` | int | 0 = home team, 1 = away team, 2 = referee | Team separation |
| `x_position` | float | Court X coordinate (feet from left baseline) | Spatial features |
| `y_position` | float | Court Y coordinate (feet from halfcourt line) | Spatial features |
| `velocity` | float | Speed in court feet/frame | Fatigue model |
| `acceleration` | float | Change in velocity per frame | Play type feature |
| `ball_possession` | bool | Whether this player has the ball | Possession labeling |
| `event` | str | "shot" / "pass" / "dribble" / "none" | Event counting features |
| `jersey_number` | int | OCR-read jersey number (-1 if unknown) | Player identity |
| `player_name` | str | Resolved player name (via roster lookup) | Identity validation |
| `distance_to_ball` | float | Feet from player to ball | Defender context |
| `nearest_opponent` | float | Feet to nearest opposing player | Spacing metric |
| `nearest_teammate` | float | Feet to nearest same-team player | Spacing metric |
| `handler_isolation` | float | Distance from ball handler to nearest defender | Isolation score |
| `team_spacing` | float | Convex hull area of 5-man unit (sq feet) | Spacing model |
| `team_centroid_x` | float | Team center of mass X | Formation detection |
| `team_centroid_y` | float | Team center of mass Y | Formation detection |
| `paint_count_own` | int | Number of own team players in paint | Paint touches |
| `paint_count_opp` | int | Number of opponents in paint | Interior defense |
| `ball_x2d` | float | Ball X in court coordinates | Ball trajectory |
| `ball_y2d` | float | Ball Y in court coordinates | Ball trajectory |
| `distance_to_basket` | float | Ball distance to nearest basket (feet) | Shot zone |
| `vel_toward_basket` | float | Component of ball velocity toward basket | Shot detection |
| `ball_velocity` | float | Overall ball speed (feet/frame) | Pass/shot speed |
| `possession_type` | str | "transition" / "drive" / "paint" / "post-up" / "double-team" | Play type model |
| `play_type` | str | "isolation" / "P&R" / "spot-up" / "cut" / "hand-off" / "post-up" | Play type model |
| `possession_duration` | float | Seconds elapsed in current possession | Possession value |
| `game_clock` | float | Seconds remaining in period (from scoreboard OCR) | Game state |
| `shot_clock` | float | Shot clock reading in seconds (-1 if unavailable) | Shot pressure |
| `home_score` | int | Home team score (from scoreboard OCR) | Game state |
| `away_score` | int | Away team score (from scoreboard OCR) | Game state |
| `score_diff` | int | home_score - away_score | Clutch context |
| `possession_number` | int | Sequential possession counter for this clip | Possession tracking |

### Notes
- Referee rows: spatial columns (team_spacing, isolation, paint_count) are set to NaN — referees are filtered from analytics calculations
- `jersey_number = -1` when OCR confidence < threshold
- `player_name = "unknown_N"` when OCR has not resolved identity yet
- `shot_clock = -1` when scoreboard OCR cannot read shot clock (broadcast angle)

---

## 2. Shot Log — `shot_log.csv`

One row per detected shot event.

| Column | Type | Description | ML Use |
|--------|------|-------------|--------|
| `game_id` | str | NBA game ID | NBA API join |
| `frame` | int | Frame of shot detection | Time alignment |
| `timestamp` | float | Seconds from clip start | PBP matching |
| `player_id` | int | Shooter tracker ID | Player link |
| `player_name` | str | Shooter name | Display |
| `team_id` | int | Shooter's team | Team attribution |
| `x` | float | Shot origin X (court feet) | Zone classification |
| `y` | float | Shot origin Y (court feet) | Zone classification |
| `distance` | float | Feet from basket | Shot distance model |
| `zone` | str | "paint" / "mid_range" / "corner_3" / "above_break_3" | xFG zone feature |
| `defender_distance` | float | Feet from nearest defender at release | xFG input |
| `team_spacing` | float | Offensive spacing at shot moment | xFG input |
| `shot_clock_at_shot` | float | Shot clock reading | Pressure feature |
| `game_clock_at_shot` | float | Game clock at shot | Clutch feature |
| `score_diff_at_shot` | int | Score differential | Clutch feature |
| `made` | bool | Shot outcome (from NBA API enrichment; NULL if not enriched) | xFG label |
| `shot_type` | str | "2pt" / "3pt" (from NBA API) | Props model |
| `action_type` | str | "jump_shot" / "layup" / "dunk" etc (from NBA API) | Shot type model |

---

## 3. Possessions — `possessions.csv`

One row per possession. Aggregated from tracking_data.csv.

| Column | Type | Description | ML Use |
|--------|------|-------------|--------|
| `game_id` | str | NBA game ID | Join |
| `possession_id` | int | Sequential possession number | Simulator |
| `team_id` | int | Possessing team | Attribution |
| `possession_type` | str | transition / halfcourt / secondary_break | Play type model |
| `play_type` | str | isolation / P&R / spot-up / cut / post-up | Play type model |
| `duration_seconds` | float | Seconds elapsed | Pace model |
| `outcome` | str | "made_2" / "made_3" / "missed" / "turnover" / "foul" / "timeout" | Possession value |
| `avg_spacing` | float | Mean team spacing during possession | Spacing model |
| `max_pressure` | float | Peak defensive pressure score | Defense model |
| `handler_isolation` | float | Ball handler isolation score | Isolation model |
| `paint_touches` | int | Paint touch count during possession | Drive model |
| `drive_attempted` | bool | Whether a drive was detected | Drive model |
| `passes_count` | int | Number of passes | Ball movement |
| `dribbles_count` | int | Number of dribbles | Ball stagnation |
| `shot_clock_at_shot` | float | Shot clock at shot attempt | Pressure model |

---

## 4. Feature Engineering Output — `features.csv`

60+ computed features per player per game, ready for ML model input.

### Rolling Window Features (computed at 30, 90, and 150 frames)

| Feature | Description |
|---------|-------------|
| `velocity_mean_Xf` | Average player speed over X frames |
| `distance_Xf` | Total distance traveled over X frames |
| `acceleration_mean_Xf` | Mean acceleration magnitude |
| `shots_per_Xf` | Shot events in rolling window |
| `passes_per_Xf` | Pass events in rolling window |

### Spatial Features

| Feature | Description |
|---------|-------------|
| `team_spacing_mean` | Rolling mean of convex hull spacing |
| `isolation_score` | Handler distance to nearest defender |
| `paint_density_own` | Mean own-team paint count |
| `paint_density_opp` | Mean opponent paint count |
| `off_ball_distance_mean` | Mean distance of non-handlers to ball |

### Context Features (from NBA API)

| Feature | Description | Source |
|---------|-------------|--------|
| `pts_season_avg` | Season scoring average | `player_scraper.py` |
| `pts_last5_avg` | Last 5 games scoring average | Gamelog |
| `ts_pct` | True shooting percentage | Advanced stats |
| `usg_rate` | Usage rate (% team possessions used) | Advanced stats |
| `off_rtg` | Offensive rating | Advanced stats |
| `def_rtg` | Defensive rating | Advanced stats |
| `bpm` | Box plus/minus | BBRef |
| `vorp` | Value over replacement player | BBRef |
| `ws_per_48` | Win shares per 48 minutes | BBRef |
| `contract_year` | Binary flag — final year of contract | Contracts |
| `rest_days` | Days since last game | `schedule_context.py` |
| `back_to_back` | Binary — second game of B2B | `schedule_context.py` |
| `travel_miles` | Miles traveled since last game | `schedule_context.py` |
| `ref_fta_tendency` | Assigned referee's historical FTA rate | `ref_tracker.py` |
| `ref_pace_tendency` | Assigned referee's historical pace | `ref_tracker.py` |
| `on_court_net_rtg` | Player's on-court net rating | On/off splits |
| `hustle_deflections` | Season deflections per game | Hustle stats |
| `hustle_screen_assists` | Screen assists per game | Hustle stats |
| `synergy_pts_per_poss` | Offensive efficiency by play type | Synergy |
| `defender_zone_fg_allowed` | Opponent FG% allowed by zone | Defender zones |
| `matchup_fg_allowed` | FG% allowed vs. specific matchup | Matchup data |

---

## 5. NBA API Cache — `data/nba/`

All NBA Stats API responses, cached to disk with smart TTL.

| File Pattern | Contents | Records |
|-------------|----------|---------|
| `gamelogs_2024-25.json` | Per-game box scores for all active players | 622 players |
| `advanced_stats_2024-25.json` | Advanced stats (BPM, eFG%, TS%, USG%, PACE) | 569 players |
| `shot_charts_2024-25.json` | Per-shot location, zone, distance, made/missed | 221,866 shots |
| `hustle_stats_2024-25.json` | Deflections, screens, charges drawn, loose balls | 567 players |
| `on_off_2024-25.json` | On-court vs. off-court net rating splits | 569 players |
| `defender_zone_2024-25.json` | FG% allowed by court zone | 566 players |
| `matchups_2024-25.json` | Who guards whom + pts/poss allowed | 2,269 records |
| `synergy_offense_2024-25.json` | Offensive pts/poss by play type | 300 players |
| `synergy_defense_2024-25.json` | Defensive pts/poss allowed by play type | 300 players |
| `shot_zone_tendency.json` | Player zone preferences (42-dim feature per player) | 566 players |
| `clutch_scores_2024-25.json` | Clutch efficiency composite score | 228-255 players |
| `schedule_*.json` | Full season schedule with home/away/date | 3 seasons |
| `lineups.json` | 5-man unit data (on/off per lineup) | All lineups |

---

## 6. External Data Cache — `data/external/`

| File Pattern | Contents | Records |
|-------------|----------|---------|
| `bbref_advanced_2024-25.json` | BPM, VORP, WS, WS/48 (Basketball Reference) | 736 players |
| `historical_lines_2024-25.json` | Opening + closing spread + total | 1,225 games |
| `contracts_2024-25.json` | Salary, years remaining, contract year flag | 523 players |

---

## 7. Trained Model Artifacts — `data/models/`

| File | Model | Key Metric |
|------|-------|------------|
| `win_probability.pkl` | Pre-game win probability (XGBoost) | 67.7% acc, Brier 0.204 |
| `props_pts.json` | Points prop model | MAE 0.32, R² 0.92 |
| `props_reb.json` | Rebounds prop model | MAE 0.11, R² 0.94 |
| `props_ast.json` | Assists prop model | MAE 0.09, R² 0.93 |
| `props_fg3m.json` | 3-pointers made prop model | Trained |
| `props_stl.json` | Steals prop model | Trained |
| `props_blk.json` | Blocks prop model | Trained |
| `props_tov.json` | Turnovers prop model | Trained |
| `game_total.json` | Game total (over/under) model | Trained |
| `game_spread.json` | Game spread model | Trained |
| `game_blowout.json` | Blowout probability model | Trained |
| `game_first_half.json` | First half total model | Trained |
| `game_pace.json` | Game pace model | Trained |
| `xfg_v1.pkl` | Expected field goal (xFG v1) | Brier 0.226 |
| `matchup_model.json` | Matchup scoring differential (M22) | R² 0.796, MAE 4.55 |

---

## 8. Game Video Data — `data/games/`

Each subdirectory contains one game's assets:

```
data/games/gsw_lakers_2025/
├── clip.mp4                  # Original broadcast video
├── tracking_data.csv         # Per-frame tracking output
├── shot_log.csv              # Detected shots
├── possessions.csv           # Possession aggregates
├── features.csv              # ML-ready feature matrix
└── benchmark_results.json    # Quality metrics from last run
```

Game clips currently available (17 clips, all short <2 min):
- `atl_ind_2025/`, `bos_mia_2025/`, `cavs_gsw_2016_finals_g7/`
- `den_gsw_playoffs/`, `gsw_lakers_2025/` + 12 more

---

## 9. PostgreSQL Schema — `database/schema.sql`

Nine tables designed for production-scale storage of all system outputs.

```sql
-- Key table relationships
teams (team_id PK)
    ← players (team_id FK)
    ← games (home_team_id, away_team_id FK)

games (game_id PK)
    ← tracking_frames (game_id FK)
    ← possessions (game_id FK)
    ← shots (game_id FK)
    ← game_lineups (game_id FK)
    ← model_predictions (game_id FK)

players (player_id PK)
    ← tracking_frames (player_id FK)
    ← shots (player_id FK)
    ← player_identity_map (player_id FK)
```

**Indexes:** `game_date`, `team_id`, `player_id`, `season` — optimized for dashboard queries, lineup lookups, and model backtests.

---

## 10. Live Data Feeds

Updated continuously during the season:

| Feed | File | Frequency | Contents |
|------|------|-----------|----------|
| Injuries (NBA official) | in-memory + cache | 6h | Player injury status, expected return |
| Injuries (Rotowire) | in-memory + cache | 30min | Injury/lineup news feed |
| Prop lines (DK/FD) | in-memory + cache | 15min | Current player prop O/U + juice |
| Betting lines (opening/current) | in-memory + cache | 1h | Spread + total opening vs. current |
| Referee assignments | in-memory + cache | 24h | Tonight's ref crew + historical tendencies |

---

## Key Data Quality Notes

1. **Shot enrichment gap**: 0 of 17 tracked shots have been enriched with NBA PBP outcomes yet — requires running `run_clip.py --game-id [id]` on a real game clip. Planned for Phase 6.

2. **Identity resolution**: Jersey OCR resolves ~70% of players per clip in good lighting. Unknown players are tracked with anonymous IDs (`unknown_N`) and linked to rosters manually in `data/player_identity_map.json`.

3. **Court coordinate accuracy**: Current SIFT homography gives ±12-15 inches spatial accuracy. Phase 2.5 pose estimation (ankle keypoints) will improve this to ±6-8 inches.

4. **PBP coverage**: 3,627/3,685 games (98.4%) have play-by-play data. Remaining 58 are preseason games.

5. **Shot chart coverage**: 221,866 shots from 569 players across 3 seasons. Each shot has: zone, distance, shot type, action type, and made/missed label — ready for xFG v1 training.
