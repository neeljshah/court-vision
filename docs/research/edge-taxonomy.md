# Edge Taxonomy — 37 Enumerated Edges

*Status: Living document. Edges marked **BUILT** are wired in production; **IN PROGRESS** are under active development; **PLANNED** have design specs but no code.*

---

## Overview

This document enumerates every identified source of systematic edge in NBA player prop markets. Edges are grouped into four categories reflecting their origin: information advantages that arise from seeing what others can't; model advantages that arise from thinking about the problem differently; execution advantages that arise from acting faster and cheaper; and structural advantages that arise from the market being built wrong.

The 37 edges are not independent — many compound each other. CV-derived spatial features (edges 1–9) feed the possession simulator (edge 19), which enables joint distribution pricing (edge 20) and SGP exploitation (edge 34). The architecture is designed so that building any one edge reinforces several others.

---

## Category I: Information Edges — You See What Others Can't

### CV-Derived Spatial Features (Edges 1–9)

The primary moat. Sportsbooks price player props using box-score models: season averages, opponent defensive rating, recent game trends. They do not deeply integrate spatial tracking into prop lines. The gap between spatial reality and box-score summary is the exploitable inefficiency.

| # | Name | Status | Build Estimate |
|---|------|--------|----------------|
| 1 | Defender distance distributions | BUILT (17 games) | — |
| 2 | Court spacing — convex hull | BUILT | — |
| 3 | Closeout speed on shooters | PLANNED | 1–2 days |
| 4 | Paint density per possession | PLANNED | hours |
| 5 | Transition vs half-court classification | PLANNED | hours |
| 6 | Catch-and-shoot vs off-dribble detection | PLANNED | 1 day |
| 7 | Off-ball movement quality | PLANNED | 1–2 days |
| 8 | Shot trajectory / release angle | PLANNED | 2 weeks |
| 9 | Pick-and-roll detection | PLANNED | 2–3 weeks |

---

**Edge 1 — Defender Distance Distributions** `BUILT (17 games; retrain at 80)`

Not "open vs contested" — the full continuous distribution of defender distance at shot release, per player, per matchup. FG% varies dramatically by closest-defender distance; Darryl Blackport's research identifies this as the most influential variable in shot outcome prediction beyond shot distance alone. The CV pipeline extracts this post-homography in court coordinates. No retail data source ships it.

- **Academic backing:** Blackport et al. (SportVU-era research), reproduced in NBA.com Closest Defender dataset (aggregated, not per-possession)
- **What it predicts:** FG% above/below expected given volume; conditional over/under probability on points, FGA-derived props
- **SHAP contribution:** Combined CV spatial features = 31% of mass on pts model; Δ R² = +0.08 over API-only baseline
- **Current limitation:** 17-game dataset is narrow for tail markets (blk, stl). Intervals tighten at N=80.

---

**Edge 2 — Court Spacing: Convex Hull of Offensive Players** `BUILT`

Convex hull area of the 4 off-ball offensive players per possession, normalized to half-court dimensions. 5-out spacing versus traditional 4-out-1-in configurations has measurable impact on drive efficiency and kick-out 3P opportunities. Derived trivially from existing tracking homography.

- **What it predicts:** 3PM opportunities, paint touches, assist likelihood, defender compression
- **SHAP contribution:** `spacing_score` is one of three moat features; combined CV = 31% of pts model
- **Build path:** Already wired; quality to improve with N=80 games

---

**Edge 3 — Closeout Speed on Shooters** `PLANNED — 1–2 days`

Defender velocity vector toward ball-handler after kick-out pass, measured in km/h in court coordinates. Slow closeout → open 3P attempt. Fast closeout → contested pull-up or ball reversal. Second Spectrum advertises "contest quality" as a headline commercial metric; this is a broadcast approximation.

- **What it predicts:** Per-player 3P% above/below expectation given shot volume; 3PM prop edge
- **Implementation:** Compute velocity from consecutive frame positions of tracking ID assigned to closest defender at catch point

