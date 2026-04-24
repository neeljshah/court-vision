# Results

Reliability diagrams, CLV plots, and per-model ECE for CourtVision v0.14.0-80g.

## Schema

| File | Description |
|------|-------------|
| `reliability_pts.png` | Reliability diagram — points model |
| `reliability_reb.png` | Reliability diagram — rebounds model |
| `reliability_ast.png` | Reliability diagram — assists model |
| `reliability_fg3m.png` | Reliability diagram — 3PM model |
| `reliability_tov.png` | Reliability diagram — turnovers model |
| `reliability_blk.png` | Reliability diagram — blocks model |
| `reliability_stl.png` | Reliability diagram — steals model |
| `clv_by_market.png` | CLV distribution by market type |
| `clv_by_time.png` | CLV vs time-to-close scatter |
| `clv_cumulative.png` | Cumulative CLV over bet sequence with bootstrap band |
| `ece_by_model.csv` | ECE and MCE per model, walk-forward folds |
| `clv_picks.csv` | Full 312-pick CLV dataset |

## Current status

Plots pending release v0.14.0-80g. Run `python scripts/generate_results.py` after
the 80-game holdout to populate this directory.
