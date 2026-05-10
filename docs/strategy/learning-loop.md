# Learning Loop — How the System Improves Every Night

*Status: Framework designed. Nightly automation is Phase 8. Residual collection and CLV computation are wired as of Phase 13.5. Updated 2026-05-10.*

---

## Overview

The system is not static. Every game produces new residuals, every settled bet produces a new CLV data point, and the calibration and model weights can be updated from this stream. The goal: a system that is measurably better on October 22 (NBA Opening Night target) than it was three months earlier — without manual intervention for each improvement.

---

## The Nightly Pipeline

After the last game of each evening settles:

```
1. Residual collection
2. CLV computation
3. Calibration layer update
4. Feature importance drift check
5. Model retrain gate evaluation
6. Account health update
7. Adversarial book model update
8. Morning readiness confirmation
```

---

## Step 1: Residual Collection

For every settled bet:
```python
residual = {
    'game_id': ...,
    'player_id': ...,
    'prop_type': ...,
    'model_prediction': predicted_value,  # the point estimate
    'actual_outcome': actual_value,
    'prediction_error': predicted_value - actual_value,
    'settled_at': timestamp
}
```

Residuals are written to `data/output/residuals/` and accumulated in `prop_residuals.json`.

**Why residuals matter:**
- Calibration training: the calibration layer learns from `(predicted_probability, actual_outcome)` pairs
- Correlation matrix: Ledoit-Wolf shrinkage on the residual covariance matrix between prop types per player (is pts error correlated with reb error for the same player?)
- Systematic bias detection: if pts residuals are consistently positive for home teams, there's a feature leak or missing feature

---

## Step 2: CLV Computation

For every settled bet, compute:
```python
clv = shin_devig(model_prob_at_placement) - shin_devig(pinnacle_closing_prob)
```

Both probabilities are devigged before comparison. This removes vig-level changes between when the bet was placed and when the market closed.

**Rolling windows maintained:**
- 7-day CLV (weekly signal — detects rapid edge decay)
- 30-day CLV (monthly signal — primary performance metric)
- 90-day CLV (quarterly signal — structural trend)
- Full-history CLV (overall validation)

**CLV alerts:**
- If 7-day CLV < 30-day CLV by > 10 bps: flag edge decay
- If 7-day CLV turns negative for 5+ consecutive days: alert for model review
- If 30-day CLV positive and stable: system is performing as expected

---

## Step 3: Calibration Layer Update

The calibration layer (Platt scaling / isotonic regression) maps raw model probability → calibrated probability. It learns from `(raw_prob, actual_binary_outcome)` pairs.

**Update trigger:** When new residuals in the rolling window exceed a minimum count threshold per prop type (e.g., 50 new samples since last calibration), refit the calibration layer on the updated dataset.

**Validation before deployment:** Calibration update is only deployed if the new calibration reduces ECE on a holdout set. Otherwise, keep the prior calibration.

```python
# Nightly calibration check
def maybe_update_calibration():
    for prop_type in PROP_TYPES:
        new_samples = get_new_residuals(prop_type, since=last_calibration_date[prop_type])
        if len(new_samples) >= CALIBRATION_UPDATE_THRESHOLD:
            new_cal = fit_isotonic_regression(new_samples)
            if evaluate_ece(new_cal, holdout) < current_ece[prop_type]:
                deploy_calibration(prop_type, new_cal)
                log_calibration_update(prop_type, old_ece, new_ece)
```

---

## Step 4: Feature Importance Drift Detection

Monthly (not nightly): compute SHAP feature importance on the most recent N games.

**Comparison:** Current-month importance vs 3-month-ago importance.

| Feature drift pattern | Interpretation | Action |
|----------------------|----------------|--------|
| CV features losing importance | Books starting to price spatial data | Edge decay signal — accelerate edge 8, 9 development |
| Referee features gaining importance | Line markets not fully adjusting | Increase position sizing on ref-sensitive props |
| Any feature gains/loses > 20% relative importance | Structural shift | Manual review of that feature pipeline for data quality |

**The core alarm:** If `defender_distance` and `spacing_score` importance drops significantly versus prior months, the structural moat (books pricing from box scores while we use spatial data) may be narrowing. This is the signal to act on edge 23 (adversarial book model) and accelerate CV feature development.

---

## Step 5: Model Retrain Gate

Monthly: evaluate whether to retrain models on the expanding dataset.

**Retrain triggers:**
- New CV games available (Tier 3–4 models need more data)
- Season data added (season start to current date)
- A/B test result confirms new features improve holdout R²

**Validation gate:** New model must beat prior model on holdout by Δ R² ≥ 0.01 before deployment. Walk-forward validation harness required; K-fold is not permitted.

**Deployment:** New model goes live on the next day's slate if gate passes. CLV monitoring on first 50 bets from new model before full deployment.

---

## Step 6: Account Health Update

Post-game:
- Update bet count per book
- Recompute rolling win rate per book (50-bet window)
- Recompute heat score per book
- Flag any books approaching threshold
- Log the routing allocation for the day

The account health trajectory is as important as the current snapshot: a book whose heat score is rising 0.05/week is approaching limits in ~10 weeks at current velocity.

---

## Step 7: Adversarial Book Model Update

As more line movement data accumulates:
- Update per-book line adjustment speed estimates
- Update steam detection thresholds (what magnitude of movement is actually signal vs noise)
- Track whether steam detection generates positive CLV

The adversarial model is most valuable after 3–6 months of continuous line monitoring, not in early days. Building the data store now enables this improvement later.

---

## Step 8: Morning Readiness Confirmation

Before the 6am prop sweep:
- Confirm all APIs are responding
- Confirm models are loaded and serving
- Confirm residuals from prior day were written
- Confirm calibration layer is current
- Send system health summary

If any component is not ready, alert before the 6am window. Missing the opening line capture because of a silent failure is an avoidable loss.

---

## The Compounding Effect

The learning loop creates compounding improvement:
- Better calibration → better edge estimates → better Kelly sizing → less overstaking
- More residuals → better correlation matrix → better portfolio optimization
- More line movement data → better steam detection → better timing
- More CV games → retrain Tier 3–4 models → higher R² → more accurate distributions

The value of the system in October 2027 is materially higher than in October 2026 because of these compounding improvements — if the learning loop runs correctly.

---

*See [validation-methodology.md](../research/validation-methodology.md) for the CLV framework underlying these metrics. See [calibration.md](../models/calibration.md) for probability calibration implementation.*
