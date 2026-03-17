# Requirements: NBA AI System

## Data Maximization Principle
Every phase must extract the maximum possible data from available sources. NBA API data (no video needed) should be scraped exhaustively before building models. CV tracking data enhances models but does not gate them.

---

## Phase 1 Requirements — Data Infrastructure ✅ COMPLETE

- REQ-01: PostgreSQL schema with tables: games, players, teams, tracking_frames, possessions, shots, lineups, odds, predictions
- REQ-02: schedule_context.py returns rest days, back-to-back flag, travel distance (miles)
- REQ-03: nba_stats.py fetches opponent defensive rating, pace, eFG% allowed

---

## Phase 2 Requirements — Critical Tracker Bug Fixes

- [x] REQ-02A: Team color classification separates players into two distinct teams (team_a / team_b) — NOT all-green. Both teams present in team column of every game output. ✅ Fixed by 02-06
- REQ-02B: EventDetector fires shot events — at least 1 shot detected per minute of broadcast footage
- REQ-02C: EventDetector fires dribble events — ball_pos and possessor_pos not None in 2D mode (ISSUE-011)
- REQ-02D: Pass events fire correctly on ball possession transfer between players
- REQ-02E: Clip duration validator rejects clips under 60 seconds as insufficient for analytics
- REQ-02F: All 17 existing clips re-processed through fixed tracker; output validated (non-zero shots, both teams present)

---

## Phase 3 Requirements — NBA API Data Maximization (No Video Needed)

### 3A: Advanced Player Stats — All Active Players
- REQ-03A-1: Advanced stats scraped for all 569 players: usg_pct, ts_pct, off_rtg, def_rtg, net_rtg, pie, ast_pct, reb_pct, efg_pct (currently 0/569)
- REQ-03A-2: Scoring stats scraped: pct_pts_paint, pct_pts_mid_range, pct_pts_3pt, pct_pts_ft, pct_pts_2pt
- REQ-03A-3: Misc stats scraped: pts_off_tov, pts_paint, pts_fb, pts_2nd_chance, blk_pct, stl_pct
- REQ-03A-4: Defense stats: matchup data, contested shots, deflections (where available)
- REQ-03A-5: All tiers written to player_full_{season}.json with coverage score = 1.0

### 3B: Player Gamelogs — All Active Players
- REQ-03B-1: Gamelogs scraped for ALL active players (not just LeBron/Curry/Jokic) — 24 stats per game × full season
- REQ-03B-2: Gamelogs for 3 prior seasons (2022-23, 2023-24, 2024-25) per player
- REQ-03B-3: Last-5, last-10, last-15, last-20 game splits computed and stored per player
- REQ-03B-4: Home/away splits per player per season
- REQ-03B-5: Per-game plus_minus stored (used for lineup correlation)

### 3C: Shot Charts — NBA API ShotChartDetail
- REQ-03C-1: Shot chart scraped for every active player — 3 seasons minimum
- REQ-03C-2: Each shot record contains: court_x, court_y, shot_distance, shot_zone_basic, shot_zone_area, made/missed, shot_type (2pt/3pt/layup/dunk/floater/midrange/3pt), quarter, game_clock, score_margin, game_id
- REQ-03C-3: Minimum 50,000 total shot records across all players/seasons
- REQ-03C-4: Shot chart data stored per-player per-season in data/nba/shotcharts/
- REQ-03C-5: Aggregated shot chart lookup: get_player_shot_zones(player_id) → zone makes/attempts/pct

### 3D: Play-by-Play — All Season Games
- REQ-03D-1: Play-by-play scraped for all 1,225+ games in season_games_2024-25.json
- REQ-03D-2: Each PBP record: event_type, player1, player2, team, period, game_clock, score, score_margin, home_score, away_score
- REQ-03D-3: PBP for prior 2 seasons (2022-23, 2023-24) also scraped (used for sequence models)
- REQ-03D-4: PBP stored in data/nba/pbp/{game_id}.json; indexed in data/nba/pbp_index.json

