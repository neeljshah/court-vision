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
| Phase 2.5 — CV Tracker Upgrades | 🟡 Active | Pose estimation (025-07 — MUST finish before Phase 6), ByteTrack, per-clip homography |
| Phase 3 — NBA API Data Maximization | ✅ Done | 568/569 gamelogs, 221K shots, 3,102 PBP games |
| Phase 3.5 — Expanded Data Collection | 🔲 | BBRef 6yr history + The Odds API (fwd from P11) + ProSportsTransactions injury history + news |
| Phase 4 — Tier 1 ML Models | ✅ Done | 13 models trained: win prob + all props + game models |
| Phase 4.5 — Betting + Lifecycle Models | 🔲 | Sharp detector, CLV, correlation matrix, DNP predictor |
| Phase 4.6 — Untapped Signal Wiring | 🔲 | Wire all existing cache data into models — props 30→52 features, no new scraping |
| Phase 4.7 — Prediction Quality Stack | 🔲 | Model stacking, temporal weighting, confidence-gated meta-model, motivation flags |
| Phase 4.8 — Quantitative Betting Infrastructure | 🔲 | CLV tracking, cross-book arb, market structure edges, portfolio construction, execution pipeline |
| Phase 4.9 — Backtesting + Validation Infrastructure | 🔲 | Strategy backtester, paper trading mode, historical prop results DB, validation gate before live money |
| Phase 5 — External Factors | ✅ Done | Injury monitor, ref tracker, line monitor wired |
| Phase 6 — Full Game Processing + Rich Events | 🔲 | 20+ full games, rich event aggregation (drives/box-outs/closeouts/cuts/screens) |
| Phase 7 — Tier 2-3 ML Models + CV Wiring | 🔲 | xFG v2 with closeout speed + shot clock, props retrained with CV behavioral features |
| Phase 8 — Possession Simulator v1 | 🔲 | 7-model chain with rich event inputs, 10K Monte Carlo |
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

**⚠️ PHASE 6 DEPENDENCY:** Pose estimation (025-07) and per-clip homography (025-04/05/06) MUST be complete before Phase 6 game processing begins. First 20 games need pose data for xFG v2 training. Running games without pose means reprocessing them later.

**Plans:** 7 plans
Plans:
- [x] 025-01-PLAN.md — Broadcast detection mode (conf threshold 0.35)
- [x] 025-02-PLAN.md — Jersey OCR brightness normalisation + 2x resize
- [x] 025-03-PLAN.md — Tests for broadcast detection + jersey OCR
- [ ] 025-04-PLAN.md — court_detector.py per-clip homography module
- [ ] 025-05-PLAN.md — Wire detect_court_homography into unified_pipeline
- [ ] 025-06-PLAN.md — Tests for court_detector (synthetic images)
- [ ] 025-07-PLAN.md — YOLOv8-pose ankle keypoints (HIGHEST ROI — do before Phase 6)
  - Replace bbox bottom edge with YOLOv8-pose ankle keypoints as foot position
  - Position error: ±18 inches → ±4 inches (closes 60% of Second Spectrum gap)
  - Unlocks: contest arm angle for xFG v2, movement asymmetry for injury risk
  - Wire ankle_x/ankle_y into tracking_data.csv schema (columns exist, not populated)
  - Test: position error < 6 inches on court line validation frames
  - Time: 3 days

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
- **[GAP FIX] Historical game logs 2017-18 → present (6+ seasons)** — DNP predictor needs coach-specific rest patterns across 6+ seasons to hit 78%+ accuracy. 3 seasons gives ~72%. bbref_scraper.py already handles BPM — extend `get_historical_gamelogs(player_id, seasons=range(2017,2026))` to pull full game-by-game availability (played/DNP/inactive) per player per season. Stores to `data/external/bbref_gamelogs_{season}.json`.
- **[GAP FIX] Extend to 10+ seasons (2014-present)** — critical for: age curves (need 500+ samples per age bracket), injury recurrence (need 50+ per injury type), coaching tendencies (need 5+ seasons per coach), contract year effect (need 200+ walk-year seasons), trade deadline adjustment speed (need 30+ deadline scenarios), B2B fatigue by position (need 500+ B2B pairs per position). Target: `seasons=range(2014, 2026)` for all BBRef endpoints. Storage: `data/external/bbref_*_{season}.json`. Model quality ceiling raise: +2-3% across all categories from better calibration on rare events.
- **[ADD] Player bio data** — height, weight, wingspan per player. Relevant for xFG (wingspan affects shot blocking), rebound positioning (height + wingspan = contest radius), defensive matchup model. Source: NBA API `CommonPlayerInfo`. Store to `data/nba/player_bio.json`.

**3.5-C — Betting Market Scrapers (1-2 days)**
- Action Network: public bet% + money% per game/prop → sharp vs public signal
- OddsPortal: historical closing lines 15 years → CLV backtesting ground truth
- Pinnacle: sharpest opening lines → steam detection, market benchmark
- DraftKings/FanDuel: current player props → soft book lag detection
- **[GAP FIX] The Odds API — pull forward from Phase 11 to here.** Every betting model (sharp detector, CLV predictor, public fade, soft book lag) needs REAL closing lines to train and validate. The current CLV backtest uses actual game margins as a proxy — it can tell you win/loss accuracy but NOT whether you're beating the line. Wire `The Odds API` (free tier: 500 req/month) into `src/data/odds_scraper.py` alongside the existing NBA API fallback. Once live lines are available, `backtest_clv()` in `betting_edge.py` should compare model spread vs real closing lines, not actual margins. This is the single biggest gap between "accuracy metrics" and "actual betting edge."

**3.5-D — Expanded News/Injury Pipeline (1 day)**
- NBA official injury report PDF (~5pm ET daily) → faster than ESPN by 30-60min
- RotoWire RSS feed (feedparser) → injury/lineup news
- Reddit r/nba API (praw package) → injury threads, lineup news, sentiment
- HoopsHype/Spotrac scraper → contracts, cap data, transaction history
- **[GAP FIX] ProSportsTransactions.com historical injury data** — The NLP injury severity model (Phase 9, M66) needs a TRAINING SET of historical injury reports matched to outcomes (how many games missed, efficiency on return). `prosportstransactions.com` has free structured injury history back to 2000+ for all NBA players. Build `src/data/injury_history_scraper.py` → `get_injury_history(player_name)` → returns list of `{date, injury_type, games_missed, return_efficiency}`. Without this, the injury NLP model is just keyword matching, not ML. Data stored to `data/external/injury_history_{player_id}.json`.

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

**[ADD] Roster Opportunity Model (M41)**
When a star player is injured or DNP, books scramble and misprice replacement players for 2-5 games. This is one of the highest-edge opportunities in the entire market.

```python
# src/prediction/roster_opportunity.py
class RosterOpportunity:
    def get_beneficiaries(self, injured_player_id, team_id) -> list:
        """
        Sources: on/off splits (who plays more when X is out?)
                 historical lineup data (who replaces X in rotation?)
                 synergy play types (who runs X's plays when absent?)
                 coaching rotation patterns
        Returns: [{player_id, usage_absorption_pct, minutes_gain, pts_boost_expected}]
        """
    def first_game_edge(self, injured_player_id) -> list:
        """
        First game post-injury = maximum edge window.
        Books price replacements at baseline. Your model prices the exact redistribution.
        """
```

**[ADD] Player Similarity Model (M42)**
Used for: rookie projections, mid-season trade fit estimation, injury replacement comps.
```python
# Finds N most similar players using: shooting zones, play type distribution,
# physical profile, on/off splits, hustle stats, synergy efficiency
# Application: new player → find historical comps → bootstrap predictions
```

**Success Criteria:**
1. Prop correlation matrix covers all 569-player pair combinations
2. DNP predictor backtests at > 75% accuracy on historical data
3. CLV predictor identifies +2% CLV edges on validation set
4. Return-from-injury curve has enough historical samples per injury type (≥30)
5. Roster opportunity model identifies correct top beneficiary in >70% of star DNP games
6. Player similarity model finds statistically valid comps (cosine similarity > 0.80) for 90%+ of players

---

### Phase 4.6: Untapped Signal Wiring (No New Data Needed)
**Goal**: Wire all data that already exists in cache files into every model that should be using it. Zero new scraping needed — this is pure connection work that immediately improves every trained model.
**Depends on**: Phase 4 (models trained), Phase 3.5 caches populated
**Status**: 🔲

This phase exists because data was scraped and models were trained independently. Dozens of high-value signals are sitting in cache files that no model reads yet. Wire them all before processing any games.

---

**4.6-A — Prop Models: 30 → 52 Features**

Current prop features (30): season avgs, rolling form, Bayesian avgs, home/away splits, vs-opp history, opp_def_rtg, fg_pct, clutch stats, bbref_bpm, contract_year.

Add from existing cache files:

| New Feature | Source Cache | Expected Impact |
|---|---|---|
| `bbref_vorp` | bbref_advanced_*.json | Better player value signal than BPM alone |
| `bbref_ws_per_48` | bbref_advanced_*.json | Win share rate — production efficiency |
| `hustle_deflections_pg` | hustle_stats_*.json | Defensive activity → correlates with on-court time |
| `hustle_screen_assists_pg` | hustle_stats_*.json | Screener role → AST inflation for ball handlers |
| `hustle_contested_shots_pg` | hustle_stats_*.json | Defensive effort → opponent xFG suppression |
| `on_off_diff` | on_off_*.json | Impact rating — better than net_rtg alone |
| `synergy_iso_ppp` | synergy_offensive_*.json | Isolation efficiency → pts model |
| `synergy_pnr_ppp` | synergy_offensive_*.json | PnR handler efficiency → pts + AST model |
| `synergy_spotup_ppp` | synergy_offensive_*.json | Spot-up efficiency → 3pm + pts model |
| `cap_hit_pct` | contracts_2024-25.json | Salary pressure — complements contract_year |
| `contested_shot_pct` | shot_dashboard_all_*.json | How often player's shots are contested |
| `catch_and_shoot_pct` | shot_dashboard_all_*.json | C&S rate → 3pm model accuracy |
| `pull_up_pct` | shot_dashboard_all_*.json | Pull-up rate → pts model, harder shots |
| `avg_defender_dist` | shot_dashboard_all_*.json | Average defender proximity at shot release |
| `rest_days` | schedule_context (already built) | Missing from props — B2B drops stats significantly |
| `travel_miles` | schedule_context (already built) | Away trips → efficiency drop |
| `games_in_last_14` | gamelog (derivable) | Workload accumulation → fatigue proxy |
| `ref_fta_tendency` | ref_tracker.py | High-foul refs → pts prop boost for foul drawers |
| `def_synergy_iso_allowed` | synergy_defensive_*.json | Opponent's ISO defense quality vs this player's style |
| `defender_zone_fg_allowed` | defender_zone_*.json | FG% this team's defender allows in each zone |
| `matchup_fg_allowed` | matchups_*.json | Specific historical FG% of likely defender on this player |
| `shot_zone_tendency_entropy` | shot_zone_tendency.json | How predictable player's zone distribution is |

