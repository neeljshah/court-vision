# Development Roadmap — NBA AI Basketball System

This document describes the 18-phase build plan for the complete system. Each phase has a clear goal, dependencies, and expected outcomes.

**Vision:** A self-improving possession-by-possession Monte Carlo game simulator — 100 ML models, 10,000 simulations per game — producing stat distributions compared to sportsbook lines, accessible via conversational AI that renders charts inline.

---

## Current Status

| Layer | Status |
|-------|--------|
| CV Tracking Pipeline | ✅ Operational (5.7 fps, Phase 2 complete) |
| Data Collection | ✅ Complete (25+ sources, 3 seasons, Phase 3 complete) |
| Tier 1 ML Models | ✅ 18 models trained (Phase 4 complete) |
| Live Data Feeds | ✅ Injury / refs / lines wired (Phase 5 complete) |
| CV Quality Upgrades | 🟡 Active (Phase 2.5) |
| Feature Wiring | 🔲 Next (Phase 4.6) |

---

## Phase Overview

| Phase | Name | Status | Key Deliverable |
|-------|------|--------|----------------|
| 1 | Data Infrastructure | ✅ | PostgreSQL schema, schedule context, lineup data |
| 2 | Tracker Bug Fixes | ✅ | Team color re-ID, EventDetector, 431 tests |
| 2.5 | CV Quality Upgrades | 🟡 | Pose estimation, ByteTrack, per-clip homography |
| 3 | NBA Data Collection | ✅ | 622 gamelogs, 221K shots, 98.4% PBP |
| 4 | Tier 1 ML Models | ✅ | Win prob (67.7%), 7 props, 5 game models |
| 4.6 | Feature Wiring | 🔲 | 22 new features → retrain all models, +5-8% accuracy |
| 5 | External Factors | ✅ | Injury monitor, ref tracker, line monitor |
| 6 | Full Game Processing | 🔲 | 20 full games → PostgreSQL → shots enriched |
| 7 | Tier 2-3 ML Models | 🔲 | xFG v2, play type, CV behavioral features |
| 8 | Possession Simulator v1 | 🔲 | 7-model chain, 10K Monte Carlo |
| 9 | Feedback Loop | 🔲 | Nightly retrain → continuous improvement |
| 10 | Tier 4-5 ML Models | 🔲 | Fatigue, lineup chemistry, matchup matrix |
| 11 | Betting Infrastructure | 🔲 | Odds API, Kelly, CLV pipeline |
| 12 | Full Monte Carlo | 🔲 | All 50 models, complete stat distributions |
| 13 | FastAPI Backend | 🔲 | 12 endpoints, Redis, WebSocket |
| 14 | Analytics Dashboard | 🔲 | Next.js, D3 shot charts, 10 chart types |
| 15 | AI Chat Interface | 🔲 | Claude API + 10 tools + render_chart inline |
| 16 | Live Win Probability | 🔲 | 200+ games, LSTM, real-time WebSocket |
| 17 | Infrastructure | 🔲 | Docker, CI/CD, cloud GPU, monitoring |
| 18 | Calibration + Scale | 🔲 | Full season automation, production monitoring |

---

## Phase Detail

### Phase 2.5 — CV Quality Upgrades (Active)

**Goal:** Bring CV tracking accuracy to competitive level before accumulating full games.

| Task | Impact | Effort |
|------|--------|--------|
| Pose estimation — YOLOv8-pose ankle keypoints | Position accuracy ±15" → ±6-8" | 3 days |
| ByteTrack replacement — ID switch rate 15% → 3% | Identity continuity | 2 days |
| YOLOv8x upgrade — detection 87% → 94% | Fewer missed players | 1 day |
| Per-clip court homography — auto-detect per broadcast angle | Fixes ISSUE-017 | 2 days |

**After Phase 2.5:** Position ±6-8 inches, xFG ~64%, ID switches ~3%. vs. Second Spectrum: ±3", ~68%, <1%.

---

### Phase 4.6 — Feature Wiring (Next)

**Goal:** Wire 22 already-collected but unwired features into all models. Zero new data collection required. Immediate accuracy improvements.

**New features for player props (30 → 52 features):**

