# CourtVision MASTER PLAN — The Renaissance of Sports
*Canonical strategic document. Updated 2026-05-18 to reflect agentic AI framing.*

---

## Executive Summary

Sports prediction sits on a $200-500M/year extractable profit pool that institutional capital structurally cannot reach: per-game bet limits ($25-500 at retail books) make the math impossible for quant funds that need $50M+ deployment. The regulatory architecture (sportsbooks close professional entities) further blocks institutions. Solo operator + Claude agents = the only economic model that works.

The Renaissance comparison: Jim Simons built the Medallion Fund not as a trading desk but as a research institution — ruthless signal testing, ruthless retirement, no emotional attachment to any model that stops working. 66% gross returns for 30 years. CourtVision applies the same architecture to sports: not "90 models" but a signal universe (500-5000 signals over 3-5 years), each with documented information ratio, birth date, retirement date, and P&L attribution. Claude agents replace the PhD research staff at 100-1000x lower cost.

The exit thesis: 5-7 year path to $300M-$2B acquisition by Stats Perform, Genius Sports, DraftKings, Two Sigma Sports, or Anthropic-adjacent sports vertical. The asset being acquired is the agentic research system + knowledge graph + audited track record + commercial relationships — not just a software product.

## What Changed in This Update (2026-05-18)

- Reframed from "90-model betting system" to "agentic AI research platform"
- Signal-based architecture (500-5000 signals with IR tracking) replaces model-based (90 target models)
- Multi-surface monetization (6 revenue streams) made explicit — betting is surface 1, not the product
- Renaissance-style methodology added as core intellectual framework
- Multi-agent Claude research system added as the 6th system (the moat)
- Canonical R² corrected: pts=0.41, reb=0.38, ast=0.36, fg3m=0.29, blk=0.16, tov=0.22, stl=0.18
- Gate 1 status clarified: NOT YET RUN — top priority

## Canonical Facts (2026-05-25)

> **Honest framing.** R² rows below come from `data/models/model_registry.json` (squared-error fit quality). MAE rows come from `data/models/quantile_pergame_metrics.json` / `verify_production_mae.py` (median absolute error). For the q50 stats (REB/FG3M/STL/BLK/TOV — 5 of 7), **R² gets worse but MAE wins decisively** because sportsbook prop O/U lines score against the median, not the mean, and q50 pinball loss targets the median directly. The MAE numbers are the betting-relevant ones.

| Metric | Canonical value | Source |
|--------|----------------|--------|
| Props holdout R² — pts | 0.5105 | `data/models/model_registry.json` |
| Props holdout MAE — pts | 4.6210 (sqrt+Huber blend) | `data/models/quantile_pergame_metrics.json` |
| Props holdout R² — reb | 0.38 (q50 — R² regresses, MAE wins) | `data/models/model_registry.json` |
| Props holdout MAE — reb | 1.9023 (LGB-q50) | `quantile_pergame_metrics.json` |
| Props holdout R² — ast | 0.4988 | `model_registry.json` |
| Props holdout MAE — ast | 1.3559 (multitask MLP blend) | `quantile_pergame_metrics.json` |
| Props holdout R² — fg3m | 0.29 (q50 — R² regresses, MAE wins) | `model_registry.json` |
| Props holdout MAE — fg3m | 0.8943 (XGB-q50) | `quantile_pergame_metrics.json` |
| Props holdout R² — stl | 0.18 (q50 — R² regresses, MAE wins) | `model_registry.json` |
| Props holdout MAE — stl | 0.7153 (XGB-q50) | `quantile_pergame_metrics.json` |
| Props holdout R² — blk | 0.16 (q50 — R² regresses, MAE wins) | `model_registry.json` |
| Props holdout MAE — blk | 0.4398 (XGB-q50, -16% session win) | `quantile_pergame_metrics.json` |
| Props holdout R² — tov | 0.22 (q50 — R² regresses, MAE wins) | `model_registry.json` |
| Props holdout MAE — tov | 0.8932 (XGB-q50) | `quantile_pergame_metrics.json` |
| Win prob accuracy | 0.7094 (WF) / 0.717 (single-split) | `data/models/win_prob_metrics.json` |
| Win prob Brier | 0.193 (WF) / 0.188 (single-split) | same |
| xFG Brier | 0.226 (221K shots) | model registry |
| In-play endQ3 MAE vs pregame | -43% to -55% across 7/7 stats (550-game retro) | `retro_inplay_mae_v2.json` |
| CV games | 17 quality / 29 usable / 75 attempted | `data/ingest/queue.db` |
| Models trained | 85+ trained ML artifacts (119 .pkl files incl. residual heads, period heads, calibration) | `data/models/` |
| Gate 1 status | NOT YET RUN | — |

---

## The Core Thesis

A solo AI-native operator can build and run what would take a traditional quant firm 50 engineers and $5M/year — and can operate in markets those firms structurally cannot enter. The bet is that AI collapses the labor cost advantage of large firms in markets too thin for institutional capital but too complex for retail bettors.

**The primary edge:** CV-derived spatial features from broadcast video (defender distance, spacing, fatigue, scheme detection) that retail bettors cannot access and that sportsbooks are NOT deeply integrating into player prop pricing. Books price props primarily from box-score models (season averages, opponent DRTG, recent trends). The gap between what your model knows (spatial reality) and what the book priced (box-score summary) is the exploitable inefficiency.

**The window:** 1-3 years before Genius Sports or Sportradar ships a tracking-integrated prop pricing product. Move fast. Edge decay is real.

**What you're building:** A one-person AI-native sports quant firm. NBA first. Then every major sport. Eventually the most advanced real-time sports betting quant dashboard that has ever existed.

---

## Why This Works — The Structural Argument

### Why Large Firms Can't Do This

SIG (via Nellie Analytics, founded 2017) and Jump Trading are the ONLY major quant firms with sports operations — and both focus exclusively on exchange-level market making on Kalshi and Polymarket, NOT retail player props. Citadel, IMC, Hudson River, DE Shaw have explicitly stayed out. Here's why:

- **No hedging instrument.** Sports event contracts have no underlying spot asset for mechanical hedging (unlike options on equities). Quant firms can't build the risk-management infrastructure they rely on.
- **Labor economics don't work.** A SIG-caliber 10-15 person team costs $7-10M/year in compensation alone. Player props represent ~$18-26B in US sportsbook handle but the extractable edge pool is maybe $50-100M annually across all bettors — invisible at institutional scale.
- **Account-level access is blocked.** Sportsbooks flag and close accounts for professional betting entities. Registered investment firms literally cannot hold DraftKings accounts. You can hold 6+ simultaneously as an individual.
- **Minimum deployment size.** A quant fund needs to deploy enough capital to justify desk costs. Player props are limited to $25-500 per bet at retail books. You can't deploy $50M into DraftKings props.
- **Capacity constraint.** This mirrors micro-cap equities: institutions systematically ignore markets below $500M-1B in deployable capacity because the alpha doesn't justify infrastructure. Solo traders dominate micro-caps for exactly this reason. You are the micro-cap trader of sports.

### The AI-Native Advantage

Solo founders in 2026: 36% of all startups, achieving 77% first-year profitability vs ~40% for traditional teams. The force multiplier math:

| Function | Traditional Firm | You + AI |
|---|---|---|
| Data engineering | 5-10 engineers, months | Claude writes pipelines, you architect, days |
| Research | PhD teams, quarters | Claude researches in minutes, you direct |
| Model development | ML engineering teams, quarters | Claude builds models, you validate, weeks |
| Execution infra | Trading systems team, 6-12 months | Claude builds FastAPI adapters, days |
| Risk management | Dedicated risk team, proprietary systems | Claude implements Kelly/correlation/limits |
| Compliance | Lawyers, compliance officers, slow | You're an individual — minimal burden |
| Coordination | Meetings, Jira, PRDs, code review cycles | Zero — you decide, Claude builds, you ship |
| Market expansion | Board approval, team allocation, quarters | Point Claude at new sport, weeks |

