# Development Roadmap — NBA AI System

**Vision:** A self-improving possession-by-possession Monte Carlo game simulator — 90 ML models, 10,000 simulations per game — producing full stat distributions for every player compared against sportsbook lines, accessible via conversational AI that renders charts inline.

---

## Phase Overview

| Phase | Name | Status | Key Deliverable |
|---|---|---|---|
| 1 | Data Infrastructure | ✅ Done | PostgreSQL schema, schedule context, lineup data |
| 2 | Tracker Bug Fixes | ✅ Done | Team color re-ID, EventDetector, 431 tests |
| 2.5 | CV Quality Upgrades | 🟡 Active | Pose estimation, ByteTrack, per-clip homography |
| 3 | NBA Data Collection | ✅ Done | 622 gamelogs, 221K shots, 98.4% PBP |
| 3.5 | Expanded Data Collection | 🔲 | BBRef 6yr + untapped nba_api + betting markets |
| 4 | Tier 1 ML Models | ✅ Done | Win prob 69.1%, 7 props R²>0.93, 5 game models |
| 4.5 | Betting + Lifecycle Models | 🔲 | Sharp detector, CLV predictor, DNP, load mgmt |
| 4.6 | Feature Wiring | ✅ Done | 30→57 features, retrained all models |
| 4.7 | Prediction Quality Stack | 🔲 | Model stacking, temporal weighting, meta-model |
| 4.8 | Quantitative Betting Infra | 🔲 | CLV tracking, cross-book arb, portfolio construction |
| 4.9 | Backtesting + Validation | 🔲 | Strategy backtester, paper trading, validation gate |
| 5 | External Factors | ✅ Done | Injury monitor, ref tracker, line monitor |
| 6 | Full Game Processing | 🔲 | 20 full games → PostgreSQL → shots enriched |
| 7 | Tier 2–3 ML Models | 🔲 | xFG v2 + CV behavioral features + props retrain |
| 8 | Possession Simulator v1 | 🔲 | 7-model chain, 10K Monte Carlo |
| 9 | Feedback Loop + NLP | 🔲 | Nightly retrain, NLP injury models |
| 10 | Tier 4–5 ML Models | 🔲 | Fatigue, lineup chemistry, matchup matrix |
| 10.5 | Advanced CV Signals | 🔲 | Coverage type, shot arc, biomechanics, audio |
| 11 | Betting Infrastructure | 🔲 | Odds API, Kelly, CLV pipeline |
| 12 | Full Monte Carlo | 🔲 | All 90 models, complete stat distributions |
| 13 | FastAPI Backend | 🔲 | 12 endpoints, Redis caching, WebSocket |
| 14 | Analytics Dashboard | 🔲 | Next.js + D3 shot charts + 10 chart types |
| 15 | AI Chat Interface | 🔲 | Claude API + 10 tools + render_chart inline |
| 16 | Live Win Probability | 🔲 | 200+ games, LSTM, real-time WebSocket |
| 17 | Infrastructure | 🔲 | Docker, CI/CD, cloud GPU, monitoring |
| 18 | Calibration + Scale | 🔲 | Full season automation, production monitoring |

---

## Completed Phases

### Phase 1 — Data Infrastructure ✅
**Completed:** 2026-03-12

- PostgreSQL schema — 9 tables, 2 views (`database/schema.sql`)
- `schedule_context.py` — rest days, back-to-back, travel distance
- `lineup_data.py` — 5-man units, on/off splits
- `nba_stats.py` — opponent features (off/def rating, pace, eFG%)
- `db.py` — connection helper

---

### Phase 2 — Critical Tracker Bug Fixes ✅
**Completed:** 2026-03-17

- Dynamic KMeans team color separation (warm-up 30 frames → calibrate → recalibrate every 150)
- Ball position fallback: possessor 2D coords → EventDetector fires on shot
- Frozen player eviction: `_freeze_age` after 20 consecutive frozen frames
- Mean HSV replaces per-crop KMeans → 2 fps → 15 fps
- SIFT_INTERVAL=15, SIFT_SCALE=0.5 → 44s → ~4s SIFT overhead per clip
- 431 tests passing

---

### Phase 3 — NBA API Data Collection ✅
**Completed:** 2026-03-17 (gap-filled 2026-03-18)

