# Data Schema — NBA AI Basketball System

This document describes every data point tracked or collected by the system, what it means, and how it is used in models and analytics.

---

## 1. CV Tracking Output — `tracking_data.csv`

The primary output of the computer vision pipeline. One row per player per frame. ~25,000 rows per game clip.

### Core Columns

The live CSV header has 54 columns (verified via header read); the 36 below are
the ones consumed downstream by feature engineering and models. The remaining
~18 (`bbox_x1/y1/x2/y2`, `ankle_x/y`, `confidence`, `scoreboard_*` raw fields,
`contest_arm_angle`, `jump_detected`, `dribble_hand`, `ball_shot_arc_angle`,
`ball_peak_height_px`, `ball_pass_speed_pxpf`, `direction_deg`, `drive_flag`,
`fast_break_flag`, `possession_side`, `shot_clock_est`) are intermediate /
detector-internal columns not yet promoted to a documented feature.

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

One row per detected shot event. Actual header (verified, 15 columns):

| Column | Type | Description | ML Use |
|--------|------|-------------|--------|
| `game_id` | str | NBA game ID | NBA API join |
| `shot_id` | int | Sequential shot counter for this clip | Row identity |
| `frame` | int | Frame of shot detection | Time alignment |
| `timestamp` | float | Seconds from clip start | PBP matching |
| `player_id` | int | Shooter tracker slot ID | Player link |
| `nba_player_id` | int | Resolved NBA.com player ID (once identity is linked) | NBA API join |
| `team` | str | Shooter's team | Team attribution |
| `x_position` | float | Shot origin X (court feet) | Zone classification |
| `y_position` | float | Shot origin Y (court feet) | Zone classification |
| `court_zone` | str | "paint" / "mid_range" / "corner_3" / "above_break_3" | xFG zone feature |
| `defender_distance` | float | Feet from nearest defender at release | xFG input |
| `team_spacing` | float | Offensive spacing at shot moment | xFG input |
| `possession_id` | int | Possession this shot belongs to | Join to `possessions.csv` |
| `possession_duration` | float | Seconds elapsed in possession before shot | Pressure feature |
| `made` | bool | Shot outcome (from NBA API enrichment; NULL if not enriched) | xFG label |

Note: `game_clock`/`score_diff` at shot time and NBA-API `shot_type`/`action_type`
are not columns in this CSV -- they must be joined in from the NBA API PBP cache
(`data/nba/pbp_<game_id>_p*.json`) by frame/timestamp if needed for a clutch or
shot-type feature.

---

## 3. Possessions — `possessions.csv`

One row per possession. Aggregated from tracking_data.csv. Actual header
(verified, 16 columns):

| Column | Type | Description | ML Use |
|--------|------|-------------|--------|
| `game_id` | str | NBA game ID | Join |
| `possession_id` | int | Sequential possession number | Simulator |
| `team` | str | Possessing team | Attribution |
| `start_frame` | int | First frame of possession | Time alignment |
| `end_frame` | int | Last frame of possession | Time alignment |
| `duration_frames` | int | Frame count of possession | Pace model |
| `duration_sec` | float | Seconds elapsed | Pace model |
| `avg_spacing` | float | Mean team spacing during possession | Spacing model |
| `avg_defensive_pressure` | float | Mean defensive pressure score | Defense model |
| `avg_vel_toward_basket` | float | Mean ball velocity toward basket | Drive model |
| `drive_attempts` | int | Drive attempts detected during possession | Drive model |
| `shot_attempted` | bool | Whether a shot was attempted | Possession value |
| `shot_frame` | int | Frame of the shot attempt (-1 if none) | Time alignment |
| `fast_break` | bool | Whether this was a fast-break possession | Play type model |
| `result` | str | "made_2" / "made_3" / "missed" / "turnover" / "foul" / "timeout" | Possession value |
| `outcome_score` | float | Points scored on this possession | Possession value |

Note: `max_pressure`, `handler_isolation`, `paint_touches`, `passes_count`,
`dribbles_count`, and `shot_clock_at_shot` are not columns in this CSV -- those
per-possession aggregates are not currently computed here (some exist per-frame
in `tracking_data.csv` instead).

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

