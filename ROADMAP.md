# Build Roadmap

Full phase-by-phase plan to complete the NBA AI system. Phases are ordered by dependency — each phase unlocks the next.

---

## Phase 1 — Data Infrastructure
**Goal:** Everything downstream needs a real database and complete NBA context. Build this before any models.

- [ ] PostgreSQL schema — tables: `games`, `players`, `teams`, `tracking_frames`, `possessions`, `shots`, `lineups`, `odds`, `predictions`
- [ ] Database migrations + seed scripts
- [ ] `src/data/schedule_context.py` — rest days, back-to-back flag, home/away, travel distance (miles) from city coordinates
- [ ] `src/data/lineup_data.py` — 5-man units and on/off splits from NBA API
- [ ] Opponent feature fetcher in `src/data/nba_stats.py` — opponent defensive rating, pace, eFG% allowed
- [ ] NBA API caching layer — rate limit protection, cache to `data/nba/` (already partially done)
- [ ] Auto-write tracking outputs to PostgreSQL after each clip run

**Unlocks:** Complete feature vectors for all ML models

---

## Phase 2 — Tracking Improvements
**Goal:** Player IDs need to map to named NBA players. The current system tracks anonymous IDs — models can't be attributed to specific players without this.

- [ ] Jersey number OCR — add PaddleOCR or fine-tuned CRNN to read jersey number from player crop each frame
- [ ] Jersey number → player name lookup using NBA API roster for the game
- [ ] Persist named player ID mapping in PostgreSQL — once identified, player keeps their name across clips
- [ ] HSV re-ID improvements — tackle jersey confusion on similar-colored uniforms (current known issue)
  - Candidate fix: add dominant-color clustering (k-means k=3) on jersey crop to get more robust color descriptor
  - Candidate fix: use jersey number as tiebreaker when HSV similarity is ambiguous
- [ ] Filter referees from all analytics calculations — they are currently tracked as team_id=2 but corrupt spacing/pressure metrics

**Unlocks:** Player-attributed tracking data, named player prop models, per-player analytics

---

## Phase 3 — First ML Models (NBA API Only)
**Goal:** Build the models that don't require tracking data first — these can go live immediately and backtest immediately.

- [ ] `src/prediction/win_probability.py` — XGBoost pre-game win probability
  - Features: team offensive rating, defensive rating, pace, home/away, rest days, back-to-back, travel, recent form (last 5 games), season record
  - Training data: 3 seasons of NBA games from NBA API
  - Output: win probability (0–1), expected point margin
- [ ] `src/prediction/game_prediction.py` — wraps win probability + point total model
- [ ] Player prop models — one file per target, XGBoost
  - `src/prediction/props_points.py` — projected points
  - `src/prediction/props_rebounds.py` — projected rebounds
  - `src/prediction/props_assists.py` — projected assists
  - Features: rolling usage rate, TS%, matchup defensive rating, rest, minutes projection, home/away
- [ ] `src/pipeline/model_pipeline.py` — train/eval/save model pipeline
- [ ] Backtesting framework — run predictions on historical games, measure accuracy vs actual results
  - Primary metric: Closing Line Value (CLV) — did the model beat the closing sportsbook line?
  - Secondary: Brier score, calibration curve, ROI at various edge thresholds
- [ ] SHAP explainability — top feature contributions per prediction

**Unlocks:** First working predictions, betting edge detection (Phase 6), prop model validation

---

## Phase 4 — Tracking-Enhanced ML Models
**Goal:** Use the tracking pipeline outputs to train models that need spatial data. Requires processed game clips (20–50 games).

- [ ] Shot quality model (needs 20+ games, ~200+ shots labeled)
  - Features: zone prior (NBA eFG%), defender distance, team spacing, shot clock, possession depth, shot type
  - Label: made/missed from NBA API shot logs
  - Output: xFG (0–1) per shot
- [ ] Possession outcome model (needs 50+ games, ~500+ possessions labeled)
  - Features: possession type, spacing, defensive pressure, ball-handler quality, shot clock, lineup net rating
  - Label: scored / turnover / foul from NBA API play-by-play
  - Output: probability of each outcome
- [ ] Integrate shot quality + possession outcome into betting edge scoring
- [ ] `src/pipeline/feature_pipeline.py` — automated feature extraction from raw tracking data
- [ ] `src/pipeline/data_loader.py` — load and merge tracking + NBA API features for model training

**Unlocks:** Tracking-based prop model enhancements, possession value analytics, bet sizing based on model confidence

---

## Phase 5 — Automated Game Processing
**Goal:** The dataset compounds only if games are processed automatically. Manual processing won't scale to 200+ games.

- [ ] Nightly cron job — auto-run `run_clip.py` on new game clips added to a watch folder
- [ ] Job queue (e.g. Celery + Redis or simple subprocess queue) — batch-process historical clips without manual intervention
- [ ] Auto-trigger NBA API enrichment after tracking completes
- [ ] Auto-write all outputs to PostgreSQL
- [ ] Historical odds data collection — pull and store historical sportsbook lines from The Odds API (required for backtesting Phase 6)
- [ ] Dataset versioning — tag each processed game with tracker version so outputs can be reprocessed when tracker improves
- [ ] Progress tracker — simple CLI dashboard showing: games processed, shots labeled, possessions labeled, model readiness by phase

**Unlocks:** Dataset at ML-usable scale, historical odds for backtesting

---

## Phase 6 — Betting Infrastructure
**Goal:** Compare model predictions to sportsbook lines and identify edge.

