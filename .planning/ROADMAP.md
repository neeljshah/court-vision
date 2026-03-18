# Roadmap: NBA AI System

## Vision

Build the world's best NBA analytics and prediction system — a self-improving feedback loop combining computer vision tracking, exhaustive NBA API data, external context, and 50 ML models to simulate games possession-by-possession, surface betting edges, and deliver professional-grade analytics through a conversational AI interface.

**End Products:**
1. **Betting Dashboard** — model predictions vs live lines, Kelly-sized edge alerts, prop value finder
2. **Analytics Dashboard** — 96 metrics, interactive shot charts, court heatmaps, lineup matrices, win probability timelines
3. **AI Chat** — "Give me Jamal Murray's shot quality vs guards and his prop value tonight" → Claude calls tools, renders charts inline, synthesizes insight

**The Moat:** Possession-by-possession Monte Carlo simulator trained on CV spatial data (defender distance, spacing, fatigue, play type) that no public tool has. Self-improves with every game processed.

---

## Phase Overview

| Phase | Status | Goal |
|---|---|---|
| Phase 1 — Data Infrastructure | ✅ Done | PostgreSQL, schedule context, lineup data, NBA stats |
| Phase 2 — Tracker Bug Fixes | ✅ Done | Team color, event detector, test suite |
| Phase 2.5 — CV Tracker Upgrades | 🟡 Active | Pose estimation, ByteTrack, per-clip homography |
| Phase 3 — NBA API Data Maximization | ✅ Done | 568/569 gamelogs, 221K shots, 3,102 PBP games |
| Phase 3.5 — Expanded Data Collection | 🔲 | BBRef + untapped nba_api + betting market + news |
| Phase 4 — Tier 1 ML Models | ✅ Done | 13 models trained: win prob + all props + game models |
| Phase 4.5 — Betting + Lifecycle Models | 🔲 | Sharp detector, CLV, correlation matrix, DNP predictor |
| Phase 5 — External Factors | ✅ Done | Injury monitor, ref tracker, line monitor wired |
| Phase 6 — Full Game Processing | 🔲 | 20+ full games, PostgreSQL wired, shots enriched |
| Phase 7 — Tier 2-3 ML Models | 🔲 | xFG v2 (CV), play type, defensive pressure, spacing |
| Phase 8 — Possession Simulator v1 | 🔲 | 7-model chain, 10K Monte Carlo |
| Phase 9 — Feedback Loop + NLP | 🔲 | Nightly processing, auto-retrain, NLP injury models |
| Phase 10 — Tier 4-5 ML Models | 🔲 | Fatigue curve, lineup chemistry, matchup matrix |
| Phase 10.5 — Advanced CV Signals | 🔲 | Coverage type, shot arc, biomechanics, audio |
| Phase 11 — Betting Infrastructure + Live | 🔲 | Live models, CLV backtesting, Kelly+correlation |
| Phase 12 — Full Monte Carlo (90 models) | 🔲 | All 90 models in simulator, full stat distributions |
| Phase 13 — FastAPI Backend | 🔲 | 12 endpoints, Redis caching, async |
| Phase 14 — Analytics Dashboard | 🔲 | Next.js + D3 shot charts + 10 chart types |
| Phase 15 — AI Chat Interface | 🔲 | Claude API + tool use + render_chart inline |
| Phase 16 — Tier 6 + Live Win Prob | 🔲 | 200+ games, LSTM, WebSocket real-time |
| Phase 17 — Infrastructure | 🔲 | Docker, CI/CD, cloud GPU, drift monitoring |

---

## Phase Details

### Phase 1: Data Infrastructure ✅
**Status**: COMPLETE 2026-03-12
- PostgreSQL schema (9 tables, 2 views)
- schedule_context.py — rest days, back-to-back, travel distance
- lineup_data.py — 5-man units, on/off splits
- nba_stats.py — opponent features
- db.py — connection helper

---

### Phase 2: Critical Tracker Bug Fixes ✅
**Status**: COMPLETE 2026-03-17
- Dynamic KMeans team color separation (warm-up 30 frames → calibrate → recalibrate every 150)
- Ball position fallback using possessor 2D coords → EventDetector fires
- Frozen player eviction (_freeze_age after 20 consecutive frozen frames)
- Mean HSV replaces per-crop KMeans → 2fps → ~15fps
- SIFT_INTERVAL=15, SIFT_SCALE=0.5 downscale → 44s → ~4s SIFT overhead
- 431 tests passing

---

### Phase 2.5: CV Tracker Quality Upgrades
**Goal**: Close the data quality gap with Second Spectrum from software alone. No new hardware.
**Depends on**: Phase 2
**Priority order by ROI:**

**2.5-01 — Pose Estimation (HIGHEST ROI)**
- Replace bbox bottom edge with YOLOv8-pose or ViTPose ankle keypoints
- Position error: ±18 inches → ±4 inches (closes 60% of SS gap)
- Court coordinate accuracy dramatically improves
- Time: 3 days

**2.5-02 — Per-Clip Homography (ISSUE-017)**
- Auto-detect court lines per broadcast clip
- Build M1 from line intersections, not pano_enhanced
- 2D coordinates currently systematically wrong for all broadcast clips
- Time: 1 week

