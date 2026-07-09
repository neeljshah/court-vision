# Pregame Player-Prop Models — Cross-Sport Pricing Chain

Player-prop pricing follows the same shape in every sport: a **rate** (per-possession,
per-plate-appearance, per-90-minutes) times an **exposure estimate** (minutes, batters
faced, expected playing time) produces a mean, a **dispersion model** turns that mean into a
full count distribution, and a **calibration layer** maps model output to a trustworthy
`P(over)`. This page is the cross-sport index; the NBA chain is the deepest and is described
first in full, followed by the sport-specific variants.

Every number here is a calibration/sharpness claim (R², MAE, ECE, coverage), never a
promised profit edge — see [`calibration-and-validation.md`](calibration-and-validation.md)
for the full honesty framing this inherits.

---

## NBA — the deepest prop chain

**Primary files:** `src/prediction/player_props.py` (3,296 lines),
`src/prediction/prop_model_stack.py` (921 lines), plus domain-side pricing helpers in
`domains/basketball_nba/`.

### Layer 1 — base pricing (`player_props.py`)

`price_prop(player, stat, line, date)` is leak-free by construction: `_player_history`
filters strictly to games before the pricing date. It blends rolling L5/L10/L20 empirical
hit-rates with a recency-weighted Gaussian (last-15 games, linear recency weights), and
converts to `p_over` via an erf-based normal CDF (`_phi`). It also supports derived combo
markets — `PRA`/`PR`/`PA`/`RA`, `price_double_double`, and `price_player_card`.

### Layer 2 — empirical-CDF alternative (`prop_quantile_pricer.py`)

