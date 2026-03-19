# The Master Prediction Pipeline
> How every data source and every model combines into the single most accurate prediction possible.
> Last updated: 2026-03-17

---

## The Core Question

**"What's my edge on Jamal Murray over 22.5 pts tonight vs Golden State?"**

Every layer of the system answers a different part of this question. Together they produce a probability that's more accurate than the sportsbook's implied probability. The difference is your edge.

---

## The 6-Layer Prediction Stack

### Layer 1 — Game Context
*"What kind of game is this going to be?"*

These run before any player-level analysis. They set the macro environment every other model operates inside.

```
Win probability model (M1)         → DEN 58% vs GSW
Game pace model (M6)               → 98 possessions projected
Game total model (M2)              → 223.5 pts
Schedule context (Tier 0)          → DEN: 2 rest days, GSW: B2B road game
Referee assignment (ref_tracker)   → Tonight's ref: +1.8 pace, high foul rate
Arena context                      → Ball Arena: altitude neutral (both acclimated)
Line monitor (line_monitor.py)     → DEN opened -3, now -4.5 → sharp money on DEN
Action Network                     → 62% of money on DEN → confirms sharp lean
```

**Output:** Game environment object — pace, tone, foul rate, home advantage, sharp signal

---

### Layer 2 — Player Context
*"How is Murray specifically positioned for this game?"*

```
Rolling form (Tier 1 props)        → Murray L5: 27/26/22/29/24 — hot
Zone tendency (M15)                → Murray: 42% at rim, 31% mid-range, 27% 3pt
Shot creation type (M18)           → Murray: 68% off-dribble, 32% C+S
Usage model                        → Murray usage ~31% — primary option
Matchup matrix (M60)               → Murray vs GSW primary defenders: historically 1.14 pts/possession
Clutch efficiency (M17)            → Murray: 87th percentile in clutch
Injury monitor                     → Murray: active, no listing
DNP predictor (M35)                → P(DNP) = 2% — healthy
Contract year (M40)                → Not applicable (has 4 years left)
```

**Output:** Murray player profile for tonight

---

### Layer 3 — Spatial Context (CV Data — Phase 6+)
*"What does the physical matchup look like at the possession level?"*

```
xFG by zone vs GSW defense:
  At rim:    P(make) = 0.61 (vs 0.58 league avg) — GSW weak at rim
  Mid-range: P(make) = 0.47 (vs 0.44 avg) — slight edge
  3pt:       P(make) = 0.38 (vs 0.36 avg) — GSW moderate 3pt D

Defensive pressure score (M44)     → GSW: 72nd percentile pressure on ball handlers
Spacing context (M45)              → Jokic on court: spacing drops (defense sags)
                                     → Murray gets fewer clean looks but better spacing when Jokic draws double
Drive frequency (M46)              → Murray drive rate vs GSW: above average
Closeout quality (M54)             → GSW closeouts: 68th percentile speed → open corner 3s likely
Fatigue model (M51)                → Murray: ~34 min/game average, no B2B
                                     → GSW: B2B road game → opponent fatigue modifier Q4
```

**Output:** xFG multiplier per zone, pressure modifier, fatigue adjustments

---

### Layer 4 — External Factors
*"What external context changes the baseline tonight?"*

```
Injury cascade (injury_monitor):
  → Jokic active → Murray not forced into primary scorer role
  → GSW: no major injuries

Referee tendency:
  → Tonight's ref historically: +2.1 FTA/100 possessions vs avg
  → Murray FT rate increases ~8% with this ref's foul calling style

Line movement analysis:
  → Pinnacle: Murray opened 22.5, now 23.5 → public money
  → DraftKings: 22.5 unchanged → soft book lag
  → Signal: bet DraftKings 22.5 not Pinnacle 23.5

News NLP (M68):
  → Murray post-game yesterday: "I feel great, legs feel fresh" → positive
  → No injury concerns from beat reporters
  → No trade rumors, no distractions

National TV flag:
  → ABC game → Murray historically +1.4 pts on national TV
```

**Output:** External modifier set — all factors that shift the baseline

---

### Layer 5 — Monte Carlo Simulation
*"Given all the above, what's the full distribution of Murray's points tonight?"*

```
Possession simulator runs 10,000 times:

Each possession:
[1] Play type → ISO 40% / PnR-BH 35% / C+S 25% (given Murray + Jokic lineup)
[2] Shot selector → zone based on tendency + game state
[3] xFG v2 → P(make) adjusted for defender, zone, fatigue, spacing
[4] TO/Foul → P(shot) 71% / P(TO) 14% / P(foul) 15% per possession
[5] Rebound → if miss, P(Murray offensive rebound) = 4%
[6] Fatigue → efficiency at minute N: mild decay in Q4 (Murray is fit)
[7] Substitution → coach sits Murray if score margin > 20 → affects minutes
    (Garbage time predictor M72 flags when to stop counting)

10,000 simulations → Murray pts distribution:
  Mean:    24.3 pts
  Std Dev: 5.1 pts
  P25:     20.8 pts
  P50:     24.1 pts
  P75:     27.9 pts
  P(≥22.5): 61.4%
  P(≥27.5): 28.1%
```

