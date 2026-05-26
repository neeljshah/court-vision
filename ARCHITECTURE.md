# CourtVision — System Architecture

> Technical shape of the platform. For strategy: [VISION.md](VISION.md). For build sequence: [ROADMAP.md](ROADMAP.md).
> See also: [docs/architecture/system-overview.md](docs/architecture/system-overview.md) for full system descriptions.

---

## The Six Core Systems

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BROADCAST VIDEO                             │
│              (29 usable / 75 attempted → 80 CLEAN target)           │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CV PIPELINE [LIVE]                             │
│  src/tracking/ + src/pipeline/                                      │
│  YOLOv8n → SIFT homography → Kalman+Hungarian → OSNet re-ID        │
│  Output: defender_distance, spacing_score, legs_fatigue, events     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ (CV spatial features)
        ┌───────────────────┤
        │ (NBA API features)│
        ▼                   ▼
┌───────────────────────────────────────────────────────────────────┐
│            SYSTEM 1: POSSESSION SIMULATOR [PLANNED]               │
│   Lineup-dependent transition matrices + 10K Monte Carlo paths    │
│   Output: P(stat > X) for every player, every stat, any X        │
└───────────────────────────┬───────────────────────────────────────┘
                            │ (full distributions)
        ┌───────────────────┴────────────────────┐
        ▼                                        ▼
┌────────────────────────┐          ┌───────────────────────────────┐
│ SYSTEM 2: LINE         │          │ SYSTEM 3: CORRELATION ENGINE  │
│ EVALUATOR [SCAFFOLDED] │          │ [SCAFFOLDED]                  │
│ devig.py exists;       │          │ kelly_corr not yet populated; │
│ live pipeline pending  │          │ Ledoit-Wolf code exists       │
└───────────┬────────────┘          └──────────────┬────────────────┘
            └──────────────┬───────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                  SYSTEM 4: KELLY SIZER [LIVE]                    │
│   Fractional Kelly (0.25-0.5) + Ledoit-Wolf shrinkage on corr   │
│   Drawdown circuit breakers • betting_portfolio.py               │
└──────────────────────────┬───────────────────────────────────────┘
                           │ (sized bets)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                 SYSTEM 5: EXECUTION ROUTER [PLANNED]             │
│   DK, FD, BetMGM, Caesars, bet365, Fanatics, Novig, Kalshi      │
│   api/execution_router.py + src/execution/                       │
└──────────────────────────────────────────────────────────────────┘

  SYSTEM 6: AGENTIC RESEARCH SYSTEM [PLANNED]
  Multi-agent Claude loop: Orchestrator → Researcher → Engineer
  → Validator → Risk Manager → Retirement Monitor
  Autonomously discovers, validates, ships, and retires signals.
