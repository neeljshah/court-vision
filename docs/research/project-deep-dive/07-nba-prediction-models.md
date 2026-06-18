# 07 - NBA Prediction Models (props, win-prob, the ~190-feature stack)

Scope: the pregame player-prop models, the meta-stack, the quantile/conformal/MC
variants, win probability, and the feature surface that feeds them. In-game/live
prediction is its own area; this doc touches it only where pregame hands off.

Honesty rails (binding): markets are efficient. The defensible win here is
CALIBRATION (leak-free OOS RMSE/Brier that matches or trails the devigged close),
NOT a dollar edge. AST pregame is the one documented near-durable model signal and
even that is fragile. No profit edge is claimed. Paper-only.

---

## 1. INVENTORY (exists AND used)

Core pregame prop pipeline (production, wired into API + loop):

- `src/prediction/prop_pergame.py` (5,403 LOC) -- THE real per-game prop pipeline.
  Each row is one game; every feature is computed strictly from the player's PRIOR
  games (leak-free). Per-stat XGBoost + LightGBM + seed-ensemble MLP base learners,
  NNLS-blended, isotonic-calibrated, with q50 quantile dispatch for 5 of 7 stats.
  7 stats: pts/reb/ast/fg3m/stl/blk/tov. This is the model that matters.
- `src/prediction/player_props.py` (3,296 LOC) -- legacy season-average prop path +
  the big `_build_player_features` (line 1034) feature assembler + `predict_props`
  (line 2235). Its season-average training reports R^2~0.99 = near-identity artifact
  (honest holdout ~0.45); kept for fallback + feature plumbing, NOT the honest model.
- `src/prediction/prop_model_stack.py` (921 LOC) -- Ridge meta-model over the 7 base
  XGBoost stats + confidence gate. `stack_predict()` (the entry the API calls),
  `BASE_LEARNERS` registry {xgboost,lightgbm,catboost}. Artifact:
  `data/models/prop_stack_meta.json` (exists).
- `src/prediction/prop_stacker.py` (441 LOC) -- linear base-learner combiner;
  artifact `prop_stacker_metrics.json` (exists).
- `src/prediction/win_probability.py` (2,238 LOC) -- pregame win-prob `WinProbModel`
  (XGBoost primary + optional LGB/LR/MLP-ensemble/NB base learners, NNLS-blended
  `_blend_prob` line 487, optional isotonic calibrator). Served by `api/models_router.py`.
- `src/features/feature_engineering.py` (1,693 LOC) -- CV-tracking feature builder
  (rolling/event/momentum from tracking_data.csv) + `advanced_features.py` A-1..A-14.
  NOTE: this is the broadcast-CV feature surface, largely SEPARATE from the prop
  feature columns (which live inside `prop_pergame.feature_columns`).

Uncertainty / distribution variants:

- `src/prediction/quantile_props.py` (162 LOC) -- `QuantilePropsModel`, 5-level
  GradientBoosting quantile regression, `predict_proba_over(X, line)` by interpolation
  (no Gaussian assumption). Used to TRAIN the q50 heads consumed by prop_pergame.
- `src/prediction/prop_quantiles.py` -- q50 LGB+XGB heads (the shipped quantile path
  for reb/blk/stl/tov/fg3m; see `_USE_Q50_STATS`).
- `src/prediction/conformal_props.py` (105 LOC) -- split-conformal residual intervals.
  Artifacts `conformal_{stat}.json` exist for all 7 stats + games.
- `src/prediction/prop_uncertainty_estimator.py` -- XGBoost q25/q75 interval heads.
- `src/prediction/correlation_recal.py` (303 LOC) -- archetype-conditioned + globally
  recalibrated prop correlations for parlays. Flag `CV_ARCHETYPE_CORR` default OFF.
- `src/prediction/minutes_aware_props.py` (148 LOC) -- post-process: scale counting
  stats by (exp_minutes/season_avg_minutes)^elasticity; `MINUTES_ELASTICITY` table.
