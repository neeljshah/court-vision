---
tags: [models, metrics]
updated: 2026-05-17
aliases: ["Model Performance"]
---
# Model Performance

Tracking dashboard for all model metrics.

## Primary Models

| Model | Metric | Value | Target |
|-------|--------|-------|--------|
| [[Win Probability]] | Accuracy | 69.1% | 72% |
| [[Win Probability]] | Brier | 0.203 | <0.19 |
| [[Player Props]] PTS | Holdout R² | 0.41 | 0.55 |
| [[Player Props]] REB | Holdout R² | 0.38 | 0.50 |
| [[Player Props]] AST | Holdout R² | 0.36 | 0.55 |
| [[Player Props]] FG3M | Holdout R² | 0.29 | 0.35 |
| [[Player Props]] BLK | Holdout R² | 0.16 | 0.25 |
| [[Player Props]] TOV | Holdout R² | 0.22 | 0.30 |
| [[Player Props]] STL | Holdout R² | 0.18 | 0.20 |
| [[xFG Model]] | Brier | 0.226 | <0.20 |
| [[DNP Predictor]] | AUC | 0.979 | >0.97 |
| [[Matchup Model]] | R² | 0.796 | >0.80 |

## Improvement Path

1. More [[CV Data Status|CV games]] (17 → 80) — biggest single lever
2. Wire [[Market Microstructure]] features
3. [[Calibration]] tuning across all models
4. [[Tier 4-5 CV Models]] as meta-features

→ All models in [[Model Registry]]
→ Tracked per session in [[Tracker Improvements]]

## Validation Infrastructure (2026-05-17)
- **Temporal CV**: `retrain_props_temporal_cv` uses forward-chaining splits; rolling features computed per-fold (no leakage)
- **Model registry**: `data/models/model_registry.json` stores holdout_r2/mae, train_r2/mae, needs_retrain flag per stat
- **CI regression gate**: `test_holdout_r2_above_baseline` fails CI if any model's holdout R² drops below floor
- **Holdout R² floors**: pts≥0.25, reb≥0.22, ast≥0.20, fg3m≥0.12, stl≥0.08, blk≥0.07, tov≥0.10
