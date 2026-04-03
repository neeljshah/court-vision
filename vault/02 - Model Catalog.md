# Model Catalog
*Last updated: 2026-03-25*

← [[01 - System Architecture]] | → [[03 - Data Sources]]

---

## Summary

90 models total across 6 tiers. **46 trained and validated.** Remaining tiers unlock as full-game CV data accumulates.

| Tier | Target | Trained | Status | Unlock |
|------|--------|---------|--------|--------|
| Tier 1 — NBA API Core | 13 | 13 | ✅ Done | Now |
| Tier 1B — Betting + Lifecycle (Phase 4.5) | 6 | 6 | ✅ Done | Now |
| Tier 1C — Specialist models (Phase 4.6–4.9) | 27 | 27 | ✅ Done | Now |
| Tier 2 — Shot Charts + xFG | 5 | 2 | 🟡 Partial | Now (xFG v1 done; v2 needs CV data) |
| Tier 3 — 20 CV Games | 10 | 0 | 🔲 Phase 7 | 20 games |
| Tier 4 — 50 Games | 8 | 0 | 🔲 Phase 10 | 50 games |
| Tier 5 — 100 Games | 7 | 0 | 🔲 Phase 10 | 100 games |
| Tier 6 — 200 Games + LSTM | 7 | 0 | 🔲 Phase 16 | 200 games |
| **Total** | **90** | **46** | | |

---

## Trained Models (✅ 46)

### Win Probability

| File | Algorithm | Features | Performance |
|------|-----------|----------|-------------|
| `win_probability.py` | XGBoost | 27 (team ratings, pace, rest, travel, form) | 69.1% acc, Brier 0.203 |

- Class: `WinProbModel` (alias: `WinProbabilityModel`)
- Train: `python src/prediction/win_probability.py --train`
- Artifact: `data/models/win_probability.pkl`
- Walk-forward backtest: 70.7% correct winner, MAE 10.2 pts (3,685 games)

### Player Props (7 models)

| Stat | Algorithm | MAE | R² |
|------|-----------|-----|----|
| pts | XGBoost | 0.308 | >0.93 |
| reb | XGBoost | 0.113 | >0.93 |
| ast | XGBoost | 0.093 | >0.93 |
| fg3m | XGBoost | 0.083 | >0.93 |
| stl | XGBoost | 0.066 | >0.93 |
| blk | XGBoost | 0.044 | >0.93 |
| tov | XGBoost | 0.078 | >0.93 |

- 52 features: base stats + advanced + shot_dashboard (contested%, pull-up%, catch-shoot%, defender dist)
- 559/569 players have real shot dashboard data (rest: league-average fallback)
- Artifacts: `data/models/props_{stat}.json`
- Train: `python src/prediction/player_props.py --train`

### Prop Model Stack

- **File:** `src/prediction/prop_model_stack.py`
- **Algorithm:** Ridge meta-model over all 7 XGBoost prop models
- **Gating:** Confidence-gated — only uses stack when base model confidence is high
- Phase 4.7 addition (2026-03-20)

### Game Models (5 models)

| Model | Target | File |
|-------|--------|------|
| Game total | Total points | `game_models.py` |
| Spread | Point margin | `game_models.py` |
| Blowout | Win >15 pts | `game_models.py` |
| First half | 1H total | `game_models.py` |
| Pace | Possessions | `game_models.py` |

### DNP Predictor

- **File:** `src/prediction/dnp_predictor.py`
- **Algorithm:** LogisticRegression
- **AUC:** 0.979
- **Integration:** Wired into `predict_props()` — if P(DNP) ≥ 0.4, props zeroed
- **Artifact:** `data/models/dnp_model.pkl`

### xFG v1

- **File:** `src/prediction/xfg_model.py`
- **Algorithm:** XGBoost (shot location + game context)
- **Brier:** 0.226 (221K shots)
- **Artifact:** `data/models/xfg_v1.pkl`
- League-avg baseline Brier ~0.25

### Matchup Model (M22)

- **File:** `src/prediction/matchup_model.py`
- **Algorithm:** XGBoost with hustle + on/off features
- **R²:** 0.796, **MAE:** 4.55
- **Artifact:** `data/models/matchup_model.json`

### Phase 4.5 — Betting + Lifecycle Models (✅ 6)

| Model | Artifact | Notes |
|-------|---------|-------|
| Load management | `load_management.pkl` | Rest-based DNP/minutes cap predictor |
| Injury return curve | `injury_return.pkl` | Efficiency ramp on return from injury |
| Injury risk | `injury_risk.pkl` | In-game injury probability |
| Breakout predictor | `breakout_predictor.pkl` | Usage spike + opportunity flags |
| Public fade | `public_fade.pkl` | Fade signal when public% > 75% |
| Soft book lag | `soft_book_lag.pkl` | Line lag detector vs sharp books |

### Phase 4.6–4.9 — Specialist Models (✅ 23)

