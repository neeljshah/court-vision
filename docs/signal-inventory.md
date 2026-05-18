Status: current as of 2026-04-23.

# Signal Inventory

Exhaustive catalog of features used by CourtVision's prop models. Features are
grouped by data source tier. "Wired" means the feature is in the current training
set for at least one prop model. Feature counts are approximate; exact column lists
are in [src/features/feature_engineering.py](../src/features/feature_engineering.py).

---

## 1. API Box-Score Features

**Source:** `nba_api` game logs, 2018-19 to present. Fetched by `src/data/nba_stats.py`.

| Feature | Definition | Source function | Wired |
|---------|-----------|----------------|-------|
| pts_L{3,5,10,20} | Points rolling mean, last N games | `add_rolling_features` | ✅ |
| reb_L{3,5,10,20} | Rebounds rolling mean | `add_rolling_features` | ✅ |
| ast_L{3,5,10,20} | Assists rolling mean | `add_rolling_features` | ✅ |
| fg3m_L{3,5,10,20} | 3PM rolling mean | `add_rolling_features` | ✅ |
| blk_L{3,5,10,20} | Blocks rolling mean | `add_rolling_features` | ✅ |
| stl_L{3,5,10,20} | Steals rolling mean | `add_rolling_features` | ✅ |
| tov_L{3,5,10,20} | Turnovers rolling mean | `add_rolling_features` | ✅ |
| min_L{3,5,10,20} | Minutes played rolling mean | `add_rolling_features` | ✅ |
| fg_pct_L10 | Field goal % rolling 10 | `add_rolling_features` | ✅ |
| ft_pct_L10 | Free throw % rolling 10 | `add_rolling_features` | ✅ |
| pts_season_mean | Season-to-date weighted mean | `add_rolling_features` | ✅ |
| regression_weight | Bayesian regression-to-mean weight | `compute_regression_weight` | ✅ |
| pts_max_L5 | Maximum pts in last 5 games | `add_rolling_features` | ✅ |
| usage_rate | Possession-end usage rate | `usage_rate_model.py` | ✅ |
| ts_pct | True shooting percentage | `true_shooting_model.py` | ✅ |
| per_100_pts | Points per 100 possessions | `add_per100_features` | ✅ |
| per_100_reb | Rebounds per 100 possessions | `add_per100_features` | ✅ |

**Total: ~20 box-score features.**

---

## 2. API Derived Features

**Source:** Computed from `nba_api` game logs + schedule + lineup data.
Functions: `add_context_features`, `add_external_player_features`,
`get_home_away_splits` in `src/features/feature_engineering.py`.

| Feature | Definition | Source | Wired |
|---------|-----------|--------|-------|
| pace_diff | Team pace vs opponent pace differential | `add_context_features` | ✅ |
| team_implied_total | Vegas-implied team total from game total + spread | `add_context_features` | ✅ |
| opp_def_rtg_pos | Opponent defensive rating vs player's position | `add_context_features` | ✅ |
| back_to_back | 1 if game is second of back-to-back | `add_context_features` | ✅ |
| home_away | Home/away indicator | `get_home_away_splits` | ✅ |
| rest_days | Days since last game | `rest_day_model.py` | ✅ |
| altitude | Venue altitude above sea level (ft) | `altitude_model.py` | ✅ |
| travel_miles | Travel distance since last game | `travel_impact_model.py` | ✅ |
| ref_foul_rate | Referee crew historical foul rate | `add_external_player_features` | ✅ |
| lineup_net_rtg | Current 5-man unit net rating | `add_context_features` | ✅ |
| opp_lineup_net_rtg | Opponent current 5-man unit net rating | `add_context_features` | ✅ |
| injury_risk_score | Player injury risk index (days since return, workload) | `injury_risk.py` | ✅ |
| load_mgmt_flag | Load management probability | `load_management.py` | ✅ |
| schedule_strength | SOS over next 7 days | `add_context_features` | Partial |

**Total: ~12 API derived features.**

---

## 3. CV Spatial Features

**Source:** Broadcast video, processed through the CV pipeline (YOLOv8 → SIFT
homography → Kalman+Hungarian → OSNet re-ID → EasyOCR → EventDetector).
Post-homography computation in `src/features/feature_engineering.py`::`compute_spatial_features`.

Available for 29 usable games (9 CLEAN + 20 PARTIAL) of 75 attempted; target 80 CLEAN.
Features marked "Partial" are in the model feature set but carry imputed means for
non-CV games.

| Feature | Definition | Source function | Wired |
|---------|-----------|----------------|-------|
| defender_distance | Meters to nearest defender at shot release (court coords) | `compute_spatial_features` | Partial |
| spacing_score | Convex-hull area of 4 off-ball offensive players, normalized to half-court | `add_momentum_features` | Partial |
| legs_fatigue | Cumulative running distance last 6 min, exponentially decayed | `add_fatigue_features` (via `add_external_player_features`) | Partial |
| spacing_advantage | Own team spacing minus opponent spacing (ft²) | `add_momentum_features` | Partial |
| nearest_opponent | Distance to nearest opponent player (ft) | `compute_spatial_features` | Partial |
| nearest_teammate | Distance to nearest teammate (ft) | `compute_spatial_features` | Partial |
| handler_isolation | Ratio of ball-handler space to court average | `compute_spatial_features` | Partial |
| team_centroid_x | X-position of team centroid relative to basket | `compute_spatial_features` | Partial |

