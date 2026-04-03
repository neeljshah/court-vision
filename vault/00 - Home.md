# CourtVision — Knowledge Base Home
*Last updated: 2026-03-25*

---

## Quick Navigation

| Note | Description |
|------|-------------|
| [[01 - System Architecture]] | End-to-end architecture, data flow, component map |
| [[02 - Model Catalog]] | All 90 models, tiers, training status, performance |
| [[03 - Data Sources]] | Every data source, scraper, TTL, coverage stats |
| [[04 - Pipeline Flow]] | Step-by-step pipeline from video to edge flag |
| [[05 - Ideas and Future Work]] | Roadmap ideas, experiments, backlog |
| [[Roadmap]] | Phase-by-phase build plan with current status |
| [[Project Vision]] | Full product vision, architecture, competitive edge |

---

## Current Status

**Phase:** Pre-Phase 6 — collecting full-game CV data
**Active blocker:** CV tracker needs per-clip homography (025-04) + pose estimation (025-07) before Phase 6 processing begins
**Next action:** Reprocess 10 games → reach 13+ clean games → retrain xFG CV

### Phase Completion

| Phase | Status |
|-------|--------|
| 1 — Data Infrastructure | ✅ Done |
| 2 — Tracker Bug Fixes | ✅ Done |
| 2.5 — CV Tracker Upgrades | 🟡 Partial (025-04, 025-07 blocked) |
| 3 — NBA API Data Maximization | ✅ Done |
| 3.5 — Expanded Data Collection | 🟡 Partial |
| 4 — Tier 1 ML Models | ✅ Done |
| 4.5 — Betting + Lifecycle Models | ✅ Done |
| 4.6 — Untapped Signal Wiring | ✅ Done |
| 4.7 — Prediction Quality Stack | ✅ Done |
| 4.8 — Quantitative Betting Infra | ✅ Done |
| 4.9 — Backtesting + Validation | ✅ Done |
| 5 — External Factors | ✅ Done |
| Phase G — Full Game Collection | 🟡 Active |
| 6 — Full Game Processing | 🔲 Next |
| 7–17 | 🔲 Not started |

---

## Model Performance (46/90 Trained)

| Model | Metric | Value |
|-------|--------|-------|
| Win probability | Accuracy | 69.1% |
| Win probability | Brier | 0.203 |
| Player props (pts) | MAE | 0.308 |
| Player props (all 7) | R² | >0.93 |
| xFG v1 | Brier | 0.226 |
| DNP predictor | AUC | 0.979 |
| Matchup model | R² | 0.796 |
| Phase 4.5–4.9 specialist models | — | 23 models trained |

---

## CV Data Status

| Game | Status |
|------|--------|
| 0022400625 | ✅ Clean |
| 0022400710 | 🟡 Reprocessing |
| 0022400430, 0022400537, 0022400909, 0022401123, 0022401156 | 🟡 Needs defender_distance patch |
| 5 remaining games | 🟡 Reprocessing |
| **Target** | **20 clean games for Phase 6** |

---

## Open Issues

| Priority | Issue |
|----------|-------|
| 🔴 | Phase 6 blocked — need 025-04 (per-clip homography) + 025-07 (pose estimation) first |
| 🔴 | PostgreSQL writes not wired (ISSUE-021) |
| 🟡 | Ball detection 14.1% valid — fix applied, re-test pending (ISSUE-029) |
| 🟡 | 5 games have 200.0 defender_distance sentinel (ISSUE-022) — needs reprocess |
| 🟡 | Phase 3.5 data gaps: Odds API, ProSportsTransactions, full BBRef injury history |
| 🔴 | Analytics + tracking dashboards not built (Phase 14) |
| 🔴 | Frontend + AI chat not built (Phase 13–15) |

---

## Session Log

- Latest: [[Sessions/Session-2026-03-25]]
- Full history in `vault/Sessions/`

---

## Key Decisions

- **2026-03-17:** Full system vision — simulator + AI chat + analytics → [[01 - System Architecture]]
- **2026-03-17:** 90-model architecture, 6 tiers, 96 analytics metrics, Claude AI chat with render_chart → [[02 - Model Catalog]]
- **2026-03-18:** All Phase 3.5 advanced stats fetched (hustle, on/off, matchups, synergy, BBRef, contracts) → [[03 - Data Sources]]
- **2026-03-20:** Prop model stack (Ridge meta) + betting portfolio (Kelly + CLV) + backtester built → [[02 - Model Catalog]]
- **2026-03-25:** OSNet re-ID upgraded to ImageNet pretrained (512-dim); pipeline hardening — run_clip.py restored, defender_distance sentinels patched, team_spacing normalized → [[Improvements/Tracker Improvements Log]]
