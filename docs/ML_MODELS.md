# ML Models — CourtVision

85+ trained ML artifacts in `data/models/` (119 `.pkl` files including residual heads, period-specific projection heads, calibration layers, and metric JSONs). Models built in tier order — each tier requires more CV game data.

> **Two prediction surfaces:**
> 1. **Pregame** — the 7 prop models + WinProb + game-level models documented below. Trained on box-score + context features, locked at architecture/feature ceiling (cycle 96e+).
> 2. **In-play** — additive residual layers on top of pregame base, period-specific projection heads (endQ1/endQ2), learned Q4 minutes trajectory, and calibrated live quantile bands. Shipped through improve_loop R3-R7 + cycles 103-110. **endQ3 in-play beats pregame by -43% to -55% MAE across 7/7 stats** on a 550-game retro.

---

## TRAINED — Pregame (85+ artifacts, Phases 1–13.5)

### Win Probability

| | |
|---|---|
| **File** | `data/models/win_probability.pkl` |
| **Algorithm** | XGBoost classifier |
| **Accuracy** | 0.7094 (3-fold walk-forward) / 0.717 (single-split) |
| **Brier Score** | 0.193 (WF) / 0.188 (single-split) |

### Game-Level Models

| Model | File | Notes |
|---|---|---|
| Total | `data/models/game_game_total.json` | Points over/under |
| Spread | `data/models/game_spread.json` | Point differential |
| Blowout | `data/models/game_blowout.json` | P(margin > 20) |
| First Half | `data/models/game_first_half.json` | First-half total |
| Pace | `data/models/game_pace.json` | Possessions per 48 |

### Player Prop Models — Pregame MAE (walk-forward, N=99,818)

| Stat | MAE | R² | Model | File (v2 active) |
|------|-----|----|----|---|
| pts | **4.6210** | 0.5105 | sqrt+Huber XGB/LGB blend + 5-seed MLP, NNLS-stacked | `data/models/props_pts_v2.json` |
| reb | **1.9023** | 0.38 | LGB-q50 (log1p) | `data/models/props_reb_v2.json` |
| ast | **1.3559** | 0.4988 | log1p XGB+LGB + multitask MLP, NNLS-stacked | `data/models/props_ast_v2.json` |
| fg3m | **0.8943** | 0.29 | XGB-q50 (log1p) | `data/models/props_fg3m_v2.json` |
| blk | **0.4398** | 0.16 | XGB-q50 (-16% session win, biggest single-stat win of loop) | `data/models/props_blk_v2.json` |
| tov | **0.8932** | 0.22 | XGB-q50 (log1p) | `data/models/props_tov_v2.json` |
| stl | **0.7153** | 0.18 | XGB-q50 (log1p) | `data/models/props_stl_v2.json` |

**Quantile architecture (cycle 26-27, 96e):** q50 (median) is the **PRIMARY predictor for 5 of 7 stats** — REB / FG3M / STL / BLK / TOV. AST + STL use the cycle-23 **multitask MLP** (7-output MLPRegressor on shared representation). q50 quantile heads dominate squared-error/Huber blends because sportsbook prop O/U lines score against the median, not the mean. R² gets *worse* on q50 stats (median is less correlated with high-variance outcomes) but MAE wins decisively — and MAE is what matters for betting. v1 files (`props_pts.json`, etc.) are retained as fallback.

Sources: pregame MAE from `data/models/quantile_pergame_metrics.json` (verified via `scripts/verify_production_mae.py`); R² from `data/models/model_registry.json`. Dispatch lives in `src/prediction/prop_pergame.py::_USE_Q50_STATS`. q10/q90 intervals calibrated to 80% empirical coverage in `data/models/quantile_calibration.json`.

### xFG (Expected Field Goal)

| | |
|---|---|
| **File** | `data/models/xfg_v1.pkl` |
| **Brier Score** | 0.226 |
| **Training data** | 221,866 shots (3 seasons) |
| **Stack** | `data/models/xfg_cv_stack.pkl` (CV-augmented) |

### Supporting Models