Player gamelogs are NOT one aggregated file -- they are cached one file per
player: `gamelog_<player_id>_2024-25.json` (verified: 4,386+ individual files
on disk). Likewise, per-game shot charts are cached per game
(`shot_chart_<game_id>.json`), not as one season-wide aggregate; there is no
`advanced_stats_2024-25.json` aggregate file on disk today.

| File Pattern | Contents | Records |
|-------------|----------|---------|
| `gamelog_<player_id>_2024-25.json` | Per-game box score log for one player | one file per player (4,386+ files) |
| `shot_chart_<game_id>.json` | Per-shot location, zone, distance, made/missed for one game | one file per game |
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
| `win_probability.pkl` | Pre-game win probability (5-way NNLS stack) | 0.7094 acc / 0.193 Brier (WF); 0.717 / 0.188 (single-split) |
| `props_pts.json` | Points prop model (sqrt+Huber blend) | MAE 4.83 (WF, re-measured 2026-07-20) |
| `props_reb.json` | Rebounds prop model (LGB-q50) | MAE 1.92 (WF, re-measured 2026-07-20) |
| `props_ast.json` | Assists prop model (multitask MLP) | MAE 1.39 (WF, re-measured 2026-07-20) |
| `props_fg3m.json` | 3-pointers made prop model (XGB-q50) | MAE 0.89 (walk-forward) |
| `props_stl.json` | Steals prop model (XGB-q50) | MAE 0.72 (walk-forward) |
| `props_blk.json` | Blocks prop model (XGB-q50) | MAE 0.44 (walk-forward, -16% session win) |
| `props_tov.json` | Turnovers prop model (XGB-q50) | MAE 0.89 (walk-forward) |
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

Game clips currently available (24 game directories, excluding `_templates`):
- `atl_ind_2025/`, `bos_mia_2025/`, `cavs_gsw_2016_finals_g7/`
- `den_gsw_playoffs/`, `gsw_lakers_2025/` + 19 more

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

## 9b. Multi-Sport Platform Corpora -- `data/domains/<sport>/`

The sport-blind platform stores one parquet per corpus stem named in
`domains/<sport>/ingest_manifest.py`. Each source carries a `leak_class` (when it
becomes known relative to the event) and an `sla_minutes` freshness target. These
are the provenance contract -- a builder asserts a feature only ever reads a
`pre_game` / `reference` source.

### Leak classes (the as-of contract)

| leak_class | Meaning | May feed a pregame feature? |
|---|---|---|
| `pre_game` | known before tip/first-pitch/kickoff | yes |
| `reference` | slowly-updated static (e.g. park factor, player registry) | yes |
| `in_game` | revealed during play (e.g. per-quarter linescores) | in-game conditioning only |
| `post_game` | only known after the event (final box, settlement) | NO -- training labels only |

`asof_*` corpora are derived from `post_game` raw box but are themselves
`pre_game` **by construction** (snapshot-before-update; see
`scripts/platformkit/asof_common.py`). The label columns (`home_win`,
`target_home_win`, `target_over25`, `winner`) are `post_game` labels, never
features.

### Per-sport corpus stems (file = `data/domains/<sport>/<stem>.parquet`)

| Sport | pre_game / reference stems | post_game / in_game stems |
|---|---|---|
| `basketball_nba` | games, odds, asof_features, asof_box_extra, asof_runvar | linescores (in_game), player_boxscores, espn_boxscores, postmortem |
| `mlb` | games, games_current, odds, pitchers, asof_features, asof_park (ref) | player_gamelogs, espn_boxscores, postmortem |
| `soccer` | matches, odds, asof_features, asof_xg_proxy, espn_club_priors (ref) | match_stats, espn_matchstats, espn_player_stats, postmortem |
| `tennis` | matches, wta_matches, odds, asof_features, asof_hold, asof_return, players (ref) | match_stats, postmortem |

### Normalized team-odds event -- `OddsEvent` (`odds_provider/base.py`)

