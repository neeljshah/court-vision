# What the AI Does -- End to End

> **Framing note:** This system is a calibrated prediction engine. The goal is accurate,
> well-calibrated forecasts -- matching or approaching the sharpness of the sharp closing
> line. It is not a profit-claiming product. Where the system MATCHES the devigged close
> that is the correct, honest result for an efficient market. The one measured calibration
> win is in-game state conditioning (see Section 5). No retracted figures appear here; the
> truth source for every number is `docs/JOB_EVIDENCE_PACKET.md`.

---

## Plain-language summary

Given a game scheduled tonight, the system does the following:

1. Pulls fresh stats for every player and team from the NBA API (box scores, game logs,
   synergy data, injury monitor).
2. Builds a feature vector for each player capturing recent form, opponent defensive
   ratings, home/away splits, and contextual signals (rest, travel, referee tendencies).
3. Runs seven trained XGBoost/LightGBM models -- one per statistical category -- to
   predict each player's likely final line for PTS, REB, AST, FG3M, STL, BLK, TOV.
4. Runs a separate win-probability model (a 5-way NNLS-stacked ensemble) to estimate the
   probability each team wins.
5. Feeds both outputs into a possession-level Monte Carlo simulation. The sim runs
   thousands of synthetic games, player by player, possession by possession, routing each
   scoring opportunity through a shared "scoring pie." This makes the outputs coherent:
   the moneyline, the game total, player props, and same-game parlay prices all come from
   the same pool of simulated paths.
6. Passes every output through Shin/Platt calibration to convert raw model scores into
   fair-probability estimates anchored against the devigged closing line.
7. Serves pregame predictions via the FastAPI layer (100 endpoints).

During a live game the system repeats a subset of those steps after each quarter checkpoint,
conditioning the pregame prior on the realized score state, foul counts, and blowout
factors. This in-game update is the one measured calibration improvement in the system.

---

## Step 1 -- Data ingest

### What data comes in

- **NBA Stats API** (keyless): per-player game logs, season averages, synergy offensive /
  defensive play-type breakdowns (isolation PPP, post-up, P&R), referee FTA tendency, team
  pace and rating differentials.
- **Schedule and context**: arena coordinates for travel-distance computation
  (`src/data/schedule_context.py::compute_travel_distance`), back-to-back flags.
- **Injury monitor** (`src/data/injury_monitor.py`): pulls the injury feed and returns a
  DNP probability per player. A DNP probability above 0.30 suppresses that player's
  prediction at the confidence-gate stage.
- **Broadcast video (offline)**: a YOLOv8n ball detector, SIFT homography, Kalman +
  Hungarian multi-object tracker, OSNet re-ID, and EasyOCR scoreboard reader turn raw
  broadcast frames into per-player court-coordinate and event data stored in
  `data/nba_ai.db`. This feed is wired into the feature layer as an optional enhancement
  but carries SHAP importance ~0 in current production prop models -- the pipeline exists
  and is architecturally complete; its predictive contribution is not yet demonstrated.

### Caching and staleness

Game-log and player-average caches expire after 24 hours (`_GAMELOG_TTL_HOURS = 24` in
`src/prediction/player_props.py`). An offline mode (`NBA_OFFLINE=1`) bypasses network
fetches and serves the last-written cache, used in backtesting flows where rate-limiting
is a concern.

---

## Step 2 -- Feature engineering

The prop models use a per-player, per-game feature matrix built from:

- **Bayesian rolling averages** (shrinkage prior weight = 15 games; pulls the rolling
  average toward the season average when sample size is small).
- **Opponent defensive rating** (points allowed per 100 possessions).
- **Home/away splits** from historical game logs.
- **Historical head-to-head performance** vs the specific opponent.
- **Context flags**: back-to-back, travel distance, rest days, synergy isolation PPP for
  both team and opponent, referee FTA tendency.

The CV-derived tracking features (velocity, defender distance, shot zone distributions)
are built in `src/features/feature_engineering.py` and `src/features/advanced_features.py`
and are joined to the same matrix, but as noted above their current predictive signal in
the prop models is near zero.

All features are built as-of the prediction date using strict expanding-window joins --
no future information leaks in.

---

## Step 3 -- The seven prop models

Seven XGBoost / LightGBM regressors, one per stat, live in `src/prediction/player_props.py`
(base models) and `src/prediction/prop_model_stack.py` (the stacked dispatch layer).

### Architecture by stat

The key insight is that sportsbook prop lines score against the **median** outcome, not the
mean, so quantile (q50) models outperform squared-error / Huber objectives for most stats.