| Model | File | Type | Notes |
|---|---|---|---|
| DNP predictor | `data/models/dnp_model.pkl` | LogisticRegression | AUC 0.979 |
| Matchup model | `data/models/matchup_model.json` | XGBoost | R²=0.796 |
| Breakout predictor | `data/models/breakout_predictor.pkl` | XGBoost | |
| Load management | `data/models/load_management.pkl` + `.json` | Logistic | |
| Injury risk | `data/models/injury_risk.pkl` | XGBoost | |
| Injury return | `data/models/injury_return.pkl` | XGBoost | |
| Injury severity | `data/models/injury_severity_clf.pkl` | Classifier | |
| Age curve | `data/models/age_curve_model.pkl` | Regression | |
| Altitude impact | `data/models/altitude_model.pkl` | Regression | |
| Back-to-back | `data/models/back_to_back_model.pkl` | XGBoost | |
| Beneficiary cascade | `data/models/beneficiary_cascade.pkl` | | Star-out usage |
| Clutch lineup | `data/models/clutch_lineup_model.pkl` | | |
| Contested rate | `data/models/contested_rate_model.pkl` | | |
| Contested shot | `data/models/contested_shot_predictor.pkl` | | |
| Foul trouble | `data/models/foul_trouble.pkl` | | |
| Garbage time | `data/models/garbage_time.pkl` | | |
| Home/away | `data/models/home_away_model.pkl` | | |
| Line movement | `data/models/line_movement_predictor.pkl` | | Sharp detector |
| Minutes floor | `data/models/minutes_floor.pkl` | | |
| Overtime prob | `data/models/overtime_probability.pkl` | | |
| Play type selector | `data/models/play_type_selector.joblib` | | Possession simulator |
| Plus/minus | `data/models/plus_minus_predictor.pkl` | | |
| Possession outcome | `data/models/possession_outcome.pkl` | | |
| Public fade | `data/models/public_fade.pkl` | | |
| Referee model | `data/models/referee_model.pkl` | | Pace/FTA tendencies |
| Rest day | `data/models/rest_day_model.pkl` | | |
| Rotation predictor | `data/models/rotation_predictor.pkl` | | |
| Shot clock pressure | `data/models/shot_clock_pressure_model.pkl` | | |
| Shot quality | `data/models/shot_quality.pkl` | | |
| Shot type | `data/models/shot_type_model.pkl` | | |
| Soft book lag | `data/models/soft_book_lag.pkl` | | Sharp window timing |
| Substitution timing | `data/models/substitution_timing_model.pkl` | | |
| Tier 4: closeout | `data/models/tier4_closeout.pkl` | | CV-derived |
| Tier 4: help def | `data/models/tier4_help_def.pkl` | | CV-derived |
| Tier 4: late game | `data/models/tier4_late_game.pkl` | | |
| Tier 4: rebound | `data/models/tier4_rebound.pkl` | | |
| Tier 4: screen | `data/models/tier4_screen.pkl` | | |
| Tier 4: stagnation | `data/models/tier4_stagnation.pkl` | | Ball stagnation risk |
| Tier 4: turnover | `data/models/tier4_tov.pkl` | | |
| Tier 5: foul drawing | `data/models/tier5_foul_drawing.pkl` | | |
| Tier 5: momentum | `data/models/tier5_momentum.pkl` | | |
| Tier 5: second chance | `data/models/tier5_second_chance.pkl` | | |
| Tier 5: sub timing | `data/models/tier5_sub_timing.pkl` | | |
| Travel impact | `data/models/travel_impact_model.pkl` | | |
| True shooting | `data/models/true_shooting_model.pkl` | | |
| Usage rate | `data/models/usage_rate_model.pkl` | | |
| OSNet re-ID | `data/models/osnet_x0_25_imagenet.pth` | PyTorch | 512-dim embeddings |

### Model Registry Files

| File | Purpose |
|---|---|
| `data/models/model_registry.json` | Central manifest — model lineage, data windows, metrics |
| `data/models/dnp_model_meta.json` | DNP model metadata |
| `data/models/matchup_model_meta.json` | Matchup model metadata |
| `data/models/game_models_metrics.json` | Game-level model evaluation metrics |
| `data/models/win_prob_metrics.json` | Win prob evaluation metrics |
| `data/models/quantile_pergame_metrics.json` | Pregame q10/q50/q90 MAE + coverage_80 per stat |
| `data/models/quantile_calibration.json` | Per-stat q10/q90 scale factors for 80% empirical coverage |

---

## TRAINED — In-Play Prediction System (cycles 103–110, improve_loop R3–R7)

The in-play architecture is a **layered residual stack on top of the pregame base model**. Each layer adds information about how the game is actually unfolding and shrinks toward the truth as more of the game is observed.

### Architecture

```
pregame base prediction
  + (period-specific projection — endQ1 / endQ2 heads)
  + (residual head — pregame stratum, foul_change, blowout flip, heat_check shrinkage)
  + (learned Q4 minutes trajectory — minute_trajectory.py)
  = live projection  (with calibrated q10/q90 bands)
```

### Components

| Component | File | Status | Measured impact |
|---|---|---|---|
| Pregame residual heads | `src/prediction/residual_heads.py` | **6/7 stats SHIP** (improve_loop R7, commit `61c454eb`) | Additive learners on top of base pregame |
| endQ1 + endQ2 period heads | `src/prediction/live_engine.py::project_from_snapshot` + endQ1/endQ2 residual layers (cycle 106a `6178d8e3`, R3+R4 `476d02a7`) | **SHIPPED** | Pregame enrichment lift validated cycle 108a |
| endQ3 residual head | `live_engine` (cycle 109) | **REJECTED** (2/7 stats) | Period heads default off after endQ3 reject |
| Learned Q4 minutes trajectory | `src/prediction/minute_trajectory.py` | **SHIPPED** (cycle 110 `fe27de4a`) | **PTS -0.2312 MAE, 7/7 stats positive** |
| Live quantile bands (q10/q90) | `src/prediction/live_quantile_bands.py` | **SHIPPED** (cycle 105c `cd3e4fda`; recalibrated cycle 109) | 80% empirical coverage on in-play projections |
| In-play foul_change residual | `live_engine` (`cb39cbd6`) | **SHIPPED** | PTS -0.24 on foul stratum, 0.00 non-foul, WF 4/4 |
| Blowout flip residual | `blowout_residual.lgb` (`dfd4ce0b`) | **SHIPPED** | Stratified dispatch |
| Heat_check shrinkage | (`f1ae0919`) | **SHIPPED** | Stratified dispatch |
| Multitask MLP with live head | (cycle 103c `b15d5ac1`) | **SHIPPED** (back-compat opt-in) | |
| Live engine consolidated API | `src/prediction/live_engine.py` | active | `project_from_snapshot()` is the single entry |
| In-play daemon | `scripts/live_inplay_daemon.py` | active | Streams snapshot → projection |
| EndQ2 bet recommender | `scripts/recommend_endQ2_bets.py` | active | Generates in-game ladders |

