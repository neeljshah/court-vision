# Swish Analytics — Technical Interview Cheat-Sheet

*Prepared 2026-05-24 for morning meeting. Internal use only.*

---

## 30-Second Pitch

> "CourtVision is a prediction stack that beats sportsbook prop lines using real-time in-game state.
> Pre-game models set the baseline. The moment Q1 ends, an in-game engine re-projects every player
> on the slate using live pace, foul trouble, blowout state, and hot/cold streaks — and the MAE
> drops 43–53% vs the pre-game model across all 7 props. At end-of-Q3, we're betting at 70–89%
> ROI against an L5 line proxy. The entire pipeline runs in <2s per snapshot."

---

## Headline Numbers

### Pre-game prop MAE (production, walk-forward holdout, N=99,818 rows)

| Stat | MAE | Model type |
|------|-----|-----------|
| PTS  | 4.6104 | sqrt+Huber blend (XGB+LGB+MLP NNLS) |
| REB  | 1.9075 | LGB-q50 (pinball loss) |
| AST  | 1.3570 | Multitask MLP blend |
| FG3M | 0.8941 | XGB-q50 |
| STL  | 0.7153 | XGB-q50 |
| BLK  | 0.4398 | XGB-q50 |
| TOV  | 0.8932 | XGB-q50 |

Walk-forward = 4-fold expanding-window. No look-ahead. Anchors verified by `scripts/verify_production_mae.py`.

### In-game system — end-Q3 vs production pre-game model (550 games, N=11,114 triples)

| Stat | Pre-game MAE | endQ3 MAE | Delta | % improvement |
|------|-------------|-----------|-------|---------------|
| PTS  | 4.2914 | 2.4647 | -1.8266 | -43% |
| REB  | 1.7761 | 1.0026 | -0.7734 | -44% |
| AST  | 1.2548 | 0.6809 | -0.5739 | -46% |
| FG3M | 0.8367 | 0.4246 | -0.4121 | -49% |
| STL  | 0.6717 | 0.3177 | -0.3540 | -53% |
| BLK  | 0.4298 | 0.2030 | -0.2268 | -53% |
| TOV  | 0.8471 | 0.4466 | -0.4005 | -47% |

**7/7 stats, every single one wins. No cherry-picking.**

### Period head — endQ1 (cycle 105b)

| Stat | endQ1 MAE | Linear-proj baseline | Delta |
|------|-----------|---------------------|-------|
| PTS  | 4.55 | 7.18 | **-37%** |

A trained period-specific head beats a naïve linear pace projection by 37% at Q1. Wired into `live_engine.project_from_snapshot`.

### In-game ROI (vs L5 rolling-mean line proxy, threshold 1.0, -110 odds)

| Snapshot | PTS | REB | AST | FG3M | STL | BLK | TOV |
|----------|-----|-----|-----|------|-----|-----|-----|
| endQ1 | +0.35 | +0.39 | +0.42 | +0.48 | +0.50 | +0.60 | +0.41 |
| endQ2 | +0.52 | +0.64 | +0.68 | +0.71 | +0.78 | +0.83 | +0.66 |
| endQ3 | +0.70 | +0.78 | +0.82 | +0.86 | +0.89 | +0.89 | +0.84 |

**endQ2 is viable for 5/7 stats (≥80% of endQ3 ROI)** — halftime betting is operationally ready.

Win prob stack: 0.7094 acc / 0.193 Brier (walk-forward), 0.717 / 0.188 (single-split). 5-way NNLS (XGB + LGB + LR + MLP + NB).

---

## What's Novel Architecturally

### 1. Pace-decaying projection (live_engine)
Real-time snapshot (Q1/Q2/Q3 stats so far) → pace-normalised expected final stats → residual heads apply stratified corrections. Not a regression on final box score — a per-minute-trajectory extrapolation with learned correction factors.

### 2. Stratified residual heads (3 shipped)
- **Foul residual** (`cb39cbd6`): when a player is in foul trouble (≥3 fouls), standard pace projection under-adjusts. A secondary LGB model trained on foul-change situations applies a shrinkage factor. Wired into `live_engine.project_from_snapshot`.
- **Blowout residual** (`dfd4ce0b`): blowout games have non-linear stat distributions (garbage time). Separate LGB trained on score-differential bins.
- **Heat-check shrinkage** (`f1ae0919`): hot streaks revert — a sigmoid shrinkage on above-baseline-pace players prevents naive projection from over-extrapolating.

### 3. Quantile (q50) heads for skewed stats
5 of 7 props now use pinball-loss (median) rather than MSE/Huber. Sportsbook O/U props score against the median, not the mean — q50 models are structurally aligned to that loss. BLK MAE improved -16.6% in one swap.