**Target**: Props go from 30 → 52 features. Retrain all 7 prop models.
**Expected MAE improvement**: pts 0.32 → ~0.22, reb 0.11 → ~0.07, ast 0.09 → ~0.06

---

**4.6-B — Win Probability: Add Missing Signals**

Currently missing from win_probability.py features:
- `ref_pace_tendency` — high-pace refs → higher total, tighter games
- `home_hustle_avg` / `away_hustle_avg` — team deflections/game → proxy for effort and winning close games
- `home_synergy_pnr_ppp` / `away_synergy_pnr_ppp` — offensive scheme efficiency head-to-head
- `home_contested_pct` / `away_contested_pct` — shot quality generation vs concession

Wire all from existing caches. Retrain win prob — target Brier 0.204 → ~0.195.

---

**4.6-C — Game Models: Add Missing Signals**

Currently missing from game_models.py features:
- `ref_pace_tendency` — pace model needs actual ref pace tendency, not just avg fouls
- `ref_fta_per_game` — ref-specific foul rate → game total (foul shots add points)
- `pace_avg` already wired ✅ but `synergy_transition_ppp` sum for both teams is missing → transition teams score faster = higher total
- `home_ts_pct` / `away_ts_pct` already wired ✅ but `home_pull_up_pct` / `away_pull_up_pct` (pull-up heavy teams → lower eFG → lower total) missing

---

**4.6-D — Matchup Model: Wire Defender Zone + Synergy Defense**

Current matchup model (M22) uses hustle + on/off. Missing:
- `defender_zone_fg_allowed` (zone-specific FG% the defender allows) — per `defender_zone_*.json`
- `def_synergy_iso_allowed` — pts/poss allowed on isolation by this defender — per `synergy_defensive_*.json`
- `matchup_fg_pct_allowed` — actual historical FG% when guarding similar player — per `matchups_*.json`

These three signals make matchup model directly answer: *"Can this defender guard a player of this offensive style?"* not just *"Is this defender generally good?"*

---

**4.6-E — Shot Quality: Wire Shot Clock + Fatigue**

`shot_quality.py` has `shot_clock_pressure_score()` and `fatigue_penalty()` already coded but never called automatically. Wire them into the main `score_shot()` pipeline so every shot gets:
- Shot clock pressure decay (0–3 sec remaining → 20% quality penalty)
- Fatigue penalty from `velocity_mean_90 / velocity_mean_150` at shot frame

This improves xFG v1 accuracy immediately — late-clock shots are systematically overvalued without this.

---

**4.6-F — Momentum + Pressure → Prop Inputs**

`momentum.py:scoring_run_length()` and `momentum_shift_flag()` are never aggregated per-player per-game. After each game processed, compute:
- `player_momentum_when_shooting` — was team on a run when this player shot?
- `avg_pressure_when_handling` — defensive pressure the player faced
These become features in the pts/reb prop models (high-pressure games → lower efficiency).

---

**4.6-G — Clutch Score as Context-Adjusted Prop Modifier**

`data/nba/clutch_scores_*.json` has per-player clutch efficiency scores but is not used as a conditional prop modifier. Add:
- When tonight's projected spread is ≤4 pts (close game): multiply pts prop by `1 + (clutch_score - league_avg) * 0.05`
- High-clutch players (score ≥8.0) get a +3-5% pts boost in close game projections
- Low-clutch players (score ≤4.0) get suppressed
- Source: `predict_props()` → read projected spread from game model → apply clutch multiplier conditionally

**Expected lift:** +2-3% on pts props in close game contexts

---

**4.6-H — SHAP Explainability Layer**

Every model needs SHAP values computed — not just for debugging, but as a core feature of the AI chat interface ("why did the model predict 28.4?") and for detecting model drift.

```python
# src/analytics/model_explainer.py
class ModelExplainer:
    def explain_prediction(self, player_id, stat, game_id) -> dict:
        """
        Returns SHAP contributors for this specific prediction.
        Example: {
          "base_value": 22.1,
          "contributors": [
            {"feature": "rolling_pts_5", "value": 31.2, "shap": +3.1},
            {"feature": "matchup_fg_allowed", "value": 0.48, "shap": +1.8},
            {"feature": "b2b_road", "value": 1, "shap": -2.4},
            ...
          ],
          "final_prediction": 28.4
        }
        Powers AI chat: 'Explain this prediction' → readable reasoning.
        """

    def top_features_report(self, model_name) -> dict:
        """Global SHAP importance — confirms new features are contributing."""

    def drift_check(self, model_name, recent_games=20) -> dict:
        """
        Detects if SHAP distribution has shifted from training distribution.
        Input feature drift >2σ → flag for manual model review.
        """
```

**[ADD] Regression Detector (pull forward from Phase 12)**

```python
# src/analytics/regression_detector.py
class RegressionDetector:
    def find_candidates(self) -> list:
        """
        Players shooting significantly above/below xFG over last 10 games.
        - Scoring > xFG by 3+ pts → due for negative regression → fade
        - Scoring < xFG by 3+ pts → positive regression coming → back
        Books use scoring averages. You use xFG. Gap = systematic edge.
        Run daily. Output feeds BetFilter as a signal.
        """
```

**Success Criteria:**
1. All 7 prop models retrained with 52 features — MAE improves on all stats
2. Win prob retrained with new team-level signals — Brier improves
3. Matchup model retrained with defender_zone + synergy_defense — R² improves from 0.796
4. Shot quality score includes shot clock and fatigue automatically
5. SHAP computed for all models — new features confirmed in top 15 by importance
6. All new feature columns documented in `src/prediction/player_props.py:_ALL_FEATS`
7. Clutch multiplier applied when spread ≤4 and clutch_score available
8. Regression detector running daily — outputs flagged players with xFG vs actual gap
9. ModelExplainer.explain_prediction() works for all 7 prop models — powers AI chat
10. All 4.6-I little edge features added — verified by SHAP that each contributes

---

**4.6-I — Advanced Feature Engineering (Little Edges Stack)**

Every feature here adds 0.3-1% individually. Together they close the gap with Second Spectrum on prop accuracy.

```python
# ── Home/Away Split Differential ──────────────────────────────────────────
# Books blend home/away. Some players have massive splits (arena noise sensitive).
home_away_split_delta = player_home_avg - player_away_avg
# If delta > 4pts: on road games, adjust line down by 0.6 * delta
# Source: gamelog history. Wire into: all counting stat props.

# ── Opponent Defensive TRAJECTORY (not just season average) ───────────────
opp_def_rtg_trend = opp_def_rtg_last10 - opp_def_rtg_season
# Negative = defense improving → suppress offensive props
# Positive = defense collapsing → boost offensive props
# Books use season average. You use trajectory.

# ── Post-Trade Performance Curve ──────────────────────────────────────────
days_since_trade → post_trade_multiplier:
# Week 1 (0-7d): 0.82, Week 2 (7-14d): 0.88, Weeks 3-4 (14-28d): 0.94,
# Month 2 (28-45d): 0.98, Fully adjusted (45d+): 1.00
# Source: 6+ seasons transaction history + gamelog matching
# Edge: fade newly traded stars for weeks 1-4. Books overprice immediately.

# ── Lineup-Specific Usage (not season average) ─────────────────────────────
usage_with_star    = float  # usage when team's primary star plays
usage_without_star = float  # usage when star injured/sits → DNP beneficiary edge
# Source: NBA API lineups + PBP usage calculation
# Critical for: injury replacement props, DNP beneficiary models

# ── xFG Persistent Overperformers ─────────────────────────────────────────
career_xfg_gap = actual_career_fg_pct - career_xfg
# Players with gap > +0.04 = true elite shooters. Don't fully regress them.
# Players with gap < -0.03 = structural inefficiency. Regress harder.
# Source: 6 seasons xFG v1 vs actual → per-player persistent gap

# ── Drive Outcome Distribution (not just rate) ─────────────────────────────
drive_finish_rate   = float  # → pts model boost
drive_foul_rate     = float  # → FTA prediction improvement
drive_kickout_rate  = float  # → AST model (not pts)
drive_turnover_rate = float  # → negative pts signal
# Source: PBP drive events + outcome classification

# ── Pace VARIANCE (not just average) ──────────────────────────────────────
team_pace_variance = std(possessions_per_game, last_20)
# High variance matchups → widen confidence intervals → BetFilter downgrades

# ── ELO Rating with Recency Decay ─────────────────────────────────────────
# FiveThirtyEight-style Elo: K=20, home_advantage=100pts
# More predictive than win% for actual team quality
# Corrects for strength of schedule automatically
# Add: home_elo, away_elo, elo_differential to win prob + game models

# ── Dynamic Career/Season Regression Weighting ───────────────────────────
def regression_weight(games_played: int) -> float:
    # Games 1-10: 80% career, 20% current season
    # Games 10-25: 50% career, 50% current season
    # Games 25-50: 25% career, 75% current season
    # Games 50+: 10% career, 90% current season
# Bayesian updating with proper prior weight decay
# Better than fixed weighting used by all public models

# ── Interaction Terms (multiplicative effects) ────────────────────────────
interaction_features = [
    b2b_flag * is_road,              # combined fatigue (worse than additive)
    b2b_flag * usage_rate,           # high-usage players hurt MORE by B2B
    contract_year * hot_streak,      # motivation × current form
    high_foul_ref * foul_draw_rate,  # ref tendency × player tendency
    home_away_split * is_away,       # player-specific road penalty
    playoff_implication * clutch_score,  # high stakes × clutch ability
    pace_variance * model_confidence,    # uncertain game → lower bet confidence
]

# ── Foul Cascade Probability (Markov Chain) ───────────────────────────────
foul_transition_matrix = {
    (1_foul, Q1): {bench_prob: 0.22, foul_out_prob: 0.04},
    (2_fouls, Q1): {bench_prob: 0.73, foul_out_prob: 0.12},
    (2_fouls, Q2): {bench_prob: 0.44, foul_out_prob: 0.18},
    (3_fouls, Q2): {bench_prob: 0.81, foul_out_prob: 0.31},
}
# Build from 6 seasons PBP foul events + minutes data
# Feeds: minutes model, pts model, garbage time predictor (live betting)

# ── Shooting Slump Type Detection ─────────────────────────────────────────
# Compare current shot zone distribution vs career baseline
# Shot selection shift (taking worse shots): will self-correct → OVER value
# Uniform FG% drop (true slump): genuine cold streak → UNDER value
# Most models treat all slumps identically. This splits them.

# ── All-Star Break Return Effect ──────────────────────────────────────────
days_since_allstar_break → player_specific_asb_multiplier
# Some players consistently underperform first 2-3 games post-ASB (vacation mode)
# Some consistently outperform (rested, energized)
# Source: 6 seasons gamelog, games immediately post-ASB vs pre-ASB baseline
# Books use season averages through this period

# ── G-League Callup Adjustment ────────────────────────────────────────────
# G-League → NBA adjustment by position:
# Guards: pts/36 × 0.65, AST/36 × 0.75
# Bigs: pts/36 × 0.72, REB/36 × 0.85
# Books often blank-slate callup players or price too high
# Player similarity model (Phase 4.5 M42) comps them to historical callups

# ── Second Quarter Coaching Adjustment Rating ─────────────────────────────
coach_q3_adjustment_rating = mean(Q3_pts_allowed - Q1_pts_allowed, over_3_seasons)
# Negative = coach improves D at half (Spoelstra, Pop)
# Positive = opponent out-adjusts them
# Wire into: second half total props, live halftime models
```