`price_empirical_over(sample, line, dates, as_of, half_life_days=60)` replaces the Gaussian
tail assumption with a recency-weighted **empirical CDF** (exponential decay weights over
the player's own game log; falls back to `UNAVAILABLE` below a 5-game minimum sample). This
matters most for heavy-tailed, low-count stats (blocks, steals, 3-pointers made) where a
Gaussian tail systematically misprices the extremes.

### Layer 3 — conformal interval alternative (`prop_cqr.py`)

`run_cqr_gate()` implements **Conformalized Quantile Regression**: LightGBM quantile models
trained on a chronological TRAIN fold, conformalized on a CALIB fold, and evaluated
(coverage + pinball loss) on a TEST fold against the incumbent constant-width
split-conformal band. This is a default-off measurement script — a candidate interval
method, not something currently wired into live pricing.

### Layer 4 — sigma calibration (`prop_sigma_calib.py`, `prop_sigma_asym.py`)

`load_scale_factors()` derives a per-stat multiplicative sigma-inflation factor `k >= 1.0`
from out-of-fold residuals (the empirical z-score at the 68.27th percentile), clamped to
never *deflate* an interval — only widen a too-narrow one. `prop_sigma_asym.py` extends this
to **asymmetric** tail inflation (separate `k_up`/`k_down`, from an IQR-based robust sigma
estimate), because NBA count stats are right-skewed and floored at zero — a symmetric sigma
under-covers the upside tail and over-covers the (impossible) downside. This is currently a
readout/measurement module, not wired into the served interval.

### Layer 5 — the stacking meta-model (`prop_model_stack.py`)

Stacks the outputs of 7 per-stat base models (`pts`, `reb`, `ast`, `fg3m`, `stl`, `blk`,
`tov`) through a **Ridge regression meta-model** trained on residuals. Meta-features include
the base prediction itself plus DNP risk, injury multiplier, recent-form z-score, and
motivation flags (contract year, load management, breakout signal). A **confidence gate**
suppresses low-quality predictions outright (`|base_pred - line| < edge_threshold`, or
`dnp_prob > 0.30`, or `injury_mult < 0.70`) rather than emitting an untrustworthy number.
Three base-learner backends are registered (`BASE_LEARNERS`): XGBoost (`props_{stat}.json`),
LightGBM (`props_lgb_{stat}.pkl`), CatBoost (`props_cb_{stat}.cbm`) — `predict_base_learner`
loads whichever artifact exists per stat and returns `None` (not a fabricated value) if the
file is missing.

### Layer 6 — over/under win-probability calibration (`CalibrationLayer`)

`CalibrationLayer.train_win_prob()` maps the model's implied edge (`pred/line - 1`) to
`P(actual > line)` via isotonic regression, one calibrator per stat
(`calibration_win_{stat}.joblib`). When a stat has no fitted calibrator, it falls back to a
sigmoid `1 / (1 + exp(-edge/0.15))`, always clamped to `[0.05, 0.95]` — never a raw,
unclamped probability. A `CohortCalibrator` can further condition on minutes/usage/rest
segments where the data supports it, otherwise falling back to the global calibrator (safe
passthrough, never a KeyError).

### Recorded verdicts (what shipped vs. what was rejected)

The feature-block-level walk-forward gate applied to this chain has produced honest rejects
alongside ships — see the rejected-block table in
[`feature-inventory.md`](feature-inventory.md#how-the-prop-feature-stack-is-built-and-what-the-gate-rejected)
for the full list (e.g. advanced-stat rolling windows regressed 5 of 7 stats; officiating
crew tendency was a holdout-slice artifact that regressed all 7 walk-forward; a REB
LightGBM quantile backend shipped after beating the incumbent 4/4 folds).

---

## Soccer — Poisson/NegBinom prop engine

**File:** `domains/soccer/prop_engine.py`

`prop_distribution()` builds `lam = per90_rate * E[minutes]/90 * opponent_multiplier`, using
per-90 rates from `domains/soccer/player_rates.py` and expected-minutes from
`domains/soccer/player_minutes.py`. The count distribution is Poisson by default, or
Negative-Binomial when a `dispersion` parameter is supplied (see below). `p_over(line)` and
`prop_ladder()` (an alt-line ladder across several thresholds) never raise — an unresolvable
player/stat degrades to `status: "unknown"` rather than fabricating a number.

**`dispersion.py`** is the soccer-specific dispersion calibrator: it estimates a per-stat
overdispersion ratio `phi = variance/mean` from real data (shots ~1.35, shots-on-target
~1.25, fouls ~1.20, via a `_PRIOR_PHI` table), converts to a row-specific Negative-Binomial
size parameter `r = lambda/(phi-1)`, and is the mechanism that prevents Poisson's
under-dispersion from fabricating false tail confidence on prop markets.

**`prop_recal.py`** performs per-stat isotonic recalibration (with a pure-Python PAVA
fallback if scikit-learn is unavailable), requiring a 150-pair minimum sample per stat or
falling back to identity — explicitly flagged in the code as "THIN" given the current corpus
size (~24 World Cup matches at time of writing).

**`prop_settle.py`** grades a settled prop against realized ESPN per-player stats, with a
specific correctness fix worth noting: it distinguishes a *genuine* zero from a *missing*
(DNP) value rather than fabricating a realized zero for a player who didn't play — tracked
by an explicit `SETTLE_LOGIC_VERSION` marker so old-logic cached grades can't be mistaken for
a validated calibration result.

---

## MLB — rate x exposure prop engine

**File:** `domains/mlb/prop_engine_mlb.py`

Same shape as soccer's engine and in fact reuses its core PMF math
(`domains/soccer/prop_engine._make_p_over`, a sport-blind function): `lam = rate x exposure`,
where exposure is `E[PA]` for batter props (per-plate-appearance rate x expected plate
appearances) or `E[BF]` for pitcher props (per-batter-faced rate x expected batters faced);
per-start counting stats (e.g. innings pitched) are modeled directly. Distribution is
Poisson by default or Negative-Binomial when a dispersion `r` is supplied. Like the soccer
engine, it degrades to `status: "unknown"` rather than raising or fabricating.

**Evaluation gates specific to MLB props:**
- **`props_eval_gate_mlb.py`** ("Lane 3") — a leak-free per-opportunity evaluator for
  starting-pitcher strikeouts/hits/walks: a walk-forward exponentially-weighted rate times
  expected-batters-faced projection, scored by CRPS and pinball loss against two baselines
  (season mean, league average) across three independent corpora (a fit corpus and two
  separate holdout corpora). A verdict requires beating both baselines in **both** holdouts
  (the conservative worst-of-two rule) with a minimum-30-observations floor per holdout. No
  historical prop market line exists on disk for MLB props, so this is explicitly labeled
  "calibration-vs-outcome only" — there is no close to compare against.
- **`props_eval_shootout2_mlb.py`** ("Lane 4") — a four-way baseline shootout (season mean,
  league-shrunk, exponentially-weighted, prior-season) to determine which naive baseline is
  actually hardest to beat; the standing baseline is only replaced if one family wins both
  holdouts independently, otherwise `season_mean` remains standing "by parsimony" — a
  deliberately conservative default.

---

## Cross-sport pattern summary

| Sport | Rate source | Exposure estimate | Dispersion model | Calibration |
|---|---|---|---|---|
| NBA | Rolling/recency-weighted per-game rates | (implicit in per-game modeling) | Empirical CDF (heavy tails) or Gaussian; asymmetric sigma inflation measured | Isotonic per-stat, cohort-conditioned, sigmoid fallback |
| Soccer | Per-90 rate (`player_rates.py`) | Expected minutes (`player_minutes.py`) x opponent multiplier | Negative-Binomial, `phi` from a prior table | Per-stat isotonic, 150-pair minimum, identity fallback |
| MLB | Per-PA (batter) / per-BF (pitcher) rate | Expected PA / BF | Negative-Binomial (shared math with soccer) | Walk-forward CRPS/pinball vs. multiple baselines (no market close available) |

Every engine in this table shares the same discipline: never raise on missing data (degrade
to an explicit "unavailable"/"unknown" status), never silently zero-fill a rate, and gate any
new dispersion or calibration layer on an out-of-fold or walk-forward improvement before it
is trusted.

---

## Related

- [`calibration-and-validation.md`](calibration-and-validation.md) — the calibration/leak-avoidance discipline this page's models inherit
- [`feature-inventory.md`](feature-inventory.md) — the full NBA prop feature stack and its walk-forward-rejected blocks
- [`model-registry.md`](model-registry.md) — the NBA prop-model artifact inventory (which `.pkl`/`.json` file backs which stat)
- [`signal-factory-and-ratings.md`](signal-factory-and-ratings.md) — upstream signals these prop models consume
