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

**CV Tracking Pipeline** — YOLOv8n → SIFT homography → Kalman+Hungarian → OSNet re-ID → EasyOCR → EventDetector. Converts broadcast video to court-coordinate spatial features. 29 usable games processed (target: 80 clean).

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

**Backtested edge.** A 19,964-game holdout (cycle 30, re-validated cycle 38) bets every player-game where the model deviates from L5-line proxy by ≥ edge threshold. At -110 odds (break-even 52.4%): PTS +19.9% / REB +23.6% / AST +26.8% / FG3M +23.9% / TOV +28.1% / STL +21.5% / BLK +26.5% ROI at +0.5 edge; rises to +24% to +52% at +1.0 edge. Re-test against a smarter line proxy (L5 × opp_def × home_adj) still wins 26-32% ROI. Source: [`data/models/betting_backtest.json`](data/models/betting_backtest.json), [`data/models/betting_backtest_smart_line.json`](data/models/betting_backtest_smart_line.json).

**xFG** (shot quality): Brier 0.226 on 221K shots. **DNP predictor:** AUC 0.979.

**Validation Infrastructure** — Shipped 2026-05-17. Temporal CV harness, model registry with holdout gates, regression test suite (2,661 pass on RunPod / 1040+ on core suite locally; ~26 transient failures, none prediction-critical), CLV tracker scaffolding, CV benchmark.

**Execution Layer** — Fractional Kelly + Ledoit-Wolf shrinkage, Shin devig, CLV vs Pinnacle close, multi-book routing, paper-trading harness.

**What's not yet built:** The agentic research layer (the multi-agent Claude system that autonomously discovers signals). Gate 1 (first CLV validation against real closing lines, not yet run). The news ingestion pipe.

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