**2.5-03 — ByteTrack or StrongSORT**
- Replace custom Kalman+Hungarian with ByteTrack
- Uses low-confidence detections to maintain tracks through occlusions
- ID switch rate: ~15% → ~3%
- Time: 3 days

**2.5-04 — Optical Flow Between Detections**
- Lucas-Kanade flow between detection frames
- Speed accuracy: ±1-2 mph → ±0.4 mph
- Smoother position continuity on fast cuts
- Time: 2 days

**2.5-05 — YOLOv8x Detection Model**
- Upgrade nano → extra large
- Detection accuracy: 87% → 94%
- Post-game processing only (3x slower acceptable)
- Time: 1 day

**2.5-06 — OSNet Deep Re-ID**
- Replace 96-dim HSV histogram with deep learned re-ID
- Fine-tune on NBA jersey crops
- ID confusion on similar uniforms: eliminated
- Time: 1 week

**2.5-07 — Ball Arc + Height Estimation**
- Fit parabola to tracked ball trajectory
- Estimate shot arc from broadcast angle
- Closes the "unbridgeable" ball height gap partially
- Requires consistent ball tracking (95%+ frames) first
- Time: 1 week

**2.5-08 — Player Height Prior for Depth Estimation**
- Use known NBA heights as prior for depth from single camera
- Murray = 6'4" → scale bbox → estimate z-depth
- Partial 3D reconstruction from 2D feed
- Time: 1 week

**Success Criteria:**
1. Position error measured ≤ ±6 inches via court line validation
2. ID switch rate < 5% on 500-frame test clip
3. 2D court coordinates geographically accurate on broadcast clips
4. Ball tracked in ≥95% of frames

**Plans:** 6 plans
Plans:
- [x] 025-01-PLAN.md — Broadcast detection mode (conf threshold 0.35)
- [x] 025-02-PLAN.md — Jersey OCR brightness normalisation + 2x resize
- [x] 025-03-PLAN.md — Tests for broadcast detection + jersey OCR
- [ ] 025-04-PLAN.md — court_detector.py per-clip homography module
- [ ] 025-05-PLAN.md — Wire detect_court_homography into unified_pipeline
- [ ] 025-06-PLAN.md — Tests for court_detector (synthetic images)

---

### Phase 3: NBA API Data Maximization
**Goal**: Exhaust every NBA API endpoint. No video needed. Unlocks Tier 1-2 models.
**Status**: ✅ COMPLETE 2026-03-17 — 568/569 gamelogs, 221,866 shots, 3,102 PBP games
**Depends on**: Phase 1

**Remaining work:**
- [ ] Finish gamelog scrape — 209 players remaining (`--loop --max 569`)
- [ ] ShotChartDetail — 50K+ shots with coordinates, made/missed, context (ISSUE-019)
- [ ] Play-by-play — 1,223 games unscraped (ISSUE-018)
- [ ] Lineup on/off splits — all 30 teams × 3 seasons
- [ ] Referee assignments + historical tendencies
- [ ] Retrain win probability model with sklearn 1.7.2 (ISSUE-016)

**Success Criteria:**
1. 569/569 gamelogs with last-5/10/15/20 splits
2. ≥50,000 shots with court_x, court_y, made/missed, shot_type, zone, game_clock
3. PBP for all 1,225+ games indexed in pbp_index.json
4. 5-man lineup net_rtg/off_rtg/def_rtg for all 30 teams × 3 seasons
5. Referee features available for prediction inputs

---

### Phase 3.5: Expanded Data Collection
**Goal**: Pull all untapped free data sources. No video needed. Unlocks 10 additional models immediately.
**Depends on**: Phase 3
**Status**: 🔲

**3.5-A — Untapped nba_api Endpoints (1-2 days)**
- `BoxScorePlayerTrackV2` → speed (mph), distance (mi), touches, paint touches per game
- `PlayerDashPtShots` → contested%, C+S%, pull-up%, touch time, dribbles before shot
- `LeagueDashPtDefend` → FG% allowed by zone per defender
- `MatchupsRollup` → who guards whom, time, pts/100
- `LeagueHustleStatsPlayer` → deflections, screen assists, contested shots, loose balls
- `SynergyPlayTypes` → pts/possession by play type (ISO/PnR/Post/C+S/Cut/Transition) — GROUND TRUTH for play type classifier
- `LeaguePlayerOnDetails` → net rtg with player on vs off
- `VideoEvents` → free labeled video clips for CV play type classifier training

**3.5-B — Basketball Reference Scraper (3 days)**
- BPM / VORP / Win Shares — advanced impact metrics not in nba_api
- Historical game availability per player (injury log)
- Coaching records: wins/losses, tenure, system tendencies
- Player contracts: salary, years remaining (contract year motivation)
- Transactions: every trade/signing/waiver date (chemistry disruption clock)
- Draft history + college stats (player development curves)
- Arena altitude (Denver/Utah elevated — quantifiable fatigue effect)
- Historical Vegas lines ~2008+ (CLV backtesting without paid data)