---

**Edge 4 — Paint Density Per Possession** `PLANNED — hours`

Count of players within paint polygon per frame, averaged over possession. High paint density suppresses drive completions, reduces free throw attempts, increases perimeter shot frequency.

- **What it predicts:** FTA rate, points in paint vs perimeter split, drive efficiency degradation
- **Implementation:** Paint polygon is constant in court coordinates post-homography; trivial count

---

**Edge 5 — Transition vs Half-Court Classification** `PLANNED — hours`

Binary classification: if all 5 offensive players cross half-court within N seconds of possession start, possession is in transition. Transition possessions have higher pace, higher scoring efficiency, different shot-type distributions.

- **What it predicts:** Pace model, points per possession projection, all counting stats in fast-break-heavy matchups
- **Implementation:** Rule-based on player positions at frame T and frame T+N

---

**Edge 6 — Catch-and-Shoot vs Off-Dribble Detection** `PLANNED — 1 day`

Was the ball-handler stationary (velocity < threshold) for N frames before shot release? C&S shots carry significantly higher FG% than off-dribble for most players; the effect varies by player and matchup.

- **What it predicts:** Per-player FG% given shot type distribution; points model calibration by shot type
- **Implementation:** Velocity thresholding on tracked player position over 5-10 frames pre-release

---

**Edge 7 — Off-Ball Movement Quality** `PLANNED — 1–2 days`

Total distance traveled by non-ball-handlers per possession. High off-ball movement correlates with active offensive schemes that create open looks; low movement indicates passive spacing or call plays.

- **What it predicts:** Scheme quality classification; open shot generation rate; points from catch-and-shoot opportunities
- **Academic backing:** Second Spectrum publishes aggregate off-ball movement as a commercial product feature
- **Implementation:** Sum of Euclidean distances per player per possession for all non-handler tracks

---

**Edge 8 — Shot Trajectory / Release Angle** `PLANNED — 2 weeks`

Parabolic curve fitting to ball trajectory on shot attempts. Extract release angle (degrees from horizontal) and entry angle at rim. NBA's own data: release angles in the 45–55° range correlate with higher make rates; entry angle below 32° is a "flat" shot with lower tolerance for rim error.

- **What it predicts:** FG% independent of defender distance; complements edge 1
- **Academic backing:** Haralick et al. on trajectory reconstruction from monocular video; 2024 arxiv work on shot arc reconstruction from broadcast
- **Implementation:** Faster R-CNN ball segmentation + Kalman smoother on trajectory + parabola fit in court coordinates

---

**Edge 9 — Pick-and-Roll Detection** `PLANNED — 2–3 weeks`

Spatial-temporal detection of screen-setting: two offensive players converge, defender paths cross. PnR is the most common NBA play type; scheme classification enables PnR-specific possession outcome models. Simple rule-based approach first, then spatial-temporal graph model.

- **What it predicts:** Which player (ball-handler vs roller) receives the scoring opportunity; assist-vs-direct-score probability
- **Academic backing:** TacticExpert (arXiv:2503.10722, 2025) — spatial-temporal graph models for tactical action recognition in basketball
- **Implementation (v1):** Rule-based convergence detection (two players within X feet, movement vectors converging). Implementation (v2): STGNN trained on labeled PnR sequences.

---

### Context Features (Edges 10–18)

Free, underused, high signal. These require data ingestion (not CV) and can be built independently of the video pipeline.

| # | Name | Status | Build Estimate |
|---|------|--------|----------------|
| 10 | Referee foul rates and pace impact | IN PROGRESS | 1 day |
| 11 | Travel fatigue index | PLANNED | 1–2 days |
| 12 | Denver altitude adjustment | PLANNED | hours |
| 13 | Lineup-dependent usage redistribution | PLANNED | 1 week |
| 14 | Load management / rest prediction | PLANNED | 2 weeks |
| 15 | Contract year effect | PLANNED | hours |
| 16 | NBA2Vec player embeddings | PLANNED | 2 weeks |
| 17 | SportVU 2015-16 calibration dataset | PLANNED | 1 week |
| 18 | Venue-specific and situational effects | PARTIAL | incremental |

