# Prop Model Holdout Validation Report

**Generated:** 2026-03-24 15:33  
**Train cutoff:** 2025-02-01  
**Holdout window:** 2025-02-01 → 2025-03-24  
**Method:** Per-game rolling features (10-game window) from gamelog files  

## Summary

| Stat | N | MAE | R² | Hit Rate (±1.5) | Over% | Under% | Reported MAE | Reported R² | Status |
|------|---|-----|----|-----------------|----|------|------------|-----------|--------|
| PTS | 10336 | 4.797 | 0.4831 | 21.3% | 49.9% | 50.1% | 0.310 | 0.994 | 🔴 NEEDS_RETRAIN |
| REB | 10336 | 2.002 | 0.4148 | 48.2% | 52.6% | 47.4% | 0.115 | 0.995 | 🔴 NEEDS_RETRAIN |
| AST | 10336 | 1.397 | 0.4853 | 65.7% | 54.1% | 45.9% | 0.091 | 0.992 | 🔴 NEEDS_RETRAIN |
| FG3M | 10336 | 0.930 | 0.3029 | 81.1% | 59.3% | 40.7% | 0.083 | — | 🔴 NEEDS_RETRAIN |
| STL | 10336 | 0.709 | 0.0947 | 91.7% | 56.6% | 43.4% | 0.066 | — | 🔴 NEEDS_RETRAIN |
| BLK | 10336 | 0.507 | 0.1897 | 95.0% | 70.7% | 29.3% | 0.044 | — | 🔴 NEEDS_RETRAIN |
| TOV | 10336 | 0.885 | 0.2753 | 84.3% | 53.2% | 46.8% | 0.078 | — | 🔴 NEEDS_RETRAIN |

## Key Findings

### Why Reported R²=0.994 Is Inflated

Training used simulated features: `roll = season_avg × (1 + noise_15%)`,
target = `season_avg`. This is a near-identity function — the model learns to
denoise a synthetic signal, not predict per-game outcomes from player form.
Holdout R² above reflects true out-of-sample performance on real per-game data.

### MAE Delta (Holdout − Reported)

- **PTS**: holdout MAE = 4.797 (reported 0.310, Δ = +4.487)
- **REB**: holdout MAE = 2.002 (reported 0.115, Δ = +1.887)
- **AST**: holdout MAE = 1.397 (reported 0.091, Δ = +1.306)
- **FG3M**: holdout MAE = 0.930 (reported 0.083, Δ = +0.847)
- **STL**: holdout MAE = 0.709 (reported 0.066, Δ = +0.643)
- **BLK**: holdout MAE = 0.507 (reported 0.044, Δ = +0.463)
- **TOV**: holdout MAE = 0.885 (reported 0.078, Δ = +0.807)

### Prediction Bias

- **PTS**: under-predicts by 0.816 on average (mean_pred=10.37, mean_actual=11.19)
- **REB**: under-predicts by 0.195 on average (mean_pred=4.05, mean_actual=4.25)
- **AST**: under-predicts by 0.152 on average (mean_pred=2.46, mean_actual=2.62)
- **FG3M**: under-predicts by 0.124 on average (mean_pred=1.20, mean_actual=1.33)
- **STL**: under-predicts by 0.089 on average (mean_pred=0.68, mean_actual=0.77)
- **BLK**: under-predicts by 0.016 on average (mean_pred=0.43, mean_actual=0.45)
- **TOV**: under-predicts by 0.170 on average (mean_pred=1.10, mean_actual=1.27)

## CV Feature Lift (Phase 7)

CV features (defender distance, contested shot rate, shot zone tendencies) are not yet
in the training set — no full games have been processed through the tracker.
After Phase G (10+ games), these features should add ~2–5% lift on pts/fg3m.

## Action Items

- 🔴 **Retrain required:** PTS, REB, AST, FG3M, STL, BLK, TOV — holdout R² < 0.7
- Current models trained on season-level aggregates with simulated noise.
  For production: retrain on per-game rolling features from gamelogs.
- After Phase G: add cv_features to training row → expect pts/fg3m lift.

## Raw Results

```json
{
  "pts": {
    "n": 10336,
    "mae": 4.797,
    "r2": 0.4831,
    "hit_rate": 0.213,
    "over_rate": 0.499,
    "under_rate": 0.501,
    "mean_actual": 11.185,
    "mean_pred": 10.369
  },
  "reb": {
    "n": 10336,
    "mae": 2.002,
    "r2": 0.4148,
    "hit_rate": 0.482,
    "over_rate": 0.526,
    "under_rate": 0.474,
    "mean_actual": 4.247,
    "mean_pred": 4.052
  },
  "ast": {
    "n": 10336,
    "mae": 1.397,
    "r2": 0.4853,
    "hit_rate": 0.657,
    "over_rate": 0.541,
    "under_rate": 0.459,
    "mean_actual": 2.615,
    "mean_pred": 2.463
  },
  "fg3m": {
    "n": 10336,
    "mae": 0.93,
    "r2": 0.3029,
    "hit_rate": 0.811,
    "over_rate": 0.593,
    "under_rate": 0.407,
    "mean_actual": 1.327,
    "mean_pred": 1.203
  },
  "stl": {
    "n": 10336,
    "mae": 0.709,
    "r2": 0.0947,
    "hit_rate": 0.917,
    "over_rate": 0.566,
    "under_rate": 0.434,
    "mean_actual": 0.771,
    "mean_pred": 0.682
  },
  "blk": {
    "n": 10336,
    "mae": 0.507,
    "r2": 0.1897,
    "hit_rate": 0.95,
    "over_rate": 0.707,
    "under_rate": 0.293,
    "mean_actual": 0.446,
    "mean_pred": 0.43
  },
  "tov": {
    "n": 10336,
    "mae": 0.885,
    "r2": 0.2753,
    "hit_rate": 0.843,
    "over_rate": 0.532,
    "under_rate": 0.468,
    "mean_actual": 1.266,
    "mean_pred": 1.096
  }
}
```