**Where these wire in:**
- `src/features/feature_engineering.py` — add all as computed columns
- `src/prediction/player_props.py` — add interaction terms + post-trade multiplier + ASB multiplier
- `src/prediction/win_probability.py` — add ELO, opp_def_trend, interaction terms
- `src/tracking/ball_detect_track.py` — foul cascade feeds live garbage time predictor

---

### Phase 4.7: Prediction Quality Stack
**Goal**: Stack the models, apply temporal weighting, build a confidence-gated meta-model, and add motivation/context flags that no competitor uses. Pure modeling improvements — no new data sources, no video.
**Depends on**: Phase 4.6 (all signals wired, models retrained)
**Status**: 🔲

This phase is what separates "good model" from "sharp tool." All ceiling raisers that are about HOW predictions combine rather than WHAT data feeds them.

---

**4.7-A — Model Stacking (Ensemble Layer)**

Replace single XGBoost per prop with a 3-layer stack:
```
Layer 1 — Base models (trained independently):
  XGBoost (season stats + rolling form + contextual features)
  Ridge regression (recent form — last 10 games, heavily weighted)
  Bayesian update (prior = season avg, likelihood = last 5 game trend)

Layer 2 — Meta-model:
  Logistic regression trained on L1 predictions → learns which base
  model to trust most per player type / situation

Layer 3 — Calibration:
  Platt scaling on final probability → calibrated confidence scores
```

**Expected MAE improvement:** pts 0.22 → ~0.18 (after Phase 4.6 retraining)
**Expected prop hit rate improvement:** +1-2% globally, +3-4% on high-confidence filtered plays
**Time:** 3 days

---

**4.7-B — Temporal Weighting (Recency Decay)**

Current gamelog model weights all 82 games equally. Games from October are stale by March.

Add exponential decay weighting:
```python
# Half-life = 15 games
game_weight = 0.5 ** (games_ago / 15)
# Result: last 5 games = 4x weight of games 25-30 ago
```

Apply to:
- All rolling features in `feature_engineering.py` (rolling_pts_5, rolling_pts_10, etc.)
- Gamelog regression in prop training
- Season average computation (use weighted mean, not arithmetic mean)

**Expected improvement:** +0.5-1% MAE — most impactful for in-season slump/hot streak detection
**Time:** 1 day

---

**4.7-C — Confidence-Gated Meta-Model (Bet Filter)**

The single highest-ROI change in the entire system. Don't bet every prop — only the top 20% by confidence.

Build `src/prediction/bet_filter.py`:
```python
class BetFilter:
    """Meta-model that predicts when the prop model is most likely to be correct."""

    # Features:
    # - model_confidence_spread (difference between model line and book line)
    # - injury_flag_age_hours (how fresh is the injury signal)
    # - player_type (role player vs star — role players priced lazier)
    # - line_movement_direction (agrees or disagrees with sharp money)
    # - days_rest (well-rested = more predictable)
    # - home_away (home players more consistent)
    # - b2b_flag (B2B = higher variance)
    # - contract_year_flag (higher motivation = less regression)
    # - dnp_probability (higher DNP prob = less reliable projection)

    def should_bet(self, prediction) -> tuple[bool, float]:
        """Returns (bet_yes/no, confidence_score)."""
```

Train on historical prop results (Phase 3.5-C backtest data).

**Expected filtered hit rate:** 65%+ on top-20% confidence plays vs 57-60% overall
**Time:** 3 days (needs historical prop results from Phase 3.5-C)

---

**4.7-D — Revenge Game / Motivation Flag**

Players facing former teams or in high-motivation spots average +3.2pts vs expectation. Books don't adjust.

Build `src/data/motivation_flags.py`:
```python
def get_motivation_flags(player_id: int, game_id: str) -> dict:
    """
    Returns motivation context for tonight's game.
    Sources: trade history (transactions), schedule, rivalry games.
    """
    flags = {
        "vs_former_team": bool,         # traded away from this opponent
        "former_team_recency": int,      # seasons ago — recent trade = stronger signal
        "rivalry_game": bool,            # Celtics-Lakers, Knicks-Nets, etc.
        "milestone_proximity": str|None, # "12 pts from 20K career" → usage spike
        "national_tv_game": bool,        # ESPN/ABC/TNT → star usage spikes
        "playoff_elimination": bool,     # team fighting for playoff spot
        "motivation_multiplier": float,  # composite 0.95-1.12
    }
```

**Data sources:** NBA transactions API (free), schedule context, known rivalry list (hardcoded)
**Expected lift:** +2-4% on flagged games (~30-40 per season per flag type)
**Time:** 2 days

---

**4.7-E — Coaching Minutes Distribution Model**

Minutes props are the highest-leverage input because `minutes × per_minute_rate = counting stat`. Current props use season-average minutes. Build a coach-specific model:

```python
# Per-coach rotation tendencies:
# - Typical starter minutes distribution (Q1-Q4 breakdown)
# - B2B rest patterns (coach-specific, not league average)
# - Foul trouble response (some coaches bench immediately at 2 fouls Q1)
# - Load management threshold (which coaches have used it before)
# - Blowout substitution patterns (when do starters exit in a blowout)

# Build from:
# - 3 seasons of boxscores × coach_id
# - data/nba/lineups/ directory (already fetched)
```

**Expected lift:** +2-3% on ALL counting stats (more accurate minutes → more accurate everything)
**This is the highest single-leverage input in prop modeling.**
**Time:** 3 days

---

**4.7-F — Injury Recurrence Curve**

Players returning from injury are systematically overpriced by books — books reset to "healthy average" immediately. You have the data to do better.

Build `src/prediction/injury_recurrence.py`:
```python
# Per injury type × player age × severity:
# - hamstring: game 1-5 back → 85% of normal efficiency, game 6-10 → 92%, game 11+ → 100%
# - ankle: game 1-3 back → 88% of normal, game 4+ → 98%
# - knee: game 1-10 back → 80%, game 11-20 → 90%, game 21+ → 97%
# Data: BBRef injury history + gamelog matching (data/external/bbref_advanced_*.json)

def return_efficiency_multiplier(player_id, injury_type, games_since_return) -> float:
    """Returns expected efficiency fraction vs baseline (0.8-1.0)."""
```

**Expected lift:** +5-8% on return-from-injury props — largest single edge in the market
**Time:** 3 days

---

**4.7-G — Quantile Regression (Replace Mean Prediction)**

The single highest-impact modeling upgrade. NBA stat distributions are NOT Gaussian — they're right-skewed with fat tails. Predicting the mean then assuming normality is wrong.

```python
from sklearn.ensemble import GradientBoostingRegressor

# Train separate models at 5 quantile levels:
quantile_models = {
    0.10: GradientBoostingRegressor(loss='quantile', alpha=0.10),  # floor
    0.25: GradientBoostingRegressor(loss='quantile', alpha=0.25),
    0.50: GradientBoostingRegressor(loss='quantile', alpha=0.50),  # median
    0.75: GradientBoostingRegressor(loss='quantile', alpha=0.75),
    0.90: GradientBoostingRegressor(loss='quantile', alpha=0.90),  # ceiling
}
# Result: direct P(over X) at any threshold without Gaussian assumption
# P(Tatum > 27.5) = interpolate from quantile curve — no normality needed
# Better calibration on big game outliers (fat tails captured)
```

---

**4.7-H — Multi-Task Learning (Train All Props Simultaneously)**

```python
# Current: separate XGBoost per stat. Each model ignorant of the others.
# Better: shared player representation across all stats

# Architecture:
# Shared encoder: player_features + context → 128-dim player_state
# Task heads: player_state → pts_head, reb_head, ast_head, fg3m_head, etc.

# Why: pts and ast are correlated (high-usage players get both)
#      pts and reb are correlated (bigs who score also rebound)
# Sharing the encoder forces a better player representation
# Especially useful for low-sample players (5-10 games: shared rep helps)

# Build with: PyTorch or Keras functional API
# Expected improvement: +0.5-1% MAE across all stats
```

---

**4.7-I — Bayesian Hierarchical Model (Small Sample Superiority)**

