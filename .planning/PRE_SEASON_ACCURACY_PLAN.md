# Pre-Season Accuracy Maximization Plan
**Goal:** Every feature, model, and simulator component needed for maximum prediction accuracy before the full 2025-26 NBA season opens.
**Created:** 2026-03-26 | **Status:** 🔲 Not Started
**Priority:** Complete before October 2025 tip-off.

---

## Completion Status

| Block | Items | Status |
|-------|-------|--------|
| A — Feature Engineering | 14 additions | 🔲 |
| B — CV-to-Model Integration | 4 wires | 🔲 |
| C — Win Probability Upgrades | 8 features | 🔲 |
| D — Props Model Upgrades | 8 algorithmic | 🔲 |
| E — Possession Outcome Model | 5 upgrades | 🔲 |
| F — Monte Carlo Simulator | core build | 🔲 |
| G — Game Total / Spread Models | rebuild as ML | 🔲 |
| H — Validation & Calibration | 4 systems | 🔲 |

---

## Critical Path (ordered by dependency)

```
Phase G done (20 clean games)
  → A: Feature Engineering complete
    → B: CV data wired into models
      → E: Possession Outcome Model upgraded
        → F: Monte Carlo Simulator built
          → D: Props retrained with all features
            → C: Win Prob retrained with ELO + signals
              → G: Game total/spread rebuilt as ML
                → H: Validation + calibration
```

---

## Block A — Feature Engineering Completions
**File:** `src/features/feature_engineering.py`
**Priority:** Do first — everything downstream depends on clean features.

### A-1: Acceleration Rolling Features
**What:** `acceleration` column exists in tracking_data.csv but is never rolled. Add:
- `acceleration_mean_{30,90,150}` — sustained acceleration (explosive vs grind players)
- `acceleration_std_{90}` — variability (erratic vs smooth movers)
- `velocity_std_{30,90}` — burst detection (high std = stop-and-go, low = steady pace)

**Why:** Velocity mean alone misses player explosiveness. Steph Curry vs DeAndre Jordan have similar average speeds but totally different burst profiles. xFG v2 needs this.

### A-2: Fatigue Index
**What:** Per-player, per-game fatigue decay score.
```python
fatigue_index = dist_traveled_150 / player_season_avg_dist_per_min
# > 1.0 = running harder than normal → fatigue coming
# < 0.75 = coasting → potentially slumping or injured
```
**Why:** B2B fatigue models use rest days as proxy. This uses actual running load measured mid-game. Feeds xFG v2 (tired players shoot worse), props retrain (minutes/efficiency decay), injury risk.

### A-3: Defender Distance Rolling Features
**What:** `nearest_opponent` exists per-frame but is never rolled. Add:
- `defender_dist_mean_{30,90,150}` — average defensive pressure over time
- `defender_dist_min_{90}` — closest defender in last 3 seconds (shot quality)
- `contested_fraction_{90}` — fraction of frames with defender within 4 ft

**Why:** This is the core moat data. Must become ML features before it can influence predictions. Currently only raw per-frame values, useless for model training.

### A-4: Off-Ball Distance Rolling Features
**What:** `off_ball_distance` column written by pipeline, never rolled. Add:
- `off_ball_dist_mean_{90,150}` — average off-ball distance (spacing tendency)
- `off_ball_dist_std_{90}` — movement variability (cutter vs stagger)

### A-5: Paint Pressure Rolling Features
**What:** `paint_count_own` / `paint_count_opp` exist per-frame, never rolled. Add:
- `paint_pressure_{90}` — fraction of frames with ≥1 own player in paint
- `paint_pressure_opp_{90}` — opponent paint density (defense packing paint vs spacing)