---

**Edge 10 — Referee Foul Rates and Pace Impact** `IN PROGRESS — 1 day`

NBA posts daily ref crew assignments at official.nba.com/referee-assignments ~9am ET. NBAstuffer and Basketball-Reference carry multi-season ref stats: personal foul rate per game, FTA rate, pace impact, home/away tendency. An Oregon State study found statistically significant foul-calling biases in NBA officiating; a 2025 Journal of Sports Economics paper analyzed L2M report data for referee performance near spread.

**The timing edge:** Props are posted before ref assignments. At 9am, when refs are announced, lines have not fully adjusted. Your model updates in seconds. The window is 10–20 minutes while books manually review and recalibrate FTA-sensitive props.

- **What it predicts:** FTA rate (direct), pace (indirect → all counting stats), total points
- **Data sources:** `official.nba.com/referee-assignments`, `nbastuffer.com/nba-stats/referee`, `covers.com/sport/basketball/nba/referees`
- **Implementation:** Morning scrape job at 9am ET; look up ref ID → historical foul/pace stats → inject as model features

---

**Edge 11 — Travel Fatigue Index** `PLANNED — 1–2 days`

Beyond the binary back-to-back flag. A continuous fatigue index computing:
- Great-circle flight distance between cities
- Timezone crossing magnitude and direction (westward travel is harder due to circadian phase advance)
- Estimated arrival time relative to game time
- Days since last full rest day
- Cumulative schedule density over prior 7 days

West Coast teams playing early-window East Coast games consistently underperform; the circadian misalignment effect is well-documented in NBA scheduling literature.

- **What it predicts:** All counting stats (fatigue reduces uniformly); guard scoring and assists most sensitive
- **Data sources:** Team schedule (nba_api), city coordinate lookup
- **Implementation:** `geopy.distance.great_circle` + timezone offset table + schedule density rolling sum

---

**Edge 12 — Denver Altitude Adjustment** `PLANNED — hours`

Denver has the largest home court advantage in NBA history: .652 all-time home win%, .350 away (.302 delta). The mechanism is altitude — reduced oxygen density increases metabolic cost of anaerobic bursts. The visiting-team effect peaks in Q3–Q4 (altitude effect accumulates over game duration). Sportico confirmed this after controlling for team quality; ESPN documented it during the 2023 Finals.

- **What it predicts:** Visiting player performance decay in second half; lower counting stats for visitors; Nuggets home overs
- **Implementation:** Binary "visiting team in Denver" flag; optional: continuous altitude-weighted feature using elevation data for all arenas (Salt Lake City is also elevated at 4,226 ft)

---

**Edge 13 — Lineup-Dependent Usage Redistribution** `PLANNED — 1 week`

When a key player is ruled out, usage redistributes to teammates according to their on/off data. PBPStats API provides per-player on/off splits: when Player A sits, Player B's usage rate increases by X%. A usage redistribution model computes new usage shares for all teammates given any subset of absences.

**The timing edge:** Late scratches occur 30–60 minutes pre-game. Prop lines adjust over 5–15 minutes as books manually recalculate. Your model recomputes all affected distributions in seconds. Every teammate's prop is stale during that window.

- **Data sources:** PBPStats API (api.pbpstats.com), NBA injury reports
- **Implementation:** Offline: build usage-redistribution lookup table per player pair per team. Online: when scratch detected, look up redistribution, push to simulator.

---

**Edge 14 — Load Management / Rest Prediction** `PLANNED — 2 weeks`

Predictive signals for unannounced rest decisions:
- Minutes trend over last 7 games
- Schedule density (3-in-4, 4-in-6 patterns)
- Player age and injury history
- NBA Player Participation Policy constraints
- Team's current win/loss position relative to playoff seeding