```python
# Problem: rookie has 8 games. Early season: 6 games per player.
# Pure ML overfits to noise on small samples.

# Structure (using PyMC):
# Level 1 — league prior: all PGs → Normal(18, 5)
# Level 2 — archetype: PnR handlers → Normal(24, 3.5)
# Level 3 — player: this player's games → update toward posterior
# Result: new player prediction starts near archetype, updates with data

# When to use: games_played < 25 → use hierarchical
#              games_played ≥ 25 → trust XGBoost ensemble
# Blend: weight = min(games_played / 25, 1.0) * XGBoost + (1 - weight) * Bayesian

# Biggest early-season edge: Oct-Nov when everyone has <10 games
# Books use preseason projections. You use archetypes + actual data blended.
```

---

**4.7-J — Regime Detection (Hidden Markov Model for Streaky Players)**

```python
from hmmlearn import hmm

# Two-state HMM per player:
# State 0 (cold): lower_mean, higher_variance
# State 1 (hot):  higher_mean, lower_variance
# Viterbi algorithm → P(currently_in_hot_state | last_N_games)

# Wire into prop model:
# prediction = hot_prob * hot_state_mean + (1-hot_prob) * cold_state_mean
# + hot_prob * hot_variance_adjustment (more confidence when hot)

# Most valuable for: demonstrably streaky players (Curry, Kyrie, Booker)
# Detectable by: autocorrelation in gamelog > 0.35 threshold
# Not useful for: consistent players (Jokic, DeRozan) — just adds noise for them
# So: auto-detect streakiness, apply HMM only where appropriate
```

---

**4.7-K — Conformal Prediction (Provably Calibrated Uncertainty)**

```python
from nonconformist import IcpRegressor

# Problem: model says 70% confident → reality it's only 58% correct
# This miscalibration makes you bet too large on false confidence

# Conformal prediction gives VALID coverage guarantees:
# "My 80% prediction interval covers the true value EXACTLY 80% of the time"
# Proven mathematically, not just claimed

# Implementation:
# 1. Train base model on 80% of data
# 2. Calibrate on 10% holdout → learn residual distribution
# 3. For new predictions: interval width = residual quantile at target coverage
# 4. Narrow intervals = model is confident. Wide intervals = skip the bet.

# Wire into BetFilter: only bet when conformal interval < 1.5 * line_vig_width
```

---

**4.7-L — Optimal Lookback Window Per Player**

```python
def optimal_lookback(player_id: int, stat: str) -> int:
    """
    Consistent players (Jokic, DeRozan): long lookback (20+ games) is fine.
    Volatile players (Westbrook): short lookback (5-8 games).
    Injured/returning: very short lookback (last 3 games only).

    Method: fit AR(p) model on gamelog, AIC/BIC model selection → optimal p.
    Auto-computes per player per stat at season start, updates monthly.
    """
    # Expected improvement: +0.5-1% MAE on volatile players
    # Zero cost on consistent players (they select similar lookback anyway)
```

---

**4.7-M — Asymmetric Loss Function**

```python
def asymmetric_betting_loss(y_true, y_pred, alpha=1.5):
    """
    Standard MSE treats over/under predictions equally.
    For betting: false confidence (betting bad lines) costs more than
    missed confidence (skipping good lines).

    alpha > 1: penalizes over-prediction more → conservative by design
    Trains model to only be confident when genuinely warranted.
    """
    residuals = y_true - y_pred
    return np.where(residuals >= 0,
                    alpha * residuals**2,
                    residuals**2).mean()

# Use: replace MSE in all XGBoost training with this custom objective
# Effect: model becomes conservative → BetFilter catches more real edges
```

---

**4.7-N — Per-Segment Calibration (Platt Scaling)**

```python
# One calibration curve for all situations is wrong.
# Model confidence on B2B games is different from normal games.

calibrators = {
    "star_players":        PlattScaler(),
    "role_players":        PlattScaler(),   # model is least calibrated here
    "b2b_games":           PlattScaler(),
    "early_season_g10":    PlattScaler(),   # high uncertainty, wider intervals
    "home_games":          PlattScaler(),
    "road_games":          PlattScaler(),
    "post_injury_return":  PlattScaler(),   # systematically overconfident here
    "post_trade_14d":      PlattScaler(),   # systematically overconfident here
}
# Train each calibrator on its segment's holdout data
# Result: 70% confidence means 70% in EVERY segment
```

---

**Success Criteria:**
1. Model stacking implemented for all 7 prop models — ensemble MAE < base model MAE on holdout set
2. Temporal weighting applied — verified rolling features outperform flat on validation set
3. `BetFilter.should_bet()` operational — top-20% confidence plays hit ≥63% on 6-month backtest
4. Motivation flags fire correctly on known revenge game examples (Kyrie vs Celtics 2022, etc.)
5. Coaching minutes model backtests with <2.5 minutes MAE per player per game
6. Injury recurrence curve validated on ≥50 return-from-injury historical samples per major injury type
7. Full pipeline: `predict_props()` → `BetFilter` → only output bets with confidence ≥ threshold
8. Quantile regression deployed — P(over X) directly from quantile curve, no Gaussian assumption
9. Bayesian hierarchical model active for players with <25 games — MAE improves vs pure XGBoost on early-season holdout
10. Regime detection (HMM) active for players with autocorrelation > 0.35 — hot/cold state probabilities in feature vector
11. Conformal prediction intervals computed — BetFilter uses interval width as confidence gate
12. Optimal lookback selected per player — volatile players (autocorr < 0.2) use 5-8 game window
13. Asymmetric loss function training all prop models — confirmed by lower false-confidence rate on validation
14. Per-segment Platt calibration deployed — all 8 segments show <3% calibration error on holdout

---

### Phase 4.8: Quantitative Betting Infrastructure
**Goal**: Build the full quantitative trading stack on top of the prediction models. This phase turns model outputs into a systematic, risk-managed, profit-optimized betting operation. Think of this as the execution layer — the models are the alpha, this is the trading desk.
**Depends on**: Phase 4.5 (market models), Phase 4.7 (BetFilter)
**Status**: 🔲

---

**4.8-A — Make-Your-Own-Line (MYOL) Engine**

The foundation of quant betting discipline. Before any book is consulted, your model outputs its own number.

```python
# src/prediction/myol.py
class MakeYourOwnLine:
    """
    Generates model lines for every market before consulting books.
    Forces discipline — you never anchor to the book's number.
    """
    def generate_slate(self, game_date: str) -> dict:
        # Runs all prop models + game models
        # Returns: {player: {stat: model_line, confidence: float}}

    def find_discrepancies(self, model_lines, book_lines, min_gap=0.75) -> list:
        # Compares MYOL vs books across all markets
        # Returns bets sorted by edge size (model_line - book_line)
        # min_gap = minimum point difference to flag as bettable
```

**Rule:** Only bet when `abs(model_line - book_line) > vig_equivalent`. Everything below that threshold is noise.

---

**4.8-B — CLV Tracking System (Primary Performance Metric)**

Stop measuring win/loss rate. CLV (Closing Line Value) is the only statistically valid short-term performance signal.

```python
# src/analytics/clv_tracker.py
class CLVTracker:
    """
    Tracks every bet's value relative to the closing line.
    CLV > 0 consistently = positive expected value regardless of results.
    """
    def log_bet(self, player, stat, bet_line, bet_side, book, timestamp): ...
    def record_close(self, player, stat, closing_line, book): ...
    def clv_report(self, start_date, end_date) -> dict:
        # Returns: avg_CLV, CLV_by_book, CLV_by_stat, CLV_by_tier
        # Target: avg CLV > +0.8 pts on props, > +1.2 pts on game lines

    def model_accuracy_signal(self) -> float:
        # Converts CLV into model accuracy estimate
        # +1pt CLV on NBA props ≈ +3-4% hit rate above break-even
```

**Why this matters:** In a 100-bet sample, win/loss variance is ±15%. CLV variance is ±0.3 pts. CLV gives you a real model quality signal 5x faster.

---

**4.8-C — Cross-Book Arbitrage + Middle Detection**

Books disagree daily. Systematic exploitation requires automation.

```python
# src/analytics/arb_detector.py
class ArbDetector:
    """
    Finds cross-book price discrepancies and middle opportunities.
    Runs on every prop fetch — flags instantly.
    """
    def find_middles(self, book_lines: dict) -> list:
        """
        Middle: Book A has over 27.5, Book B has under 29.5
        → Bet both → free win if result is 28 or 29
        → Worst case: one loss (small), best case: two wins
        Returns: [{player, stat, book_a, line_a, book_b, line_b, middle_width}]
        """

    def find_stale_lines(self, book_lines: dict, pinnacle_line: float) -> list:
        """
        If any book is >1.5 pts off Pinnacle → stale line → bet immediately.
        Pinnacle = sharpest book, others lag 15-45 min.
        Returns: [{player, stat, stale_book, stale_line, pinnacle_line, gap}]
        """

    def best_price_router(self, player, stat, side) -> tuple[str, float]:
        """Always route to lowest-vig book for each specific market."""
```

**Expected EV on middles:** +12-18% per identified middle, ~2-5/week
**Expected EV on stale lines:** +8-12% EV, ~5-10/week (pure information arbitrage)

---

**4.8-D — Opening Line Timing Exploit**

Books post lines 24-48h before tip with high uncertainty. First 30-60 minutes = softest prices.

```python
# Add to line_monitor.py:
def monitor_line_posts(callback_fn):
    """
    Polls all major books every 2 minutes for new lines posting.
    When a new line appears → immediately run MYOL comparison.
    If gap > threshold → fire callback_fn(bet_signal).
    """

# Opening line betting rule:
# If model is high-confidence (BetFilter tier 1) AND line just posted → bet immediately
# Don't wait — steam corrects lines within 30-90 min
```

---

**4.8-E — Reverse Line Movement (RLM) Confirmation**

RLM is your second independent signal. When it agrees with your model → highest confidence tier.

```python
# src/analytics/rlm_detector.py
class RLMDetector:
    """
    Reverse Line Movement: line moves AGAINST public bet percentage.
    Signal: sharp money on the other side.
    """
    def detect_rlm(self, public_pct: float, line_open: float, line_current: float) -> dict:
        """
        If public_pct > 65% on side A but line moves toward side B → RLM detected.
        Returns: {rlm_detected, sharp_side, confidence_boost}
        """

    def combined_signal(self, model_side, rlm_side) -> str:
        """
        Both agree → HIGH CONFIDENCE (size up 1.5x)
        Disagree → skip (conflicting signals)
        """
```

