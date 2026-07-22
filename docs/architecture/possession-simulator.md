# Possession Simulator — Monte Carlo Engine Design

*Possession-level mechanics and full distribution output. Lineup-dependent transitions and foul/blowout logic are planned extensions.*

---

## Concept

The possession simulator is the reason this system generates probability distributions rather than point estimates. Every other retail tool predicts a number. This generates a full distribution over each player's statistical output.

Given the lineup on the floor, the score, the time remaining, and the spatial/context features for this game, the simulator runs a batch of possession sequences (`n_sims` -- default 1,000 on the reference CPU engine `basketball_sim.py`, 10,000 on the GPU engine `fast_sim.py`) and produces: `P(stat > X)` for every player, every stat, at any threshold X.

---

## Why This Architecture Is Correct

**Problem with point estimates:** If your model says a player will score 26 points, you can only evaluate whether to bet O/U 27.5 (the mainline). If the book also offers alternates at 24.5 and 30.5, you have no principled way to evaluate them — because your model didn't produce a distribution, it produced a number.

**Problem with independent models per line:** You could train separate models for "P(pts > 24.5)", "P(pts > 27.5)", "P(pts > 30.5)" etc. But these models will be independently calibrated and will not respect the monotonicity constraint (probability must decrease as threshold increases). Boundary violations produce arbitrage-able outputs.

**Solution:** Generate the full distribution from one simulation. Every threshold is evaluated consistently. The distribution is inherently monotonic because it comes from 10,000 simulated games, not from 10 independent models.

---

## Why Distributions Beat Point Estimates (worked)

A point model emits one number. A distribution model emits the whole shape, and
*every* betting question is a question about the shape, not the mean. Two players
can share a 24.0-point projection yet price the alternates completely differently:

```
  player A (steady wing)        player B (volatile gunner)
  mean 24.0  sd 5               mean 24.0  sd 9
  pts                            pts
  18 .........####               10 ...####
  21 .......########             16 ..######
  24 ......##########  <-mean--> 24 .#########   <- same mean
  27 .......########             32 ..######
  30 .........####               40 ...####

  P(pts > 29.5):  ~0.13          P(pts > 29.5):  ~0.27
  P(pts < 18.5):  ~0.13          P(pts < 18.5):  ~0.27
```

The mean cannot tell A from B, but the book's alternate ladder (O 29.5, U 18.5)
is mispriced for exactly one of them. A point model is blind here; the simulator
emits `P(stat > X)` for every X off one run, so the ladder is priced coherently
and monotonically by construction (more sims clear 18.5 than clear 29.5 -- the
curve cannot cross). This is the entire reason the engine simulates rather than
regresses.

