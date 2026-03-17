# Roadmap: NBA AI System

## Overview

Build the world's best NBA analytics and prediction system — combining computer vision player tracking, exhaustive NBA API data, external context (injuries, refs, odds), and ML to predict game outcomes, player performance, and identify betting edges.

**Data Maximization Principle**: Extract every possible data point from the NBA API first (no video needed). CV tracking enhances models — it does not gate them.

**Final Product**: Betting Dashboard + Analytics Dashboard + AI Chat Interface

---

## Phases

- [x] **Phase 1: Data Infrastructure** — PostgreSQL schema, schedule context, lineup data, NBA stats fetcher
- [ ] **Phase 2: Critical Tracker Bug Fixes** — Fix team-color separation (all-green bug), event detector (0 shots/dribbles), validate clip outputs (gap closure plans 02-06 through 02-08 in progress)
- [ ] **Phase 3: NBA API Data Maximization** — Advanced stats + gamelogs for all 569 players, shot charts (50K+ shots), play-by-play for all 1,225 games, lineup data, referee history
- [ ] **Phase 4: First ML Models** — Win probability (train now), player props (full data), shot quality from NBA API shot charts, lineup efficiency
- [ ] **Phase 5: External Factors Scraper** — Injury monitor, referee tracker, line movement, news scraper
- [ ] **Phase 6: Full Game Video Processing** — 20+ full broadcast games on GPU machine, PostgreSQL writes wired, shots + possessions enriched with game IDs
- [ ] **Phase 7: CV-Enhanced ML Models** — Shot quality v2 (add spatial context), possession outcome model, player movement analytics
- [ ] **Phase 8: Automated Game Processing** — Nightly pipeline, dataset versioning, model readiness alerts
- [ ] **Phase 9: Betting Infrastructure** — The Odds API, betting edge detection, Kelly criterion, CLV backtesting
- [ ] **Phase 10: Backend API** — FastAPI: /predictions, /props, /analytics, /betting-edges, /shot-chart, /lineup, /player-movement, /chat
- [ ] **Phase 11: Frontend** — React + Next.js: Betting Dashboard, Analytics Dashboard, player tracking view, player profiles
- [ ] **Phase 12: AI Chat Interface** — Claude API with 8 tools calling FastAPI, natural language analytics
- [ ] **Phase 13: Live Win Probability** — LSTM on possession sequences, WebSocket real-time updates
- [ ] **Phase 14: Infrastructure** — Docker, CI/CD, cloud GPU for video processing, model drift monitoring

---

## Phase Details

### Phase 1: Data Infrastructure
**Goal**: Build PostgreSQL schema and NBA data layer so all downstream models have a real database and complete context.
**Depends on**: Nothing
**Requirements**: REQ-01, REQ-02, REQ-03
**Success Criteria** (what must be TRUE):
  1. PostgreSQL schema created with all 9 tables and 2 views
  2. schedule_context.py returns rest days, back-to-back flag, travel distance
  3. lineup_data.py returns 5-man units and on/off splits
  4. nba_stats.py returns opponent defensive rating, pace, eFG% allowed
**Plans**: 3 plans
**Status**: COMPLETE

Plans:
- [x] 01-01: PostgreSQL schema + migrations
- [x] 01-02: schedule_context.py + lineup_data.py
- [x] 01-03: nba_stats.py opponent features + API caching layer

---

### Phase 2: Critical Tracker Bug Fixes
**Goal**: Fix the two critical bugs that make all existing CV tracking data unreliable: team color separation (all players currently labeled 'green') and event detection (0 shots, 0 dribbles detected across all 17 clips).
**Depends on**: Phase 1
**Requirements**: REQ-02A, REQ-02B, REQ-02C, REQ-02D, REQ-02E, REQ-02F
**Success Criteria** (what must be TRUE):
  1. Both teams appear in team column (e.g. 'white' and 'green') for all re-processed clips
  2. Shot events detected at ≥1 per minute of footage across all clips
  3. Dribble events fire — ISSUE-011 (ball_pos/possessor_pos None in 2D) resolved
  4. Pass events fire on ball possession transfers
  5. Re-processed clips have non-zero shot_events and two distinct team labels
  6. 17 existing clips re-processed; new CSVs validated before committing

