# Execution Engine — Multi-Book Routing and Account Health

*Architecture design. Dry-run (`LIVE_BETTING=0`) gate enforced until paper trading passes.*

---

## Overview

The execution engine is the last mile: sized bets from the Kelly sizer flow here and get placed at the optimal venue at the best available price. It manages nine venue adapters, tracks account health across all books, routes to P2P when price is competitive, and enforces kill switches.

No live capital is deployed until all circuit breakers are coded, tested, and the paper-trading gate is passed (≥50 paper bets, CLV beat rate ≥55%, paper ROI ≥3%).

---

## Routing Logic

For each bet received from the Kelly sizer:

```
Priority 1: Best available price
    → Compare devigged implied probability across all healthy books
    → Route to the book offering the highest probability at acceptable vig

Priority 2: Account health
    → Skip any book where heat score ≥ threshold
    → Skip any book where bet count approaching ~300

Priority 3: Book-level max bet limit
    → If Kelly says $200 but book caps props at $50:
      → Split remaining $150 across next-best books

Priority 4: Correlation with existing bets at same book
    → Don't concentrate correlated bets at same account
      (limits detect correlated prop betting faster)

Priority 5: P2P preference
    → If Novig/ProphetX price within 0.5 points of best sportsbook price:
      → Route to P2P (zero vig makes up the difference over volume)
```

---

## Book Adapters

### Sportsbook Adapters (DraftKings, FanDuel, BetMGM, Caesars, bet365, Fanatics)

No public API exists for these books. Two approaches:

**Option A: Manual bet slip generation**
System generates bet slip details (book, market, side, amount) and alerts for manual placement. Lowest automation, highest reliability, no TOS risk.

**Option B: Playwright automation**
Automate web interface via headless browser. Higher throughput; higher detection risk. Books increasingly fingerprint browser automation. Implementation: `src/execution/book_router.py`

Current implementation: manual queue for DraftKings and FanDuel; Playwright path in development.

### Exchange Adapters

| Exchange | API | Adapter | Notes |
|----------|-----|---------|-------|
| Kalshi | REST (CFTC-regulated) | `src/execution/kalshi.py` | Limit orders preferred — captures maker rebates |
| Polymarket | CLOB order placement | `src/execution/polymarket.py` | USDC; US residents technically prohibited |
| Sporttrade | Connect Trade REST | `src/execution/sporttrade.py` | Exchange-model sportsbook |
| Novig | API (sweepstakes) | Planned | Zero vig; no limiting |
| ProphetX | API (sweepstakes) | Planned | Zero vig; no limiting |

### Kalshi Detail

Kalshi operates as a CFTC-regulated event contract exchange. Player performance contracts are available for some markets (primarily game-level; some player performance). The calibration layer (`CalibrationLayer.win_prob()`) converts stat projections to binary contract prices. Limit orders at FV − half_spread capture maker rebates and reduce effective cost.

Market making on Kalshi: quote at `FV ± half_spread`, where FV is calibrated win probability and half_spread widens under high model uncertainty or detected adverse-selection flow. Kill switch: inventory > 10% bankroll or adverse-selection ratio > 2.0.

---

## Account Health Model

Each book tracked separately:

| Signal | Weight | Threshold |
|--------|--------|-----------|
| Bet count | 0.35 | Flag at 250; critical at 280 |
| Win rate (rolling 50-bet) | 0.30 | Flag > 55% sustained |
| Bet velocity (bets/day) | 0.15 | Flag if > 3 SD from recreational mean |
| Prop type concentration | 0.15 | Flag if > 60% same market type |
| Bet size variance | 0.05 | Flag if suspiciously uniform |

**Heat score** = weighted composite. Traffic light system:
- Green (< 0.4): no restriction
- Yellow (0.4–0.7): reduce routing frequency by 50%
- Red (> 0.7): stop routing; alert for manual review

**Auto-rotation:** When heat exceeds threshold, router stops sending to that book without manual intervention. Volume shifts to next-healthiest book.

---

## Circuit Breakers

All must be coded and tested before live capital is deployed:

| Breaker | Trigger | Response |
|---------|---------|----------|
| Daily loss cap | −5% of bankroll in one day | Halt all new bets; 24-hour cooldown |
| Drawdown kill switch | > 10% below high-water mark | Paper-only mode + 24hr cooldown |
| Consecutive losing streak | 3 losses → 50% stake; 5 → paper only | Automatic stake reduction |
| Model disagreement halt | Ensemble spread > 3 stat units | Skip market |
| Data quality degradation | Fallback vendor active | 0.5× Kelly multiplier |

**Global dry-run gate:** `LIVE_BETTING=0` flag in `scripts/daily_run.sh` forces all adapters to log intent and skip real orders. This flag is hard-coded until the paper-trading gate is passed.

---

## Paper Trading

Before live capital:
1. Run the full daily stack with `LIVE_BETTING=0`
2. Record every recommended bet: book, market, side, recommended amount, model edge
3. Record actual outcome for each settled bet
4. Compute CLV (closing line at tip-off vs model probability at recommendation)
5. Compute paper ROI (would have been returned if bets were placed)
6. **Gate:** ≥50 paper bets, CLV beat rate ≥55%, paper ROI ≥3%
7. If gate passes: manual review → flip `LIVE_BETTING=1`

Paper trading catches real issues that backtests cannot simulate: API timeouts, stale lineup data, race conditions between injury announcements and line updates.

---

## P2P Market Making

On Novig and ProphetX, the router can post lines rather than match them. Mechanics:

1. Model identifies a market where it has edge on both sides (e.g., model says P(pts > 27.5) = 0.54, book is posting -110/-110 implying 0.5238 per side)
2. Router posts your own line: O27.5 at -108 over, +100 under
3. Other bettors match your posted lines
4. You collect the edge in aggregate across matched bets

**Endgame significance:** No account limiting is possible when you are the market maker, not the bettor. As sportsbook accounts age and limits tighten, P2P market making becomes the primary venue for sustained edge extraction.

**Requirements:** Well-calibrated model (calibration errors produce adverse selection), sufficient bankroll to post meaningful contract sizes, low enough variance that edge realizes before a bad run forces withdrawal.

---

## Monitoring

**System health panel** (see [dashboard-spec.md](dashboard-spec.md)):
- Data freshness: last successful API pull per vendor
- Model latency: time from lineup announcement to updated predictions
- Execution status: last successful bet placement per book
- Error log: anything that failed in last 24 hours

**Critical monitoring windows:**
- 6am ET: confirm prop lines ingested from Odds API
- 9am ET: confirm ref assignments processed and features updated
- 1pm and 5pm ET: confirm injury reports processed
- 30 min pre-game: confirm lineup updates and final distribution recalculation

---

*See [system-overview.md](system-overview.md) for routing context. See [account-longevity.md](../strategy/account-longevity.md) for limiting avoidance strategy. See [timing-layer.md](../strategy/timing-layer.md) for when to bet throughout the day.*
