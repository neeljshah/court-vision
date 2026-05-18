---
tags: [tracking, issues]
updated: 2026-05-16
aliases: ["Open Issues"]
---
# Open Issues

*Auto-synced from `docs/CLAUDE-state.md` on 2026-05-17*

1. `betting_portfolio.kelly_corr` — correlation matrix not populated. Run `--build-residuals` then `--compute-corr`.
2. CV registry sparse (29 usable: 9 CLEAN + 20 PARTIAL of 75 attempted) — target 80 CLEAN to meaningfully improve R².
3. `ball_valid_pct=0%` on some games: `ball_track_suspended` stays True entire video — investigate after 80-game run.

-> Tracked in `docs/CLAUDE-state.md`
-> Priority aligned with [[Strategy/Build Phases]]