| Stat | Primary model | Architecture note |
|------|---------------|-------------------|
| PTS  | sqrt+Huber XGB/LGB + 5-seed MLP, NNLS-stacked | High variance; ensemble balances |
| REB  | LGB q50 (log1p) | Right-skewed; median beats mean |
| AST  | log1p XGB+LGB + multitask MLP, NNLS-stacked | Multitask shares signal across stats |
| FG3M | XGB q50 (log1p) | Discrete count; median is the right estimator |
| STL  | XGB q50 (log1p) | R^2=0.18; low confidence |
| BLK  | XGB q50 (log1p) | Biggest single-stat loop gain (-16% MAE) |
| TOV  | XGB q50 (log1p) | log1p reduces impact of outlier games |

### Honest holdout metrics (20,354-row production-model chronological holdout)

| Stat | MAE | R^2 |
|------|-----|-----|
| PTS  | 4.83 | 0.51 |
| REB  | 1.92 | 0.38 |
| AST  | 1.39 | 0.50 |
| FG3M | 0.89 | 0.29 |
| STL  | 0.71 | 0.18 |
| BLK  | 0.44 | 0.16 |
| TOV  | 0.89 | 0.22 |

MAE column: last-20%-by-date chronological holdout (20,354 player-game rows) scored
through the production inference path by `scripts/verify_production_mae.py`,
re-measured 2026-07-20 (the script fails if any stat drifts >0.02 from this table).
R^2 + architecture: `data/models/quantile_pergame_metrics.json` (99,818 player-game
rows in the training universe). The separate walk-forward OOF measurement (~51K
rows/stat, `data/cache/pregame_oof.parquet`, OOF byte-identical to the calibration
frame) reads PTS 4.58 / REB 1.90 / AST 1.34 / FG3M 0.88 / BLK 0.515 -- quote it only
under that OOF label; full split in `docs/JOB_EVIDENCE_PACKET.md`.

### The stacking layer

`src/prediction/prop_model_stack.py::stack_predict()` wraps the base models in a Ridge
meta-model trained on residuals. A confidence gate suppresses a prediction when:
- The edge vs the market line is below the threshold, OR
- DNP probability exceeds 0.30, OR
- Injury multiplier falls below 0.70.

---

## Step 4 -- Win probability

`src/prediction/win_probability.py` trains a 5-way NNLS-stacked ensemble (XGBoost +
logistic) on three seasons of NBA games. In one trained version, NNLS autonomously zeroed
the XGB weight, leaving the logistic component as the effective model -- a notable example
of the stack making its own regularization decision.

### Features used

Team pace, offensive and defensive rating differentials, rest days, travel distance,
synergy isolation PPP (team and opponent), referee FTA tendency, back-to-back flag.

### Validated metrics (3-fold walk-forward)

- Accuracy: 0.709
- Brier score: 0.193

Full-season season backtest (2025-26, leak-free walk-forward, truncation-invariance
proven): Brier 0.208 (model) vs 0.198 (closing line). Well-calibrated, does not beat
the close. The spread/total pregame CLV is approximately 0 (corr-with-outcome = 0.001).
This is the cleanest market-efficiency proof in the system -- the correct finding.

---

## Step 5 -- Possession Monte Carlo simulation

This is the architectural centerpiece. Everything in steps 3 and 4 is an input to the
simulator; the simulator is what makes the outputs **coherent with each other**.

### The problem a simulator solves

If you price player props and the game moneyline from separate models, nothing prevents
them from contradicting each other. A player projected at 35 PTS but a team win-prob of
30% is internally inconsistent. The simulator eliminates that contradiction by generating
joint samples -- thousands of synthetic game paths where all players, all possessions, and
the final scoreline are drawn from the same process.

### How the simulator works

The implementation lives in `src/sim/basketball_sim.py`.

```
TeamModel.from_cache("BOS")
  -> loads player_rates.parquet + team_rates.json
  -> attaches role propensities, defensive ratings, recency weights, PBP assist network
  -> builds lineup sampling distribution from real stint minutes

simulate_game(home, away, n_sims=1000)
  -> for each simulated game:
       sample a starting lineup (from real stint-minute weights)
       for each possession:
         route to ONE player (weighted by usage per minute, role, creation propensity)
         sample shot zone (rim / paint / mid / 3) from that player's zone distribution
         apply per-zone make probability
         apply defender-suppression (opponent interior/perimeter defensive ratings)
         branch: made -> AST routing via real PBP assist network; missed -> OREB chain
         track pace, FTs, TOVs via team-level rates
       accumulate player totals
       at game end: record winner, scores, individual stat lines
```