**3.5-C — Betting Market Scrapers (1-2 days)**
- Action Network: public bet% + money% per game/prop → sharp vs public signal
- OddsPortal: historical closing lines 15 years → CLV backtesting ground truth
- Pinnacle: sharpest opening lines → steam detection, market benchmark
- DraftKings/FanDuel: current player props → soft book lag detection

**3.5-D — Expanded News/Injury Pipeline (1 day)**
- NBA official injury report PDF (~5pm ET daily) → faster than ESPN by 30-60min
- RotoWire RSS feed (feedparser) → injury/lineup news
- Reddit r/nba API (praw package) → injury threads, lineup news, sentiment
- HoopsHype/Spotrac scraper → contracts, cap data, transaction history

**3.5-E — Context Data (2 hours)**
- Arena altitude lookup table (static)
- TimeZoneDB API (free) → timezone shift per road trip
- Travel distance calculator (arena coordinates)

**Models Unlocked by 3.5:**
M19-M28: defensive effort, ball movement quality, screen ROI, touch dependency, play type efficiency (Synergy), defender zone xFG, age curve, injury recurrence, coaching adjustment, ref tendency extended

**Success Criteria:**
1. All nba_api tracking/hustle/synergy endpoints pulled and cached
2. BBRef scraper producing BPM/injury history/coaching records for all active players
3. Action Network public %s available for all games
4. OddsPortal historical lines for 3 seasons available for CLV backtesting
5. Official injury PDF being parsed within 5 minutes of publication

---

### Phase 4: Tier 1 ML Models (NBA API Only)
**Goal**: Train all 13 models that need only NBA API data. No CV required.
**Status**: ✅ COMPLETE 2026-03-17
**Depends on**: Phase 3

**Models to train:**
1. Win probability (XGBoost, 27 features) — retrain with sklearn 1.7.2
2. Game total over/under
3. Spread / point differential
4. Player points prop (per player, rolling features)
5. Player rebounds prop
6. Player assists prop
7. Player minutes prop
8. Player 3PM prop
9. Player efficiency (TS%, eFG%)
10. Lineup net rating predictor
11. Blowout probability
12. First half total
13. Team pace predictor

**Success Criteria:**
1. Win prob Brier score < 0.22, walk-forward backtest complete
2. Props RMSE < 15% of league average per stat
3. Shot quality v1 AUC > 0.65 (NBA API location only)
4. All models saved to data/models/ with SHAP importance
5. Backtesting: CLV proxy, Brier score, ROI at 3 edge thresholds

---

### Phase 4.5: Betting Market Models + Player Lifecycle Models
**Goal**: Build the 12 models that require betting market data and player availability data. No CV needed.
**Depends on**: Phase 3.5 (betting market scrapers + BBRef injuries)
**Status**: 🔲

**Betting Market Models (M29-M34):**
1. **Sharp money detector** — reverse line movement: line moves against public bet% = sharp action
2. **CLV predictor** — will this line improve by closing? (opening vs current vs Pinnacle historical close)
3. **Public fade model** — when public% > 75% one side + historical fade ROI → fade signal
4. **Prop correlation matrix** — P(A over) given P(B over): 3-season joint gamelog distributions
5. **Same-game parlay optimizer** — correlation-adjusted true probability vs book's independence assumption
6. **Soft book lag model** — minutes until DraftKings/FanDuel adjusts after Pinnacle moves (time-based edge)

**Player Lifecycle Models (M35-M40):**
1. **DNP predictor** — P(player sits tonight): coach B2B history × player workload × schedule × team record
2. **Load management predictor** — P(star rests on B2B): coach-specific patterns
3. **Return-from-injury curve** — efficiency at game 1/2/3/5/10 post-return by injury type
4. **Injury risk model** — P(injury next 7 days): CV speed decline + B2Bs + historical pattern
5. **Breakout predictor** — sustained usage increase signal: trend + efficiency + roster opportunity
6. **Contract year model** — last year of deal: historical performance lift, quantified per position

**Success Criteria:**
1. Prop correlation matrix covers all 569-player pair combinations
2. DNP predictor backtests at > 75% accuracy on historical data
3. CLV predictor identifies +2% CLV edges on validation set
4. Return-from-injury curve has enough historical samples per injury type (≥30)

---

### Phase 5: External Factors Scraper
**Goal**: Injury status, referee tendencies, line movement — systematically underpriced by books.
**Depends on**: Phase 1

1. injury_monitor.py — poll NBA official + Rotowire every 30 min
2. ref_tracker.py — daily assignments + historical pace/foul/home-win%
3. line_monitor.py — The Odds API, opening vs closing, sharp money signal
4. news_scraper.py — ESPN headline keyword monitor

**Success Criteria:**
1. All external features as columns in model inputs
2. Model accuracy delta measured with/without (+1-2% expected on props)

---

### Phase 6: Full Game Video Processing
**Goal**: 20+ complete 48-minute broadcast games, PostgreSQL wired, shots enriched with outcomes.
**Depends on**: Phase 2.5 (tracker quality), Phase 1 (PostgreSQL)

**Critical tasks:**
- Wire PostgreSQL writes (ISSUE-018) — every run currently overwrites tracking_data.csv
- Run 20+ games with --game-id flags so shots get outcomes
- Per-game M1 homography from Phase 2.5 must be working first