**Action Network public %** (Phase 3.5-C) feeds this. RLM + model agreement → bet tier upgrades from 2 → 1 automatically.

---

**4.8-F — Market Arbitrage: Correlated Markets**

Books price related markets independently. They're not.

```python
# src/analytics/market_arb.py

def prop_vs_team_total_arb(player_prop, team_total, player_usage):
    """
    If game total is high but player prop isn't adjusted upward:
    expected_pts = (team_total/2) * (usage_rate / 1.0) * (minutes/48)
    if expected_pts > book_prop_line + 1.5: → bet player over
    """

def first_half_vs_full_game_arb(full_game_total, first_half_total):
    """
    Implied second half = full_game - first_half
    Your model's second half total = model_q3_q4_pace + fatigue_adjustment
    If implied > model by >2 pts: → bet first half over + full game under
    """

def team_total_vs_player_stack(game_id, team):
    """
    If team total implies 118+ pts:
    → Stack: PG assists over + C rebounds over + SF points over
    All correlated with high team scoring. Books price independently.
    """
```

---

**4.8-G — Fractional Kelly + Correlation-Adjusted Portfolio Sizing**

```python
# src/analytics/portfolio_manager.py
class PortfolioManager:
    """
    Quant-grade position sizing. Never bet Kelly directly — use 25% Kelly.
    Adjusts for correlation across bets on same game/player.
    """

    KELLY_FRACTION = 0.25  # 25% Kelly — eliminates ruin risk
    MAX_SINGLE_BET = 0.02  # max 2% bankroll per bet
    MAX_GAME_EXPOSURE = 0.08  # max 8% bankroll on correlated game bets
    MAX_DAILY_RISK = 0.12   # max 12% bankroll per day
    MONTHLY_STOP_LOSS = 0.25  # if down 25% → cut sizes 50% until recovered

    def size_bet(self, edge: float, confidence: float, correlation_group: str) -> float:
        """
        edge = model_prob - implied_prob
        Returns: fraction of bankroll to bet
        Accounts for: Kelly fraction + correlated bets on same game
        """

    def size_portfolio(self, bets: list) -> list:
        """
        Given N bets today, size each accounting for:
        - Individual Kelly
        - Correlation matrix (prop_correlations.json)
        - Max game/daily exposure limits
        Returns: [{bet, size, correlation_group}]
        """
```

**Why 25% Kelly:** Even with 60% hit rate, full Kelly leads to 30%+ drawdowns in bad stretches. 25% Kelly captures 75% of theoretical growth with drawdowns under 10%.

---

**4.8-H — Seasonal Market Inefficiency Calendar**

Systematic timing of when book pricing is worst:

```python
INEFFICIENCY_WINDOWS = {
    "early_season": {
        "weeks": range(1, 7),  # Oct-Nov
        "description": "Books use preseason projections. Your model uses real game data.",
        "edge_multiplier": 1.4,  # 40% larger edges
        "priority": "bet aggressively — highest-edge window of season"
    },
    "trade_deadline": {
        "days_after": range(1, 8),  # 7 days after Feb deadline
        "description": "Role changes + new team fits. Books take 5-7 games. You take 3.",
        "edge_multiplier": 1.6,
        "priority": "bet new team player roles immediately"
    },
    "injury_return": {
        "games_after_return": range(1, 11),
        "description": "Books reset to healthy average. Your recurrence curve is better.",
        "edge_multiplier": 1.5,
        "priority": "fade returning players games 1-5"
    },
    "b2b_road": {
        "description": "B2B road games — books use static lines. Position-specific decay model.",
        "edge_multiplier": 1.25,
        "priority": "bet visiting team star unders on game 2 of road B2B"
    }
}
```

---

**4.8-I — Line Freeze Detection**

When a line stops moving while comparable markets are moving — a book has maxed exposure.

```python
# Add to line_monitor.py:
def detect_line_freeze(line_history: list, comparable_movements: list) -> dict:
    """
    If line unchanged >4h while Pinnacle moved >0.5 pts on same market:
    → Frozen book has one-sided max exposure
    → After freeze lifts, books often overcorrect
    → Bet opposite side when line unfreezes (within first 30 min)
    Returns: {frozen_book, frozen_line, pinnacle_line, freeze_duration_hours}
    """
```

---

**4.8-J — Automated Daily Execution Schedule**

The full workflow as a systematic operation:

```
05:00 — Fetch overnight line movements, injury updates, lineup news
05:30 — Run MYOL engine on tonight's full slate → generate all model lines
06:00 — ArbDetector: find middles + stale lines → flag immediate bets
06:30 — BetFilter: score all props by confidence tier → output bet list
07:00 — [BETTING WINDOW 1] Opening lines: Tier 1 bets placed (highest CLV)
08:00 — Beat reporter monitor starts (morning shootaround window)
08:00 — Line movement monitor: track steam + RLM detection starts
10:00 — [BETTING WINDOW 2] RLM-confirmed bets + model agrees → place Tier 1+2
12:00 — Re-run models with updated injury/lineup info → flag new discrepancies
16:00 — Official injury report publishes → parse within 60 seconds
16:05 — [BETTING WINDOW 3] Injury-affected props → highest edge window (78%+ hit rate)
17:00 — [BETTING WINDOW 4] Liquidity peak — Tier 2+3 bets placed (best prices)
17:30 — Portfolio manager: check total exposure, correlation limits, daily max
19:30 — Games start → live betting mode (Phase 11)
23:00 — Log all bets: bet_line, closing_line, result → CLV update
23:30 — Weekly CLV report if Sunday → model accuracy signal

AUTOMATED: Beat reporter monitor (continuous), line movement alerts (real-time), injury alerts (real-time)
```

Build as `src/execution/daily_workflow.py` — orchestrates all components above.

---

**Success Criteria:**
1. MYOL generates lines for all props before any book is consulted — daily slate in <60 seconds
2. CLV tracker live — every bet logged with opening line + closing line + result
3. ArbDetector finds middles/stale lines automatically — tested on 30-day historical data
4. Portfolio manager enforces all exposure limits — no single day exceeds 12% bankroll risk
5. RLM detector correctly identifies sharp money on 80%+ of known historical steam moves
6. Seasonal inefficiency calendar flags active windows daily
7. Daily execution schedule runs as automated cron with alert system for manual review
8. After 90 days: CLV report shows avg CLV > +0.8 pts on props → confirms positive EV
9. Market timing rules active — stat-specific bet windows followed (game totals: 24-48h; props: 4-6h)
10. Alternate line scanner running — identifies mechanically-priced alternate line value daily
11. Team total math check running — flags when team totals don't sum to game total correctly
12. Injury report filing time monitor active — polling NBA API at 4:55pm ET daily

---

**4.8-K — Market Timing Rules**

Not all bets should be placed at the same time. Different markets have different optimal windows.

```python
BET_TIMING_RULES = {
    "game_totals":    "24-48h before tip — sharpest price available early",
    "game_spreads":   "24-48h before tip — same as totals",
    "player_props":   "4-6h before tip — most liquid, best vig, latest injury info",
    "live_props":     "first 90 seconds of each quarter — books slowest to update",
    "sgp":            "2-4h before tip — books still building correlation adjustments",
    "injury_reaction": "immediately — 15-minute window before books adjust",
    "opening_lines":  "within 60 minutes of posting — softest before steam",
}
# Wire into daily_workflow.py: each bet type routes to its optimal window
```

---

**4.8-L — Alternate Line Value Scanner**

Books price alternate lines mechanically (+1 pt = -15 cents). Your model finds where this is wrong.

```python
# src/analytics/alt_line_scanner.py
def scan_alternate_lines(player, stat, model_prob_curve) -> list:
    """
    For every alternate line the book offers:
    1. Get book's implied probability (from odds)
    2. Get your model's probability (from quantile curve — Phase 4.7-G)
    3. If model_prob > book_implied_prob + min_edge: flag as bet

    Example:
    Tatum main line: over 27.5 at -110 (52.4% implied)
    Your model: P(>27.5) = 57% → +4.6% edge → bet
    Alternate:   over 24.5 at -185 (64.9% implied)
    Your model: P(>24.5) = 78% → +13.1% edge → MUCH better
    Books price alternate lines lazily. Quantile model finds the best line.
    """
```

---

**4.8-M — Team Total Implied Math Check**

```python
# src/analytics/market_arb.py — add to existing:
def check_team_total_math(game_total, home_team_total, away_team_total) -> dict:
    """
    game_total should = home_team_total + away_team_total (approximately).
    When they don't add up → mathematical edge.

    Example:
    Game total: 228 → implies home ~117, away ~111
    Book's home team total: 119.5 (2.5 pts too high)
    Book's away team total: 113.5 (2.5 pts too high)
    → Combined implied = 233 vs actual 228
    → Bet UNDER on both team totals (mathematical certainty of value)

    Run on every game every day. Occurs 3-5x per week.
    """

def prop_vs_team_total_arb(player_stats, team_total, lineup) -> list:
    """
    If game total is high but player props aren't adjusted:
    expected_pts = (team_total/2) * usage_rate * (minutes/48)
    If expected > book_line + 1.5: → bet over
    """
```

---

**4.8-N — Injury Report Filing Time Monitor**

```python
# src/data/injury_monitor.py — add to existing:
def monitor_nba_injury_report_filing():
    """
    NBA teams file injury reports by 5pm ET.
    Some teams file consistently at 4:57pm. Others at exactly 5:00pm.
    Poll NBA API endpoint directly every 60 seconds starting 4:45pm.
    First team to file = 3-13 minute head start on late filers.

    Separately: monitor NBA official CDN URL for PDF update timestamp.
    When PDF timestamp changes → parse immediately → alert affected props.
    """
```

---

### Phase 4.9: Backtesting + Validation Infrastructure
**Goal**: Build the quantitative validation layer that sits between model output and real money. Every strategy must be backtested and paper-traded before live bets. This is the most critical missing infrastructure piece.
**Depends on**: Phase 4.8 (MYOL + CLV systems), Phase 3.5-C (historical prop results)
**Status**: 🔲

