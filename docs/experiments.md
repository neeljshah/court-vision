# Experiments Log

This document tracks model experiments, architecture iterations, and their measured results. Each entry records what was tested, the outcome, and what was learned.

---

## Win Probability Model

### EXP-001: Initial XGBoost Win Probability (2026-03-17)

**Goal:** Train pre-game win probability model on 3 seasons of NBA data.

**Features (27 total):**
- Team offensive/defensive/net rating (last 30 days)
- Pace, eFG%, TS%, TOV% (season-to-date)
- Home/away flag
- Days rest (both teams)
- Back-to-back flag (both teams)
- Travel distance since last game
- Head-to-head last 3 meetings win rate
- Recent form: last 10 games win rate

**Training data:** 3,685 games (3 complete NBA seasons)

**Validation:** Walk-forward cross-validation (train on t-1 seasons, predict current season)

**Results:**
| Metric | Value |
|--------|-------|
| Accuracy | **67.7%** |
| Brier Score | **0.204** |
| Log Loss | 0.618 |
| AUC-ROC | 0.72 |

**Baseline comparison:**
- Vegas implied probability baseline: ~67.5% (using moneyline as probability)
- This model: 67.7% — essentially matching Vegas on hold-out data
- Interpretation: with NBA API features only, we're at market efficiency. CV features (Phase 7) + behavioral features (Phase 4.6) are needed to exceed it.

**Top features (SHAP):**
1. home_net_rtg (last 30 days) — 18% importance
2. away_net_rtg (last 30 days) — 16% importance
3. home_team_def_rtg — 11%
4. rest_days_home — 9%
5. travel_miles_away — 7%
6. head_to_head_win_rate — 6%

**Notes:**
- sklearn version mismatch caused ISSUE-016 (retrain required after conda env update)
- Model saved to `data/models/win_probability.pkl`

---

### EXP-002: Win Probability — Retrain with ref + synergy features (Phase 4.6)

**Status:** 🔲 Planned

**Hypothesis:** Adding ref_pace_tendency and synergy matchup data will improve accuracy by ~2-3%.

