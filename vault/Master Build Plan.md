# Master Build Plan — NBA AI System
> **Goal: 100-model self-improving NBA prediction system. Every game processed makes every model better. Full 2024-25 season in one weekend via rolling pipeline.**
> Last updated: 2026-03-19
> Budget: $160-200 cloud GPU total (rolling pipeline, no bulk storage needed)

---

## The Vision in One Sentence

Process every NBA game through a CV tracker, extract spatial features no public tool has, combine with every available data source, run 100 ML models, beat closing lines by +2.8-4.2 pts average CLV, and let the system retrain itself nightly forever.

---

## Current Status

| Phase | Status | Notes |
|---|---|---|
| A — Data Collection | ✅ | Shot dashboard pull running (bug fixed 2026-03-19) |
| B — Wire + Retrain | ✅ | Props retrained with shot dashboard features |
| C — Infrastructure | ✅ | migrations.py + tasks.py + batch_process.py built |
| D — Self-Improving Pipeline | ✅ | event_aggregator + outcome_recorder + auto_retrain + model_version_manager |
| E — API + Dashboard + Models | ✅ | 10 endpoints, 9 tests, predictions_tab.py, 6 Phase 4.5 pkl files |
| F — Tracker Optimizations | ✅ | TensorRT + imgsz=480 + pose interval + stationary skip + PyAV |
| G — 10 Local Test Games | 🔲 | Next: record 10 games with OBS, verify full loop |
| H — Full Season Rolling Pipeline | 🔲 | RunPod A100, 1,230 games, rolling download→process→delete |

---

## Architecture Overview

```
RAW DATA → AVAILABILITY → GAME CONTEXT → MATCHUP → PROJECTIONS → EDGE → SIZING
```

Every downstream layer conditions on every upstream output. Nothing runs independently.

```
DATA SOURCES                    PROCESSING                   OUTPUTS
────────────────                ────────────────             ────────────────
NBA API (3 seasons)  ──────►   Layer 1: Availability   ──►  dnp_prob, proj_min
Shot Dashboard       ──────►   Layer 2: Game Context   ──►  pace, total, spread
PBP (3,627 games)    ──────►   Layer 3: Matchup        ──►  matchup_pts_adj
Shot Charts (221K)   ──────►   Layer 4: Baselines      ──►  proj_pts/reb/ast...
Hustle / On-Off      ──────►   Layer 5: Correlations   ──►  normalized projections
BBRef VORP/WS48      ──────►   Layer 6: Edge Detection ──►  edge%, CLV, sharp_signal
Injury Reports       ──────►   Layer 7: Sizing         ──►  bet list, DFS lineup
Current Props Lines  ──────►
CV Tracking          ──────►   (powers Layers 3, 4, 5 after 20+ games)
```

---

## Complete 100-Model System

### Layer 1 — Availability Models (run first, gate everything)

| #   | Model                  | Key Inputs                                                | Output                       | Status           |
| --- | ---------------------- | --------------------------------------------------------- | ---------------------------- | ---------------- |
| M01 | DNP Predictor          | injury report, gamelogs, rest, BBRef injury history       | dnp_prob (0-1)               | ✅ AUC=0.979      |
| M02 | Load Management        | games played, age, B2B, rest, minutes trend               | load_risk, min_reduction     | ✅ pkl            |
| M03 | Injury Return Curve    | injury type, games missed, historical return              | performance_discount (0-1)   | ✅ pkl            |
| M04 | Injury Risk            | age, minutes load, injury history, fatigue index          | future_injury_prob           | ✅ pkl            |
| M05 | Foul Trouble Predictor | historical foul rate, opp foul-drawing rate, ref tendency | foul_out_prob, min_reduction | 🔲               |
| M06 | Garbage Time Detector  | blowout prob, score differential dist, coach patterns     | garbage_time_min_lost        | 🔲               |
| M07 | Minutes Floor Model    | M01-M06 + coach sub patterns from PBP                     | proj_min (precise)           | 🔲               |
| M08 | Beneficiary Cascade    | star dnp_prob + historical minutes fill from gamelogs     | min_boost per beneficiary    | 🔲 HIGH PRIORITY |
|     |                        |                                                           |                              |                  |

