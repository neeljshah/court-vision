# Possession Simulator — Best Possible Design Plan

**Goal:** Improve win probability (currently 69.1%) and player props (pts R²=0.47, MAE=4.88)
**Constraint:** No wiring yet. This is the design document.
**Written:** 2026-03-26

---

## Executive Summary

The current simulator has **three structural problems** that prevent it from improving either
win probability or player props no matter how many models are added:

1. **Players are simulated independently.** There's no shared team state. If LeBron scores 40
   in a sim, his teammates still get their full usage — no competition for shots.

2. **Game score is disconnected from player stats.** `home_score` comes from a separate
   `rng.normal(predicted_total/2, ...)` call, not from summing player contributions. The
   simulator's win probability has nothing to do with the player distributions.

3. **All 10,000 sims are identical.** `rng = np.random.default_rng(seed=42)` — hardcoded seed
   means every run produces the same 10,000 numbers. There is zero stochastic variance.

Fix these three things first. Everything else builds on top.

---

## Current State: What the Simulator Actually Does

```
for each player independently:
    mins ~ Normal(avg_min, avg_min*0.15)
    fga  ~ Poisson(fga_rate * mins * pace_scalar)
    fgm  ~ Binomial(fga, season_fg_pct * cv_adj)      ← cv_adj never injected
    fg3m ~ Binomial(fg3a, season_fg3_pct)              ← independent from fgm!
    tov  ~ Poisson(tov_rate * mins)
    reb  ~ Poisson(reb_rate * mins)
    stl  ~ Poisson(stl_rate * mins)
    blk  ~ Poisson(blk_rate * mins)
    pts  = 2*fgm + fg3m + ftm                          ← disconnected from game score

home_score ~ Normal(total/2 + spread/2, total*0.07)   ← no relation to player pts
win_prob   = mean(home_score > away_score)             ← not derived from player sims
```

**Result:** Win probability from the simulator is just a Normal curve around the input spread.
It adds no information. Player distributions are independent Poissons with no coupling.

---

## The Right Architecture: Possession-by-Possession with Shared Team State

Instead of simulating each player across a full game, simulate each **possession**.
Each possession has a ball handler, a play type, and an outcome. Player stats are
tallies of what happened to them during possessions. Team scores sum naturally.

```
for each sim (10,000):
    home_score = 0; away_score = 0
    player_stats = {pid: zeros} for all active players

    for each possession (~200 per game, ~100 per team):
        offense = home | away (alternates, turnovers switch)

        1. PACE     → how many possessions this game? (game_pace.json)
        2. LINEUP   → who's on court? (minutes_floor + rotation_predictor + dnp_model)
        3. HANDLER  → who handles the ball? (usage_rate_model, usage-weighted sample)
        4. PLAY     → what type? (synergy_offense distribution for this player+team)
        5. OUTCOME  → shot_prob, tov_prob, fta_prob (possession_outcome_model)
        6. FG%      → if shot: xfg_v1 + matchup_model + CV features
        7. REBOUND  → if miss: team oreb% → extra possession or switch
        8. FOUL     → if foul: FT attempt, foul tally update (foul_trouble.pkl)
        9. CLOCK    → update game_time, check period, check late-game context
        10.ACCUM    → update player_stats[handler] and player_stats[rebounder]

    win_prob = mean(home_score > away_score across 10K sims)
    player_dists = {pid: {stat: array(10K)}}
```

This produces:
- **Win probability** derived from actual simulated scores — not a Normal distribution guess
- **Player distributions** that are correlated — stars and role players compete for usage
- **Consistency** — player stats sum to team score (they should be close, not disconnected)

---

## Layer 0: Fix Critical Bugs Before Adding Any Models

These must be fixed first or everything built on top will be wrong.

### BUG-1: Hardcoded RNG seed (all 10K sims identical)
```python
# CURRENT (line 252):
rng = np.random.default_rng(seed=42)

# FIX: Remove seed entirely — each call to simulate() must be random
rng = np.random.default_rng()
```

### BUG-2: fg3m generated independently from fgm (can exceed total FGM)
```python
# CURRENT: fg3m_arr = rng.binomial(fg3a_arr, fg3pct)
# fgm_arr and fg3m_arr are sampled separately — fg3m can be > fgm in same sim row

# FIX: Sample 3PA from total FGA. fg3m is a subset of fgm.
fg3a_arr = rng.binomial(fga_arr, fg3a_frac)          # 3PA ⊂ FGA
fg2a_arr = fga_arr - fg3a_arr                        # 2PA = FGA - 3PA
fg3m_arr = rng.binomial(fg3a_arr, fg3pct)            # 3PM from 3PA
fg2m_arr = rng.binomial(fg2a_arr, fg2pct)            # 2PM from 2PA
fgm_arr  = fg2m_arr + fg3m_arr                       # total FGM
pts_arr  = 2*fg2m_arr + 3*fg3m_arr + ftm_arr        # correct pts formula
```