| Dataset | Count |
|---|---|
| Player gamelogs | 622 / 569 players |
| Shot chart coordinates | 221,866 shots |
| Play-by-play | 3,627 / 3,685 games (98.4%) |
| Advanced stats | 569 / 569 players |
| Hustle stats | 567 players × 3 seasons |
| On/off splits | 569 players × 3 seasons |
| Defender zone FG% | 566 players × 3 seasons |
| Matchup data | 2,200+ records × 3 seasons |
| Synergy play types | 600 records |
| BBRef VORP/WS48/BPM | 736 players × 3 seasons |
| Historical closing lines | 1,225+ games × 3 seasons |
| Player contracts | 523 players |

---

### Phase 4 — Tier 1 ML Models ✅
**Completed:** 2026-03-18

- Win probability: XGBoost, 27 features, 69.1% accuracy, Brier 0.203
- Player props: 7 models (pts/reb/ast/3pm/stl/blk/tov), R²>0.93 all
- Game models: 5 models (total/spread/blowout/first-half/pace)
- xFG v1: Brier 0.226, trained on 221,866 shots
- DNP predictor: LogisticRegression, ROC-AUC 0.979
- Matchup model: XGBoost R²=0.808, MAE 4.55
- Prop correlation matrix: 508 players, 3,447 lineup pairs

---

### Phase 4.6 — Feature Wiring ✅
**Completed:** 2026-03-18

Wired 27 previously unused cached data signals into prop models — zero new scraping:

| Feature Added | Source | Impact |
|---|---|---|
| VORP, WS/48 | BBRef | +0.02 R² (pts model) |
| Hustle deflections/game | NBA Hustle | Defensive activity signal |
| On/off net rating diff | On/Off splits | True impact rating |
| Synergy ISO/PnR/Spot-up PPP | Synergy | Play type efficiency |
| Contested shot %, C&S%, pull-up % | Shot Dashboard | Shot creation profile |
| DNP risk score | DNP predictor | Future availability |
| Sharp detector | CLV backtest | Confidence adjustment |
| q4_shot_rate, q4_pts_share | PBP | Clutch usage |
| fta_rate_pbp, foul_drawn_rate | PBP | Foul-drawing tendency |
| paint_rate, corner_3_rate | Shot zones | Zone tendency |

**Result:** Props grew from 30 → 57 features. All models retrained.

---

### Phase 5 — External Factors ✅
**Completed:** 2026-03-18

- `injury_monitor.py` — polls RotoWire RSS + NBA official injury report PDF
- `ref_tracker.py` — historical referee tendencies (pace, foul rate, home win%)
- `line_monitor.py` — opening vs closing line, sharp money signal

---

## Active Phase

### Phase 2.5 — CV Tracker Quality Upgrades 🟡
**Goal:** Bring CV tracking accuracy to competitive level before accumulating full games.
**Priority order (ROI):**

| Task | Impact | Status |
|---|---|---|
| 025-01 Broadcast detection mode (conf=0.35) | More detections on broadcast feeds | ✅ Done |
| 025-02 Jersey OCR brightness normalisation | Better jersey reads in varied lighting | ✅ Done |
| 025-03 Broadcast detection tests | Test coverage for above | ✅ Done |
| 025-04 Per-clip court homography module | Fixes ISSUE-017 — wrong 2D coords on broadcast | 🔲 |
| 025-05 Wire court_detector into pipeline | Homography auto-detected per clip | 🔲 |
| 025-06 Court detector tests | Synthetic image tests | 🔲 |
| 025-07 YOLOv8-pose ankle keypoints | Position ±18" → ±4", closes 60% of SS gap | 🔲 HIGH PRIORITY |

**Success criteria:**
1. Position error ≤ ±6 inches on court line validation
2. ID switch rate < 5% on 500-frame test clip
3. 2D coordinates correct on broadcast clips
4. Ball tracked in ≥95% of frames

**⚠️ Phase 6 dependency:** Pose estimation (025-07) and per-clip homography (025-04/05/06) **must complete before Phase 6**. First 20 games need pose data for xFG v2 training.

---

## Upcoming Phases

### Phase 3.5 — Expanded Data Collection
**Goal:** Pull all untapped free data sources and wire into models.

**3.5-A — Untapped nba_api endpoints**
- `PlayerDashPtShots` → contested%, pull-up%, C&S%, avg defender dist
- `BoxScorePlayerTrackV2` → speed, distance, paint touches per game
- Unlocks: 4 new prop features, improves matchup model

**3.5-B — Basketball Reference extension**
- Extend BBRef to 10+ seasons (2014–present)
- Injury history with games missed + return efficiency
- Coaching records, player bio data (height/weight/wingspan)
- Target: +2–3% accuracy across all categories from better calibration