### Layer 2 — Game Context Models

| # | Model | Key Inputs | Output | Status |
|---|---|---|---|---|
| M09 | Win Probability | team ratings, rest, travel, pace, recent form | home_win_prob | ✅ 69.1% |
| M10 | Game Pace | team pace, opp pace, referee pace tendency | expected_possessions | ✅ |
| M11 | Game Total | off/def rtg, pace, rest, referee | predicted_total | ✅ |
| M12 | Spread | team ratings, rest, home adv, injuries | predicted_margin | ✅ |
| M13 | First Half Model | team fast-start tendency, half pace | h1_total, h1_spread | ✅ |
| M14 | Blowout Detector | talent gap, pace, road fatigue | blowout_prob | ✅ |
| M15 | Overtime Probability | predicted margin distribution | ot_prob | 🔲 |
| M16 | Referee Tendency | historical pace, foul rate, home win%, T rate | pace_adj, foul_rate_adj | 🔲 HIGH PRIORITY |
| M17 | Back-to-Back Discount | second-night performance from gamelogs | b2b_performance_mult | 🔲 |
| M18 | Travel Impact | distance, time zones, departure time | travel_fatigue_adj | 🔲 |
| M19 | Altitude Model | Denver road team performance history | altitude_adj | 🔲 |

### Layer 3 — Player Baseline Models

| # | Model | Key Inputs | Output | Status |
|---|---|---|---|---|
| M20 | Props — Points | ~167 features: Groups A–J + PBP expanded (gamelogs, synergy, shot zones, schedule, ATS, PBP) | proj_pts | ✅ MAE=0.310 R²=0.994 |
| M21 | Props — Rebounds | same feature set | proj_reb | ✅ MAE=0.115 R²=0.995 |
| M22 | Props — Assists | same feature set | proj_ast | ✅ MAE=0.091 R²=0.992 |
| M23 | Props — 3PM | same + catch_shoot_pct | proj_fg3m | ✅ MAE=0.082 R²=0.981 |
| M24 | Props — Steals | same + hustle stats | proj_stl | ✅ MAE=0.064 R²=0.935 |
| M25 | Props — Blocks | same + zone tendency | proj_blk | ✅ MAE=0.044 R²=0.955 |
| M26 | Props — Turnovers | same + pressure stats | proj_tov | ✅ MAE=0.077 R²=0.979 |
| M27 | Usage Rate Model | synergy usage share, lineup, star availability | proj_usg% | 🔲 HIGH PRIORITY |
| M28 | True Shooting % | shot dashboard, zone tendency, defender dist | proj_ts% | 🔲 |
| M29 | Plus/Minus Predictor | on/off splits, lineup net rating, matchup | proj_pm | 🔲 |
| M30 | Age Curve Model | BBRef age curves, position, minutes trend, VORP trajectory | age_discount per season | 🔲 |
| M31 | Contract Year Effect | walk-year flag, contract size, performance history | contract_year_boost | ✅ heuristic |
| M32 | Home/Away Split | 3-season home vs road gamelog splits | home_boost, road_discount | 🔲 |
| M33 | Rest Day Performance | performance by days rest (0,1,2,3+) | rest_mult | 🔲 |
| M34 | Clutch Performance | PBP clutch situations, clutch score, pressure | clutch_adj | ✅ |
| M35 | Breakout Predictor | recent form trend, matchup, usage spike | breakout_score | ✅ pkl |

### Layer 4 — Matchup Models

| # | Model | Key Inputs | Output | Status |
|---|---|---|---|---|
| M36 | Matchup Model | who guards whom, pts allowed per matchup | matchup_pts_adj | ✅ R²=0.808 |
| M37 | Defender Zone xFG | defender zone data, shot chart zones, fg% allowed | zone_fg_pct_adj | ✅ |
| M38 | Synergy Matchup | synergy play types vs opponent defense | pts_per_play_vs_opp | ✅ data ready |
| M39 | Contested Shot Predictor | shot dashboard + opponent hustle/deflection rate | contested_pct_vs_opp | 🔲 data ready |
| M40 | Defensive Scheme Detector | PBP + lineup → zone/man/switch/drop/hedge | defensive_scheme | 🔲 |
| M41 | Switch Coverage Model | matchup data + play type → who gets switched | switch_matchup_adj | 🔲 |
| M42 | Help Defense Frequency | PBP drive outcomes, paint defense | help_defense_rate | 🔲 Phase 6 |
| M43 | Weakside Defender | spacing → which shooters get ignored | open_shot_rate_adj | 🔲 Phase 6 |

