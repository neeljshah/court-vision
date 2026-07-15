# Glossary

> Every term used across the docs, defined once. Navigation: [Index](INDEX.md) - [Home](../README.md)

## Honesty / proof vocabulary

- **CLV (Closing Line Value)** -- the difference between the price you got and the market's
  *closing* price on the same outcome. Positive CLV = you beat the number before it sharpened. The
  honest, forward-looking yardstick for "did we have an edge", because it is far less noisy than
  raw profit.
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
  when counts are over-dispersed (real-world variance exceeds Poisson).
- **Dispersion calibration** -- widening/narrowing a count distribution so its spread matches
  reality; a too-tight distribution fabricates fake edges.
- **Empirical-Bayes shrinkage** -- pulling a noisy per-player rate toward a role/archetype prior in
  proportion to how little data the player has.
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
  fit, matchup splits, clutch shape, ...). 48 of them (30 player + 18 team).
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
  correlation a marginal model cannot.
- **Vig / juice** -- the book's built-in margin; raw odds sum to >100% implied probability.
- **Devig / Shin devig** -- removing the vig to recover the market's *fair* probability; Shin (1992)
  accounts for informed-trader bias.
- **EV (expected value)** -- `p * payout - 1`; the per-unit expected return of a bet.
- **Kelly / fractional / quarter-Kelly** -- bankroll-optimal bet sizing; the system caps at a
  fraction (quarter-Kelly) and is correlation-aware.
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

## Platform / execution vocabulary (2026-07)

- **Baseball date** -- the MLB day boundary the GUMBO live poller schedules against: UTC minus 10
  hours, not calendar-UTC midnight. A sport's "day" is a domain concept; defaulting to raw UTC
  goes blind every evening once the date rolls past midnight UTC while West Coast games are still
  live. See [INGEST_PIPELINES](INGEST_PIPELINES.md).
- **Census (data census)** -- `data/frontend/ops/data_census.json`, a machine-readable,
  regenerate-on-demand inventory of every derivable data family per sport (61 across NBA / MLB /
  soccer / soccer_intl / tennis / WNBA / NPB / KBO / cross-sport-market), each tagged BUILT /
  PARTIAL / UNBUILT; UNBUILT families carry a `leverage_rank` feeding the standing cross-sport
  priority queue. See [DATA_DEPTH](DATA_DEPTH.md).
- **Fill quality (book / no_book)** -- the honesty stamp on a simulated paper fill: `book` = priced
  by walking a fresh captured order-book depth ladder; `no_book` = no usable book (stale, missing,
  or one-sided), so the bet is recorded at its snapshot price without a fabricated fill. See
  [PAPER_TRADING_STACK](PAPER_TRADING_STACK.md).
- **Greenlight gate (a-g criteria)** -- `scripts/platformkit/econ/edge_greenlight.py`; seven
  pre-registered criteria (sample size in both independent halves, both-halves profitability, CLV
  significance, after-cost units, trust + eval-gate honesty, excess win rate) a paper channel must
  clear before a units figure means anything. Read-only, RED / AMBER / GREEN, fail-closed on any
  missing input. See [PAPER_TRADING_STACK](PAPER_TRADING_STACK.md).
- **id-aware G1** -- the phase-tier regression gate that compares per-test node ids (not aggregate
  pass/fail counts) against a frozen baseline, so a genuinely new failure can't be masked by an
  unrelated new pass, and a pre-existing flaky failure doesn't block work that never touched it.
  See [PLATFORM_HARNESS](PLATFORM_HARNESS.md).
- **One-conclusion composer** -- the `compose_best()` pattern for "who is the best X" questions:
  ONE name out, reached via a declared, auditable rule (domain filter -> primary axis selected by
  a pre-registered gate verdict -> attribution axes for context -> honest disagreement surfaced,
  never hidden), never a re-weighted score. Contrast with trait vector/profile below. See
  [ASK_SURFACES](ASK_SURFACES.md).
- **pairs_for_claim_stores subset loading** -- the loader composers must call instead of a bare
  `load_verified_claims()`: restricts claim-source pairs to a named subset of stores so a composer
  never whole-loads a GB-scale bulk claim store (e.g. `nba_player_box_rate`, 59,710 rows) into
  memory. See [ASK_SURFACES](ASK_SURFACES.md).
- **STUCK detector** -- a counter of consecutive processing ticks that had open work and zero
  completions; past a threshold (e.g. 24 ticks / ~6h at a 900s settlement cadence) it flips a
  status file to `STUCK` so ops monitoring alerts, turning a silent stall into a visible state
  instead of an unread log line. See [PAPER_TRADING_STACK](PAPER_TRADING_STACK.md).
- **Trait vector / profile** -- the `compose_profile()` answer shape for "what kind of X is
  player" questions: an independently-cited multi-axis vector (e.g. volume / efficiency /
  difficulty / gravity / context for a shooter), never combined into one score. Contrast with the
  one-conclusion composer above. See [ASK_SURFACES](ASK_SURFACES.md).
- **VWAP fill walk** -- `fill_sim.fill_price()`'s method for pricing a simulated paper fill: walks
  the opposite side's bid ladder best-price-first until the requested size fills or depth runs
  out, producing an honest partial fill rather than a fabricated full one. See
  [PAPER_TRADING_STACK](PAPER_TRADING_STACK.md).
- **Watermark refetch window** -- a trailing re-fetch window (e.g. `refetch_days = 3`) that always
  re-pulls the last N days even when already cached, so a pure "fetch from watermark forward"
  ingest can't permanently lock out a day that was only partially complete when first fetched.
  See [INGEST_PIPELINES](INGEST_PIPELINES.md).

---

*Numbers vocabulary note: every metric above is reported as calibration / sharpness, never as a
dollar edge. Truth-source: [JOB_EVIDENCE_PACKET](JOB_EVIDENCE_PACKET.md).*