### 3E: Lineup Data — All 30 Teams
- REQ-03E-1: 5-man lineup combinations and their on/off splits for all 30 teams, current season
- REQ-03E-2: Per-lineup: net_rtg, off_rtg, def_rtg, pace, minutes, plus_minus
- REQ-03E-3: Two-man combination stats (pick-roll partners, defensive pairs)
- REQ-03E-4: Prior 2 seasons for continuity/chemistry tracking

### 3F: Referee Data
- REQ-03F-1: Daily referee assignments scraped (NBA official schedule)
- REQ-03F-2: Historical ref tendencies per referee: avg_foul_rate, avg_pace_impact, home_win_pct, techs_per_game
- REQ-03F-3: Referee features injected into win probability model

### 3G: Injury History
- REQ-03G-1: Current injury report scraping (already exists in injury_monitor.py)
- REQ-03G-2: Historical injury log per player: injury_type, games_missed, return_performance (first 5 game stats after return)
- REQ-03G-3: Injury impact features: days_out, injury_type severity score, return game flag

---

## Phase 4 Requirements — First ML Models (Full Data)

- REQ-04-1: Win probability model trained (XGBoost, 26 features, 3 seasons), Brier score < 0.22 — model currently exists, just needs training run
- REQ-04-2: Player prop models (points, rebounds, assists) using full gamelogs + advanced stats for all 569 players, RMSE < 15% of league average
- REQ-04-3: Shot quality model trained on NBA API shot chart data (50,000+ shots) — AUC > 0.65. Features: shot_distance, shot_zone, shot_type, game_clock, score_margin, quarter. No CV data required.
- REQ-04-4: Lineup efficiency model — predict lineup net_rtg from player advanced stats combinations. Trained on all 30 teams × 3 seasons of lineup splits.
- REQ-04-5: Backtesting framework: CLV, Brier score, ROI at 3 edge thresholds, SHAP feature importance
- REQ-04-6: All models save to data/models/ as .pkl; model cards saved as data/model_reports/

---

## Phase 5 Requirements — External Factors Scraper

- REQ-05-1: injury_monitor.py polls NBA official + Rotowire every 30 min; status stored in DB
- REQ-05-2: ref_tracker.py scrapes daily referee assignments; historical pace/foul features available at prediction time
- REQ-05-3: line_monitor.py polls The Odds API for opening vs closing line; sharp money signal derived from CLV
- REQ-05-4: news_scraper.py scrapes ESPN headlines; keyword flags: load_management, questionable, illness
- REQ-05-5: All external features injected into win_probability and player_props models as new feature columns

---

## Phase 6 Requirements — Full Game Video Processing

*Note: Must be run on a GPU-capable machine, not the dev machine (CRITICAL: never run video processing on local machine)*

- REQ-06-1: At least 20 full NBA broadcast game videos (48 minutes each) processed end-to-end
- REQ-06-2: Each game processed with correct --game-id; NBA API shot outcomes attached to CV shots
- REQ-06-3: All CV tracking outputs written to PostgreSQL (not just CSV) — db.py writes wired into run_clip.py
- REQ-06-4: Shot log enriched: made/missed outcome, shot_type from NBA API, matched by court proximity + timestamp
- REQ-06-5: Possession results labeled: scored/turnover/foul from play-by-play matching
- REQ-06-6: Dataset validated: ≥200 enriched shots, ≥500 labeled possessions
- REQ-06-7: Player identity resolved: jersey OCR + NBA API roster → named player for ≥70% of tracked players per game

---

## Phase 7 Requirements — CV-Enhanced ML Models

