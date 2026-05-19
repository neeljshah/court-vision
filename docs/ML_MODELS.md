# ML Models — CourtVision

75 trained model artifacts in `data/models/`. Models built in tier order — each tier requires more CV game data.

---

## TRAINED (75 artifacts, Phases 1–13.5)

### Win Probability

| | |
|---|---|
| **File** | `data/models/win_probability.pkl` |
| **Algorithm** | XGBoost classifier |
| **Accuracy** | 69.1% (walk-forward backtest, 3 seasons) |
| **Brier Score** | 0.203 |

### Game-Level Models

| Model | File | Notes |
|---|---|---|
| Total | `data/models/game_game_total.json` | Points over/under |
| Spread | `data/models/game_spread.json` | Point differential |
| Blowout | `data/models/game_blowout.json` | P(margin > 20) |
| First Half | `data/models/game_first_half.json` | First-half total |
| Pace | `data/models/game_pace.json` | Possessions per 48 |

### Player Prop Models — Actual R² (walk-forward validation)

| Stat | R² | File (v2 active) |
|------|-----|---|
| pts | **0.47** | `data/models/props_pts_v2.json` |
| reb | **0.40** | `data/models/props_reb_v2.json` |
| ast | **0.46** | `data/models/props_ast_v2.json` |
| fg3m | **0.28** | `data/models/props_fg3m_v2.json` |
| blk | **0.18** | `data/models/props_blk_v2.json` |
| tov | **0.25** | `data/models/props_tov_v2.json` |
| stl | **0.18** | `data/models/props_stl_v2.json` |

**Note:** R² values reflect actual walk-forward validation. STL R²=0.18 is weak — do not size aggressively. `opp_to_rate` + `opp_pace` features are planned to improve it. v1 files (`props_pts.json`, etc.) are retained as fallback.

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

## 7-Model Possession Chain (Simulator Core)

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