**Key Bugs to Fix**:
- `color_reid.py` / `advanced_tracker.py`: k-means team assignment producing single cluster (all green) — needs dominant opponent color seeding or global k=2 across all detections
- `event_detector.py`: ball_pos and possessor_pos passed as None when using 2D court coordinates — need to trace call path from unified_pipeline.py to EventDetector.update()
- `event_detector.py`: shot detection threshold likely too strict for broadcast angle — review velocity/arc/zone thresholds

**Plans**: 9 plans (02-00 through 02-08)

Plans:
- [x] 02-00-PLAN.md — Wave 0 test infrastructure (pytest.ini, conftest.py, test stubs)
- [x] 02-01-PLAN.md — Jersey OCR: EasyOCR dual-pass + JerseyVotingBuffer
- [x] 02-02-PLAN.md — Tracker integration: _jersey_buf per slot, reset_slot() on eviction
- [x] 02-03-PLAN.md — Referee filtering: NaN sentinel, string label "referee"
- [x] 02-04-PLAN.md — Player identity persistence: player_identity_map + persist_identity_map()
- [x] 02-05-PLAN.md — download_batch() in video_fetcher + scripts/loop_processor.py
- [ ] 02-06-PLAN.md — REQ-02A: Remove all-green unification, 5+5+1 dual-team slot layout (gap closure)
- [ ] 02-07-PLAN.md — REQ-02B/C/D/E: EventDetector unit tests + clip duration validator (gap closure)
- [ ] 02-08-PLAN.md — REQ-02F: Re-process 17 clips on GPU machine, update CLAUDE.md (gap closure, human checkpoint)

---

### Phase 3: NBA API Data Maximization
**Goal**: Exhaust every NBA API endpoint to build the richest possible dataset before training any models. No video processing required. This phase unlocks shot quality, player props, and lineup models using pure NBA data.
**Depends on**: Phase 1
**Requirements**: REQ-03A-1 through REQ-03G-3
**Success Criteria** (what must be TRUE):
  1. Advanced stats scraped for all 569 active players (usg%, TS%, off/def/net_rtg, PIE, ast%, reb%, eFG%, scoring zones, misc) — scraper_coverage.json shows score = 1.0 for all
  2. Gamelogs scraped for all active players × 3 seasons (2022-23, 2023-24, 2024-25) with last-5/10/15/20 splits
  3. Shot charts scraped: ≥50,000 total shots with court_x, court_y, made/missed, shot_type, zone, distance, quarter, game_clock, score_margin
  4. Play-by-play scraped for all 1,225+ games in 2024-25; indexed in pbp_index.json
  5. 5-man lineup data with net_rtg/off_rtg/def_rtg/pace/minutes for all 30 teams × 3 seasons
  6. Referee assignments + historical pace/foul tendencies available for prediction features

**Data This Unlocks**:
- 50,000+ shots with outcomes → shot quality model (no CV needed)
- All-player rolling stats → player prop models for every player
- Full PBP sequences → possession outcome patterns
- Lineup on/off splits → lineup chemistry model
- Referee features → win probability accuracy improvement

Plans: TBD

---