### Layer 5 — Shot Quality Models

| # | Model | Key Inputs | Output | Status |
|---|---|---|---|---|
| M44 | xFG v1 | shot location (distance, angle) | xfg (Brier 0.226) | ✅ 221K shots |
| M45 | xFG v2 | + defender dist, shot clock, fatigue (CV) | xfg_v2 | 🔲 Phase 7 |
| M46 | Shot Selection Quality | xFG vs player's avg xFG → decision quality | shot_quality_score | 🔲 Phase 7 |
| M47 | Shot Clock Pressure | shots with <4s clock from PBP | pressure_fg_discount | 🔲 data ready |
| M48 | Pull-Up vs Catch-Shoot | shot dashboard pull_up_pct vs catch_shoot_pct | shot_type_fg_adj | 🔲 data now ready |
| M49 | Contested Rate Model | shot dashboard contested_pct vs opponent defense | expected_contested_rate | 🔲 data now ready |
| M50 | Off-Ball Movement Impact | CV positions → spacing → open shot creation | spacing_shot_quality | 🔲 Phase 6 |

### Layer 6 — CV Spatial Models (unlock at 20+ games)

| # | Model | Key Inputs | Output | Status |
|---|---|---|---|---|
| M51 | Play Type Classifier | CV positions + events | iso/PnR/cut/spot-up/post/transition | ✅ rule-based |
| M52 | Defensive Pressure Index | CV defender proximity + angle | pressure_score per possession | ✅ built |
| M53 | Spacing Rating | CV positions → convex hull, paint density | spacing_index | 🔲 Phase 6 |
| M54 | Drive Frequency | CV dribble penetration events | drives_per_36 | 🔲 Phase 6 |
| M55 | Closeout Quality | CV closeout speed + distance at shot | closeout_score | 🔲 Phase 6 |
| M56 | Screen Effectiveness | CV screen set → open shot rate | screen_roi | 🔲 Phase 6 |
| M57 | Transition Frequency | CV possession start + speed | transition_rate | 🔲 Phase 6 |
| M58 | Ball Movement Rating | CV pass events → stagnation index | ball_movement_score | 🔲 Phase 6 |
| M59 | Fatigue Curve | CV speed over game time → decline rate | fatigue_index per minute | 🔲 Phase 7 |
| M60 | Rebound Positioning | CV positions at shot → reb prob per player | reb_prob_by_player | 🔲 Phase 7 |
| M61 | Pose Estimation | YOLOv8-pose → ankle keypoints, contest arm | contest_angle, body_lean | 🔲 Phase 2.5 |
| M62 | Shot Arc Model | CV ball trajectory → arc, release point | arc_score | 🔲 Phase 8+ |
| M63 | Movement Asymmetry | CV gait → injury precursor signal | asymmetry_index | 🔲 Phase 10+ |
| M64 | Double Team Detector | CV 2+ defenders within 4ft of ball handler | double_team_rate | 🔲 Phase 6 |
| M65 | Off-Ball Movement | CV non-ball-handler positions → cut freq | off_ball_activity | 🔲 Phase 6 |

### Layer 7 — Lineup & Team Models

