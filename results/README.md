# Results

This directory will contain reliability diagrams, CLV plots, and per-model ECE once the 80-game CV run and paper-trading gate complete.

## Status

`scripts/generate_results.py` has been run and produced [`STATUS.md`](STATUS.md), [`holdout_metrics.csv`](holdout_metrics.csv), and [`holdout_metrics.png`](holdout_metrics.png) — see `STATUS.md` for the current holdout R²/MAE table and the list of gated artifacts still pending.

The 80-game CV ingest run is stalled, not progressing: as of 2026-07-15, 9 CLEAN + 20 PARTIAL of 307 tracked games (81 processed, 26 verified, 46 REJECT), still short of the 80-CLEAN target, with 0 games processed in the last 24h.

Metrics available right now: [`data/models/model_registry.json`](../data/models/model_registry.json) — API-data holdout R² and MAE per model, walk-forward temporal CV.

## Artifact schema (post-run)

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
| `clv_picks.csv` | Full pick-log CLV dataset (populated after paper-trading gate: ≥50 settled bets) |