| Feature | Source | Expected Impact |
|---------|--------|----------------|
| VORP | BBRef | +0.02 R² pts model |
| WS/48 | BBRef | +0.02 R² |
| Hustle deflections/game | NBA Hustle | +0.01 R² |
| On/off net rating | On/Off splits | +0.01-0.02 R² |
| Synergy pts/poss by play type | Synergy | +0.02 R² |
| cap_hit_pct | Contracts | Contract year signal |
| rest_days | Schedule | Travel/rest impact |
| travel_miles | Schedule | Fatigue proxy |
| games_in_last_14 | Schedule | Load management |
| ref_fta_tendency | Ref Tracker | FTA prop edge |
| ref_pace_tendency | Ref Tracker | Pace/total impact |
| defender_zone_fg_allowed | NBA Tracking | Matchup context |
| matchup_fg_allowed | Matchup data | Direct matchup |
| contested_shot_pct | Shot Dashboard | Shot difficulty |
| pull_up_pct | Shot Dashboard | Shot creation |
| catch_and_shoot_pct | Shot Dashboard | Role definition |
| avg_defender_dist | Shot Dashboard | Open look rate |
| shot_zone_tendency_entropy | Shot Tendency | Zone variance |
| shot_clock_pressure_score | Shot Quality | Pressure scoring |
| fatigue_penalty | Shot Quality | Minutes-adjusted eff |
| momentum_shift_flag | Momentum | Game state |
| scoring_run_length | Momentum | Momentum context |

**Expected accuracy gains:**
- Points MAE: 0.32 → ~0.22
- Rebounds MAE: 0.11 → ~0.07
- Assists MAE: 0.09 → ~0.06
- Win probability: 67.7% → ~70-71%

---

### Phase 6 — Full Game Processing

**Goal:** Run 20 complete NBA games through the CV pipeline. Wire PostgreSQL writes. Enrich tracked shots with NBA PBP outcomes.

**Deliverables:**
- 20+ full games processed (each ~6 hours on RTX 4060)
- PostgreSQL writes wired (ISSUE-010 resolved)
- Shot enrichment working — matched CV shots to NBA PBP (ISSUE-009 resolved)
- `event_aggregator.py` built — aggregate EventDetector.events per player per game:
  - drives_per_36, box_out_rate, crash_speed
  - closeout_speed_allowed, cuts_per_36, screens_per_36
  - paint_touches_per_36, off_ball_distance_per_36
  - shot_clock_at_shot_avg

---

### Phase 7 — Tier 2-3 ML Models

**Goal:** Train CV-behavioral models using data from Phase 6.

**New models (10):**
- xFG v2: adds closeout_speed + shot_clock_decay + fatigue_penalty (Brier target: 0.200)
- Play type classifier: isolation / P&R / spot-up / cut (from CV events)
- Defensive pressure model: pressure_score → possession outcome
- Spacing rating model: convex hull spacing → scoring efficiency
- Drive → FTA model
- Box-out rebound model
- Closeout suppression model
- Prop model retrains with all CV behavioral features

**Expected accuracy:**
- xFG: Brier 0.226 → ~0.200
- Props (pts): MAE ~0.22 → ~0.18 with CV features
- Win probability: ~70% → ~72-73% with full CV feature set

---

### Phase 8 — Possession Simulator v1

**Goal:** Implement the 7-model possession chain, run 10,000 Monte Carlo simulations per game.

**Simulator architecture:**
```
Possession Start
    [1] Play Type → [2] Shot Selector → [3] xFG → [4] TO/Foul
    → [5] Rebound → [6] Fatigue → [7] Substitution
× 10,000 simulations → full stat distributions per player
```

**Output per simulation run:**
- Full box score (pts/reb/ast/stl/blk/tov for all players)
- Final score + spread margin
- First half total, pace
- Player prop distributions: mean, std, P25, P75, P90, bust/boom probability

---

### Phase 9 — Feedback Loop

**Goal:** Automate the process of turning each game into training data and improving all models.

```
Process game → extract CV features + enrich with NBA API
    → retrain models (walk-forward) → compute new predictions
    → compare vs book lines → store edges → repeat nightly
```

The system becomes genuinely self-improving. Every game processed makes every model slightly better.

---

### Phase 10 — Tier 4-5 ML Models

**Requires:** 50-100 full games processed

**Models:**
- Fatigue curve — per-player efficiency decay vs. minutes
- Rebound positioning — crash angle → rebound probability
- Lineup chemistry — 5-man unit synergy beyond net rating
- Matchup matrix — full player vs. player efficiency grid
- Late-game efficiency — clutch factor calibration
- Closeout quality — defender closeout speed → FG% impact
- Help defense frequency — help rotations per possession
- Ball stagnation — low ball movement → turnover risk

---

### Phase 11 — Betting Infrastructure

**Goal:** Full betting workflow with position sizing and CLV tracking.

**Components:**
- The Odds API integration — real-time lines from 20+ books
- Kelly Criterion position sizing (fractional Kelly: 0.25-0.50)
- CLV tracking — compare bet price to closing line
- Sharp money detector — line movement classifier
- Soft book opportunity scanner (DraftKings/FanDuel vs Pinnacle/BetRivers)
- Daily edge report generation