- [ ] `src/data/odds_fetcher.py` — The Odds API integration, pull live lines for all markets
- [ ] Historical odds storage in PostgreSQL — game lines, player prop lines, closing lines
- [ ] `src/analytics/betting_edge.py` — edge = model probability − implied probability
- [ ] Star rating system (1–3★) based on edge magnitude and model confidence interval
- [ ] CLV backtesting — compare model's pre-game line to closing sportsbook line to validate predictive quality
- [ ] Kelly criterion sizing — optimal bet fraction given edge and bankroll (for reference, not auto-betting)
- [ ] Bet tracker — log recommended bets and actual results for ongoing accuracy monitoring

**Unlocks:** Betting Dashboard, model validation against real markets

---

## Phase 7 — Backend API
**Goal:** Wrap all models and data in a FastAPI service that the frontend and AI chat can query.

- [ ] `api/main.py` — FastAPI app setup
- [ ] `/predictions` — pre-game win probability and spread for all today's games
- [ ] `/props/{player_id}` — player prop projections vs posted lines
- [ ] `/analytics/{game_id}` — full game analytics (shot chart, spacing, momentum, lineups)
- [ ] `/betting-edges` — ranked list of today's best bets with edge scores
- [ ] `/chat` — Claude API proxy with tool injection
- [ ] PostgreSQL connection pooling (asyncpg)
- [ ] Redis caching layer — cache NBA API responses and model outputs
- [ ] Rate limiting and auth (API key)
- [ ] Injury / availability endpoint — flag players listed as questionable/out

**Unlocks:** Frontend, AI chat

---

## Phase 8 — Frontend
**Goal:** Build the three-surface web app.

- [ ] Next.js project scaffold with Tailwind + D3 + Recharts
- [ ] **Betting Dashboard**
  - Today's games with win probability and spread
  - Model vs sportsbook table, edge scores, star ratings
  - Player props panel — projected vs posted line
  - Historical model accuracy tracker
- [ ] **Analytics Dashboard**
  - Court visualizations — shot chart, movement heatmap, spacing map (D3)
  - Win probability chart over game time
  - Momentum and defensive pressure timelines
  - Lineup table — filter by lineup, view net rating and spacing
  - Pass network graph
- [ ] **Player tracking view** — animated 2D court with player movement scrubber
- [ ] Responsive layout, game selector, date picker

**Unlocks:** AI Chat integration, deployable product

---

## Phase 9 — AI Chat Interface
**Goal:** Natural language access to all predictions and analytics via Claude API.

- [ ] Claude API integration with tool use
- [ ] Tool implementations calling FastAPI backend:
  - `get_game_prediction(game_id)` → win probability, spread
  - `get_player_props(player_name, date)` → prop projections
  - `get_analytics(game_id)` → shot chart, spacing, lineup data
  - `get_betting_edges(date)` → top value bets
  - `get_lineup_data(team, lineup)` → net rating, spacing
- [ ] Context management — inject today's games + lines into system prompt
- [ ] Chat UI panel in the frontend

**Unlocks:** Full product complete

---

## Phase 10 — Live Win Probability
**Goal:** Real-time win probability updates during games (requires 200+ processed games for LSTM training).

- [ ] LSTM model on possession sequences
  - Input: running score diff, time remaining, possession outcomes, momentum, lineup net rating
  - Output: win probability per possession
  - Training: 200+ full games of possession sequences
- [ ] Real-time game feed — pull live play-by-play from NBA API during games
- [ ] WebSocket endpoint in FastAPI — push win probability updates to frontend
- [ ] Live win probability chart in Analytics Dashboard

**Unlocks:** In-game betting features, live dashboard

---

## Phase 11 — Infrastructure and Production
**Goal:** Make the system deployable, maintainable, and self-improving.

- [ ] Docker — containerize FastAPI + PostgreSQL + Redis + Next.js
- [ ] `docker-compose.yml` for local dev
- [ ] Cloud deployment — VPS or managed Postgres (Railway / Render / AWS)
- [ ] CI/CD — GitHub Actions: lint + test on push, auto-deploy on merge to main
- [ ] Automated model retraining — retrain win probability and prop models every 2 weeks as season progresses
- [ ] Feature drift monitoring — alert when input feature distributions shift significantly
- [ ] Model performance dashboard — track accuracy vs closing line over time
- [ ] Test coverage — unit tests for data pipeline, analytics modules, API endpoints

---

## Data Volume Milestones

| Games Processed | What Becomes Available |
|---|---|
| 0 | Pre-game win probability, player props (NBA API only) |
| 20 | Shot quality model |
| 50 | Possession outcome model |
| 100 | Lineup chemistry model |
| 200+ | Live win probability LSTM |

---

## Known Issues (Tracker)

| ID | Issue | Status |
|---|---|---|
| ISSUE-001 | Ball detection on fast shots | ✅ Fixed |
| ISSUE-002 | Team color classification in poor lighting | ✅ Fixed |
| ISSUE-003 | Player re-ID when leaving/re-entering frame | ✅ Fixed |
| ISSUE-004 | Homography drift on long videos | ✅ Fixed |
| ISSUE-005 | HSV re-ID on similar-colored uniforms | 🟡 In Progress |
| ISSUE-006 | Anonymous player IDs (no jersey OCR) | 🔲 Phase 2 |
| ISSUE-007 | Referees included in analytics calculations | 🔲 Phase 2 |
| ISSUE-008 | No shot clock from video (using API fallback) | 🔲 Phase 2 |
