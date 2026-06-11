# ML Models — CourtVision

> Model zoo, validation discipline, and honest metrics.
> For the full evidence narrative see
> [`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md).
> For system context see [`ARCHITECTURE.md`](../ARCHITECTURE.md).

---

## What Survives Scrutiny

All metrics below are **leak-free walk-forward** unless noted otherwise.
The inflated +18.38% ROI, endQ3 Brier 0.119, and +54% in-play ROI figures have been
retracted — see `docs/JOB_EVIDENCE_PACKET.md §3-4` for root causes.

### Prop Model MAE (pregame, walk-forward, ~51k held-out player-games)

| Stat | MAE | R² | Architecture |
|------|-----|-----|--------------|
| PTS | **4.58** | 0.51 | sqrt+Huber XGB/LGB blend + 5-seed MLP, NNLS-stacked |
| REB | **1.90** | 0.38 | LGB q50 (log1p) |
| AST | **1.34** | 0.50 | log1p XGB+LGB + multitask MLP, NNLS-stacked |
| FG3M | **0.88** | 0.29 | XGB q50 (log1p) |
| STL | **0.72** | 0.18 | XGB q50 (log1p) |
| BLK | **0.44** | 0.16 | XGB q50 (log1p) |
| TOV | **0.89** | 0.22 | XGB q50 (log1p) |

Source: `data/models/quantile_pergame_metrics.json`, `data/cache/pregame_oof.parquet`
(OOF predictions byte-identical to calibration frame; folds have monotonic non-overlapping
holdout windows; N=99,818 player-game rows in training universe).

### Win Probability (pregame)

| Metric | Walk-forward 3-fold | Single-split |
|--------|-------------------|--------------|
| Accuracy | **0.709** | 0.717 |
| Brier score | **0.193** | 0.188 |

Model: 5-way NNLS stack (`win_probability.py`). XGBoost + logistic ensemble;
NNLS autonomously zeroed the XGB weight in one trained version.

### In-Play MAE Lift vs Pregame (endQ3, 550-game retro, RunPod RERUN 2026-05-25)

| Stat | Pregame MAE | endQ3 MAE | Reduction |
|------|-------------|-----------|-----------|
| PTS | ~4.58 | **2.46** | **-47%** |
| REB | ~1.90 | **1.00** | **-47%** |
| AST | ~1.34 | **0.68** | **-50%** |
| FG3M | ~0.88 | **0.42** | **-53%** |
| STL | ~0.72 | **0.32** | **-55%** |
| BLK | ~0.44 | **0.20** | **-55%** |
| TOV | ~0.89 | **0.45** | **-50%** |

Important context: most of the ~47–55% reduction is **mechanical** — three quarters
of box score are observed by endQ3. The learned-head value-add over a naive
carry-forward baseline is ~26%, validated walk-forward.

### Market Efficiency (honest)

Against real DraftKings/FanDuel/MGM **closing** lines: model is roughly
break-even-minus-vig overall (~-2% unfiltered from `gate1_full_analysis.json`).
One genuine exception: **AST ~+4–5% ROI**, positive on three independent line
corpora, book-robust but regime-dependent (breaks in playoffs).
The market is efficient on closing lines; that is the honest, sophisticated finding.

---

## Model Inventory

### Win Probability

**File:** `data/models/win_probability.pkl`
**Algorithm:** XGBoost classifier (5-way NNLS stack)
**Features:** team pace, offensive/defensive rating differentials, rest days,
travel distance (`schedule_context.compute_travel_distance`), synergy isolation
PPP, referee FTA tendency, back-to-back flag

```python
# Load and predict
from src.prediction.win_probability import load, predict
model = load("data/models/win_probability.pkl")
result = predict("BOS", "MIL", season="2025-26")
# {"home_win_prob": 0.61, "confidence_interval": [0.56, 0.66], ...}
```

**endQ3 Brier — honest version:** the famous endQ3 Brier 0.1191 figure is
**retracted** (two Q4-derived features leaked; the cited source reports 0.1354,
not 0.1191). Leak-free walk-forward endQ3 Brier: **~0.141** after removing
`halftime_pace_shift` and `trailing_team_q4_usg_hhi` from `build_quarter_features.py`.

---

### Player Prop Models

**Primary dispatch:** `src/prediction/prop_model_stack.py` — `stack_predict()`
**Fallback:** `src/prediction/player_props.py` — `predict_props()`
**Files:** `data/models/props_{stat}_v2.json` (v2 active; v1 retained as fallback)

```python
from src.prediction.prop_model_stack import stack_predict
result = stack_predict("Jayson Tatum",
                       game_context={"away_team": "MIL", "season": "2025-26"})
# result.predictions → {"pts": 27.4, "reb": 8.1, "ast": 4.8, ...}
# result.confidence  → 0.82
# result.suppressed  → False (True if DNP risk > 0.40)
```

#### Architecture by Stat

The q50 (quantile) architecture dominates squared-error/Huber blends because
sportsbook prop lines score against the median, not the mean.

| Stat | Primary head | Why q50 wins |
|------|-------------|--------------|
| PTS | sqrt+Huber XGB/LGB + 5-seed MLP, NNLS | High variance; NNLS balances |
| REB | LGB q50 (log1p) | Right-skewed; median is the better point estimate |
| AST | log1p XGB+LGB + multitask MLP, NNLS | Q50 + multitask share signal |
| FG3M | XGB q50 (log1p) | Discrete count; median beats mean |
| BLK | XGB q50 (log1p) | Biggest single-stat loop win: -16% MAE |
| TOV | XGB q50 (log1p) | log1p transform reduces impact of outlier games |
| STL | XGB q50 (log1p) | R²=0.18 — do not size aggressively |

**Dispatch logic** (`prop_pergame.py::_USE_Q50_STATS`):
```python
_USE_Q50_STATS = {"reb", "fg3m", "stl", "blk", "tov"}
# AST + PTS use the NNLS-stacked ensemble
```

#### Quantile Intervals

`data/models/quantile_calibration.json` — per-stat q10/q90 scale factors for 80%
empirical coverage. `src/prediction/quantile_calibration.py` applies the calibration.

#### Conformal Prediction Intervals

**Module:** `src/prediction/conformal_props.py` — `ConformalPredictor`

Split conformal intervals with guaranteed finite-sample coverage:

```python
from src.prediction.conformal_props import ConformalPredictor

cp = ConformalPredictor()
cp.calibrate(y_holdout, model.predict(X_holdout))
lo, hi = cp.predict_interval(y_hat=22.5, coverage=0.80)
# Only bet when interval_width < 1.5 × vig_width (rule of thumb)
```

The conformal interval `[y_hat ± q]` satisfies `P(y_true ∈ interval) ≥ coverage`
for any finite sample, without distributional assumptions. `q` is the empirical
quantile of absolute residuals on the calibration holdout.

---

### In-Play Residual Stack

**Primary entry point:** `src/prediction/live_engine.py` — `project_from_snapshot()`

Architecture: layered residual stack on top of the pregame base model.

```
pregame base prediction (q50)
  + endQ1 period snapshot head    (SHIPPED, cycle 106a)
  + endQ2 period snapshot head    (SHIPPED, cycle 106a)
  + foul_change residual          (SHIPPED: PTS -0.24 on foul stratum)
  + blowout_flip residual         (SHIPPED: data/models/blowout_residual.lgb)
  + heat_check shrinkage          (SHIPPED: stratified dispatch)
  + learned Q4 minute trajectory  (SHIPPED, cycle 110: PTS -0.2312 MAE)
  = live projection
      + calibrated q10/q90 bands  (80% empirical coverage)
```

Rejected: endQ3 period head (2/7 stats, did not meet ≥4/7 ship gate).

**Ship gate for period heads:** 4/4 walk-forward folds positive AND production
single-split positive AND ≥4/7 stats win. Cycle 105a (play_probability) failed
correctly: WF 4/4 on only 2/7 stats → rejected.

#### In-Play Usage

```python
from src.prediction.live_engine import project_from_snapshot

# Snapshot: dict with period, minutes_played, current_pts, current_reb, ...
proj = project_from_snapshot(player_id=2544, game_id="0022400512", snapshot=snapshot)
# proj.pts, proj.reb, proj.ast, ... (projected final stats)
# proj.intervals → {pts: (lo, hi), ...}  (80% calibrated bands)
```

---

### xFG (Expected Field Goal)

**File:** `data/models/xfg_v1.pkl`
**Brier score:** 0.226 on 221,866 shots (3 seasons)
**Stack:** `data/models/xfg_cv_stack.pkl` (CV-augmented; gated on CV data availability)

Features: shot distance, court zone, nearest defender distance, shot angle,
fatigue proxy, game clock, shot clock.

```python
# Via API: GET /predictions/shot?defender_dist=3.1&shot_angle=45&court_zone=paint
# → {"probability": 0.487, "model": "xfg_v1", ...}
```

---

### Supporting Models

| Model | File | Algorithm | Key metric |
|-------|------|-----------|------------|
| DNP predictor | `data/models/dnp_model.pkl` | LogisticRegression | AUC 0.979 |
| Matchup model | `data/models/matchup_model.json` | XGBoost | R² 0.796 |
| Overtime probability | `data/models/overtime_probability.pkl` | Classifier | — |
| Referee FTA tendency | `data/nba/ref_fta_tendency.json` | Lookup table | Integrated into win-prob features |
| Age curve | `data/models/age_curve_model.pkl` | Regression | — |
| Altitude impact | `data/models/altitude_model.pkl` | Regression | — |
| Back-to-back | `data/models/back_to_back_model.pkl` | XGBoost | — |
| Injury risk | `data/models/injury_risk.pkl` | XGBoost | — |
| Injury return | `data/models/injury_return.pkl` | XGBoost | — |
| Load management | `data/models/load_management.pkl` | Logistic | — |
| Line movement | `data/models/line_movement_predictor.pkl` | — | Sharp-money detector |
| Breakout predictor | `data/models/breakout_predictor.pkl` | XGBoost | — |
| Foul trouble | `data/models/foul_trouble.pkl` | — | — |
| Garbage time | `data/models/garbage_time.pkl` | — | — |
| Rotation predictor | `data/models/rotation_predictor.pkl` | — | — |
| Soft book lag | `data/models/soft_book_lag.pkl` | — | Sharp-window timing |
| CV-derived (Tier 4/5) | `data/models/tier4_*.pkl`, `tier5_*.pkl` | — | Gated on CV data; SHAP ≈ 0 in prod |

**Model registry:** `data/models/model_registry.json` — central manifest tracking
model lineage, data windows, and metrics. 85 models registered.

---

### De-Vig Engine

**Module:** `src/prediction/devig.py`

Four de-vig methods implemented from scratch:

| Method | Notes |
|--------|-------|
| **Shin (1992)** | Default; insider-trading model; numerically stable bisection solver |
| Additive | Simple hold removal |
| Proportional | Proportional to implied probabilities |
| Multiplicative | Log-linear |
| Power | Exponent shrinkage |

```python
from src.prediction.devig import devig, american_to_prob, prob_to_american

fair = devig(over_odds=-115, under_odds=-105, method="shin")
# {"fair_over": 0.523, "fair_under": 0.477, "overround": 0.049}
```

7 unit tests verify output matches published Shin theory.

---

### Kelly Sizing + CLV

**Module:** `src/prediction/betting_portfolio.py` — `kelly_corr()`

```
edge = fair_prob - implied_prob  (after de-vig)
kelly_f = edge / (implied_prob * (1/fair_prob - 1))  # raw Kelly

# Applied constraints:
kelly_f *= 0.25          # quarter-Kelly (fractional)
kelly_f = min(kelly_f, 0.05)  # cap at 5% of bankroll
# Ledoit-Wolf shrinkage on 7×7 residual covariance matrix
# Drawdown circuit breaker: halt sizing when drawdown > threshold
# Isotonic calibration override on win-prob input
```

**CLV tracking:** `src/prediction/betting_portfolio.py` records predicted prob
vs Pinnacle closing line when available. Historical Gate 1 ran on DK/FD/MGM/BetRivers
closes (8,360 bets); Pinnacle CLV data pending (first archive Oct 2026).

---

## Validation Discipline

This section documents the methodology that governs all model evaluation.
Violating these rules causes inflated metrics that collapse on live data.

### Walk-Forward Cross-Validation

**Module:** `src/prediction/walk_forward_backtester.py`

```
Split strategy: expanding window (not k-fold)

fold 1: train [0..N/4]        test [N/4..N/2]
fold 2: train [0..N/2]        test [N/2..3N/4]
fold 3: train [0..3N/4]       test [3N/4..N]

For each fold:
  assert max(train_dates) < min(test_dates)  ← assertion-level leak guard
```

No K-fold on time-ordered data. K-fold would allow future information to flow
into the training window (adjacent folds share temporal neighbors).

**Ship gate:** ALL folds must show delta_MAE < 0. A single fold that regresses
kills the signal.

### Truncation-Invariance Leak Test

**Module:** `tests/test_ingame_leak_free.py`

```python
# Property: a feature computed at time T must be identical
# whether or not future events are in the event stream.

stream_full     = all_events_through_game_end
stream_truncated = all_events[:halfway_point]

features_full      = featurize(stream_full,      as_of=T)
features_truncated = featurize(stream_truncated, as_of=T)

assert np.allclose(features_full[:len_truncated],
                   features_truncated)  # byte-identical
```

This catches lookahead bias in rolling/cumulative features where a "past" row's
value changes when future rows are added.

### Multi-Corpus Calibration Gate

**Module:** `scripts/validate_calibration_multicorpus.py`

A calibration layer only ships if it beats raw model predictions on **≥2
independent out-of-sample corpora**. Single-window calibration gains are artifacts
(the calibrator overfits to the window's specific distribution shift). The
multi-corpus requirement is the minimum bar for durability.

### Shadow Logging + Settlement

**Shadow logger:** `src/prediction/shadow_logger.py`

Records every bet the engine evaluates, including bets the decision engine
**blocked** (`gate_blocked_by` column). This creates a counterfactual dataset:
what would have happened if the threshold had been lower? This prevents
survivorship bias in threshold calibration.

```
data/shadow/<game_id>_<date>.csv
columns: player, stat, direction, predicted_prob, market_prob, edge, ev,
         gate_blocked_by, kelly_fraction, ...
```

**Settlement:** `src/prediction/settlement_engine.py` — nightly join of shadow
log to `cdn.nba.com` final box scores → realized W/L/P and ROI per bet.

### Self-Caught Leaks (The Real Track Record)

The most important validation artifacts are the self-caught errors:

1. **+18.38% ROI → retracted.** `scripts/run_gate1_full_analysis.py` showed the
   grader reads `devig(over_odds, under_odds)` — the market's own lean — and never
   reads the model prediction. At real odds: ~-4%.
2. **endQ3 Brier 0.1191 → retracted.** `halftime_pace_shift` and
   `trailing_team_q4_usg_hhi` in `build_quarter_features.py` are computed from Q4
   data, leaking the quarter being predicted. Honest leak-free: ~0.141.
3. **0.79 CV R² → 0.06 holdout R².** Caught in `src/prediction/prop_cv_split.py`;
   corrective regularization hard-coded so the mistake cannot silently reappear.

---

## Model Registry and File Map

| File | Purpose |
|------|---------|
| `data/models/model_registry.json` | Central manifest: lineage, data windows, metrics |
| `data/models/quantile_pergame_metrics.json` | Walk-forward MAE + coverage_80 per stat |
| `data/models/quantile_calibration.json` | Per-stat q10/q90 scale factors |
| `data/models/win_prob_metrics.json` | Win-prob evaluation metrics |
| `data/models/game_models_metrics.json` | Game-level model evaluation |
| `data/models/dnp_model_meta.json` | DNP model metadata |
| `data/models/gate1_results_summary.json` | Real-Vegas Gate 1 (8,360 bets, DK/FD/MGM/BetRivers) |
| `data/cache/pregame_oof.parquet` | OOF predictions (byte-identical to calibration frame) |
| `data/models/edge_isotonic_*.joblib` | Per-stat isotonic edge calibration (iter-34) |

---

## Planned (Data-Blocked)

These models require more CV game data and are not yet trained.

### CV Behavioral (requires 20+ A/B-grade games)

- **xFG v2 (Full Spatial):** closeout speed + shot-clock at release + fatigue penalty → target Brier 0.200
- **Play-type classifier:** ISO / P&R / Spot-up / Cut / Transition from CV event sequence
- **Spacing rating → scoring efficiency**

### Prop Retrain with CV Features (Phase 7)

All 7 prop models will retrain with `drives_per_36`, `box_out_rate`,
`off_ball_distance_per_36`, `closeout_speed_allowed` when sufficient CV game
coverage exists. Current SHAP ≈ 0 reflects data scarcity, not model exclusion.

---

*Related: [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`docs/CV_TRACKING.md`](CV_TRACKING.md) · [`docs/API.md`](API.md) · [`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md)*

*Last verified: 2026-06-11*