---

### Phase 12 — Full Monte Carlo

**Requires:** 100+ games, all 50 models trained

**Output per game:**
- Full stat distributions for every player (P10/P25/mean/P75/P90)
- Bust/boom probability per prop
- SGP correlation matrix
- Lineup optimizer for DFS

---

### Phase 13 — FastAPI Backend

12 REST endpoints + WebSocket + Redis caching layer.

```
GET  /predictions/game/{game_id}      Win prob + spread + total
GET  /predictions/props/{player_id}   All 7 prop projections
GET  /predictions/edges               All +EV edges today
GET  /analytics/shot-chart/{player_id}
GET  /analytics/lineup/{team_id}
GET  /data/injuries                   Live injury feed
POST /simulate/{game_id}              Run 10K Monte Carlo
WS   /ws/live/{game_id}              Real-time win probability
```

---

### Phase 14 — Analytics Dashboard

**Stack:** Next.js + TypeScript + D3 + Recharts + TailwindCSS

**10 chart types:**
1. Shot chart (D3 hexbin — zone frequency + efficiency)
2. Bar comparison (player vs. league average)
3. Line trend (rolling stats over time)
4. Distribution curve (prop vs. simulation)
5. Radar chart (multi-metric player profile)
6. Court heatmap (zone efficiency)
7. Scatter (shot quality vs. defender distance)
8. Win probability waterfall
9. Box plot (prop from 10K sims)
10. Lineup matrix (5-man net ratings)

---

### Phase 15 — AI Chat Interface

Claude API with 10 tools + inline chart rendering.

```
User: "How does Tatum perform vs zone defense and what's his best prop tonight?"

Claude calls:
  1. get_analytics("Tatum", "shot_quality", {"defense_type": "zone"})
  2. get_player_props("Tatum", ["pts", "ast", "3pm"], today)
  3. render_chart("scatter", tatum_zone_data, ...)
  4. render_chart("distribution", tatum_pts_dist, ...)

Frontend renders both charts inline in chat conversation.
```

---

### Phase 16 — Live Win Probability

**Requires:** 200+ full games, LSTM architecture

- LSTM on possession sequences — hidden state encodes game history
- WebSocket push — win probability updates every possession
- Live prop adjustments based on momentum + fatigue
- Q4 star usage model for crunch-time prediction

---

### Phase 17 — Infrastructure

- Docker containerization (API, dashboard, pipeline workers)
- CI/CD pipeline (GitHub Actions → staging → production)
- Cloud GPU option (A100 for overnight batch processing)
- Model drift monitoring — accuracy decay alerts
- Data quality monitoring — tracking quality degradation alerts
- PostgreSQL backup + read replica

---

### Phase 18 — Calibration + Scale

- Betting automation (paper trading first → live testing → real capital)
- Multi-season model calibration
- Automated nightly game clip download + processing
- Full 82-game regular season + playoffs pipeline
- Production monitoring + alerting + on-call runbook

---

## Accuracy Progression Targets

| Phase | Win Prob | Props (pts MAE) | xFG Brier |
|-------|----------|-----------------|-----------|
| 4 (current) | 67.7% | 0.32 | 0.226 |
| 4.6 | ~70-71% | ~0.22 | — |
| 7 | 72-73% | ~0.18 | ~0.200 |
| 10+ | 74-76% | ~0.15 | ~0.185 |
| 16+ (full stack) | 76-78% | ~0.12 | ~0.175 |

---

## Data Volume Milestones

| Games Processed | Models Unlocked |
|-----------------|-----------------|
| 20 (Phase 6) | xFG v2, play type, shot enrichment |
| 50 (Phase 10) | Fatigue, lineup chemistry |
| 100 (Phase 10) | Full Tier 4-5 stack |
| 200+ (Phase 16) | LSTM live win probability |

---

## Competitive Position

| Feature | This System | Second Spectrum | Public Tools |
|---------|-------------|-----------------|-------------|
| CV tracking from broadcast | ✅ | ✅ (proprietary) | ❌ |
| Spatial features | ✅ | ✅ | ❌ |
| ML prop prediction | ✅ | ❌ | Partial |
| Monte Carlo simulator | 🔲 Phase 8 | ❌ | ❌ |
| Betting edge detection | 🔲 Phase 11 | ❌ | Partial |
| AI chat with inline charts | 🔲 Phase 15 | ❌ | ❌ |
| Cost | Free (self-built) | $1M+/year | Free/cheap |

The moat: spatial CV signals (defender distance, spacing, closeout speed, drive frequency) that no public data source exposes. Every additional game processed widens this gap.