```

---

## Component Status

| Component | File(s) | Status |
|-----------|---------|--------|
| YOLOv8n detection | `src/tracking/advanced_tracker.py` | ✅ [LIVE] |
| SIFT homography | `src/pipeline/unified_pipeline.py` | ✅ [LIVE] |
| Kalman+Hungarian tracking | `src/tracking/advanced_tracker.py` | ✅ [LIVE] |
| OSNet re-ID (512-dim) | `src/tracking/osnet_reid.py` | ✅ [LIVE] |
| HSV team classification | `src/tracking/color_reid.py` | ✅ [LIVE] |
| EasyOCR jersey reading | `src/pipeline/unified_pipeline.py` | ✅ [LIVE] |
| EventDetector | `src/pipeline/unified_pipeline.py` | ✅ [LIVE] |
| Ball detection/tracking | `src/tracking/ball_detect_track.py` | 🟡 [LIVE] bug: ball_valid_pct=0% some games |
| Feature engineering (60+ features) | `src/features/feature_engineering.py` | ✅ [LIVE] |
| 7 prop models (q50 quantile heads + multitask MLP) | `src/prediction/player_props.py`, `prop_quantiles.py`, `multitask_props.py` | ✅ [LIVE] walk-forward validated (MAE: pts 4.62, reb 1.90, ast 1.36, fg3m 0.89, tov 0.89, stl 0.72, blk 0.44) |
| Residual heads (pregame + period-specific) | `src/prediction/residual_heads.py`, `multitask_residual_head.py` | ✅ [LIVE] 6/7 stats SHIP pregame; endQ1+endQ2 wired into `live_engine` |
| Live engine + in-play projection | `src/prediction/live_engine.py` | ✅ [LIVE] endQ1/endQ2/endQ3 snapshots; 7/7 stats win vs pregame at endQ3 |
| Live quantile bands | `src/prediction/live_quantile_bands.py` | ✅ [LIVE] 80% empirical coverage on in-play projections |
| Learned Q4 minute trajectory | `src/prediction/minute_trajectory.py` | ✅ [LIVE] endQ3 head: PTS -0.2312 MAE |
| Overtime probability | `src/prediction/overtime_probability.py` | ✅ [LIVE] |
| Win probability (5-way NNLS stack) | `src/prediction/win_probability.py` | ✅ [LIVE] 0.7094 acc / 0.193 Brier (walk-forward), 0.717 / 0.188 (single-split) |
| Quantile interval calibration | `src/prediction/quantile_calibration.py` | ✅ [LIVE] 80% target coverage |
| Betting backtest harness | `scripts/betting_backtest*.py` | ✅ [LIVE] 19,964-game holdout, +20-28% ROI @ +0.5 edge |
| xFG model | `src/prediction/` | ✅ [LIVE] Brier 0.226 on 221K shots |
| DNP predictor | `src/prediction/` | ✅ [LIVE] AUC 0.979 |
| Matchup model | `src/prediction/` | ✅ [LIVE] |
| Fractional Kelly sizing | `src/prediction/betting_portfolio.py` | ✅ [LIVE] |
| Shin devig | `src/prediction/devig.py` | ✅ [LIVE] |
| Risk guards | `src/prediction/risk_guards.py` | ✅ [LIVE] |
| Ingest queue (SQLite) | `src/ingest/` | ✅ [LIVE] |
| FastAPI serving | `api/main.py` | ✅ [LIVE] 6 endpoints + 5 routers |
| Temporal CV harness | `src/prediction/prop_backtester.py` | ✅ [LIVE] walk-forward, 48-hr purge |
| Model registry | `data/models/model_registry.json` | ✅ [LIVE] 85 models registered |
| Regression test suite | `tests/` | ✅ [LIVE] 1040 passing |
| CLV tracker | `src/prediction/betting_portfolio.py` | 🟡 [SCAFFOLDED] Gate 1 not run |
| Line evaluator | `src/prediction/devig.py` + analytics | 🟡 [SCAFFOLDED] live pipeline pending |
| Correlation engine | `src/prediction/betting_portfolio.py` | 🟡 [SCAFFOLDED] kelly_corr not populated |
| PostgreSQL schema | `database/schema.sql` | 🟡 Schema ready, migration pending |
| Possession simulator (Monte Carlo) | — | 🔲 [PLANNED] |
| Execution router | `api/execution_router.py` (stub) | 🔲 [PLANNED] |
| Book adapters (DK/FD/BetMGM/Novig) | `src/execution/` (stub) | 🔲 [PLANNED] |
| P2P exchange integration | — | 🔲 [PLANNED] |
| Nightly calibration loop | — | 🔲 [PLANNED] |
| Agentic research system | — | 🔲 [PLANNED] |

---

## Data Flow (Detailed)

```
Broadcast Video (.mp4)
    │
    ▼
unified_pipeline.py
    ├─ advanced_tracker.py → player detections (bbox, class, conf)
    ├─ SIFT homography → court coordinates (feet, 94×50 plane)
    ├─ osnet_reid.py → player identity (512-dim embedding)
    ├─ color_reid.py → team classification (HSV clusters)
    ├─ ball_detect_track.py → ball position + possession
    ├─ EasyOCR → jersey numbers + game clock
    └─ EventDetector → shot/pass/dribble/screen/rebound/foul events
    │
    ▼
tracking_data.csv + events.json
    │
    ▼
feature_engineering.py
    ├─ CV spatial features: defender_distance, spacing_score, fatigue_index
    ├─ CV temporal: rolling shots/passes/dribbles over 5/10/20-frame windows
    ├─ NBA API features: pace, team total, lineup on/off, ref, altitude, travel
    └─ Market features: Pinnacle no-vig, line velocity, steam flag
    │
    ▼
