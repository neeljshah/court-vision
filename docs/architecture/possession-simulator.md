# Possession Simulator — Monte Carlo Engine Design

*Possession-level mechanics and full distribution output. Lineup-dependent transitions and foul/blowout logic are planned extensions.*

---

## Concept

The possession simulator is the reason this system generates probability distributions rather than point estimates. Every other retail tool predicts a number. This generates a full distribution over each player's statistical output.

Given the lineup on the floor, the score, the time remaining, and the spatial/context features for this game, the simulator runs 10,000 possession sequences and produces: `P(stat > X)` for every player, every stat, at any threshold X.

---

## Why This Architecture Is Correct

**Problem with point estimates:** If your model says a player will score 26 points, you can only evaluate whether to bet O/U 27.5 (the mainline). If the book also offers alternates at 24.5 and 30.5, you have no principled way to evaluate them — because your model didn't produce a distribution, it produced a number.

**Problem with independent models per line:** You could train separate models for "P(pts > 24.5)", "P(pts > 27.5)", "P(pts > 30.5)" etc. But these models will be independently calibrated and will not respect the monotonicity constraint (probability must decrease as threshold increases). Boundary violations produce arbitrage-able outputs.

**Solution:** Generate the full distribution from one simulation. Every threshold is evaluated consistently. The distribution is inherently monotonic because it comes from 10,000 simulated games, not from 10 independent models.

---

## Simulation Mechanics

### Possession-Level Structure

Each possession:
1. Sample a lineup (who is on the floor?) from the substitution model for the current game state
2. Compute possession outcome probabilities conditioned on the lineup
3. Sample an outcome: shot attempt, turnover, offensive foul, free throws initiated
4. If shot attempt: determine who shoots, from where, under what defensive pressure
5. Sample shot outcome given shooter + defender distance + contest angle + shot type
6. Update game state: score, possession, time remaining, foul counts

### Lineup Dependency

The key distinction between a lineup-dependent simulator and a player-average model: two players on the same team do not produce independent statistics. A ball-dominant point guard's shot volume suppresses other players' shot attempts. An elite passer's presence increases teammates' assist opportunities. These dependencies are captured at the lineup level, not by summing individual player profiles.

**Implementation approach:**
- Historical on/off data from PBPStats API: for each 2-man, 3-man, 5-man lineup combination, compute observed pace, efficiency, usage distribution
- Transition probabilities: `P(shot attempt | lineup L)`, `P(player P attempts | shot attempted, lineup L)`
- These are calibrated from 3+ seasons of PBP data, updated each week during the season

### Substitution Model

The simulator must know when starters sit:
- **Foul trouble:** Player with N fouls in Qk sits (coach-specific threshold, learned from historical foul management)
- **Blowout:** When lead exceeds T points with M minutes remaining, bench players enter (coach-specific and season-specific)
- **Standard rotation:** Typical substitution windows per coach, learned from PBP data

Garbage time is particularly important: if a blowout is likely (your blowout probability model says 40%), every player's projected counting stats must be adjusted downward for starters who will sit Q4.

### Monte Carlo Execution

```python
def simulate_game(lineup_state, features, n_paths=10_000):
    results = defaultdict(list)  # player_id -> list of stat realizations
    
    for _ in range(n_paths):
        game_state = GameState(lineup_state, features)
        while not game_state.is_terminal():
            # Sample possession outcome
            outcome = sample_possession(game_state)
            # Update stats for players involved
            game_state.apply(outcome)
            # Check substitution triggers
            game_state.update_lineup()
        
        for player_id, stats in game_state.player_stats.items():
            results[player_id].append(stats)
    
    return results  # 10K realizations per player per stat
```

**Output from 10K paths:**
```python
# For any player, any stat, any threshold:
p_over = np.mean([s['pts'] > 27.5 for s in results['203076']])
# -> 0.623 (62.3% probability of scoring > 27.5)

# Full distribution for violin plot / alternate line pricing:
pts_distribution = [s['pts'] for s in results['203076']]
```

---

## Inputs Required

| Input | Source | Timing |
|-------|--------|--------|
| Lineup on floor per possession | NBA API (live lineups 30 min pre-game) | Pre-game |
| Lineup on/off data (historical) | PBPStats API | Ingested weekly |
| CV spatial features | CV pipeline | Game-day |
| Referee crew | NBA official assignments | ~9am ET game day |
| Travel fatigue index | Computed from schedule | Pre-game |
| Denver altitude flag | Static lookup | Pre-game |
| Player embeddings (NBA2Vec) | Trained offline | Session |
| Blowout probability | Blowout model | Pre-game |

---

## Calibration Requirement

The distributions must be calibrated. A distribution that assigns 60% probability to events that happen 42% of the time is useless for betting decisions — worse than useless, because confident bad estimates are more dangerous than explicitly uncertain ones.

Calibration process:
1. Collect 152K prop residuals (already available)
2. Run calibration curve analysis: predicted probability vs empirical frequency
3. Apply Platt scaling or isotonic regression to debias
4. Verify: reliability diagram lies on diagonal across all prop types

Current calibration status:

| Prop | ECE |
|------|-----|
| pts | 0.021 |
| reb | 0.028 |
| ast | 0.024 |
| fg3m | 0.035 |
| tov | 0.041 |
| blk | 0.056 |
| stl | 0.071 |

ECE (Expected Calibration Error): lower is better; < 0.05 is target.

---

## SGP Joint Distribution

When evaluating a multi-leg Same Game Parlay, pass all legs to the simulator simultaneously:

```python
def evaluate_sgp(legs: list[BetLeg], n_paths=10_000) -> float:
    """Returns joint probability of all legs hitting."""
    results = simulate_game(...)
    hits = sum(
        all(
            results[leg.player_id][i][leg.stat] > leg.threshold
            for leg in legs
        )
        for i in range(n_paths)
    )
    return hits / n_paths
```

The joint probability naturally captures game-level correlation (all legs that depend on pace, opponent defense, game script fire or miss together). Compare to the book's SGP price (multiply individual leg probabilities × formulaic discount). When yours is higher: +EV SGP. See edge 20 in [edge-taxonomy.md](../research/edge-taxonomy.md).

---

## Planned Extensions

| Extension | What it enables |
|-----------|----------------|
| Full lineup-dependent transition matrices | Accurate joint distributions; SGP pricing |
| Blowout / garbage time integration | Counting stat overs suppressed in blowout scenarios |
| Foul trouble substitution model | FTA props, minutes-based props |
| NBA2Vec lineup quality scoring | Better lineup compatibility estimation for sparse combos |
| Bayesian in-season parameter updating | Distributions improve as season progresses |

---

*See [system-overview.md](system-overview.md) for the full system context. See [calibration.md](../models/calibration.md) for probability calibration methodology.*
