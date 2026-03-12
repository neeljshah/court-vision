# Machine Learning

How machine learning is used in the NBA AI system.

---

## Overview

The system uses multiple ML models trained on a combination of computer vision tracking data and official NBA statistics. Each model targets a specific prediction problem in basketball. Models are built in order of data requirements — simpler stat-only models first, tracking-dependent models once sufficient clip volume is accumulated.

---

## Training Data Sources

### Tracking Data (from CV pipeline)
- Per-frame player and ball positions (2D court coordinates)
- Speed, acceleration, spacing metrics
- Possession classifications, shot context
- Defensive setup at moment of shot
- Event labels: pass, shot, drive, screen

### NBA Statistics (from NBA API)
- Box scores: points, rebounds, assists, shooting splits
- Team offensive and defensive ratings, pace
- Lineup data: on/off splits, net ratings, minutes together
- Shot logs: location, make/miss, shot clock, defender distance
- Play-by-play: possession outcomes, scoring runs

### Contextual Features
- Rest days, back-to-back games, travel distance
- Home / away / neutral court
- Opponent strength (defensive rating, pace)
- Season timing (early season vs playoff push)
- Player injury and minutes load history

---

## Model Objectives

### 1. Game Outcome Prediction
- **Input:** team stats, lineup data, contextual variables
- **Output:** win probability, expected point margin
- **Training label:** actual game result
- **Notes:** No tracking needed — can be built immediately from NBA API data

### 2. Shot Quality Evaluation
- **Input:** shooter position, defender distance, shot type, spacing, shot clock
- **Output:** expected field goal % (xFG), shot quality score (0–1)
- **Training label:** shot made / missed (from NBA API shot logs)
- **Notes:** Requires tracking data for spatial features

### 3. Possession Outcome Prediction
- **Input:** possession type, spacing, defensive pressure, ball-handler quality, shot clock
- **Output:** probability of scoring / turnover / foul
- **Training label:** actual possession outcome (from play-by-play)
- **Notes:** Requires tracking + possession segmentation

### 4. Player Performance Projection
- **Input:** player rolling stats, usage rate, matchup, rest, minutes projection
- **Output:** projected points / rebounds / assists for a given game
- **Training label:** actual box score stats
- **Notes:** Stat-only model; tracking enhances with effort metrics

### 5. Live Win Probability (In-Game)
- **Input:** current score, time remaining, possession sequence, momentum features
- **Output:** real-time win probability curve
- **Training label:** actual game result
- **Notes:** Requires sequence model over full game possession data; needs 200+ full games

### 6. Lineup Impact
- **Input:** 5-man lineup identities, individual ratings, spacing, on/off history
- **Output:** projected net rating for lineup in a given matchup
- **Training label:** actual lineup net rating splits
- **Notes:** Tracking adds spacing and movement synergy features

---

## Model Types

| Type | Use Case |
|---|---|
| Gradient boosting (XGBoost / LightGBM) | Game outcome, player props, shot quality |
| Neural networks (fully connected) | Possession value, lineup embeddings |
| LSTM / sequence models | Live win probability over possession sequence |
| Spatial / CNN models | Court zone heatmaps, movement pattern recognition |
| Survival / time-to-event models | Shot clock pressure, foul propensity |

---

## Prediction Outputs

### Win Probability Models
- Pre-game win probability (team stats + context)
- Live win probability updated after each possession
- Confidence intervals on final margin

### Possession Value Models
- Expected points per possession by play type
- Possession outcome probabilities (score / turnover / foul)
- Value-above-average for each offensive action

### Shot Success Models
- Expected field goal % per shot (xFG)
- Shot quality score — how much better/worse than average shot
- Zone efficiency maps per player or team

### Lineup Impact Models
- Projected net rating for any 5-man combination
- Best lineup for a given opponent matchup
- Fatigue-adjusted projections based on minutes load

---

## Build Order

Models are built in this order based on data availability:

1. **Pre-game win probability** — NBA API data only, build first
2. **Player prop projections** — NBA API data only
3. **Shot quality model** — needs tracking spatial features
4. **Possession outcome model** — needs tracking + possession segmentation
5. **Live win probability** — needs 200+ full games of tracking
6. **Lineup chemistry** — needs on/off tracking data at scale

---

## Dataset Strategy

Every game processed through the tracking pipeline automatically grows the training dataset:

- Tracking outputs (positions, spacing, events) are saved per frame to `data/`
- NBA API enrichment joins shot outcomes and possession results automatically
- After 50 processed games: enough data for shot quality and possession models
- After 200+ processed games: enough data for live win probability LSTM