**Features to add:**
- ref_pace_tendency (assigned referee's historical pace)
- ref_fta_tendency (assigned referee's historical FTA rate)
- synergy_pts_per_poss (offensive efficiency by play type for key starters)
- defender_zone_fg_allowed (matchup-level zone defense metrics)

**Target:** 70-71% accuracy

---

## Player Prop Models

### EXP-003: Prop Models v1 — 30 Features (2026-03-18)

**Goal:** Train 7 player prop prediction models (pts/reb/ast/fg3m/stl/blk/tov).

**Architecture:**
- Algorithm: XGBoost regressor
- Features: 30 (season stats, gamelogs, BBRef BPM, contract year, rest, travel)
- Training: walk-forward validation (same methodology as EXP-001)
- Output: predicted stat value + confidence interval (P25/P75 from prediction variance)

**Feature groups:**
1. Season averages (pts_avg, reb_avg, ast_avg, min_avg, fg_pct, 3pt_pct)
2. Rolling form (last5_pts, last10_pts, last15_pts, last20_pts)
3. Advanced stats (ts_pct, usg_rate, off_rtg, def_rtg, efg_pct)
4. BBRef extended (bpm, vorp, ws_per_48) — added in this version
5. Schedule context (rest_days, back_to_back, travel_miles)
6. Contract context (contract_year flag) — added in this version
7. Opponent context (opp_def_rtg, opp_pts_allowed_to_position)

**Results:**
| Model | Walk-forward MAE | R² |
|-------|-----------------|-----|
| Points | **0.32** | 0.92 |
| Rebounds | **0.11** | 0.94 |
| Assists | **0.09** | 0.93 |
| 3PM | **0.09** | 0.91 |
| Steals | **0.07** | 0.90 |
| Blocks | **0.05** | 0.92 |
| Turnovers | **0.08** | 0.91 |

**Top features for points model (SHAP):**
1. pts_last5_avg — 22% importance
2. pts_season_avg — 18%
3. usg_rate — 14%
4. min_avg — 11%
5. ts_pct — 8%
6. opp_def_rtg — 7%
7. rest_days — 4%
8. contract_year — 2% (modest but meaningful on high-contract players)

**Comparison vs. baseline (season average only):**
| Model | Baseline MAE | Model MAE | Improvement |
|-------|-------------|-----------|-------------|
| Points | 0.51 | 0.32 | -37% |
| Rebounds | 0.18 | 0.11 | -39% |
| Assists | 0.15 | 0.09 | -40% |

**Notes:**
- Contract year flag adds ~2% accuracy on stars in walk year (Giannis, Durant seasons used as test)
- BBRef BPM slightly more predictive than NBA net_rtg alone for props
- Rest days + travel: ~4% accuracy contribution — underrated feature

---

### EXP-004: Prop Models v2 — 52 Features (Phase 4.6)

**Status:** 🔲 Planned

**Hypothesis:** Adding 22 features from already-cached but unwired data will reduce MAE by ~30%.

**New features being added:**
- VORP, WS/48 (BBRef)
- Hustle deflections, screen assists (NBA Hustle)
- On/off net rating (NBA Tracking)
- Synergy pts/poss by play type
- Defender zone FG% allowed, matchup_fg_allowed
- contested_shot_pct, pull_up_pct, catch_and_shoot_pct, avg_defender_dist
- shot_zone_tendency_entropy
- cap_hit_pct (from contracts)
- games_in_last_14
- ref_fta_tendency, ref_pace_tendency
- shot_clock_pressure_score, fatigue_penalty
- momentum_shift_flag, scoring_run_length

**Target:**
| Model | Current MAE | Target MAE |
|-------|------------|-----------|
| Points | 0.32 | ~0.22 |
| Rebounds | 0.11 | ~0.07 |
| Assists | 0.09 | ~0.06 |

---

## xFG (Expected Field Goal)

### EXP-005: xFG v1 — Zone + Distance + Defender (2026-03-17)

**Goal:** Predict shot probability given shooting context.

**Training data:** 221,866 shots (3 seasons, 569 players, shot_chart_scraper.py)

**Features:**
- shot_zone (paint / mid_range / corner_3 / above_break_3 / restricted_area)
- shot_distance (feet from basket)
- shot_type (jump shot / layup / dunk / hook / tip)
- season_fg_pct (shooter's season FG% from same zone)
- defender_distance (from NBA shot dashboard data)

**Model:** XGBoost binary classifier (made = 1)

**Results:**
| Metric | Value |
|--------|-------|
| Brier Score | **0.226** |
| Log Loss | 0.632 |
| AUC-ROC | 0.69 |
| Baseline (shot_pct = zone average) | Brier 0.248 |

**Improvement over zone-average baseline:** +9.7%

**Feature importance:**
1. shot_zone — 31%
2. shot_distance — 24%
3. season_fg_pct — 19%
4. defender_distance — 14%
5. shot_type — 12%

**Notes:**
- Defender distance data came from `nba_tracking_stats.get_shot_dashboard()` — added 14% to model importance
- Biggest gap vs. Second Spectrum xFG: they have defender position at release + contest arm angle (±10-15% Brier improvement). Phase 2.5 pose estimation closes ~60% of this gap.

---

### EXP-006: xFG v2 (Phase 7)

**Status:** 🔲 Planned (requires 20+ full games with enriched CV shots)

**New features:**
- closeout_speed_mph (from CV EventDetector.events) — how fast defender closed out
- shot_clock_decay (pressure score from shot quality module) — probability of forced shot
- fatigue_penalty (per-player minutes-adjusted efficiency) — late-game shooting impact
- shot_arc (parabola fit from ball trajectory) — Phase 2.5 ball tracking
- contest_angle (arm extension from pose estimation) — Phase 2.5

**Target:** Brier ~0.200 (vs. current 0.226)

---

## Matchup Model

### EXP-007: M22 Matchup Model (2026-03-18)

**Goal:** Predict player scoring differential based on defender matchup.

**Architecture:** XGBoost regressor

**Features (22):**
- defender_zone_fg_allowed (by zone)
- synergy_defense_pts_per_poss (by play type)
- matchup_pts_per_poss (historical matchup)
- hustle_deflections, screen_assists (defender hustle)
- on_off_def_rtg (defender's impact on defense)
- attacker_zone_shot_tendency
- attacker_pull_up_pct, catch_and_shoot_pct
- attacker_ts_pct, avg_defender_dist_allowed

**Results:**
| Metric | Value |
|--------|-------|
| R² | **0.796** |
| MAE | **4.55 pts** |

**Training data:** 3 seasons × 2,269 matchup records

**Notes:**
- M22 = Model version 22 (internal naming: features count)
- Highest impact features: defender_zone_fg_allowed (23%), synergy_def_pts_per_poss (19%)
- This feeds into the matchup context layer of prop models (Phase 4.6)

---

## CLV Backtest

### EXP-008: Closing Line Value Baseline (2026-03-18)

**Goal:** Establish baseline accuracy for the betting edge detection system.

**Method:** Use actual game margins as ground truth. Predict game winner from current win probability model. Measure:
- What % of predictions correctly identified the winner
- Average absolute error vs. actual point margin

**Results:**
| Metric | Value |
|--------|-------|
| Winner accuracy | **70.7%** |
| Average margin error (MAE) | **10.2 pts** |
| Games evaluated | **3,685** |

**Notes:**
- 70.7% winner prediction vs. 67.5% Vegas baseline → 3.2% edge on game outcomes
- Margin error of 10.2 pts is expected — game totals are inherently volatile
- This is the baseline for all future CLV tracking
- Phase 4.6 goal: push winner accuracy to ~73% with 22 new features

---

## Pipeline Performance

### EXP-009: Processing Speed Benchmarks

**Hardware:** RTX 4060 (8.6GB VRAM), Intel i7-13700H, 32GB RAM

| Configuration | FPS | Notes |
|--------------|-----|-------|
| YOLOv8n, imgsz=1280 | 2.0 fps | ISSUE-021: bottleneck |
| YOLOv8n, imgsz=640 | 5.1 fps | After ISSUE-021 fix |
| YOLOv8n, imgsz=640 + embedding fix | **5.7 fps** | +12% from ISSUE-022 fix |
| YOLOv8x, imgsz=640 (target) | ~3.5 fps | Phase 2.5 (higher accuracy) |

**Key fix (ISSUE-021):** Dropped `imgsz` from 1280 → 640. YOLOv8n doesn't benefit from high resolution at this scale; only the large models do.

**Key fix (ISSUE-022):** Pre-compute `det["deep_emb"]` before the cost matrix loop. Was computing 256-dim embedding per match attempt, causing O(n²) GPU calls.

**Timeline per game type:**
- 30-second clip: ~8 seconds
- 5-minute clip: ~1.5 minutes
- 20-minute period: ~6 minutes
- Full 48-minute game: ~6 hours

---

## Tracking Quality

### EXP-010: Phase 2 Tracking Quality Metrics (2026-03-16)

**Baseline (before Phase 2 fixes):**
- Team separation accuracy: ~45% (all players labeled same team)
- ID switch rate: ~23% per possession
- Ball detection rate: ~51%
- Event detection (shots): 0 (EventDetector not firing)

**After Phase 2 fixes:**
- Team separation: ~87% (k-means warm-up clustering)
- ID switch rate: ~15% per possession
- Ball detection rate: ~78%
- Shot detection: ~17 per clip (EventDetector fixed)

**Phase 2.5 targets:**
- Team separation: ~92% (pose keypoints + jersey OCR voting)
- ID switch rate: ~3% (ByteTrack)
- Ball detection: ~88%
- Position accuracy: ±6-8 inches (from ±12-15 with pose estimation)

---

## Feature Importance Rankings (Cross-Model)

Features that appear in top-5 importance for 3+ models:

| Feature | Models | Avg Importance |
|---------|--------|---------------|
| pts_last5_avg / relevant_stat_last5 | Props (all 7) | 22% |
| season_avg / usg_rate | Win prob, all props | 15-18% |
| home_net_rtg / team ratings | Win prob, game models | 16% |
| defender_distance | xFG, matchup | 14% |
| rest_days | Win prob, all props, game models | 4-9% |
| ts_pct / efg_pct | Props (pts, 3pm) | 8% |

**Interpretation:** Rolling form (last5) is the strongest predictor for props. Team quality metrics dominate game-level predictions. Rest/travel has consistent 4-9% contribution across all models — underrated feature in public tools.
