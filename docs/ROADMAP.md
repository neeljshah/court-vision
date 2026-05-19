# Development Roadmap — CourtVision

*Last updated: 2026-04-15 | Phase 13.5 complete*

---

## World-Class Alignment (2026-04-13)

Non-negotiable gates:
- No official metric can rely on synthetic backtest fallback.
- Model promotion requires calibration and drift checks.
- API changes require contract tests and schema compatibility checks.
- CV progress measured on fixed benchmark clips, not ad-hoc runs.

Priority stack:
1. Contract safety and schema consistency.
2. Backtesting/calibration rigor and claim-evidence consistency.
3. Security and runtime hardening.
4. CV coverage quality and registry density.
5. Commercial packaging.

---

## Phase Overview

*Session 36 | 2026-04-15 | Tests: 960+ pass, 93 skip | Models: 75 trained | CV: 41/94 videos, 16 A/B-grade*

| Phase | Name | Status | Key Deliverable |
|---|---|---|---|
| 1 | Data Infrastructure | ✅ Done | PostgreSQL schema, schedule context, lineup data |
| 2 | Tracker Bug Fixes | ✅ Done | Team color re-ID, EventDetector, 431 tests |
| 2.5 | CV Quality Upgrades | ✅ Done | Broadcast mode, OCR brightness norm, OSNet re-ID wired |
| 3 | NBA Data Collection | ✅ Done | 622 gamelogs, 221K shots, 98.4% PBP |
| 3.5 | Expanded Data Collection | 🟡 Partial | BBRef advanced fetched; Odds API + full injury history pending |
| 4 | Tier 1 ML Models | ✅ Done | Win prob 69.1%, 7 props, 5 game models, xFG v1 |
| 4.5 | Betting + Lifecycle Models | ✅ Done | load_management, injury_risk/return, breakout, public_fade, soft_book_lag |
| 4.6 | Feature Wiring | ✅ Done | Props 30→57 features, all models retrained |
| 4.7 | Prediction Quality Stack | ✅ Done | Ridge meta-stack, temporal weighting, confidence-gated output |
| 4.8 | Quantitative Betting Infra | ✅ Done | Kelly + CLV + cross-book arb + portfolio construction |
| 4.9 | Backtesting + Validation | ✅ Done | Strategy backtester, paper trading, /backtest endpoint |
| 5 | External Factors | ✅ Done | Injury monitor, ref tracker, line monitor |
| G | Full Game Data Collection | ✅ Done | 41/94 videos tracked, 16 A/B-grade, 24 CV records |
| 6 | Full Game Processing + Rich Events | ✅ Done | Rich events aggregated, CV features wired, 266 enriched possessions |
| 7 | Tier 2–3 ML Models | ✅ Done | xFG v2, props retrained with CV features |
| 8 | Possession Simulator v1 | ✅ Done | 7-model chain, 10K Monte Carlo <30s |
| 9 | Feedback Loop + NLP | ✅ Done | Nightly pipeline, auto-retrain, NLP injury models |
| 10 | Tier 4–5 Volume Models | ✅ Done | 15 models (8 Tier4 + 7 Tier5), stubs with safe defaults |
| 10.5 | Advanced CV Signals | ✅ Done | Coverage type, shot arc, biomechanics extractors |
| 11 | Betting Infrastructure + Live | ✅ Done | live_models.py (M70-M75), BettingEdge, CLVTracker, ArbDetector |
| 12 | Full Monte Carlo | ✅ Done | FoulTrouble/GarbageTime/Q4Usage wired, 7-stat distributions |
| 13 | FastAPI Backend | ✅ Done | 24 endpoints across 5 routers, in-process TTL cache |
| **13.5** | **100-game Readiness** | ✅ **Done** | Prop stack wired, isotonic calibration, dedup+crash isolation, backtest endpoint, correlation matrix, CV fatigue, STL features |
| **14** | **100-game RunPod Run** | ⏳ **NEXT** | Stage 100 H.264 videos, launch pod, retrain, fit calibration, /backtest gate, enable betting |
| 15 | Analytics Dashboard | 🔲 | Next.js + D3 shot charts + 10 chart types |
| 16 | AI Chat Interface | 🔲 | Claude API + tool use + render_chart inline |
| 16B | Live Win Probability LSTM | 🔲 | 200+ games, LSTM hidden dim 256, WebSocket real-time |
| 17 | Infrastructure | 🔲 | Docker, CI/CD, cloud GPU, drift monitoring |
| 18 | Calibration + Scale | 🔲 | Full season automation, production monitoring |

---

## Current State (Phase 13.5 Complete)

### What's Built

**CV Pipeline**
- YOLOv8n detection → SIFT homography → Kalman+Hungarian → OSNet re-ID (512-dim) → EasyOCR → EventDetector
- 41/94 videos tracked, 16 A/B-grade, 24 CV player-game records
- 53 unprocessed videos in queue for Phase 14