If you predict a rest day 6–12 hours before announcement: every line for that player is stale, and every teammate's prop reprices upward.

- **Academic backing:** arXiv:2603.26935 (2026) addresses the "healthy-worker survivor effect" in NBA injury and rest modeling — selection bias in observational load management data
- **Implementation:** Binary classification model on historical rest decisions, trained on features above; predict probability of rest each morning for players flagged by schedule density

---

**Edge 15 — Contract Year Effect** `PLANNED — hours`

Players in the final year of their contract statistically perform differently — motivation effect. Salary and contract data is public (spotrac.com, basketball-reference.com). Feature: boolean "contract year" flag per player-season. Effect sign varies by player type (some shrink under pressure, some elevate).

- **Implementation:** Annual lookup from spotrac or basketball-reference contract tables; flag players in last year of deal

---

**Edge 16 — NBA2Vec Player Embeddings** `PLANNED — 2 weeks`

Word2Vec-style embeddings trained on 3.5M+ play-by-play sequences. Each player represented as an 8-dimensional vector in which positional roles emerge without supervision. Players similar in embedding space play similar basketball roles.

- **Academic backing:** arXiv:2302.13386 — NBA2Vec: Dense feature representation for NBA players
- **Uses:**
  - Lineup quality scoring: sum embedding vectors → lineup compatibility metric
  - Counterfactual simulation: "what would Player X's stats be with different teammates?"
  - Cold-start for new players / rookie estimates: find embedding-space neighbors
  - Trade impact modeling: player joins new team → find historical embedding-space neighbors who made same transition → prior for post-trade performance

---

**Edge 17 — SportVU 2015-16 Calibration Dataset** `PLANNED — 1 week (one-time)`

The only public release of raw NBA tracking data: 631 games at 25fps XY coordinates for all 10 players plus ball, available at `github.com/sealneaward/nba-movement-data`. Use case: validate broadcast CV-derived spatial features against ground-truth tracking.

- **Method:** For any 2015-16 game where CV pipeline can be run, compare defender distance estimates, spacing measurements, etc. against SportVU ground truth. Quantify error → calibrate.
- **Why it matters:** This determines whether your CV features are signal or noise at the precision you're computing them. The Δ R² = +0.08 figure needs this validation to be credible.

---

**Edge 18 — Venue-Specific and Situational Effects** `PARTIAL`

Incrementally-buildable features already partially wired:
- Home court advantage (modeled as residual from neutral-site expected performance)
- Back-to-back road game performance (different from home B2B)
- Rest advantage delta (3+ days rest vs B2B opponent)
- Playoff vs regular season (starters play more minutes, different strategic intensity)
- Early vs late regular season (teams know each other better; playoff implications)

---

## Category II: Model Edges — You Think About the Problem Differently

| # | Name | Status | Build Estimate |
|---|------|--------|----------------|
| 19 | Full probability distributions | BUILT (needs calibration) | — |
| 20 | Joint stat distributions for SGP pricing | PLANNED | 2–3 weeks |
| 21 | Regime detection | PLANNED | 1–2 weeks |
| 22 | Bayesian in-season updating | PLANNED | 1–2 weeks |
| 23 | Adversarial book model | PLANNED | 3–4 weeks |
| 24 | Counterfactual simulation | PLANNED | builds on edge 16 |
| 25 | RL-optimized bet timing | PLANNED | longer term |

---

**Edge 19 — Full Probability Distributions, Not Point Estimates** `BUILT — needs calibration`

Every other retail tool predicts a number. The possession simulator generates a distribution. `P(pts > 27.5) = 52%` is a weak signal; `P(pts > 27.5) = 62%` with a tight confidence interval is a strong bet. Distributions enable pricing of any line threshold — mainline, alternates, and SGP legs alike.

- **Required calibration work:** Run Platt scaling or isotonic regression on 152K prop residuals. Calibration curves (reliability diagrams) must show predicted probabilities matching empirical frequencies. See [calibration.md](../models/calibration.md).