| # | Model | Key Inputs | Output | Status |
|---|---|---|---|---|
| M66 | Lineup Chemistry | PBP on-court lineups, net rating by 5-man unit | lineup_net_rtg | 🔲 Phase 7 |
| M67 | Lineup Interaction | who elevates whom (PG assists → SF pts) | pairwise_boost matrix | 🔲 Phase 7 |
| M68 | Rotation Predictor | PBP sub patterns per coach, score context | expected_lineup_at_T | 🔲 data ready |
| M69 | Substitution Timing | coach tendencies (foul trouble, matchup, rest) | sub_trigger_model | 🔲 data ready |
| M70 | Team Total Normalizer | sum(proj_pts all players) → constrain to total | normalization_factor | 🔲 HIGH PRIORITY |
| M71 | Pace-Adjusted Lineup | lineups that push vs slow pace | lineup_pace_adj | 🔲 Phase 7 |
| M72 | Clutch Lineup Model | PBP clutch situations → coach lineup choices | clutch_lineup_prob | 🔲 data ready |

### Layer 8 — Live / In-Game Models

| # | Model | Key Inputs | Output | Status |
|---|---|---|---|---|
| M73 | Live Win Prob LSTM | possession sequences, score, time, momentum | live_win_prob | 🔲 Phase 11 |
| M74 | Live Prop Updater | current stats + proj remaining minutes | updated prop projection | 🔲 Phase 11 |
| M75 | Comeback Probability | deficit + time + pace + clutch ratings | comeback_prob | 🔲 Phase 11 |
| M76 | Momentum Run Detector | PBP scoring runs → momentum score | momentum_score | ✅ built |
| M77 | Foul Trouble Live | live foul count + matchup | min_remaining_adj | 🔲 Phase 11 |
| M78 | Q4 Star Usage | blowout prob → star rest probability | star_usage_adj_live | 🔲 Phase 11 |
| M79 | Garbage Time Live | score diff live + pace | garbage_time_flag | 🔲 Phase 11 |

### Layer 9 — Betting Edge Models

| # | Model | Key Inputs | Output | Status |
|---|---|---|---|---|
| M80 | Sharp Money Detector | line movement, public %, reverse line move | sharp_side, sharp_conf | ✅ |
| M81 | CLV Tracker | opening vs closing line vs prediction | historical_clv | ✅ |
| M82 | Public Fade | public betting %, ESPN mentions | fade_signal | ✅ pkl |
| M83 | Soft Book Lag | DK/FD vs Pinnacle spread | lag_score (0-1) | ✅ pkl |
| M84 | Line Movement Predictor | injury news timing + historical move patterns | expected_line_move | 🔲 |
| M85 | Injury News Lag | news timestamp vs line movement | news_edge_window (min) | 🔲 HIGH PRIORITY |
| M86 | Prop Correlation Matrix | historical prop correlation per player/team | correlation_adj | ✅ 508 players |
| M87 | SGP Optimizer | correlated legs + correlation matrix | optimal SGP combo | ✅ heuristic |
| M88 | Parlay Optimizer | uncorrelated +EV legs | optimal parlay | ✅ heuristic |
| M89 | Kelly Sizing | win_prob + payout odds | bet fraction | formula |
| M90 | Prop Pricing Engine | reverse-engineer book model from line history | book_model_implied_proj | 🔲 Phase 12 |

### Layer 10 — NLP / Sentiment Models

| # | Model | Key Inputs | Output | Status |
|---|---|---|---|---|
| M91 | Injury Severity NLP | NBA official report text | severity (0-1), games_missed_est | 🔲 HIGH PRIORITY |
| M92 | Coach Language Model | press conf + beat reporter patterns | dnp_prob_update | 🔲 |
| M93 | Beat Reporter Credibility | reporter historical accuracy | credibility_weight | 🔲 |
| M94 | Team Chemistry Sentiment | beat reporter articles → locker room signal | chemistry_score | 🔲 |
| M95 | Trade Rumor Impact | trade news → distraction discount | trade_distraction_adj | 🔲 |

### Layer 11 — Self-Improving Pipeline

| # | Model | Key Inputs | Output | Status |
|---|---|---|---|---|
| M96 | Outcome Recorder | prediction vs actual | prediction_error log | ✅ |
| M97 | Auto-Retrain | error log → trigger retraining | retrain_trigger | ✅ |
| M98 | Model Version Manager | performance history | active_model_version | ✅ |
| M99 | Prediction Calibration | predicted prob vs actual outcome rate | calibration_curve | 🔲 |
| M100 | Feature Drift Detector | feature importance over time | stale_features flag | 🔲 |

---

