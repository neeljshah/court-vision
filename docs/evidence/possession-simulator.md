# Possession Monte Carlo -- correlation that EMERGES, and a sim that grades itself

> The engine simulates the *mechanism*, not the summary. Teammate correlation is not a
> parameter I fit -- it falls out of shared-possession mechanics, and the measured value
> matches reality where a prior simulator's hand-tuned matrix was badly wrong. The sim then
> grades its own forecast quality by game-state bucket and names the buckets it handles worst.
> The single truth-source for any figure below is
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md) (Section F); `edge_claimed=false`
> throughout, and no dollar, ROI, or betting-edge figure appears anywhere on this page.

---

## The claim

Most projection tools regress to a summary statistic -- a mean, maybe a variance -- and then
staple correlations on afterward with a hand-tuned matrix. I built the opposite: a
player-level possession Monte Carlo where the joint structure between players is not an input
at all. Two teammates compete for the same finite pile of possessions, so the *correct*
slightly-negative teammate scoring correlation **emerges from the mechanics** rather than being
imposed. The measured emergent value matches realized boxscores, where a prior simulator that
imposed a correlation matrix got the sign and magnitude wrong. The sim then grades its own
calibration by game-state cell and publishes a ranked backlog of its worst buckets.

---

## The mechanism -- a shared scoring pie sampled from real stint minutes

`src/sim/basketball_sim.py` runs a possession chain. There is no teammate-correlation matrix
anywhere in the code. Each possession is *used* by exactly one of the five on-court offensive
players:

```
  one possession  (N of these per simulated game)
  ------------------------------------------------
  sample the on-court 5 from REAL stint minutes  (MIN_MPG 6.0 rotation floor)
      -> pick the user u by  use_per_min ^ 1.25   (role-aware: routes more to primaries)
      -> u draws tov / drawn-foul / SHOT; scores or misses -> OREB loop or possession ends
  the other four CANNOT use this possession -- it is spent
```

Because the possession pie is finite and one player spending a possession denies it to his
teammates, their scoring is *mechanically* anti-correlated. Nothing about that is tuned; it is
a consequence of the sampling. Every rate feeding the chain (usage, zone shot profile, FG% by
zone, foul/turnover rates) is parameterized from `data/cache/team_system/` built off boxscores
and play-by-play -- no broadcast CV in this path -- and the engine is pure and leak-free given
those rate inputs.

---

## The emergent-correlation receipt

The payoff is the measured teammate points-points correlation, read off simulated games against
realized boxscores, with no correlation ever imposed:

```
     new possession sim   :  rho ~ -0.10   (EMERGENT -- nothing imposed)
     realized boxscores   :  rho ~ -0.10   (what actually happens)
     prior game_simulator :  rho   +0.65   (hand-tuned rho-matrix -- wrong sign AND magnitude)
```

The prior `game_simulator` imposed a positive teammate correlation of about **+0.65**; reality
is about **-0.10**, and the new engine reproduces that **-0.10** without being told to
(`src/sim/sgp_from_sim.py` measures **-0.104**). Getting a joint quantity right *by
construction* -- rather than fitting it, which invites overfitting the sign -- is the whole
point of simulating the mechanism instead of the summary.

That joint structure is not a covariance matrix either: it *is* the N-by-stats block of
per-sim realizations the chain already produced. `sgp_from_sim.py` prices any set of same-game
legs as a boolean mask over the sims (fraction where all legs hit) and reports the correlation
lift versus the independence product, so mispricing direction is explicit -- same-player legs
correlate positive (lift > 1), teammate scoring legs negative (lift < 1). **Honest scope:** the
`validate_joint_calibration` harness grades the sim-joint against the realized joint on
historical games at the sim's own median lines (each leg ~50/50, isolating the joint), and the
sim-joint beats the independence model on Brier where correlation matters. No SGP ROI is
claimed -- the repo has no real same-game-parlay price capture to grade against.

---

## The self-grading heatmap

`scripts/platformkit/benchmarks/sim_heatmap/build_heatmap.py` turns "improve the sim" into a
ranked, data-driven backlog. It reads each engine's own walk-forward validation artifact and
reshapes the per-bucket PIT-deviation + CRPS + n into one normalized cross-sport schema across
NBA, MLB, soccer, and tennis, so the worst state cells are **named** and tracked release over
release. `edge_claimed:false` throughout -- sharpness and calibration only. It ships with a
self-check test and states its own ceilings instead of papering over them:

- NBA and the MLB pitch engine simulate *from* a mid-game snapshot, so real
  `(period|inning x margin)` cells carry per-bucket PIT/CRPS/n. The worst named NBA cell is
  Q3 at a near-even margin (`P3|m3`), which the builder cross-references to the knowledge
  ledger and flags as an un-probed mechanism **gap**, not a solved problem.
- Tennis and soccer only simulate whole matches, so their rows are one honest whole-match
  pseudo-cell with a `coverage_gap` note -- not fabricated buckets.
- Neither MLB harness computes CRPS per bucket yet, so that is flagged `crps_per_bucket:false`,
  not faked.

The per-sport JSON outputs (`data/frontend/ops/sim_heatmap_{nba,mlb,soccer,tennis}.json`) live
under `data/`, which is gitignored and absent from a fresh clone; the committed builder
regenerates them with `--refresh`.

---

## Receipts

| Number / artifact | Path |
|---|---|
| Emergent teammate pts-pts rho ~ -0.10 vs realized (no imposed matrix); fixes prior +0.65 | `src/sim/basketball_sim.py` |
| Joint pricing straight off the sample block; measured rho -0.104; `validate_joint_calibration` grades sim-joint vs realized (no ROI claimed) | `src/sim/sgp_from_sim.py` |
| Cross-sport state-cell heatmap: per-bucket PIT/CRPS + ranked worst cells, named ceilings, self-check test | `scripts/platformkit/benchmarks/sim_heatmap/build_heatmap.py`, `.../test_build_heatmap.py` |
| Per-sport heatmap outputs (LOCAL: `data/` gitignored; regenerated by `--refresh`) | `data/frontend/ops/sim_heatmap_{nba,mlb,soccer,tennis}.json` |
| Full engine design (mechanics, `_finalize`, joint pricing) | [`docs/architecture/possession-simulator.md`](../architecture/possession-simulator.md) |
| Truth-source row | [`docs/JOB_EVIDENCE_PACKET.md`](../JOB_EVIDENCE_PACKET.md) (Section F) |

---

## Why this matters

The hire signal for quant research is not "I built a simulator." It is that the simulator's
*joint* structure is generative -- correlation emerges from the mechanics and lands on the
realized value by construction, exactly the property a fitted matrix lacks and exactly where a
prior version got the sign wrong at +0.65. Then, instead of one aggregate calibration number,
the engine decomposes its forecast quality by game state, names the buckets it handles worst,
states its coverage ceilings, and refuses to convert a validated joint structure into a
betting-edge claim it did not earn. Building a generative model whose emergent joint behavior
matches reality -- and grading it honestly, cell by cell -- is the work, not the headline.

---

*edge_claimed = false everywhere. Every figure is a calibration / correlation / CRPS quantity
against realized outcomes, never a dollar figure. Retracted measurement artifacts appear only
in [JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md), never on this page.*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