**Why this phase exists:** Without it, you have no way to know if your edges are real. Model accuracy metrics (MAE, Brier) tell you if the model is good. Backtesting tells you if the *strategy* makes money. These are different things. Every quant fund gates real money behind a paper trading period.

---

**4.9-A — Historical Prop Results Database**

You need ground truth: what was the closing line AND what was the actual result for every prop.

```python
# src/data/prop_results_scraper.py
class PropResultsScraper:
    """
    Scrapes historical prop results (bet line + actual stat + over/under result).
    Sources: OddsPortal historical props, PropGuru, or manual from DK/FD exports.
    Covers: 2021-22 → present (3 seasons minimum, 6 seasons ideal)
    """
    def fetch_historical_props(self, season, stat) -> list:
        # Returns: [{player, date, book, line, actual_stat, over_under_result, closing_line}]
        # Store to: data/external/prop_results_{season}.json
```

This data enables:
- True hit rate measurement per model/segment/market
- CLV backtesting (did you beat closing lines historically?)
- BetFilter training (what features predict model correctness?)
- Seasonal inefficiency window validation

---

**4.9-B — Strategy Backtester**

```python
# src/backtesting/strategy_backtester.py
class StrategyBacktester:
    """
    Replays any betting strategy on historical data.
    Simulates exactly: what you would have bet, at what price,
    with what result, and what CLV you captured.
    """
    def backtest_prop_model(self, model, seasons, min_edge=0.75) -> BacktestResult:
        """Walk-forward backtest — never use future data to inform past predictions."""

    def backtest_market_edge(self, edge_type, seasons) -> BacktestResult:
        """Backtest any market structure edge: middles, stale lines, RLM, etc."""

    def backtest_seasonal_window(self, window_type, seasons) -> BacktestResult:
        """Early season, trade deadline, injury return — validate each window."""

    def backtest_bet_filter(self, confidence_threshold, seasons) -> BacktestResult:
        """Does top-X% confidence actually hit Y%? Validate the BetFilter."""

@dataclass
class BacktestResult:
    total_bets: int
    hit_rate: float
    roi: float           # return on investment
    clv_avg: float       # average closing line value captured
    sharpe: float        # risk-adjusted return
    max_drawdown: float  # worst peak-to-trough
    by_segment: dict     # breakdown by stat/player type/book/season
```

**Validation rules:**
- All backtests must be walk-forward (train on past, test on future, no lookahead)
- Must cover minimum 500 bets per strategy to be statistically significant
- Strategies with Sharpe < 0.5 are not deployed live
- Strategies with max_drawdown > 30% are not deployed live

---

**4.9-C — Paper Trading Mode**

```python
# src/execution/paper_trader.py
class PaperTrader:
    """
    Full simulation of the live betting operation.
    Generates all bet recommendations daily.
    Records what the closing line was.
    Tracks simulated P&L as if real money was bet.
    Gate: run for minimum 6 weeks / 300 bets before going live.
    """
    LIVE_GATE = {
        "min_bets": 300,
        "min_clv": +0.6,       # avg CLV must be > +0.6 pts
        "min_hit_rate": 0.535,  # above break-even on -110
        "max_drawdown": 0.20,   # simulated drawdown must stay under 20%
        "min_weeks": 6
    }

    def run_daily(self, game_date: str):
        """Runs full recommendation pipeline, records without placing bets."""

    def gate_check(self) -> tuple[bool, str]:
        """Returns (ready_for_live, reason). All criteria must pass."""

    def generate_report(self) -> dict:
        """Daily paper trading report: CLV, hit rate, ROI, drawdown, by segment."""
```

**Rule:** Do not bet real money until paper trading gate passes. No exceptions.

---

**4.9-D — P&L Ledger + Tax Records**

```python
# src/execution/ledger.py
class BettingLedger:
    """
    Complete financial record of every bet placed.
    Required for: tax reporting, performance analysis, account tracking.
    """
    def log_bet(self, book, player, stat, side, amount, line, timestamp): ...
    def log_result(self, bet_id, actual_stat, won: bool, payout): ...
    def log_closing_line(self, bet_id, closing_line): ...

    def pnl_report(self, period) -> dict:
        # actual_pnl, theoretical_clv_pnl, variance_explanation
        # by book, by market type, by model tier

    def tax_report(self, year) -> dict:
        # All winning bets, total income, total losses (deductible)
        # W-2G equivalent records — required for IRS reporting
        # Store: data/ledger/bets_{year}.json (never delete, never in git)
```

**Tax note:** Gambling income is ordinary income. Gambling losses are deductible only up to winnings. Keep bet-by-bet records from day one — this is a legal requirement once profitable at scale.

---

**4.9-E — Account Health Manager**

```python
# src/execution/account_manager.py
class AccountManager:
    """
    Manages betting accounts across all books.
    Books limit/ban profitable bettors — this is the #1 operational risk.
    """
    BOOK_ROSTER = [
        "DraftKings",    # mainstream, mid-limit
        "FanDuel",       # mainstream, mid-limit
        "ESPNBet",       # softest — least likely to limit
        "Fanatics",      # softest — new, want action
        "BetMGM",        # mainstream
        "Caesars",       # mainstream
        "Pinnacle",      # sharpest — CLV benchmark only, low limits
    ]

    ANTI_LIMIT_RULES = {
        "max_bet_pct": 0.40,      # never bet more than 40% of book's posted limit
        "round_numbers": False,    # always use odd amounts ($107 not $100)
        "timing_vary": True,       # vary bet times — don't always bet at line open
        "book_rotate": True,       # spread same edge across multiple books
        "soft_book_priority": ["ESPNBet", "Fanatics"],  # bet here first, hardest to limit
    }

    def log_limit(self, book, market, new_max): ...
    def recommend_book(self, market_type, bet_size) -> str:
        """Routes bet to best available book given current limits."""
    def limit_alert(self, book) -> str:
        """Fires when a book reduces your max bet — adjust routing immediately."""
```

---

**Success Criteria:**
1. Historical prop results database covers 3+ seasons — validated against known outcomes
2. Strategy backtester produces walk-forward results for all 7 prop models — hit rates match paper trading
3. Paper trading gate: 300 bets, 6 weeks, avg CLV > +0.6 pts before any live bet
4. P&L ledger logging every bet from day one — tax records complete
5. Account manager routing bets to optimal book — limit events trigger alerts
6. All strategies deployed live have Sharpe > 0.5 and max drawdown < 20% in paper trading

---

### Phase 5: External Factors Scraper
**Goal**: Injury status, referee tendencies, line movement — systematically underpriced by books.
**Depends on**: Phase 1

1. injury_monitor.py — poll NBA official + Rotowire every 30 min
2. ref_tracker.py — daily assignments + historical pace/foul/home-win% + micro-tendencies (see below)
3. line_monitor.py — The Odds API, opening vs closing, sharp money signal
4. news_scraper.py — ESPN headline keyword monitor
5. **[ADD] schedule_strength.py** — remaining schedule strength per team, game importance score (playoff implications, elimination, rivalry, dead rubber detection)
6. **[ADD] beat_reporter_monitor.py** — Twitter/X keyword monitor for ~150 beat reporters (5 per team). Alert within 30 seconds of injury tweet. Highest-edge information window.
7. **[ADD] travel_model.py** — direction-aware travel fatigue (east→west -1.1pts, west→east +0.4pts, red-eye -1.8pts). Not just travel miles — travel direction. Derive from arena coordinates + game schedule.

**Referee Micro-Tendencies (extend ref_tracker.py beyond pace/foul rate):**
```python
ref_micro_features = {
    "offensive_foul_rate":    float,  # charges vs blocking calls ratio
    "q4_whistle_swallow":     float,  # fouls/possession in Q4 vs Q1-Q3 (some refs let it go late)
    "star_protection_rate":   float,  # FTA rate when star drives vs role player drives
    "back_to_back_ref_flag":  bool,   # ref on their own B2B — tired refs call fewer fouls
    "crew_sync_score":        float,  # how many times this exact crew has worked together
    "home_bias_by_team":      dict,   # some refs have documented team-specific home bias
}
# Source: PBP foul event analysis across 6 seasons + ref assignment records
# Edge: star foul-drawers on high-star-protection refs → pts boost
#       Q4 whistle-swallowing refs → under on pts in close games
#       B2B refs → suppress total (fewer fouls = fewer FTA = fewer pts)
```

**Success Criteria:**
1. All external features as columns in model inputs
2. Model accuracy delta measured with/without (+1-2% expected on props)
3. Beat reporter monitor fires within 60 seconds of injury tweet
4. Game importance score available for all games on slate
5. Referee micro-tendencies computed for all active refs — star_protection_rate + q4_whistle_swallow in prop model inputs
6. Travel direction model active — east→west road games flagged with suppression multiplier

---

### Phase 6: Full Game Video Processing + Rich Event Capture
**Goal**: 20+ complete 48-minute broadcast games, PostgreSQL wired, shots enriched, AND all rich tracker events captured into per-game per-player summary tables.
**Depends on**: Phase 2.5 (tracker quality), Phase 1 (PostgreSQL), Phase 4.6 (signal wiring)

**Critical tasks:**
- Wire PostgreSQL writes (ISSUE-018) — every run currently overwrites tracking_data.csv
- Run 20+ games with --game-id flags so shots get outcomes
- Per-game M1 homography from Phase 2.5 must be working first

**6-NEW: Rich Event Aggregation Pipeline**

`EventDetector.events` fires `screen_set`, `cut`, `drive`, `closeout`, `rebound_position` events every game but they're never stored or aggregated. Build `src/pipeline/event_aggregator.py`:

```
After each game processed → read EventDetector.events log →
aggregate per player per game:

drives_per_36            = drive_events.count * (36 / minutes_played)
avg_drive_distance       = mean(drive.end_x - drive.start_x)
box_out_rate             = box_out_events.count / shots_while_on_court
avg_crash_speed          = mean(rebound_position.crash_speed)
avg_crash_angle          = mean(rebound_position.crash_angle) — optimal = 90°
screens_set_per_36       = screen_set_events.count * (36 / minutes_played)
cuts_per_36              = cut_events.count * (36 / minutes_played)
closeout_speed_allowed   = mean(closeout.closeout_speed) — when player shot, how fast was closeout?
avg_pressure_score       = mean(defense_pressure.csv[player_frames])
avg_possession_type      = mode(possession_type when player had ball)
paint_touches_per_36     = sum(paint_touches) * (36 / minutes_played)
off_ball_distance_per_36 = sum(off_ball_distance) * (36 / minutes_played)
shot_clock_at_shot_avg   = mean(shot_clock_est at player's shot frames)
```