**Success Criteria:**
1. 20+ full games processed end-to-end
2. ≥200 shots with outcome + court coordinates + defender distance
3. ≥500 possessions labeled with result
4. All outputs in PostgreSQL — no CSV overwrites
5. Both teams labeled correctly in all outputs
6. ≥70% of players identified via OCR + roster lookup

---

### Phase 7: Tier 2-3 ML Models (20 Games)
**Goal**: Add CV spatial context to base models. First models that beat public analytics.
**Depends on**: Phases 4, 6

**Tier 2 — Shot Charts + NBA API (5 models):**
1. xFG v1 — location only (court_x, court_y, shot_type, distance)
2. Shot zone tendency per player
3. Shot volume by zone
4. Clutch efficiency model
5. Shot creation classifier (catch-and-shoot vs off-dribble)

**Tier 3 — CV Data (10 models):**
1. xFG v2 — location + defender_distance + shooter_velocity + pressure
2. Shot selection quality (good/bad decision)
3. Play type classifier — ISO/PnR/Post/C+S/Transition (from CV sequences)
4. Defensive pressure score per possession
5. Spacing rating per lineup
6. Drive frequency predictor
7. Open shot rate model
8. Transition frequency model
9. Off-ball movement score
10. Possession value model (expected pts per possession)

**Success Criteria:**
1. xFG v2 AUC > 0.70 (improvement over v1 at 0.65)
2. Play type classifier accuracy > 80%
3. Defender distance as significant feature in xFG (SHAP confirms)

---

### Phase 8: Possession Simulator v1
**Goal**: Chain the 7 core models into a possession-level game simulator. The central piece everything else plugs into.
**Depends on**: Phase 7

**7 chained models:**
1. Play Type Selector — given lineup + game state → play type distribution
2. Shot Selector — given play type → who shoots + from where
3. xFG Model — given shooter + location + defender → P(make)
4. Turnover/Foul Model — P(shot) / P(TO) / P(foul) per possession
5. Rebound Model — who gets rebound given positions at shot
6. Fatigue Model — efficiency multiplier from distance run + minutes
7. Lineup Substitution Model — when/who subs based on foul + fatigue + score

**Simulator output (per game, 10,000 simulations):**
```python
{
  "win_probability": {"team_a": 0.61, "team_b": 0.39},
  "score_distribution": {"mean": [114.2, 109.8], "std": [8.1, 7.9]},
  "player_stats": {
    "Jamal Murray": {
      "pts": {"mean": 24.3, "p_over_22.5": 0.61},
      "reb": {"mean": 4.1, "p_over_4.5": 0.44},
      "ast": {"mean": 5.8, "p_over_5.5": 0.54}
    }
  }
}
```

**Success Criteria:**
1. Simulator runs 10,000 game simulations in < 30 seconds
2. Win probability calibrated — Brier score < 0.22 on holdout
3. Simulated stat distributions match actual game distributions
4. Prop over/under probabilities within 5% of model accuracy

---

### Phase 9: Automated Feedback Loop + NLP Models
**Goal**: Every game processed automatically improves every model. The system gets better without manual work. Add NLP models for injury and sentiment signals.
**Depends on**: Phase 6, Phase 8

**Feedback Loop Pipeline:**
```
New game detected → download clip → process with tracker →
enrich with NBA API game-id → label possessions →
update training data → retrain affected models →
run simulator on tomorrow's games → flag edges
```

**NLP Models (M66-M69) — add in this phase:**
1. **Injury report severity NLP (M66)** — BERT classifier on injury report text: "questionable (ankle)" → severity score. Feeds DNP predictor.
2. **Injury news lag model (M67)** — timestamp: beat reporter tweet → Pinnacle line move → book adjustment. Quantifies your reaction window.
3. **Team chemistry sentiment (M68)** — rolling sentiment on post-game interviews + Reddit r/nba thread sentiment. Detects morale shifts.
4. **Beat reporter credibility ranker (M69)** — historical accuracy of each reporter's injury news vs official timeline. Weight their signals by track record.

**Data sources needed for NLP:** Reddit r/nba (praw), RotoWire RSS, official injury PDF (all in Phase 3.5)

**Success Criteria:**
1. Nightly cron detects new clips, queues processing
2. Model retraining triggers automatically at data milestones
3. Dataset versioned — every output tagged with tracker_version + date
4. CLI dashboard: games processed, shots labeled, model accuracy trend
5. Feedback loop closes: game outcome → model update → next prediction
6. Injury NLP classifier achieves >80% severity accuracy on holdout
7. Injury lag model identifies 15-60 min window consistently

---

### Phase 10: Tier 4-5 ML Models (50-100 Games)
**Goal**: The models that require volume to train. Lineup chemistry and fatigue are the biggest edge unlocks.
**Depends on**: Phase 9 (enough games processed)

**Tier 4 — 50 Games:**
1. Rebound positioning model (proximity at shot)
2. Fatigue curve per player (distance run → efficiency decay)
3. Late-game efficiency model (4Q vs full game)
4. Closeout quality score
5. Help defense frequency
6. Ball stagnation score
7. Screen effectiveness (pts created per screen)
8. Turnover under pressure model