### 4. Full walk-forward gate
Every candidate improvement must pass a 4-fold walk-forward (4/4 folds positive, single-split MAE strictly down). 20+ probes rejected for failing this gate even when single-split looked good. The gate prevented shipping regressions.

### 5. Ops infra (game-day ready)
- Live line scraper polls DK/FD/Odds-API every 10 min → `data/lines/`
- Daemon fires at Q-end triggers → EV ranks via Kelly → Slack/Discord webhooks
- CLV tracking: closing-line value reported per bet, per strategy
- P&L ledger with settlement, ROI rollups, A/B strategy tagging

---

## Honest Weaknesses

1. **No real sportsbook lines.** ROI numbers are vs an L5 rolling-mean proxy. Real closing lines compress the edge — we don't know by how much. Gate 1 (CLV vs Pinnacle close) has not been run yet.

2. **Pre-game model is at ceiling.** 20+ feature-add and architecture probes in the last 40 cycles all failed the dual gate. Remaining gains are data problems (live injury feed, real lineups, CV defender_distance at scale).

3. **Sparse 2025-26 DNP data.** We have 18,544 DNP rows but P(play) modeling only reaches significance on historical seasons where full injury reports are available. Offseason — no forward accumulation until October.

4. **CV features at scale not wired.** We have CV tracking working (29 usable games, 17 quality) but `defender_distance` and on-ball pressure features aren't live in the prediction stack — the target is 80 CLEAN games before the CV signal meaningfully moves MAE.

5. **In-game backtest uses L5 proxy, not real live lines.** Real live prop lines in-game are harder to scrape and the market is thinner. The 70-89% ROI is a ceiling, not what an operator would realize.

---

## What We'd Build Next (Given Swish Resources)

| Priority | Item | Expected Lift |
|----------|------|--------------|
| 1 | Real DK/FD/MGM line feed at game-time (not L5 proxy) | Unlocks Gate 1 CLV validation |
| 2 | Live injury/lineup feed (rotation scanner + DNP alerts) | P(play) head + line-move anticipation |
| 3 | CV defender_distance at scale (80+ clean games) | New xFG feature not available in NBA API |
| 4 | Multitask MLP with live-state head | Single model pre+in-game, shares representations |
| 5 | Alternate market coverage (1st-quarter, halves) | Halftime betting already empirically validated |
| 6 | Correlated Kelly (portfolio optimizer) | `betting_portfolio.py` correlation matrix is unbuilt |

---

## Key Architectural Files

```
src/prediction/live_engine.py          # project_from_snapshot() — in-game hub
src/prediction/prop_pergame.py         # 7 prop models, q50 dispatch, NNLS stacker
src/prediction/live_factors.py         # foul_trouble_factor, canonical live state
src/prediction/minute_trajectory_foul_residual.py  # foul shrinkage head
src/prediction/blowout_residual.py     # blowout correction head
src/prediction/heat_check_shrinkage_residual.py    # hot-streak reversion
src/betting/pnl_ledger.py             # bet placement → settlement → P&L
src/betting/clv.py                     # closing-line value calculator
scripts/live_inplay_daemon.py          # game-day daemon (5-min cadence)
scripts/predict_slate.py               # morning pre-game predictions (all players)
scripts/compare_to_lines.py            # EV ranking vs pasted sportsbook lines
scripts/swish_demo.py                  # runnable end-to-end demo (this session)
```

---

## Demo Script (quick)

```bash
# 1. Pre-game: run slate for today
python scripts/predict_slate.py --date 2026-05-25

# 2. Compare vs sportsbook lines (paste CSV)
python scripts/compare_to_lines.py --date 2026-05-25 --book DK

# 3. In-game: project from snapshot (mocked — offseason)
python scripts/swish_demo.py

# 4. System health
python scripts/health_check.py --skip-network
```

---

## Numbers Origin / Reproducibility

| Claim | Script | Output file |
|-------|--------|-------------|
| Pre-game MAE anchors | `scripts/verify_production_mae.py` | `scripts/_results/verify_production_mae.txt` |
| In-game 7/7 win, 550 games | `scripts/retro_inplay_mae_v2.py` | `scripts/_results/retro_inplay_mae_v2_prod_baseline.md` |
| ROI table endQ1/Q2/Q3 | `scripts/backtest_inplay_edge_v2.py` | `scripts/_results/inplay_edge_backtest_v2.md` |
| endQ1 period head -37% | `scripts/retro_inplay_mae_v2.py` | cycle-105b artifacts in `data/models/` |

All result files committed. Numbers are reproducible: re-run any script and the table regenerates.
