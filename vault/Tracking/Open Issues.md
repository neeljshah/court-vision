---
tags: [tracking, issues]
updated: 2026-05-16
aliases: ["Open Issues"]
---
# Open Issues

*Auto-synced from `docs/CLAUDE-state.md` on 2026-05-17*

1. `betting_portfolio.kelly_corr` — correlation matrix not populated. Run `--build-residuals` then `--compute-corr`.
2. CV registry sparse (17 games) — target 80 to meaningfully improve R².
3. `ball_valid_pct=0%` on some games: `ball_track_suspended` stays True entire video — investigate after 80-game run.

## Addressed (2026-05-17)
- ✅ CLV validation gap — `scripts/clv_tracker.py` tracks realized CLV vs opening lines; `tests/test_betting_portfolio.py` tests full CLV pipeline
- ✅ Temporal CV leakage — `prop_cv_split.py` + `retrain_props_temporal_cv` enforce forward-chaining splits
- ✅ Model drift detection — `data/models/model_registry.json` + CI regression gate (test_model_registry.py::test_holdout_r2_above_baseline)

-> Tracked in `docs/CLAUDE-state.md`
-> Priority aligned with [[Strategy/Build Phases]]
