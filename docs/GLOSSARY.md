# Glossary

> Every term used across the docs, defined once. Navigation: [Index](INDEX.md) - [Home](../README.md)

## Honesty / proof vocabulary

- **CLV (Closing Line Value)** -- the difference between the price you got and the market's
  *closing* price on the same outcome. Positive CLV = you beat the number before it sharpened. The
  honest, forward-looking yardstick for "did we have an edge", because it is far less noisy than
  raw profit. See [methods/clv-computation](research/edge-intelligence/_framework/methods/clv-computation.md).
- **Edge** -- a genuine, repeatable divergence between the model's probability and the *fair*
  (devigged) market probability, where the model is correct out-of-sample. Distinct from accuracy.
- **Calibration** -- whether predicted probabilities match observed frequencies (of events you call
  60%, ~60% happen). A calibration win is *forecaster quality*, not a dollar edge.
- **Accuracy is not edge** -- a model can be more accurate by hugging the market and still have no
  edge; edge lives where the model *correctly* diverges from the market.
- **Evidence tiers** -- how a candidate edge is labeled: **HYPOTHESIS** (plausible, unmeasured) ->
  **CALIBRATION-PROVEN** (sharper than the line OOS, leak-free) -> **CLV-PROVEN** (forward CLV
  accrues at sample size; the only bar that justifies real money) -> **REJECTED**.
- **Paper trading** -- recording bets and grading them without real money. The system is paper-only;
  real money is human-gated behind a CLV record.

## Validation vocabulary

- **Leak-free** -- a feature computed at time T uses only information available at T; no future data
  leaks in. Enforced with assertion-level guards.
- **Walk-forward (WF) cross-validation** -- train on the past, test on the strictly-later future,
  rolling forward. The realistic test for time-series; avoids the look-ahead bias of random folds.
- **Purge / embargo** -- dropping (purging) training rows whose outcome window overlaps the test
  set, and skipping (embargoing) a gap after it, so adjacent-in-time leakage cannot occur.
- **Truncation-invariance** -- a feature at time T is byte-identical whether or not later events
  exist in the data; a strong leak test.
- **OOS (out-of-sample)** -- measured on data not used to fit the model.
- **Multi-corpus / replication** -- a result must hold on **>=2 independent** data sets; a single
  good fold is treated as a probable artifact.
- **Diebold-Mariano (DM) test** -- a statistical test for whether one forecaster is significantly
  more accurate than another; used cluster-robust here.
- **Null-shuffle / permutation control** -- re-running with labels shuffled to confirm the signal
  isn't noise; **noise-p0** is a control that rejects "added flexibility" artifacts.
- **Benjamini-Hochberg (FDR)** -- false-discovery-rate control when testing many candidate signals,
  so a few false positives don't slip through multiple-comparisons.
- **Parity matrix** -- a cross-sport check that each sport's adapter output byte-matches its feature
  spec and all ingests are valid. **GREEN** = aligned.

## Scoring metrics

- **Brier score** -- mean squared error of probabilistic forecasts (lower = sharper).
- **BSS (Brier Skill Score)** -- Brier improvement vs a baseline (>0 = better than baseline).
- **ECE (Expected Calibration Error)** -- average gap between predicted and observed probability
  across bins (lower = better calibrated).
- **RMSE / MAE** -- root-mean-squared / mean-absolute error for point forecasts (e.g. totals, props).
- **CRPS / pinball loss** -- proper scores for full predictive distributions / quantiles.

## Modeling vocabulary

- **Win-probability anchor** -- the single calibrated per-sport win-prob that every market
  (moneyline, spread, total, in-game reprice) is derived from coherently.
- **Poisson / Negative-Binomial (NB)** -- count distributions for player props; NB adds dispersion
  when counts are over-dispersed (real-world variance exceeds Poisson). See
  [poisson-vs-negbin](research/edge-intelligence/_framework/methods/poisson-vs-negbin-for-counts.md).
- **Dispersion calibration** -- widening/narrowing a count distribution so its spread matches
  reality; a too-tight distribution fabricates fake edges.
- **Empirical-Bayes shrinkage** -- pulling a noisy per-player rate toward a role/archetype prior in
  proportion to how little data the player has. See
  [empirical-bayes-shrinkage](research/edge-intelligence/_framework/methods/empirical-bayes-shrinkage.md).
- **Isotonic / Platt / temperature calibration** -- methods to map raw model scores to calibrated
  probabilities. See [models/calibration](models/calibration.md).
- **NNLS (non-negative least squares)** -- the stacking method that blends sub-models into the
  win-prob anchor with non-negative weights.
- **Elo / EW-Poisson / serve-hold ratings** -- the per-sport team/player strength priors
  (margin-of-victory Elo for NBA, exponentially-weighted Poisson for soccer, serve/return Elo for
  tennis).