Model Stack (85 models)
    ├─ Tier 1: Win prob, 7 prop models, game total, spread, pace, blowout
    ├─ Tier 2: xFG (Brier 0.226), shot zones, xPTS
    ├─ Tier 2B: DNP predictor (AUC 0.979), load management, injury return
    ├─ Tier 3-4: gated on 80+ CV games (retrain pending)
    └─ Meta-model: Ridge on stacked outputs
    │
    ▼
betting_portfolio.py
    ├─ Shin devig → implied probabilities
    ├─ Kelly fraction (0.25-0.5) × model confidence tier
    ├─ Ledoit-Wolf shrinkage on 7×7 residual covariance
    └─ CLV tracker → vs Pinnacle close
    │
    ▼
FastAPI (api/main.py)
    └─ ~49 endpoints across 7 routers (main, predictions, models, analytics, dashboard, execution, stitch)
```

---

## Integration Points

| System | Where it connects | Current state |
|--------|------------------|---------------|
| NBA API | `src/data/nba_api_collector.py` | ✅ 569 gamelogs, 221K shots, 3.6K PBP |
| The Odds API | `src/data/odds_collector.py` | ✅ Live lines 6 books |
| Pinnacle (CLV) | `src/prediction/betting_portfolio.py` | 🟡 Scaffolded, Gate 1 pending |
| Injury feeds | `src/data/injury_collector.py` | ✅ ESPN + NBA official |
| RunPod (CV compute) | `scripts/launch_multigpu.sh` | ✅ Operational |
| B2 storage | `scripts/sync_remote.py` | ✅ Syncing |
| PostgreSQL | `database/schema.sql` | 🟡 Schema ready, migration pending |

---

## Module Ownership Map

| Concern | Owner file |
|---------|-----------|
| Pipeline orchestration | `src/pipeline/unified_pipeline.py` |
| Player tracking | `src/tracking/advanced_tracker.py` |
| Ball tracking | `src/tracking/ball_detect_track.py` |
| Team color re-ID | `src/tracking/color_reid.py` |
| Identity re-ID (deep) | `src/tracking/osnet_reid.py` |
| Feature engineering | `src/features/feature_engineering.py` |
| Prop models | `src/prediction/player_props.py` |
| Win probability | `src/prediction/win_probability.py` |
| Kelly + CLV | `src/prediction/betting_portfolio.py` |
| Devig | `src/prediction/devig.py` |
| Backtesting | `src/prediction/prop_backtester.py` |
| Risk guards | `src/prediction/risk_guards.py` |
| API serving | `api/main.py` |
| Ingest queue | `src/ingest/` |
| Batch runner | `scripts/batch_season.py` |

---

## Key Invariants

- `_VRAM_FLUSH_INTERVAL` in `unified_pipeline.py` must be **3000** (not 100 — causes OOM crashes)
- Panorama SIFT ratio: 3-10 (not default 2.0 — broadcast frames break at default)
- OMP thread cap: set before any YOLO call (`OMP_NUM_THREADS=4`)
- Never run: `run.py`, `loop_processor.py`
- Video: always headless (`--no-show`), never `cv2.imshow`
- PostgreSQL and CV clusters are isolated — never mix in same process

---

| Live engine + residual heads | `src/prediction/live_engine.py`, `residual_heads.py`, `multitask_residual_head.py` |
| Live quantile bands | `src/prediction/live_quantile_bands.py` |
| Minute trajectory (Q4) | `src/prediction/minute_trajectory.py` |
| Daily ops chain | `scripts/daily_run.py`, `predict_player.py`, `predict_slate.py`, `compare_to_lines.py` |
| Live data feeds | `scripts/fetch_live_prop_lines.py`, `fetch_dk_props.py`, `update_inactives.py` |
| Health check | `scripts/health_check.py` |

*Related: [VISION.md](VISION.md) · [ROADMAP.md](ROADMAP.md) · [docs/architecture/system-overview.md](docs/architecture/system-overview.md) · [docs/CLAUDE-state.md](docs/CLAUDE-state.md) · [CHANGELOG.md](CHANGELOG.md)*

---
*Last verified: 2026-05-25*
