# System Overview — The 5 Core Systems

*Reference document — the 5 core systems and how they interconnect.*

---

## Architecture Principle

The 75 trained models are not the system. They are components. Everything flows through five systems. Understanding those five systems — and how they interconnect — is the prerequisite for understanding any individual component.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BROADCAST VIDEO                             │
│                    (17 games → 80 target)                           │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CV PIPELINE                                    │
│  YOLOv8n → SIFT homography → Kalman/Hungarian → OSNet re-ID        │
│  Output: defender_distance, spacing_score, legs_fatigue, ...        │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ (CV spatial features)
        ┌───────────────────┤
        │ (API features)    │
        ▼                   ▼
┌───────────────────────────────────────────────────────────────────┐
│                  SYSTEM 1: POSSESSION SIMULATOR                   │
│   Lineup-dependent transition matrices + 10K Monte Carlo paths    │
│   Output: P(stat > X) for every player, every stat, any X        │
└───────────────────────────┬───────────────────────────────────────┘
                            │ (full distributions)
        ┌───────────────────┴────────────────────┐
        ▼                                        ▼
┌────────────────────────┐          ┌───────────────────────────────┐
│ SYSTEM 2: LINE         │          │ SYSTEM 3: CORRELATION ENGINE  │
│ EVALUATOR              │          │                               │
│ Model prob vs          │          │ Joint distributions for SGP   │
│ book implied prob      │          │ pricing; portfolio correlation │
│ Edge = Δprobability    │          │ across active bets            │
└───────────┬────────────┘          └──────────────┬────────────────┘
            │ (+EV opportunities)                  │
            └──────────────┬───────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                  SYSTEM 4: KELLY SIZER                           │
│   Edge × confidence × bankroll × correlation → bet size         │
│   Fractional Kelly with Ledoit-Wolf shrinkage on correlated legs │
│   Drawdown circuit breakers                                      │
└──────────────────────────┬───────────────────────────────────────┘
                           │ (sized bets)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                 SYSTEM 5: EXECUTION ROUTER                       │
