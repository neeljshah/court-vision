# CourtVision — The Renaissance of Sports

> An AI-native sports intelligence platform where Claude-powered agents autonomously discover, validate, ship, and retire prediction signals across multiple monetization surfaces.

---

## The Structural Arbitrage

Sports prediction is sitting on a $200-500M/year extractable profit pool that institutional capital structurally cannot reach. Not because institutions lack the talent or data — but because the market architecture makes it physically impossible for them to operate at the scale that would justify their cost structure.

The per-game bet limit at every retail sportsbook is $25-500. The top quant firms need to deploy tens of millions of dollars to justify a desk. The math never worked — until now.

For a solo operator, the math inverts completely:

| Factor | Institutional firm | CourtVision |
|--------|-------------------|-------------|
| Team cost | $5-15M/year | ~$50-80/month compute |
| Account access | Blocked (books close professional entities) | 6+ simultaneous retail accounts |
| Bet limits | Must deploy $50M+ | $25-500/bet is fine at $10K bankroll |
| Regulatory burden | Registered funds can't hold DraftKings accounts | Individual — minimal |
| Research cost | PhD team, $3-5M/year | Claude agents, weeks not months |

The extractable pool exists because books price props primarily from box-score models — season averages, opponent defensive rating, recent trends. They do not have defender distance at shot release. They do not have spacing as a convex hull. They do not have fatigue curves derived from movement telemetry. CourtVision has all three, from free broadcast video, at $0.40/GPU hour.

That gap — between what the model sees and what the book priced — is the edge. It exists in every game, on dozens of markets. And the window to exploit it is 1-3 years, before Genius Sports or Sportradar ships a tracking-integrated prop pricing API and sells it to books at retail scale.

---

## Why Renaissance Technologies

The most successful quant trading operation in history wasn't a hedge fund. It was a research institution that happened to also trade. Jim Simons built the Medallion Fund by hiring mathematicians and physicists — not traders — and running them like a university research department: ruthless signal testing, ruthless retirement, no emotional attachment to any model that stopped working.

The result: 66% gross returns for 30 years. A Sharpe ratio that makes modern funds look like noise.

CourtVision applies the same architecture to sports:

| Renaissance principle | CourtVision implementation |
|----------------------|---------------------------|
| Hire researchers, not traders | Claude agents = permanent research staff |
| 500-5000 signals, not 5 big bets | Signal universe vs model-based |
| Ruthless retirement (signals decay) | Automated IR tracking + deprecation |
| Deflated Sharpe (beat overfitting) | Purged k-fold, walk-forward, 48-hr purge |
| Factor decomposition of P&L | Attribution to CV / context / market signals |
| Research substrate, not a trading desk | The system is the moat, not any one model |

The key difference from traditional quant sports betting: Renaissance doesn't predict games. It runs a research machine that continuously discovers, validates, and retires signals. CourtVision is that machine, applied to sports, built in 2026 with Claude agents replacing 95% of the research headcount.

**Cost of a Renaissance-style research program the traditional way:** $5-15M/year in PhD researchers.
**Cost with Claude agents:** ~$50-80/month compute, plus time to direct.

This is why the window exists now. AI collapsed the research labor cost by 100-1000x. The solo operator has Renaissance-depth research at sharp-shop budget.

---

## What's Already Built

The substrate that makes the research machine possible is largely done:

**CV Tracking Pipeline** — YOLOv8n → SIFT homography → Kalman+Hungarian → OSNet re-ID → EasyOCR → EventDetector. Converts broadcast video to court-coordinate spatial features. **85 games tracked / 7 with full feature extraction (target: 80 clean).** Cost: ~$0.10-0.13/game on RunPod 3090.

**Intelligence Layer** — 80 derived artifacts at `data/intelligence/` between CV tracking and the prediction models: player archetypes + similarity (26K-pair matrix), defensive scheme tags, position×scheme + archetype×scheme interaction tables, lineup chemistry (4.7K rows / 1.2K lineups), clutch/quarter/shot-clock splits, matchup deviations, coaching adjustments, officials impact, game-similarity retrieval, CV-quality + per-player confidence curves. Public manifest: [docs/INTELLIGENCE.md](docs/INTELLIGENCE.md).

**ML Signal Stack** — 85 trained models across 7 tiers. Honest walk-forward holdout, N=99,818 player-games (loop-5 cycle 96e production):

