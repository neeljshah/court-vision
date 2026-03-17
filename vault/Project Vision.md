# Project Vision — NBA AI Analytics & Prediction System

> **Goal: Build the world's best NBA analytics and prediction system.**

---

## What We Are Building

A full-stack system that combines computer vision player tracking, official NBA statistics, and machine learning to:

1. Predict game outcomes and player performance better than sportsbooks
2. Generate research-level analytics for any NBA game
3. Surface betting edges automatically by comparing model predictions to live odds
4. Answer any basketball analytics question via AI chat

---

## Three End Products

### 1. Betting Dashboard
- Pulls live sportsbook lines (spread, total, moneyline, props) via The Odds API
- Compares model predictions to every market, ranks by edge
- Star rating system (1–3★) based on edge magnitude and model confidence
- Markets: game spread, game total, moneyline, first half, player pts/reb/ast/threes O/U
- Historical model accuracy vs closing line (CLV tracking)

### 2. Analytics Dashboard
- Court heatmaps — shot locations, player movement density
- Win probability chart across all possessions in a game
- Team spacing over time — convex hull area per possession
- Shot quality by zone — xFG vs actual eFG%
- Lineup performance — any 5-man unit, net rating, spacing score
- Ball movement network — pass map, touch distribution
- Defensive pressure timeline
- Momentum chart — EMA-smoothed possession momentum per team

### 3. AI Chat Interface (Claude API + tool use)
- Tools: `get_game_prediction()`, `get_player_props()`, `get_analytics()`, `get_lineup_data()`, `get_betting_edges()`
- Answers with real data, not general knowledge
- Examples:
  - *"How will Steph Curry perform tonight vs Memphis?"*
  - *"What lineup should the Celtics use vs zone defense?"*
  - *"What are the best bets tonight?"*
  - *"Show me the win probability chart for last night's Lakers game"*

---

## System Architecture

```
NBA Broadcast Video (.mp4)
    ↓
CV Tracking Pipeline
    → player positions (2D court), ball, spacing, possession, events, shot context
    ↓
NBA API Enrichment
    → shot outcomes, possession results, lineups, box scores, schedule
    ↓
PostgreSQL Database
    → all tracking + stats stored, versioned, queryable
    ↓
ML Models
    → win probability, shot quality, possession outcome, player props, lineup impact
    ↓
Betting Edge Detection
    → model probability vs sportsbook implied probability
    ↓
FastAPI Backend → Web App + AI Chat
```

---

## ML Model Stack

| Model | Type | Input | Output | Data Needed |
|---|---|---|---|---|
| Pre-game win probability | XGBoost | Team stats, rest, home/away, form | Win% + spread | NBA API only — build now |
| Player prop (points) | XGBoost | Usage, TS%, matchup, rest, tracking shot quality | Expected points | NBA API + tracking |
| Player prop (rebounds) | XGBoost | Reb rate, pace, lineup, paint time | Expected rebounds | NBA API + tracking |
| Player prop (assists) | XGBoost | AST rate, ball movement, usage | Expected assists | NBA API |
| Shot quality | XGBoost | Zone, defender dist, spacing, shot clock | xFG (0–1) | 20+ games tracked |
| Possession outcome | XGBoost | Play type, spacing, pressure, clock, lineup | Score/TO/foul % | 50+ games tracked |
| Live win probability | LSTM | Possession sequence: score diff, momentum, spacing, lineups | Win% per possession | 200+ full games |
| Lineup chemistry | Clustering + regression | On/off splits, tracking synergy, spacing | Best unit combos | 100+ games tracked |

---

## Data Sources

| Source | What It Provides | Status |
|---|---|---|
| CV Tracker | positions, spacing, possession, shot context, events | ✅ Built |
| `nba_api` — play-by-play | possession outcomes, shot made/missed, score | ✅ Built |
| `nba_api` — box scores | player stats, team stats, lineups | ✅ Partial |
| `nba_api` — schedule | rest days, back-to-back, home/away, travel | 🔲 Phase 1 |
| `nba_api` — lineup | 5-man units, on/off splits | 🔲 Phase 1 |
| `nba_api` — player info | age, career stats, workload | 🔲 Phase 1 |
| Jersey number OCR | named player identity from video | 🔲 Phase 2 |
| The Odds API | live + historical sportsbook lines | 🔲 Phase 6 |

---

## Build Roadmap

### Phase 1 — Data Infrastructure 🔲
- PostgreSQL schema (games, players, teams, tracking_frames, possessions, shots, lineups, odds, predictions)
- `schedule_context.py` — rest days, back-to-back, travel distance
- `lineup_data.py` — 5-man units, on/off splits from NBA API
- Opponent feature fetcher — defensive rating, pace, eFG% allowed
- NBA API caching layer (rate limit protection)
- Auto-write tracking outputs to PostgreSQL