### BUG-3: Game score disconnected from player stats
The game-level Normal draw must be replaced with the summed player score architecture
(see Layer 2). Until then, `home_win_prob` output is meaningless as a simulator product.

---

## Layer 1: Wire Existing Trained Models as Seeds

No architecture change. Replace hardcoded constants with trained model outputs.
These are all trained and ready today — no new data needed.

### L1-A: Replace `total/222` pace formula with `game_pace.json`

```python
# CURRENT (line 443):
return float((predicted_total or 222.0) / 222.0)

# REPLACE WITH:
pace_model = load("data/models/game_pace.json")
possessions = pace_model.predict(home_team, away_team, game_features)
# Returns estimated possessions per team (e.g. 98.3)
```

**Impact:** Correct team pace affects how many FGAs each player accumulates per game.
High-pace teams (OKC ~103 poss) produce more stat volume than slow teams (NYK ~96 poss).
Getting this right directly affects pts/reb/ast distributions.

### L1-B: Replace `mins < 3.0` DNP check with `dnp_model.pkl` (AUC 0.979)

```python
# CURRENT (line 385):
dnp_mask = mins_arr < 3.0   # arbitrary threshold

# REPLACE WITH:
dnp_prob = dnp_model.predict_proba(player_id, game_context)
# dnp_mask = rng.binomial(1, dnp_prob, n_sims).astype(bool)
# This propagates DNP uncertainty into the distribution (not binary)
```

**Impact on props:** If a player has 25% DNP probability, his expected stats should
drop by 25% and his distribution should have a spike at zero. Currently the simulator
ignores this entirely for active players. DNP model has AUC 0.979 — extremely reliable.

### L1-C: Replace hardcoded `_OREB_RATE = 0.27` with per-team offensive rebound rate

```python
# CURRENT (line 47):
_OREB_RATE = 0.27   # league average

# REPLACE WITH:
home_oreb_pct = team_stats[home_team]["oreb_pct"]   # from nba_api cache
away_oreb_pct = team_stats[away_team]["oreb_pct"]
# Range: 0.20 (worst) to 0.35 (best rebounding teams)
```

**Impact:** Teams in the extremes (OKC, MIL) see 30%+ variance vs league average.
Oreb% affects how many possessions each team gets, which feeds directly into
pts/reb distributions.

### L1-D: Replace Poisson TO/foul constants with `possession_outcome_model`

```python
# CURRENT (line 365):
tov_rate = avg_tov / max(avg_min, 1.0)
tov_arr  = rng.poisson(tov_rate * mins_arr)

# REPLACE WITH:
outcome = possession_outcome_model.predict_outcome(
    player_id=pid,
    play_type=sampled_play_type,
    zone=sampled_zone,
    opp_team=opp_team,
    score_diff=current_score_diff,   # game state context
    period=current_period,
    lineup_quality=on_off_diff,
)
# outcome = {shot_prob, tov_prob, fta_prob, fg_pct_est}
# Use outcome["tov_prob"] instead of league-average Poisson rate
```

**Why this matters:** The possession_outcome_model was trained on 3,627 PBP games.
It knows that LeBron has a 9% turnover rate on ISO plays but 6% on spot-ups.
The current simulator uses the same league-average 13.5% for every player on every play.

This model already includes:
- Per-player per-play-type tov_prob, shot_prob, fta_prob, fg_pct
- Defender distance adjustment (sigmoid, validated against shot dashboard)
- Spacing multiplier (team spacing → shot probability)
- Game state context (blowout: tov +15%, clutch: tov -8%)
- Lineup quality scaling (on/off differential)
- Zone-specific FG% (paint vs midrange vs 3pt)

None of this is being used.

### L1-E: Add matchup adjustment from `matchup_model.json` (R²=0.796)

```python
# For each ball-handler × defender matchup:
matchup_edge = matchup_model.predict(player_id, primary_defender_id)
# Returns: pts_per_100 differential for this matchup

# Apply as fg_pct multiplier:
fg_pct_adj = base_fg_pct * (1.0 + matchup_edge * 0.01)
```

**Why this matters:** A player guarded by his worst defensive matchup vs his best
matchup can have 4-6 PPP swing. The current simulator ignores defense entirely —
it uses the same FG% regardless of who's on the other team. matchup_model.json has
R²=0.796, the highest-accuracy model in the entire system.