- REQ-07-1: Shot quality model v2 — adds CV spatial features to NBA API baseline: defender_distance, team_spacing, drive_flag, court_zone_from_tracking, possession_duration. AUC > 0.70 (improvement over API-only v1).
- REQ-07-2: Possession outcome model — trained on 500+ labeled possessions. Features: avg_spacing, avg_defensive_pressure, drive_attempts, fast_break, pick_roll_proxy, team_velocity. Accuracy > 55%.
- REQ-07-3: Player movement profile — distance covered, speed zones, paint time % per player per game. Stored in DB, surfaced in analytics.
- REQ-07-4: Off-ball movement analytics — per player: cuts per game, screens set, curl frequency
- REQ-07-5: Drive success rate — fraction of drive_flag possessions ending in score or foul
- REQ-07-6: Spacing analytics — per-team per-possession: avg player separation, paint density, 3pt spacing index

---

## Phase 8 Requirements — Automated Game Processing

- REQ-08-1: Nightly cron auto-detects new clips in data/games/watch/ and queues for processing (on cloud GPU)
- REQ-08-2: All outputs auto-written to PostgreSQL after each clip completes
- REQ-08-3: Dataset versioning: outputs tagged with tracker_version + date
- REQ-08-4: CLI dashboard: games_processed, shots_labeled, model_readiness thresholds, dataset size
- REQ-08-5: Email/Slack alert when model readiness thresholds crossed (200 shots → retrain shot quality, 500 poss → retrain outcome)

---

## Phase 9 Requirements — Betting Infrastructure

- REQ-09-1: The Odds API returns live lines for all NBA markets: spread, moneyline, totals, player props
- REQ-09-2: betting_edge.py: edge = model_probability − implied_probability; star rating 1–3★
- REQ-09-3: Kelly criterion bet sizing per edge magnitude
- REQ-09-4: CLV backtesting: compare model lines to closing lines; track edge retention
- REQ-09-5: Historical edge tracking stored in DB for drift detection

---

## Phase 10 Requirements — Backend API

- REQ-10-1: FastAPI endpoints: /predictions, /props, /analytics, /betting-edges, /chat, /shot-chart, /lineup, /player-movement
- REQ-10-2: PostgreSQL + asyncpg connection pooling
- REQ-10-3: Redis caching for NBA API responses (TTL: 5min live, 1h recent, 24h historical)
- REQ-10-4: Rate limiting and API key auth
- REQ-10-5: /player-movement endpoint returns per-player court heatmap data for frontend D3 rendering

---

## Phase 11 Requirements — Frontend

- REQ-11-1: Betting Dashboard: today's games, win probability, spread, model edge, star ratings
- REQ-11-2: Analytics Dashboard: shot chart (court map with hex bins), momentum timeline, lineup table with on/off splits, spacing visualization
- REQ-11-3: Player tracking view: animated 2D court, player trails, possession replay scrubber
- REQ-11-4: Player profile page: shot zones, movement heatmap, rolling prop trends, advanced stats
- REQ-11-5: Shot quality overlay: court zone coloring by xFG model output

---

## Phase 12 Requirements — AI Chat Interface

- REQ-12-1: Claude API with tool use calling FastAPI backend
- REQ-12-2: Tools: game_prediction, player_props, analytics, betting_edges, lineup_data, shot_chart, player_movement, injury_status
- REQ-12-3: Context injection: today's games, live injury report, current lines
- REQ-12-4: Natural language shot chart queries: "where does Curry shoot best vs zone defense"

---

## Phase 13 Requirements — Live Win Probability

- REQ-13-1: LSTM trained on 200+ full games of possession sequences, AUC > 0.70
- REQ-13-2: Input features per possession: score_margin, time_remaining, avg_spacing, momentum_score, lineup_net_rtg
- REQ-13-3: WebSocket endpoint pushes updates every possession to frontend
- REQ-13-4: Live win probability chart animates in real time on Analytics Dashboard

---

## Phase 14 Requirements — Infrastructure

- REQ-14-1: Docker Compose runs full stack locally
- REQ-14-2: GitHub Actions: lint + test on push, auto-deploy on merge
- REQ-14-3: Models auto-retrain every 2 weeks on latest data
- REQ-14-4: Feature drift alerts when input distributions shift > 2 sigma
- REQ-14-5: Cloud GPU instance configuration for video processing (separate from web server)