**Your operating cost: ~$50-80/mo. A competing firm: $3-5M/year minimum.**

### Precedents for Solo Operators Winning

- **Haralabos Voulgaris** — exploited NBA totals mispricing at ~70% win rate for years, eventually staking $1M+/day. Solo operation, proprietary modeling on data others weren't using.
- **Bill Benter** — built a 130-variable horse racing model that produced $118M in a single day. Started as an individual, minimal staff.
- Both succeeded with: proprietary data + mathematical modeling + automation. That's exactly what you're building, but with AI making each component 10x faster to build.

---

## Markets & Venues — Complete Detail

### Iowa Legal Status (Current Residence)

**Fully legal, online, no in-person signup required since Jan 1, 2021. Must be physically in Iowa (geo-fenced). Must be 21+.**

#### Sportsbooks (Primary Venue)
All the following are licensed, fully online, offering NBA player props:

| Book | Prop Menu | Typical Vig | Limiting Speed | Notes |
|---|---|---|---|---|
| **DraftKings** | Deepest — pts/reb/ast/3pm/blk/stl/tov + combos + alternates | -110 to -120 (5-9%) | Fastest — within weeks at 300 bets | Most volume, limits hardest |
| **FanDuel** | Deep, similar to DK | -110 to -115 (5-7%) | Slowest of majors | Most tolerant, start here |
| **BetMGM** | Good | -110 to -120 | Fast, similar to DK | Watch win rate closely |
| **Caesars** | Good | -110 to -115 | Moderate | Less data on limiting patterns |
| **bet365** | Good | -110 to -115 | Moderate | UK-origin, slightly different model |
| **Fanatics** | Growing | -110 to -115 | Unknown (new) | Least data, possibly most tolerant early |

**Standard prop vig:** -110/-110 = 4.55% vig. Many books run -115/-115 (6.5%) or -120/-120 (~9%). Know which books are sharper on which markets.

**Account limiting reality:** Books now use AI-driven profiling. Limiting triggers within ~300 bets for consistent winners (down from ~1,000 a few years ago). Props get limited before mainlines. Specific market types get limited before account-wide limits. Strategy: **never hit the same book repeatedly on same prop type, vary bet sizes, vary timing.**

#### P2P Exchanges (Zero Vig — Sustainable Long-Term)

| Platform | Legal in Iowa | Model | Vig | NBA Coverage | Limiting |
|---|---|---|---|---|---|
| **Novig** | Yes (42 states) | Sweepstakes/P2P | Zero | TBD — test at season start | None ever |
| **ProphetX** | Yes (40+ states) | Sweepstakes/P2P | Zero | TBD | None ever |

**Why these matter:** Zero vig means any positive edge (50.01% win rate) is pure profit. On a sportsbook at -110, you need 52.4% to break even. On P2P, 50.01% wins. This is the endgame venue once bankroll grows. The limiting problem disappears permanently.

**Endgame play:** Become a market maker on P2P exchanges. Post your own lines where you have edge on both sides. You're no longer a bettor — you're the house.

#### Prediction Markets (Legally Precarious — Monitor)

| Platform | Status in Iowa | NBA Coverage | Fee Structure | Notes |
|---|---|---|---|---|
| **Kalshi** | Gray — Iowa AG suing, Kalshi filed federal counter-suit (March 2026). Accessible now. | Game-level + some player performance | <2% of max profit | CFTC-regulated, institutional participation, deepest liquidity of prediction platforms |
| **Polymarket** | Gray — crypto-based, technically US residents prohibited | Thin NBA | ~0.75% | USDC, growing, NBA exploring partnership |

**Iowa AG joined multi-state coalition against prediction markets (May 2026). Iowa Senate Bill SB 2470 failed but legal pressure continues. Use carefully, not a foundation to build on.**

#### NOT Available in Iowa
- **PrizePicks** — not licensed in Iowa
- **Underdog Fantasy** — not licensed in Iowa
- **Pinnacle** — US residents blocked (sharpest lines in world, 2-3% margin, "winners welcome")

**If you move to Illinois:** Gain PrizePicks access (massive — deep player prop DFS market). Lose ability to bet on in-state college teams (Illinois prohibits this, Iowa allows it). Net: move gains you PrizePicks.

#### Cross-Venue Arbitrage Opportunity
Same event priced differently on sportsbook vs P2P exchange vs Kalshi. When lines diverge enough to guarantee profit regardless of outcome, that's pure arbitrage. Your system should scan for this continuously. No edge, no model needed — just price comparison.

---

## The 6 Core Systems

Everything in the system flows through these 6. Not 85 models — 6 systems. The 85 models are components that feed into them. System 6 (the agentic research layer) is the moat that discovers and retires what feeds into Systems 1-5.

> **Signal-based reframe (2026-05-18):** The "90 models" language is deprecated. The architecture targets a signal universe of 500-5000 signals over 3-5 years — each signal tracked by information ratio (IR), birth date, and retirement date. Individual signals are like individual hypotheses in a research program: most fail, the survivors compound. This is how Renaissance Technologies worked. This is how CourtVision works.

### System 1: Possession Simulator

The centerpiece. Everyone else predicts a number. You generate a distribution.

**What it does:** Simulates game flow possession-by-possession using lineup-dependent transition matrices. 10,000 Monte Carlo paths per game → full probability distribution over every player's every stat.

**Why distributions matter:**
- Pricing ANY line, not just the mainline. If book posts O/U 27.5 but also offers alternates at 24.5 and 30.5, your distribution tells you which has the most edge.
- Confidence intervals. `P(pts > 27.5) = 52%` is a weak signal. `P(pts > 27.5) = 62%` with a tight CI is a strong bet.
- SGP pricing. Joint probability of correlated legs requires modeling them together, not multiplying independent probabilities.

**Required inputs:**
- Lineup on floor at each possession (from NBA API)
- CV spatial features (defender distance, spacing, fatigue — from your pipeline)
- Context features (ref crew, rest days, altitude, travel)
- Player embeddings (NBA2Vec — encode playing style)
- Game state (score differential, time remaining — for blowout/garbage time modeling)
- Historical on/off splits per player (from PBPStats)

**Possession-level mechanics needed:**
- Lineup-dependent possession outcome probabilities (shot attempt, turnover, foul, etc.)
- Shot selection per player given defensive scheme
- Substitution patterns per coach per game state
- Garbage time threshold (when starters sit in blowouts — kills all counting stat overs)
- Foul trouble logic (player with 3 fouls in Q2 sits)
- Blowout logic (large leads → bench players → different stat distributions)

**Output:** For every player, for every stat: `P(stat > X)` for any threshold X. A complete probability distribution, not a point estimate.

### System 2: Line Evaluator

**What it does:** Real-time comparison of simulator output against every available market line across all books and venues.

**Mechanics:**
- Poll Odds API every 30-60 seconds for live lines from 40+ books
- For each prop line at each book: compute implied probability (remove vig using no-vig formula)
- Compare to simulator's probability for same outcome
- Edge = simulator_probability - book_implied_probability
- Rank all opportunities by: edge × confidence × liquidity
- Filter by: minimum edge threshold, book health, correlation with existing bets

**Critical: the no-vig line.** To compute true edge, you must remove the book's vig first. For -110/-110 lines: no-vig probability = 0.5238... × adjustment. Don't compare raw odds to raw odds.