- `src/prediction/prop_pricing_engine.py` (268 LOC) -- `PropPricingEngine`, 10K Monte
  Carlo over `PossessionSimulator` -> full stat distributions vs book lines; Gaussian
  fallback when sim unavailable.
- `src/prediction/hierarchical_props.py` (188 LOC) -- Bayesian blend toward 5 position
  archetype priors (hardcoded `ARCHETYPES`) + AR(p)-based optimal lookback.
- `src/prediction/betting_portfolio.py` (603 LOC) -- Kelly sizing, CLV tracking, arb
  detection, drawdown guard. (See memory: `record_clv()` sign is backwards -- known bug.)
- `src/prediction/injury_availability.py` (364 LOC) -- DNP / availability multiplier.

Adapter layer (the honest "best predictor" the platform actually outputs):

- `domains/basketball_nba/player_props.py` (193 LOC) -- leak-free recency baseline
  prop pricer over `data/domains/basketball_nba/player_boxscores.parquet` (~27.8k
  player-games). Rolling L5/L10/L20 hit-rates + recency-weighted Gaussian P(over),
  with a `_SIGMA_FLOOR` per stat. Explicitly "calibration baseline, NOT the production
  stack; no $ edge."
- `domains/basketball_nba/predictor.py` (297 LOC) -- MOV-aware Elo win-prob +
  as-of-possessions x efficiency totals, reusing the proof builders. The documented
  honest line: "match the devigged close on ML; trail on totals by the freshness gap."

STUB / stranded:

- `src/prediction/multitask_props.py` (85 LOC) -- `MultiTaskPropsModel.train()` raises
  NotImplementedError. Pure stub (PyTorch shared-encoder never built). The REAL
  multitask MLP that ships lives inside `prop_pergame._MultitaskMLPEnsemble` (line 851).

---

## 2. HOW IT WORKS (data flow + key algorithms)

### Per-game prop pipeline (the real one)

Data flow:
1. `build_pergame_dataset(gamelog_dir, min_prior)` (prop_pergame.py:3804) -- walks each
   player's game logs in chronological order; for game G it computes features from games
   strictly before G (rolling L5/L10/std/EWMA/prev per form-stat, rest/travel, home/away,
   opponent-defense factors, playtype frequency joined PRIOR-SEASON only, BBRef advanced,
   contracts, defender-matchup, player-profile, officials/foul/DNP/adv-splits rolling).
   Target = that game's actual box line. No leakage by construction.
2. `feature_columns(stat)` (prop_pergame.py:382) defines the ORDERED schema. Canonical
   live schema = **129 columns** (reb gets +3 reb-context = 132). Verified at runtime.
   The "~190" figure counts all the infrastructure-ready feature groups including the
   many DISABLED ones (tracking, hustle, on_off, gamelog_full, linescore, officials-crew):
   there are ~106 `_KEYS` group references and **23 REVERTED/disabled blocks** in this
   one file -- a large built-but-off feature surface.
3. `train_pergame_models(...)` (prop_pergame.py:4197) -- chronological train/val/holdout
   (val drives XGBoost early stopping; most-recent `holdout_frac=0.2` is the honest OOS).
   Recency-decay sample weights `exp(-decay*age_years)` (older rows count less -- recency
   beats volume). Per-stat regularization overrides in `_STAT_PARAMS` (e.g. STL depth=2,
   min_child_weight=40 to close a 0.18 train/holdout gap). NaN-impute uses TRAIN-split
   medians only (no leak into val/holdout). MLP path = `_MLPSeedEnsemble` (line 759,
   multi-seed avg for stability) + a multitask MLP ensemble (line 851).