│   Best price → Account health → Book limits → P2P preference    │
│   Adapters: DK, FD, BetMGM, Caesars, bet365, Fanatics,         │
│   Novig, ProphetX, Kalshi                                        │
└──────────────────────────────────────────────────────────────────┘
```

---

## System 1: Possession Simulator

**The centerpiece.** Every other tool predicts a number. This generates a distribution.

The simulator runs the game possession-by-possession using lineup-dependent transition matrices. 10,000 Monte Carlo paths per game produce a full probability distribution over every player's every stat.

**Why distributions matter:**
- Price any line, not just the mainline. If the book posts O/U 27.5 but also offers alternates at 24.5 and 30.5, the distribution prices all three simultaneously.
- Confidence intervals: `P(pts > 27.5) = 52%` is a weak signal. `P(pts > 27.5) = 62%` with a tight CI is a strong bet.
- SGP pricing: joint probability of correlated legs requires modeling them together. The simulator does this naturally.

**Inputs:**
- Lineup on floor per possession (NBA API)
- CV spatial features: defender_distance, spacing_score, legs_fatigue
- Context: referee crew, rest days, altitude, travel fatigue index
- Game state: score differential, time remaining (for garbage time modeling)
- Player embeddings (NBA2Vec — planned)

**Possession mechanics:**
- Lineup-dependent possession outcome probabilities
- Shot selection per player given defensive scheme
- Substitution patterns per coach per game state
- Garbage time threshold (starters sit in blowouts)
- Foul trouble logic (player at 3 fouls in Q2 sits)

**Output:** `P(stat > X)` for any threshold X, for every player, for every stat.

Implementation: [`src/prediction/win_probability.py`](../../src/prediction/win_probability.py), [`src/prediction/player_props.py`](../../src/prediction/player_props.py)

---

## System 2: Line Evaluator

Real-time comparison of simulator output against every available market line across all books and venues.

**Mechanics:**
1. Poll Odds API every 30–60 seconds for live lines from 40+ books
2. For each prop line at each book: compute implied probability (Shin devig)
3. Compare to simulator's probability for same outcome
4. `Edge = simulator_probability - book_implied_probability`
5. Rank all opportunities by `edge × confidence × liquidity`
6. Filter by: minimum edge threshold, book health, correlation with existing bets

**Timing triggers** — re-evaluate immediately when:
- New prop line posted (~6am ET)
- Referee assignments announced (~9am ET)
- Injury report filed (1pm and 5pm mandatory)
- Starting lineup confirmed (~30–35 min pre-game)
- Late scratch announced (any time)
- Line moves > 0.5 points (steam detection)

See [timing-layer.md](../strategy/timing-layer.md) for the full timing architecture.

---

## System 3: Correlation Engine

**The SGP opportunity:** Books price Same Game Parlays by multiplying individual leg probabilities with a generic correlation discount. Your possession simulator generates joint distributions naturally. When the book's discount is wrong, that's edge.

**Example:** "Player A over 27.5 points AND Player B over 7.5 assists." These are positively correlated (both benefit from high-tempo efficient offense). The book might price this as `P(A>27.5) × P(B>7.5) × 0.90`. Your simulator says the joint probability is higher because both fire in the same game scenarios. That difference is pure edge.

**Also handles:**
- Multi-game parlays (correlation in same-direction totals when league-wide pace is high)
- Portfolio correlation: all active bets → how correlated is total exposure?
- Ledoit-Wolf shrinkage on correlation matrix (raw N=80 game sample is rank-deficient)

Implementation: [`src/prediction/betting_portfolio.py`](../../src/prediction/betting_portfolio.py)

---

## System 4: Kelly Sizer

**Inputs:** Edge, confidence interval, current bankroll, correlation with existing bets, book-specific max bet limit, current drawdown state.

**Kelly fraction:**
```
f* = edge / (1 - probability_of_loss)
```
Full Kelly is too aggressive under parameter uncertainty. The system uses fractional Kelly:

| Tier | k multiplier | When |
|------|-------------|------|
| Quarter Kelly | 0.25 | < 50 calibrated observations; or drawdown trigger |
| Half Kelly | 0.50 | Standard; recommended starting point |
| Three-quarter Kelly | 0.75 | High-confidence tier (future; not yet wired) |

**Portfolio-aware modification:** If 5 bets share the same game or correlated lineup, Kelly fraction for each decreases. Naive Kelly on correlated props overstakes by 20–40% in simulation.

**Drawdown circuit breakers:**
- 10% bankroll drawdown → reduce all sizing to half Kelly
- 20% drawdown → reduce to quarter Kelly
- 30% drawdown → suspend all betting, alert, manual review required

**Position limits:**
- Total portfolio exposure: ≤ 20% of bankroll per slate
- Per-game exposure: ≤ 5% of bankroll
- Per-player exposure: ≤ 8% of bankroll
- Correlated-cluster cap: ≤ 15% allocated to any player-pair cluster

Implementation: [`src/prediction/betting_portfolio.py`](../../src/prediction/betting_portfolio.py)

---

## System 5: Execution Router

Routes each sized bet to the optimal venue.

**Routing priority:**
1. Best available price (line shopping — always buy the best number)
2. Account health (avoid books at heat threshold)
3. Max bet limits at each book
4. Correlation with existing bets at same book
5. P2P if price is within 0.5 points of best sportsbook price (zero vig compensates)

**Account health monitor per book:**
- Bet count (flag at 250, approaching ~300 limit trigger)
- Win rate (flag if > 55% sustained over 50+ bets)
- Bet velocity (bets per day — unnatural consistency triggers review)
- Prop type concentration (same markets → faster limits)
- Heat score: composite of all above
- Auto-rotation: when heat score exceeds threshold, stop routing to that book

**Book adapters:**
- DraftKings, FanDuel, BetMGM, Caesars, bet365, Fanatics (sportsbooks; manual queue or Playwright)
- Novig, ProphetX (P2P; API where available)
- Kalshi (CFTC-regulated exchange; limit orders preferred for maker rebates)

Implementation: [`api/execution_router.py`](../../api/execution_router.py), [`src/execution/`](../../src/execution/)

---

## Data Flow Summary

```
Broadcast video
    │
    ▼
CV pipeline → CV features (defender_dist, spacing, fatigue)
                    │
NBA API ────────────┼──→ Feature store (timestamped for walk-forward)
                    │
                    ▼
              75 prop models
                    │
                    ▼
         Possession simulator (10K Monte Carlo)
                    │
                    ▼
         ┌──────────┴──────────┐
         ▼                     ▼
    Line evaluator       Correlation engine
         │                     │
         └──────────┬──────────┘
                    ▼
              Kelly sizer
                    │
                    ▼
           Execution router → DK / FD / BetMGM / Novig / Kalshi
                    │
                    ▼
             CLV tracker → residuals → nightly calibration update
```

---

*See [cv-pipeline.md](cv-pipeline.md) for the CV layer. See [possession-simulator.md](possession-simulator.md) for simulator mechanics. See [execution-engine.md](execution-engine.md) for book adapters and routing.*
