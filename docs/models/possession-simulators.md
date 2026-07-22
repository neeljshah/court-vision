# Possession / Sequence Monte Carlo Simulators — Across Every Sport

Every sport in this platform is ultimately priced by a **sequence-level Monte Carlo
engine**: basketball simulates possessions, baseball simulates pitches/plate-appearances,
soccer simulates a bivariate-Poisson scoreline, tennis simulates points. Each engine is
sport-specific (built inside `domains/<sport>/`), but they share one architectural pattern
described in [`../PLATFORM.md`](../PLATFORM.md): a calibrated **anchor probability** (from a
leak-free rating system) pins the engine's aggregate win-probability, and the engine then
supplies everything *else* — totals, margins, props, joint distributions — coherently
derived from the same simulated paths, never fit independently. For the sport-blind
Monte-Carlo path framework these engines optionally plug into, see
`kernel/sim_framework/` and [`../architecture/possession-simulator.md`](../architecture/possession-simulator.md)
(the deep-dive on the NBA engine's internals).

This page is the cross-sport index: what each engine models, its state space, and how it's
gated. Nothing here is a betting-edge claim — every validation script below reports
calibration/sharpness only (Brier, RMSE, CRPS, PIT-uniformity) against a held-out corpus or
the devigged market close, and `edge_claimed: False` is stamped through the code.

---

## NBA — possession-level engine (two implementations)

NBA has **two** possession simulators at different maturity stages, both real and both
documented in the codebase (this is not duplication to clean up — `sim2/` is the newer,
kernel-facing conditioned engine; `src/sim/basketball_sim.py` is the older, deeper
lineup-aware engine still in production use).

### `src/sim/basketball_sim.py` — the lineup-sampling possession engine

A data-driven, player-level Monte Carlo where each possession is "used" by exactly one of
the five on-court players (the shared scoring pie), with **on-court lineups sampled from
real stint minutes** — so teammate scoring competes for the same possessions and the
correct (slightly negative) teammate correlation *emerges* rather than being imposed by a
correlation matrix. The module docstring names this explicitly as the fix for an earlier
simulator's teammate-correlation bug (measured 0.645 vs. a real -0.011).

Every mechanic is parameterized from `data/cache/team_system/{player_rates.parquet,
team_rates.json}` (built from box scores + play-by-play — no broadcast computer-vision
input). Public API: `TeamModel.from_cache(tricode)` and `simulate_game(home, away,
n_sims=1000, seed=0)`.

Defense is an explicit first-class input, not an afterthought: on-court defenders'
`INTERIOR_D`/`PERIMETER_D` ratings (from the role-aware rating builder — see
[`signal-factory-and-ratings.md`](signal-factory-and-ratings.md)) suppress the offense's
shot-make probability via calibrated slopes (`DEF_RIM_SLOPE`, `DEF_PERIM_SLOPE`), anchored
at the league-average opposing-team defense level (`REF_RIM_D=65.0`, `REF_PERIM_D=65.0` —
deliberately *not* the median individual player's 50, since every team fields a rim
protector). These slopes were calibrated against `scripts/team_system/backtest_defense.py`'s
real-outcome backtest (team scoring MAE 11.7 -> 11.0, RMSE 14.1 -> 13.4) and set
conservatively (~1.5x smaller than the sweep's apparent optimum) to avoid overfitting one
in-sample season. A newer, still-gated lever (`CV_AGENT_DEF_SUPP`, default OFF) adds a
per-defender opponent-PPP-suppression term on top; it ships only if it clears a walk-forward
gate (`scripts/team_system/gate_def_supp.py`) on both the fit roster and a holdout roster,
with seed stability required — default-off means it never changes output unless explicitly
enabled.

### `domains/basketball_nba/sim2/` — the kernel-facing conditioned engine

A cell-based possession model built for the kernel/adapter split:

- **`possession_model.py`** — a possession is a team-continuity unit (an offensive rebound
  stays "in possession"; point outcomes 0-6+). State is a 5-dimensional cell:
  `time_b` (6 buckets: Q1/Q2/Q3/Q4>3min/Q4<=3min/OT), `margin_b` (7 offense-relative
  buckets), `off_t`/`def_t`/`pace_t` (as-of terciles) — 1,134 total cells (6 x 7 x 3 x 3 x 3).
  Cells with fewer
  than 40 possessions back off to the (time, margin) marginal (42 dense cells), then to the
  global distribution — the same sparse-cell backoff pattern used throughout this codebase's
  empirical models.
- **`pace_model.py`** — empirical possession-duration distribution conditioned on the same
  (time, margin) cells, so late-game hurry-up / stall regimes emerge from data rather than
  hand-coded rules.
- **`simulator.py`** — a fully vectorized numpy possession-alternation loop to the final
  buzzer (with overtime), producing final-score ensembles.
- **`cond_composite.py`** — a v3 extension adding a 6th cell dimension: a minutes-weighted
  lineup-quality composite built from strictly prior-season player profiles. The fallback
  discipline is explicit in the module docstring: "worst case v3==v2, an honest null, never
  worse" — a thin conditioned cell backs off to the unconditioned v2 distribution rather than
  extrapolating on sparse data.
- **`validate.py` / `validate_v3.py`** — walk-forward validation fitting on two prior seasons
  and evaluating on a held-out season, across three panels: PIT-uniformity by
  (period x margin) bucket, CRPS of the simulated final-margin ensemble against a Gaussian
  repricer baseline, and checkpoint win-probability Brier against both a mechanism-ladder
  logistic and the live market. Results are written as JSON scoreboards
  (`data/frontend/ops/nba_sim2_validation.json`), not a pass/fail gate object — a human or
  agent adjudicates whether the sim beats its baselines, and a null result (it doesn't) is
  recorded honestly rather than discarded. `validate_v3.py` runs the same panels paired
  against v2 to test specifically whether the composite conditioner sharpens three named
  worst-performing v2 buckets.

Both NBA engines feed `predictor.py::to_jd()` for coherent joint-distribution sampling and
the in-game repricing layer (see [`../LIVE_ENGINE_V2.md`](../LIVE_ENGINE_V2.md) for the full
predictor/repricer chain).

---

## MLB — pitch-level engine (`domains/mlb/pitch_engine/`)

A hierarchical **empirical** model (not a physics simulator) that chains pitch-selection and
outcome models through an exactly-solved Markov process over ball-strike counts:

- **`selection.py`** — `SelectionModel`: `P(pitch class in {fastball, breaking, offspeed} |
  pitcher, count, platoon, base-out state)`, with a four-rung backoff (pitcher-specific ->
  pitcher x count -> league cell -> global), Laplace-smoothed. A companion league-level
  sub-model predicts zone location given class and count.
- **`outcome.py`** — `OutcomeModel`: a 10-way pitch-outcome distribution conditioned on
  class, zone, count, and batter skill tier (`BatterTiers` fits prior-season wOBA-like
  terciles leak-free — fit on one season, applied to the next).
- **`pa_chain.py`** — the key architectural choice: rather than Monte Carlo simulating each
  plate appearance pitch-by-pitch, `context_outcome_matrix`/`pa_event_dist` chain
  selection x outcome through the 12 ball-strike count states as an **absorbing Markov chain
  solved exactly** (linear algebra, not sampling) into an 8-way plate-appearance event
  distribution (`OUT, K, BB, HBP, 1B, 2B, 3B, HR`). A `DirectPAModel` (a no-chain empirical
  twin) serves as the ablation baseline that isolates whether the count-chain machinery adds
  anything over just fitting the PA-event distribution directly.
- **`game_sim.py`** — a `BaseOutTransition` (empirical `(runs scored, next base-out state)`
  sampler keyed by base-out state and PA event) feeds `simulate_game`, fully vectorized
  across simulations, implementing standard walk-off and extra-innings rules.
- **`bullpen.py`** / **`game_sim_v2.py`** — v2 adds a starter-removal hazard model and a
  pooled reliever PA-distribution (by inning bucket, leverage, tier, and days-rest
  freshness) on top of v1, specifically targeting a named v1 weakness (over-projecting
  home-team scoring in a 7th-inning home-lead state). Two further reliever-conditioning
  candidates have since been gated on top of v2: **`bullpen_v3.py`** crossed the pooled
  reliever distribution with a K-rate quality tier (per-pitcher or per-team), but
  `validate_v3.py`/`validate_v3_team.py` found the tiering variable INERT (mathematically
  identical to the plain pooled marginal once every tier cell clears the min-sample floor).
  **`bullpen_v4.py`** instead conditions each simulated team's reliever PA-distribution
  directly on that team's own (inning bucket, lead state) history, no tier axis, with
  per-cell backoff to the pooled marginal (`game_sim_v3.py` supplies the two separate
  home/away matrices this needs; gated in `validate_v4.py`). Separately,
  **`outcome_platoon.py`** adds a same-hand (pitcher-throws vs. batter-stand) dimension to
  the outcome table for the previously ungated inn4|margin-2 bucket, tested in
  `validate_platoon_inn4.py`.
- **`rung6_composite.py`** — builds a per-game composite win-probability logit from the
  actual starting nine batters and starting pitchers (first-nine-distinct-appearance-order
  lineups, event-level log5 tilt), feeding into the in-game win-prob ladder.
- **`validate.py` / `validate_v2.py`** — fit on prior seasons, validate on a held-out season
  across four panels: selection log-loss vs. a no-context baseline, PA-chain log-loss vs.
  the direct-model ablation, full-game PIT/CRPS vs. a prior-season-Normal climatology
  baseline, and state-conditional PIT at fixed innings snapshots. `validate_v2.py`
  specifically compares v1 vs. v2 at the inning-7/home-lead bucket to test whether the
  bullpen seam actually fixes the named weakness — the verdict note states plainly that the
  reliever seam is judged to help only if its uniformity deviation at that bucket is
  strictly smaller than v1's.

### The run-scoring alternative: `negbinom_engine.py` / `negbinom_sim.py`

A simpler, complementary model used by `predictor.py` for the pregame market surface (moneyline / run-line / totals), independent of the pitch-by-pitch engine above: independent
**Negative-Binomial** run-scoring marginals per team (rather than Poisson), because Poisson
understates real run-total tail variance. `r` (the dispersion parameter) is fit leak-free by
method-of-moments on the first half of the corpus (`fit_dispersion_first_half`). The
resulting joint score matrix (`runs_matrix_nb`) is tilted so the NegBinom-implied moneyline
matches the Elo-anchored win-probability exactly (`_anchor_nb_tiesplit`, a sum-preserving
tilt) — the same anchor-coherence pattern used across every sport. `run_validation` reports
Brier deltas vs. plain Poisson and tail-coverage in the extreme-probability buckets.

---

## Soccer — bivariate-Poisson scoreline engine

**File:** `domains/soccer/scoreline_engine.py`

Confirmed **Dixon-Coles (1997) bivariate Poisson**: `scoreline_matrix(lam_home, lam_away,
rho=0.0, max_goals=12)` first builds the independent-Poisson outer product over a home/away
goals grid, then applies the Dixon-Coles low-score correlation correction (`tau`) to exactly
four cells — (0,0), (0,1), (1,0), (1,1) — before renormalizing. `rho` (the DC correlation
parameter, fit by `domains/soccer/rho_fit.py` via bounded maximum-likelihood, clipped to
`[-0.2, 0.0]`) captures soccer's empirically observed tendency for low-scoring outcomes
(especially 0-0 and 1-1) to be more correlated than independence implies; at `rho=0` the
engine is provably identical to plain independent Poisson (verified to 1e-6 by
`engine_over25()`). `markets_from_matrix()` reads every market — 1X2, over/under at five
lines, both-teams-to-score (via inclusion-exclusion), and top-N correct scores — off the same
matrix, so nothing can disagree with anything else.

`domains/soccer/ratings.py::GoalsState` supplies the `lam_home`/`lam_away` inputs: an
exponentially-weighted (leak-free, snapshot-before-update) per-team goals-for/against rate
model. `domains/soccer/hfa_lambda.py` learns a mass-preserving home-field correction (scales
`lam_home` up and `lam_away` down by `sqrt(h)`/`1/sqrt(h)` so total expected goals is
conserved) via a leak-free expanding-window fit.

`domains/soccer_intl/` (the international-fixtures predictor) **reuses this exact scoreline
engine and market surface by import** (not duplication) — it supplies its own ratings state
tuned for sparser international data (slower decay, `MIN_MATCHES=8`) and adds neutral-site
awareness (`neutral` flag skips the home-goals bump for tournament matches on neutral
ground; the bump itself is fit from the corpus, not hardcoded).

---

## Tennis — point-level Monte Carlo engine (`domains/tennis/point_engine/` + `match_engine.py`)

Tennis has two related but distinct simulation components:

### `match_engine.py` — the production hold-rate engine (what `predictor.py` calls)

`serve_probs_from_winprob(target_match_p, best_of, base_hold, ...)` is the **bisection**
step that realizes the anchor pattern described in `docs/PLATFORM.md`: it parameterizes
per-point serve-hold probability as `hold_1 = base_hold + delta`, `hold_2 = base_hold -
delta`, Monte Carlo simulates matches at candidate `delta` values, and bisects until the
simulated match-win rate matches the calibrated Elo-anchor win-probability within an
MC-noise-aware tolerance. `markets_from_engine()` then reads match-win, straight-sets
probability, and game/set totals off the resulting joint distribution — all coherent with
the single anchored number by construction (MC-approximate, not an analytic identity; the
docstring quantifies the residual noise at under 0.05 at 20,000 simulations). A declared
simplification: 6-6 tiebreaks are modeled as a flat 50/50 regardless of server strength.
`match_engine_holds.py` is a variant that seeds `base_hold` from each player's own as-of
hold-rate (instead of a flat constant) while still bisecting the shared delta to the same
Elo target.

### `point_engine/` — a separate research/validation harness on real point-by-point data

- **`point_model.py`** — `PointModel`: empirical `P(server wins point | server, score bucket,
  set bucket)` with a declared backoff hierarchy (full cell -> server-only -> league cell ->
  global), plus a `naive_baseline()` (classic i.i.d.-points, per-server-constant-rate) used
  as the comparison floor.
- **`corpus.py`** — builds the point-level state frame from the real Sackmann Grand Slam
  point-by-point corpus, collapsing (server points, returner points) into 19 leak-free
  pre-point cells via a groupby+shift (never looking at the point's own outcome to build its
  own state label).
- **`match_sim.py`** — the game -> set -> match Monte Carlo chain (`play_game`,
  `play_tiebreak`, `play_set`, `play_match`), using standard scoring and real tiebreak
  server-rotation rules. Declared simplification: tiebreak points reuse the "deuce" score
  bucket as a max-pressure proxy rather than a dedicated 7-point tiebreak state space.
- **`validate.py`** — fits on 2011-2013 Grand Slam points, validates on held-out 2014 across
  two panels: point-level log-loss (state-conditioned model vs. the naive constant-rate
  baseline) and match-level PIT/CRPS of the simulated games-margin plus match-winner Brier
  vs. a climatology-Normal baseline. Explicitly skips any market-based baseline (the
  corpus's era doesn't share match IDs with a market feed) rather than fabricate one;
  `edge_claimed: False` throughout.

This point-engine is genuinely separate infrastructure from `match_engine.py` — it exists to
validate serve-point modeling assumptions against real charted point-by-point data, not to
serve live predictions. `TennisPredictor` calls `match_engine.py`, not `point_engine/`.

---

## Cross-sport comparison

| Sport | Engine location | State granularity | Anchor mechanism | Dispersion handling |
|---|---|---|---|---|
| NBA | `src/sim/basketball_sim.py` (production) + `domains/basketball_nba/sim2/` (kernel-facing) | Possession, 5-D cell (time x margin x off/def/pace tercile) | Elo win-prob anchors margin distribution mean | Empirical possession-outcome distribution per cell |
| MLB | `domains/mlb/pitch_engine/` (pitch-level) + `negbinom_engine.py` (run-scoring) | Pitch -> count -> plate appearance (Markov-exact) -> base-out state | MOV-Elo win-prob anchors NegBinom lambda tilt | Negative-Binomial `r` fit leak-free vs. Poisson |
| Soccer | `domains/soccer/scoreline_engine.py` | Team-level goals, bivariate Poisson | EW goals-rate lambdas; DC `rho` for low-score correlation | Dixon-Coles low-score correction; separate NB dispersion for player-prop counts (`dispersion.py`) |
| Tennis | `domains/tennis/match_engine.py` (production) + `point_engine/` (validation harness) | Point -> game -> set -> match | Elo-recalibrated win-prob bisects serve-hold delta | MC sampling noise only (no explicit dispersion parameter) |

Every engine above shares the same three disciplines: (1) sparse-cell **backoff** to a
coarser distribution rather than extrapolating on thin data, (2) a **leak-free anchor**
(a rating system's calibrated win-probability) that every derived market must stay coherent
with, and (3) a **walk-forward validation** on a held-out season/corpus reporting
calibration/sharpness metrics only — never a fabricated dollar edge.

---

## Related

- [`../architecture/possession-simulator.md`](../architecture/possession-simulator.md) — deep-dive on the NBA engine's internals
- [`signal-factory-and-ratings.md`](signal-factory-and-ratings.md) — the rating/signal inputs these engines consume
- [`calibration-and-validation.md`](calibration-and-validation.md) — the walk-forward + truncation-invariance discipline every validation script above follows
- [`../domains/README.md`](../domains/README.md) — per-sport domain docs with the full predictor/repricer chain around each engine
