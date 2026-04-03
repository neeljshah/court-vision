# Roadmap — CourtVision Build Plan

*Synced from `.planning/ROADMAP.md` — see that file for full task-level detail.*
*Last updated: 2026-03-26*

---

## Phase Status

| Phase | Name                                | Status      |
| ----- | ----------------------------------- | ----------- |
| 1     | Data Infrastructure                 | ✅ Done      |
| 2     | CV Tracker Bug Fixes                | ✅ Done      |
| 2.5   | CV Tracker Quality Upgrades         | 🟡 Partial  |
| 3     | NBA API Data Maximization           | ✅ Done      |
| 3.5   | Expanded Data Collection            | 🟡 Partial  |
| 4     | Tier 1 ML Models                    | ✅ Done      |
| 4.5   | Betting + Lifecycle Models          | ✅ Done      |
| 4.6   | Untapped Signal Wiring              | ✅ Done      |
| 4.7   | Prediction Quality Stack            | ✅ Done      |
| 4.8   | Quantitative Betting Infrastructure | ✅ Done      |
| 4.9   | Backtesting + Validation            | ✅ Done      |
| 5     | External Factors                    | ✅ Done      |
| G     | Full Game Data Collection           | 🟡 Active   |
| 6     | Full Game Processing + Rich Events  | 🔲 **NEXT** |
| 7     | Tier 2-3 CV Models                  | 🔲          |
| 8     | Possession Simulator v1             | 🔲          |
| 9     | Feedback Loop + NLP                 | 🔲          |
| 10    | Tier 4-5 Volume Models              | 🔲          |
| 10.5  | Advanced CV Signals                 | 🔲          |
| 11    | Betting Infrastructure + Live       | 🔲          |
| 12    | Full Monte Carlo (90 models)        | 🔲          |
| 13    | FastAPI Backend                     | 🔲          |
| 14    | Analytics Dashboard                 | 🔲          |
| 15    | AI Chat Interface                   | 🔲          |
| 16    | Tier 6 + Live Win Prob LSTM         | 🔲          |
| 17    | Infrastructure + Deployment         | 🔲          |

---

## What's Built ✅

### Data
- PostgreSQL schema (9 tables, 2 views)
- 569/569 player gamelogs, 3 seasons
- 221,866 shot chart coordinates
- 3,102 play-by-play games (98.4% coverage)
- BBRef advanced stats (736 players), contracts (523), hustle, on/off, matchups, synergy
- Injury monitor, referee tracker, schedule context, lineup on/off

### CV Tracker
- YOLOv8n detection → SIFT homography → Kalman+Hungarian tracking
- **OSNet-x0.25 torchreid re-ID** (512-dim ImageNet pretrained) — wired 2026-03-25
- EasyOCR jersey number reader
- EventDetector (shot/pass/dribble/drive)
- ByteTrack always-on
- Ball detection (Hough + YOLO fine-tuned)
- 431 tests passing

### ML Models (46/90)
- **Win probability:** XGBoost, 69.1% acc, Brier 0.203
- **Props × 7:** pts/reb/ast/fg3m/stl/blk/tov — R² >0.93, MAE pts=0.308, 52 features
- **Prop meta-stack:** Ridge over all 7 props, confidence-gated
- **Game models × 5:** total, spread, blowout, first-half, pace
- **xFG v1:** Brier 0.226, 221K shots (location + context)
- **DNP predictor:** AUC 0.979 — zeroes props when P(DNP) ≥ 0.4
- **Matchup model:** R² 0.796
- **Phase 4.5–4.9 specialist × 29:** load management, injury risk/return, breakout, public fade, soft book lag, age curve, altitude, B2B, contested rate, foul trouble, garbage time, home/away, line movement, minutes floor, OT probability, plus/minus, rotation, shot clock pressure, shot type, substitution timing, travel impact, true shooting, usage rate, clutch lineup, beneficiary cascade, contested shot predictor, rest day, referee

### Infrastructure
- FastAPI backend — 10 endpoints (`api/main.py`)
- `predictions_router.py` — injury-risk, breakout, lineup-optimizer, today, props endpoints
- Kelly + CLV + arb detection (`betting_portfolio.py`)
- Prop backtester + paper trading (`prop_backtester.py`)
- Daily pipeline (`scripts/daily_pipeline.py`)

---

## What's In Progress 🟡

