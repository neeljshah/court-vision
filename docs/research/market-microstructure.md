# Market Microstructure — How Books Price Props and Where They're Wrong

*Status: Research document. Updated 2026-05-10.*

---

## How Sportsbooks Set Player Prop Lines

### The Pricing Model

Player props at US retail sportsbooks are priced by a small team working through a large market menu. A typical NBA game day has 8–15 games, each with 10+ players per game, each with 5–8 prop types (points, rebounds, assists, 3PM, blocks, steals, turnovers), each with a mainline plus several alternates. That's 4,000–10,000+ individual markets per slate.

The pricing model is primarily **box-score driven**:
- Season average for the stat
- Rolling 5 and 10-game average (trend detection)
- Opponent defensive rating (specifically position-adjusted DRTG)
- Back-to-back flag
- Home/away split

This is what the prop pricing team can compute quickly enough to set lines across the full slate before the 6am posting. It is not what a sophisticated model would use if it had unlimited time.

### The Vig Structure

Standard NBA prop vig:

| Format | Implied vig | Break-even win rate |
|--------|-------------|---------------------|
| -110 / -110 | 4.55% | 52.38% |
| -115 / -115 | 6.52% | 53.49% |
| -120 / -120 | 9.09% | 54.55% |

Most retail books post -110/-110 on mainline props. Some books post -115/-115 on lower-liquidity markets. Alternate lines (e.g., O31.5 when mainline is O27.5) frequently carry -115 or worse on both sides.

**Why this matters:** At -110, you need 52.38% to break even. At P2P exchanges (Novig, ProphetX), you need 50.01%. The vig floor is the cost of doing business at retail books; exploiting P2P is the endgame.

### Shin Devig

To compute true edge, remove the book's vig before comparing to model probability. The Shin (1992) method estimates a single insider-trading probability *z* and corrects:

```
p_true = (p_observed - z) / (1 - 2z)
```

*z* is solved numerically per market. On NBA mainline props, *z* ≈ 0.02–0.04. On lower-liquidity alternates and exotic markets, *z* rises. The Shin method handles the favourite-longshot bias better than symmetric power-sum methods, which over-correct for the bias on longer-priced outcomes.

Implementation: [`src/prediction/betting_edge.py`](../../src/prediction/betting_edge.py)

---

## Where Books Are Wrong

### Systematic Errors

**Spatial data is not in the price.** This is the core finding. Books have access to Genius Sports and Hawk-Eye tracking enterprise contracts, but prop pricing teams do not deeply integrate player-level spatial data. The gap between what tracking data shows (defender distance, spacing, fatigue, scheme) and what the box-score model prices is the exploitable inefficiency. See [edge-taxonomy.md](edge-taxonomy.md), edges 1–9.

**Referee context is priced slowly.** Ref assignments are posted ~9am ET. Props are posted ~6am. The model does not update immediately for ref-specific foul rate effects. The 3-hour window between posting and ref announcement is the clearest timing edge. See [timing-layer.md](../strategy/timing-layer.md).

**Injury adjustments are manual.** When a player is scratched, the book must manually recalculate 50+ teammate props. This takes 5–15 minutes per major injury event. A model that can recompute all distributions in seconds captures edge during this window. See edge 28 in [edge-taxonomy.md](edge-taxonomy.md).

**SGP correlation discounts are formulaic.** Same Game Parlays are priced with a generic correlation adjustment, not a model-derived one. Books use a lookup table that applies similar discounts across diverse correlation structures. The possession simulator generates joint distributions that capture true correlation; the difference between your joint probability and the book's formulaic price is edge. See [edge-taxonomy.md](edge-taxonomy.md), edge 34.

**Alternate lines get less attention.** Books concentrate modeling resources on mainline accuracy. Alternates at O+4 or O-4 from mainline carry the same vig but have softer pricing. The tail of a well-calibrated distribution prices these accurately; see edge 35.

**Early season miscalibration is predictable.** The first 2–3 weeks of each season are systematically mispriced (ScienceDirect literature). Books have no current-season data and rely on preseason projections. A model trained on multiple prior seasons has better priors. This edge recurs every October without any model improvement required.

### Structural Errors

**Props priced as independent markets.** If a player's expected pace is high, all his counting stats should drift up. Books price points, rebounds, and assists as separate markets with separate modeling; they don't propagate the joint implication of a high-pace game across all markets simultaneously. The possession simulator does this naturally.

**Player role changes not fully reflected.** After a major lineup change (injury, trade), the full redistribution of usage takes 3–5 games to appear in book lines. Your model can compute the redistribution from on/off data immediately (see edge 13).

---

## Market Venues and Their Characteristics

### Retail Sportsbooks