**3.5-C — Betting market scrapers**
- The Odds API — real closing lines (vs current game margin proxy)
- Action Network — public bet% and money% per game/prop
- OddsPortal — historical closing lines 15 years (CLV ground truth)
- DraftKings/FanDuel live props

**Models unlocked:** M19–M28 — defensive effort, screen ROI, play type efficiency, defender zone xFG, age curve, injury recurrence, coaching adjustment, ref tendency extended

---

### Phase 4.5 — Betting Market + Player Lifecycle Models
**Goal:** 12 models requiring betting market data and player availability data.

**Betting Market Models:**
1. Sharp money detector — reverse line movement vs public bet%
2. CLV predictor — will this line improve by closing?
3. Public fade model — when public% > 75% + historical fade ROI
4. Prop correlation matrix — P(A over) given P(B over)
5. SGP optimizer — correlation-adjusted true probability
6. Soft book lag — minutes until DK/FD adjusts after Pinnacle moves

**Player Lifecycle Models:**
1. Load management predictor — P(star rests on B2B), coach-specific
2. Return-from-injury curve — efficiency at game 1/2/3/5/10 post-return
3. Injury risk model — P(injury next 7 days): CV speed decline + B2B history
4. Breakout predictor — sustained usage increase: trend + efficiency + opportunity
5. Contract year effect — last year of deal → historical performance lift
6. Roster opportunity model — who absorbs usage when a star is DNP

---

### Phase 6 — Full Game Processing
**Goal:** Run 20 complete NBA games through the CV pipeline.
**Requires:** Phase 2.5 complete (pose estimation + per-clip homography)

**Deliverables:**
- 20+ full games processed (~6 hrs each on RTX 4060)
- PostgreSQL writes wired (ISSUE-010 resolved)
- Shot enrichment working — CV shots matched to NBA PBP outcomes
- `event_aggregator.py` — per-player-per-game CV events:
  - drives/36, box_out_rate, crash_speed, closeout_speed_allowed
  - cuts/36, screens/36, paint_touches/36, shot_clock_at_shot_avg

---

### Phase 7 — Tier 2–3 ML Models (CV-dependent)
**Requires:** 20 full games processed

**New models (10):**
- xFG v2: adds closeout_speed + shot_clock_decay + fatigue_penalty (Brier target: 0.200)
- Play type classifier: ISO / P&R / spot-up / cut (from CV events)
- Defensive pressure → possession outcome model
- Spacing rating → scoring efficiency model
- Drive → FTA model, box-out rebound model, closeout suppression model
- Prop model retrain with all CV behavioral features

**Accuracy targets:** xFG Brier 0.226 → ~0.200 | Props pts MAE ~0.22 → ~0.18

---

### Phase 8 — Possession Simulator v1
**Goal:** 7-model possession chain, 10,000 Monte Carlo simulations per game.

```
Possession Start
    [1] Play Type → [2] Shot Selector → [3] xFG → [4] TO/Foul
    → [5] Rebound → [6] Fatigue → [7] Substitution
    × 10,000 simulations
    = Full box score distribution per player
```

**Output per run:**
- Full box score distributions (pts/reb/ast/stl/blk/tov for all players)
- Final score + spread margin distribution
- First half total, pace projections
- Prop distributions: mean, std, P25, P75, P90, bust/boom probability

---

### Phase 9 — Feedback Loop + NLP Models
**Goal:** Automate retraining. Every processed game improves every model.

```
Process game → extract CV + enrich with NBA API
    → retrain models (walk-forward)
    → compute predictions → compare vs book
    → store edges → CLV tracking → repeat nightly
```

**NLP models (4):**
- Injury report severity NLP — text → severity score + games-missed estimate
- Injury news lag — time from news to book adjustment (edge window)
- Team chemistry sentiment — beat reporter signal
- Beat reporter credibility scoring

---

### Phase 10 — Tier 4–5 ML Models
**Requires:** 50–100 full games processed

- Fatigue curve — per-player efficiency decay vs cumulative minutes
- Rebound positioning — crash angle + speed → rebound probability
- Lineup chemistry — 5-man unit synergy beyond net rating
- Matchup matrix — full player-vs-player efficiency grid
- Late-game efficiency — clutch factor calibration
- Closeout quality — defender speed → FG% impact
- Help defense frequency — rotation rate per possession
- Ball stagnation — low movement → turnover risk elevation

---

### Phase 11 — Betting Infrastructure
**Goal:** Full betting workflow with CLV tracking.

