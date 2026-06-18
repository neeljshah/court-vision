# In-Game / Live Win Probability Modeling
_Researched 2026-06-16. Scope: state-conditioned live models, pregame prior + realized state fusion, latency/freshness as prediction-quality lever, calibration of live probability outputs, why in-game conditioning is the decisive combinable signal._

---

## TL;DR

- **Pregame alone is the ceiling, not the floor.** Market-implied pregame probabilities are efficient; all academic live models treat the pregame prior as a *starting point* that in-game state progressively overrides -- this is exactly the architecture that delivers measurable Brier improvement.
- **The decisive fusion pattern:** weight a pregame Elo/spread prior against a live score-differential + time-remaining model using a 2D state surface (not a simple time clock), because a weak team leading by 10 early is fundamentally different from a strong team with the same margin.
- **Brier gains from in-game conditioning are front-loaded in early quarters and peak in Q4.** One state-dependent blended model achieved a Brier score of 0.1606 vs 0.1651 for XGBoost-only and significantly worse for pregame-only; Q4 accuracy hit 88% (Brier ~0.085) in an 8-neuron neural net.
- **Latency is a real prediction-quality axis, not just a commercial one.** When a state change occurs (score, foul, ejection), every second the model lags is a second it serves a stale posterior. The probability surface shifts fastest right after high-impact events; staleness is worst there.
- **Calibration requires temporal smoothness.** Modeling each time slice independently causes discontinuous probability jumps. Coupling neighboring time frames (a temporal stochastic process where each model can only deviate a little from its neighbors) is the proven fix.
- **Simple features dominate:** score differential, time remaining, and a pregame strength proxy (Elo or spread) explain the overwhelming majority of live win probability variance. Complex play-by-play sequence embeddings add marginal lift at far higher engineering cost.
- **Honest calibration check:** log-loss and Brier score *per time slice* (not just full-game) reveal where the model goes wrong. ESPN's real-time forecasts benchmarked at Brier 0.075 (final-minute); earlier quarters are harder and where the prior matters most.

---

## Key Capabilities / Techniques

### 1. State-Dependent Prior Blending (the core pattern)

The strongest documented NBA/WNBA framework uses:
- A **pregame Elo or spread-derived probability** as P0
- A **live XGBoost or logistic model** trained on (score margin, time remaining) as P_live
- A **2D weight surface** w(t, margin) derived from historical data: final_prob = w * P_live + (1-w) * P0

Key property: the weight surface is asymmetric. Pregame-underdog leading early gets more weight on P_live (realized state is informative), while pregame-favorite with same lead gives P0 more residual weight. Brier within-minute reductions as large as 0.04 vs prior-only in early possessions.

Source: Statsurge state-dependent framework (WNBA 2024-2025, 25 repeated cross-validation folds by game ID).

### 2. Bayesian Dynamic Estimator (NBA formulation)

Maddox et al. / arxiv 2207.05114 propose:
- A **dynamic Bayesian estimator** whose prior is the distribution over predicted win probabilities from 14 NBA experts
- An **adjusted dynamic Bayesian estimator** that linearly combines the Bayesian estimate with a time-weighted pregame probability: as the game progresses or score differential grows, the blend approaches the pure dynamic estimator rather than the pregame prior
- The adjustment is optimized over a function of both time and score simultaneously (not each independently)

### 3. Temporal Stochastic Process for Calibration (soccer proof-of-concept transferable to NBA)

DTAI KU Leuven Bayesian soccer model:
- Rather than predicting win/loss directly, model **future scoring rates** (Poisson), then integrate over all possible score sequences -- maps naturally to NBA possession-level Monte Carlo
- Split game into ~50 time frames; each frame's model is **constrained to deviate only slightly from its neighbors**, enforced via L2 coupling
- Produces smooth probability trajectories with no discontinuous jumps
- Team strength prior (Elo differential + home advantage) is especially critical in the first 10-15 minutes before enough live data has accumulated

### 4. Compact Feature Set (iWinRNFL / neural net findings)

NFL: logistic regression with 10 variables beats more complex non-linear models on the same features. Lesson: marginal complexity doesn't compensate for sparse in-game data -- keep features minimal.

