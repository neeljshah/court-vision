# Roadmap: NBA AI System

## Overview

Build the world's best NBA analytics and prediction system — combining computer vision player tracking, official NBA statistics, and machine learning to predict game outcomes, player performance, and identify betting edges. Final product is a web app with Betting Dashboard, Analytics Dashboard, and AI Chat Interface.

## Phases

- [x] **Phase 1: Data Infrastructure** - PostgreSQL schema, schedule context, lineup data, NBA stats fetcher
- [ ] **Phase 2: Tracking Improvements** - Jersey OCR, named player IDs, HSV re-ID upgrades, referee filtering, better footage acquisition
- [ ] **Phase 3: First ML Models** - Pre-game win probability, player prop models, backtesting framework
- [ ] **Phase 4: Tracking-Enhanced ML Models** - Shot quality model, possession outcome model, feature pipeline
- [ ] **Phase 5: Automated Game Processing** - Nightly cron, job queue, dataset versioning, progress tracker
- [ ] **Phase 6: Betting Infrastructure** - The Odds API integration, betting edge detection, CLV backtesting
- [ ] **Phase 7: Backend API** - FastAPI service wrapping all models, analytics, and NBA data
- [ ] **Phase 8: Frontend** - React + Next.js: Betting Dashboard, Analytics Dashboard, player tracking view
- [ ] **Phase 9: AI Chat Interface** - Claude API with tool use calling FastAPI backend
- [ ] **Phase 10: Live Win Probability** - LSTM on possession sequences, WebSocket real-time updates
- [ ] **Phase 11: Infrastructure** - Docker, CI/CD, cloud deployment, model drift monitoring

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

### Phase 2: Tracking Improvements
**Goal**: Map anonymous player IDs to named NBA players, improve re-ID on similar uniforms, filter referees from analytics, and acquire better game footage.
**Depends on**: Phase 1
**Requirements**: REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-08b
**Success Criteria** (what must be TRUE):
  1. Jersey numbers read from player crops and matched to NBA API roster → named player IDs
  2. Named player mapping persisted in PostgreSQL across clips
  3. HSV re-ID uses k-means color clustering + jersey number tiebreaker on ambiguous cases
  4. Referees (team_id=2) excluded from all spacing, pressure, and analytics calculations
  5. At least 5 real NBA broadcast clips acquired and processed through pipeline
  6. shot_log_enriched populated with --game-id enrichment on processed clips
**Plans**: 6 plans

Plans:
- [ ] 02-00-PLAN.md — Wave 0 test stubs (pytest.ini, conftest.py, test_phase2.py)
- [ ] 02-01-PLAN.md — Jersey OCR module (EasyOCR) + NBA API roster lookup
- [ ] 02-02-PLAN.md — HSV k-means re-ID upgrade + jersey number tiebreaker
- [x] 02-03-PLAN.md — Referee filter completion (feature_engineering + shot_quality)
- [ ] 02-04-PLAN.md — PostgreSQL db.py + player_identity persistence layer + run_clip.py wiring
- [ ] 02-05-PLAN.md — Broadcast footage acquisition + 3-min recurring loop

### Phase 3: First ML Models
**Goal**: Build and backtest pre-game win probability and player prop models using NBA API data only.
**Depends on**: Phase 1
**Requirements**: REQ-09, REQ-10, REQ-11
**Success Criteria** (what must be TRUE):
  1. Win probability model trained on 3 seasons, Brier score < 0.22
  2. Player prop models (points, rebounds, assists) with RMSE within 15% of league average
  3. Backtesting framework reports CLV, Brier score, ROI at 3 edge thresholds
  4. SHAP explains top 5 features per prediction
**Plans**: TBD

### Phase 4: Tracking-Enhanced ML Models
**Goal**: Train shot quality and possession outcome models using tracking pipeline outputs.
**Depends on**: Phases 2 and 3, and 20+ processed games
**Requirements**: REQ-12, REQ-13
**Success Criteria** (what must be TRUE):
  1. Shot quality (xFG) model trained on 20+ games, AUC > 0.65
  2. Possession outcome model trained on 50+ games, accuracy > 55%
  3. feature_pipeline.py and data_loader.py automate feature extraction
**Plans**: TBD

### Phase 5: Automated Game Processing
**Goal**: Auto-process new game clips nightly to compound the dataset without manual intervention.
**Depends on**: Phase 4
**Requirements**: REQ-14, REQ-15
**Success Criteria** (what must be TRUE):
  1. Nightly cron auto-processes new clips in watch folder
  2. All outputs auto-written to PostgreSQL after each clip
  3. Dataset versioning tags outputs with tracker version
  4. CLI dashboard shows games processed, shots labeled, model readiness
**Plans**: TBD

### Phase 6: Betting Infrastructure
**Goal**: Compare model predictions to live sportsbook lines to surface edge bets.
**Depends on**: Phase 3
**Requirements**: REQ-16, REQ-17
**Success Criteria** (what must be TRUE):
  1. The Odds API returns live lines for all NBA markets
  2. betting_edge.py computes edge = model probability − implied probability
  3. Star rating (1–3★) assigned based on edge magnitude
  4. CLV backtesting validates model against closing lines
**Plans**: TBD

### Phase 7: Backend API
**Goal**: FastAPI service wrapping all models, analytics, NBA data, and odds for frontend and AI chat.
**Depends on**: Phases 3 and 6
**Requirements**: REQ-18, REQ-19
**Success Criteria** (what must be TRUE):
  1. All 6 endpoints live and returning correct data
  2. PostgreSQL connection pooling with asyncpg
  3. Redis caching for NBA API responses
  4. Rate limiting and API key auth active
**Plans**: TBD

### Phase 8: Frontend
**Goal**: Three-surface web app with Betting Dashboard, Analytics Dashboard, and player tracking view.
**Depends on**: Phase 7
**Requirements**: REQ-20, REQ-21, REQ-22
**Success Criteria** (what must be TRUE):
  1. Betting Dashboard shows today's games with win probability, spread, edge scores
  2. Analytics Dashboard has shot chart, momentum timeline, lineup table
  3. Player tracking view shows animated 2D court with scrubber
**Plans**: TBD

### Phase 9: AI Chat Interface
**Goal**: Natural language access to all predictions and analytics via Claude API with tool use.
**Depends on**: Phase 8
**Requirements**: REQ-23
**Success Criteria** (what must be TRUE):
  1. Claude can answer any basketball question with real data from FastAPI tools
  2. 5 tools implemented: game_prediction, player_props, analytics, betting_edges, lineup_data
  3. Context management injects today's games and lines into system prompt
**Plans**: TBD

### Phase 10: Live Win Probability
**Goal**: Real-time win probability updates during games via LSTM on possession sequences.
**Depends on**: Phase 9, and 200+ processed games
**Requirements**: REQ-24
**Success Criteria** (what must be TRUE):
  1. LSTM trained on 200+ games, AUC > 0.70
  2. WebSocket endpoint pushes updates to frontend every possession
  3. Live win probability chart updates in real time on Analytics Dashboard
**Plans**: TBD

### Phase 11: Infrastructure
**Goal**: Docker, CI/CD, cloud deployment, automated retraining, model drift monitoring.
**Depends on**: Phase 10
**Requirements**: REQ-25
**Success Criteria** (what must be TRUE):
  1. Docker Compose runs full stack locally
  2. GitHub Actions lint + test on push, auto-deploy on merge
  3. Models auto-retrain every 2 weeks
  4. Feature drift alerts when input distributions shift
**Plans**: TBD