- The Odds API integration — real-time lines from 20+ books
- Kelly Criterion sizing (fractional Kelly: 0.25–0.50)
- CLV tracking — compare bet price to closing line at kickoff
- Sharp money detector — line movement classifier
- Soft book scanner — DraftKings/FanDuel vs Pinnacle lag
- Daily edge report: ranked list, Kelly sizes, CLV history

---

### Phase 12 — Full Monte Carlo (90 models)
**Requires:** 100+ games, all models trained

**Output per game:**
- Full stat distributions (P10 / P25 / mean / P75 / P90) for every player
- Bust/boom probability per prop
- SGP correlation matrix
- DFS lineup optimizer output

---

### Phase 13 — FastAPI Backend
12 REST endpoints + WebSocket + Redis caching.

```
GET  /predictions/game/{game_id}       Win prob + spread + total
GET  /predictions/props/{player_id}    All 7 prop projections
GET  /predictions/edges                All +EV edges today
GET  /analytics/shot-chart/{player_id} Shot chart + xFG
GET  /analytics/lineup/{team_id}       Lineup net ratings
GET  /data/injuries                    Live injury feed
POST /simulate/{game_id}               Run 10K Monte Carlo
WS   /ws/live/{game_id}               Real-time win probability
```

---

### Phase 14 — Analytics Dashboard
**Stack:** Next.js + TypeScript + D3 + Recharts + TailwindCSS

**10 chart types:**
1. Shot chart — D3 hexbin, zone frequency + efficiency
2. Bar comparison — player vs league average
3. Line trend — rolling stats over time
4. Distribution curve — prop vs 10K simulation
5. Radar chart — multi-metric player profile
6. Court heatmap — zone efficiency
7. Scatter — shot quality vs defender distance
8. Win probability waterfall — possession-by-possession
9. Box plot — prop distribution from simulations
10. Lineup matrix — 5-man net ratings grid

---

### Phase 15 — AI Chat Interface
Claude API with 10 tools + inline chart rendering.

**10 tools:**
1. `get_game_prediction(game_id)` — win prob + spread + total
2. `get_player_props(player_id, stats, date)` — projections vs lines
3. `get_analytics(player_id, metric, filters)` — any of 96 metrics
4. `get_shot_chart(player_id, season, filters)` — shot data
5. `get_lineup_data(team_id, filters)` — lineup net ratings
6. `get_injuries(date)` — current injury report
7. `simulate_game(game_id)` — run Monte Carlo
8. `get_betting_edges(date, min_edge)` — ranked edge list
9. `get_player_similarity(player_id)` — comparable players
10. `render_chart(type, data, config)` — renders chart inline

---

### Phase 16 — Live Win Probability
**Requires:** 200+ full games

- LSTM on possession sequences — hidden state encodes game history
- WebSocket push — win probability updates every possession
- Live prop adjustments based on momentum + fatigue
- Q4 star usage model for crunch-time prediction

**Architecture:**
```
Possession stream → LSTM (hidden dim 256, 3 layers) → win_prob
→ WebSocket → frontend win probability chart updates live
```

---

### Phase 17 — Infrastructure
- Docker containerization (API, dashboard, pipeline workers)
- CI/CD pipeline (GitHub Actions → staging → production)
- Cloud GPU option (A100 for overnight batch processing)
- Model drift monitoring — accuracy decay alerts
- Data quality monitoring — tracking degradation alerts
- PostgreSQL backup + read replica

---

### Phase 18 — Calibration + Scale
- Paper trading → live testing → real capital
- Multi-season model calibration
- Automated nightly game clip download + processing
- Full 82-game regular season + playoffs pipeline
- Production monitoring, alerting, on-call runbook

---

## Accuracy Progression

| Phase | Win Prob | Props MAE (pts) | xFG Brier |
|---|---|---|---|
| 4 — current | 69.1% | 0.308 | 0.226 |
| 4.6 — feature wiring | ~70–71% | ~0.22 | — |
| 7 — CV behavioral | ~72–73% | ~0.18 | ~0.200 |
| 10 — 50–100 games | ~74–76% | ~0.15 | ~0.185 |
| 16 — full stack, 200+ games | ~76–78% | ~0.12 | ~0.175 |

## Data Volume Milestones

| Games Processed | Models Unlocked |
|---|---|
| 20 (Phase 6) | xFG v2, play type, shot enrichment |
| 50 (Phase 10) | Fatigue curve, lineup chemistry |
| 100 (Phase 10) | Full Tier 4–5 model stack |
| 200+ (Phase 16) | LSTM live win probability |
