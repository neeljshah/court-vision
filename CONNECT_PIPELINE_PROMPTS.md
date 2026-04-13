# Pipeline Connection Prompts — Run in Order

## Prompt 1: Wire micro-models into prop_model_stack.py

```
In src/prediction/prop_model_stack.py, the meta-model uses DNP risk + injury mult + form z-score + motivation flags as meta features. But we have 40+ trained micro-models in data/models/ that are NOT connected:

- contested_rate_model.pkl, foul_trouble.pkl, garbage_time.pkl, minutes_floor.pkl
- rotation_predictor.pkl, usage_rate_model.pkl, rest_day_model.pkl
- home_away_model.pkl, back_to_back_model.pkl, matchup_model (json+meta)
- travel_impact_model.pkl, altitude_model.pkl, referee_model.pkl
- beneficiary_cascade.pkl, shot_type_model.pkl, true_shooting_model.pkl
- plus_minus_predictor.pkl, clutch_lineup_model.pkl, public_fade.pkl
- soft_book_lag.pkl, contested_shot_predictor.pkl

Task: In prop_model_stack.py, add a function `_collect_micro_signals(player_id, game_context)` that loads each micro-model .pkl, calls .predict() with available features from game_context, and returns a dict of signal values. Then add these as additional meta features in the existing `stack_predict()` flow. Only add models whose .pkl exists (skip missing gracefully). Don't change the public API signature. Keep under 300 LOC total for the new code. Read each micro-model's source in src/prediction/ to understand its predict() signature before wiring it.
```

## Prompt 2: Wire micro-models into game_models.py

```
In src/prediction/game_models.py, the 5 game-level models (total, spread, blowout, first_half, pace) use a 30-feature vector from team ratings + rest/travel. Current R2: spread=0.25, total=0.16 — weak.

Add these as additional features to the FEATURE_COLS list and the feature-building function:
1. From win_probability.py: call predict() for both teams, add win_prob_home as feature
2. From matchup_model.py: load matchup_model.json, get matchup score
3. From overtime_probability.pkl: add OT probability
4. From referee_model.pkl: add ref tendency (if ref data available, else 0)
5. From rest_day_model.pkl + back_to_back_model.pkl + travel_impact_model.pkl: add rest/travel signals
6. From public_fade.pkl: add public betting % signal

Read each model's source to understand its API. Add features to the feature vector, retrain by calling train(). Store updated metrics in game_models_metrics.json. Keep changes minimal — just extend the existing feature builder, don't restructure.
```

## Prompt 3: Connect CV features to prop predictions

```
The CV pipeline (unified_pipeline.py -> feature_engineering.py) produces spatial features in data/features.csv: defender_distance, spacing, velocity, paint_pressure, fatigue, off_ball movement. These are per-player-per-frame from broadcast video.

But player_props.py and prop_model_stack.py don't use any CV data — they only use NBA API stats.

Task: Create src/features/cv_feature_bridge.py (new file, <150 LOC) that:
1. Reads data/features.csv (if it exists)
2. Aggregates per-player spatial stats: avg_defender_distance, avg_spacing, avg_velocity, fatigue_score, paint_time_pct, off_ball_distance
3. Exposes `get_cv_features(player_name: str) -> dict` returning these aggregates (or empty dict if no CV data)

Then in player_props.py, import cv_feature_bridge and add CV features to the XGBoost feature vector when available (graceful fallback to 0s when missing). This is the key differentiator — spatial data from video that sportsbooks don't have.
```

## Prompt 4: Build the game prediction orchestrator

```
Create src/prediction/game_orchestrator.py (<200 LOC) that connects everything into one call:

def predict_game(home_team, away_team, season="2025-26", player_ids=None):
    """Full prediction for a single game combining all models."""
    
    result = {}
    
    # 1. Win probability (win_probability.py -> predict)
    # 2. Game models (game_models.py -> predict) — spread, total, blowout, pace, first_half
    # 3. Player props for key players (prop_model_stack.py -> stack_predict)
    #    - If player_ids not given, get starters from nba_api
    # 4. Betting edges (betting_portfolio.py -> kelly_corr for each prop with edge)
    # 5. Return unified dict with all predictions + confidence + edges

Wire the output of each model as input context to downstream models where applicable. Save prediction output to data/predictions/{date}_{home}_{away}.json for tracking.

Also add a CLI: `python -m src.prediction.game_orchestrator --home LAL --away BOS`
```

## Prompt 5: Connect orchestrator to API + add /predictions/game endpoint

```
In api/predictions_router.py, add a new endpoint:

POST /predictions/game
Body: {"home_team": "LAL", "away_team": "BOS", "season": "2025-26"}
Returns: Full game prediction from src/prediction/game_orchestrator.predict_game()

Also update GET /predictions/today to use game_orchestrator instead of calling individual models. Currently /predictions/today and /predictions/props/{player_id} call models independently — they should go through the orchestrator so all signals are connected.

Keep the existing endpoints working. Just rewire their internals to use game_orchestrator.
```

## Prompt 6: Add prediction tracking + accuracy feedback loop

```
Create src/prediction/prediction_tracker.py (<150 LOC):

1. After each prediction is saved to data/predictions/, track it
2. After game completion, score predictions against actual results (from nba_api box scores)
3. Compute: MAE by stat, calibration by confidence bucket, CLV by edge size
4. Save scored results to data/predictions/scored/
5. Expose get_accuracy_report(last_n_days=30) -> dict

Add CLI: `python -m src.prediction.prediction_tracker --score-yesterday`

Then in game_orchestrator.py, after generating predictions, also call prediction_tracker to log them. This closes the feedback loop so you can see which models are actually profitable.
```

## Run Order
1 + 2 + 3 can run in parallel (independent)
4 depends on 1-3
5 depends on 4
6 depends on 4
