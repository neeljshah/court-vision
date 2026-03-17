# Basketball Analytics — Key Metrics Reference

Formulas and definitions for analytics models being built.

---

## Shooting Metrics

| Metric | Formula | Notes |
|--------|---------|-------|
| FG% | FGM / FGA | Basic field goal % |
| eFG% | (FGM + 0.5 * 3PM) / FGA | Accounts for 3-pointer value |
| TS% | PTS / (2 * (FGA + 0.44 * FTA)) | True shooting efficiency |
| Shot Quality | Distance + defender proximity + shot type | What we're building |

## Tracking-Derived Metrics

| Metric | How To Compute | Why It Matters |
|--------|---------------|----------------|
| Speed | Δposition / Δtime | Sprint bursts, effort |
| Acceleration | Δspeed / Δtime | Explosive movements |
| Player Spacing | Avg distance between offensive players | Spacing = defense stress |
| Closest Defender Distance | Euclidean dist from shooter to nearest defender | Shot difficulty |
| Paint Touches | Time with ball in paint zone | Post/drive aggression |
| Off-Ball Movement | Total distance traveled without possession | Offensive activity |

## Game State Metrics

| Metric | Description |
|--------|-------------|
| Momentum | Rolling win probability change over last N possessions |
| Pace | Possessions per 48 minutes |
| Offensive Rating | Points per 100 possessions |
| Defensive Pressure | Avg defender distance to ball carrier |

---

## Shot Quality Model (To Build)

**Input features:**
- Shot distance (from 2D court coordinates)
- Defender distance (closest defender at shot time)
- Shot angle (relative to basket)
- Dribbles before shot (derived from possession events)
- Time in possession

**Output:** Shot quality score 0-1 (higher = better look)

**Target label:** Made/missed (from video or manual annotation)

---

## Win Probability Model (To Build)

**Input features:**
- Score differential
- Time remaining
- Current momentum (last 5 possessions)
- Home/away
- Team offensive rating (season average)
- Team defensive rating (season average)

**Output:** Win probability 0-1 for home team