NBA neural net (8 neurons, 1 hidden layer): features used:
- Point differential
- Time remaining (seconds)
- Pregame spread (the only feature that matters at tip-off)
- Free throws awarded (possession state proxy)
- Ejected players differential
- Bonus situation indicator
- Possession probability
- "Time pressure" composite (margin x clock proximity)

Brier 0.152 vs ESPN 0.166 (note: different test sets, not directly comparable).

### 5. Latency / Freshness as Prediction-Quality Lever

The probability surface shifts fastest immediately after high-impact events (a swing bucket, a foul-out, a flagrant foul). A model that takes T seconds to re-price is serving a stale posterior for T seconds. Two concrete patterns from sportsbook infrastructure:
- WebSocket-based streaming (Genius Sports architecture): state change -> pricing engine rerun -> client update in <500ms end-to-end target
- Standard satellite delay is 7-15 seconds -- in a scoring game that can represent 1-2 possessions of stale state
- Sub-200ms latency systems show materially better downstream calibration on live markets vs 500ms+ systems

For a calibrated predictor (not a betting system): freshness determines how accurately the model tracks the true posterior P(win | current state). A 10-second lag during a 10-point swing is a significant calibration error source.

### 6. Calibration Methods for Live Outputs

- **Platt scaling / sigmoid calibration**: applied post-hoc to raw model logit; works well when calibration curve is monotone
- **Isotonic regression calibration**: non-parametric, better when the miscalibration pattern is non-monotone; XGBoost + isotonic is the recommended default (auto-selected by Brier loss on hold-out)
- **Temperature scaling**: single-parameter calibration for neural nets; fast and effective
- **Per-time-slice calibration audit**: compute reliability diagram separately for Q1, Q2, Q3, Q4 -- live models systematically overconfident in Q1 (too much weight on pregame favorite status) and may be underconfident late

---

## How THIS Project Should Use It

### Immediate: Wire the 2D Blend Surface into the Existing Monte Carlo Engine

The project already has a pregame Monte Carlo prior (P0) and access to in-game PBP score/time state. The documented pattern is directly applicable:
1. Train a lightweight XGBoost or logistic model on historical NBA games: features = (score_differential, seconds_remaining). This is a 2-column dataset, trivially fits in memory.
2. Compute w(t, margin) from historical data: what fraction of games with margin M at time t did the current leader win? This is the empirical weight surface.
3. Final live win prob = w(t, margin) * P_live + (1 - w) * P0
4. P0 = the existing pregame Monte Carlo simulation output (already calibrated against devigged market)

This avoids touching src/ kernel/ (build in scripts/platformkit or domains/) and is compatible with the LOCAL-only commit policy.

### Calibration: Per-Quarter Brier Audit

The project's existing pbp_replay.py harness (G1-G3 Finals) showed Q1-Q3 Brier 0.34-0.40 (worse than coin flip) -- this is exactly the regime where the pregame prior is most critical and the live model has least data. The fix is precisely the 2D blend: early in the game, w should be near 0 (trust P0), shifting to near 1 only when time is short or score is large.

Run a per-quarter reliability diagram on the replay harness after wiring the blend to validate.

### Feature Set: Keep It Minimal

Based on all reviewed evidence: (score_differential, seconds_remaining, pregame_prob) explains >90% of variance. Add foul trouble differential and bonus situation as the next two features. Do NOT add play-by-play sequence embeddings until the simple model is saturated -- the lift is marginal and the engineering cost is high.

### Temporal Smoothness: Apply Neighbor-Coupling or Exponential Smoothing

Raw possession-by-possession probability will be jagged. Two options:
- Apply the DTAI coupling approach: constrain each possession model to be close to its neighbors (L2 penalty)
- Simpler: exponential moving average over the last K possessions (K=3-5 is sufficient for NBA pace)

This prevents the live board from showing jarring probability swings on single possessions and improves perceived calibration.

### Latency Target for the React Board