### L1-F: Replace `xfg_v1` for FG% (Brier 0.226 > league average 0.24)

```python
# CURRENT (line 354):
fgm_arr = rng.binomial(fga_arr, fg_pct)   # fg_pct = season average

# REPLACE WITH:
xfg_prob = xfg_v1.predict(player_id, shot_distance, defender_dist, season_context)
fgm_arr  = rng.binomial(fga_arr, xfg_prob)
```

**Why this matters:** xFG accounts for shot distance, shot type, and defender distance.
It knows that a guarded mid-range is 38% and an open corner 3 is 41% — the raw FG%
for both players might both be 45%. xFG v1 has Brier 0.226 vs the 0.24 baseline.

---

## Layer 2: Possession-by-Possession Architecture (The Core Upgrade)

This is the most impactful change. Rebuild `_simulate_player()` into
`_simulate_game()` — a single shared loop over possessions.

### New Data Flow

```python
def _simulate_game(self, home_roster, away_roster, game_context, n_sims):
    """
    Simulate n_sims full games possession-by-possession.
    Returns (home_score_dist, away_score_dist, player_stat_arrays).
    """
    poss_per_team = game_pace_model.predict(game_context)  # e.g. 98.3

    # Per-player probability tables (computed once, used all sims)
    usage  = {pid: usage_rate_model.predict(pid, game_context) for pid in all_players}
    dnp_p  = {pid: dnp_model.predict(pid, game_context) for pid in all_players}
    mins_p = {pid: minutes_floor_model.predict(pid, game_context) for pid in all_players}

    # Normalize usage within each team (must sum to 1.0 for active players)
    home_usage = _normalize_usage(usage, home_roster, dnp_p)
    away_usage = _normalize_usage(usage, away_roster, dnp_p)

    # Simulation batch — vectorized over n_sims
    home_scores = np.zeros(n_sims)
    away_scores = np.zeros(n_sims)
    player_pts  = {pid: np.zeros(n_sims) for pid in all_players}
    # ... other stats

    for possession_n in range(int(poss_per_team * 2)):
        offense  = home_roster if possession_n % 2 == 0 else away_roster
        defense  = away_roster if possession_n % 2 == 0 else home_roster
        usage_w  = home_usage  if possession_n % 2 == 0 else away_usage

        period    = min(4, possession_n // (poss_per_team // 2) + 1)
        score_diff = (home_scores - away_scores).mean().astype(int)  # approximate

        # 1. Select ball handler (usage-weighted sample)
        handler = rng.choice(offense, p=usage_w, size=n_sims)

        # 2. Sample play type per handler from team synergy distribution
        play_type = self._sample_play_type(handler, offense_team)

        # 3. Get possession outcome probs from possession_outcome_model
        outcomes = self._batch_predict_outcome(handler, play_type, defense,
                                               score_diff, period)
        # outcomes[i] = {shot_prob, tov_prob, fta_prob, fg_pct_est}

        # 4. Determine possession result (vectorized)
        result = self._resolve_possession(outcomes, rng, n_sims)
        # result = {pts: array(n_sims), is_tov: array, is_foul: array, is_oreb: array}

        # 5. Update scores
        if offense is home_roster:
            home_scores += result["pts"]
        else:
            away_scores += result["pts"]

        # 6. Update player stat tallies
        for sim_i, pid in enumerate(handler):
            player_pts[pid][sim_i] += result["pts"][sim_i]
            # ... reb, ast, tov, etc.

    return home_scores, away_scores, player_pts
```

### Why This Solves the Coupling Problem

When LeBron takes a shot on possession #47, he was selected because his `usage_weight`
was drawn from the normalized usage distribution. His teammates had their usage reduced
proportionally. If LeBron is shooting well in this sim, the remaining possessions
still have his usage weight — he gets more possessions in hot-hand games, fewer in
cold games. This is how real basketball works.

The team score = sum of possession pts. The win probability = mean(home > away). These
are not separate calculations — they're the same data.

### Usage Normalization (Critical Detail)

```python
def _normalize_usage(usage_dict, roster, dnp_probs):
    """
    Given raw usage rates, return per-possession probabilities that sum to 1.
    DNP players get weight 0. Remaining weights are renormalized.
    """
    active = [pid for pid in roster if rng.random() > dnp_probs[pid]]
    raw    = np.array([usage_dict[pid] for pid in active])
    return active, raw / raw.sum()
```

This is the mechanism that makes player stats correlated. Absent players shift usage
to teammates — exactly what happens in real games when someone is DNP.