**Total: ~8 CV spatial features. SHAP contribution on pts model: 31% combined for
defender_distance + spacing_score + legs_fatigue. Δ R² vs API-only baseline: +0.08.**

These three features are the CV moat. Their signal is not replicated by any public
NBA dataset.

---

## 4. CV Temporal Features

**Source:** Frame-level event detections aggregated over rolling windows. Computed by
`add_event_features` and `add_basket_features` in
[src/features/feature_engineering.py](../src/features/feature_engineering.py).

| Feature | Definition | Window | Wired |
|---------|-----------|--------|-------|
| shots_{N} | Shot attempts in last N frames | 5, 10, 20 | ✅ |
| passes_{N} | Pass events in last N frames | 5, 10, 20 | ✅ |
| dribbles_{N} | Dribble events in last N frames | 5, 10, 20 | ✅ |
| basket_dist_mean_{N} | Mean distance to basket over last N frames | 5, 10 | ✅ |
| drive_rate_{N} | Proportion of frames with player driving toward basket | 5, 10 | ✅ |
| pace_30 | Shots + turnovers per 30 frames (rolling) | 30 | ✅ |
| shot_quality_proxy | zone_weight × defender_factor × spacing_factor (composite) | — | ✅ |
| team_velocity_mean | Mean team movement speed (ft/frame) | frame-level | ✅ |
| opp_velocity_mean | Opponent mean movement speed | frame-level | ✅ |

**Total: ~12 CV temporal features. All available for any game processed through the
CV pipeline, including games without valid homography (velocity features survive
without court registration).**

---

## 5. CV Biomechanical Features

**Source:** Pose estimation and shot biomechanics, extracted by Phase 10.5
(`add_pose_features` in `src/features/feature_engineering.py`).

| Feature | Definition | Source | Wired |
|---------|-----------|--------|-------|
| ankle_x, ankle_y | Ankle joint coordinates from pose estimation | `add_pose_features` | Partial |
| contest_arm_angle | Angle of nearest defender's contest arm | `add_pose_features` | Partial |
| jump_detected | Binary: player in jump phase at shot release | `add_pose_features` | Partial |
| shot_arc | Inferred shot arc from wrist-to-ball trajectory | `add_pose_features` | Partial |
| body_lean | Torso lean angle at shot release | `add_pose_features` | Partial |
| contact_indicator | Binary: defensive contact detected | `add_pose_features` | Partial |

**Total: ~6 CV biomechanical features. Phase 10.5 code complete; feature availability
depends on pose model quality per game. Not used in current betting stack (wired but
not in active feature set).**

---

## 6. Market Microstructure Features

**Source:** Odds API, Pinnacle direct, Action Network. Collected by
`src/data/line_monitor.py` and `src/data/action_network.py`.

| Feature | Definition | Source | Wired |
|---------|-----------|--------|-------|
| pinnacle_no_vig_prob | Shin-devigged Pinnacle opening line probability | `betting_edge.py` | Partial |
| line_velocity | Pinnacle line movement per hour since open | `line_monitor.py` | Not in model |
| steam_flag | Binary: Pinnacle moved ≥0.5 pt in < 5 min | `line_monitor.py` | Not in model |
| public_pct | % of bets on one side (Action Network) | `action_network.py` | Not in model |
| vig_differential | Vig gap between Pinnacle and soft book | `betting_edge.py` | Partial |
| sharp_pct | % of money (not bets) on one side | `action_network.py` | Not in model |

**Total: ~6 microstructure features. Currently used in `bet_selector.py` as a filter
rather than as model features. Phase 14.7 wires the Pinnacle no-vig probability into
the bet_selector triangulation gate; Phase 16.7 adds the timing optimizer.**

---

## 7. Sentiment / NLP Features

**Source:** Injury reports, beat reporter Twitter, press conferences. Processed by
`src/prediction/nlp_models.py` (Phase 9).

| Feature | Definition | Source | Wired |
|---------|-----------|--------|-------|
| injury_severity | Numeric injury severity score from NLP classifier | `nlp_models.py` | Partial |
| reporter_credibility | Beat reporter reliability score (historical accuracy) | `beat_reporter_credibility.py` | Partial |
| lineup_freshness | Hours since last official lineup announcement | `nlp_models.py` | Partial |
| dnp_probability | Probability of DNP (did not play) | `dnp_predictor.py` | ✅ |
| load_signal | NLP-detected load management language in pregame reports | `nlp_models.py` | Partial |

**Total: ~5 NLP features. Phase 9 wired; coverage is partial because beat reporter
data collection is not fully automated. `dnp_predictor.py` (AUC 0.979) is the most
production-ready NLP model.**

---

## Feature Count Summary

| Class | Count | Status |
|-------|-------|--------|
| API box-score | ~20 | ✅ Fully wired |
| API derived | ~12 | ✅ Fully wired |
| CV spatial | ~8 | Partial (29/80 target — 9 CLEAN + 20 PARTIAL) |
| CV temporal | ~12 | ✅ Fully wired |
| CV biomechanical | ~6 | Partial (not in betting stack) |
| Market microstructure | ~6 | Partial (filter only) |
| Sentiment / NLP | ~5 | Partial |
| **Total** | **~69** | |