| Book | Prop depth | Typical vig | Limiting speed | Notes |
|------|-----------|-------------|----------------|-------|
| DraftKings | Deepest — pts/reb/ast/3pm/blk/stl/tov + combos + alternates | -110 to -120 | Fast: within ~300 bets for consistent winners | Most volume, hardest limits |
| FanDuel | Deep | -110 to -115 | Slowest of majors | Most tolerant; start here |
| BetMGM | Good | -110 to -120 | Fast, similar to DK | Watch win rate closely |
| Caesars | Good | -110 to -115 | Moderate | Less data on limiting patterns |
| bet365 | Good | -110 to -115 | Moderate | UK-origin, slightly different model |
| Fanatics | Growing | -110 to -115 | Unknown (new entrant) | Likely most tolerant early |

**Limiting reality:** Books use AI-driven account profiling. Consistent winners get flagged within ~300 bets (down from ~1,000 a few years ago). Props get limited before mainlines; specific market types before account-wide limits. The account health model (see [account-longevity.md](../strategy/account-longevity.md)) is designed to stay under these thresholds.

### P2P Exchanges

| Platform | Legal in Iowa | Model | Vig | Notes |
|----------|--------------|-------|-----|-------|
| Novig | Yes (42 states) | Sweepstakes/P2P | Zero | No limiting ever |
| ProphetX | Yes (40+ states) | Sweepstakes/P2P | Zero | No limiting ever |

**The P2P thesis:** Zero vig means any positive edge (50.01% win rate) is profitable. At -110, you need 52.38%. The vig differential compounds over thousands of bets. As sportsbook accounts age and limits tighten, migrating volume to P2P is the path to sustainable long-run profitability.

**Market making on P2P:** Post your own lines; other bettors match them. You collect the edge in aggregate. No limiting possible — you are the price-setter. This is the endgame.

### Prediction Markets

| Platform | Status | NBA coverage | Fee | Notes |
|----------|--------|--------------|-----|-------|
| Kalshi | Gray — Iowa AG litigation ongoing (March 2026) | Game-level + some player performance | <2% of max profit | CFTC-regulated, deepest liquidity |
| Polymarket | Gray — technically prohibited for US residents | Thin NBA | ~0.75% | USDC, growing |

**Iowa regulatory note:** Iowa AG joined a multi-state coalition against prediction markets (May 2026). Iowa Senate Bill SB 2470 failed, but legal pressure continues. Use carefully — not a foundation to build the core strategy on.

---

## Line Movement Dynamics

### How Lines Move

1. **Opening line** (~6am ET): set by book's own model
2. **Sharp money** (6am–12pm): syndicate accounts and sharp bettors hit lines they disagree with; books respond by moving in the direction of the sharp action
3. **Ref announcement** (~9am): small adjustments to FTA-sensitive props
4. **1pm injury report**: manual recalculation; 5–15 minute window of stale lines
5. **5pm injury report**: same, larger stakes for evening games
6. **Lineup confirmation** (~30–35 min pre-game): large adjustments if late scratches
7. **Closing line**: the sharpest estimate of true probability; reflects all publicly available information

### Why Closing Lines Are the Benchmark

The closing line is not the "true probability" — it is the market's best estimate of probability after a full day of price discovery including sharp syndicate action. Consistently beating the closing line (positive CLV) is the gold standard for having real edge. It means you identified the correct direction before sharp money corrected it.

CLV formula:
```
CLV = devig(your_line_at_placement) - devig(closing_line)
```

Average CLV > 0 over 500+ bets with statistical significance (p < 0.05): the edge is real.

### Steam Detection

A steam move is coordinated sharp account action at multiple books simultaneously. Detectable by:
- 3+ books moving the same direction within 60 seconds
- Movement magnitude > 0.5 points on the line
- Unusually high bet velocity at affected books

Steam is directional information. If your model agrees with the steam direction, bet the residual at books that haven't adjusted yet. See edge 29 in [edge-taxonomy.md](edge-taxonomy.md).

---

## Not Available in Iowa

- **PrizePicks** — not licensed in Iowa (significant loss; PrizePicks is the deepest player prop DFS market in the US)
- **Underdog Fantasy** — not licensed in Iowa
- **Pinnacle** — blocks US residents; sharpest lines globally (2–3% margin, "winners welcome"), used as CLV benchmark but not for actual betting

*Note: Illinois residency adds PrizePicks access and loses the ability to bet on in-state college teams. Net gain for a market-focused operator.*

---

*See [edge-taxonomy.md](edge-taxonomy.md) for all 37 edges and how they exploit these structural pricing errors. See [validation-methodology.md](validation-methodology.md) for how to measure and confirm the edge using CLV against closing lines.*