**Tier 5 — 100 Games:**
1. Lineup chemistry model (5-man spatial fit → net_rtg)
2. Defensive matchup matrix (player A vs player B efficiency)
3. Substitution timing model
4. Momentum model (run probability from sequence)
5. Foul drawing rate model
6. Second chance points model
7. Pace per lineup model

**Success Criteria:**
1. Fatigue curve shows statistically significant efficiency decay
2. Lineup chemistry R² > 0.50 on holdout
3. Matchup matrix covers 80%+ of regular lineup combinations

---

### Phase 10.5: Advanced CV Signal Extraction
**Goal**: Extract the remaining high-value CV signals from broadcast video. These feed the Tier 4-5 models and close the gap with Second Spectrum.
**Depends on**: Phase 10 (enough games for training)
**Status**: 🔲

**10.5-A — Defensive Scheme Recognition**
- Pick-and-roll coverage classifier: drop / hedge / switch / ICE / blitz — from help defender movement when screen is set
- Zone vs man detection — from off-ball defender positioning patterns
- Double team detection — two defenders converging on one player
- Help rotation angle — degrees/frame of nearest off-ball defender closing on drive

**10.5-B — Ball Trajectory**
- Shot arc — fit parabola to ball tracked positions in air (→ low arc = lower make rate)
- Release speed — distance / frames from last possession contact to airborne
- Pass speed — ball distance / frames in air between passer and receiver
- Dribble rhythm — time between ball-ground contacts (changes under pressure)

**10.5-C — Player Biomechanics (Injury + Fatigue)**
- Movement asymmetry — left vs right leg favor across 50+ frames per possession (sub-clinical injury signal)
- Speed vs season baseline — is player 20% slower than their normal? Real-time fatigue before box score shows it
- Jump frequency — how often player leaves ground per possession. Declines measurably in Q4 B2B

**10.5-D — Audio Signals**
- Crowd noise level — audio RMS amplitude per possession → momentum swing proxy
- Announcer keyword detection — speech-to-text: "AND ONE", "FLAGRANT", "TIMEOUT", "TECHNICAL" → faster event labeling