| Signal | MAE | Production recipe |
|--------|----:|-------------------|
| PTS  | 4.62 | sqrt+Huber XGB/LGB blend + 5-seed MLP, NNLS-stacked |
| REB  | 1.90 | log1p LGB quantile q50 |
| AST  | 1.36 | log1p XGB+LGB + multitask MLP, NNLS-stacked |
| FG3M | 0.89 | log1p XGB quantile q50 |
| TOV  | 0.89 | log1p XGB quantile q50 |
| STL  | 0.72 | log1p XGB quantile q50 |
| BLK  | 0.44 | log1p XGB q50 (**−16% vs prior best**) |

MAE — not R² — is the betting-relevant loss because sportsbook prop O/U lines score against the median, not the mean. 6 of 7 stats now ship q50 quantile heads as the primary predictor.

**Win probability:** 70.94% accuracy / 0.193 Brier on 3-fold walk-forward; 71.7% / 0.188 on single-split. 5-way NNLS stack (XGB+LGB+LR+5-seed MLP+GaussianNB). Source: [`data/models/win_prob_metrics.json`](data/models/win_prob_metrics.json).

**Real-money read vs real closes (Gate 1 re-grade, HONEST):** against real DK / FanDuel / MGM / Pinnacle **closing** lines the **market is efficient** — the prop edge is **break-even-minus-vig** (−2.00% unfiltered). The one genuinely durable, book-robust edge is **assists, ~+4–5% ROI** (selection skill, not under-bias; breaks in the playoffs — size conservative). Re-grade: `python scripts/run_gate1_full_analysis.py`. *(The earlier "+18.38% / +8.94pp CLV" was a market-follow grading artifact — the grader bet the market's devig favorite and never read the model — retracted; see [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md).)*

**In-play stack (shipped 2026-05-27):** endQ1/Q2/Q3 LGB residual heads. In-game endQ3 MAE lift ~46% pooled vs pregame (mostly mechanical; **~26% over a naive carry-forward baseline**, WF-validated, leak-clean). endQ3 win-prob Brier **~0.141 leak-free** (the earlier "0.1191" was a Q4 feature leak, caught and retracted).

**In-play paper backtest (L5 proxy, NOT real closes):** 78% hit / +54% ROI on n=55,073 calibrated bets — a **model-quality ceiling, not realized edge**. Real-money estimate **+15–25%**. First real Pinnacle close CLV reading: Oct 2026; zero real money placed by design.

**xFG** (shot quality): Brier 0.226 on 221K shots. **DNP predictor:** AUC 0.979.

**Validation Infrastructure** — Shipped 2026-05-17. Temporal CV harness, model registry with holdout gates, regression test suite (4,100+ collected, 48/48 critical-path pass, 63/63 in-play subset pass), CLV tracker, CV benchmark.

**Execution Layer** — Shin devig + Kelly-B + per-stat isotonic edge calibration + Ledoit-Wolf shrinkage + shadow logger (every eval incl. blocked) + settlement engine + decision engine with per-quarter EV floor (calibrated 0.01 → 0.12 post-hoc). 9 production daemons watchdog'd. Live trading desk UI: `/scan`, `/clv`, `/parlays`, `/live/{game_id}`, SSE arbs.

**Agentic Research System** — LIVE as the improve_loop. Opus orchestrates, Sonnet executes, Haiku searches. Two arms: ARM A mines residuals into gated leaf signals, ARM B writes intel atlas sections. Ship gate built to *refute*: expanding walk-forward (all folds improve) + null-shuffle permutation (z≥3) + ablation + Benjamini-Hochberg FDR. Most candidates correctly rejected — and **this same loop caught and retracted the inflated +18.38% / endQ3-0.119 headlines.** Spec: `.claude/commands/workday-loop.md`.

**What's not yet built:** Pinnacle real-close Gate 1 (gated on Oct 2026 preseason ingestion). Possession simulator (Monte Carlo). Book adapters with order management for DK/FD/BetMGM/Novig. News ingestion pipe.

---

## The Six Revenue Surfaces

CourtVision is not a betting tool. It's a sports intelligence substrate that supports six monetization surfaces simultaneously. Each surface enriches the others.

**1. Personal Betting** — Iowa-legal, fully online since 2021-01-01. Multi-book (DK/FD/BetMGM/Caesars/bet365) + P2P exchanges (Novig, ProphetX, zero vig). First revenue surface, primary feedback signal. CLV vs Pinnacle close is the validation metric.

**2. Fund Management** — Audited returns attract LP capital. Operates on exchanges where institutions can participate (Kalshi), but routed through individually-held accounts. Target: 5-10 LP investors, $500K-2M under management, after 12+ months audited track record.

**3. Signal Subscriptions** — $5-25K/month per sharp subscriber, capped at ~30 to preserve edge. Only available after CLV track record is public. Target: Q4 2026 earliest. Revenue: $3-8M/year at scale.

**4. Team / Agent / Scouting Licensing** — CV spatial features (defender pressure, spacing, play type, shot quality by context) are what NBA front offices buy from Second Spectrum for $100K+/year. CourtVision extracts the same signals from broadcast video. Target: $150-400K/year per franchise.

**5. Media / Broadcast Augmentation** — Real-time court-coordinate overlays ("open / contested / impossible" shot probabilities) during live broadcasts. Target: regional sports networks, streaming platforms. Revenue: $500K-2M per deal.

**6. AI Knowledge Layer API** — Sports brain queried by LLM applications, metered by call. As LLM apps proliferate, sports context becomes a commodity call. The knowledge graph (player history, spatial telemetry, prediction distributions) is a natural API product.

---

## The Moat (In Order of Defensibility)

**1. Agentic research system architecture** — The system that discovers signals, not the signals themselves. A competitor who copies the current model stack doesn't get the discovery engine that generated it.

**2. CV behavioral features from broadcast video** — Defender hand position at shot release. Screen quality index. Body language before a drive. These are qualitatively different from Second Spectrum's raw tracking. Second Spectrum gives you positions. CourtVision derives judgment.

**3. Multi-surface monetization compounds** — Signal subscriptions reveal which edges are known. Team licensing reveals which plays are underexploited. Fund management validates returns. Each surface informs the research agenda for the others.

**4. Solo regulatory access** — Institutions cannot hold retail sportsbook accounts. P2P exchanges with zero vig are inaccessible to registered funds. The regulatory moat is structural, not tactical.

**5. Signal universe accumulation** — 500-5000 signals over 3-5 years, each with documented IR (information ratio), birth date, retirement date, and P&L attribution. The historical signal database is not reproducible without running the full research pipeline.

---

## The Exit Thesis

**Timeline:** 5-7 years from first audited return.

**Strategic acquirers:**
- Stats Perform, Genius Sports, Sportradar — the data layer wants the research machine
- DraftKings, FanDuel — the operator wants the signal universe + team licensing relationships
- Two Sigma Sports, SIG/Nellie Analytics — the quant firm wants the agentic research architecture
- Anthropic-adjacent sports vertical — the AI company wants the domain-specific agent deployment

**What's being acquired:** The agentic research system + foundation model + knowledge graph + audited fund track record + commercial relationships. Not just a software product. A moat.

**Valuation range:** $300M-$2B depending on which surfaces materialize and whether the signal subscription business achieves defensible margins before exit conversations begin.

The bet: sports prediction research has never had a Renaissance Technologies. Build it first. 1-3 year head start on AI-native methodology. 5-7 year compounding before any well-funded competitor can match the signal universe depth.

---

## What's Required to Realize the Ceiling

In priority order:

1. **Gate 1 this week** — Run CLV validation against real Pinnacle closing lines. This is the only test that matters for the entire enterprise. Everything else is theory until this passes.

2. **80-game CV corpus** — RunPod run is next. 17 quality games → 80 clean. Unlocks Tier 3-4 model retrain with spatial features.

3. **Agentic research system** — The Claude agent layer that turns the substrate into a self-improving research machine. This is the difference between "a prediction system" and "the Renaissance of sports."

4. **Signal-based refactor** — Move from model-based thinking (90 models) to signal-based (500-5000 signals with IR tracking and retirement). The architecture is more defensible, more honest about what's working, and more aligned with how durable quant edges actually work.

5. **First commercial surface** — Signal subscriptions or team licensing. Establishes external validation of the research quality.

---

*For technical architecture: [ARCHITECTURE.md](ARCHITECTURE.md)*
*For the build sequence: [ROADMAP.md](ROADMAP.md)*
*For the full strategic plan: [MASTER_PLAN.md](MASTER_PLAN.md)*
*Renaissance methodology references live in the maintainer's local `vault/Research/` (gitignored — not present on GitHub).*