4. `predict_pergame(stat, feature_row)` (prop_pergame.py:4859):
   - For `stat in _USE_Q50_STATS` ({reb,blk,stl,tov,fg3m}) -> sole q50 quantile head,
     inverse-transform (sqrt/log per stat), garbage-time haircut, residual correction.
   - Else (pts, ast) -> load base learners, slice X to the artifact's `n_features_in_`
     (handles 85-col legacy vs 129-col current coexistence), invert transforms, NNLS
     blend, isotonic calibrator (`calibration_pergame_<stat>.joblib`), garbage-time
     haircut, then `pregame_residual_heads.apply_residual_correction`.
   - AST deliberately stays on the BLEND path (NOT q50) because calibration toward the
     mean kills the AST edge (see VS_VEGAS sec5 / memory feedback_ast_edge_is_real).

Honest holdout metrics (from `data/models/props_pergame_metrics.json`, n_feature_cols=85
legacy artifact; train/val/holdout temporal split):

| stat | holdout R^2 | holdout MAE | train R^2 | gap |
|------|------------|------------|-----------|-----|
| pts  | 0.5105 | 4.62 | 0.5836 | 0.073 |
| reb  | 0.4224 | 1.91 | 0.4922 | 0.070 |
| ast  | 0.4988 | 1.36 | 0.5582 | 0.059 |
| fg3m | 0.3151 | 0.91 | 0.3827 | 0.068 |
| stl  | 0.1120 | 0.74 | 0.1358 | 0.024 |
| blk  | 0.2166 | 0.52 | 0.2688 | 0.052 |
| tov  | 0.2960 | 0.90 | 0.3466 | 0.051 |

These are honest, leak-free, modest, and gaps are controlled (<0.075). STL is near-noise
(R^2 0.11) -- correctly so; it has no strong player-form signal.

### Win probability

- `WinProbModel.predict(home, away, season, game_date, ref_names)` (line 513) builds a
  feature row via `_build_features` (line 1073) from NBA-Stats-only inputs (Elo, season
  /rolling team net/off/def, rest, travel, last-5, stars-available, synergy PPP, hustle,
  bench net rtg, pace variance, ref FTA tendency). `_blend_prob` (line 487) is an NNLS
  blend of XGB (+optional LGB/LR/MLP-seed-ensemble/NB), optionally isotonic-calibrated.
- `backtest()` (line 951): walk-forward `TimeSeriesSplit(4)`, chronologically sorted,
  reports accuracy / Brier / clv_proxy(=acc-home_baseline). Served at ~69.1% acc
  (models_router.py:114) -- this is an ACCURACY number, not an edge.

### Distribution / pricing variants

- Quantile (`QuantilePropsModel`): P(over) = interpolate the 5-quantile curve at the line
  (no Gaussian). Conformal (`ConformalPredictor`): interval half-width = empirical
  residual quantile -> finite-sample coverage guarantee.
- MC pricing (`PropPricingEngine.get_distribution`): 10K possession sims -> full
  empirical stat distribution -> P(over) and 3% min-edge screen; Gaussian fallback.
- Domains baseline (`price_prop`): recency-weighted L15 Gaussian + L5/L10/L20 hit-rates
  with a per-stat sigma FLOOR -- the honest, transparent reference.

---

## 3. HOW IT IS USED (callers / consumers)

- API: `api/predictions_router.py:293` imports and calls `stack_predict(player_id, ...)`
  for prop predictions. `api/models_router.py:17,105` loads `WinProbModel` and serves
  `/win_probability`. `api/courtvision_router.py`, `api/main.py`, `api/stitch_router.py`
  also reference these.
- Self-improving loop: `src/loop/discovery.py`, `gate.py`, `wiring.py`, `atlas_features.py`
  consume prop_pergame / feature_engineering for signal discovery + the eval gate.
- Scripts: a large fleet of `scripts/*` (backtest_holdout_wf*, backtest_2025_26_rs_oos,
  audit_prop_pergame_variance, audit_quantile_crossing, ablate_*_features, ast_edge_*)
  drives walk-forward validation, ablation, and the ship/revert decisions encoded in the
  inline comments of prop_pergame.py.
