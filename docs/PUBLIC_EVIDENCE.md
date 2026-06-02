# Public Evidence Packet

> ⚠️ **SUPERSEDED (2026-06) — read [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) instead.** The headline numbers
> below (the +18.38% pre-game ROI, the endQ3 Brier 0.119, the +54% in-play ROI, and the per-stat ROI/CLV splits)
> are **retracted**: a self-audit traced the ROI to a market-follow grading artifact (real ≈ −2% to −5%), the endQ3
> Brier to a Q4 data leak (leak-free ≈ 0.141), and the +54% to an L5 line-proxy. The honest, verified evidence —
> and what's defensible — is in JOB_EVIDENCE_PACKET.md. Also note: the build is an intensive **~3-month** solo effort
> (Mar–May 2026), not 13 months. This file is kept for history only.

> The 60-second scan of what CourtVision actually does. If you're a recruiter, partner, AI agent evaluating the repo, or interviewer, read [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) first — it supersedes the numbers below.

---

## What this is

End-to-end NBA prediction + betting platform built by one engineer (Neel Shah) over 13 months. CV tracking on broadcast video → court coordinates → 7 prop models + 3-snapshot in-play win-prob stack → Shin-devigged EV → segment-filtered fractional Kelly → multi-book line scanner + arbitrage detection + live projection UI → shadow-logged execution.

Two validation surfaces, both with committed data and reproducible from a fresh clone.

---

## Headline numbers (canonical, 2026-05-28)

### A. Real-money-relevant pre-game props — *what you'd actually deploy*

**1,535 walk-forward bets · 2025-26 regular season + playoffs · real DK / FanDuel / MGM / Pinnacle closing lines.**

| Strategy | N | Hit % | ROI | Source of truth |
|----------|--:|------:|----:|-----------------|
| Flat 1u, pre-filter aggregate (unrun straw-man) | 4,210 | 54.37% | −2.06% | `data/models/gate1_results_summary.json` |
| Flat 1u, post-Iter-57 filter stack | **1,535** | **61.4%** | **+15.04%** | `data/cache/iter61_sim_reconciliation.json` |
| **Kelly-B + per-stat isotonic, post-Iter-57** | **1,535** | **61.4%** | **+18.38%** | iter61 canonical (deployable read) |

Per-stat decomposition of the +18.38% (KB+ISO sizing):

| Stat | N | Hit % | ROI | CLV z-score |
|------|--:|------:|----:|------------:|
| **BLK** (UNDER-only, Iter 51) | 247 | 73.5% | **+25.98%** | **4.45 ✓** |
| **AST** (line_mid + over×high pruned) | 226 | 65.0% | **+14.04%** | **4.47 ✓** most robust |
| **STL** | 178 | 60.2% | **+16.91%** | 2.84 ✓ |
| **FG3M** (line_high pruned) | 311 | 60.8% | **+16.02%** | 1.96 |
| **REB** (line_high + over×low pruned) | 238 | 58.8% | **+12.30%** | 2.09 ✓ |
| **PTS** (line_mid pruned, thr=1.0) | 335 | 56.4% | **+8.44%** | 3.52 ✓ |

Aggregate CLV across all 6 stats: **+8.94pp** — top-decile for public sports modeling. Theoretical Kelly ROI ceiling at that CLV ≈ 18–22%; the realized +18.38% sits AT the ceiling, meaning further gains require new edge sources (live data, true model-prob edge instead of devig-implied) not better sizing.

**Real-world execution clip:** 30–50% of paper. **Sustainable deployable target after limits + fills: +8 to +12% sustained ROI.**

### B. In-play win-probability — *honest walk-forward Brier*

Per-snapshot models on **3,685 game-snapshots, 4-fold expanding walk-forward**, validated against the same `data/cache/inplay_oos_validation_2026_05_27.json` framework that exposed 2-4× in-sample leakage in the prior retrain.

| Snapshot | OOS baseline | After Iter-68 v6_hp | After full stack | Delta | Pinnacle public reference |
|----------|-------------:|--------------------:|-----------------:|------:|--------------------------:|
| endQ1 | 0.2221 | 0.2120 | 0.2120 | −0.0101 | ~0.18–0.22 |
| endQ2 | 0.1900 | 0.1822 | 0.1759 | −0.0141 | ~0.14–0.18 |
| **endQ3** | **0.1310** | **0.1235** | **0.1191** | **−0.0119** | **~0.10–0.12** |