A second, deeper reason is *correlation*. A marginal-per-stat model has no way to
say whether "Player A 25+ pts AND Player B 18+ pts" is more or less likely than the
product of the two marginals. The simulator answers it for free because both numbers
are read off the *same* simulated games (see [SGP](#sgp-joint-distribution)).

---

## Simulation Mechanics

The reference engine is `src/sim/basketball_sim.py`; `src/sim/fast_sim.py` runs the
*identical* possession chain as batched GPU tensor ops (all N sims in parallel) and
shares the same `_finalize` packaging, so the two are statistically equivalent
(validated in `validate_fast_sim.py`). One ~3-4s GPU run at N~10-40k prices the whole
prop / SGP surface for a matchup.

### The shared scoring pie (why correlation EMERGES)

The defining design choice: each possession is *used* by exactly one of the five
on-court offensive players. There is no hand-tuned teammate correlation matrix.
Because two teammates compete for the same finite pile of possessions, a possession
the point guard uses is one the wing cannot -- so their scoring is *mechanically*
slightly anti-correlated, and the measured teammate pts-pts rho comes out **~ -0.10**
against realized boxscores (no rho was imposed). This is the fix for the older
`game_simulator`, whose imposed rho matrix produced +0.645 where reality is ~ -0.10.

```
        ONE POSSESSION  (N of these per simulated game)
        ----------------------------------------------
        sample on-court 5 (offense) and 5 (defense) from real stint minutes
                          |
        pick the user u of the 5 by  use_per_min ^ 1.25   (role-aware: routes
                          |                                 more to primary options)
        draw a ~ U(0,1)
         |        |               |
       a<tov    a<tov+ft        else -> SHOT
         |        |               |
      turnover  drawn-foul     sample zone (rim/paint/mid/3) from u's shot profile
      (+steal)  FT trip          |
                                make? p = FG%(zone) * base_x   (base_x folds in
                                  |                             context + DEFENSE)
                          make ---+--- miss
                           |           |
                    +2 / +3 pts    block? (best rim protector) -> OREB? -> continue
                    assist?         else DREB, possession ends
                    (real PBP
                     feeder net)
```

The OREB branch loops up to 4 times (an offensive rebound keeps the same offense on
the floor), so a possession can produce multiple shot attempts -- this is what gives
second-chance points and the correct rebound counts.

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

### How the make probability is built (worked)

The shot make probability is `FG%(zone) * base_x`, where `base_x` is a product of
bounded multipliers. DEFENSE is not a flat season constant -- it is applied per shot
from *who is actually on the floor*: rim shots face the single best interior defender
in the lineup (you only need one rim protector), perimeter shots face the lineup's
mean perimeter defense. The interior/perimeter ratings aggregate the whole defensive
attribute vault.

```
  Worked rim attempt (illustrative slopes from basketball_sim.py):
    FG%(rim)            = 0.625      (shooter's own rim make rate)
    context base_x      = 1.000      (home/road, B2B from apply_context)
    rim defender int_d  = 78  -> factor = clip(1 - 0.0024*(78-50), 0.78, 1.12)
                                       = clip(1 - 0.0672, ...) = 0.933
    make prob           = 0.625 * 1.000 * 0.933 ~ 0.583

  The same shot vs a league-average rim (int_d = 50): factor 1.0 -> make ~ 0.625.
```

Two layers of defense compose: the *per-shot* lineup factor above (who is on the
floor right now) and an *anchor matchup* drag applied at finalize time, weighted by
the shooter's shot profile (rim scorers feel rim protection, shooters feel perimeter
D), centered at the league-average TEAM defense (~65, not the median player 50) so an
average opponent is a no-op. Optional gated levers (`CV_AGENT_DEF_SUPP` defender
suppression, `CV_LLM_SCHEME` scheme priors) fold in only when their flag is set;
default-OFF they touch nothing and the sim is byte-identical on CPU and GPU.

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

### Finalize: anchor, dispersion, count-stat calibration

The raw possession chain gets the *shape* and the *joint structure* right, but its
marginal means need pinning to season/recency levels and its individual-player spread
needs widening. `_finalize` (shared by the CPU and GPU engines) does three things, in
order:

1. **Anchor** -- rescale each player's per-sim samples so the mean hits his
   recency-blended season target (PTS blends flat season with a half-life-~10-game
   recency rate, `RECENCY_W = 0.6`, because playoff scoring runs below the season
   rate). The ~8 players who carry a game are pinned to their individual targets;
   the bench absorbs the residual to the team total. REB/AST and the secondary
   counts (3PM/STL/BLK/TOV/FTM/PF) are anchored from the same per-minute rates the
   chain used, so the marginals stay consistent and the joint rank-correlation
   survives the rescale.
2. **Dispersion** -- the chain *under*-disperses individual scoring (team totals are
   well calibrated, ~79% coverage, but a star's q10..q90 covered ~66% vs an 80%
   target). A per-player right-skewed lognormal shock widens each player, then is
   renormalized *per sim to hold the team total*, then each mean is re-pinned last
   so the good team calibration and the marginals both survive.
3. **Count-stat calibration** -- the possession chain produces zero-clumped low
   counts (e.g. P(>=1 block) too low). BLK / FG3M / FTM (and STL under `CV_COUNT_STL`)
   are re-sampled from a Poisson at the player's real per-game mean; `CV_COUNT_NB`
   upgrades genuinely over-dispersed counts (var > 1.5x mean) to a negative binomial.
   This trades the weak cross-stat correlation on those low-frequency counts for
   honest single-prop frequency and tails.

Documented limit (kept honest): the player-level scoring pie over-allocates slightly,
so **team totals run a few points high** on a playoff-weighted eval -- trust the side
and the player marginals more than the team over. Two anchor-side "fixes" were tried
and both made it worse; left as a documented limit. See
[KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md).

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

The joint probability naturally captures game-level correlation (all legs that depend on pace, opponent defense, game script fire or miss together). Compare to the book's SGP price (multiply individual leg probabilities x formulaic discount). When yours is higher: +EV SGP. (Edge 20 in the internal edge-taxonomy corpus, local-only.)

### How the joint matrix is built (it isn't a matrix -- it's the samples)

There is no covariance matrix to estimate. The "joint distribution" *is* the N x stats
block of per-sim realizations that the engine already produced. Each leg is a boolean
mask over the N sims; the joint is the fraction of sims where ALL masks are true
(`src/sim/sgp_from_sim.py`, `joint_prob`). The correlation lift is the joint divided by
the independence product of the same marginals:

```
  sim      Brunson    Brunson    Towns
  index    pts        ast        pts        Brunson 24+ pts  &  Brunson 6+ ast
  -----    -------    -------    -------     (same player: positive corr)
   0        27         8         15            hit   &  hit   -> joint hit
   1        19         5         22            miss  &  miss
   2        31        10         14            hit   &  hit   -> joint hit
   3        23         4         20            miss  &  miss
   ...      (N sims)
                                            joint = (#both-hit) / N
                                            indep = P(pts24) * P(ast6)
                                            lift  = joint / indep
```

- **Same-player legs** (Brunson pts AND ast) are positively correlated -- a high-usage
  game lifts both -- so `lift > 1` and pricing the legs as independent UNDER-prices the
  parlay.
- **Teammate scoring legs** (Brunson pts AND Towns pts) share the scoring pie, so
  `lift < 1` (negative corr) and independence OVER-prices.

`describe()` reports `joint | independent | correlation lift xN | fair odds 1/joint`
for any leg list, so the mispricing direction is explicit. **Honest scope:** the joint
*structure* is validated -- `validate_joint_calibration` grades the sim-joint vs the
realized joint outcome on historical games at the sim's own median lines (each leg
~50/50, isolating the joint), and the sim-joint model beats the independence model on
Brier when correlation matters. **No SGP ROI is claimed**: the repo has no real
same-game-parlay price capture to grade against. See
[KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md).

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

*See [system-overview.md](system-overview.md) for the full system context. See [calibration.md](../models/calibration.md) for probability calibration methodology. The live in-game repricer that fuses this pregame distribution with realized game state is documented in [LIVE_ENGINE_V2.md](../LIVE_ENGINE_V2.md) (operator), [LIVE_ENGINE_V2_WEB.md](../LIVE_ENGINE_V2_WEB.md) (web), and [LIVE_OPERATOR_RUNBOOK.md](../LIVE_OPERATOR_RUNBOOK.md) (game-day). Full doc map: [INDEX.md](../INDEX.md).*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