---

**Edge 20 — Joint Stat Distributions for SGP Pricing** `PLANNED — 2–3 weeks`

When evaluating a multi-leg Same Game Parlay: run the possession simulator for ALL legs simultaneously and extract joint probability from the simulation output. Compare to the book's SGP price (which uses a formulaic correlation discount). When joint probability > book's implied probability: +EV SGP.

This is a structural exploit — see edge 34 for the structural argument. This edge is the model implementation of it.

- **Implementation:** Pass multi-leg SGP specification to simulator; record what fraction of 10K paths have all legs hit simultaneously; compare to book's quoted SGP price after no-vig conversion

---

**Edge 21 — Regime Detection: Role and Situation Changes** `PLANNED — 1–2 weeks`

Players' roles change during a season. A model trained on season-level data may not reflect current reality. Regime change triggers: trade, teammate injury, coaching change, lineup shift, return from injury.

- **Implementation:** Monitor NBA transactions feed + lineup data for trigger events. After regime change: weight recent games more heavily (exponential decay on historical game weight), flag reduced model confidence, widen confidence intervals until new-regime sample size reaches threshold.

---

**Edge 22 — Bayesian In-Season Updating** `PLANNED — 1–2 weeks`

Prior at season start: pre-season model trained on historical data. Posterior after each game: Bayesian update on player skill parameters. The posterior becomes more accurate as the season progresses; books recalibrate more slowly (they manage too many markets to give each one full attention).

- **Technical approach:** Conjugate priors on player skill distributions (Normal-Normal for counting stats); update mean and variance each game; shrink toward prior early in season, release to observed data after ~15 games.

---

**Edge 23 — Adversarial Book Model: Line Movement Prediction** `PLANNED — 3–4 weeks`

Model how each book sets and adjusts lines. Data: poll odds every 5–10 minutes from open to tip, track movement direction and magnitude. Features: which books lead price discovery (Circa and BetCRIS as sharp market-maker proxies in the US; Pinnacle closes are used as ground truth but not accessible pre-game), lag times between books, movement speed distribution per book.

Goal: predict the direction of line movement before it happens. When you can predict a line will move from O27.5 to O26.5, bet O27.5 immediately before the adjustment.

Also: detect steam moves — when sharp accounts hit multiple books simultaneously, movement is fast and directional. See edge 29.

---

**Edge 24 — Counterfactual Simulation** `PLANNED — builds on edge 16`

Using NBA2Vec embeddings + possession simulator: "what would Player X's stats look like if Player Y was on the floor instead of Player Z?" Primary application: trade deadline. Player joins new team. Find historical players with similar embeddings who made the same transition. Use their performance delta as a prior.

Books reprice slowly after trades. This counterfactual provides an early estimate that is systematically better than mean-reversion assumptions.

---

**Edge 25 — RL-Optimized Bet Timing** `PLANNED — longer term`

Current heuristic: bet at line open (best CLV) and again at lineup confirmation. RL approach: train agent on historical line movement data to decide when to bet given current line, model confidence, time until game, expected movement direction.

- **Academic backing:** ICAART 2024 — XGBoost + RL for dynamic wager placement
- **Technical approach:** Conservative Q-Learning (CQL) for offline RL — trains without live exploration on historical movement data
- **Expected improvement:** 0.5–1% CLV improvement from optimal timing. Meaningful at scale; not worth building before the core system is running.

---

## Category III: Execution Edges — You Act Faster and Cheaper

| # | Name | Status | Build Estimate |
|---|------|--------|----------------|
| 26 | Multi-book line shopping | PARTIAL | 1 week |
| 27 | Opening line capture | PLANNED | automate first |
| 28 | Injury/lineup news speed | PLANNED | 1 week |
| 29 | Steam move detection | PLANNED | 1–2 weeks |
| 30 | Cross-venue arbitrage | PLANNED | 2 weeks |
| 31 | Account rotation | PLANNED | 1 week |
| 32 | P2P exchange market making | PLANNED | longer term |