---

## Layer 3: CV Feature Injection (Requires Phase G — 20 Clean Games)

The `inject_cv_features()` hook already exists. Once Phase G completes:

```python
# Per-game, per-player CV features from tracking_data.csv
simulator.inject_cv_features({
    player_id: {
        "defender_dist": tracking.groupby("player_name")["defender_distance"].mean(),
        "spacing":       features.groupby("team_abbrev")["spacing_advantage"].mean(),
        "fatigue":       compute_fatigue(tracking, player_id),  # dist traveled
        "shot_clock":    features["shot_clock"].mean(),
    }
    for player_id in game_roster
})
```

### CV Impact on FG% Accuracy

The possession_outcome_model already has a sigmoid curve for defender_dist:
- 0–2 ft defender: FG% × 0.82
- 4–6 ft defender: FG% × 0.93
- 10+ ft defender: FG% × 1.04

When we inject real tracking data, the simulator knows that Curry gets wide open looks
(defender_dist 7+ ft) on average but Embiid is always contested (2–3 ft). This is
invisible in NBA API data but visible in broadcast tracking.

**Expected improvement:** CV-adjusted FG% → pts distribution tighter by ~0.5 pts MAE.

### CV Impact on Spacing

The spacing multiplier affects `shot_prob` (whether a possession results in a shot):
- High spacing (good 3pt shooting team): +12% shot_prob
- Low spacing (no shooters): −12% shot_prob

This affects teams like Golden State (highest shot_prob) vs teams that force contested
dribble-drive situations.

---

## Layer 4: Use Simulator to Feed Back Into Win Prob and Props

This is where the simulator becomes a force multiplier, not a replacement.

### Win Probability: Simulator as Feature Generator

The XGBoost win probability model (69.1%) is trained on team-level stats.
Run the simulator first, add its outputs as features, retrain:

```python
# New features for win_probability.py training:
sim_result = simulator.simulate(game_id, n_sims=1000)   # fast run for features
X_new_features = {
    "sim_home_win_prob":    sim_result.home_win_prob,
    "sim_pts_std_home":     sim_result.home_score_dist.std(),
    "sim_pts_std_away":     sim_result.away_score_dist.std(),
    "sim_total_mean":       (sim_result.home_score_dist + sim_result.away_score_dist).mean(),
    "sim_spread_mean":      (sim_result.home_score_dist - sim_result.away_score_dist).mean(),
    "sim_ot_prob":          (abs(sim_result.home_score_dist - sim_result.away_score_dist) < 3).mean(),
}
# Add to the 47 existing FEATURE_COLS in win_probability.py
# Retrain XGBoost with these new features
```

The simulator encodes lineup-level information (which players are injured/resting,
DNP probabilities, usage matchups) that the team-rating features miss.

**Expected win prob improvement:** 69.1% → 71–73% after retrain with sim features.

### Player Props: Use Simulator for Distributions, XGBoost for Point Estimates

The current props pipeline outputs a single number (point estimate). Betting lines
need a **probability** — P(pts > 24.5). The simulator provides this directly.

**Proposed blended architecture:**

```python
# Step 1: XGBoost gives the best point estimate (seed for simulator)
xgb_pred = predict_props(player, opp, season)
# xgb_pred = {pts: 26.3, reb: 7.1, ...}

# Step 2: Inject XGBoost prediction as simulator seed rate
# The simulator uses XGBoost pts/min as the rate, not just season average
# This means XGBoost's opponent/rest/context adjustments are preserved

# Step 3: Run simulator → get full distribution
sim_result = simulator.simulate(game_id, player_ids=[player_id])
dist = sim_result.distributions[player_id]["pts"]   # array(10K)

# Step 4: over_prob from distribution (not a Gaussian assumption)
p_over = sim_result.over_prob(player_id, "pts", line=24.5)

# Step 5: Calibrate — does simulator mean match XGBoost mean?
sim_mean = dist.mean()
xgb_mean = xgb_pred["pts"]
if abs(sim_mean - xgb_mean) > 2.0:
    # Blend: weight XGBoost 60%, simulator 40%
    blended_mean = 0.6 * xgb_mean + 0.4 * sim_mean
    dist = dist * (blended_mean / sim_mean)  # scale distribution
```

The distribution shape from the simulator (right-skewed for scorers, Poisson-like for
rare events) is more realistic than the implicit Normal assumption in the current
over_prob calculation.

**Expected props improvement:** Calibration-adjusted over_prob → +3–5% Kelly betting ROI.

---

## Model Integration Map (All Models, Priority Order)