## Priority Build Queue (highest ROI, buildable now — no CV needed)

| Priority | Model | Why | Estimated Impact |
|---|---|---|---|
| 1 | M70 Team Total Normalizer | Raw model sums drift 5-10 pts from game total. Systematic bias killing all props. | +3-5% prop accuracy immediately |
| 2 | M08 Beneficiary Cascade | Stars miss games every week. Books lag 30-90 min. Best repeatable edge. | +4-8 pts CLV on beneficiary bets |
| 3 | M27 Usage Rate Model | Biggest single error source in props — assumes static usage | +2-4% prop accuracy |
| 4 | M07 Minutes Floor Model | Second biggest error source — base_min assumption too simple | +2-3% accuracy |
| 5 | M16 Referee Tendency | 3 seasons of ref data exists, just not wired. Pace affects all counting stats. | +1-2% accuracy |
| 6 | M91 Injury Severity NLP | 10-15 min edge window when news breaks before lines move | Best timing edge |
| 7 | M47 Shot Clock Pressure | PBP has shot clock. Easy feature, direct pts/3pm impact | +1% on pts/3pm models |
| 8 | M68 Rotation Predictor | 3,627 games of sub data. Coach patterns are very predictable. | +1-2% on min model |
| 9 | M32 Home/Away Split | Simple regression on existing gamelog data | +1% accuracy |
| 10 | M84 Line Movement Predictor | Timing edge — bet before line moves in your direction | CLV improvement |

**Build all 10 in order before Phase G. No CV required. Pure data → model work.**

---

## Rolling Pipeline Architecture (Phase H)

### The Key Insight
You never need to store raw video. Extract features, delete the video, keep only the data.

```
Raw video (1.5-2 GB per game)    →  DELETE after processing
                ↓
CV Pipeline extracts:
  positions, shots, possessions,
  defender distance, fatigue,
  play type, spacing
                ↓
Extracted features (10-20 MB per game)  →  KEEP FOREVER
```

**Ratio: 100:1 compression.** The full season as extracted data = ~25 GB, not 2.5 TB.

### Rolling Pipeline Flow

```
DOWNLOAD WORKER        PROCESS WORKER          RETRAIN WORKER
      │                      │                       │
  game_001.mp4  ──────►  extract features  ──────►  accumulate DB rows
  [20 min DL]             enrich NBA API                  │
      │                   delete video              every 50 games:
  game_002.mp4  ──────►  extract features           retrain xFG v2
      │                   delete video              every 100 games:
  game_003.mp4  ──────►  ...                        retrain props
                                                    every 200 games:
                                                    retrain all
```

At any moment: 3-5 games on disk, everything else extracted and deleted.

### Storage You Actually Need

| Data | Per Game | Full Season |
|---|---|---|
| Raw video | 1.5-2 GB | **Never store — delete immediately** |
| Tracking rows | 8-12 MB | ~12 GB |
| Shot features | 2-3 MB | ~3 GB |
| Possession features | 3-5 MB | ~5 GB |
| NBA API enrichment | 1-2 MB | ~2 GB |
| **Total extracted** | **~20 MB** | **~25 GB total** |

### Video Source
**NBA League Pass archive** (~$20/month): every 2024-25 game, all 3 prior seasons available.
Use `yt-dlp` with cookies at 720p. Players are large objects — 720p is sufficient for tracking.

### RunPod Specs

```
1× A100 80GB pod, 200GB local SSD
Running: download worker + process worker in parallel threads
Cost:
  1,230 games × 3-4 min = ~80 hours processing
  + download bottleneck: ~120 hours total
  120 hrs × $1.64/hr = ~$197
  (vs old plan: 4× A100s + 2.5TB storage = ~$300+)
```

One pod, rolling pipeline, no bulk storage cost.

---

## Incremental Retraining Schedule

Models retrain automatically as data accumulates. Each retrain uses ALL historical data.