Store to: `data/player_game_events/{game_id}_{player_id}.json`
Aggregate across games to: `data/player_career_events/{player_id}.json`

**Why this matters**: These aggregated metrics become the NEW features in prop models, xFG v2, rebound models, and the possession simulator. Without this aggregation step, rich events are detected but never used.

**Success Criteria:**
1. 20+ full games processed end-to-end
2. ≥200 shots with outcome + court coordinates + defender distance
3. ≥500 possessions labeled with result
4. All outputs in PostgreSQL — no CSV overwrites
5. Both teams labeled correctly in all outputs
6. ≥70% of players identified via OCR + roster lookup
7. Per-game event summary JSON generated for every player in every processed game
8. `drives_per_36`, `box_out_rate`, `closeout_speed_allowed`, `crash_speed_avg` available for all players with ≥5 games processed

---

### Phase 7: Tier 2-3 ML Models (20 Games) + CV Signal Integration
**Goal**: Add CV spatial context to base models. First models that beat public analytics. Wire all rich event aggregates into the models that should use them.
**Depends on**: Phases 4.6, 6 (events aggregated)

**Tier 2 — Shot Charts + NBA API (5 models) — already trained ✅:**
1. xFG v1 — location only (court_x, court_y, shot_type, distance) ✅
2. Shot zone tendency per player ✅
3. Shot volume by zone ✅
4. Clutch efficiency model ✅
5. Shot creation classifier (catch-and-shoot vs off-dribble) ✅

**Tier 3 — CV Data (10 models):**
1. **xFG v2** — location + `defender_distance` + `shooter_velocity` + `team_spacing` + `closeout_speed_allowed` + `shot_clock_at_shot` + `fatigue_penalty` + possession_type
   - `closeout_speed_allowed` from Phase 6 rich events — fastest defender approaching at shot time
   - `shot_clock_at_shot` from PossessionClassifier — late clock dramatically reduces P(make)
   - `fatigue_penalty` from velocity_mean_90 / velocity_mean_150 — tired players miss more
   - Expected AUC: 0.65 → 0.73+
2. **Shot selection quality** — was this the right shot? (xFG v2 × possession_type × shot_clock_est)
3. **Play type classifier** — ISO/PnR/Post/C+S/Transition — from CV possession_type + synergy ground truth
4. **Defensive pressure score** — per possession, from defense_pressure.py output + help_rotation_latency
5. **Spacing rating** — team_spacing convex hull × off_ball_distance + cut_frequency
6. **Drive frequency model** — `drives_per_36` from Phase 6 aggregation → predicts FTA rate
   - Wire into pts prop model: `drives_per_36 * historical_foul_rate * ft_pct = FTA_pts_add`
7. **Open shot rate** — fraction of shots with `avg_defender_dist > 4ft` from shot_dashboard + CV
8. **Transition frequency** — `fast_break` + `transition` possession_type counts per game
9. **Off-ball movement model** — `off_ball_distance_per_36` + `cuts_per_36` per player → AST opportunities
   - Wire into AST prop model as feature: high off-ball movers generate more catch-and-finish scenarios
10. **Possession value model** — expected pts per possession given possession_type + lineup + matchup

**7-NEW: Re-train Prop Models with CV Features (5 → 10 games threshold)**

Once 5+ games processed for a player, add to their prop feature vector:
```
drives_per_36           → pts model (paint scorer vs perimeter scorer)
avg_drive_distance      → FTA rate (longer drives = more contact)
box_out_rate            → reb model (direct reb positioning quality)
avg_crash_speed         → reb model (effort metric — who fights harder)
closeout_speed_allowed  → pts model (defenders close out slower on this player = easier shots)
off_ball_distance_per_36→ ast model (teams with moving off-ball generate more assists for handler)
paint_touches_per_36    → pts model (paint scorers are more foul-prone = FTA)
shot_clock_at_shot_avg  → pts model (players who wait too long get bad shots)
screens_set_per_36      → ast model (screeners create handler opportunities)
avg_pressure_score      → all props (high-pressure games = lower efficiency across board)
```

This upgrades prop models from pure statistics to **behavioral profiles** — not just "how much did he score" but "how does he score, and does tonight's matchup suit that style."

**Success Criteria:**
1. xFG v2 AUC > 0.73 (vs v1 at 0.65) — improvement confirmed by Brier score
2. `closeout_speed_allowed` and `shot_clock_at_shot` rank in xFG top-5 features (SHAP)
3. Play type classifier accuracy > 80% on labeled possession holdout
4. Prop models retrained with CV features — pts MAE < 0.22
5. `drives_per_36` correlates with FTA rate R² > 0.55 (validation)
6. `box_out_rate` + `crash_speed` improve reb model MAE from 0.11 → < 0.08

---

### Phase 8: Possession Simulator v1
**Goal**: Chain the 7 core models into a possession-level game simulator. The central piece everything else plugs into.
**Depends on**: Phase 7

**7 chained models:**
1. **Play Type Selector** — given lineup + game state + `synergy_pnr_ppp` + `possession_type` distribution → play type probability vector
2. **Shot Selector** — given play type + `drives_per_36` + `synergy_iso_ppp` + `shot_zone_tendency` → who shoots + zone
3. **xFG Model** (v2) — given shooter + location + `closeout_speed_allowed` + `shot_clock_at_shot` + `team_spacing` + `fatigue_penalty` → P(make)
4. **Turnover/Foul Model** — P(shot) / P(TO) / P(foul) per possession, informed by `avg_pressure_score` + `ref_fta_tendency`
5. **Rebound Model** — who gets rebound given `box_out_rate` + `crash_speed` + `crash_angle` + `rebound_position` proximity
6. **Fatigue Model** — efficiency multiplier from `dist_per100` + `velocity_mean_150` decay + minutes + `games_in_last_14`
7. **Lineup Substitution Model** — when/who subs based on foul + fatigue + score + coach-specific `load_management` patterns

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

**[GAP FIX] Feedback Loop Architecture — define before building:**

The loop only works if you know exactly when/what/how to retrain. Design decisions to lock in:

**Retraining triggers (per model):**
| Model | Retrain when | Validation gate |
|---|---|---|
| xFG v2 | +50 new shots accumulated | Brier score must improve vs current |
| Props (pts/reb/ast) | +10 new game logs per player | Walk-forward MAE must not regress >5% |
| Win probability | +100 new game outcomes | Accuracy must stay ≥ 67.7% |
| Play type classifier | +200 new labeled possessions | Accuracy must stay ≥ 80% |
| Fatigue curve | +5 new games per player | Correlation must stay ≥ 0.45 |
| Live LSTM | +20 new full games | AUC must stay ≥ 0.75 |

**Validation gate (before any model promotion):**
1. New model evaluated on last 20% of data held out (time-ordered, not random)
2. Must beat current production model on primary metric
3. Must not catastrophically fail on any player/team subgroup (max 2x error)
4. If gate fails → rollback to previous version, flag for manual review

**Model versioning scheme:**
- Each trained model saved as `data/models/{model_name}_v{N}.pkl` + metadata JSON
- `data/models/{model_name}_current.pkl` symlink → promoted version
- `data/models/model_registry.json` → `{model_name: {current_version, trained_date, metric, n_samples}}`
- Never overwrite a promoted model — always write new version first

**Drift detection:**
- Input feature distributions tracked with rolling Z-score (window=30 games)
- If any feature drifts >2 sigma from training distribution → alert + schedule retrain
- Example: if player's usage suddenly spikes 40% due to injury (new role), model needs update

**What NOT to auto-retrain:**
- Win probability (too slow, needs manual review of feature importance)
- NLP models (domain shift risks, manual validation required)
- Anything with R² < 0.40 (not enough signal to trust auto-retrain)

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

**Betting Infrastructure (extends Phase 4.8 quant stack):**
- The Odds API integration — spread, ML, totals, player props (already built)
- betting_edge.py — edge = model_prob − implied_prob, star ratings 1-3★
- Fractional Kelly (25%) + correlation-adjusted portfolio sizing (Phase 4.8-G)
- CLV tracking live — primary performance metric (Phase 4.8-B)
- Cross-book arb + middle detection automated (Phase 4.8-C)
- RLM detector wired into confidence tier upgrade (Phase 4.8-E)
- MYOL engine live for all markets (Phase 4.8-A)
- Daily execution schedule automated as cron (Phase 4.8-J)
- Book limit tracker — flag accounts getting limited
- Account diversification — spread across 5+ books to avoid limits

**Live In-Game Models (M70-M75) — build in this phase:**
1. **Live prop updater (M70)** — Bayesian update: pre-game sim prior + halftime box score → full game projection. Exploits book's slow live prop adjustment
2. **Comeback probability (M71)** — P(team trailing by X with Y minutes recovers) → live spread edge
3. **Garbage time predictor (M72)** — P(game decided, starters pulled in Q4) → kills prop bets when game is a blowout. Don't count garbage time stats
4. **Foul trouble model (M73)** — Markov chain: P(player fouls out given N fouls at halftime) → affects lineup + usage
5. **Q4 star usage model (M74)** — does coach increase usage in close 4th? Historical by coach + player
6. **Momentum run detector (M75)** — P(team goes on 8-0 run from this state) → live totals edge

**Target markets (highest edge):**
1. Role player props — spatial model vs lazy book pricing
2. Injury reaction window — 15-60 min lag exploit (beat reporter monitor from Phase 5)
3. Same-game parlays — correlation matrix vs independence assumption
4. Back-to-back fatigue props — player-specific curves
5. Live halftime props — M70 live updater vs slow book
6. DFS lineup optimization — projection quality vs free tools
7. Roster opportunity window — star DNP → beneficiary props (Phase 4.5 M41)
8. Early season props — books use preseason projections, model uses real data
9. Post-trade deadline props — 7-day window after Feb deadline

**[ADD] DFS Optimizer (no limits, no banning)**