### Phase 2 — Tracking Improvements 🔲
- **Jersey number OCR** — PaddleOCR/CRNN reads jersey number → NBA API roster lookup → named player
- **HSV re-ID improvements** — k-means color clustering + jersey number as tiebreaker for similar-colored uniforms
- **Referee filtering** — exclude team_id=2 from all spacing and pressure analytics
- Shot clock reading (OCR overlay or pure API fallback)

### Phase 3 — First ML Models (NBA API only) 🔲
- Pre-game win probability (XGBoost, 3 seasons data)
- Player prop models: points, rebounds, assists
- Backtesting framework — CLV as primary metric, Brier score, ROI curves
- SHAP explainability

### Phase 4 — Tracking-Enhanced ML Models 🔲
- Shot quality model (needs 20+ games)
- Possession outcome model (needs 50+ games)
- Integrate into betting edge scoring
- `feature_pipeline.py` + `data_loader.py`

### Phase 5 — Automated Game Processing 🔲
- Nightly cron + job queue for batch processing
- Historical odds collection (The Odds API)
- Dataset versioning by tracker version
- Progress tracker CLI

### Phase 6 — Betting Infrastructure 🔲
- `odds_fetcher.py` — The Odds API live + historical
- `betting_edge.py` — edge = model probability − implied probability
- Star rating (1–3★), Kelly criterion sizing
- CLV backtesting against closing lines

### Phase 7 — Backend API 🔲
- FastAPI: `/predictions`, `/props`, `/analytics`, `/betting-edges`, `/chat`
- PostgreSQL + asyncpg, Redis caching, rate limiting
- Injury/availability endpoint

### Phase 8 — Frontend 🔲
- React + Next.js, Tailwind, D3 + Recharts
- Betting Dashboard, Analytics Dashboard, player tracking view

### Phase 9 — AI Chat 🔲
- Claude API with tool use calling FastAPI backend
- Context: today's games + lines injected into system prompt

### Phase 10 — Live Win Probability 🔲
- LSTM on possession sequences (needs 200+ games)
- Real-time play-by-play feed + WebSocket to frontend

### Phase 11 — Infrastructure 🔲
- Docker, docker-compose, cloud deployment
- CI/CD (GitHub Actions), automated retraining, model drift monitoring

---

## Dataset Compounding Strategy

Every game processed builds the dataset automatically:

```
python run_clip.py --video game.mp4 --game-id XXXXXX --period P --start S

Outputs:
  tracking_data.csv         → per-frame positions, spacing, events
  possessions_enriched.csv  → possession outcomes + score context
  shot_log_enriched.csv     → shot context + made/missed labels
  features.csv              → 60+ ML-ready engineered features
  player_clip_stats.csv     → per-player aggregates
```

| Games Processed | Milestone |
|---|---|
| 0 | Win probability + player props (NBA API only) live |
| 20 | Shot quality model |
| 50 | Possession outcome model |
| 100 | Lineup chemistry model |
| 200+ | Live win probability LSTM |

---

## Tech Stack

| Layer | Technology |
|---|---|
| CV Tracking | Python, YOLOv8n, OpenCV, Kalman, Hungarian |
| Analytics | Python, NumPy, Pandas, SciPy |
| ML Models | XGBoost, LightGBM, PyTorch (LSTM) |
| Database | PostgreSQL |
| Backend API | FastAPI (Python) |
| Frontend | React, Next.js, D3, Recharts, Tailwind |
| AI Chat | Claude API (tool use) |
| Odds Data | The Odds API |
| Environment | conda `basketball_ai`, Python 3.9, CUDA 11.8 |

---

## Known Tracker Issues

| ID | Issue | Status |
|---|---|---|
| ISSUE-001 | Ball detection on fast shots (motion blur) | ✅ Fixed |
| ISSUE-002 | Team color classification in poor lighting | ✅ Fixed |
| ISSUE-003 | Player re-ID when leaving/re-entering frame | ✅ Fixed |
| ISSUE-004 | Homography drift on long videos | ✅ Fixed |
| ISSUE-005 | HSV re-ID on similar-colored uniforms | 🟡 In Progress |
| ISSUE-006 | Anonymous player IDs (no jersey OCR) | 🔲 Phase 2 |
| ISSUE-007 | Referees included in analytics calculations | 🔲 Phase 2 |
| ISSUE-008 | No shot clock from video | 🔲 Phase 2 |

---

## Related Files

- [[CLAUDE.md]] — always read first, current session state
- [[unified_pipeline]] — tracking → CSV pipeline
- [[nba_enricher]] — NBA API enrichment
- [[feature_engineering]] — ML feature generation
- [[shot_quality]] — shot scoring analytics
- [[momentum]] — team momentum tracking
- [[defense_pressure]] — defensive pressure scoring
- [[Tracker Improvements Log]] — all issues and fixes

---

*Last updated: 2026-03-12*