```
Games 1-10:     Validate pipeline. Catch extraction bugs. No retrain.

Games 10-20:    xFG v2 FIRST TRAIN (defender dist as feature)
                Play type classifier first ML train
                Props get first CV features baked in
                → First accuracy jump: +3-4% on pts/3pm

Games 20-50:    Fatigue curve first train (speed decline measured)
                Rebound positioning first train
                Closeout quality first train
                Spacing index activated
                → Second jump: role player props hit 62-65%

Games 50-100:   Full matchup matrix with CV-measured defense
                Lineup chemistry first train (5-man units)
                Rotation predictor reaching full accuracy
                Coach sub patterns fully learned
                → Props hit 63-66% sustained

Games 100-200:  All CV models in high-confidence zone
                Live LSTM first train (possession sequences)
                Every player has dense spatial feature vector
                → CLV stable at +3.0-4.5 pts average

Games 200-1230: Refinement. Rare matchups filled in.
                Scheme-specific matchup model reaches full power
                → CLV stable at +3.5-5.0 pts
                → Live LSTM powers live betting at +3-5.5 pts CLV
```

---

## Prediction Accuracy Targets

### Win Probability

| Stage               | Accuracy    | Notes                        |
| ------------------- | ----------- | ---------------------------- |
| Current             | 69.1%       | Team ratings + rest + pace   |
| + referee + travel  | ~71%        | Easy wins, data exists       |
| + CV lineup quality | ~72%        | Phase 6                      |
| Full build ceiling  | **~73-74%** | Hard wall — rest is variance |

### Player Props — The Primary Market

| Stage                      | Pts Over/Under | Role Player Props | Beneficiary Props |
| -------------------------- | -------------- | ----------------- | ----------------- |
| Current (67 features)      | ~55-56%        | ~57-58%           | —                 |
| + priority 10 models built | ~58-59%        | ~60-62%           | ~62-65%           |
| + 20 CV games (Phase I)    | ~60-62%        | ~63-65%           | ~64-67%           |
| + 100 games full CV        | ~62-64%        | ~65-67%           | ~66-70%           |
| Full build (200+ games)    | **~63-65%**    | **~66-69%**       | **~68-72%**       |
|                            |                |                   |                   |

### CLV by Bet Type at Full Build

| Bet Type             | Expected CLV     | Notes                                   |
| -------------------- | ---------------- | --------------------------------------- |
| Game spreads         | +0.5-1.0 pts     | Efficient market, narrow edge           |
| Game totals          | +0.8-1.5 pts     | Pace/referee under-modeled publicly     |
| Star props           | +0.8-1.8 pts     | Efficient, but injury lag helps         |
| Role player props    | +2.5-4.5 pts     | Primary market — books use lazy pricing |
| Beneficiary props    | +5.0-9.0 pts     | Best edge, repeatable weekly            |
| Live bets (LSTM)     | +3.0-5.5 pts     | Possession sequence edge                |
| SGP correlation edge | +3.5-6.0 pts     | Correlated legs mispriced               |
| **Blended average**  | **+2.8-4.2 pts** | **Professional tier**                   |

### ROI Projection (500 prop bets/season, $100/bet flat)

| Accuracy | ROI | Profit |
|---|---|---|
| 52.4% | 0% | $0 (break-even) |
| 56% | +7% | +$3,500 |
| 60% | +15% | +$7,500 |
| 63% | +20% | +$10,000 |
| 67% (beneficiary) | +28% | +$14,000 on that subset |

---

## The Self-Improving Nightly Loop

```
NIGHTLY (2 AM, after all games complete):

1. Outcome Recorder
   → pull actual stats from NBA API
   → compare to every prediction made that day
   → log {model, player, stat, predicted, actual, error}

2. CLV Check
   → pull closing lines
   → compute CLV = closing_line - your_line_at_bet_time
   → log to clv_log table
   → rolling 7-day avg CLV = primary health metric

3. Drift Check (per model, per stat)
   → rolling_20_game_MAE > 1.5× baseline → flag for retrain
   → rolling_20_game_MAE > 2.0× baseline → emergency retrain now

4. Retrain (if triggered)
   → pull all historical + new data
   → walk-forward validate on last 20 games
   → if new_MAE < old_MAE → promote new model
   → if not → keep old, investigate feature drift

5. Feature Drift Check
   → which features have degraded importance?
   → flag stale player caches (traded players, role changes)
   → auto-refresh stale data

6. Morning 9AM pull
   → injury reports, lines, today's props
   → run full prediction pipeline for today's games
   → post edge list to dashboard
```