- Adapter layer: `domains/basketball_nba/predictor.py` + `player_props.py` are what the
  platform's calibrated-predictor skills (predict-matchup, cross-sport-benchmark,
  calibration-report) actually call -- they are the public-honest surface.

---

## 4. STRENGTHS

- **Genuinely leak-free per-game design.** Every prop feature is built from strictly
  prior games; NaN-impute uses train-split medians only; train/val/holdout is temporal;
  win-prob backtest sorts chronologically before TimeSeriesSplit. This is the hard part
  done right and it is rare.
- **Honest, modest, well-controlled metrics.** Holdout R^2 0.31-0.51 on the volume stats
  with train/holdout gaps <0.075 -- no overfit blowup. The README/packet explicitly
  retract the season-average R^2~0.99 as a near-identity artifact.
- **Disciplined ship/revert culture baked into the code.** 23 disabled feature blocks,
  each annotated with the WF result that killed it (e.g. gamelog_full: train MAE down but
  OOS ROI down across all stats = overfitting; reverted). This is the feature-ceiling
  evidence trail, in-line.
- **Recency-decay weighting** and **per-stat regularization** are principled and measured
  (STL gap 0.18 -> 0.011).
- **Edge-aware calibration policy:** AST kept OFF the q50 calibration path on purpose to
  preserve its divergence-from-market signal -- the team understands accuracy != edge.
- **Multiple coherent uncertainty representations** (quantile, conformal, MC sim) all
  exist and the q50 path actually ships for 5 stats.
- **Clean adapter baseline** (`domains/`) that states its honest limits explicitly.

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS

- **At the historical-data ceiling.** Memory + inline comments document ~17 feature-add
  REVERTs (Loop 7): per-row historical features cannot extract more. The real lever is
  same-day freshness (minutes/role/lineup), which a historical box model cannot see.
- **`multitask_props.py` is a dead stub** -- `train()` raises NotImplementedError; the
  module-level docstring promises a PyTorch shared encoder that was never built. The real
  multitask MLP is buried inside prop_pergame; the standalone file is stranded.
- **Artifact/schema drift risk.** Live artifacts in `data/models` are 85-col legacy while
  the canonical schema is 129-col; `predict_pergame` survives only by slicing to
  `n_features_in_`. The `_BBREF_REORDER_FIX` comment documents that 5/85 feature SLOTS
  were fed WRONG values on the live slate path under the legacy order (fix exists but is
  default OFF pending OOS validation). This is exactly the train/inference-parity bug
  class flagged in memory -- currently mitigated, not eliminated.
- **Sigma too tight (intervals overconfident).** Memory (`feedback_prop_interval_sigma_too_tight`)
  records that prop-interval sigma is too tight on EVERY stat (blk ~x1.86); the prescribed
  fix is multiplicative inflation, not switching to NegBinom. No explicit inflation
  constant is wired into the prop point/interval path -- the domains baseline uses only a
  sigma FLOOR (`_SIGMA_FLOOR`), which raises a too-LOW sigma but does nothing about a
  too-tight learned sigma. Interval coverage is the weakest link.
- **The stack/meta layer is thin relative to the base.** `prop_model_stack` is a Ridge on
  7 base preds + a confidence gate; `prop_stacker` is a linear combiner. Gains over the
  NNLS blend inside prop_pergame are small and the meta artifacts are small JSONs.
- **Win-prob "69.1% accuracy" is an accuracy figure, not an edge.** `clv_proxy = acc -
  home_baseline` is a proxy, not realized CLV; the honest read (predictor.py, season
  backtest memory) is that it MATCHES the devigged close and CLV ~ 0.
- **`betting_portfolio.record_clv()` sign is backwards** (memory feedback_clv_sign) -- do
  not re-endorse its CLV numbers without fixing the sign.
- **Correlation recal is accuracy-only, no price history.** `correlation_recal.py` states
  it has NO SGP price history -- improvements are joint-distribution accuracy, not
  validated ROI; default OFF, recommend-don't-flip.