---

**Edge 26 — Multi-Book Line Shopping** `PARTIAL — 1 week`

The same prop can differ by 1–2 points across DraftKings, FanDuel, BetMGM, Caesars, bet365. Always buy the best number. Research shows consistent line shopping adds 1–3% ROI vs single-book betting. At 5–12% vig, this is often the difference between profitable and unprofitable.

- **Implementation:** The Odds API normalizes props across ~40 books in one call ($20–80/mo). Current system polls but routing logic needs full multi-book comparator.

---

**Edge 27 — Opening Line Capture** `PLANNED — automate first`

Props are posted 12–24 hours before tip, often at 6am ET. Opening lines have maximum error — sharp money has not corrected them. Research shows bets placed 24+ hours pre-game average +1.2% CLV; final-hour bets average −0.5%.

- **Implementation:** 6am ET polling job; compare newly-posted lines against model; flag any +EV immediately; auto-queue for placement.

---

**Edge 28 — Injury/Lineup News Speed** `PLANNED — 1 week`

Mandatory injury reports: 1pm and 5pm ET game days. Late scratches: any time up to ~30 minutes pre-game. When a starter is ruled out, every teammate's prop is potentially mispriced. Books adjust over 5–15 minutes as lines are manually recalculated. Your model recomputes full distributions in seconds.

**Window size:** 5–15 minutes per major injury event. Several events per week. This fires multiple times per week during the regular season.

- **Data sources:** NBA official injury report, RotoWire, beat reporters on X (often faster than official)
- **Implementation:** Poll official report 2× per day; monitor RotoWire RSS; optional X/Twitter monitor for credible beat reporters

---

**Edge 29 — Steam Move Detection** `PLANNED — 1–2 weeks`

A steam move occurs when sharp accounts hit a line at multiple books simultaneously, causing rapid cross-book movement. Detectable by monitoring 5+ book feeds every 30–60 seconds and flagging when 3+ books move the same direction within 60 seconds.

If you detect steam direction within 60 seconds, there is residual CLV at slower-moving books. Sharp money is directional information.

- **Signal:** Bet in the direction of steam at books that haven't adjusted yet
- **Weight:** Steam is directional but not always correct; weight by your model's own directional agreement

---

**Edge 30 — Cross-Venue Arbitrage** `PLANNED — 2 weeks`

Same event priced such that betting both sides across different venues guarantees profit. Example: sportsbook prices -110/-110 (52.4% implied per side). Kalshi prices same event at 54¢/46¢. The sportsbook over-side vs Kalshi under is a risk-free arb.

- **Limitation:** Windows close in minutes; must be automated
- **Scanner:** Continuous comparison across sportsbooks, P2P exchanges, and Kalshi for every active market

---

**Edge 31 — Account Rotation** `PLANNED — 1 week`

Track heat score per book (bet count, win rate, bet velocity, prop type concentration). Auto-rotate action to cooler books as heat rises. Pattern variations to delay limiting: vary bet timing, vary bet sizes, bet occasional mainlines to appear recreational.

See [account-longevity.md](../strategy/account-longevity.md) for full limiting model.

---

**Edge 32 — P2P Exchange Market Making** `PLANNED — longer term`

On Novig and ProphetX, post lines rather than match them. Set prices where your model has edge on both sides. Other bettors match your lines; you collect the edge in aggregate. No account limiting possible — you are the market maker.

- **Requirement:** Well-calibrated model, sufficient bankroll to post meaningful lines, low enough variance that edge realizes before a bad run forces withdrawal.

---

## Category IV: Structural Edges — The Market Itself Is Built Wrong