**Daily volume (ongoing after initial season run):**
- 1-2 new games per night
- Process in ~25 min on RTX 4060 (post-TensorRT optimization)
- Delete video, keep features
- System stays current automatically

---

## Build Phases

### Phase G — 10 Local Test Games 🔲

**Goal:** Verify entire loop before cloud spend. Fix any bugs.

1. Record 10 games with OBS (League Pass, 1080p, H.264, 15 Mbps)
2. Name: `{AWAY}_{HOME}_{DATE}.mp4` → e.g. `LAL_GSW_20250115.mp4`
3. Run: `python scripts/batch_process.py --folder recordings/ --workers 1`
4. Verify: tracking data in DB, CV features extracted, video deleted
5. Run: `python src/prediction/player_props.py` for those game dates
6. After games complete: check outcome_recorder, CLV log
7. **Do not proceed to cloud until 10-game loop is clean**

**Also build Priority Queue models 1-10 during this phase** (no CV needed, pure data work):
- M70 Team Total Normalizer
- M08 Beneficiary Cascade
- M27 Usage Rate Model
- M07 Minutes Floor Model
- M16 Referee Tendency
- M91 Injury Severity NLP
- M47 Shot Clock Pressure
- M68 Rotation Predictor
- M32 Home/Away Split
- M84 Line Movement Predictor

### Phase H — Full Season Rolling Pipeline 🔲

**Goal:** Process 1,230 games in one weekend. All models reach full accuracy.

**Friday evening:**
```bash
# 1. Subscribe to NBA League Pass ($20)
# 2. Set up RunPod A100 pod (200GB SSD)
bash scripts/setup_runpod.sh

# 3. Start rolling pipeline
python scripts/rolling_pipeline.py \
  --seasons 2024-25 \
  --quality 720p \
  --workers 4 \
  --delete-after-process
```

**The rolling_pipeline.py script (build in Phase G):**
```python
# Download worker: 8 parallel streams, fills 3-game buffer
# Process worker: CV → enrich → features → DB → DELETE VIDEO
# Retrain worker: fires at 20/50/100/200/500 game milestones
# All three run in parallel threads
```

**Saturday-Sunday:**
- Monitor progress dashboard
- Models automatically improve at each milestone
- By Sunday evening: all 1,230 games processed, all models retrained

**Cost breakdown:**
```
RunPod A100: ~120 hrs × $1.64/hr = ~$197
NBA League Pass: $20
Storage (25GB features): ~$5/month S3
Total: ~$222 one-time
```

### Phase I — Model Milestones (auto-triggered)

| Games | Models Unlocked | Accuracy Jump |
|---|---|---|
| 20 | xFG v2, play type ML, pressure, spacing | +3-4% props |
| 50 | Fatigue curve, rebound positioning, closeout | +2-3% more |
| 100 | Lineup chemistry, matchup matrix v2, rotation | +2-3% more |
| 200 | Live LSTM first train, prop pricing engine | +CLV +1.5 pts |
| 1,230 | Full calibration, every player profiled | Ceiling reached |

### Phase J — Full Simulator Operational

7-model possession chain × 10,000 Monte Carlo per game:

```
[1] Play Type (M51)
        ↓
[2] Shot Selector — who shoots, from where
        ↓
[3] xFG v2 (M45) — P(make) with CV features
        ↓
[4] Turnover/Foul Model
        ↓
[5] Rebound (M60) — positioning-based
        ↓
[6] Fatigue Multiplier (M59) — by minute
        ↓
[7] Substitution (M69) — coach pattern
        ×
    10,000 simulations
        ↓
    Stat distribution per player
        ↓
    Compare vs sportsbook lines
        ↓
    Flag +EV edges → Kelly sizing → bet list
```

---

## Complete Data Catalog (all sourced)

