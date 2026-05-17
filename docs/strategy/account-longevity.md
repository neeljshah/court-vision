# Account Longevity — Anti-Limiting Tactics

*Heat score model, rotation strategy, and P2P migration for account longevity.*

---

## The Core Problem

You WILL get limited on sportsbooks. The question is not whether, but when and how severely. Books have deployed AI-driven account profiling that flags consistent winners within approximately 300 bets (down from ~1,000 a few years ago). The system must be designed to maximize account lifespan across all books and gracefully migrate volume to P2P exchanges as accounts degrade.

A limited account doesn't mean losses. It means the book reduces maximum bet size — sometimes to $5–10 per bet. This makes the account unprofitable from a transaction-cost perspective. The system treats a limited account as effectively closed and shifts volume elsewhere.

---

## What Triggers Limiting

Books use a combination of signals. Any one signal alone rarely triggers limits; the combination does.

| Signal | Threshold | Notes |
|--------|-----------|-------|
| Sustained win rate | > 55% on props over 50+ bets | Internal model flags as statistically significant |
| Bet count | Approaching ~300 per account | Increasing precision in profiling with more data |
| Prop type concentration | > 60% of bets in same market category | "Always betting same player/prop" pattern |
| Timing consistency | Always betting at same times | Natural bettors have varied timing |
| Bet size uniformity | Same Kelly fraction every bet | Recreational bettors bet irregular amounts |
| Steam chasing | Betting same direction as sharp line moves | Correlated with professional sharp behavior |
| Correlated bet patterns | Multiple correlated props at same book | Detectable by books' correlation modeling |

**Key asymmetry:** Books limit props before mainlines. Within props, they limit specific player/market combinations before account-wide limits. The degradation is usually gradual: max bet size reduces from $500 → $200 → $50 → $5.

---

## Mitigation Tactics

### 1. Book Rotation (Most Important)

Spread volume across 6+ books. Target no more than 20% of total bets at any single book. This extends the bet-count runway across all books from 300 to ~1,800 before any single account reaches the threshold.

**Operational:** The execution router tracks bet count per book and auto-rotates before limits trigger.

### 2. Market Type Mixing

Occasional mainline bets (game spreads, totals) make an account look recreational. Books profile prop-only accounts differently than accounts that also bet mainlines. The opportunity cost is low (mainlines are less edge-rich but not necessarily -EV given line shopping).

**Frequency:** 1 mainline bet per 8–10 prop bets is sufficient to shift the profile.

### 3. Timing Variation

Don't always bet at opening (6am) or always at lineup confirmation (30 min pre-game). Vary across the day:
- Some bets at open (when CLV is best)
- Some after referee announcement (when ref features update)
- Some at 1pm/5pm injury report (injury-reaction bets)
- Occasional bets at irregular times mid-morning

The goal is to look like a bettor who is engaged throughout the day, not a system polling at precise intervals.

### 4. Size Variation

Full Kelly produces the same sized bet every time (same fraction, different dollars as bankroll grows). This is detectable. Add controlled noise:
- Randomly round bet size up or down by 5–15%
- Occasionally bet at 40% Kelly instead of 50%
- Very occasionally pass on a bet even when edge is above threshold (unpredictability)

### 5. Account Diversification

Holding accounts in multiple names (family members, etc.) is technically permitted by most books and legally allowed. Each account gets its own bet-count runway. This is the most powerful longevity extension available.

**Risk:** Some books have explicit TOS prohibitions on this. Verify per-book before using family accounts. The legal exposure is nil (betting is legal); the operational risk is account closure.

### 6. P2P Migration Ramp

As sportsbook accounts age (approaching limits), shift volume to Novig and ProphetX. Zero vig means the volume is equally profitable per unit of edge at slightly lower CLV (P2P lines are less sharp than Pinnacle). The limiting problem disappears permanently — P2P exchanges have no incentive to limit bettors; they need market makers and takers both.

**Target allocation over time:**
- Year 1: 80% sportsbooks, 20% P2P
- Year 2: 60% sportsbooks, 40% P2P
- Year 3+: primarily P2P + market making

### 7. Account Health Monitoring

The account health panel (see [dashboard-spec.md](../architecture/dashboard-spec.md)) tracks heat score per book in real time. The goal is to know you're approaching limits before the book does, not after.

**Operational trigger:** When heat score > 0.7, stop routing to that book immediately. Don't wait for the limit confirmation email.

---

## Venue Hierarchy for Long-Term Sustainability

```
P2P Exchanges (Novig, ProphetX) ← Target endgame
        No limiting, zero vig, market-making available
        
Prediction Markets (Kalshi) ← Medium term
        Regulated, institutional participation, thin NBA coverage

Newer Sportsbooks (Fanatics) ← Near term
        Less profiling data, likely most tolerant early

Established Books (FanDuel, Caesars) ← Current primary
        FanDuel is slowest to limit; Caesars moderate

Aggressive Books (DraftKings, BetMGM) ← Use selectively
        Most volume but fastest limits; reserve for best opportunities
```

---

## Realistic Account Lifecycle

| Phase | Duration | Action |
|-------|----------|--------|
| Honeymoon | 0–100 bets | Full limits available; prioritize highest-edge opportunities |
| Monitoring | 100–200 bets | Book internal model accumulating data; maintain patterns |
| Degradation risk | 200–300 bets | Heat score rising; reduce concentration; vary patterns |
| Soft limit | 300–400 bets | Max bet size reduced; account still valuable for line-shopping |
| Hard limit | 400+ bets | Account effectively closed for systematic betting; maintain for line data |
| P2P transition | Ongoing | Migrate volume to P2P; maintain closed accounts for reference |

---

## What Not To Do

- **Don't always bet on the same player.** Even if you have consistent edge on one player's points prop, spreading bets across players extends account life dramatically.
- **Don't use the same timing every day.** Scheduled behavior is detectable.
- **Don't be too good too fast.** A 70% win rate in the first 50 bets is likely to trigger early review even with low volume.
- **Don't ignore soft limits.** When bet size drops from $500 to $200 without explanation, that is a soft limit. Update heat score and reduce routing.

---

*See [execution-engine.md](../architecture/execution-engine.md) for the technical implementation of account health monitoring and routing. See [market-microstructure.md](../research/market-microstructure.md) for the P2P exchange venue analysis.*