### A-6: Shot Quality Using xFG Model (Replace Naive Proxy)
**What:** `shot_quality_proxy` is hand-tuned: `zone_w * (1/(1+opp_d/50)) * spacing_n`. Replace with actual xFG v1 call.
```python
# current (bad):
sq_proxy = zone_weight * (1 / (1 + opp_d/50)) * (0.5 + 0.5*spacing_n)
# correct:
from src.prediction.xfg_model import predict_xfg
sq_proxy = predict_xfg(ft_x, ft_y, defender_dist, game_clock, shot_type)
```
**Why:** xfg_v1.pkl was trained on 221K shots with Brier 0.226. The hand formula is a guess.

### A-7: ELO Rating Features
**What:** Build FiveThirtyEight-style ELO (K=20, home_advantage=100) from 3 seasons of game results. Store as `data/nba/elo_ratings.json`, update daily.
- Add `home_elo`, `away_elo`, `elo_differential` to all game-level feature sets.

**Why:** ELO corrects for strength of schedule automatically. Win% doesn't. A 35-win team that beat top-5 opponents is better than a 40-win team that played a soft schedule. ELO captures this.

### A-8: Opponent Defensive Trajectory
**What:** For each team, compute:
- `opp_def_rtg_last10` — last 10 games defensive rating
- `opp_def_rtg_trend` = `opp_def_rtg_last10 - opp_def_rtg_season`
  - Negative = defense improving → suppress offensive props
  - Positive = defense collapsing → boost offensive props

**Why:** Books use season-average defensive rating. A defense that's been on a 10-game tear getting exploited isn't captured by the average. The trend is the signal.

### A-9: Home/Away Split Differential
**What:** Per-player:
- `home_away_pts_delta` = `player_home_avg_pts - player_away_avg_pts`
- Same for reb, ast.

**Why:** Some players have 6+ pt home/away splits (arena-noise sensitive). Books blend to a single line. On road games, fade them. Edge: `~0.5 pts MAE improvement` on affected subset.

### A-10: Drive Outcome Distribution
**What:** From PBP event classification, per-player:
- `drive_finish_rate` — drives that end in FGA at rim
- `drive_foul_rate` — drives that draw FTA
- `drive_kickout_rate` — drives that generate kick-out AST
- `drive_turnover_rate` — drives lost to TOV

**Why:** Current model only has `drive_rate`. A 35% drive rate player who kicks out 60% of the time contributes AST, not PTS. Knowing outcome distribution separates scorers from facilitators.

### A-11: Interaction Terms
**What:** Add multiplicative features:
```python
b2b_road_combined    = b2b_flag * is_road_game
b2b_usage            = b2b_flag * usage_rate_season
contract_hot_streak  = contract_year_flag * hot_streak_score
foul_ref_tendency    = high_foul_ref_flag * foul_draw_rate
playoff_clutch       = playoff_push_flag * clutch_score
pace_uncertainty     = team_pace_variance * (1 - model_confidence)
```
**Why:** B2B fatigue is multiplicative, not additive. A 34 min/game player on B2B road is hurt 3x more than the sum of components. These terms are systematically missing from all current models.

### A-12: Dynamic Regression Weighting (Career vs Current Season)
**What:** Replace fixed season-average features with blended career/season weights:
```python
games_played = gamelog_season_count
season_weight = min(games_played / 50, 1.0)
blended_pts = (season_weight * season_avg_pts) + ((1-season_weight) * career_avg_pts)
```
- Games 1-10: 20% season, 80% career
- Games 11-25: 50% season, 50% career
- Games 26-50: 75% season, 25% career
- Games 50+: 90% season, 10% career

**Why:** In October (game 5), pure season average is noise. In March (game 70), career average is stale. Current model uses fixed proportions.

### A-13: Slump Type Detection
**What:** Compare current 10-game shot zone distribution vs career baseline.
- `shot_selection_shift` = KL-divergence of current zone distribution from career
- High KL + FG% drop = taking worse shots → will self-correct → OVER value
- Low KL + FG% drop = uniform slump → genuine cold streak → UNDER value

**Why:** Books treat all slumps identically. This splits them into two separate signals with opposite betting implications.