DraftKings/FanDuel DFS cannot limit or ban profitable players. It's skill-based competition. All existing models apply directly.

```python
# src/prediction/dfs_optimizer.py
class DFSOptimizer:
    def optimize_cash_lineup(self, salary_cap=50000) -> list:
        """Cash (50/50): highest floor projections. Use BetFilter top-tier only."""

    def optimize_gpp_lineups(self, n=150) -> list:
        """
        GPP (tournament): contrarian + correlated stacks.
        Your prop_correlation matrix = massive GPP edge.
        Find low-owned correlated stacks books haven't priced correctly.
        Most DFS tools don't have your spatial data or correlation model.
        """

    def ownership_projection(self, player_id) -> float:
        """Estimate public ownership % — fade high-owned in GPP."""

    def stack_builder(self, game_id) -> list:
        """
        Build correlated stacks from same game.
        QB+WR analog: PG+C (PnR), PG+SF (ball movement), team stack on high total.
        """
```

**[ADD] Monitoring + Alert System**

```python
# src/monitoring/
├── data_health.py    # scraper freshness, last fetch times, missing data alerts
├── model_health.py   # CLV trend, 7-day rolling hit rate, drift detection
├── edge_alerts.py    # SMS/push when Tier 1 edge found or injury window opens
├── pipeline_health.py # game processing queue, PostgreSQL writes, disk space
└── limit_alerts.py   # book limit detected → reroute immediately

# Alert types:
# CRITICAL: injury news detected → affected props flagged within 60 seconds
# HIGH:     stale line found (book >1.5pts off Pinnacle) → bet immediately
# MEDIUM:   model CLV below +0.5 for 10+ consecutive days → investigate
# LOW:      data pipeline delay >24h → check scraper
```

**[ADD] Performance Dashboard (internal)**

```python
# src/analytics/performance_dashboard.py
# Daily report covering:
# - Actual P&L vs theoretical CLV P&L (variance explained)
# - Hit rate by model tier, stat type, book, season window
# - CLV trend (7-day, 30-day, season)
# - Top edges today (sorted by confidence tier)
# - Account status (which books still accepting full action)
# - Model health (drift alerts, retraining queue)
# - Paper trading status if pre-live
```

**[ADD] Data Backup Strategy**

```
Automated daily backup (add to Phase 17 cron but implement from Phase 6):
- data/nba/ → cloud storage (S3/Backblaze B2) daily sync
- data/models/ → versioned backup after every training run
- data/external/ → weekly sync (changes slowly)
- data/ledger/ → real-time sync (financial records — never lose)
- PostgreSQL → nightly pg_dump → compressed → cloud
- Never commit large data files to git (already in .gitignore ✅)
```

**Success Criteria:**
1. Live lines available for all major books within 60 seconds
2. Edge computed and star-rated for every prop + game
3. Kelly sizing accounts for correlated bets (M32)
4. CLV backtesting shows positive edge retention on flagged bets
5. Live prop updater runs within 3 seconds of halftime box score available
6. Garbage time predictor accuracy > 85% on holdout
7. DFS optimizer producing lineups — cash lineup floor > 60th percentile on holdout
8. Alert system fires within 60 seconds of injury tweet detected
9. Performance dashboard running — daily P&L vs theoretical CLV reconciled
10. Data backup running daily — recovery test passes (can restore all data from backup)

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
| 4.6 | 7 | **Prop models retrained (52-feat)**, win prob retrained, game models retrained, matchup model retrained (w/ zone+synergy_def), shot quality (w/ shot_clock+fatigue), momentum→prop wiring, pressure→prop wiring | Existing caches (no new data) | 🔲 Phase 4.6 |
| 6 | 10 | xFG v2 (+closeout_speed+shot_clock+fatigue_penalty), shot selection quality, play type classifier, defensive pressure, spacing, drive frequency (→FTA model), open shot rate, transition freq, off-ball movement (→AST model), possession value | 20 CV full games + rich event aggregation | 🔲 Phase 7 |
| 6B | 3 | **Drive→FTA→pts model** (drives_per_36 × foul_rate × ft_pct), **Box-out rebound model** (box_out_rate + crash_speed + crash_angle), **Closeout suppression model** (closeout_speed_allowed → shot quality baseline) | 20 CV games rich events | 🔲 Phase 7 |
| 7 | 8 | Fatigue curve, rebound positioning, late-game efficiency, closeout quality, help defense, ball stagnation, screen effectiveness, turnover under pressure | 50 CV full games | 🔲 Phase 10 |
| 8 | 7 | Lineup chemistry, defensive matchup matrix, substitution timing, momentum, foul drawing rate, second chance, pace per lineup | 100 CV full games | 🔲 Phase 10 |
| 8B | 4 | Injury NLP, injury lag, team chemistry sentiment, reporter credibility | Reddit + RotoWire | 🔲 Phase 9 |
| 9 | 6 | Live prop updater, comeback probability, garbage time, foul trouble, Q4 usage, momentum run | Live data feed | 🔲 Phase 11 |
| 10 | 7 | Full simulator, live LSTM, true player impact, lineup optimizer, prop pricing engine, regression detector, injury impact | 200 CV full games | 🔲 Phase 12/16 |
| **Total** | **92** | | | |

Plus 8 Tier 0 computed schedule features = **100 total model outputs**

**New models added vs original plan (18 additions):**
- Tier 4.6: 7 retrained/wired models from existing cache (immediate — no new data)
- Tier 6B: 3 new CV behavioral models (drives→FTA, box-out reb, closeout suppression)
- Master Prediction Formula: upgraded from 6 → 7 layers (Layer 3 = behavioral profile, new)
- Prop model feature count: 30 → 52 (22 new features from existing caches)

---

## Data Volume Milestones

| Games / Data | Models Unlocked | Key Capability Added |
|---|---|---|
| Phase 3 ✅ (NBA API complete) | Tiers 1+2 (18 models) | Win prob + props + xFG v1 |
| Phase 3.5 (untapped APIs + BBRef) | Tiers 2B+3+4+5 (22 models) | Sharp signal, lifecycle, play type efficiency |
| **Phase 4.6 (wire existing caches)** | **Tier 4.6 (7 models, zero new data)** | **Props 30→52 features, prop MAE -30%, immediate gain** |
| Phase 6 (20 full CV games + rich events) | Tier 6+6B (13 models) | xFG v2 + drives→FTA + box-out reb + closeout suppression |
| Phase 9 (NLP live) | Tier 8B (4 models) | Injury lag, sentiment |
| Phase 10 (50-100 CV games) | Tiers 7+8 (15 models) | Fatigue curves, lineup chemistry, matchup matrix |
| Phase 11 (live feed) | Tier 9 (6 models) | Live props, garbage time, comeback |
| Phase 12 (all models) | Tier 10 — simulator | Full 100-model Monte Carlo |
| Phase 16 (200+ CV games) | Tier 10 final | Live LSTM, prop pricing engine |
| 1,000 CV games | Quality converges | Noise averages out, xFG ~66% correlation |

---

## The Master Prediction Formula

> Full detail: `vault/Concepts/Prediction Pipeline.md`

Every prediction runs through 6 layers in sequence:

```
LAYER 1 — GAME CONTEXT
Win prob + pace + total + ref tendency + ref_fta_tendency + ref_pace_tendency
+ altitude + schedule + line movement + sharp signal
+ home/away hustle_avg + synergy_pnr_ppp matchup head-to-head
    ↓
LAYER 2 — PLAYER CONTEXT (52-feature prop vector)
Rolling form (Bayesian) + zone tendency + usage + matchup history (matchups_*.json)
+ clutch + DNP risk + contract year + cap_hit_pct
+ VORP + WS/48 + on_off_diff + synergy_iso/pnr/spotup_ppp
+ contested_shot_pct + pull_up_pct + catch_and_shoot_pct + avg_defender_dist
+ rest_days + travel_miles + games_in_last_14 + ref_fta_tendency
+ defender_zone_fg_allowed + def_synergy_iso_allowed + matchup_fg_allowed
    ↓
LAYER 3 — BEHAVIORAL PROFILE (Phase 6+ — CV rich events)
drives_per_36 → FTA projection (+pts)
box_out_rate + crash_speed + crash_angle → reb projection
off_ball_distance_per_36 + cuts_per_36 → ast opportunities
closeout_speed_allowed → shot quality baseline for this player
paint_touches_per_36 → paint scoring rate + foul drawing
screens_set_per_36 → ball handler ast boost
shot_clock_at_shot_avg → late-clock shot tendency (quality penalty)
avg_pressure_score → efficiency under defensive attention
    ↓
LAYER 4 — SPATIAL CONTEXT (Phase 6+)
xFG v2 per zone vs tonight's defense + closeout_speed at shot + shot_clock decay
+ defensive pressure score + team_spacing + fatigue_penalty (velocity decay)
+ possession_type distribution + help_rotation_latency
    ↓
LAYER 5 — EXTERNAL FACTORS
Injury cascade (who's out → who's up) + ref foul tendency + line movement signal
+ NLP severity (Phase 9) + return-from-injury curve + momentum shift flag
    ↓
LAYER 6 — MONTE CARLO SIMULATION
7-model possession chain (play type → shot selector → xFG v2 → TO/foul
→ rebound w/ crash_speed → fatigue w/ velocity_decay → substitution)
× 10,000 = full stat distribution per player
    ↓
LAYER 7 — MARKET COMPARISON
Model P(over) vs book implied P(over) = edge
Prop correlation matrix → correlated leg adjustment
Kelly sizing → bankroll fraction
Sharp confirmation (Action Network) → confidence modifier
CLV check: did line move in model's direction after open?
→ Final: bet/no-bet, size, which book, star rating
```

**Prediction accuracy by phase:**
- Phase 4 (today): ~55-58% props. Small edge on role player props.
- Phase 4.6 (52-feature retrain, no new data): ~57-60%. Immediate gain from wiring existing cache.
- Phase 6 (20 games + rich events): ~60-63% with drives/box-outs/closeouts wired.
- Phase 7 (xFG v2 + behavioral profiles): ~62-65% — behavioral profiles beat pure statistics.
- Phase 10 (100 games): ~63-67% with lineup chemistry + full matchup matrix.
- Phase 12 (full stack): ~65-69% on targeted props. +10-15% edge on best bets.
