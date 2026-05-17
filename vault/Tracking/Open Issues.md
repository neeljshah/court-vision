---
tags: [tracking, issues]
updated: 2026-05-16
aliases: ["Open Issues"]
---
# Open Issues

*Updated 2026-05-17 (credibility audit)*

## Open
1. `betting_portfolio.kelly_corr` — correlation matrix not populated. Run `--build-residuals` then `--compute-corr`.
2. CV registry sparse (17 games) — target 80 to meaningfully improve R².
3. `ball_valid_pct=0%` on some games: `ball_track_suspended` stays True entire video — investigate after 80-game run.

## Resolved
- `win_probability._MODEL_FEATURE_COLS` stale slice bug — model retrained to 71 features but code was slicing to 67; fixed (2026-05-17).

-> Tracked in `docs/CLAUDE-state.md`
-> Priority aligned with [[Strategy/Build Phases]]