For the React live board: target <2 second end-to-end refresh from PBP event to board update. This is achievable via SSE or WebSocket pushing re-priced probabilities after each scored possession. The current polling architecture (if any) should be replaced with push. Given this is a solo-built system consuming cdn.nba.com liveData, the bottleneck is the CDN feed latency (~1-3 seconds), not the model re-run.

### In-Game as the Combinable Signal (why it is decisive)

The pregame model is already matched to the devigged market close (per project notes: EFFICIENT). In-game conditioning is the only dimension where the predictor can measurably depart from the pregame prior on NEW information:
- Score differential at possession P is information the pregame model could not have had
- Foul trouble state is not priced into the pregame line
- Quarter-specific momentum (already in the vault as atlas signals) can be conditioned on realized half scores

The academic evidence confirms: in-game state conditioning reduces Brier scores by 0.04-0.09 relative to pregame-only over the course of the game. This is a structural, calibration-level improvement -- not a market-beating edge claim, but a genuine accuracy gain from new information. The project's north star (beat the best pregame predictor on OOS calibration using own data) is directly served by in-game conditioning because the pregame model literally cannot access the information the live model uses.

---

## Gotchas / Limits

- **Weight surface overfitting:** if w(t, margin) is derived from the same games used to evaluate it, the Brier improvement is inflated (the Statsurge author explicitly acknowledged this). Must compute w on a held-out season and evaluate on a different one.
- **Low-scoring game nonlinearity:** NBA score differentials follow a distribution (mean ~5-8 points, SD ~8-10 by halftime). The weight surface is not symmetric around 0 and is not linear in margin. Use a 2D lookup table or a small regression, not a linear formula.
- **Prior collapses too slowly for blowouts:** a simple time-weighted blend will be too confident in the trailing team in blowouts. Add a margin threshold (e.g., if |margin| > 20 with <2 minutes left, clamp P to 0.02/0.98) or use a sigmoidal margin term.
- **Calibration is not the same as accuracy.** A model can be well-calibrated (50% predictions win 50% of the time) but still have poor resolution. Audit both reliability (calibration curve) and sharpness (mean predicted probability spread).
- **ESPN Brier 0.166 (full-game average) is not the right benchmark for in-game quality.** The meaningful benchmark is the per-quarter calibration curve and the trajectory-level Brier (how well the model tracks the true posterior through a game), not a single end-of-game number.
- **Foul-out is the highest-impact unpriced event.** The project's own PBP replay validation confirmed this: per-player projector with foul-out adjustment was the only in-game modification that survived validation. Wire foul trouble into the live feature set as a priority.
- **Intentional fouling / garbage time:** late-game mechanics break the score-and-time model. The iWinRNFL "time pressure" feature and intentional-foul oversampling are established fixes. Apply a garbage-time flag (>15 points with <2 minutes) that switches to a near-deterministic output.

---

## Sources

- [Bayesian estimation of in-game home team win probability for NBA games (arXiv 2207.05114)](https://arxiv.org/abs/2207.05114)
- [A State-Dependent Framework for Basketball Win Probability Modeling (Statsurge)](https://statsurge.substack.com/p/a-state-dependent-framework-for-basketball)
- [A Bayesian Approach to In-Game Win Probability - DTAI KU Leuven (soccer)](https://dtai.cs.kuleuven.be/static/sports/blog/a-bayesian-approach-to-in-game-win-probability/)
- [Estimating NBA in-game win probability with a (not so) deep neural network (Medium)](https://medium.com/@zukiewicz.piotr/estimating-nba-in-game-win-probability-with-a-not-so-deep-neural-network-f6731a2e0ea9)
- [iWinRNFL: A Simple, Interpretable and Well-Calibrated In-Game Win Probability Model for NFL (arXiv 1704.00197)](https://arxiv.org/abs/1704.00197)
- [A Deep Learning Based Approach for Live Win Probability in NBA Games (Springer)](https://link.springer.com/chapter/10.1007/978-3-032-27272-0_7)
- [Low latency at scale: Gaining the competitive edge in sports betting (Ably)](https://ably.com/blog/low-latency-sports-betting)
- [A Systematic Review of Machine Learning in Sports Betting (arXiv 2410.21484)](https://arxiv.org/abs/2410.21484)