### A-14: Temporal Exponential Weighting for All Rolling Features
**What:** Add an exponentially-weighted version of all rolling features:
```python
# Half-life = 15 games
game_weight[i] = 0.5 ** (games_ago[i] / 15)
velocity_ewma_{90} = weighted_mean(velocity, game_weight, window=90)
```
Apply to: all rolling features in `add_rolling_features()`, all event rates, all per-100 normalizations.

**Why:** Games from 3 months ago shouldn't weight equally with last week. Current rolling windows are flat.

---

## Block B — CV Data Integration (The Moat)
**Current state:** Tracking data (defender_distance, spacing, ft_x/ft_y) collected but not wired into any prediction model.

### B-1: Defender Distance → xFG Adjustment
**File:** `src/prediction/xfg_model.py` and `src/prediction/possession_outcome_model.py`
**What:**
```python
# In possession_outcome_model.predict_outcome():
# Current: fg_pct uses only historical PBP zone rates
# Add: defender distance adjustment factor
def _defender_adjustment(defender_dist_ft: float) -> float:
    # Sigmoid: 0-2ft = 0.82x, 3-5ft = 0.91x, 6-10ft = 0.99x, 10+ft = 1.05x
    # Source: NBA shot dashboard avg_defender_dist vs FG% (validate against nba_api)
    return sigmoid_adjustment(defender_dist_ft)

fg_pct_adjusted = fg_pct_base * _defender_adjustment(defender_dist)
```

**Why:** This is the entire moat. Spatial CV data is only worth something if it adjusts predictions. Currently tracking data and prediction models are completely disconnected.

### B-2: Spacing Advantage → Possession Outcome Scaling
**File:** `src/prediction/possession_outcome_model.py`
**What:** Wire `spacing_advantage` (ft² hull differential) into shot_prob and fg_pct:
```python
# High spacing advantage (open court) → higher shot_prob + higher fg_pct
# Negative spacing (tight defense) → lower shot_prob, more drives
spacing_multiplier = 1.0 + 0.08 * sigmoid(spacing_advantage / 500)
shot_prob_adjusted = shot_prob * spacing_multiplier
```
**Calibration:** Validate multiplier range against PBP shot frequency distributions.

### B-3: Fatigue Index → Props Retrain
**File:** `src/prediction/player_props.py`
**What:** After Block A-2 adds `fatigue_index` to features.csv, add it to the props training feature set:
- `fatigue_index_game_avg` = mean fatigue index across all possessions for this player this game
- `dist_traveled_game_total` = cumulative distance in feet
- Add both to `_ALL_FEATS` in player_props.py and retrain all 7 props.

### B-4: xFG CV Stack Integration
**Note:** `xfg_cv_stack.pkl` exists in data/models/. Confirm it's being called in `shot_quality_proxy` (currently it's not — A-6 fix).

---

## Block C — Win Probability Upgrades
**File:** `src/prediction/win_probability.py`
**Current:** 34 features, Brier 0.203, 69.1% accuracy
**Target:** Brier < 0.195, 71%+ accuracy

### C-1: ELO Rating (Highest Single Feature Impact)
Add `home_elo`, `away_elo`, `elo_differential` to `FEATURE_COLS`.
ELO differential is the single most predictive pre-game win probability feature in academic literature (Hvattum & Arntzen, 2010). It adds ~1% accuracy.

### C-2: Opponent Defensive Trajectory
Add `home_def_rtg_trend`, `away_def_rtg_trend` (last10 vs season diff). See A-8.

### C-3: Team Pace Variance
Add `home_pace_variance`, `away_pace_variance` (std of possessions_per_game over last 20). High variance = high outcome uncertainty → affects confidence calibration.

### C-4: Hustle Stats Per Team
Add `home_hustle_deflections_pg`, `away_hustle_deflections_pg`. Hustle correlates with close-game wins — teams that fight harder in chaos win more than their net_rtg predicts.

