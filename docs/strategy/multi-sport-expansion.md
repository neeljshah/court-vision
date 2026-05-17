# Multi-Sport Expansion Plan

*NFL, MLB, Soccer expansion plan — infrastructure reuse by component.*

---

## Why NBA First

Basketball has the strongest case for this specific approach:
1. **Broadcast CV opportunity:** 5-on-5 game on a defined court; homography is tractable from broadcast; player count is manageable for re-ID
2. **Prop market depth:** NBA props are the deepest player-level prop market at US sportsbooks; more markets = more opportunities
3. **Free data richness:** NBA API, PBPStats, Basketball-Reference provide the richest free dataset of any major sport
4. **Short possessions:** Each possession is a discrete, bounded unit — natural atomic unit for Monte Carlo simulation

---

## Infrastructure Reuse by Component

| Component | NBA | NFL | MLB | Soccer |
|-----------|-----|-----|-----|--------|
| Odds ingestion (The Odds API) | NBA | 100% reuse | 100% reuse | 100% reuse |
| Execution adapters (all books) | NBA | 100% reuse | 100% reuse | 100% reuse |
| Kelly / risk systems | NBA | 100% reuse | 100% reuse | 100% reuse |
| Dashboard | NBA | 90% reuse | 90% reuse | 90% reuse |
| Context features (fatigue, travel) | NBA | 80% reuse | 80% reuse | 70% reuse |
| Possession simulator | NBA | Rebuild | Rebuild | Rebuild |
| CV pipeline | NBA | Adapt | Adapt | Harder |
| Spatial feature engineering | NBA | Sport-specific | Sport-specific | Sport-specific |

The key insight: the execution, risk, and market infrastructure is sport-agnostic. Building it once for NBA means 100% of those components transfer. The simulator and CV pipeline are sport-specific, but they constitute only ~20% of total system complexity.

---

## NFL (Next Sport After NBA)

**Why NFL is second:**
- Same downstream infrastructure reuses 100%
- Deep prop markets: passing yards, receiving yards, rushing yards, TDs — same O/U structure as NBA props
- High-frequency games (once per week) means less betting volume but larger per-game edge opportunities
- Box-score modeling is similarly unsophisticated relative to what's possible

**New models required:**
- Different stat distributions (Gamma/Negative Binomial for receiving yards; Poisson for TDs)
- Different game flow (4 downs, field position, clock management)
- QB-receiver dependency modeling (passing yard props are highly correlated)

**CV challenge:**
- Football broadcast uses wider angles covering 22 players on a 100-yard field
- Player identification is harder (helmets, similar body types, numbers less visible)
- Start with box-score-only NFL models while adapting CV
- Player tracking opportunity: receiver route running, separation at catch, QB pressure metrics

**Timeline:** Post-2026 NBA season; simultaneous development during NBA off-season.

---

## MLB (Third Sport)

**Why MLB is well-suited:**
- Game structure is discrete plate appearances — natural atomic unit, similar to possessions
- Statcast: publicly available, extremely detailed pitch and ball tracking data at no cost
- Pitcher-batter matchup modeling replaces lineup-scheme modeling
- The "edge" is similarly structured: books price strikeouts and hits from aggregate stats; Statcast provides much richer inputs

**Statcast features:**
- Release speed, spin rate, pitch type and location by pitcher × batter matchup
- Exit velocity, launch angle, batted ball direction
- Outs above average (OAA) for fielder positioning
- Sprint speed for base-running props

**CV opportunity:**
- Statcast already provides most relevant pitch/batted ball data officially
- CV adds: pitcher fatigue detection (release point drift), fielder pre-shift positioning
- Less urgency to build custom CV vs NBA where no equivalent tracking exists

**New simulator mechanics:**
- Markov chain on base/out states per at-bat
- Pitcher fatigue model (pitch count + velocity decline + location drift)
- Handedness matchup effects (vs LHP/RHP split)

**Timeline:** Second half of 2027, after NFL infrastructure is running.

---

## Soccer (Longer Term)

**Global market context:**
- Soccer is the largest betting market globally; European books dominate
- Player prop markets for goals, shots on target, assists, key passes
- Genius Sports and similar have deep soccer data feeds already

**Challenges:**
- 11v11 on a much larger field; broadcast coverage less consistent
- Lower scoring (goals are rare events; Poisson with mean ~1.5/game per team)
- Player props are thinner; market liquidity lower per bet than NBA/NFL
- European books (Bet365, Betway) are sharper and more sophisticated

**Opportunity:**
- Pre-game match outcome modeling (existing techniques transfer)
- Player-level expected goals (xG) is a well-understood framework; books underutilize it
- Set piece probability is modeled poorly by retail books

**Timeline:** 2028+ or opportunistically if a clear edge is identified earlier.

---

## Expansion Decision Framework

Each sport is worth building when:
1. The downstream infrastructure is already running (execution, risk, dashboard)
2. A specific modeling edge has been identified that books are not using
3. The expected CLV is positive in pre-launch backtests

Do not expand to a new sport without item #2. The infrastructure reuse is high but the modeling work is substantial; only justify it if there's a specific hypothesis about where the edge is.

**For NFL:** The hypothesis is that box-score prop pricing misses air yards, target share changes, and route-running separation metrics that Statcast for Football and broadcast CV can provide.

**For MLB:** The hypothesis is that Statcast plate-discipline metrics (chase rate, whiff rate, contact quality) are underutilized in strikeout and hits props.

---

*See [MASTER_PLAN.md](../../MASTER_PLAN.md) for the full multi-sport vision. See [system-overview.md](../architecture/system-overview.md) for the infrastructure components that will transfer.*