| Priority | Model | File | What it replaces | Impact |
|---|---|---|---|---|
| 🔴 BUG | Fix RNG seed=42 | possession_simulator.py:252 | Broken stochasticity | Critical |
| 🔴 BUG | Fix fg3m independence | possession_simulator.py:357-361 | Wrong pts formula | Critical |
| 🔴 BUG | Disconnect game score | possession_simulator.py:272-278 | Meaningless win prob | Critical |
| 1 | `possession_outcome_model` | predict_outcome() | Hardcoded Poisson rates | Very high |
| 2 | `dnp_model.pkl` (AUC 0.979) | predict_proba() | `mins < 3.0` check | High |
| 3 | `game_pace.json` | predict() | `total/222` formula | High |
| 4 | `matchup_model.json` (R²=0.796) | predict() | No opponent adjustment | High |
| 5 | `usage_rate_model.pkl` | predict() | Hardcoded usage weights | High |
| 6 | `xfg_v1.pkl` (Brier 0.226) | predict() | Season avg FG% | Medium |
| 7 | Team oreb% from cache | team_stats lookup | Hardcoded 0.27 | Medium |
| 8 | `minutes_floor.pkl` | predict() | Normal(avg_min, ...) | Medium |
| 9 | `foul_trouble.pkl` | predict() | No foul modeling | Medium |
| 10 | `home_away_model.pkl` | predict() | No H/A split | Low-medium |
| 11 | CV features (Phase G) | inject_cv_features() | None currently | High (when ready) |
| 12 | Sim as win_prob feature | retrain win_probability.py | Standalone XGBoost | Win prob +2-4% |
| 13 | Sim distributions for Kelly | betting_portfolio.py | Gaussian over_prob | Kelly calibration |

Models skipped (stubs or too sparse):
- `stl/blk props` — R² < 0.15, keep Poisson for now
- `age_curve_model`, `altitude_model`, etc. — stubs, no training data

---

## Accuracy Projections

| Metric | Current | After L0+L1 (bugs+models) | After L2 (poss-by-poss) | After L3 (CV) | After L4 (retrain) |
|---|---|---|---|---|---|
| Win prob accuracy | 69.1% | 69.5% | 70.5% | 71.0% | **72–74%** |
| Win prob Brier | 0.203 | 0.198 | 0.193 | 0.189 | **~0.185** |
| Props pts R² | 0.471 | 0.48 | 0.50 | 0.53 | **0.55–0.58** |
| Props pts MAE | 4.88 | 4.60 | 4.30 | 4.00 | **3.7–4.0** |
| over_prob calibration | N/A | N/A | Exists (raw) | Calibrated | **+3-5% ROI** |

Notes:
- L0+L1: no architecture change, just better seeds. Modest improvement.
- L2: possession coupling catches lineup effects. Meaningful improvement.
- L3: CV defender_dist and spacing tighten FG% distributions.
- L4: Simulator outputs as XGBoost features — where the biggest win_prob gain happens.

---

## Implementation Sequence (When Ready to Build)

```
Step 1 (1 day):   Fix 3 bugs (seed, fg3m, game score disconnect)
Step 2 (1 day):   Wire Layer 1 models into current architecture (drop-in replacements)
Step 3 (2 days):  Rebuild as possession-by-possession (Layer 2 architecture)
Step 4 (0.5 day): Add team oreb%, home_away splits, minutes_floor
Step 5 (0.5 day): Write simulator → win_prob features, retrain win_probability.py
Step 6 (1 day):   Write sim_result.over_prob() pipeline into daily_pipeline.py
Step 7 (Phase G): Inject CV features when 20 clean games are ready
Step 8 (1 day):   Retrain XGBoost win_prob with simulator features
```

Total estimate (excluding Phase G): 6–7 days of coding work.

---

## Files to Create/Modify (When Building)

| File | Change |
|---|---|
| `src/simulation/possession_simulator.py` | Full rewrite of `_simulate_player` → `_simulate_game` |
| `src/simulation/game_state.py` | New: shared state object per simulation (score, period, fouls) |
| `src/simulation/lineup_resolver.py` | New: usage normalization + DNP resolution per possession |
| `src/prediction/win_probability.py` | Add sim features to FEATURE_COLS, retrain |
| `src/prediction/player_props.py` | Add sim over_prob as calibration output |
| `scripts/daily_pipeline.py` | Call simulator after props, output distributions |
| `api/predictions_router.py` | Add `/distributions/{player_id}` endpoint |
| `tests/test_possession_simulator.py` | Tests: score consistency, usage sums, DNP propagation |