- **Possession Monte-Carlo simulator** -- simulates a game possession-by-possession (N paths) so the
  whole market surface prices coherently and teammate correlation *emerges* from a shared scoring
  pie rather than a hand-tuned matrix. See [architecture/possession-simulator](architecture/possession-simulator.md).
- **JointDistribution** -- the coherent score matrix from which every derived market is read.
- **Atlas** -- a deep descriptive + correlation table of a player/team dimension (usage role, pace
  fit, matchup splits, clutch shape, ...). 44 of them (28 player + 16 team).
- **Archetype / playstyle** -- a role (striker, holding-mid, keeper; power-hitter, strikeout-pitcher;
  high-usage creator, 3-and-D wing, rim-runner; big-server, grinder, returner) used as the shrinkage
  prior. The graph is built on playstyles, never on people.

## Markets / betting vocabulary

- **Moneyline (ML)** -- a straight bet on who wins.
- **Total (O/U)** -- over/under on combined score.
- **Spread / run-line / handicap** -- a margin-adjusted bet.
- **1X2** -- soccer home-win / draw / away-win.
- **BTTS** -- both teams to score (soccer).
- **Correct-score** -- the exact final score.
- **Prop (player prop)** -- a bet on a player stat (points, rebounds, assists, strikeouts, shots...).
- **Alt-line ladder** -- the full range of lines for one prop (over 0.5 / 1.5 / 2.5 ...).
- **SGP (same-game parlay)** -- multiple correlated legs from one game; a coherent sim prices the
  correlation a marginal model cannot. See [correlated-sgp](research/edge-intelligence/_framework/inefficiencies/correlated-sgp.md).
- **Vig / juice** -- the book's built-in margin; raw odds sum to >100% implied probability.
- **Devig / Shin devig** -- removing the vig to recover the market's *fair* probability; Shin (1992)
  accounts for informed-trader bias. See [shin-devig](research/edge-intelligence/_framework/methods/shin-devig.md).
- **EV (expected value)** -- `p * payout - 1`; the per-unit expected return of a bet.
- **Kelly / fractional / quarter-Kelly** -- bankroll-optimal bet sizing; the system caps at a
  fraction (quarter-Kelly) and is correlation-aware. See
  [kelly-sizing-correlation](research/edge-intelligence/_framework/methods/kelly-sizing-correlation.md).
- **Tier floors (A / B / C)** -- minimum EV thresholds a bet must clear to be surfaced; below the
  floor = **no bet**. Output is in **units, never dollars**.
- **Line shopping** -- comparing the same bet across books to take the best available price.
- **Closing line** -- the final price before an event starts; the sharpest public estimate, used as
  the comparison forecaster (never a model input).

## Data / venue vocabulary

- **Keyless source** -- a feed usable without an API key (ESPN site API, MLB StatsAPI, Sackmann,
  football-data); preferred for resilience and zero cost.
- **Kalshi / Polymarket** -- regulated / on-chain **prediction markets** (low-/no-vig: the fair
  price *is* the tradeable price, so a proven calibration edge converts directly).
- **DFS feeds (Underdog / PrizePicks / FanDuel / DraftKings)** -- daily-fantasy / sportsbook prop
  lines; the soft-prop pockets where edge can plausibly exist.
- **As-of-stamped** -- every data row carries the timestamp at which it was known, so features can be
  rebuilt leak-free for any historical moment.
- **Crosswalk** -- a mapping between id systems that disagree (ESPN event_id != NBA-stats game_id;
  MLB game_pk != book event_id); a known landmine that must be coverage-verified before trusting a join.

## Architecture vocabulary

- **Kernel** -- the sport-blind, validated core machinery shared by every sport.
- **Adapter / domain** -- the per-sport plug-in (`domains/<sport>/`): feature spec + ingest manifest
  + builder. Adding a sport is an adapter, not a kernel rewrite. See [PLATFORM](PLATFORM.md).
- **Platformkit** -- the tooling layer (`scripts/platformkit/`): proof harnesses, eval gates, odds
  connectors, the in-game engine, CLIs. See [PLATFORM_TOOLING](PLATFORM_TOOLING.md).
- **Snapshot / canonical store** -- the one authoritative per-sport JSON the APIs and front-end read
  (none of them recompute).
- **Computer vision (CV) lineage** -- the broadcast-video tracking pipeline (YOLOv8n -> SIFT
  homography -> Kalman + Hungarian -> OSNet re-ID -> EasyOCR -> EventDetector) the platform grew out
  of. Engineering history; its features carry ~0 measured predictive value today. See [CV_TRACKING](CV_TRACKING.md).

---

*Numbers vocabulary note: every metric above is reported as calibration / sharpness, never as a
dollar edge. Truth-source: [JOB_EVIDENCE_PACKET](JOB_EVIDENCE_PACKET.md).*