**Output:** Full probability distribution for every stat — pts, reb, ast, 3pm, stl, blk, tov

---

### Layer 6 — Market Comparison + Edge Calculation
*"Where is the book wrong and by how much?"*

```
Your model:    P(Murray > 22.5) = 61.4%
Book line:     22.5 pts at -115 → implied probability = 53.5%
Raw edge:      61.4% - 53.5% = +7.9%

Correlation check (M32):
  → Nuggets team total line: 116.5 over -110
  → Correlation: Murray pts + Nuggets total = 0.68
  → If betting both: reduce Kelly on correlated legs

Kelly sizing:
  → f* = (0.614 × 1.87 - 1) / 0.87 = 0.116
  → Fractional Kelly (½): 5.8% of bankroll on this bet
  → Cap at 3% max single bet → bet 3% of bankroll

Sharp money confirmation:
  → Action Network: 57% of bets on over, 71% of money on over
  → Line has NOT moved → public money, books not concerned
  → Reduces confidence slightly vs if sharp money were one-sided

Final output:
  Edge: +7.9%
  Confidence: ★★★ (3 stars — edge > 7%, sharp confirmation neutral)
  Bet size: 3% of bankroll at DraftKings (22.5, not Pinnacle's 23.5)
  SGP correlation: if pairing with Nuggets over, reduce combined Kelly by 35%
```

---

## How Accuracy Improves At Each Phase

```
Phase 4 (TODAY):
Models available: M1-M18 (Tiers 1+2)
Layer 3 (spatial): EMPTY — no CV game data yet
Accuracy: ~55-58% on props vs 52-54% implied
Edge: Small but real on role player props

Phase 6 (20 games):
Models available: M1-M50 (xFG v2, play type, spacing, pressure)
Layer 3: FULL spatial context
Accuracy: ~58-62% on props
Edge: Real and consistent on most props

Phase 8 (Simulator v1 built):
Layer 5: Monte Carlo RUNNING
Accuracy: Full distribution, not just mean
Edge: Correlated leg detection unlocked

Phase 10 (100 games):
Models available: M1-M65 (lineup chemistry, matchup matrix, fatigue curves)
Layer 2: TRUE matchup efficiency (Murray vs specific GSW defenders)
Accuracy: ~60-65% on targeted props
Edge: Role player props where matchup matrix has edge

Phase 12 (200 games, full stack):
All 90 models running
Layer 3: CV biometrics (movement asymmetry, real-time fatigue)
Layer 4: NLP injury lag model
Layer 5: Full 90-model chain in simulator
Accuracy: ~63-67% on props (vs 52-54% implied)
Edge: +8-12% on best bets, consistent CLV
```

---

## The Self-Improving Loop

```
Game tonight (new video + game-id)
    ↓
CV tracker extracts: positions, events, spacing, pressure, play types
    ↓
NBA API enrichment: shot outcomes, box score, possession results
    ↓
PostgreSQL: all data stored, versioned (tracker_version + date)
    ↓
Auto-retrain trigger: if new data > threshold for any model tier
    ↓
Models improve → simulator improves → next prediction more accurate
    ↓
Outcome logged: did Murray hit over? What was our edge?
    ↓
CLV tracker: did we beat the closing line? (primary success metric)
    ↓
Feedback into confidence calibration → bet sizing improves
```

**The compound effect:** Every game processed makes every model slightly better. At 200 games, the system has processed enough lineup combinations, matchup pairings, and possession sequences to produce stable estimates for every model tier. At 1,000 games, noise averages out and spatial correlations become highly reliable.

---

## Prediction Accuracy By Market

| Market | Current Edge (Phase 4) | Full Stack Edge |
|---|---|---|
| Game lines (spread/ML) | +0-1% — efficient market | +1-2% with full sharp signal |
| Game total | +1-2% | +2-4% with pace + spatial |
| First half total | +2-3% | +3-5% |
| Role player props | +3-5% | +6-10% |
| Star player props | +0-2% | +2-4% |
| Back-to-back props | +3-5% | +5-8% with fatigue curves |
| Injury reaction props | +8-15% (30-min window) | +8-15% (speed unchanged) |
| Same-game parlays | +3-5% (correlation edge) | +4-8% |
| Live props (halftime update) | N/A yet | +5-12% |
| DFS lineups (cash) | +5-8% | +8-15% |

---

## Related
- [[Complete Data Sources]] — every input that feeds the pipeline
- [[Complete Model Catalog]] — all 90 models with inputs and targets
- [[System Architecture]] — technical implementation
- [[Project Vision]] — the three end products this pipeline powers