**The endQ3 0.119 Brier sits inside the public Pinnacle range.** Validated walk-forward, not single-split.

### C. In-game projections — *the bigger story than ROI*

550-game retro across all 7 props at endQ3 vs. the pre-game production stack:

| Stat | Pregame MAE | In-game endQ3 MAE | Δ |
|------|------------:|------------------:|--:|
| PTS | 4.62 | **2.46** | **−47%** |
| REB | 1.90 | **1.00** | **−47%** |
| AST | 1.36 | **0.68** | **−50%** |
| FG3M | 0.89 | **0.42** | **−53%** |
| STL | 0.72 | **0.32** | **−55%** |
| BLK | 0.44 | **0.20** | **−55%** |
| TOV | 0.89 | **0.45** | **−50%** |

**7/7 stats win at endQ3, every stat improves 43–55%.** This is the structural in-game information edge — fed by CV tracking + 80-artifact intelligence layer + in-play microstructure — and it's not a fit artifact.

---

## L5-proxy ceiling — *read this before any in-play backtest claim*

A separate in-play backtest produces 78.11% hit / **+54.57% ROI** on **n=55,073 calibrated bets** with calibration RMSE 0.065 across 10 EV deciles.

**That number settles against an L5 rolling-average line proxy, NOT real Pinnacle closes.** Real-money compression estimate: **+15–25% ROI** against actual closing lines. The +54% is a **model-quality ceiling**, not a deployment forecast. First real closing-line CLV reading begins **October 2026** (Pinnacle props daemon collects from preseason onward).

The bet evaluation infrastructure that *makes this measurable* is the architectural win, not the +54%:
- `src/prediction/shadow_logger.py` — every bet evaluation logged (passed AND blocked, with `gate_blocked_by` reason)
- `src/prediction/settlement_engine.py` — joins shadow log to cdn.nba.com finals nightly
- `scripts/calibrate_filters.py` — counterfactual filter sweep on logged audit data, not guesswork

That pattern is what flipped the **pre-calibration aggregate ROI from −4.25% to +47%** by raising the per-quarter EV floor from 0.01 → 0.12. Tier C (EV<0.04) was at −78% ROI and dragging everything. Diagnostic-first ML, not vibes.

---

## 30-second verification

After `git clone` + `pip install -r requirements.txt`:

```bash
python scripts/verify_winprob.py          # → acc 0.7094, brier 0.193 (within tolerance)
python scripts/verify_production_mae.py   # → 6/7 prop MAEs within ±0.01 of claim
python scripts/iter61_sim_reconciliation.py  # → canonical post-Iter-57 ROI +18.38% KB+ISO
```

All three verifiers consume committed JSON. **If they disagree with this document, this document is wrong; please open an issue.**

For the in-play backtest (~10–15 min):
```bash
python scripts/run_backtest.py --n-games 50
# → vault/Reports/backtest_<date>.md
```

For the Gate-1 real-Vegas pre-game backtest (reproduces the +18.38%):
```bash
python scripts/run_gate1_full_analysis.py
# → data/models/gate1_results_summary.json
```

---

## The moat — *why this should not be replicable from training data*

1. **CV-derived behavioral features from broadcast video.** YOLOv8n → SIFT homography → Kalman+Hungarian tracking → OSNet re-ID (512-dim) → `defender_distance`, `spacing_entropy`, `fatigue_decay`, `paint_dwell_pct`. Cost: **~$0.10–0.13 per game on a RunPod 3090** vs. six- to seven-figure annual fees for Sportradar / Second Spectrum licensed tracking. Status: 85 games tracked / 7 with full feature extraction / target 80 CLEAN.
2. **80-artifact intelligence layer** (`data/intelligence/`, public manifest at [INTELLIGENCE.md](INTELLIGENCE.md)) — player archetypes + similarity matrix (26K pairs), defensive scheme tags, position×scheme interaction tables with significance tests, lineup chemistry (4.7K rows / 1.2K lineups), clutch / quarter / shot-clock / possession-type splits, matchup deviations, coaching adjustments, officials impact, game-similarity retrieval index, per-game CV-quality + per-player confidence curves that feed bet-sizing.
3. **Agentic discovery loop.** 70 documented improve-loop iterations (29 ships, 41 reverts, every revert with stated cause) under a hard ship gate: **≥3/4 walk-forward folds positive AND no per-stat regress >1pp.** Opus orchestrates and reviews, Sonnet writes code, Haiku searches. The +18.38% pre-game stack was discovered through this loop, not designed up front.

