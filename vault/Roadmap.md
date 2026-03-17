# Roadmap — 11 Phase Build Plan

*Synced from `ROADMAP.md` — check that file for full task details.*

---

## Phase Status

| Phase | Name | Status |
|---|---|---|
| 1 | Data Infrastructure | 🔲 **START HERE** |
| 2 | Tracking Improvements | 🔲 |
| 3 | First ML Models (NBA API only) | 🔲 |
| 4 | Tracking-Enhanced ML Models | 🔲 |
| 5 | Automated Game Processing | 🔲 |
| 6 | Betting Infrastructure | 🔲 |
| 7 | Backend API (FastAPI) | 🔲 |
| 8 | Frontend (React + Next.js) | 🔲 |
| 9 | AI Chat (Claude API) | 🔲 |
| 10 | Live Win Probability (LSTM) | 🔲 |
| 11 | Infrastructure + Deployment | 🔲 |

---

## Phase 1 — Data Infrastructure 🔲
- [ ] PostgreSQL schema — tables: `games`, `players`, `teams`, `tracking_frames`, `possessions`, `shots`, `lineups`, `odds`, `predictions`
- [ ] `src/data/schedule_context.py` — rest days, back-to-back, travel distance
- [ ] `src/data/lineup_data.py` — 5-man units, on/off splits
- [ ] Opponent feature fetcher in `nba_stats.py`
- [ ] NBA API caching layer
- [ ] Auto-write tracking outputs to PostgreSQL after each clip run

---

## Phase 2 — Tracking Improvements 🔲
- [ ] Jersey number OCR (PaddleOCR/CRNN → NBA API roster → named player)
- [ ] HSV re-ID on similar-colored uniforms (ISSUE-005)
- [ ] Referee filtering from analytics (ISSUE-007)

---

## Phase 3 — First ML Models (NBA API only) 🔲
- [ ] Pre-game win probability (XGBoost, 3 seasons data)
- [ ] Player prop model — points
- [ ] Player prop model — rebounds
- [ ] Player prop model — assists
- [ ] Backtesting framework (CLV as primary metric)
- [ ] SHAP explainability

---

## Phase 4 — Tracking-Enhanced ML Models 🔲
*Requires 20+ processed games*
- [ ] Shot quality model
- [ ] Possession outcome model
- [ ] `feature_pipeline.py` + `data_loader.py`
- [ ] Integrate into betting edge scoring

---

## Phase 5 — Automated Game Processing 🔲
- [ ] Nightly cron + job queue
- [ ] Historical odds data collection
- [ ] Dataset versioning by tracker version
- [ ] Progress tracker CLI

---

## Phase 6 — Betting Infrastructure 🔲
- [ ] `src/data/odds_fetcher.py` — The Odds API
- [ ] `src/analytics/betting_edge.py`
- [ ] Star rating system (1–3★)
- [ ] CLV backtesting
- [ ] Kelly criterion sizing

---

## Phase 7 — Backend API 🔲
- [ ] FastAPI: `/predictions`, `/props`, `/analytics`, `/betting-edges`, `/chat`
- [ ] PostgreSQL + asyncpg, Redis caching, rate limiting
- [ ] Injury/availability endpoint

---

## Phase 8 — Frontend 🔲
- [ ] React + Next.js + Tailwind + D3 + Recharts
- [ ] Betting Dashboard
- [ ] Analytics Dashboard
- [ ] Player tracking view

---

## Phase 9 — AI Chat 🔲
- [ ] Claude API with tool use
- [ ] Tool implementations calling FastAPI
- [ ] Chat UI in frontend

---

## Phase 10 — Live Win Probability 🔲
*Requires 200+ processed games*
- [ ] LSTM on possession sequences
- [ ] Real-time play-by-play feed
- [ ] WebSocket to frontend

---

## Phase 11 — Infrastructure 🔲
- [ ] Docker + docker-compose
- [ ] Cloud deployment
- [ ] CI/CD (GitHub Actions)
- [ ] Automated model retraining
- [ ] Feature drift monitoring

---

## Dataset Milestones

| Games Processed | Unlocks |
|---|---|
| 0 | Win probability + player props (Phase 3) |
| 20 | Shot quality model (Phase 4) |
| 50 | Possession outcome model (Phase 4) |
| 100 | Lineup chemistry model |
| 200+ | Live win probability LSTM (Phase 10) |

---

## Related

- [[Project Vision]] — full product spec
- [[Pipeline/System Architecture]] — technical architecture
- [[Improvements/Tracker Improvements Log]] — open issues