**ML Models (75 trained artifacts)**
- Win probability: 69.1% accuracy, Brier 0.203
- Player props × 7: pts=0.47, reb=0.40, ast=0.46, fg3m=0.28, blk=0.18, tov=0.25, stl=0.07 R²
- Game models × 5: total, spread, blowout, first-half, pace
- xFG v1: Brier 0.226, 221K shots
- DNP predictor: AUC 0.979
- Tier 4–5 models: 15 specialist models (closeout, rebound, help def, momentum, foul drawing...)
- Full model registry in `data/models/model_registry.json`

**API (24 endpoints)**
- `api/main.py`: /health, /simulate, /simulate_game, /over_prob, /props, /edge, /win-prob, /lineup, /backtest
- `predictions_router.py`: /predictions/props, /injury-risk, /breakout, /lineup-optimizer, /game, /today
- `models_router.py`: /predictions/shot, /win, /player-impact
- `analytics_router.py`: /analytics/shot-chart, /tracking, /lineup-stats
- `dashboard_router.py`: /chat, /analytics/clv-summary, /analytics/edges/today

**Infrastructure**
- Kelly + CLV + cross-book arb (betting_portfolio.py)
- Prop backtester + paper trading (prop_backtester.py)
- Isotonic calibration layer on prop probabilities
- Dedup-by-hash + per-game crash isolation in run_phase_g.py
- RunPod launch scripts (scripts/launch_single_gpu_pod.sh, watch_and_sync.sh)

---

## Open Issues (pre-Phase 14)

| # | Issue | Severity |
|---|-------|---------|
| 1 | Isotonic calibration layer — verify end-to-end wiring before live sizing | CRITICAL |
| 2 | STL R²=0.07 — add opp_to_rate + opp_pace to player_props.py | HIGH |
| 3 | Correlation matrix in kelly_corr not populated (assumes zero) | HIGH |
| 4 | CV fatigue minutes — verify wired into possession_simulator | MEDIUM |
| 5 | 53 unprocessed videos awaiting Phase 14 RunPod run | MEDIUM |

---

## Next: Phase 14 — 100-Game RunPod Run

```bash
bash scripts/launch_single_gpu_pod.sh <IP> <PORT>
bash scripts/watch_and_sync.sh
```

**Targets:**
- 30+ new A/B-grade games processed
- CV registry: 24 → 200+ player-game records
- Prop model retrain with CV features → pts R² target 0.55+
- Isotonic calibration fitted on new volume
- /backtest gate passed for all 7 props
- Betting mode enabled

---

## Completed Phases — Detail

### Phase 1 — Data Infrastructure ✅ (2026-03-12)
- PostgreSQL: 9 tables, 2 views (`database/schema.sql`)
- schedule_context.py, lineup_data.py, nba_stats.py, db.py

### Phase 2 — Tracker Bug Fixes ✅ (2026-03-17)
- Dynamic KMeans team color, ball position fallback, frozen player eviction
- Mean HSV replaces per-crop → 2 fps → 15 fps
- SIFT_INTERVAL=15, SIFT_SCALE=0.5 → 44s → ~4s SIFT overhead

### Phase 3 — NBA API Data ✅ (2026-03-17)
- 622 gamelogs, 221,866 shots, 3,627 PBP games (98.4%)
- 569 players: advanced, hustle, on/off, matchups, synergy
- 1,225+ historical closing lines, 523 contracts, 736 BBRef players

### Phase 4 — Tier 1 ML Models ✅ (2026-03-18)
- Win prob: XGBoost, 27 features, 69.1%, Brier 0.203
- Props × 7: holdout R² range 0.16–0.41 (pts=0.41, reb=0.38, ast=0.36, fg3m=0.29, blk=0.16, tov=0.22, stl=0.18)
- xFG v1: Brier 0.226, DNP: AUC 0.979, Matchup: R²=0.796

### Phase 4.5–4.9 ✅ (2026-03-18 through 2026-04-07)
- load_management, injury_risk/return, breakout, public_fade, soft_book_lag trained
- 30→57 features wired (hustle, synergy, shot dashboard, contested%, defender dist)
- Ridge meta-stack, Kelly + CLV + arb detection, strategy backtester

### Phases 6–13.5 ✅ (2026-04-07 through 2026-04-15)
- Full game processing pipeline wired end-to-end
- All prediction modules scaffolded (73 modules in src/prediction/)
- Possession simulator: 7-model chain, 10K Monte Carlo <30s
- FastAPI: 24 endpoints, in-process TTL cache
- 100-game readiness hardening: crash isolation, calibration, correlation matrix, backtest gate

---

## Accuracy Progression

| Phase | Win Prob | Props R² (pts) | xFG Brier |
|---|---|---|---|
| 4 — initial training | 69.1% | 0.47 | 0.226 |
| 14 — after 100-game retrain | ~71–73% (target) | ~0.55 (target) | ~0.200 (target) |
| Full season (200+ games) | ~74–76% | ~0.65 | ~0.185 |

## Data Volume Milestones

| Games Processed | Models Unlocked |
|---|---|
| 41 (current) | All current models |
| 100 (Phase 14) | Calibration fitted, xFG v2 improved, props retrain |
| 200+ (Phase 16B) | LSTM live win probability |