### C-5: Synergy Head-to-Head
Add `home_pnr_ppp`, `away_pnr_ppp`, `iso_matchup_edge` (already in code as 4.6 feature, verify it's populated).

### C-6: Interaction Terms
Add: `b2b_home_diff` = `away_back_to_back - home_back_to_back` (signed), `elo_diff * pace_diff` (high-pace games amplify quality gaps).

### C-7: Lineup Quality Depth (Bench Rating)
Add `home_bench_net_rtg`, `away_bench_net_rtg` — from lineup on/off data. Starter-heavy analysis misses teams with strong benches. Affects foul trouble outcomes, close 4th quarter games.

### C-8: Retrain with All 42 Features
After C-1 through C-7: full retrain with `sklearn` updated, cross-validated walk-forward. Log Brier score improvement per feature batch.

---

## Block D — Props Model Upgrades (Algorithmic)
**Files:** `src/prediction/player_props.py`, `src/prediction/prop_model_stack.py`
**Current:** Props v2 at R² > 0.93 (but this is high training R², not holdout test accuracy)

### D-1: Quantile Regression (Highest Single Upgrade)
**What:** Replace mean-prediction XGBoost with quantile regression at 5 levels:
```python
from sklearn.ensemble import GradientBoostingRegressor
quantile_models = {
    0.10: GBR(loss='quantile', alpha=0.10),  # floor
    0.25: GBR(loss='quantile', alpha=0.25),
    0.50: GBR(loss='quantile', alpha=0.50),  # median (replaces current)
    0.75: GBR(loss='quantile', alpha=0.75),
    0.90: GBR(loss='quantile', alpha=0.90),  # ceiling
}
```
Output: `P(stat > line)` directly from quantile curve interpolation. No Gaussian assumption.
**Why:** NBA stats are right-skewed (Jokic 50-pt game exists, 0-pt Jokic doesn't). Predicting the mean then assuming normality systematically underestimates upside tails.

### D-2: HMM Regime Detection (Streaky Players)
**What:** Two-state Hidden Markov Model per player with `autocorrelation > 0.35`:
```python
from hmmlearn import hmm
# State 0: cold (lower_mean, higher_variance)
# State 1: hot  (higher_mean, lower_variance)
# P(currently hot | last_10_games) → hot_prob feature
prediction = hot_prob * hot_mean + (1-hot_prob) * cold_mean
```
**Apply to:** Curry, Kyrie, Booker, Lillard (streaky by nature). Auto-detect via ACF.
**Skip for:** Jokic, DeRozan (consistent) — add noise, not signal.

### D-3: Bayesian Hierarchical (Small Sample)
**What:** For players with `games_played < 25` (early season / injury returns):
```python
# Prior: position-archetype mean (PG_PnR_handler, C_rim_runner, etc.)
# Likelihood: actual games so far
# Posterior: smoothed estimate
blend = min(games_played / 25, 1.0)
prediction = blend * xgboost_prediction + (1-blend) * hierarchical_prediction
```
**Why:** In October every team has 5 games. XGBoost overfits to 5 data points. Books use preseason projections. Your model uses real data blended with archetype priors.

### D-4: Optimal Lookback Per Player
**What:** Fit AR(p) model on each player's gamelog, use AIC/BIC to select optimal window:
- Consistent players (Jokic): 20+ games
- Volatile players (Westbrook): 5-8 games
- Returning from injury: 3 games

Currently all players use the same rolling windows (5/10/15/20). Wrong for everyone who isn't average.

### D-5: Asymmetric Loss Function
**What:** Replace MSE in XGBoost training with:
```python
def betting_loss(y_true, y_pred, alpha=1.5):
    residuals = y_true - y_pred
    return np.where(residuals >= 0,
                    alpha * residuals**2,
                    residuals**2).mean()
# alpha > 1: penalizes overconfidence (betting false edges)
```
**Why:** In betting, being wrong confidently costs more than being right cautiously. Standard MSE doesn't know this.

### D-6: Multi-Task Learning (Shared Player Representation)
**What:** PyTorch multi-task model: shared 128-dim player encoder → separate task heads for pts/reb/ast/3pm/stl/blk/tov.
- Shared encoder forces better player representation (pts and ast are correlated through usage)
- Especially valuable for low-sample players (5-10 games)

### D-7: Conformal Prediction Intervals
**What:** Calibration holdout (10% of data) → learn residual distribution → compute valid prediction intervals.
```python
# "My 80% interval covers the true value exactly 80% of the time"
# Narrow interval → confident → bet. Wide interval → uncertain → skip.
from nonconformist import IcpRegressor
```
Wire interval width into BetFilter: only bet when conformal interval < 1.5× vig_width.

### D-8: Per-Segment Platt Calibration
**What:** Separate calibration curves for: star_players, role_players, b2b_games, early_season_g10, home_games, road_games, post_injury_return, post_trade_14d.
**Why:** One calibration curve for all situations is wrong. Model confidence on B2B means something different than confidence in normal rest. 70% confident should mean 70% in EVERY segment.

---

## Block E — Possession Outcome Model Upgrades
**File:** `src/prediction/possession_outcome_model.py`
**Current:** PBP lookup table → shot_prob, tov_prob, fta_prob, fg_pct per player per play_type per zone. Laplace smoothed.

### E-1: Wire Defender Distance into fg_pct
See B-1. This is the most critical single connection in the system.

### E-2: Wire Spacing Advantage into shot_prob
See B-2.

### E-3: Game State Context
**What:** Add `score_diff` and `period` as inputs to `predict_outcome()`:
```python
def predict_outcome(player_id, play_type, zone, opp_team,
                    score_diff=0, period=2) -> dict:
    # Down 15 in Q4: tov_prob ↑, shot_prob ↑ (desperate), fg_pct ↓ (rushed)
    # Up 15 in Q4: tov_prob ↑ (lazy), shot_prob ↓ (ball movement)
    context_factor = _game_state_multiplier(score_diff, period)
```
Build multiplier table from PBP: `(score_diff_bucket, period) → {shot_prob_mult, tov_mult, fta_mult}`

### E-4: Lineup Context Scaling
**What:** Pass `lineup_on_off_diff` into predict_outcome. A LeBron possession with 4 shooters vs 4 non-shooters has different fg_pct.
```python
# lineup_quality = on_off_diff of current 5-man unit
lineup_multiplier = 1.0 + 0.03 * sigmoid(lineup_quality / 5.0)
shot_prob *= lineup_multiplier
```

### E-5: Replace Zone Classification with xFG Zone
**What:** Current zone classifier parses PBP text ("paint", "3pt", "midrange"). Wire `court_zone` from CV tracking instead — gives precise location, not text-parsed bucket.

---

## Block F — Monte Carlo Possession Simulator (CORE BUILD)
**Files:** `src/simulation/game_simulator.py` (NEW)
**Status:** DOES NOT EXIST — `spread_est = (prob-0.5)*30` is a formula, not a simulation.
**This is the most critical missing piece in the entire system.**

### F-1: Possession Loop
```python
class GameSimulator:
    def simulate_game(self, home_lineup, away_lineup, n_sims=10000) -> SimResult:
        """
        For each simulation:
        1. Determine possession count from game_possessions_model.predict()
        2. For each possession:
           a. Determine ball handler: usage_rate weighted random choice from lineup
           b. Determine play type: synergy distribution for this player
           c. Determine court zone: shot_zone_tendency.py distribution
           d. Call predict_outcome(player, play_type, zone, opp, score_diff, period)
           e. Sample outcome: shot / tov / foul
           f. If shot: sample make/miss from fg_pct_adjusted (with B-1 defender adjustment)
           g. If FT: sample FT makes from player FT%
           h. Update score, time, quarter
           i. Handle foul trouble (foul cascade from Markov chain)
        3. Return final score distribution
        """
```

### F-2: Player Stat Accumulation
```python
# Track per-simulation:
# - pts: FGM*2/3 + FTA*FT%
# - reb: possessions * reb_rate (from player_props model)
# - ast: passes that led to made FG
# - tov: turnover count
# Across 10,000 sims → full distribution for each player stat
# P(pts > line) = fraction of sims where pts_simulated > line
```

### F-3: Lineup Substitution Model
```python
# Use substitution_timing_model.pkl (already trained)
# Foul trouble: 3 fouls in first half → bench probability from foul_transition_matrix
# Blowout: score_diff > 20 with 5 min left → starters exit
# Updates lineup mid-simulation, changes usage weights
```

### F-4: Fatigue Accumulation
```python
# Minutes played → efficiency decay function (from fatigue_index)
# Q4 efficiency = Q1 efficiency * fatigue_multiplier(minutes_played, player_position)
# High-usage players decay more per minute
```

### F-5: Output
```python
@dataclass
class SimResult:
    home_win_prob: float
    spread_distribution: np.ndarray    # 10K samples
    total_distribution: np.ndarray     # 10K samples
    player_stats: dict                 # {player_id: {pts: array, reb: array, ...}}

    def prop_probability(self, player_id, stat, line) -> float:
        return (self.player_stats[player_id][stat] > line).mean()

    def spread_probability(self, spread_line) -> float:
        return (self.spread_distribution > spread_line).mean()
```

### F-6: Performance Target
- 10,000 simulations in < 60 seconds on CPU (vectorize with numpy, no Python loops)
- Validate: simulated stat distributions should match actual game distributions within 10%

---

## Block G — Game Total / Spread Models (Rebuild as ML)
**File:** `src/prediction/game_prediction.py`
**Current state:** `spread_est = (prob-0.5)*30` and `predict_total()` is arithmetic — these are NOT ML.

### G-1: Spread Model (XGBoost Regression)
**Features:**
- All win_prob features (elo_diff, ratings, pace, etc.)
- `recent_margin_home_last5`, `recent_margin_away_last5`
- `pythagorean_win_pct_diff` (points_for² / (points_for² + points_against²))
- `home_ats_last5` (against-the-spread record — captures public line accuracy)
- `home_def_rtg_trend`, `away_def_rtg_trend`

**Target:** actual point differential (not binary win). Train on 3 seasons.
**Expected:** MAE ~7-8 pts (Vegas baseline ~7.2 pts).

### G-2: Total Model (XGBoost Regression)
**Features:**
- `pace_avg`, `off_rtg_sum`, `def_rtg_sum`
- `ref_pace_tendency`, `ref_fta_per_game` (high-foul refs add points)
- `synergy_transition_ppp_sum` (transition teams = more pts)
- `home_pace_variance`, `away_pace_variance`
- `home_clutch_score`, `away_clutch_score` (close games → more possessions down stretch)
- `altitude_flag` (Denver/Utah → lower scores)
- `travel_direction_penalty` (east→west time zone shift)

**Target:** actual total points. Train on 3 seasons.

### G-3: Wire Simulator Output into Game Models (Phase F)
Once Monte Carlo simulator exists: replace XGBoost spread/total with simulator output (mean of spread_distribution, mean of total_distribution). ML models remain as pre-simulation fallback.

---

## Block H — Validation and Calibration
**Build these last — after all models retrained.**

### H-1: Walk-Forward Backtester for All Models
- For each model: train on seasons 1-2, validate on season 3 (never use future data)
- Measure: MAE, Brier, hit_rate (% of overs/unders correctly predicted), CLV proxy
- Gate: new model must beat previous version on ALL metrics before replacing

### H-2: Platt Scaling Calibration (All Models)
- After training each model, fit Platt scaler on holdout 10%
- Verify: P(outcome | model says 70%) = 70% ± 3%
- Segment calibration: separate curves for b2b, early_season, post_injury, post_trade

### H-3: SHAP Importance Audit
- Run SHAP on every trained model after Block A-D features added
- Required: every new feature from this plan must appear in SHAP top 30
- Any feature with SHAP importance < 0.001 → remove (noise)
- Output: `data/models/{model}_shap_report.json` for each model

### H-4: Regression Detection Baseline
- For each player, compute career `actual_fg_pct - xFG_v1` gap
- `gap > +0.04` → persistent elite shooter (don't fully regress)
- `gap < -0.03` → structural inefficiency (regress harder)
- Store as `data/nba/player_xfg_gaps.json` — used by simulator and props retrain

---

## Sequenced Execution Order

**Sprint 1 (CV data ready — after Phase G complete):**
- A-1, A-2, A-3, A-4, A-5 (feature additions that need tracking data)
- B-1, B-2 (wire CV data into models — highest leverage)
- E-1, E-2 (upgrade possession outcome model with spatial data)

**Sprint 2 (Pure code — no new data needed):**
- A-6 (replace shot_quality_proxy with xFG)
- A-7 (ELO rating — build from existing game results in cache)
- A-8, A-9, A-10, A-11, A-12, A-13, A-14 (remaining feature engineering)
- C-1 through C-7 (win prob feature additions)
- E-3, E-4, E-5 (possession outcome context upgrades)

**Sprint 3 (Model rebuilds):**
- F-1 through F-6 (Monte Carlo simulator — core build)
- G-1, G-2 (spread and total as ML models)
- B-3, B-4 (props retrain with CV features)

**Sprint 4 (Algorithmic upgrades):**
- D-1 (quantile regression)
- D-2 (HMM regime detection)
- D-3 (Bayesian hierarchical)
- D-4 (optimal lookback)
- D-5, D-6, D-7, D-8 (remaining prop upgrades)

**Sprint 5 (Retrain everything with all features):**
- C-8 (win prob retrain)
- Retrain all 7 props with full feature set
- Retrain matchup model
- G-3 (wire simulator into game prediction)

**Sprint 6 (Validation):**
- H-1 (walk-forward backtest all models)
- H-2 (Platt calibration)
- H-3 (SHAP audit)
- H-4 (regression detection baseline)

---

## Expected Impact Per Block

| Block | Model Affected | Expected Improvement |
|-------|---------------|----------------------|
| A: Feature Engineering | All | Baseline for everything below |
| B: CV Integration | xFG, simulator, props | Activates moat — largest unique edge |
| C: Win Prob Upgrades | Win probability | Brier 0.203 → ~0.192 (+1.5% accuracy) |
| D-1: Quantile Regression | All props | Direct P(over) without Gaussian error |
| D-2: HMM Regime | Streaky players | +3-5% on high-autocorrelation players |
| D-3: Bayesian Hierarchical | Early season (<25 games) | +4-6% on Oct-Nov slate |
| D-4: Optimal Lookback | All props | +0.5-1% MAE volatile players |
| D-5: Asymmetric Loss | All props | Lower false-confidence rate |
| E: Possession Outcome | Simulator | Foundation accuracy |
| F: Monte Carlo Simulator | Spread, total, all props | Replaces formulas with 10K-path simulation |
| G: Spread/Total as ML | Game lines | MAE 7.2 → ~7.0 pts (Vegas-level) |
| H: Validation | All | Confirms improvements are real, not overfit |

---

## Notes

- **Don't retrain on small samples.** Wait for Phase G 20 clean games before any CV-based retrain.
- **CV data is only in 4 games now.** Features A-1 through A-5 require tracking data to populate. With 4 games you can validate they're working but not train on them yet. Build the features now so when 20 games exist, retraining is immediate.
- **ELO (A-7, C-1) needs no new data** — build from `data/nba/season_games_*.json` which already exists.
- **Simulator (Block F) is the critical path item.** Everything else improves accuracy incrementally. The simulator enables: accurate spread, accurate total, full player stat distributions, lineup optimization, correlated prop pricing. Nothing else unlocks all four simultaneously.
- **Quantile regression (D-1) enables alternate line scanning** (alt_line_ev_model.py) to actually work — needs a probability curve, not a single point estimate.