| Model | Artifact |
|-------|---------|
| Age curve | `age_curve_model.pkl` |
| Altitude impact | `altitude_model.pkl` |
| Back-to-back fatigue | `back_to_back_model.pkl` |
| Beneficiary cascade (injury) | `beneficiary_cascade.pkl` |
| Clutch lineup | `clutch_lineup_model.pkl` |
| Contested rate | `contested_rate_model.pkl` |
| Contested shot predictor | `contested_shot_predictor.pkl` |
| Foul trouble | `foul_trouble.pkl` |
| Garbage time detector | `garbage_time.pkl` |
| Home/away split | `home_away_model.pkl` |
| Line movement predictor | `line_movement_predictor.pkl` |
| Minutes floor | `minutes_floor.pkl` |
| Overtime probability | `overtime_probability.pkl` |
| Plus/minus predictor | `plus_minus_predictor.pkl` |
| Referee tendencies | `referee_model.pkl` |
| Rest day impact | `rest_day_model.pkl` |
| Rotation predictor | `rotation_predictor.pkl` |
| Shot clock pressure | `shot_clock_pressure_model.pkl` |
| Shot type classifier | `shot_type_model.pkl` |
| Substitution timing | `substitution_timing_model.pkl` |
| Travel impact | `travel_impact_model.pkl` |
| True shooting estimator | `true_shooting_model.pkl` |
| Usage rate predictor | `usage_rate_model.pkl` |

### Infrastructure Models

- `CLV predictor` — `clv_tracker.py` — opening vs closing line tracking
- `Prop correlation matrix` — 508 player correlations, 3,447 lineup pairs (`prop_correlations.json`)
- `xFG CV stack` — `xfg_cv_stack.pkl` — CV-enriched shot quality (needs more game data)
- `Betting portfolio` — Kelly + correlation sizing + cross-book arb detection (`betting_portfolio.py`)
- `Prop backtester` — historical backtest + paper trading + validation gate (`prop_backtester.py`)

---

## What's Still Needed (Phase 3.5 — data gaps)

| Model | Blocker |
|-------|---------|
| Defensive effort | hustle data fetched, model not trained |
| Ball movement quality | BoxScorePlayerTrackV2 fetched, model not trained |
| Screen ROI | Synergy data fetched, model not trained |
| Touch dependency | fetched, not trained |
| Play type efficiency | fetched, not trained |
| Defender zone xFG | fetched, not trained |
| Injury recurrence | ProSportsTransactions not fetched yet |
| Coaching adjustment | PBP data available, model not coded |
| Ref tendency extended | partial — ref_tracker.py built, extended features pending |

---

## Phase 7 Models (🔲 — needs 20 CV games)

| ID | Model | Description |
|----|-------|-------------|
| M41 | xFG v2 | xFG with actual defender distance + spacing from CV |
| M42 | Shot selection quality | CV-rated shot quality vs optimal |
| M43 | Play type classifier | Improved with CV spatial features |
| M44 | Defensive pressure | Live pressure score per possession |
| M45 | Spacing rating | Team spacing index per lineup |
| M46 | Drive frequency | Drives per possession by player |
| M47 | Open shot rate | % of FGA with defender >4 ft |
| M48 | Transition frequency | Fast break % from CV |
| M49 | Off-ball movement | Cut frequency + spacing shifts |
| M50 | Possession value | CV-derived EPV estimate |

---

## Phase 9 NLP Models (🔲)

| ID | Model | Description |
|----|-------|-------------|
| M66 | Injury report severity | NLP on NBA injury report text |
| M67 | Injury news lag | Beat reporter → official report delay |
| M68 | Team chemistry sentiment | Reddit/Twitter sentiment |
| M69 | Beat reporter credibility | Source credibility weights |

---

## Phase 10–16 Models (🔲)

50–100 games: M51–M65 (fatigue curve, rebound positioning, lineup chemistry, momentum, etc.)
200+ games: M76–M82 (full possession simulator, live win prob LSTM, true player impact)

---

## The 7-Model Possession Simulator Chain

```
Input: game state (score, quarter, time, lineup, fatigue)

[1] PlayTypeClassifier → what type of possession?
[2] ShotSelectorModel → who shoots, from where?
[3] xFGv2Model → what's the make probability?
[4] TOFoulModel → does possession end early?
[5] ReboundModel → who gets the board?
[6] FatigueModel → update player fatigue states
[7] SubstitutionModel → lineup change?

× 10,000 simulations → stat distributions → compare vs book lines
```

---

## Model Versioning

`src/pipeline/model_version_manager.py` — tracks version, train date, accuracy, feature hash. Auto-retrain triggered when:
- New games processed (outcome_recorder → auto_retrain)
- Feature drift detected (feature_drift_detector)
- Model accuracy drops below threshold

---

## Related Notes

- [[01 - System Architecture]] — how models plug into the pipeline
- [[03 - Data Sources]] — where training data comes from
- [[04 - Pipeline Flow]] — how to run training
