# CourtVision — Knowledge Base Home
*Last updated: 2026-03-24*

---

## Quick Navigation

| Note | Description |
|------|-------------|
| [[01 - System Architecture]] | End-to-end architecture, data flow, component map |
| [[02 - Model Catalog]] | All 90 models, tiers, training status, performance |
| [[03 - Data Sources]] | Every data source, scraper, TTL, coverage stats |
| [[04 - Pipeline Flow]] | Step-by-step pipeline from video to edge flag |
| [[05 - Ideas and Future Work]] | Roadmap ideas, experiments, backlog |

---

## Current Status

**Phase:** 4 of 17 — Tier 1 Models (Active)
**Next action:** Phase F — run `scripts/full_game_pipeline.py`
**Full game CV data:** 0 games processed (blocker for Phases 7–16)

### Open Priority Issues

- 🔴 Win prob / game prediction — data ready, live feature pipeline TBD
- 🔴 Analytics + tracking dashboards — not yet built
- 🟡 HSV re-ID — jersey confusion on similar-colored uniforms
- 🔴 Real game clip needed for tracker benchmarking (plateaued on calibration clip)
- 🟢 Pano validation + fallback — fixed 2026-03-12

---

## Model Performance (Phase 4 — Trained)

| Model | Metric | Value |
|-------|--------|-------|
| Win probability | Accuracy | 69.1% |
| Win probability | Brier | 0.203 |
| Player props (pts) | MAE | 0.308 |
| Player props (all 7) | R² | >0.93 |
| xFG v1 | Brier | 0.226 |
| DNP predictor | AUC | 0.979 |
| Matchup model | R² | 0.796 |

---

## Session Log

- [[Sessions/Session-2026-03-24]]
- Full history in `vault/Sessions/`

---

## Key Decisions

- **2026-03-17:** Full system vision designed — simulator + AI chat + analytics dashboard → [[01 - System Architecture]]
- **2026-03-17:** 90-model architecture in 6 tiers, 96 analytics metrics, Claude AI chat with render_chart → [[02 - Model Catalog]]
- **2026-03-18:** All Phase 3.5 data fetched (hustle, on/off, matchups, synergy, BBRef, contracts) → [[03 - Data Sources]]
- **2026-03-20:** Prop model stack (Ridge meta) + betting portfolio (Kelly + CLV) + backtester built → [[02 - Model Catalog]]
