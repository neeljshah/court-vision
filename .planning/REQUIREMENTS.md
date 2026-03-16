# Requirements: NBA AI System

## Phase 1 Requirements (COMPLETE)

- REQ-01: PostgreSQL schema with tables: games, players, teams, tracking_frames, possessions, shots, lineups, odds, predictions
- REQ-02: schedule_context.py returns rest days, back-to-back flag, travel distance (miles)
- REQ-03: nba_stats.py fetches opponent defensive rating, pace, eFG% allowed

## Phase 2 Requirements

- REQ-04: Jersey number OCR reads number from player crop each frame (PaddleOCR or CRNN)
- REQ-05: Jersey number → player name lookup using NBA API roster for the game
- REQ-06: Named player ID mapping persisted in PostgreSQL across clips
- REQ-07: HSV re-ID uses k-means k=3 color clustering + jersey number tiebreaker on ambiguous cases
- [x] REQ-08: Referees (team_id=2) excluded from all spacing, pressure, and analytics calculations — COMPLETE (02-03)
- REQ-08b: At least 5 real NBA broadcast game clips acquired and enriched with --game-id

## Phase 3 Requirements

- REQ-09: Win probability model (XGBoost, 3 seasons) with Brier score < 0.22
- REQ-10: Player prop models for points, rebounds, assists
- REQ-11: Backtesting framework measuring CLV, Brier score, ROI

## Phase 4 Requirements

- REQ-12: Shot quality (xFG) model trained on 20+ games
- REQ-13: Possession outcome model trained on 50+ games

## Phase 5 Requirements

- REQ-14: Nightly cron auto-processes new clips
- REQ-15: Dataset versioning tags outputs with tracker version

## Phase 6 Requirements

- REQ-16: The Odds API integration returning live NBA lines
- REQ-17: betting_edge.py computes model edge with star ratings

## Phase 7 Requirements

- REQ-18: FastAPI endpoints: /predictions, /props, /analytics, /betting-edges, /chat
- REQ-19: PostgreSQL + asyncpg, Redis caching, rate limiting

## Phase 8 Requirements

- REQ-20: Betting Dashboard with win probability, spread, edge scores
- REQ-21: Analytics Dashboard with shot chart, momentum, lineups
- REQ-22: Player tracking view with animated 2D court

## Phase 9 Requirements

- REQ-23: Claude API with 5 tools calling FastAPI backend

## Phase 10 Requirements

- REQ-24: LSTM win probability model + WebSocket real-time updates

## Phase 11 Requirements

- REQ-25: Docker, CI/CD, cloud deployment, automated retraining
