# Cycle 92f (loop 5) -- T1-D Q1 pace residual probe (scaffold)

## Setup
- Q1 data source: data/player_quarter_stats.parquet (cycle 91a; 91 games covered, 2024-10-22 -> 2024-12-03).
- Holdout window restricted to Q1-coverage dates. holdout n=1380, rows with Q1 pace residual attached: 457.
- Possessions formula: FGA + 0.44*FTA - OREB + TOV (team-level Q1 box).
- Pace = poss * 48 / team_min; expected pre-game pace = (home_pace + away_pace) / 2 from season_games.
- Use-case: mid-game prediction (post-Q1). Probe measures value of a hypothetical live Q1-pace signal.

## Residual distribution
- n: 457
- mean: +0.184, std: 7.767
- pct: p10=-9.57, p50=-0.41, p90=+10.46
- range: [-14.40, +18.08]

## k-sweep (single split)

| k | n_improved | PTS delta | REB delta | AST delta | TOV delta | PTS+REB+AST agg |
|---|------------|-----------|-----------|-----------|-----------|-----------------|
| 0.05 | 0/7 | -0.0007 | +0.0018 | +0.0022 | +0.0018 | +0.0033 |
| 0.10 | 0/7 | +0.0253 | +0.0099 | +0.0066 | +0.0055 | +0.0419 |
| 0.15 | 0/7 | +0.0692 | +0.0232 | +0.0154 | +0.0105 | +0.1079 |
| 0.20 | 0/7 | +0.1294 | +0.0425 | +0.0274 | +0.0164 | +0.1993 |

## Verdict

**REJECT signal**

Note: see SS / WF metrics above

## Auto-scale
Probe is gated on data/cache/quarter_box/<gid>_q1.json and data/player_quarter_stats.parquet. Re-running after cycle 92c daemon adds more games will automatically widen the holdout and re-sweep without code changes.