**Timing triggers (re-evaluate immediately when):**
- New prop line posted (morning, ~6am)
- Referee assignment announced (~9am)
- Injury report filed (1pm and 5pm mandatory)
- Starting lineup confirmed (~30-35 min pre-game)
- Late scratch announced (any time)
- Line moves >0.5 points (steam detection)

### System 3: Correlation Engine

**The SGP opportunity:** Books price Same Game Parlays by multiplying individual leg probabilities with a generic "correlation discount." That discount is formulaic, not model-derived. Your possession simulator generates joint distributions naturally because it simulates the whole game. You know the actual joint probability. When the book's correlation discount is wrong, that's edge.

**Example:** "Player A over 27.5 points AND Player B over 7.5 assists" in the same game. These are positively correlated (good offense helps both). The book might price this as: `P(A>27.5) × P(B>7.5) × 0.9 correlation discount`. Your simulator says the joint probability is actually higher because both happen in high-tempo, efficient offensive games. That difference is pure edge.

**Also handles:** Multi-game parlays (positive correlation in same-direction totals bets when league-wide pace is high/low). Portfolio correlation (all your active bets → how correlated is your total exposure?).

### System 4: Kelly Sizer

**Inputs:** Edge, confidence interval, current bankroll, correlation with existing bets, book-specific max bet limit, current drawdown state.

**Kelly fraction formula:** `f = edge / (1 - probability_of_loss)` — but this is full Kelly, which is too aggressive. Use fractional Kelly:
- **Quarter Kelly** — very conservative, minimum ruin probability, slower growth
- **Half Kelly** — balanced, recommended starting point
- **Full Kelly** — aggressive, risk of large drawdowns

**Portfolio-aware modification:** If you have 5 bets on the same game, the Kelly fraction for each decreases because they're correlated. Don't apply single-bet Kelly to correlated bets — you'll oversize.

**Drawdown triggers (automatic):**
- 10% bankroll drawdown → reduce all sizing to half Kelly
- 20% drawdown → reduce to quarter Kelly
- 30% drawdown → suspend betting, alert, manual review required

**Book-specific limits:** Each book has max bet sizes per market. Kelly may say $200 but DK might cap props at $50. The router handles this by splitting across books.

### System 5: Execution Router

**Per-book adapters for:**
- DraftKings, FanDuel, BetMGM, Caesars, bet365, Fanatics
- Novig, ProphetX (P2P)
- Kalshi

**Routing logic (priority order):**
1. Best available price (line shopping — always get the best number)
2. Account health (avoid books at heat threshold)
3. Max bet limits at each book
4. Correlation with existing bets at same book
5. P2P if price is within 0.5 points of best sportsbook price (zero vig makes up the difference)

**Account health monitor per book:**
- Bet count (flag at 250, approaching ~300 limit trigger)
- Win rate (flag if >55% sustained over 50+ bets)
- Bet velocity (bets per day — unnatural consistency triggers review)
- Prop type concentration (hitting same markets repeatedly → faster limits)
- Heat score: composite of all above
- **Auto-rotation:** When heat score exceeds threshold, stop routing to that book

**Bet execution methodology (against TOS but technically feasible):**
- Selenium/Playwright automation of web interface
- OR: system generates bet slip details (book, market, side, amount) and alerts you for manual placement
- Long-term: find if any books offer unofficial APIs or if P2P exchanges have official APIs

### System 6: Agentic Research System (not yet built — the moat)

**What it is:** A multi-agent Claude system that autonomously discovers, validates, ships, and retires prediction signals. The substrate (Systems 1-5) is the instrument. System 6 is the research program that plays the instrument.

**Agents:**
- **Orchestrator** — coordinates the loop, allocates research budget, logs to vault
- **Researcher** — hypothesis generation from knowledge graph + academic literature + market microstructure
- **Engineer** — signal implementation + feature wiring + unit tests
- **Validator** — holdout testing + information ratio calculation + pass/fail gate
- **Risk Manager** — correlation impact + Kelly impact + drawdown simulation
- **Retirement Monitor** — signal decay detection + deprecation trigger

**Signal lifecycle:**
1. Hypothesis generated by Researcher
2. Signal implemented by Engineer
3. Validated against holdout by Validator (IR threshold = 0.5 minimum to promote)
4. Deployed to shadow mode by Orchestrator
5. Promoted to production after 30+ settled observations confirming IR
6. Monitored for decay by Retirement Monitor
7. Retired when IR drops below threshold for 60 consecutive days

**Why this is the real moat:** A competitor who copies the current 85 models doesn't get the discovery engine that generated them. The signal universe database (birth date, retirement date, IR history, P&L attribution) is not reproducible without running the full research pipeline from scratch.

**Target:** 50 validated signals by month 3, 200 by month 9, 500+ by year 2. Ruthless retirement: expect 60-70% of signals to fail validation or decay within 18 months.

**See:** [vault/Plans/Agentic Research System.md](vault/Plans/Agentic%20Research%20System.md) for full architecture.

---

## The Complete Edge Stack

### INFORMATION EDGES — You See What Others Can't

#### CV-Derived Spatial Features (Your Primary Moat)

**1. Defender distance distributions (BUILT — needs 80+ games)**
- Not just "open vs contested" — full distribution of defender distance on every shot attempt per player
- Academic validation: FG% varies dramatically by closest-defender distance. Darryl Blackport's research shows this is the most influential variable in shot outcome prediction.
- Your CV pipeline extracts this from broadcast homography. Nobody else at retail can do this.
- Books don't use this for prop pricing. Prop lines are box-score models.
- **After 80+ games:** You have per-player defender distance distributions per matchup. You know if this player's shots are more or less contested than his season average suggests.

**2. Court spacing — convex hull of offensive players (TRACKING DERIVATIVE — trivial build)**
- Compute convex hull area of 5 offensive players per possession
- 5-out spacing vs traditional spacing has significant impact on drive efficiency and kick-out 3P opportunities
- Predicts: 3PM opportunities, paint touches, assist likelihood
- Already validated by analytics community. Your homography gives you this for free from existing tracking data.
- Estimated build time: 1-2 days

**3. Closeout speed on shooters (TRACKING DERIVATIVE — trivial)**
- Compute defender velocity vector toward ball-handler after kick-out pass
- Slow closeout = open 3P attempt. Fast closeout = contested pull-up.
- Second Spectrum advertises "contest quality" as a headline product metric — you approximate it from broadcast
- Predicts: 3P% above/below expectation given shot volume
- Build time: 1-2 days

**4. Paint density per possession (HOMOGRAPHY DERIVATIVE — trivial)**
- Count players within paint polygon per frame
- High paint density → fewer drive completions, more perimeter shots, fewer free throws
- Predicts: FTA rate, drive efficiency, points in paint vs perimeter split
- Build time: hours

**5. Transition vs half-court classification (RULE-BASED — trivial)**
- If all 5 players cross half-court within N seconds of possession start → transition
- Transition possessions: faster pace, higher scoring efficiency, different shot types
- Directly affects: points per possession projection, pace model
- Build time: hours

**6. Catch-and-shoot vs off-dribble detection (TRACKING DERIVATIVE — trivial)**
- Was the player stationary (< velocity threshold) for N frames before shot release? → catch-and-shoot
- C&S shots have significantly higher FG% than off-dribble for most players
- Predicts: individual player FG% given shot type distribution in a matchup
- Build time: 1 day

**7. Off-ball movement quality (TRACKING DERIVATIVE — trivial)**
- Total distance traveled by non-ball-handlers per possession
- High off-ball movement = active offense, creates open looks
- Low off-ball movement = passive scheme, fewer catch-and-shoot opportunities
- Second Spectrum advertises this as a key metric
- Predicts: scheme quality, open shot generation
- Build time: 1-2 days