### Measured (550-game retro, RunPod RERUN confirmed 2026-05-25 `2bad1fca`)

**endQ3 in-play MAE vs pregame — 7/7 stats win:**

| Stat | endQ3 MAE | Δ vs pregame |
|------|----------|--------------|
| PTS  | 2.46 | **-47%** |
| REB  | 1.00 | **-47%** |
| AST  | 0.68 | **-50%** |
| FG3M | 0.42 | **-53%** |
| STL  | 0.32 | **-55%** |
| BLK  | 0.20 | **-55%** |
| TOV  | 0.45 | **-50%** |

**In-play betting ROI vs L5 proxy:** 7/7 stats win at threshold 1.0, ROI 0.70–0.89.

### Key design lessons captured (`vault/Improvements/`)

- At architecture/feature ceiling for pre-game. Remaining gains are DATA: live injury feeds, real sportsbook lines, CV defender_distance at scale, lineup projection.
- Residual heads + period-specific heads are the right architecture for in-play (additive layers on top of base pregame model, not a separate model).
- WF gate now requires **4/4 folds positive AND production single-split positive AND ≥4/7 stats wins**. Cycle 105a (play_probability) failed the ≥4 ship gate despite WF 4/4 on 2/7 stats — correctly rejected.

---

## Prediction Flow

```python
from src.prediction.prop_model_stack import stack_predict

result = stack_predict("Jayson Tatum", game_context={"away_team": "MIL", "season": "2025-26"})
# result.predictions → {"pts": 27.4, "reb": 8.1, "ast": 4.8, ...}
# result.confidence → 0.82
# result.suppressed → False (True if DNP risk > 0.40)
```

---

## 7-Model Possession Chain (Simulator Core) (planned — vision target)

Current status: foundation components exist (possession events, shot quality, transition detection); end-to-end 10K-sim integration is roadmap'd, not shipped.

```
[1] PlayTypeSelector     → What kind of possession is this?
[2] ShotSelector         → Who shoots? From where?
[3] xFG                  → P(make) given shooter + zone + spatial context
[4] Possession Outcome   → Turnover or foul instead?
[5] Tier 4 Rebound       → Who gets the board if missed?
[6] Tier 5 Momentum      → How does fatigue affect this possession?
[7] SubstitutionTiming   → Does the coach sub?

× 10,000 simulations → full box score probability distribution per player
```

---

## PLANNED (Post-100-game RunPod run)

These models require more CV game data and are not yet trained. They exist as stubs or are blocked on Phase G completion.

### CV Behavioral (Phase 7 — requires 20 A/B-grade games)

- **xFG v2 (Full Spatial):** closeout speed, shot clock at release, fatigue penalty → target Brier 0.200
- **Play Type Classifier:** ISO / P&R / Spot-up / Cut / Transition from CV event sequence (target 85%+)
- **Defensive Pressure → Outcome:** pressure_score + spacing + shot_clock → P(score/TO/foul)
- **Spacing Rating:** convex hull area → scoring efficiency
- **Drive → FTA Model:** drive speed + paint penetration → P(foul drawn)
- **Box-Out Rebound Model:** crash angle + speed → P(rebound captured)

### Prop Retrain with CV Features (Phase 7)

All 7 prop models will retrain with CV behavioral features:
- `drives_per_36`, `box_out_rate`, `off_ball_distance_per_36`, `closeout_speed_allowed`
- Expected pts MAE improvement: 0.22 → ~0.18

### Volume Models (Phase 10 — requires 50–100 games)

- Fatigue Curve, Rebound Positioning, Lineup Chemistry, Matchup Matrix (500+ pairs)
- Late-Game Efficiency, Closeout Quality, Help Defense Frequency, Ball Stagnation Risk

### Live Models (Phase 11 — requires live feed)

- Live Prop Updater, Comeback Probability, Garbage Time Predictor, Foul Trouble Model
- Q4 Star Usage Model, Momentum Run Model

### Full Stack (Phase 12/16 — requires 200+ games)

- Live Win Probability LSTM (hidden dim 256, 3 layers), True Player Impact (causal)
- Lineup Optimizer (DFS + SGP), Prop Pricing Engine, Regression Detector, Injury Impact Model

---

*Last verified: 2026-05-25*