| # | Name | Status | Notes |
|---|------|--------|-------|
| 33 | Props priced from box scores | PERMANENT | The core thesis |
| 34 | SGP correlation mispriced | STRUCTURAL | Formulaic vs model-derived |
| 35 | Alternate lines mispriced | STRUCTURAL | Mainline focus leaves tails soft |
| 36 | Early season miscalibration | RECURRING | Fires every October |
| 37 | Individual vs institutional access | PERMANENT | Structural moat |

---

**Edge 33 — Props Priced from Box Scores, Not Spatial Data** `PERMANENT`

Books have access to Genius Sports and Hawk-Eye tracking data via enterprise contracts. But prop pricing teams are small relative to the number of markets they manage. Props are low-priority markets — less modeling sophistication relative to game lines. The CV-derived spatial features this system extracts capture information that exists in the world but does not exist in the prop price. This structural gap persists as long as books do not deeply integrate player-level tracking into prop lines.

**The window:** 1–3 years before Genius Sports or Sportradar ships a tracking-integrated prop pricing product at scale.

---

**Edge 34 — SGP Correlation Is Mispriced** `STRUCTURAL`

Books price Same Game Parlays using a formulaic correlation discount applied to individual leg probabilities. The formula is not model-derived. The possession simulator produces joint distributions naturally because it simulates the entire game. When blowout probability is high, all starting-player counting stats are lower (garbage time). When the pace is high, all counting stats go up. When two players share ball-handler roles, their assists are positively correlated. The book's generic discount is wrong in both sign and magnitude depending on the game context.

**Mechanism:** When `P(all legs hit | simulator)` > `P(all legs hit | book's SGP price)`, there is +EV in the SGP.

---

**Edge 35 — Alternate Lines Mispriced vs Mainline** `STRUCTURAL`

Books concentrate modeling resources on mainline prop accuracy. Alternate lines (O27.5, O24.5, O30.5 when mainline is O27.5) get less attention. Your full distribution prices any threshold with equal accuracy. Tails of the distribution (very high and very low alternates) are where books are most wrong.

Often the alternate lines have better value than the mainline even when the mainline is slightly −EV.

---

**Edge 36 — Early Season Miscalibration** `RECURRING — fires every October`

Academic research confirms totals and props are most mispriced in the first 2–3 weeks of each season (ScienceDirect). Books lack current-season data and rely on preseason projections and prior-season means. Your model, trained on prior seasons plus spatial features, has the same data as the book but better features.

**Action:** Front-load bet volume in October and early November when the market is maximally inefficient. Effect fades as book gains current-season samples.

---

**Edge 37 — Individual vs Institutional Access** `PERMANENT`

Individuals can hold accounts at 6+ sportsbooks simultaneously, operate on prediction markets, access gray-area platforms (Novig, ProphetX), bet on Kalshi. Registered investment entities cannot hold DraftKings accounts without regulatory overhead that kills the economics. This access advantage persists regardless of system scale — in fact, the advantage compounds as sportsbooks tighten their institutional-bettor detection while leaving individual accounts more latitude.

See [competitive-landscape.md](competitive-landscape.md) for the full structural argument on why large quant firms cannot enter this market.

---

## Build Priority Matrix

| Priority | Edges | Rationale |
|----------|-------|-----------|
| P0 — Validate first | 19 (calibration) | Must confirm edge exists before building anything else |
| P1 — Trivial, high signal | 3, 4, 5, 6, 7, 10, 11, 12, 15, 18 | 1–2 days each; directly improves model features |
| P2 — Core infrastructure | 26, 27, 28, 31 | Enable profitable operation |
| P3 — High leverage | 13, 20, 34, 35 | SGP + lineup edges compound other advantages |
| P4 — Moat deepening | 8, 9, 16, 17, 21, 22, 23 | Require meaningful build but widen the moat significantly |
| P5 — Long term | 24, 25, 30, 32, 33, 36, 37 | Structural; some are free (36, 37), some are complex |

---

*See [MASTER_PLAN.md](../../MASTER_PLAN.md) for the full strategic context. See [validation-methodology.md](validation-methodology.md) for how to verify that these edges produce real CLV.*
