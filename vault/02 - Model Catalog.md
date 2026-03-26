# Model Catalog
*Last updated: 2026-03-24*

← [[01 - System Architecture]] | → [[03 - Data Sources]]

---

## Summary

90 models total across 6 tiers. 18 trained and validated. Remaining tiers unlock as full-game CV data accumulates.

| Tier | Models | Status | Unlock |
|------|--------|--------|--------|
| Tier 1 — NBA API | 18 | ✅ Trained | Now |
| Tier 2 — Shot Charts | 5 | ✅ Trained | Now |
| Tier 3 — 20 CV Games | 10 | 🔲 Phase 7 | 20 games |
| Tier 4 — 50 Games | 8 | 🔲 Phase 10 | 50 games |
| Tier 5 — 100 Games | 7 | 🔲 Phase 10 | 100 games |
| Tier 6 — 200 Games | 7 | 🔲 Phase 16 | 200 games |

---

## Trained Models (✅ 18)

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

### Phase 4.5 Models (all production-ready)

| Model | File | Artifact |
|-------|------|---------|
| Load management | `load_management.py` | `load_management.pkl` |
| Injury return curve | `injury_return.py` | `injury_return.pkl` |
| Injury risk | `injury_risk.py` | `injury_risk.pkl` |
| Breakout predictor | `breakout_predictor.py` | `breakout_predictor.pkl` |
| Public fade | `public_fade.py` | `public_fade.pkl` |
| Soft book lag | `soft_book_lag.py` | `soft_book_lag.pkl` |

### Additional Built Models

- `CLV predictor` — `clv_tracker.py` — opening vs closing line tracking
- `Prop correlation matrix` — 508 player correlations, 3,447 lineup pairs (`prop_correlations.json`)
- `Betting portfolio` — Kelly + correlation sizing + cross-book arb detection (`betting_portfolio.py`)
- `Prop backtester` — historical backtest + paper trading + validation gate (`prop_backtester.py`)
- `CLV backtest baseline` — 70.7% correct winner, MAE=10.2pts (3,685 games)

---

## Untrained / Phase 3.5 Models (🔲 10)

Waiting on data: hustle, synergy, matchup, BBRef, on/off all fetched — these models just need to be coded + trained.

| Model | Target | Data Source |
|-------|--------|------------|
| Defensive effort | Hustle stats | `hustle_stats_*.json` |
| Ball movement | Passing + touches | `BoxScorePlayerTrackV2` |
| Screen ROI | Synergy screen PPP | `synergy_*.json` |
| Touch dependency | Touch% by player | `BoxScorePlayerTrackV2` |
| Play type efficiency | Synergy PPP | `synergy_*.json` |
| Defender zone xFG | Allowed FG% by zone | `defender_zone_*.json` |
| Age curve | BBRef aging data | `bbref_advanced_*.json` |
| Injury recurrence | BBRef injury history | Pending fetch |
| Coaching adjustment | Half-time adj | PBP + lineup data |
| Ref tendency extended | Foul rate + pace | `ref_tracker.py` |

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