### Phase 4: First ML Models (Full NBA API Data)
**Goal**: Train win probability, player props, shot quality (from NBA API shot charts), and lineup efficiency models using the exhaustive NBA API dataset built in Phase 3.
**Depends on**: Phases 1 and 3
**Requirements**: REQ-04-1 through REQ-04-6
**Success Criteria** (what must be TRUE):
  1. Win probability model trained and validated — Brier score < 0.22, walk-forward backtest complete
  2. Player prop models (points, rebounds, assists) for all 569 players — RMSE < 15% of league average
  3. Shot quality model v1 trained on NBA API shot charts (no CV) — AUC > 0.65. Features: distance, zone, type, game_clock, score_margin, quarter
  4. Lineup efficiency model predicts lineup net_rtg from player advanced stats — R² > 0.40
  5. All models saved to data/models/; SHAP feature importance computed
  6. Backtesting: CLV proxy, Brier score, ROI reported at 3 edge thresholds

Plans: TBD

---

### Phase 5: External Factors Scraper
**Goal**: Add injury status, referee tendencies, line movement, and news signals as prediction features — these are systematically underpriced by sportsbooks.
**Depends on**: Phase 1
**Requirements**: REQ-05-1 through REQ-05-5
**Success Criteria** (what must be TRUE):
  1. injury_monitor.py polls NBA official + Rotowire every 30 min; player status in DB
  2. ref_tracker.py scrapes daily assignments; historical foul_rate, pace_impact, home_win_pct available
  3. line_monitor.py polls The Odds API; opening vs closing line stored; CLV proxy computed
  4. All external features available as columns in win probability and prop model inputs
  5. Model accuracy delta measured with/without external features (expect +1-2% on props)

Plans: TBD

---

### Phase 6: Full Game Video Processing
**Goal**: Process 20+ complete NBA broadcast games (48 minutes each) on a capable GPU machine to generate enriched CV tracking data with shot outcomes and possession results.
**Depends on**: Phase 2 (tracker bugs fixed), Phase 1 (PostgreSQL schema)
**Requirements**: REQ-06-1 through REQ-06-7
**CRITICAL**: Never run video processing on local dev machine — requires cloud GPU or separate workstation
**Success Criteria** (what must be TRUE):
  1. 20+ full broadcast games processed end-to-end with correct --game-id flags
  2. shot_log_enriched: ≥200 shots with made/missed outcome, court coordinates, defender distance
  3. possessions_labeled: ≥500 possessions with result (scored/turnover/foul)
  4. All outputs written to PostgreSQL — run_clip.py wired to db.py writes
  5. Team separation working: both teams labeled distinctly in all outputs
  6. Player identity resolved for ≥70% of tracked players per game via jersey OCR + roster lookup
  7. Dataset versioned with tracker_version tag

Plans: TBD

---

### Phase 7: CV-Enhanced ML Models
**Goal**: Add computer vision spatial context to existing NBA API models — defender distance, team spacing, drive context, off-ball movement — to push accuracy beyond pure statistics.
**Depends on**: Phases 4, 5, and 6 (and 20+ enriched games)
**Requirements**: REQ-07-1 through REQ-07-6
**Success Criteria** (what must be TRUE):
  1. Shot quality model v2 (CV-enhanced): AUC > 0.70 — improvement over API-only v1 (0.65)
  2. Possession outcome model trained on 500+ labeled possessions — accuracy > 55%
  3. Player movement analytics in DB: distance/game, speed zones, paint time%, court coverage
  4. Drive success rate computed per player
  5. Spacing analytics: avg player separation, paint density, 3pt spacing index per possession
  6. Off-ball movement: cuts, screens, curl frequency per player per game

Plans: TBD

---

### Phase 8: Automated Game Processing
**Goal**: Make the dataset self-compounding — process new games automatically without manual intervention.
**Depends on**: Phase 6
**Requirements**: REQ-08-1 through REQ-08-5
**Success Criteria** (what must be TRUE):
  1. Nightly cron detects new clips and queues for GPU processing
  2. All outputs auto-written to PostgreSQL after each game
  3. Dataset versioning active — every output tagged with tracker_version + date
  4. CLI dashboard shows: games processed, shots labeled, possession labels, model readiness
  5. Automatic model retraining triggered when readiness thresholds crossed

Plans: TBD