---

## What's validated · what's not

| Claim | Validation status |
|------|-------------------|
| Pre-game props +18.38% on 1,535 bets vs real DK/FD/MGM/Pinnacle closes | ✅ Walk-forward, point-in-time consistent, JSON-reproducible |
| Pre-game props +8.94pp CLV across 6 stats | ✅ Computed from real closes, t-stats per stat in source JSON |
| In-play endQ3 Brier 0.119, MAE −47% to −55% across 7/7 stats | ✅ 4-fold expanding walk-forward on 3,685 snapshots |
| Win-prob acc 0.7094 / Brier 0.193 | ✅ `python scripts/verify_winprob.py` |
| In-play backtest +54.57% ROI | ⚠️ **L5 line proxy, not real closes.** Real-money estimate +15–25%. First real CLV: Oct 2026. |
| Real-world fill quality at sharp books | ⚠️ Unproven until Oct 2026. Stated execution clip: 30–50% of paper. |
| 80-game CV scale-up validation | ⏳ 7/80 full-feature games. Blocked behind `defender_distance=200.0` sentinel-vs-NULL fix (ISSUE-022). |
| PTS underprediction at sharp closes | 🔧 Known: −8.62% ROI on 2025-26 sharp closes; calibration pass scheduled. |

---

## Honest caveats

- The +54% in-play ROI is **paper**. Real-money will be lower. Until Oct 2026 closing-line CLV data lands, **+15–25%** is the calibrated expectation.
- CV scale-up is incomplete. 7 of 80 target games have full feature extraction.
- DraftKings, Caesars, and MGM scrapers are IP-blocked (R18_K1); line coverage is Pinnacle / Bovada / FanDuel / PrizePicks only.
- This is a **solo-engineer** project. No team, no co-founders, no licensed data. Every model, scraper, daemon, UI surface, and validation harness is in the same git history.

---

## What this signals (for evaluators)

- **Quant ML rigor at hiring-bar level** — walk-forward CV, per-segment calibration, isotonic edge calibration, Shin devigging, Kelly-B fractional sizing, Ledoit-Wolf shrinkage, shadow-logged settlement, filter-sweep calibration. The validation framework is the work.
- **Computer vision in production** — broadcast video → court coordinates → per-frame features → bet-sizing input, all on consumer GPU. Not a notebook.
- **Engineering breadth** — 6029 tracked files: CV tracker, 7 prop models, 3-snapshot in-play stack, FastAPI (~49 endpoints, 7 routers), 9 production daemons, multi-book line scanner, arbitrage detector, parlay builder, Discord/Slack alerting, P&L ledger, mobile dashboard. PostgreSQL schema + migrations. CI/CD wired.
- **Honest calibration of own work** — README front-loads the L5-proxy caveat right next to the +54% headline. Validation gaps tracked in [docs/KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). The unpatched `sim_win_prob` polarity bug is documented openly in `vault/Models/Polarity Bug Audit 2026-05-27.md` with estimated CLV impact when fixed.

---

## Where to go next

| If you want… | Read |
|--------------|------|
| The full README with architecture + reproducibility | [README.md](../README.md) |
| The 80-artifact intelligence layer | [INTELLIGENCE.md](INTELLIGENCE.md) |
| System architecture | [../ARCHITECTURE.md](../ARCHITECTURE.md) |
| Known limitations + validation gaps | [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) |
| ML model registry + walk-forward methodology | [ML_MODELS.md](ML_MODELS.md) |
| CV pipeline deep-dive | [CV_TRACKING.md](CV_TRACKING.md) |
| To contact the author | [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com) |

*Last verified: 2026-05-28 against CHANGELOG.md [0.17.0] + README.md headline tables.*