The key calibration decision: teammates compete for the **same scoring pie** (a fixed
number of possessions per game, derived from pace). This means if player A takes more
possessions, player B gets fewer. The correct slightly-negative teammate correlation
(-0.104 in validation vs a prior simulator's +0.645 artifact) emerges from the mechanics
rather than being imposed by a hand-tuned correlation matrix.

### From simulation to all markets

```
simulate_game() -> GameSimResult
    |
    +-- moneyline:    fraction of sims won by each team
    +-- total O/U:    distribution of total points across sims
    +-- player props: distribution of each player's PTS/REB/AST/etc across sims
    +-- SGP pricing:  joint probability of multiple legs hitting (src/sim/sgp_from_sim.py)
                      = the fraction of sims where ALL legs hit simultaneously
```

Because everything comes from the same paths, a 4-leg same-game parlay is priced off the
actual joint distribution, not the (incorrect) product of independent marginals. The
correlation structure is inherited, not assumed.

Honest scope note from `src/sim/sgp_from_sim.py`: the joint structure is validated
(teammate-rho ~-0.10 vs realized). No $ claim is made; real SGP prices would require
capturing live book prices not present in the repo.

---

## Step 6 -- Calibration: Shin and Platt

Raw model probabilities are not the same as well-calibrated probabilities. A model that
says "60% win probability" should be right about 60% of the time, not 55% or 65%.

### Devigging (Shin 1992)

Before comparing model output to market prices, the market's implied probabilities must
be extracted from vigged (over-round) odds. The system implements four methods in
`src/prediction/devig.py`:

- **Proportional / additive**: divide by the overround (naive retail default).
- **Multiplicative**: log-odds shift that finds k such that sum(p_i^k) = 1.
- **Power**: n-th root before renormalizing.
- **Shin (1992)**: numerically-stable bisection solver for the insider-trading model.
  Recovers an estimate of z (the inferred fraction of informed bets) and loads the vig
  asymmetrically -- more onto the longshot to protect against informed flow. This is
  the production default (`POST /api/devig` defaults to `shin`).

The Shin method is verified against published theory in `tests/test_devig.py` (7 tests).

### Platt / isotonic calibration

For win probability, a Platt scaling layer (logistic regression fit on OOS holdout
predictions) maps raw model scores to calibrated probabilities. The acceptance gate
(`scripts/validate_calibration_multicorpus.py`) only ships a calibration update if it
beats the raw model on **two or more independent corpora** -- preventing single-window
overfit from masquerading as a durable gain.

For prop intervals, `src/prediction/quantile_calibration.py` applies per-stat q10/q90
scale factors for 80% empirical coverage, derived from `data/models/quantile_calibration.json`.
Conformal prediction intervals (`src/prediction/conformal_props.py`) provide
finite-sample coverage guarantees without distributional assumptions.

---

## Step 7 -- Pregame predictions served via API

The FastAPI layer (`api/main.py`, 100 endpoints across 11 routers) serves the outputs:

- `GET /predictions/props/{player}` -- per-player stat predictions with calibrated intervals
- `GET /predictions/winprob/{home}/{away}` -- calibrated win probability
- `GET /predictions/shot` -- xFG (expected field goal probability) for a shot descriptor
- `POST /api/devig` -- convert vigged odds to fair probabilities via any of four methods
- `GET /sse/live_edges` -- SSE stream of cross-book arbitrage opportunities

The dashboard (`api/templates/`, 22 Jinja templates) renders the slate, CLV tracking,
parlay prices, line scanner, and results pages server-side.

---

## Step 8 -- In-game (live) predictions

### What changes during the game

Once the game starts, three quarters of the final box score are eventually observable.
The system fuses the pregame prediction (the prior) with the realized mid-game state:

```
pregame base prediction (q50 prop models)
  + endQ1 period snapshot head     (learned residual from quarter stats so far)
  + endQ2 period snapshot head
  + foul_change residual           (PTS adjustment from foul stratum change)
  + blowout_flip residual          (lineup/usage adjusts in garbage time)
  + heat_check shrinkage           (stratified dispatch for hot/cold streaks)
  + learned Q4 minute trajectory   (projects remaining minutes from current pace)
  = live projection
      + calibrated q10/q90 bands   (80% empirical coverage)
```

Entry point: `src/prediction/live_engine.py::project_from_snapshot()`.

### The measured calibration win

Conditioning on the realized game state sharpens the win-probability forecaster
(lower Brier = sharper). This is the one measured calibration improvement in the system.

| Sport | Checkpoint | Static Brier | Conditional Brier | Gain |
|-------|-----------|-------------|-------------------|------|
| NBA | end Q1/Q2/Q3 | 0.209 | 0.159 | -0.050 |
| MLB | after inning 3/5/7 | 0.241 | 0.126 | -0.115 |
| Soccer O/U-2.5 | half-time | 0.264 | 0.176 | -0.088 |
| Tennis | after set 1 | 0.219 | 0.151 | -0.068 |

Source: `scripts/platformkit/proof_<sport>/ingame_accuracy.py`, rolled up in
`scripts/platformkit/ingame_scoreboard.py`.

Important context: this is **forecaster calibration quality**, not a dollar edge. A live
book also sees the current score. The system does not claim betting edge from in-game
conditioning; it claims sharpness improvement.

For prop MAE specifically: end-of-Q3 MAE is about 47-55% below the pregame baseline.
Most of that reduction is mechanical (three of four quarters of box score are observed).
The learned-head value-add over a naive carry-forward baseline is approximately 26%,
validated walk-forward.

---

## Step 9 -- Self-improving loop

The system does not require a human to propose new signals. `src/loop/discovery.py`
enumerates candidate feature transforms (unary: square, log1p, zscore; binary: interact,
ratio, diff) over the existing leak-safe feature matrix, screens them cheaply by target
correlation and orthogonality, and feeds the top candidates to the honest gate.

The gate (`src/loop/gate.py`) applies five criteria before anything ships:

1. **Walk-forward**: expanding folds, all folds must show MAE improvement.
2. **Null-shuffle**: the real delta must beat a shuffled-label null distribution
   (z >= 3).
3. **Ablation vs full**: the marginal delta of adding the signal column to the FULL
   production feature matrix must be positive.
4. **Calibration**: reliability / coverage for interval and win-prob targets.
5. **CLV**: closing-line value vs the sharpest available line.

Multiple-comparisons protection: Benjamini-Hochberg FDR correction across all tested
signals, plus a final held-out set touched exactly once. Most candidates correctly
get rejected.

---

## The 5-sport architecture

The validated machinery (walk-forward gating, calibration, the MC sim framework,
the discovery loop, devig, shadow logging) lives in `kernel/`. Each sport implements
a thin adapter under `domains/<sport>/predictor.py` that provides:

- A `SportContext` (runtime interface validated by `kernel/testing/conformance.py`)
- A `feature_spec.py` (identical train and inference feature matrix -- the main source of
  subtle bugs if they drift)
- An `ingest_manifest.py` (per-corpus leak class and freshness SLA)

Five sports are live: `domains/basketball_nba/`, `domains/mlb/`, `domains/soccer/`,
`domains/soccer_intl/`, `domains/tennis/`. All five share one kernel and one prediction surface.

```
                                  kernel/
           +----------+----------+----------+----------+----------+
           |          |          |          |          |          |
    basketball_nba   mlb      soccer   soccer_intl   tennis
       predictor.py  predictor.py  predictor.py  predictor.py  predictor.py
       cohesive_read  cohesive_read  cohesive_read  cohesive_read  cohesive_read
       live_read      live_read      live_read      live_read      live_read
```

Each adapter emits a single calibrated win probability per matchup. Every other market
(totals, spreads, props, SGP, in-game repricer) is derived from that anchor so the
markets stay mutually coherent across sports.

---

## Where to look in the repo

| What | File |
|------|------|
| Possession Monte Carlo simulator | `src/sim/basketball_sim.py` |
| Same-game parlay pricing from sim | `src/sim/sgp_from_sim.py` |
| Win probability model | `src/prediction/win_probability.py` |
| Seven prop base models | `src/prediction/player_props.py` |
| Prop stacking / dispatch layer | `src/prediction/prop_model_stack.py` |
| In-game live projection entry point | `src/prediction/live_engine.py` |
| Feature engineering (CV + schedule) | `src/features/feature_engineering.py` |
| Devig (Shin + 3 other methods) | `src/prediction/devig.py` |
| Quantile calibration | `src/prediction/quantile_calibration.py` |
| Conformal prediction intervals | `src/prediction/conformal_props.py` |
| Walk-forward harness with leak guard | `src/prediction/walk_forward_backtester.py` |
| Signal discovery engine (LLM-free) | `src/loop/discovery.py` |
| Ship gate (5 criteria + FDR) | `src/loop/gate.py` |
| Kernel / adapter contract | `docs/PLATFORM.md` |
| NBA adapter | `domains/basketball_nba/predictor.py` |
| Pregame calibration record | `docs/CALIBRATION_RECORD.md` |
| Market efficiency proof | `docs/MARKET_EFFICIENCY_PROOF.md` |
| Honest numbers + do-not-claim list | `docs/JOB_EVIDENCE_PACKET.md` |
| In-game scoreboard (all sports) | `scripts/platformkit/ingame_scoreboard.py` |
| Beat-the-close scoreboard | `scripts/platformkit/beat_the_close_scoreboard.py` |

---
<!-- nav-footer -->
**Navigate:** [Up: guide index](../INDEX.md) - [Home](../../README.md)