---

### Phase 9: Betting Infrastructure
**Goal**: Turn model predictions into actionable betting signals by comparing to live sportsbook lines.
**Depends on**: Phase 5 (live lines), Phase 4 (trained models)
**Requirements**: REQ-09-1 through REQ-09-5
**Success Criteria** (what must be TRUE):
  1. The Odds API returns live lines for spread, moneyline, totals, and player props
  2. betting_edge.py computes edge = model_prob − implied_prob; star ratings 1–3★
  3. Kelly criterion bet sizing active
  4. CLV backtesting validates edge retention vs closing lines
  5. Historical edge log in DB for drift detection and performance tracking

Plans: TBD

---

### Phase 10: Backend API
**Goal**: FastAPI service exposing all models, analytics, and data to frontend and AI chat.
**Depends on**: Phases 4, 7, and 9
**Requirements**: REQ-10-1 through REQ-10-5
**Success Criteria** (what must be TRUE):
  1. 8 endpoints live: /predictions, /props, /analytics, /betting-edges, /shot-chart, /lineup, /player-movement, /chat
  2. PostgreSQL + asyncpg connection pooling
  3. Redis caching: 5min live, 1h recent, 24h historical
  4. Rate limiting + API key auth
  5. /player-movement returns heatmap-ready court coordinate data

Plans: TBD

---

### Phase 11: Frontend
**Goal**: Three-surface web app with Betting Dashboard, Analytics Dashboard (including shot charts and movement heatmaps), and player tracking view.
**Depends on**: Phase 10
**Requirements**: REQ-11-1 through REQ-11-5
**Success Criteria** (what must be TRUE):
  1. Betting Dashboard: today's games, win probability, spread edge, star ratings, prop alerts
  2. Analytics Dashboard: shot chart (court hex-bin map), momentum timeline, lineup on/off table, spacing visualization
  3. Player tracking view: animated 2D court with possession replay, player trails
  4. Player profile: shot zones, movement heatmap, rolling prop trends, advanced stats radar
  5. Shot quality overlay: court zones colored by xFG model output

Plans: TBD

---

### Phase 12: AI Chat Interface
**Goal**: Natural language access to all predictions, analytics, and shot data via Claude API with tool use.
**Depends on**: Phase 11
**Requirements**: REQ-12-1 through REQ-12-4
**Success Criteria** (what must be TRUE):
  1. Claude answers any NBA question with real-time data from FastAPI tools
  2. 8 tools: game_prediction, player_props, analytics, betting_edges, lineup_data, shot_chart, player_movement, injury_status
  3. Context injection: today's games, live injury report, current lines in system prompt
  4. Shot chart natural language: "where does Curry shoot best in Q4 when down 5+"

Plans: TBD

---

### Phase 13: Live Win Probability
**Goal**: Real-time win probability updates during games via LSTM trained on possession sequences.
**Depends on**: Phase 12, and 200+ processed games from Phase 8
**Requirements**: REQ-13-1 through REQ-13-4
**Success Criteria** (what must be TRUE):
  1. LSTM trained on 200+ games — AUC > 0.70
  2. Input sequence: score_margin, time_remaining, spacing, momentum, lineup_net_rtg
  3. WebSocket endpoint pushes update every possession
  4. Live win probability chart animates in real time

Plans: TBD

---

### Phase 14: Infrastructure
**Goal**: Docker, CI/CD, cloud deployment, automated retraining, model drift monitoring.
**Depends on**: Phase 13
**Requirements**: REQ-14-1 through REQ-14-5
**Success Criteria** (what must be TRUE):
  1. Docker Compose runs full stack locally
  2. GitHub Actions: lint + test on push, auto-deploy on merge
  3. Models auto-retrain every 2 weeks on latest data
  4. Feature drift alerts when input distributions shift > 2 sigma
  5. Cloud GPU instance configured for video processing (separate from web server)

Plans: TBD