### Phase G — Full Game Data Collection
**Status: 4/20 clean games** (Session 24 audit — 2026-03-26)

| Game | Rows | Audit | Issue |
|------|------|-------|-------|
| 0022400430 | 194,950 | 6/6 ✅ | Shot OD, poss frag, x_norm OOB 34% |
| 0022400537 | 280,045 | 6/6 ✅ | Shot OD, poss frag, x_norm OOB 34% |
| 0022400909 | 362,799 | 6/6 ✅ | Shot OD, poss frag |
| 0022401123 | 805,523 | 6/6 ✅ | Shot OD, poss frag, player_name blank |
| 0022401156 | 832,908 | 5/6 ❌ | Enrichment 52% (PBP window mismatch) |
| 0022400625 | 3,745 | 1/6 ❌ | Tracking only, needs reprocess |
| 0022400687 | 6,052 | 1/6 ❌ | Tracking only, needs reprocess |
| 0022400710 | 10,607 | 1/6 ❌ | Homography 5.7% — bad source video |
| 11 others | — | 0/6 ❌ | Not yet processed |

**Known data quality issues in clean games (require reprocess to fix):**
- Shot count 4–14× inflated (264–850 per game vs expected 60–120)
- Possession duration 0.4–0.9s median (expected ~14s) — fragmentation
- Court coordinates OOB on 34% of rows in 2 games
- team_abbrev = UNK (no color map)
- player_name blank in some shot_logs

**Next:** Run pipeline on 10 unprocessed games, reprocess 2 partials, get new video for 0022400710

### Phase 2.5 — CV Tracker Upgrades (partial)
- ✅ 025-01: Broadcast detection mode (conf 0.35)
- ✅ 025-02: Jersey OCR brightness normalization
- ✅ 025-03: Broadcast detection + OCR tests
- 🔲 025-04: `court_detector.py` per-clip homography
- 🔲 025-05: Wire homography into unified_pipeline
- 🔲 025-06: court_detector tests
- 🔲 **025-07: YOLOv8-pose ankle keypoints (HIGHEST ROI — MUST complete before Phase 6)**

### Phase 3.5 — Data Gaps
- 🔲 The Odds API — live closing lines (critical for real CLV)
- 🔲 ProSportsTransactions — historical injury data for NLP training
- 🔲 BBRef 6+ season gamelogs (currently 3 seasons)
- 🔲 Full injury history per player

---

## What's Not Built Yet 🔲

### Immediate next (before Phase 6)
1. **025-07 — YOLOv8-pose ankle keypoints** — position error ±18" → ±4"
2. **025-04/05/06 — Per-clip homography** — fixes systematic court coordinate error
3. **PostgreSQL write wiring** (ISSUE-021) — Stage 2 enrichment data not persisting to DB

### Phase 6 (20 games)
- Rich event aggregation: drives, box-outs, closeouts, cuts, screens
- Shot log enrichment with all CV spatial features
- Auto-PostgreSQL write after each game

### Phases 7–12 (ML + Simulator)
- xFG v2 — with actual defender distance from CV
- Props retrained with CV behavioral features (spacing, drive frequency, open shot rate)
- Possession simulator — 7-model chain, 10K Monte Carlo
- Feedback loop — nightly processing + auto-retrain at 20/50/100 game milestones
- Full 90-model Monte Carlo stack

### Phases 13–15 (Product)
- FastAPI backend — 12 endpoints, Redis caching
- Analytics dashboard — Next.js + D3 (shot charts, spacing, win prob, lineup matrix)
- AI chat — Claude API + tool use + render_chart inline

### Phases 16–17 (Scale)
- Live win probability (LSTM, WebSocket real-time)
- Docker + CI/CD + cloud GPU + drift monitoring

---

## Key Blockers (Priority Order)

| # | Blocker | Unlocks |
|---|---------|---------|
| 1 | 025-07 pose estimation + 025-04 homography | Phase 6 data quality |
| 2 | 20 clean games | Phase 7 — xFG v2, CV-enriched props |
| 3 | PostgreSQL write wiring | Data persistence, auto-retrain |
| 4 | The Odds API live lines | Real CLV tracking vs proxy |
| 5 | Phase 6 complete | Phase 8 — Possession Simulator |
| 6 | Possession Simulator | Phase 11 — Betting dashboard live |
| 7 | FastAPI + Dashboard | Usable product |