**Models Unlocked:**
- Shot arc quality model (does this player's arc predict makes better than zone alone?)
- Crowd momentum model (does crowd noise predict next possession outcome?)
- Injury risk model update (M38) — CV asymmetry + speed decline as inputs
- Coverage type classifier → feeds Play Type Selector (M43) in simulator

**Success Criteria:**
1. Coverage type classifier accuracy > 80% on labeled test set
2. Shot arc extraction working on ≥90% of tracked shot trajectories
3. Movement asymmetry flags correlate with subsequent injury reports
4. Audio events match video events within 2-frame tolerance

---

### Phase 11: Betting Infrastructure + Live Models
**Goal**: Turn simulator output into actionable, sized bets. Add live in-game models.
**Depends on**: Phase 8 (simulator), Phase 5 (live lines), Phase 3.5 (market data)

**Betting Infrastructure:**
- The Odds API integration — spread, ML, totals, player props (already built)
- betting_edge.py — edge = model_prob − implied_prob, star ratings 1-3★
- Kelly criterion bet sizing: fractional Kelly + correlation adjustment (M32 prop correlation)
- CLV backtesting — edge retention vs OddsPortal closing lines
- Sharp money integration — Action Network public% + Pinnacle line movement
- Historical edge log for drift detection
- Book limit tracker — flag accounts getting limited

**Live In-Game Models (M70-M75) — build in this phase:**
1. **Live prop updater (M70)** — Bayesian update: pre-game sim prior + halftime box score → full game projection. Exploits book's slow live prop adjustment
2. **Comeback probability (M71)** — P(team trailing by X with Y minutes recovers) → live spread edge
3. **Garbage time predictor (M72)** — P(game decided, starters pulled in Q4) → kills prop bets when game is a blowout. Don't count garbage time stats
4. **Foul trouble model (M73)** — Markov chain: P(player fouls out given N fouls at halftime) → affects lineup + usage
5. **Q4 star usage model (M74)** — does coach increase usage in close 4th? Historical by coach + player
6. **Momentum run detector (M75)** — P(team goes on 8-0 run from this state) → live totals edge

**Target markets (highest edge):**
1. Role player props — spatial model vs lazy book pricing
2. Injury reaction window — 15-60 min lag exploit
3. Same-game parlays — correlation matrix vs independence assumption
4. Back-to-back fatigue props — player-specific curves
5. Live halftime props — M70 live updater vs slow book
6. DFS lineup optimization — projection quality vs free tools

**Success Criteria:**
1. Live lines available for all major books within 60 seconds
2. Edge computed and star-rated for every prop + game
3. Kelly sizing accounts for correlated bets (M32)
4. CLV backtesting shows positive edge retention on flagged bets
5. Live prop updater runs within 3 seconds of halftime box score available
6. Garbage time predictor accuracy > 85% on holdout

---

### Phase 12: Full Monte Carlo Simulator
**Goal**: All 50 models plugged in. Full stat distribution for every player in every game.
**Depends on**: Phase 10 (all models), Phase 11 (odds)

**Enhancements over v1:**
- Momentum model integrated
- Foul trouble simulation (player fouls out)
- Lineup substitution mid-simulation
- Fatigue accumulates across simulated quarters
- Injury impact — efficiency multiplier for listed players
- Referee pace tendency adjusts simulation pace

**Output:**
- Full distribution (not just mean) for every player stat
- Prop over/under probability vs book line → Kelly-sized recommendation
- Lineup optimizer — best 5-man unit for tonight's matchup
- Regression detector — players shooting above/below xFG

---

### Phase 13: FastAPI Backend
**Goal**: All models, analytics, and data exposed as clean API endpoints.
**Depends on**: Phase 12

**Endpoints:**
```
GET  /player/{name}/prediction        → stat distributions for next game
GET  /player/{name}/analytics         → CV metrics, shot quality, fatigue
GET  /player/{name}/shot-chart        → xFG by zone, hot/cold zones
GET  /player/{name}/prop-edges        → edge vs current book lines
GET  /game/{id}/simulation            → 10K sim result
GET  /game/{id}/lineup-optimizer      → best unit for matchup
GET  /team/{name}/analytics           → team-level CV metrics
GET  /edges/today                     → all props with +EV today, sorted
GET  /regression/candidates           → players due for shooting regression
GET  /live/{game_id}/win-probability  → real-time win prob (WebSocket)
POST /chat                            → Claude API tool use entry point
GET  /health                          → dataset status, model versions
```

**Success Criteria:**
1. All endpoints respond < 200ms (cached) / < 2s (fresh compute)
2. Redis caching: 5min live, 1h recent, 24h historical
3. Rate limiting + API key auth
4. WebSocket endpoint for live win probability

---

### Phase 14: Analytics Dashboard Frontend
**Goal**: Interactive analytics dashboard + betting dashboard. Professional-grade, conversational.
**Depends on**: Phase 13

**Tech stack:** Next.js + React, Recharts (bar/line/radar/distribution), D3.js (court maps), WebSocket

**10 chart types:**
1. **Shot chart** — court hexbin, colored by xFG%, hover for zone stats
2. **Bar comparison** — player vs position average vs top 10
3. **Line trend** — rolling stat over time with annotations
4. **Distribution curve** — prop projection bell curve with book line
5. **Radar** — 6-axis player profile spider chart
6. **Heatmap** — court zone map colored by efficiency differential
7. **Scatter** — two-variable player comparison, all guards/forwards/centers
8. **Win probability waterfall** — possession-by-possession timeline
9. **Box plot** — stat distribution vs league
10. **Lineup matrix** — 5-man unit net rating grid, best/worst matchups

**Three surfaces:**
- **Betting Dashboard** — today's games, edges sorted by EV, Kelly allocation, injury alerts
- **Analytics Dashboard** — shot charts, player profiles, team metrics, lineup analyzer
- **Live Dashboard** — real-time win prob, possession replay, live lineup tracker

**Success Criteria:**
1. Shot chart renders in < 500ms with hover interactions
2. All chart types responsive and mobile-friendly
3. Drill-down: click zone → filtered shot log, click player → full profile
4. Live win probability animates every possession during games

---

### Phase 15: AI Chat Interface
**Goal**: Conversational access to everything. Ask any basketball question, get data-backed insight with inline charts.
**Depends on**: Phase 14

**Architecture:**
```
User message → Claude (claude-sonnet-4-6) → tool calls → FastAPI
                                          → render_chart → frontend renders
                                          → synthesized text response
```

**10 tools:**
1. `get_player_prediction` — stat distributions + prop edges for next game
2. `get_player_analytics` — CV metrics, shot quality, fatigue, spacing impact
3. `get_player_shot_chart` — zone-level xFG, hot/cold zones, defender distances
4. `get_game_simulation` — run Monte Carlo, return win prob + stat distributions
5. `get_todays_edges` — all +EV props/games today sorted by edge size
6. `compare_lineups` — head-to-head net rating, best plays, defensive recs
7. `get_regression_candidates` — players overperforming/underperforming xFG
8. `get_injury_impact` — value lost when player X is out
9. `get_matchup_breakdown` — player A vs defender B historical efficiency
10. `render_chart` — instructs frontend to render chart inline in chat

**Example conversations it handles:**
- "Show me Jamal Murray's shot quality vs other guards" → scatter chart
- "What's his prop value tonight?" → distribution curve + recommendation
- "Who's most due for shooting regression this week?" → ranked scatter
- "Break down Nuggets vs Lakers tonight" → simulation + lineup matrix
- "What's my optimal $500 allocation tonight?" → Kelly-sized edge list

**Success Criteria:**
1. Claude answers within 3 seconds including tool calls
2. Charts render inline in chat panel
3. Context injection: today's games + live injuries + current lines in system prompt
4. Handles multi-turn context ("now show his last month" → correct chart)

---

### Phase 16: Tier 6 Models + Live Win Probability
**Goal**: The full 50-model stack. Requires 200+ games processed.
**Depends on**: Phase 9 (feedback loop running), Phase 15

**Tier 6 — 200 Games:**
1. Full possession simulator (all 50 models chained)
2. Live win probability LSTM (possession sequence → win prob)
3. True player impact score (spatial on/off adjusted)
4. Lineup optimizer (chemistry + matchup + fatigue)
5. Prop pricing engine (simulation → full distribution vs book line)
6. Regression detector (xFG vs actual FG% rolling window)
7. Injury impact model (lineup value without player X)

**LSTM inputs:** score_margin, time_remaining, spacing_index, momentum_score, lineup_net_rtg, possession_sequence_embedding

**Success Criteria:**
1. LSTM AUC > 0.75 on live win probability
2. WebSocket updates < 500ms per possession
3. Full stat distribution for every player from simulator
4. Prop pricing engine ROI > 0 on holdout backtest

---

### Phase 17: Infrastructure
**Goal**: Production-ready. Runs itself.
**Depends on**: Phase 16

- Docker Compose runs full stack locally
- GitHub Actions: lint + test on push, auto-deploy on merge
- Cloud GPU instance for video processing (separate from web server)
- Auto-retrain every 2 weeks on latest data
- Feature drift alerts when input distributions shift > 2 sigma
- Model performance monitoring dashboard

---

## The 50 Models

### Tier 1 — NBA API Only (train now): 13 models
Win prob, game total, spread, pts prop, reb prop, ast prop, mins prop, 3PM prop, efficiency, lineup net rating, blowout prob, first half total, team pace

### Tier 2 — Shot Charts (after Phase 3): 5 models
xFG v1, shot zone tendency, shot volume, clutch efficiency, shot creation type

### Tier 3 — 20 CV games: 10 models
xFG v2 (with defender), shot selection quality, play type classifier, defensive pressure, spacing rating, drive frequency, open shot rate, transition frequency, off-ball movement, possession value

### Tier 4 — 50 CV games: 8 models
Rebound positioning, fatigue curve, late-game efficiency, closeout quality, help defense frequency, ball stagnation, screen effectiveness, turnover under pressure

### Tier 5 — 100 CV games: 7 models
Lineup chemistry, defensive matchup matrix, substitution timing, momentum, foul drawing rate, second chance points, pace per lineup

### Tier 6 — 200 CV games: 7 models
Full possession simulator, live win prob LSTM, true player impact, lineup optimizer, prop pricing engine, regression detector, injury impact model

---

## CV Tracker Quality Roadmap

| Upgrade | Effort | Position Gap Closed | xFG Gap Closed |
|---|---|---|---|
| Pose estimation (ankles) | 3 days | 60% | 30% |
| Per-clip homography | 1 week | 40% | 20% |
| YOLOv8x detection | 1 day | 20% | 10% |
| ByteTrack/StrongSORT | 3 days | 15% | 5% |
| Optical flow | 2 days | 15% | 5% |
| OSNet deep re-ID | 1 week | 10% | 5% |
| 3D pose lifting | 2 weeks | 5% | 20% |
| Ball arc estimation | 1 week | 0% | 15% |
| 1,000 games processed | Ongoing | 30% | 35% |

**Current vs target:**
```
Today:          position ±18-24", xFG ~61%, ID switches ~15%
After Phase 2.5: position ±6-8",  xFG ~64%, ID switches ~3%
Second Spectrum: position ±3",    xFG ~68%, ID switches <1%
Gap remaining:   ~5% on prediction accuracy — closeable with data volume
```

---

## Analytics Catalog (96 Metrics)

**Player (36):** xFG%, shot quality, shooting luck index, true off_rtg, usage (spatial), drive frequency, C+S rate, shot creation rate, effective range, hot/cold zones, late-game efficiency, clutch performance, fatigue curve, distance/game, sprint rate, off-ball movement, screen effectiveness, cut frequency, foul drawing rate, turnover under pressure, defensive pressure score, closeout speed, matchup xFG allowed, help rotation rate, rebounding position, contested shot rate, defensive range, switch effectiveness, foul tendency, defensive fatigue, play type distribution, ball dominance, gravity score, floor spacing value, playmaking impact, transition involvement

**Team (21):** offensive rating (spatial), true pace, ball movement score, spacing rating, paint density, shot quality allowed, play type distribution, H/C-T split, offensive rebound rate, stagnation score, hot hand detection, corner 3 rate, defensive rating (spatial), scheme identifier, pressure tendency, help frequency, transition defense, paint protection, 3pt defense, switch rate, foul rate by zone

**Lineup (6):** 5-man net rating, lineup chemistry score, best lineup, worst matchup, optimal rotation, minutes distribution

**Game (15):** win probability timeline, momentum index, turning point detector, shot quality timeline, fatigue map, lineup impact chart, clutch possession map, ball movement heatmap, spacing timeline, defensive pressure map, xFG shot chart, defender distance chart, hot zone map, shot tendency map, assisted vs unassisted map

**Predictive (10):** regression candidates, breakout candidates, fatigue risk flags, matchup edges, line value flags, pace mismatches, injury impact projection, schedule strength, shooting luck normalization, lineup optimizer

**League-wide (8):** efficient shot zones, undervalued players, defensive scheme trends, play type efficiency by team, travel fatigue study, back-to-back efficiency, referee tendency map, home court breakdown

---

## Complete Model Count — 90 Models

| Tier | Count | Models | Requirement | Status |
|---|---|---|---|---|
| 1 | 13 | Win prob, game total, spread, blowout, first half, pace, pts/reb/ast/3pm/stl/blk/tov props | NBA API (3 seasons) | ✅ Trained |
| 2 | 5 | xFG v1, zone tendency, shot volume, clutch efficiency, shot creation type | 221K shot charts | ✅ Trained |
| 2B | 6 | Defensive effort, ball movement, screen ROI, touch dependency, play type efficiency, defender zone xFG | Untapped nba_api endpoints | 🔲 Phase 3.5 |
| 3 | 4 | Age curve, injury recurrence, coaching adjustment, ref tendency extended | Basketball Reference | 🔲 Phase 3.5 |
| 4 | 6 | Sharp money detector, CLV predictor, public fade, prop correlation, SGP optimizer, soft book lag | Betting market scrapers | 🔲 Phase 4.5 |
| 5 | 6 | DNP predictor, load management, return-from-injury, injury risk, breakout predictor, contract year | BBRef injuries + schedule | 🔲 Phase 4.5 |
| 6 | 10 | xFG v2, shot selection quality, play type classifier, defensive pressure, spacing, drive frequency, open shot rate, transition, off-ball movement, possession value | 20 CV full games | 🔲 Phase 7 |
| 7 | 8 | Fatigue curve, rebound positioning, late-game efficiency, closeout quality, help defense, ball stagnation, screen effectiveness, turnover under pressure | 50 CV full games | 🔲 Phase 10 |
| 8 | 7 | Lineup chemistry, matchup matrix, substitution timing, momentum, foul drawing rate, second chance, pace per lineup | 100 CV full games | 🔲 Phase 10 |
| 8B | 4 | Injury NLP, injury lag, team chemistry sentiment, reporter credibility | Reddit + Twitter + RotoWire | 🔲 Phase 9 |
| 9 | 6 | Live prop updater, comeback probability, garbage time, foul trouble, Q4 usage, momentum run | Live data feed | 🔲 Phase 11 |
| 10 | 7 | Full simulator, live LSTM, true player impact, lineup optimizer, prop pricing engine, regression detector, injury impact | 200 CV full games | 🔲 Phase 12/16 |
| **Total** | **82** | | | |

Plus 8 Tier 0 computed schedule features = **90 total model outputs**

---

## Data Volume Milestones

| Games / Data | Models Unlocked | Key Capability Added |
|---|---|---|
| Phase 3 ✅ (NBA API complete) | Tiers 1+2 (18 models) | Win prob + props + xFG v1 |
| Phase 3.5 (untapped APIs + BBRef) | Tiers 2B+3+4+5 (22 models) | Sharp signal, lifecycle, play type efficiency |
| Phase 6 (20 full CV games) | Tier 6 (10 models) | xFG v2 with defender, play type, spacing |
| Phase 9 (NLP live) | Tier 8B (4 models) | Injury lag, sentiment |
| Phase 10 (50-100 CV games) | Tiers 7+8 (15 models) | Fatigue curves, lineup chemistry, matchup matrix |
| Phase 11 (live feed) | Tier 9 (6 models) | Live props, garbage time, comeback |
| Phase 12 (all models) | Tier 10 — simulator | Full 90-model Monte Carlo |
| Phase 16 (200+ CV games) | Tier 10 final | Live LSTM, prop pricing engine |
| 1,000 CV games | Quality converges | Noise averages out, xFG ~66% correlation |

---

## The Master Prediction Formula

> Full detail: `vault/Concepts/Prediction Pipeline.md`

Every prediction runs through 6 layers in sequence:

```
LAYER 1 — GAME CONTEXT
Win prob + pace + total + ref tendency + altitude + schedule + line movement + sharp signal
    ↓
LAYER 2 — PLAYER CONTEXT
Rolling form + zone tendency + usage + matchup history + clutch + DNP risk + contract year
    ↓
LAYER 3 — SPATIAL CONTEXT (Phase 6+)
xFG v2 per zone vs tonight's defense + defensive pressure + spacing + fatigue vs baseline
    ↓
LAYER 4 — EXTERNAL FACTORS
Injury cascade (who's out → who's up) + ref foul tendency + line movement signal + NLP sentiment
    ↓
LAYER 5 — MONTE CARLO SIMULATION
7-model possession chain × 10,000 = full stat distribution per player
    ↓
LAYER 6 — MARKET COMPARISON
Model P(over) vs book implied P(over) = edge
Prop correlation matrix → correlated leg adjustment
Kelly sizing → bankroll fraction
Sharp confirmation (Action Network) → confidence modifier
→ Final: bet/no-bet, size, which book, star rating
```

**Prediction accuracy by phase:**
- Phase 4 (today): ~55-58% props vs 52-54% implied. Small edge on role player props.
- Phase 6 (20 games): ~58-62% with CV spatial. Real consistent edge.
- Phase 10 (100 games): ~60-65% with lineup chemistry + matchup matrix.
- Phase 12 (full stack): ~63-67% on targeted props. +8-12% edge on best bets.