| Field | Type | Description |
|---|---|---|
| `event_id` | str | venue-native id (ESPN event id / Kalshi `event_ticker` / Polymarket id) -- NOT the NBA `game_id` |
| `sport` | str | sport key (nba / mlb / soccer / soccer_intl / tennis) |
| `home`, `away` | str | team / player display names |
| `commence_time` | str | ISO start (or venue close_time) -- the key for true-close certification |
| `prices` | dict | `{venue: {home, away, [spread], [total]}}`; decimal odds > 1.0 |
| `source` | str | provider name (espn / kalshi / polymarket) |
| `as_of` | str | ISO-8601 UTC capture timestamp |

### Normalized player prop -- `PropLine` (`odds_provider/prop_base.py`)

| Field | Type | Description |
|---|---|---|
| `sport`, `event_id`, `match` | str | sport key, venue event id, match label |
| `player`, `team` | str | player name, team (nullable) |
| `stat` | str | canonical stat (via `canon_stat()`; unknown labels pass through) |
| `line` | float | over/under line value |
| `over_price`, `under_price` | float | DECIMAL odds (> 1.0) -- both `None` for DFS pick'em |
| `payout_type` | str | `"sportsbook"` (true two-sided) or `"dfs_pickem"` (flat multiple) |
| `source`, `as_of` | str | provider name, ISO-8601 UTC capture timestamp |

### Price-history tick schemas -- `data/cache/`

**Pregame line tick** (`line_history/<sport>/<date>.jsonl`, via
`snapshot.write_quotes`): the captured `MarketQuote` rows carry `game_id`,
`market_type`, `side`, `odds` (decimal), `devigged_prob` (Shin no-vig fair prob),
`captured_at` (ISO UTC), `commence_time`, and an `is_true_close` flag set when the
tick landed inside the 30-min lock window before tip.

**In-play tick** (`inplay_history/<sport>/<date>.jsonl`, canonical flat YES-prob):

| Field | Type | Description |
|---|---|---|
| `sport` | str | sport key |
| `game_id` | str | venue-native game id |
| `venue` | str | kalshi / polymarket / espn |
| `market_type` | str | "moneyline" (default) etc. |
| `side` | str | which team/outcome the YES prob is for |
| `ticker` | str | venue contract ticker |
| `prob` | float | implied probability in `[0, 1]` (out-of-range -> skipped) |
| `ts` | str | ISO-8601 UTC capture timestamp |
| `phase` | str | always `"in_play"` |

A `_freshness.json` sidecar per sport carries `{last_capture_ts, last_n_ticks}`,
advanced only on a successful poll.

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

1. **Shot enrichment gap**: shots across the 24 game directories in `data/games/` have not been enriched with NBA PBP outcomes yet -- requires running `run_clip.py --game-id [id]` on a real game clip. Planned for Phase 6.

2. **Identity resolution**: Jersey OCR resolves ~70% of players per clip in good lighting. Unknown players are tracked with anonymous IDs (`unknown_N`) and linked to rosters manually in `data/player_identity_map.json`.

3. **Court coordinate accuracy**: Current SIFT homography gives +/-12-15 inches spatial accuracy. Phase 2.5 pose estimation (ankle keypoints) will improve this to +/-6-8 inches.

4. **PBP coverage**: 3,627/3,685 games (98.4%) have play-by-play data. Remaining 58 are preseason games.

5. **Shot chart coverage**: 221,866 shots from 569 players across 3 seasons. Each shot has: zone, distance, shot type, action type, and made/missed label -- ready for xFG v1 training.

6. **ID crosswalk is not assumed**: ESPN `event_id` != NBA-stats `game_id`; MLB `game_pk` != book `event_id`; ESPN `event_id` != Kalshi/Polymarket ids. Cross-feed joins are done by team-name + commence-time resolution and their coverage must be verified; in-play liveness is decided venue-natively, never via an ESPN id cross-join. Unmatched rows are omitted, never force-joined.

7. **Prices are captured, never fabricated**: a missing line or odds field yields an omitted node / skipped row (never a guessed number). All capture is PAPER / measurement only; no $-edge is claimed. `data/` is local-only and gitignored.

See also: [DATA.md](DATA.md) - [DATA_OUTPUTS.md](DATA_OUTPUTS.md) - [operations/data-pipeline.md](operations/data-pipeline.md) - [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) - [INDEX.md](INDEX.md)


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