**8. Shot trajectory / release angle (NEW CV — medium, high value)**
- Fit parabolic curve to ball trajectory on shot attempts
- Extract release angle and entry angle
- NBA's own data: release angles 45-55 degrees correlate with higher make rates
- From broadcast: feasible with ball trajectory fitting (Faster R-CNN + curve fitting, see Research Archive 2024 paper)
- Predicts: FG% independent of defender distance (complements edge #1)
- Build time: 2 weeks

**9. Pick-and-roll detection (GRAPH MODEL ON EXISTING TRACKS — medium-hard)**
- Two offensive players converge, defender paths cross
- PnR is the most common NBA play type — scheme classification enables PnR-specific models
- TacticExpert (arXiv 2503.10722, 2025) provides methodology using spatial-temporal graph models
- Simple rule-based approach first (two players within X feet, movement patterns), then upgrade to graph model
- Predicts: which player (ball-handler vs roller) gets the scoring opportunity, assist vs direct score
- Build time: 2-3 weeks for robust version

#### Context Features (Free, Underused, High Signal)

**10. Referee foul rates and pace impact (EASY — 1 day)**
- NBA posts daily ref crew assignments at official.nba.com/referee-assignments ~9am ET game day
- NBAstuffer has multi-season ref stats: personal foul rate, free throw rate, pace under each ref
- Academic backing: Oregon State study found profitable biases in NBA ref foul calling. 2025 Journal of Sports Economics paper analyzed L2M reports for referee performance near spread.
- Star players receive favorable calls proportional to salary — ref-specific effect
- Predicts: FTA props (direct), pace (indirect, affects all counting stats), total points
- **Key timing edge:** Props are posted before ref assignments. When refs announced at 9am, lines haven't fully adjusted. Your model updates in seconds.
- Build: scrape ref assignments at 9am, look up historical foul/pace stats, inject as features

**11. Travel fatigue index (EASY — 1-2 days)**
- Go beyond back-to-back binary flag. Compute:
  - Great-circle flight distance between cities
  - Timezone crossing (East vs West direction matters — westward travel is harder)
  - Departure time and estimated arrival time relative to game time
  - Days since last rest day
  - Cumulative schedule density over prior 7 days
- West Coast teams playing early East Coast games consistently underperform (circadian misalignment)
- Academic backing: extensively studied in NBA scheduling literature
- Predicts: all counting stats (fatigue reduces them across the board), specifically guard scoring and assists
- Build: city coordinate lookup + schedule data + distance formula

**12. Denver altitude adjustment (TRIVIAL — hours)**
- Denver Nuggets have .652 all-time home win% vs .350 away (.302 delta — largest home court advantage in NBA)
- Visiting teams consistently lead at halftime then collapse in second half (altitude effect peaks in Q3-Q4)
- Sportico analysis confirms effect even controlling for team quality
- ESPN documented this during 2023 Finals
- Feature: binary "visiting team in Denver" + optional continuous altitude-weighted feature for other elevated cities
- Predicts: visiting player performance decay in second half, lower all-counting-stats for visitors

**13. Lineup-dependent usage redistribution (MEDIUM — 1 week)**
- When a key player is ruled out, usage redistributes to teammates
- Current system: has some lineup modeling. This extends it.
- From PBPStats on/off data: when Player A sits, Player B's usage rate increases by X%
- Build a usage redistribution model: starter out → compute new usage shares for all teammates
- **Timing edge:** Late scratches happen 30-60 minutes pre-game. Lines adjust over 5-15 minutes. Your model recomputes in seconds. Every prop for affected teammates is stale during that window.
- Also applies: foul trouble during game (in-play betting if you go there)

**14. Load management / rest prediction (MEDIUM — 2 weeks)**
- arxiv 2603.26935 (2026): addresses "healthy-worker survivor effect" in NBA injury modeling
- Predictive signals: minutes trend over last 7 games, schedule density, player age, NBA Player Participation Policy constraints, win/loss record of team (teams out of playoff race rest stars)
- If you predict a rest day 6-12 hours before official announcement: every line is stale
- NBA participation policy requires teams to submit likely rest plans in advance — some leaks to reporters
- Build: train classification model on historical rest decisions, features above
- **When this fires correctly:** Every prop for that star player goes to zero, every teammate's props reprice upward

**15. Contract year effect (TRIVIAL — hours)**
- Players in the final year of their contract statistically perform differently (motivation effect)
- Salary/contract data is public (spotrac.com, basketball-reference.com)
- Feature: boolean "contract year" flag per player-season
- Sign of effect varies by player type — build empirically from historical data
- Small effect, easy to add

**16. NBA2Vec player embeddings (MEDIUM — 2 weeks)**
- Train Word2Vec-style embeddings on 3.5M play-by-play sequences (you already ingest this data)
- Each player represented as 8-dimensional vector where positional roles emerge naturally
- Players similar in embedding space play similar basketball roles
- Paper: arxiv 2302.13386
- **Uses:**
  - Lineup quality scoring (sum of embedded player vectors → lineup compatibility metric)
  - Counterfactual simulation: "what would this player's stats be with different teammates on floor?"
  - Cold-start for new players: find embedding-space neighbors to estimate performance
  - Trade impact: player moves to new team → find historical players with similar embeddings who made same trade → estimate performance change

**17. SportVU 2015-16 calibration dataset (ONE-TIME — 1 week)**
- 631 games of real XY tracking data at 25fps, publicly available on GitHub (sealneaward/nba-movement-data)
- This is the only public release of raw NBA tracking coordinates
- **Use case:** Validate your broadcast CV-derived spatial features against ground-truth tracking data
- Take a 2015-16 game where you have both: your CV pipeline output AND the SportVU ground truth
- Compare defender distance estimates, spacing measurements, etc.
- Quantify the error in your broadcast estimates → calibrate accordingly
- This tells you whether your CV features are signal or noise at the level of precision you're computing them

**18. Venue-specific and situational effects (EASY — add incrementally)**
- Home court advantage (model residual from neutral-site expected performance)
- Back-to-back visiting team performance (different from home B2B)
- Rest advantage/disadvantage (team on 3 days rest vs opponent on B2B)
- Playoff vs regular season (coaches play starters more minutes, different strategies)
- Early season vs late season (players in rhythm, teams have scouted each other)
- Rivalry games (elevated intensity, different pace and physicality)

### MODEL EDGES — You Think About The Problem Differently

**19. Full probability distributions, not point estimates (EXISTS — refine)**
- Your possession simulator already outputs distributions. Key refinements needed:
  - Are the distributions well-calibrated? (Do events you assign 30% probability actually happen 30% of the time?)
  - Use your 152K prop residuals to run calibration analysis
  - Platt scaling or isotonic regression to debias outputs
  - After calibration: your probability estimates are trustworthy

**20. Joint stat distributions for SGP pricing (MEDIUM — 2-3 weeks)**
- Build: when evaluating a multi-leg SGP, run your possession simulator for ALL legs simultaneously
- Extract the joint probability from simulation (what % of 10K paths have ALL legs hit?)
- Compare to book's SGP price (which uses formulaic correlation discount)
- When your joint probability > book's implied probability: +EV SGP
- This is a structural exploit of how books price multi-leg bets

**21. Regime detection — role and situation changes (MEDIUM — 1-2 weeks)**
- Players' roles change during a season. Your model trained on season data might not reflect current reality.
- Triggers for regime change: trade, teammate injury, coaching change, lineup shift, return from injury
- Build: detect regime changes automatically from NBA transactions feed + lineup data
- After regime change: weight recent games more heavily in model features, flag reduced confidence
- This is where some of the largest individual-game edges exist — the market hasn't fully recalibrated

**22. Bayesian in-season updating (MEDIUM — 1-2 weeks)**
- Start of season: prior from your pre-season model (trained on historical data)
- Each game: update posterior based on observed performance
- Your model's estimates become more accurate as the season progresses
- Books recalibrate more slowly (they have many markets, can't give each one full attention)
- Technical approach: Bayesian update on player skill parameters, shrinking toward prior at season start, releasing to observed data as sample grows

**23. Adversarial book model — predict line movement (HARD — 3-4 weeks)**
- Model HOW each book sets and adjusts lines
- Data collection: poll odds every 5-10 minutes from open to tip, track movement
- Features: which books lead (Pinnacle is sharpest market maker globally, unavailable to US, but you can watch Circa/BetCRIS as sharp proxies), which books follow, lag times between books
- Goal: predict DIRECTION of line movement before it happens
- When you can predict line will move from O27.5 to O26.5, bet O27.5 immediately before adjustment
- Also: detect "steam moves" — when sharp accounts hit multiple books simultaneously, movement is fast and directional
- This is the meta-edge: you're not just betting on games, you're exploiting the market's own price discovery process

**24. Counterfactual simulation ("what if" analysis) (MEDIUM — builds on NBA2Vec)**
- Using NBA2Vec embeddings + possession simulator: "what would Player X's stats look like if Player Y was on the floor instead of Player Z?"
- Application: trade deadline. Player joins new team. Historical teammates with similar embeddings: what happened to Player X's stats? Use that as prior for post-trade estimate.
- Books reprice slowly after trades. Your counterfactual gives you an early estimate.

**25. RL-optimized bet timing (HARD — longer term)**
- Current heuristic: bet at line open (best CLV) and again on lineup confirmation
- RL approach: train agent to decide WHEN to bet given current line, model confidence, time until game, expected line movement
- Conservative Q-Learning (CQL) for offline RL — trains on historical line movement data without needing live exploration
- Paper: ICAART 2024, XGBoost + RL for dynamic wager placement
- Could improve CLV by 0.5-1% by optimizing timing — meaningful at scale
- Build after the core system is running, not before

### EXECUTION EDGES — You Act Faster and Cheaper

**26. Multi-book line shopping (CORE INFRASTRUCTURE — 1 week)**
- The same prop can differ by 1-2 points across DK/FD/BetMGM/Caesars/bet365
- Always get the best available number. Always.
- Research shows consistent line shopping adds 1-3% ROI vs single-book betting
- At 5-12% vig, this is often the difference between profitable and unprofitable
- Implementation: The Odds API normalizes props across ~40 books in one call

**27. Opening line capture — the best CLV window (EASY — automate first)**
- Props are posted 12-24 hours before tip, often at 6am ET
- Opening lines have the most error — sharp money hasn't corrected them yet
- Research: bets placed 24+ hours pre-game show +1.2% average CLV; final-hour bets show -0.5%
- **Automated polling:** At 6am ET, poll for newly posted lines, compare to model, flag any +EV immediately
- This is likely the most impactful timing improvement with the least build effort

**28. Injury/lineup news speed — the information latency edge (MEDIUM — 1 week)**
- NBA mandatory injury reports: 1pm ET and 5pm ET on game days
- Late scratches: can happen any time up to ~30 min pre-game
- When a starter is ruled out, EVERY teammate's prop is potentially mispriced
- Books adjust over 5-15 minutes as lines are manually recalculated
- Your model recomputes full distributions in seconds
- **Window size:** 5-15 minutes per major injury update. Multiple updates per day. This fires several times per week.
- Implementation: monitor official injury report + RotoWire + team Twitter accounts (NBA beat reporters often faster than official reports)

**29. Steam move detection (MEDIUM — 1-2 weeks)**
- A "steam move" is when sharp accounts hit a line at multiple books simultaneously, causing rapid cross-book movement
- Detectable by: monitoring line feeds from 5+ books every 30-60 seconds, flagging when 3+ books move same direction within 60 seconds
- If you detect steam direction within 60 seconds, there is residual CLV at slower-moving books
- Sharp money is directional information: if syndicates are betting heavily on one side, they know something
- Signal: bet in the direction of steam at books that haven't adjusted yet
- Limitation: Steam is directional but not always right. Weight by your model's agreement.

**30. Cross-venue arbitrage — guaranteed profit (MEDIUM — 2 weeks)**
- Same event priced such that betting both sides across different venues = guaranteed profit
- Sportsbook prices -110/-110 on game outcome. Kalshi prices same event at 54¢/46¢ (implied 54%/46%). If sportsbook line implies 52.4%/47.6%, you have pure arb on one side.
- Your system scans this continuously across all venues
- **Limitation:** Arb windows close in minutes. Must be automated.
- **Risk:** Correlated settlement (both books settle the same way) = not a risk. But line errors can cause temporary apparent arb that resolves before you get both bets down.

**31. Account rotation — multi-book management (MEDIUM — 1 week)**
- Don't concentrate action at one book
- Track heat score per book (see System 5 detail above)
- Rotate action to cooler books when heat rises
- **Pattern variations to delay limiting:**
  - Vary bet timing within day (not always at open, not always at lineup confirmation)
  - Vary bet sizes (not always the same fraction Kelly)
  - Occasionally bet mainlines (look recreational) — research needed on whether this actually delays limiting
  - Don't always bet the same prop types
- Long-term: migrate volume from sportsbooks to P2P exchanges as accounts age out

**32. P2P exchange market making — the endgame (HARD — longer term)**
- On Novig/ProphetX, you can POST lines as well as match them
- Set lines where your model says you have edge on both sides
- Other bettors match your lines — you collect the edge in aggregate
- This is what a sportsbook does. You're operating a mini-book on a platform that handles settlement.
- No account limiting possible (you're the market maker, not the bettor)
- Requires: well-calibrated model, sufficient bankroll to post meaningful lines, low enough variance that your edge realizes

### STRUCTURAL EDGES — The Market Itself Is Built Wrong

**33. Props priced from box scores, not spatial data (THE CORE THESIS)**
- Books have access to Genius Sports / Hawk-Eye tracking data via enterprise contracts
- But prop pricing teams are small relative to the number of markets they manage
- Props are low-priority markets — less modeling sophistication goes into them vs game lines
- Your CV-derived spatial features capture information that IS in the world but IS NOT in the prop price
- This is a sustained structural edge as long as books don't deeply integrate tracking into props

**34. SGP correlation is mispriced (STRUCTURAL)**
- Books price SGP legs as independent events with a generic correlation discount
- Reality: player stats are jointly distributed (game flow affects all of them simultaneously)
- Blowout: all starters' counting stats are lower (they sit Q4)
- High-tempo game: all players have more possessions, counting stats go up
- Player A's points and Player B's assists are correlated (good ball movement helps both)
- Your possession simulator models the game, not individual stats — naturally captures joint distributions
- When your joint probability ≠ book's formulaic SGP price: edge

**35. Alternate lines mispriced vs mainline (EASY ONCE DISTRIBUTIONS WORK)**
- Books focus modeling resources on mainline accuracy
- Alternate lines (O/U 25.5, 28.5, 31.5 when mainline is 27.5) get less attention
- Your full distribution prices any threshold with equal accuracy
- The tails of your distribution (very high and very low alternates) are where books are most wrong
- Often the alternate lines have better value than the mainline even when mainline is slightly -EV

**36. Early season miscalibration — timing advantage (FREE)**
- Academic research (ScienceDirect) confirms totals and props are most mispriced in first 2-3 weeks of season
- Books don't have current-season data; they're relying on preseason projections and last season's data
- Your model, trained on prior seasons + spatial features, has the same data as the book but better features
- **You start betting on opening night.** This is when the market is maximally inefficient.
- Effect fades as market gains current-season samples. Front-load action in first month.

**37. Individual vs. institutional access — permanent structural moat**
- Individual: hold accounts at 20+ books, operate on prediction markets, access gray-area platforms
- Registered entity: none of the above without regulatory overhead that kills the economics
- This doesn't close. The larger you grow, the more you might consider entity structures, but the core access advantage persists for years.

---

## Data Architecture — Every Source

### Free Tier (Cost: $0)
| Source | URL | Data | Rate Limits |
|---|---|---|---|
| `nba_api` Python package | github.com/swar/nba_api | 70+ endpoints: box scores, PBP, tracking aggregates, shot charts (x/y coords), lineup data, on/off splits | ~600 req/min max; cloud IPs get banned — use residential or add delays |
| PBPStats API | api.pbpstats.com | Possession-level PBP, on/off data, shooting by zone, lineup combos | Reasonable |
| Basketball-Reference | basketball-reference.com | Historical stats 1947-present, advanced metrics, scrapeable | Rate limit carefully, respect robots.txt |
| `shufinskiy/nba_data` | github.com/shufinskiy/nba_data | Pre-scraped PBP from stats.nba.com + pbpstats.com, 1996-present. Ready to use. | One-time download |
| NBA.com tracking pages | nba.com/stats/players/speed-distance | Speed, distance, touches, closest defender distance (aggregated, not raw) | Scrapeable via nba_api LeagueDashPtStats |
| SportVU 2015-16 | github.com/sealneaward/nba-movement-data | 631 games, raw 25fps XY player+ball coordinates. THE ONLY public raw tracking release. | One-time download |
| Kaggle NBA database | kaggle.com/datasets/wyattowalsh/basketball | 64K+ games, 4800+ players, box scores since 1947 | One-time download |
| Kaggle NBA PBP | kaggle.com/datasets/szymonjwiak/nba-play-by-play-data-1997-2023 | Play-by-play 1997-2025 | One-time download |
| Referee assignments | official.nba.com/referee-assignments | Daily ref crew, posted ~9am ET | Scrape daily |
| NBAstuffer referee stats | nbastuffer.com/nba-stats/referee | Game-by-game ref stats, multi-season | Scrapeable |
| Covers.com referee | covers.com/sport/basketball/nba/referees | Ref O/U records, ATS tendencies | Scrapeable |
| Basketball-Reference refs | basketball-reference.com/referees | Ref career directory + stats | Scrapeable |
| NBA injury reports | nba.com/players/injuries | Mandatory filings 1pm/5pm ET game days | Poll 2x/day |
| RotoWire injuries | rotowire.com/basketball/injury-report.php | Injury report + status + news | Scrapeable |
| ESPN injuries | espn.com/nba/injuries | Per-team injury status | Scrapeable |
| BallDontLie | balldontlie.io | Players, games, stats, standings, injuries | Free tier available |
| OddsPortal | oddsportal.com | Historical closing lines, odds movement | Scrapeable (respect rate limits) |
| SportsOddsHistory | sportsoddshistory.com | Archived futures, spreads, totals | Scrapeable |
| The Odds API (free) | the-odds-api.com | Live odds 40+ books, 500 req/mo | 500 req/mo free |
| YouTube highlights | youtube.com | 10-20 min highlight clips, yt-dlp + cookies | Gray area legally, working approach |
| archive.org | archive.org | Some older full games | Availability varies |

### Cheap Tier ($10-80/mo)
| Source | URL | Data | Cost |
|---|---|---|---|
| The Odds API (paid) | the-odds-api.com | Real-time props across 40+ books, enough for production | $20-80/mo |
| Cleaning the Glass | cleaningtheglass.com | Garbage-time-filtered stats, lineup combos, play types | ~$10/mo |
| BigDataBall | bigdataball.com | Validated PBP + odds combined, per-season | $30-50/season |
| Colab Pro | colab.research.google.com | T4/A100 GPU access, longer sessions | $10/mo |
| Vast.ai GPU | vast.ai | RTX 3090 $0.20-0.30/hr, RTX 4090 $0.28-0.32/hr | Pay-per-use |
| RunPod GPU | runpod.io | RTX 4090 $0.34/hr, A100 $1.39/hr. More reliable than Vast. | Pay-per-use |

### Research Resources (Free)
| Resource | What For |
|---|---|
| r/sportsbook | Betting strategy, community signal |
| @cleantheglass, @kirkgoldsberry, @SethPartnow on X | NBA analytics signal |
| arxiv.org (cs.LG, stat.ML) | Latest ML for sports prediction |
| L2M reports (nba.com) | Referee performance data, historical |

---

## The Timing Layer — When To Bet Throughout The Day

Most bettors think about WHAT to bet. The best bettors also know WHEN.

| Time | Event | Action |
|---|---|---|
| ~6am ET | Props first posted | Poll immediately, flag +EV vs model, bet opening lines |
| ~9am ET | Referee assignments posted | Update game model with ref features, re-evaluate all props for that day's games |
| 1pm ET | Mandatory injury report | Poll, update lineup models, re-evaluate all affected props |
| 5pm ET | Final injury report before evening games | Most important update — last official info before tip |
| ~30-60 min pre-game | Starting lineup confirmation | Final re-evaluation, detect any late scratches |
| Any time | Line movement alert (>0.5 pts) | Steam detection trigger, investigate direction |
| Any time | Injury news from reporters | Often faster than official report — monitor Twitter/X |
| Post-game | Results come in | Collect residuals, update calibration, log CLV |

---

## The Learning Loop — How The System Gets Better Every Night

1. **Residual collection:** Every settled bet: record `prediction - actual_outcome` per stat per player
2. **CLV computation:** Every bet: record `your_line - closing_line`. Rolling 7/30/90-day CLV. Positive CLV = real edge. Negative CLV = you're the sucker.
3. **Calibration update:** New residuals → update calibration layer → next predictions more accurate
4. **Feature importance drift detection:** Monthly, compute feature importance. If CV spatial features are losing importance → books are starting to price them → edge decay signal
5. **Monthly model retrain:** Expanding dataset (last season + current season YTD). Validate on holdout before deploying.
6. **Adversarial book learning:** Track which books move lines in what direction and speed. Update book behavior models. Better bet timing over time.
7. **Account health history:** Track which bet patterns triggered limiting at which books. Refine rotation strategy.

---

## The Dashboard — Bloomberg Terminal for Sports Betting

**No existing tool (OddsJam, Unabated, Pikkit, Betstamp) combines:**
- Custom model signals (your CV features, your simulator output)
- Portfolio-level risk management
- Bet tracking with CLV
- Account health monitoring across books

**You'd be building the first integrated quant betting dashboard.**

### Panel Specifications

**Live Opportunity Feed (primary panel)**
- Real-time ranked list of +EV bets across all books
- Columns: Player, Prop, Book, Your Prob, Book Implied Prob, Edge %, Recommended Size, Confidence CI
- Color coded: green = high confidence, yellow = moderate, gray = at threshold
- Auto-refreshes every 30-60 seconds
- Click row → drill into full distribution view

**Odds Stream**
- WebSocket-fed table showing current odds across all books for tonight's games
- Cell-level color flash: green = moved in your favor vs model, red = moved against
- Highlights books that are lagging the market (potential steam window)

**Edge Heatmap**
- Games × Prop Types matrix
- Cell color = edge magnitude at best available book
- Click cell → see book-by-book comparison
- Quickly see where tonight's best opportunities are concentrated

**Player Distribution View**
- Violin plot: your model distribution vs book's implied line
- Shows WHERE your model disagrees with the book
- Confidence intervals overlaid
- Historical calibration: how accurate have your predictions been for this player/prop type?

**Portfolio View**
- All active bets shown as positions
- Correlation heatmap: which bets are moving together?
- Net directional exposure: if all your overs hit vs miss, what's the range?
- Total at-risk capital vs bankroll %

**Bankroll Curve**
- Cumulative P&L over time
- Drawdown shading (red zones = drawdown periods)
- Kelly fraction utilization line
- Rolling Sharpe ratio annotation
- Separate lines by market type (can see which markets are most profitable)

**Book Health Dashboard**
- Per-book cards: bet count (vs ~300 threshold), win rate, avg stake, heat score (composite), days since account opened, estimated days until limiting
- Traffic light: green = healthy, yellow = watch, red = approaching limit
- Auto-triggers already routing less volume to red accounts

**CLV Tracker**
- Rolling CLV by time period and market type
- If CLV trending negative → edge decay alert
- Breakdown: which prop types have best/worst CLV?
- This is your single most important long-term validation metric

**Model Performance Panel**
- Feature importance by prop type (which features are driving predictions)
- Calibration curves: predicted probability vs actual frequency
- R² by prop type over time
- Residual distributions (are errors systematic or random?)

**System Health Panel**
- Data freshness: last successful pull from each API
- Model latency: time from lineup announcement to updated predictions
- Execution status: last successful bet placement per book
- Error log: anything that failed in last 24 hours
- This tells you when something breaks at 3am before you miss opportunities

### Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Frontend | Next.js + React | Already have React skills; SSR + client-side |
| Charting | TradingView Lightweight Charts + Recharts | Financial-grade time series + custom charts |
| Real-time | WebSocket (native or Socket.IO) | Sub-second odds updates |
| State | Zustand or Jotai | Handles high-frequency updates without React storms |
| Tables | TanStack Table + virtualization | Dense grids with 1000+ rows |
| Backend | FastAPI (already built) | WebSocket + REST in one |
| Event bus | Redis Pub/Sub | Fan out odds updates to all connected clients |
| Ops monitoring | Grafana | System health, model latency, data freshness |
| Latency targets | Pre-game: sub-5s. Live alerts: sub-1s. |

---

## Account Longevity Strategy — The Business Problem

**Reality:** You WILL get limited on sportsbooks. It's not if, it's when. The system must be designed to maximize account lifespan across all books and gracefully migrate volume to P2P exchanges as accounts degrade.

**What triggers limiting:**
- Sustained win rate >55% on props (internal model flags you as sharp)
- Bet count approaching ~300 on same account
- Consistent prop-type concentration (always betting same player/market)
- Consistent timing patterns (always betting at open, or always at lineup confirmation)
- High average bet size relative to account norm
- Steam chasing (betting same direction as sharp line moves)

**Mitigation tactics:**
1. **Book rotation:** Spread volume across 6 books. Don't hit any one book for >20% of your total bets.
2. **Market type mixing:** Don't exclusively bet player props. Occasional mainline bets look recreational.
3. **Timing variation:** Bet at open some days, at lineup confirmation others, sometimes split.
4. **Size variation:** Don't always bet the same Kelly fraction. Add some randomness to appear human.
5. **Account diversification:** Consider family member accounts (legally allowed; practically risky — check each book's TOS).
6. **P2P ramp:** As sportsbook accounts age, shift more volume to Novig/ProphetX. No limiting ever.
7. **Monitoring:** Your account health panel tells you BEFORE you get limited, not after.

---

## Revenue Streams — Beyond Bankroll

**Stream 1: Direct betting profits** (primary, requires bankroll)

**Stream 2: Picks/predictions service** (secondary, no bankroll risk)
- Once validated, your model output is a product
- Subscription services charge $50-200/month
- 100 subscribers = $5K-20K/month with zero capital at risk
- Legal question: check Iowa requirements for selling sports picks (likely no license needed for individual)

**Stream 3: Model/API licensing** (longer term)
- License model outputs or API access to other bettors or services
- DFS players would pay for predictive distributions
- Fantasy sports platforms might white-label

**Stream 4: Dashboard as a product** (longer term)
- The quant dashboard itself has standalone value
- If you open-source components and build reputation, there's a path to a SaaS product
- Target: sharp bettors who have their own models but want infrastructure

---

## Multi-Sport Expansion Plan

**Why NBA first:** Basketball has the most granular CV tracking opportunities from broadcast, the deepest player prop markets at sportsbooks, and the most game-level data available free.

**NFL (next):**
- Same downstream infrastructure (odds, execution, risk, dashboard) reuses 100%
- New models needed: different stat distributions, different game flow
- CV challenge: broadcast football has different camera angles, player density is similar but positions cluster differently
- Start with box-score-only NFL models while you adapt CV for football broadcast
- High-value props: passing yards, receiving yards, rushing yards, TDs — similar O/U structure to NBA

**MLB:**
- Different game structure (no shot clock, discrete plate appearances)
- Rich data ecosystem (Statcast: free, extremely detailed)
- Pitcher/batter matchup modeling replaces lineup/scheme modeling
- CV opportunity: pitch trajectory, spin rate, batted ball metrics from broadcast (Statcast does this officially, but your model can add features)

**Soccer:**
- Largest betting market globally
- Genius Sports and similar have deep soccer data feeds
- CV tracking is harder (11 vs 5 players, larger field, lower scoring)
- Start with pre-game match outcome modeling, then player-level shots/assists

**Infrastructure reuse by component:**
- Odds ingestion: 100% reuse (Odds API covers all sports)
- Execution adapters: 100% reuse (same books, different sport)
- Kelly/risk systems: 100% reuse
- Dashboard: 90% reuse (sport-specific panels added)
- Simulator: complete rebuild per sport (game mechanics differ)
- Feature engineering: partial reuse (fatigue, schedule, context features transfer; spatial features sport-specific)

---

## Validation Methodology — How To Prove The Edge Before Risking Money

**The test that matters above all others:**

```
CLV = (your_predicted_probability) - (closing_line_implied_probability_no_vig)
```

If average CLV is positive over 500+ predictions: you have an edge. If not: fix the model.

**Step-by-step validation protocol:**
1. Get historical closing lines for 2024-25 NBA props (OddsPortal has these, or historical Odds API)
2. For each game: what was your model's prediction for each prop?
3. For each prop: what was the no-vig closing probability?
4. Compute CLV for each: your prob - closing prob
5. Average across all predictions
6. Statistical significance test: is average CLV > 0 with p < 0.05?
7. Break down by prop type: where is CLV positive? Where negative?
8. Break down by confidence: is CLV higher on your high-confidence predictions?

**Why closing line?** The closing line is the sharpest estimate of true probability — it reflects all publicly available information after a full day of sharp money has corrected it. Beating the close consistently is the gold standard for having real edge.

**Minimum sample size:** 500+ bets for statistical confidence. 1000+ for robust conclusions by market type.

**The null hypothesis:** Your model has zero edge vs closing lines. If you cannot reject this null, the edge is not real.

---

## Build Sequencing — Phase by Phase

### Phase 0: Validation (Week 1 — DO THIS FIRST)
**Goal: Prove the edge exists before building anything else.**
- Subscribe to Odds API ($20/mo) OR scrape OddsPortal historical
- Pull 2024-25 closing lines for all NBA props
- Run existing model predictions against those lines
- Compute CLV on 500+ predictions
- **Decision gate:** If CLV > 0 with p < 0.05 → proceed. If not → fix model first.

### Phase 1: Foundation Hardening (Weeks 2-4)
**Goal: Solidify the existing system before extending it.**
- Run full 80-game CV ingestion (you have 17, need 63 more)
- Recompute all spatial features at scale
- Validate against SportVU 2015-16 ground truth dataset
- Calibrate model probabilities against historical residuals
- Build the 6 trivial tracking-derivative features (spacing, closeout speed, paint density, transition classification, catch-and-shoot, off-ball movement) — 1-2 days each

### Phase 2: Context Layer (Weeks 5-6)
**Goal: Add free, high-signal context features.**
- Referee assignment scraper + ref features into model
- Travel fatigue index (great-circle + timezone + arrival time)
- Denver altitude flag + other venue effects
- Lineup usage redistribution model (PBPStats on/off data)
- Contract year flag
- Schedule density / rest features

### Phase 3: Core Engine (Weeks 7-10)
**Goal: Wire predictions to live odds, generate ranked opportunities.**
- Odds API integration, multi-book ingestion
- Line Evaluator: simulator distributions vs every available line
- No-vig probability calculator
- Edge ranking and filtering
- Single-book Kelly sizer
- **Paper trading:** log every recommended bet + outcome for 4 weeks

### Phase 4: Execution (Weeks 11-14)
**Goal: Automate bet placement across multiple books.**
- Execution adapters per book (Selenium/Playwright or manual bet slip generation)
- Account health monitor (heat scoring per book)
- Multi-book router with line shopping
- Portfolio tracker (correlation across active bets)
- Drawdown-triggered sizing reduction
- Kill switches (max daily loss, max bets, edge floor)
- **Live deployment:** small real money to validate execution

### Phase 5: Market Expansion (Weeks 15-20)
**Goal: Layer in higher-value markets.**
- Correlation Engine for SGP pricing
- Alternate line evaluation
- Cross-venue arbitrage scanner (sportsbook vs P2P vs Kalshi)
- Novig + ProphetX adapters
- Steam move detector
- Opening line capture automation (6am polling)

### Phase 6: Intelligence Layer (Weeks 15-25, parallel)
**Goal: Widen the moat with advanced models.**
- NBA2Vec player embeddings
- Regime detection (trades, injuries, coaching changes)
- Bayesian in-season updating
- Load management prediction
- Adversarial book model (line movement prediction)
- Shot trajectory CV feature
- PnR detection (rule-based first, then graph model)

### Phase 7: Dashboard (Weeks 12-20, parallel to 4-6)
**Goal: Real-time quant terminal.**
- Next.js + React frontend on existing FastAPI backend
- WebSocket integration for live odds streaming
- All panels: Opportunity Feed → Odds Stream → Edge Heatmap → Distribution View → Portfolio → Bankroll → Book Health → CLV Tracker → Model Performance → System Health
- Mobile-responsive layout

### Phase 8: Learning Loop Automation (Weeks 18-22)
**Goal: System improves automatically every night.**
- Nightly residual collection
- CLV computation and rolling windows
- Calibration layer auto-update
- Feature importance drift detector
- Monthly retrain pipeline
- Edge decay alerting

### Phase 9: Long-Term Sustainability (Weeks 20+)
**Goal: Reduce dependence on sportsbooks.**
- Migrate volume to P2P exchanges as accounts age
- Test market-making on Novig/ProphetX (post lines, collect spread)
- Establish picks service / API revenue stream
- Build account rotation discipline

### Phase 10: Multi-Sport (Post-Season, 2027)
**Goal: Replicate for NFL, MLB, soccer.**
- NFL prop models (box-score first, CV adaptation later)
- MLB models leveraging Statcast
- Soccer pre-game match outcome models
- All reuse: odds ingestion, execution, risk, dashboard
- New per sport: simulator, sport-specific features

### Critical Path Dependencies
- Phase 0 blocks everything (validates the thesis)
- Phase 1 blocks Phase 2-3 (need solid features and calibration)
- Phase 3 blocks Phase 4 (need live signals before automating execution)
- Phase 4 blocks Phase 5 (need single-market working before expanding)
- Phases 6-8 can run parallel to Phases 4-5 once Phase 3 is done

### Concrete Calendar (assuming start late May 2026)
| Week | Date Range | Phase |
|---|---|---|
| 1 | May 18-24 | Phase 0: CLV Validation |
| 2-4 | May 25 - Jun 14 | Phase 1: Foundation |
| 5-6 | Jun 15-28 | Phase 2: Context Layer |
| 7-10 | Jun 29 - Jul 26 | Phase 3: Core Engine + Paper Trading |
| 11-14 | Jul 27 - Aug 23 | Phase 4: Execution |
| 15-20 | Aug 24 - Oct 4 | Phase 5: Market Expansion |
| 12-20 (parallel) | Aug - Oct | Phase 6: Intelligence + Phase 7: Dashboard |
| 21-22 | Oct 5-18 | Phase 8: Learning Loop + Final integration |
| **Oct 19** | **Buffer week** | **Final testing, bugfixes, dry runs** |
| **Oct 22** | **NBA Opening Night** | **GO LIVE — first real money** |

---

## The Open Questions (Research Tasks For Future Sessions)

**Critical (do first):**
1. **CLV validation** — run the closing line test on 2024-25 data immediately. Everything depends on this.
2. **Possession simulator depth** — is current implementation truly possession-level with lineup-dependent transitions, or is it game-level bootstrap? This determines whether SGP pricing and distribution accuracy are real.
3. **Automated bet placement feasibility** — research Selenium/Playwright approach for each book. What's the technical approach? What's the detection risk?

**Important:**
4. **Novig/ProphetX NBA prop liquidity** — test at season start. Is there enough volume to bet meaningful amounts?
5. **SGP pricing reverse-engineering** — empirically test: place SGPs with known correlation structure, compare to what your joint probability predicts. Quantify the mispricing.
6. **SportVU calibration** — download the 2015-16 dataset, validate your CV features against ground truth.
7. **Book API/automation** — does any sportsbook offer an official API? What's the realistic automation approach per book?

**Medium priority:**
8. **PnR detection** — start with rule-based approach (convergence detection). When does it need to become a learned model?
9. **Iowa picks service legality** — does selling predictions commercially require a license in Iowa?
10. **Account longevity empirical testing** — which patterns actually delay limiting vs folklore? Research the betting community's current knowledge.
11. **Edge decay monitoring** — build the feature importance drift detector. When should it alarm?
12. **Load management model** — how well can you actually predict rest days? What's the false positive rate?

**Research tasks (can spawn agents for these):**
13. How do DraftKings and FanDuel compute their SGP correlation discounts empirically?
14. What is the realistic throughput of Selenium-based sportsbook automation (bets per minute)?
15. What are the current Novig/ProphetX NBA market depths and typical contract sizes?
16. Is there any academic work on optimal sportsbook account management to delay limiting?
17. What's the typical timeline from positive CLV detection to profitability in practice?

---

## The Single Most Important Thing To Do First

**Before building anything in the execution layer, before building the dashboard, before adding any new features:**

Run this test:
1. Pull your 2024-25 model predictions (you have 152K prop residuals)
2. Get closing lines for those same props (OddsPortal or historical Odds API)
3. Compute average CLV

If average CLV > 0 and statistically significant: **the edge is real. Build the machine.**
If average CLV ≈ 0 or negative: **fix the model before building execution infrastructure.**

This is the fork in the road. Everything else is downstream of knowing which path you're on.

---

*Update this document as decisions are made, questions are answered, and new gaps are discovered.*
*Next session: start with the CLV validation test, then continue from where this left off.*
