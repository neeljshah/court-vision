# Model Registry — 56 Models, What Each Does, Current Performance

*56 models organized by data-requirement tier, with current performance metrics. (No fixed platform-wide model count — see `.planning/CANONICAL_VALUES.md`; this is the tally of models named in this doc's tiers below.)*

---

## Architecture

The 56 models are organized into 6 data-requirement tiers. Tier determines when retrain is warranted, not model importance.

| Tier | Data gate | Count | Algorithm | Production gate |
|------|-----------|-------|-----------|-----------------|
| 1 | NBA API only | 13 | XGBoost + Ridge stacker | Shipped |
| 2 | Shot chart data | 5 | XGBoost | Shipped |
| 2B | Lifecycle + betting signals | 6 | XGBoost / logistic | Shipped |
| 3 | 20+ CV games | 10 | XGBoost | Retrain gate: 80 games |
| 4 | 50+ CV games | 8 | XGBoost | Retrain gate: 80 games |
| 5 | NLP / feedback loop | 7 | XGBoost / logistic | Requires NLP pipeline |
| 6 | 200+ CV games | 7 | LSTM + ensemble | Requires 200+ game corpus |

**Model registry file:** `data/models/model_registry.json`

---

## Tier 1 — NBA API Only (13 models, SHIPPED)

The foundational layer. Trained on 6+ seasons of NBA API data. These are the models that established the baseline before any CV data was available.

| Model | Target | R² | MAE | ECE | Notes |
|-------|--------|-----|-----|-----|-------|
| pts_prop | Points O/U | 0.41 (holdout) | 4.12 | 0.021 | Primary betting model |
| reb_prop | Rebounds O/U | 0.40 | 2.1 | 0.028 | Solid; reb is noisier than pts |
| ast_prop | Assists O/U | 0.46 | 1.7 | 0.024 | Strong signal |
| fg3m_prop | 3PM O/U | 0.28 | 1.0 | 0.035 | 3PM has high variance |
| tov_prop | Turnovers O/U | 0.25 | 1.1 | 0.041 | Moderate signal |
| blk_prop | Blocks O/U | 0.18 | 0.6 | 0.056 | Low R²; rare event |
| stl_prop | Steals O/U | 0.09 | 0.7 | 0.071 | Near-zero signal; Poisson-ish |
| win_prob | Win probability | — | — | — | Calibrated; XGBoost |
| game_total | Game O/U | — | — | — | Pace model |
| spread | Point spread | — | — | — | Game-level |
| lineup_net | Lineup net rating | — | — | — | Feeds lineup weighting |
| blowout_prob | Blowout probability | — | — | — | Garbage time trigger |
| team_pace | Actual team pace | — | — | — | Feeds pts/possession calc |

**Stl note:** R²=0.09 is not a data problem — it's a target-noise problem. Steals are Poisson-distributed with mean < 1 per game. The zero-inflated specification is required, not more data. Model ships because the Monte Carlo needs a distribution, not because it's predictive. Do not bet stl markets until a proper zero-inflated model is validated.

---

## Tier 2 — Shot Chart Data (5 models, SHIPPED)

| Model | Target | Performance | Notes |
|-------|--------|-------------|-------|
| xfg_model | Expected FG% by zone | Brier score 0.226 | Feeds pts model as feature |
| shot_quality_v1 | Shot quality score | — | Spatial shot rating |
| zone_tendency | Player shot zone preference | — | Situational |
| shot_creation | Self-created vs assisted shots | — | Catch-and-shoot probability |
| fta_rate | Free throw attempts per possession | — | Referee interaction model |

---

## Tier 2B — Lifecycle + Betting Signals (6 models, SHIPPED)

Trained but not yet generating standalone betting signal at volume. They filter `bet_selector.py` output rather than producing bets independently.

| Model | Target | Notes |
|-------|--------|-------|
| load_management | Probability of rest decision | Binary classifier |
| injury_return | Expected performance on return from injury | Regression |
| injury_risk | Probability of in-game injury exit | Risk model |
| breakout_predictor | Probability of above-expected game | Positive deviation |
| public_fade | "Fade the public" signal | Market timing |
| soft_book_lag | Books lagging market consensus | Execution timing |

---

## Tier 3 — 20+ CV Games (10 models, RETRAIN AT 80 GAMES)

These models incorporate CV spatial features. Trained on the current CV corpus (7 full-feature / 85 tracked games; `docs/CLAUDE-state.md`); R² values below are on this limited sample. All will be retrained when the 80-CLEAN-game gate completes.

**Target after retrain:** pts R² ≥ 0.55.

| Model | Target | Current R² | Target R² | Key CV features |
|-------|--------|------------|-----------|----------------|
| pts_cv | Points (with spatial) | 0.47* | ≥ 0.55 | defender_distance, spacing_score |
| reb_cv | Rebounds (with spatial) | 0.40* | ≥ 0.48 | paint_density, off-ball movement |
| ast_cv | Assists (with spatial) | 0.46* | ≥ 0.54 | spacing_score, handler_isolation |
| fg3m_cv | 3PM (with spatial) | 0.28* | ≥ 0.36 | spacing_score, closeout_speed |
| contested_shot | Contested FG% | — | — | defender_distance, contest_angle |
| open_shot | Open FG% | — | — | spacing_score |
| transition_pts | Transition vs half-court scoring | — | — | transition_flag |
| paint_scoring | Points in paint | — | — | paint_density |
| catch_shoot_3p | C&S 3P% | — | — | catch_shoot_flag |
| fatigue_decay | Performance vs legs_fatigue | — | — | legs_fatigue |

*Reflects the current CV corpus (7 full-feature / 85 tracked games; `docs/CLAUDE-state.md`); upper bound of current CV contribution.

**No Tier 3–4 model is added to live sizing until a CV A/B test confirms Δ R² ≥ +0.05 on holdout.**

---

## Tier 4 — 50+ CV Games (8 models, RETRAIN AT 80 GAMES)

Trained stubs requiring larger CV sample for meaningful training.

| Model | Target | Status |
|-------|--------|--------|
| scheme_classification | Team offensive scheme per possession | Stub |
| pnr_outcome | PnR ball-handler vs roller outcome | Stub |
| off_ball_quality | Off-ball player contribution | Stub |
| spacing_efficiency | Lineup spacing → 3P opportunity rate | Stub |
| blowout_lineup | Lineup changes in blowout scenarios | Stub |
| intraday_drift | Player performance vs morning-set line | Stub |
| matchup_cv | Per-matchup CV-adjusted performance | Stub |
| shot_trajectory | FG% from trajectory features | Stub |

---

## Tier 5 — NLP / Feedback Loop (7 models, PHASE 9)

| Model | Target | Status |
|-------|--------|--------|
| injury_severity_clf | Injury severity from report text | Partial |
| dnp_probability | P(DNP) from current injury status | Partial |
| lineup_confirmation | P(lineup confirmed at tipoff) | Planned |
| reporter_credibility | Credibility score for injury sources | Partial |
| rest_prediction | P(star player resting today) | Planned |
| sentiment_analysis | Press conference / media tone | Planned |
| edge_decay_classifier | Detecting when a model edge is decaying | Planned |

---

## Tier 6 — 200+ CV Games (7 models, PHASE 33)

| Model | Target | Notes |
|-------|--------|-------|
| live_win_prob_lstm | In-play win probability | LSTM; requires sequential game state |
| prop_pricing_lstm | Full prop distribution from LSTM | Sequential game-state encoding |
| player_impact | True player impact (with/without) | Network model |
| game_script_lstm | Game script prediction | Sequence model |
| lineup_embedding | Deep lineup compatibility | Transformer-based |
| spatial_sequence | Spatial-temporal possession sequence | STGNN |
| fatigue_sequence | Player fatigue trajectory | LSTM on running distance |

These require 200+ CV games for meaningful LSTM sequence training. Code is scaffolded (`data/models/live_win_prob_lstm.pt` is a placeholder). Training begins after the 80-game run completes and Tier 3–4 models are validated.

---

## Artifact Inventory - files on disk, by role

The central manifest is `data/models/model_registry.json` (lineage, data windows,
metrics). The load-bearing artifacts the serving graph actually reads:

| Role | Artifact path(s) | Produced by | Read by |
|------|------------------|-------------|---------|
| Win-prob 5-way stack | `data/models/win_probability.pkl` (XGB raw bytes + LGB/LR/MLP-list/NB + NNLS weights + isotonic calibrator) | `win_probability.train()` | `win_probability.load()` / `predict()` |
| Win-prob metrics | `data/models/win_prob_metrics.json` (acc, Brier, per-base Brier, `w_xgb..w_nb`, `meta_fit_source`, seasons) | `_save_metrics()` | dashboards / docs |
| Prop root models | `data/models/props_{stat}.json` (XGB), `props_lgb_{stat}.pkl`, `props_cb_{stat}.cbm` | `prop_pergame` trainers | `prop_model_stack.predict_base_learner()` |
| Prop q50 backends | `quantile_pergame_{stat}_q50.json` (XGB), `quantile_pergame_lgb_{stat}_q50.pkl` (LGB) | `prop_quantiles` | `prop_pergame._load_q50_model()` |
| Prop WF metrics | `quantile_pergame_metrics.json` (MAE + coverage_80 per stat) | walk-forward eval | docs / monitoring |
| Interval calibration | `quantile_calibration.json` (per-stat q10/q90 scale `s`) | `quantile_calibration` grid search | `quantile_calibration.apply()` |
| Ridge meta-correction | `prop_stack_meta.json` (`coef`, `intercept` per stat) | `prop_model_stack.train_meta()` | `stack_predict()` |
| Over/under win-prob calib | `calibration_win_{stat}.joblib` | `CalibrationLayer.train_win_prob()` | `CalibrationLayer.win_prob()` |
| Cohort calibrator | `cohort_calibrator.pkl` | `train_cohort_calibration()` | `_get_cohort_calibrator()` |
| Segment Platt | `segment_calibrator.pkl` | `SegmentCalibrator.save()` | `SegmentCalibrator.calibrate()` |
| Edge isotonic | `edge_isotonic_*.joblib` (per-stat, iter-34) | edge calibration | `betting_edge` |
| Quarantine state | `quarantine_state.json` | monitoring loop | `stack_predict()` |
| xFG | `xfg_v1.pkl`, `xfg_cv_stack.pkl` (CV-gated) | xFG trainer | shot-prob endpoint |
| OOF predictions | `data/cache/pregame_oof.parquet` (byte-identical to calibration frame) | walk-forward | MAE verification |

**Honest artifact caveats (do not gloss over):**

- `prop_residuals.json` is the missing keystone. The Ridge meta, the isotonic
  over/under calibrators, and the Kelly correlation matrix all train from it, and
  it must be regenerated from the held-out tracking corpus before those layers are
  fully populated. Until then, calibration runs largely as identity passthrough
  and Kelly assumes a diagonal (independent-bet) covariance.
- The `live_win_prob_lstm.pt` (Tier 6) is a **placeholder**, not a trained model.
- Tier 3-5 R^2 values are on the current CV corpus (7 full-feature / 85 tracked
  games; `docs/CLAUDE-state.md`) and CV features carry **SHAP ~= 0** in
  production. They retrain at the 80-CLEAN gate;
  none enters live sizing until a CV A/B confirms delta R^2 >= +0.05 on holdout.

> **Honesty rail.** Registry counts and R^2 values are model-quality / calibration
> metrics. They are not edge or ROI claims, and several headline figures (the
> retracted +18.38% ROI, endQ3 Brier 0.119, +54% in-play) are documented
> measurement artifacts - see [`../ML_MODELS.md`](../ML_MODELS.md) "Self-Caught
> Leaks" and [`../JOB_EVIDENCE_PACKET.md`](../JOB_EVIDENCE_PACKET.md).

---

## Model Serving

All Tier 1–2B models are registered in `data/models/model_registry.json` and served via [`api/main.py`](../../api/main.py).

**API endpoints:**
- `POST /predict/player-props` — batch prediction for a slate
- `GET /predict/win-probability` — game win probability
- `GET /predict/game-total` — over/under for game
- `POST /portfolio/kelly-size` — Kelly-fractional bet sizing
- `GET /portfolio/positions` — current active positions
- `GET /lines/current` — live lines from Odds API
- `GET /health` — system health
- `GET /models/registry` — list all registered models
- `GET /calibration/metrics` — current ECE and calibration stats

---

*See [feature-inventory.md](feature-inventory.md) for what goes into each model. See [calibration.md](calibration.md) for how model outputs are calibrated. See [cv-pipeline.md](../architecture/cv-pipeline.md) for how CV features are generated.*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