- **Hierarchical priors are hardcoded league means**, not fit from the corpus; the AR(p)
  lookback selector is built but its production wiring is light.
- **Large stranded/disabled surface.** Many feature loaders (tracking, hustle, on_off,
  gamelog_full, linescore, officials_crew) are fully built with parquet inputs but
  disabled after WF rejection -- maintenance cost with zero current value.
- **STL model is near-noise (R^2 0.11)** -- correct, but means any STL prop confidence is
  essentially the base rate; should be flagged as non-bettable rather than priced.

## 6. PLAN TO GET BETTER (prioritized)

Quick wins (low risk, calibration-positive):
1. **Inflate prop interval sigma per the documented multiplier** (blk ~x1.86, per-stat).
   Re-fit the multiplier on holdout so empirical coverage of the 80% interval hits 80%.
   Pure calibration win; touches conformal/quantile/uncertainty interval emission, not
   the point estimate. Validate with `scripts/audit_quantile_crossing` + a coverage check.
2. **Resolve the 85->129 artifact/schema drift.** Retrain all 7 base + q50 heads on the
   frozen 129-col schema, write `feature_columns` into each `_meta.json`, then flip
   `_BBREF_REORDER_FIX` ON. Removes the 5/85 wrong-slot live-path bug. Verify
   `n_features_in_` == meta (pkl integrity check) before shipping.
3. **Delete or clearly quarantine `multitask_props.py`** (dead stub) and tag the disabled
   feature blocks as ARCHIVED so the live schema is unambiguous.
4. **Fix `betting_portfolio.record_clv()` sign** and re-baseline any CLV reporting.
5. **Flag STL (and arguably BLK) props as low-confidence/non-bettable** in the output
   schema given R^2 0.11/0.22 -- stop implying a usable distribution where there is none.

Bigger bets (the only real accuracy lever):
6. **Same-day freshness features** -- ingest projected minutes / starting lineup /
   late-scratch / load-management at slate time and wire them in BOTH train and inference
   builders (parity). This is the documented decisive lever; everything historical is
   ceilinged. Measure as a leak-free WF lift vs the close, not vs the prior model.
7. **Minutes-conditional props end to end** -- make `minutes_aware_props` a first-class
   conditioning input (predict minutes distribution, then condition the stat distribution
   on it) rather than a post-hoc elasticity scalar.
8. **Honest joint/correlation validation on the FULL stat-pair surface** before flipping
   `CV_ARCHETYPE_CORR` -- and only with real SGP price history; otherwise keep it
   accuracy-display only.
9. **Calibrate-to-the-close as the explicit objective** for win-prob and totals: report
   per-bucket calibration vs devigged close, not raw accuracy, so the product claim stays
   "we match the close."

## 7. HOW GOOD CAN IT GET (honest ceiling)

Realistic best: a **well-calibrated** prop + win-prob predictor whose leak-free OOS
distributions MATCH the devigged closing line within noise, with correctly-covered
intervals (the current single biggest gap). On prop point accuracy the per-game holdout
R^2 (~0.51 pts, ~0.50 ast, ~0.42 reb) is close to the historical-data ceiling: ~17 feature
adds were rejected on WF, so additional historical features will not move it.

What limits the ceiling:
- **Market efficiency.** Pregame books price minutes/role/injury news the model cannot see
  from historical box logs; the gap on totals/props IS that freshness, by the project's own
  diagnosis. No durable $ edge is available here and none should be claimed.
- **Irreducible game-to-game variance.** STL/BLK/3PM are low-count and near-Poisson; their
  R^2 ceilings are intrinsically low.
- **AST is the one near-durable model divergence** (pregame ~+7% in the historical record),
  and even that is fragile (never in playoffs, kept off calibration to preserve it).

The single largest available improvement is the **same-day freshness lever** (item 6): it
is the only input that could close the gap to the close on totals/props. Absent that, the
honest ceiling is "match the close, with honest intervals" -- a calibration product, not an
edge product.