| Source               | Data                                              | Status                      |
| -------------------- | ------------------------------------------------- | --------------------------- |
| NBA gamelogs         | pts/reb/ast/min per game, 3 seasons               | ✅ 622 players               |
| Shot dashboard       | contested%, pull-up%, catch-shoot%, defender dist | ✅ pulling now               |
| PBP                  | event sequences, lineup, clutch splits            | ✅ 3,627/3,685               |
| Shot charts          | 221K shots, location + make/miss                  | ✅                           |
| Hustle stats         | deflections, screens, charges                     | ✅ 3 seasons                 |
| On/off splits        | net rating on/off                                 | ✅ 3 seasons                 |
| Matchup data         | who guards whom, pts allowed                      | ✅ 3 seasons                 |
| Synergy play types   | pts/possession by play type                       | ✅ 2024-25 (backfill needed) |
| Defender zones       | FG% allowed by zone                               | ✅ 3 seasons                 |
| BBRef VORP/WS48/BPM  | true impact metrics                               | ✅ 3 seasons                 |
| Contracts            | salary, walk-year, years remaining                | ✅ 523 players               |
| Injury reports       | NBA official + RotoWire                           | ✅ live                      |
| Historical lines     | closing spread/total                              | ✅ 3 seasons                 |
| Current props        | DK/FD per-player lines                            | ✅ 15-min TTL                |
| BBRef injury history | games missed per injury                           | 🔲 built, not pulled        |
| Referee assignments  | daily ref-to-game assignments                     | 🔲 pull needed              |
| CV tracking          | positions, shots, possessions                     | 🔲 Phase G                  |
|                      |                                                   |                             |
|                      |                                                   |                             |

---

## Files To Build (priority order)

| #   | File                                      | Phase | Why                            |
| --- | ----------------------------------------- | ----- | ------------------------------ |
| 1   | `src/prediction/team_total_normalizer.py` | G     | Fixes systematic bias, 1 day   |
| 2   | `src/prediction/beneficiary_cascade.py`   | G     | Best repeatable edge           |
| 3   | `src/prediction/usage_rate_model.py`      | G     | Biggest prop error source      |
| 4   | `src/prediction/minutes_floor_model.py`   | G     | Second biggest error source    |
| 5   | `src/data/referee_model.py`               | G     | Wires ref data already fetched |
| 6   | `src/nlp/injury_severity.py`              | G     | 10-15 min timing edge          |
| 7   | `scripts/rolling_pipeline.py`             | H     | Core of Phase H                |
| 8   | `src/prediction/rotation_predictor.py`    | G     | PBP sub patterns               |
| 9   | `src/prediction/home_away_model.py`       | G     | Simple regression, big impact  |
| 10  | `src/analytics/line_movement.py`          | G     | CLV timing                     |

---

## The Number That Tells You It's Working

**CLV (Closing Line Value)** — track from day one.

```
You predict: role player over 7.5 reb, proj = 9.2
You bet at: over 7.5 (-110)
Closing line moves to: over 8.5 (-110)

Your CLV: +1.0 pt → market agreed with you after it had more information
```

If CLV is consistently positive across 100+ bets, the system is real.
If CLV is negative despite a good win rate, you're getting lucky and it won't last.

**Target CLV milestones:**
- After Phase G (priority models built): +0.8-1.2 pts
- After Phase H 20 games: +1.5-2.0 pts
- After Phase H full season: **+2.8-4.2 pts (professional tier)**

---

## What Each Weekend Costs vs What You Get

| Weekend         | Spend            | Games Added | CLV Gain             | Accuracy      |
| --------------- | ---------------- | ----------- | -------------------- | ------------- |
| Phase G         | $0 (local)       | 10          | Baseline established | ~58% props    |
| Phase H Week 1  | ~$15 (20 games)  | +20         | +0.8 pts             | ~61% props    |
| Phase H Week 2  | ~$75 (100 games) | +100        | +1.5 pts             | ~63% props    |
| Phase H full    | ~$200            | +1,230      | +2.8-4.2 pts         | ~65-69% props |
| Ongoing nightly | ~$0 (local RTX)  | +2/night    | Maintained           | Improving     |

---

*See [[Project Vision]] for end-product spec. See [[Tracker Improvements Log]] for CV quality progress. See [[Complete Model Catalog]] for full 100-model detail.*
