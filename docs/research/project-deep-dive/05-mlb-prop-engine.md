# 05 - MLB Prop Engine + MLB Team Domain

Deep-dive into the MLB player-prop model (batter per-PA / pitcher per-BF rate x
exposure -> count distribution -> P(over line)) and the surrounding MLB team
domain (MOV-Elo win-prob, NegBinom runs surface, in-game repricer, ingest).

Honesty rails (binding): markets are efficient. The honest win is CALIBRATION,
not a $-edge. Nothing here claims profit. Where something is in-sample, thin,
overfit, or built-but-unread, it is flagged as such. ASCII only.

---

## 0. TL;DR ground truth (read this first)

- The MLB **team** domain is real, leak-free, wired into the live predictor stack,
  and honest (matches/trails the close; clean NULL on in-game recal).
- The MLB **player-prop** engine is a clean, well-structured Poisson/NegBinom
  rate x exposure pipeline -- but it is currently **STRANDED and UNVALIDATED**:
  - Its only consumer is its own backtest (`props_eval_mlb.py`). No live/API/loop
    path consumes `prop_distribution`.
  - The player gamelog corpus is **17 days deep** (`player_gamelogs.parquet`:
    2026-06-01..2026-06-17, 6,558 rows, 220 games, 920 players).
  - The leak-free calibration backtest currently scores **0 predictions**
    (`data/domains/mlb/prop_calibration.json` -> `overall.n = 0`, all metrics
    `null`). With strictly-prior history required and only ~6 games/player median,
    almost every player-game is SKIPPED for lack of a prior. **There is no MLB
    prop calibration number yet -- positive OR negative.**

So: the team model is the genuine asset; the prop engine is correct machinery
sitting on top of a near-empty data corpus.

---

## 1. INVENTORY (exists AND used)

### Player-prop engine (the focus area)

| File | Purpose |
|------|---------|
| `domains/mlb/ingest_player_stats.py` | Per-player per-game batting+pitching rows from the free statsapi boxscore (`/game/{pk}/boxscore`); writes `player_gamelogs.parquet`. The substrate. |
| `domains/mlb/player_rates_mlb.py` | Leak-free empirical-Bayes-shrunk per-PA (batter) / per-BF (pitcher) / per-start (Outs) rate priors. Defines `MLB_CANON` stat map. |
| `domains/mlb/exposure_mlb.py` | Leak-free expected exposure: `expected_pa` (batter, recent mean or lineup-slot prior), `expected_bf` (pitcher, recent mean). |
| `domains/mlb/prop_engine_mlb.py` | Combines rate x exposure -> `lam` -> Poisson/NegBinom count dist -> `p_over(line)` + alt-line ladder. |
| `scripts/platformkit/props_eval_mlb.py` | Leak-free walk-forward CALIBRATION backtest of the prop engine; writes `prop_calibration.json`. The only consumer. |
| `domains/mlb/test_prop_engine_mlb.py`, `test_player_rates_mlb.py`, `test_ingest_player_stats.py` | Per-file tests (canned in-memory frames). |
| `scripts/platformkit/test_props_eval_mlb.py` | Per-file test for the backtest harness. |

### MLB team domain (the surrounding system, USED)

| File | Purpose |
|------|---------|
| `domains/mlb/predictor.py` | `MLBPredictor`: the system's best calibrated MLB game surface (win-prob + runs + O/U + full market surface + `to_jd` + `predict_live`). |
| `domains/mlb/inning_engine.py` | `RunRateState` (EW off/def run-rate lambdas) + Poisson `runs_matrix` + `markets_from_matrix` + `anchor_lambdas_to_winprob` + `build_engine_forecast` eval harness. |
| `domains/mlb/negbinom_engine.py` | Over-dispersed NegBinom run marginals; `fit_dispersion_first_half` (leak-free MoM r), `runs_matrix_nb`, `markets_from_matrix_nb`. |
| `domains/mlb/negbinom_sim.py` | `build_mlb_jd` -> a `JointDistribution` of (home_runs, away_runs) for the kernel sim/sgp surface. |
| `domains/mlb/markets.py` | `full_market_surface`: complete derivable market set (ML, run line + alts, team totals, F5) -- pure reprice of the same NegBinom matrix. |
| `domains/mlb/repricer.py` | `MLBRepricer.reprice` -- in-game re-pricing with empirical per-inning run curve. |
| `domains/mlb/ingest_current.py` | Pulls FINAL games 2022..2026-06-16 from statsapi -> `games_current.parquet`, mapped onto frozen SBR codes. |
| `domains/mlb/refresh_ratings.py` | Concatenates frozen (2010-2021) + current corpus -> `refreshed_predictor()` (ratings as-of 2026-06-16). |
| `domains/mlb/asof_sp_form.py` | Leak-free EW first-6-innings starting-pitcher form feature (`sp_first6_diff_ew`). |
| `domains/mlb/sp_elo_offset.py` | SP-aware Elo offset: `p_home = sigmoid(elo_logit + w * z_sp)`, w fitted leak-free. |
| `scripts/platformkit/proof_mlb/beat_the_close_ml.py` | The MOV-Elo win-prob engine (`final_ratings`, `_p_home`) -- single source of truth scored vs the devigged close. Imported by `predictor.py` (W150 parity). |

### Data (inspected)

| Parquet | Shape | Span | Note |
|---------|-------|------|------|
| `player_gamelogs.parquet` | 6,558 x 27 | 2026-06-01..06-17 | **17 days only**; 220 games, 920 players, median 6 games/player, max 16. 1,874 pitcher rows / 4,684 batter rows. |
| `games.parquet` (frozen) | 27,983 x 10 | 2010-2021 | Team-game corpus; the prop engine does NOT use this. |
| `games_current.parquet` | 10,826 x 10 | 2022-04..2026-06-16 | Extends frozen for live ratings. |
| `pitchers.parquet` | 27,983 x 11 | 2010-2021 | Per-game SP line-score strings; feeds `asof_sp_form`. |
| `prop_calibration.json` | n=0 | as_of 2026-06-18 | **Empty: zero scored prop predictions.** |

---

## 2. HOW IT WORKS (data flow + key algorithms)

### 2.1 Player-prop pipeline (the rate x exposure Poisson model)

```
ingest_player_stats -> player_gamelogs.parquet (one row / player / game)
         |
player_rates_mlb.batter_rate / pitcher_rate  (leak-free, EB-shrunk per-exposure rate)
exposure_mlb.expected_pa / expected_bf       (leak-free expected exposure)
         |
prop_engine_mlb.prop_distribution: lam = rate x exposure
         |
soccer.prop_engine._make_p_over(lam, model, r)  (shared sport-blind Poisson/NB pmf)
         |
p_over(line)  ->  prop_ladder (alt lines)
```

**Rate model** (`player_rates_mlb.py`):
- `MLB_CANON` (`player_rates_mlb.py:61`) maps each canonical stat to raw columns +
  role + exposure unit:
  - Batters (exposure=PA): Hits, Total Bases, RBIs, Runs, Home Runs, Walks,
    Batter Strikeouts, Stolen Bases, Hits+Runs+RBIs.
  - Pitchers (exposure=BF): Pitcher Strikeouts, Earned Runs, Hits Allowed,
    Walks Allowed; **Outs is exposure=start** (`PER_START_STATS`, line 69).
- `batter_rate(df, player_id, stat, as_of)` (`:172`): leak-free rows are those with
  `date < as_of` (`_prior_rows`, `:91`). `per_pa = sum(stat)/sum(PA)` over the
  player's own prior rows, then empirical-Bayes shrunk toward the pooled league
  per-PA baseline: `(n_pa*raw + K*baseline)/(n_pa + K)`, `SHRINK_K = 30.0` (`:32`).
  PA proxy = `atBats + baseOnBalls + hitByPitch` (`_pa_total`, `:118`).
- `pitcher_rate` (`:206`): same shape per-BF (`battersFaced`), except Outs which is
  per-start with `SHRINK_K_START = 3.0`.
- Degrades to `{"status": "unknown"}` when neither player nor league has signal;
  never raises.

**Exposure model** (`exposure_mlb.py`):
- `expected_pa(df, pid, as_of, batting_order)` (`:51`): mean PA over the player's
  last `_RECENT_GAMES = 15` prior games; falls back to lineup-slot prior
  `_LINEUP_PA` (1->4.6 ... 9->3.7, `:28`) or `_DEFAULT_PA = 4.0`.
- `expected_bf(df, pid, as_of)` (`:80`): mean `battersFaced` over the last 15 prior
  appearances (this self-separates starters ~24 from relievers); default 24.0.

**Distribution** (`prop_engine_mlb.py`):
- `_resolve_rate_and_exposure` (`:50`): `lam = per_pa * E[PA]` (batter) /
  `per_bf * E[BF]` (pitcher) / `per_start` directly (Outs).
- `prop_distribution(...)` (`:105`) returns
  `{lam, model, p_over(callable), status, rate, exposure, n}`. `model="poisson"`
  unless `dispersion` (NB size r>0) given. The pmf + `p_over = P(X>line)` math is
  IMPORTED from `domains/soccer/prop_engine._make_p_over` (`:37`) so the two
  sports' prop math can never drift.
- `prop_ladder` (`:166`) returns an alt-line `[{line, p_over, p_under}]` ladder;
  unknown -> `None` probs (never a fabricated number).

### 2.2 Which prop stats are sound vs over-projected (the central question)

The engine treats EVERY count stat as Poisson(lam) (or NegBinom). That is a
strong distributional assumption and is **not equally valid across stats**:

- **Soundest (genuinely ~Poisson / Bernoulli-sum per opportunity):**
  - Pitcher Strikeouts (per-BF K, large BF -> approx Poisson; mildly over-dispersed,
    which is exactly what the `dispersion` r argument is for).
  - Batter Strikeouts, Walks, Walks Allowed -- per-PA/BF Bernoulli-ish events.
  - Hits, Hits Allowed -- a per-PA Bernoulli success count; Poisson is a reasonable
    approximation for the low counts involved.
  - Outs (per-start) -- modelled directly, exposure-natural, the cleanest target.
- **Rough / likely OVER-projected as Poisson (flagged in the engine docstring,
  `prop_engine_mlb.py:17`):**
  - **Total Bases** -- NOT a count of independent events; it is a weighted sum
    (1B=1, 2B=2, 3B=3, HR=4). Modelling the SUM as one Poisson conflates frequency
    and magnitude and gets the variance/tail wrong. A compound (e.g. count x
    base-value) model would be more honest.
  - **RBIs / Runs** -- highly context-dependent (lineup, baserunners, batting
    order); a single per-PA rate ignores the conditional structure, so the marginal
    shape is mis-specified. The variance is not mean (often over-dispersed).
  - **Hits+Runs+RBIs** -- a sum of three correlated stats; Poisson on the sum
    ignores their positive correlation and understates the tail.
  - **Home Runs / Stolen Bases** -- very low rate, very lumpy; Poisson tail is the
    least bad here but small-N rate estimates dominate the error.

The engine's own docstring is honest about this: Poisson assumes var==mean, MLB
counting stats (esp. K) are mildly over-dispersed, so pure Poisson makes tails too
TIGHT and "FABRICATES fake edges" -- hence the `dispersion` (NB r) lever. But that
r is a PRIOR and is **not yet calibrated** for props (see Section 5).

### 2.3 MLB team model + the starting-pitcher lever

**Win probability** = leak-free walk-forward MOV-aware Elo
(`proof_mlb.beat_the_close_ml.final_ratings` / `_p_home`), imported directly into
`MLBPredictor.__init__` (`predictor.py:115-133`) so `predict()` and the
beat-the-close measurement use the SAME ratings (W150 parity).

**Expected runs** = `RunRateState` (`inning_engine.py:158`): an EW off/def run-rate
state, `ALPHA=0.06`, `MU_INIT=4.4`, `HFA=1.04`, `SEASON_REGRESS=0.25`.
`lam_home = HFA * off_home * def_away / mu`, `lam_away = off_away * def_home / mu`
(`snapshot`, `:186`), snapshot-before-update (leak-free).

**O/U + run-line surface** = over-dispersed NegBinom (`negbinom_engine.py`):
`fit_dispersion_first_half` (`:78`) fits r via method-of-moments on the first 50%
of the corpus (leak-free); `r = mu^2/(var-mu)`, with `_UNDERDISP_R=1e6` (-> Poisson)
when under-dispersed and `_MIN_R=0.5` floor. This closes the W149 audit "hardcoded
r" gap. `runs_matrix_nb` builds the independent-NegBinom joint; `markets_from_matrix_nb`
projects ML/RL/totals.

**Coherence** (`predictor.py`'s real contribution): `predict()` (`:158`) reports the
Elo win-prob, then TILTS the run-rate lambdas (`_anchor_nb_tiesplit`, `:72`,
SUM preserved so expected total is unchanged) so the NegBinom matrix tie-adjusted ML
== the reported Elo p_home. Result: ML, run-line, totals, team totals, and `to_jd`
all share ONE win-prob. `full_market_surface` (`markets.py`) re-reads that same
matrix for every market shape.

**Starting-pitcher lever** (`asof_sp_form.py` + `sp_elo_offset.py`):
- `asof_sp_form.build_sp_form_features` (`:170`): EW (`EW_ALPHA=0.35`) trailing
  first-6-innings runs-allowed per SP, snapshot-before-update, `MIN_PRIOR_STARTS=3`
  (NaN below). Strips bullpen innings -- the biggest confound in a career-mean proxy.
  Emits `sp_first6_diff_ew` (positive -> home SP historically allowed fewer runs).
- `sp_elo_offset.py`: `p_home = sigmoid(logit(p_elo) + w * z_sp)`, single scalar w
  fitted leak-free on a time-split. This is the honest, validated SP lever.
- NOTE: the SP lever lives in the proof/calibration layer
  (`scripts/platformkit/proof_mlb/fusion_mlb.py`, `calibration_providers.py`,
  `calibration_scoreboard.py`). It is **NOT wired into `MLBPredictor`** -- the live
  predictor's win-prob is pure MOV-Elo (no SP adjustment). The SP signal is measured
  but not yet delivered in the predictor's number.

### 2.4 In-game repricer (`repricer.py`)

`MLBRepricer.reprice(state)` (`:79`): `remaining_frac` from an EMPIRICAL per-inning
run curve `_INNING_SHARES` (`:36`, 1st inning ~12.2%, late innings less),
linearly interpolated at fractional innings; scales pregame lambdas, builds the
remaining-runs NegBinom matrix, shifts by runs already scored, reprices. Keeps a
regulation tie live with one extra-inning residual lambda. `predictor.predict_live`
(`:229`) anchors lambdas to Elo first, then passes fitted r through the repricer,
then applies the W156 in-game recalibrator = **IDENTITY** (a clean validated NULL:
held-out ECE 0.0085, slope 0.98; a fitted Platt would worsen it).

HONESTY flags in the code itself: the per-inning curve is GLOBAL and IN-SAMPLE
(fit on the same linescores it scores; OOS verdict deferred to `proof_mlb/curve_oos.py`,
`repricer.py:34`), and the NegBinom thinning (scale lam, reuse full-game r) is an
APPROXIMATION, not a leak (`:80`).

---

## 3. HOW IT IS USED (callers / consumers)

### Team domain (live, consumed)
- `scripts/platformkit/live_read.py` (`:69`): builds `MLBPredictor` and calls
  `predict_live` for the in-game read (cached one instance/process).
- `scripts/platformkit/predictor_jd.py` (`:64`): builds `MLBPredictor().to_jd(...)`
  for the kernel sim / sgp market surface.
- `domains/mlb/refresh_ratings.py`: `refreshed_predictor()` for as-of-today ratings.
- The `predict-matchup` / `cross-sport-benchmark` / `calibration-report` skills route
  MLB through this predictor and the `proof_mlb` engines.
- `inning_engine.build_engine_forecast` is a walk-forward EVAL harness (engine vs Elo),
  not a per-game live wiring; `runs_matrix` (Poisson) is research/demo-only (superseded
  by the NegBinom engine).

### Prop engine (NOT consumed in production)
- The ONLY caller of `prop_distribution` / `prop_ladder` / `backtest_calibration_mlb`
  is `scripts/platformkit/props_eval_mlb.py` (its own backtest) + the per-file tests.
- No API endpoint, no live board, no betting loop reads the MLB prop engine.
  `prop_edge.py` wires the SOCCER prop engine, not MLB. The MLB prop engine is
  effectively **stranded / built-but-unread** beyond its evaluator.

`props_eval_mlb.backtest_calibration_mlb` (`:167`): walk-forward over games by date;
for each player-row it feeds the player's **realized** exposure (so it tests RATE/shape
calibration, not exposure projection), picks the .5 line nearest lam
(`_nearest_half_line`), records `p_over` vs realized outcome, scores with the
sport-agnostic `score_prop_predictions` (Brier/ECE/BSS with sharpness pairing so a
collapse-to-0.5 model can't look good). `write_calibration_cache_mlb` caches per-stat
BSS to `prop_calibration.json`.

---

## 4. STRENGTHS (genuinely solid)

1. **Leak-freeness is rigorous and consistent.** Every rate/exposure uses strictly
   `date < as_of` rows (`_prior_rows`); the team Elo, run-rate, dispersion fit, and SP
   form are all snapshot-before-update. This is the load-bearing discipline and it is
   done right.
2. **Honest by construction.** Functions degrade to `{"status": "unknown"}` instead of
   fabricating a probability; the backtest SKIPS no-prior games rather than inventing
   one; docstrings explicitly flag the over-projection risk on Total Bases/RBIs/Runs
   and label every in-sample/approximation choice. No $-edge is claimed anywhere.
3. **Sport-blind code reuse.** The Poisson/NB pmf + `p_over` math is shared with the
   soccer engine (`_make_p_over`), so the two prop engines cannot drift; the team
   win-prob is the SAME object the beat-the-close proof scores (W150 parity).
4. **Coherent team market surface.** `predictor.predict()` delivers ONE win-prob that
   anchors ML, run-line, alt run-lines, totals, team totals, and the JD -- a genuinely
   coherent surface Elo alone cannot emit, and the over-dispersion is FITTED, not
   hardcoded (closes the W149 audit).
5. **The empirical-Bayes shrinkage is the right tool** for thin player priors
   (call-ups, spot starters) and is exposure-weighted correctly.
6. **The SP lever is real and validated** (EW first-6 RA + leak-free fitted offset),
   and the in-game recal is an honest measured NULL (identity), not a forced fit.

---

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS (brutally honest)

1. **The prop engine has ZERO validation today.** `prop_calibration.json` is empty
   (`overall.n = 0`, all metrics null); the readout prints no rows. With only a
   17-day gamelog corpus and ~6 games/player median, almost every player-game has no
   strict prior, so the walk-forward scores nothing. **There is currently no evidence
   the MLB prop probabilities are calibrated -- they are unmeasured.** This is the
   single biggest gap.
2. **The corpus is 17 days deep** (`player_gamelogs.parquet`: 2026-06-01..06-17). For
   a sport with a 162-game season this is the thinnest possible slice. Rates are
   dominated by the league baseline (heavy shrink) and exposure means are noisy.
3. **Distributional mis-specification on multi-value stats.** Total Bases, RBIs, Runs,
   and Hits+Runs+RBIs are NOT independent-event counts; Poisson (or even a single-r
   NegBinom) gets their variance and tails wrong. These will be the worst-calibrated
   stats and are the most likely to fabricate fake edges if ever bet. The docstring
   admits this; the code does not yet correct it.
4. **The prop engine is stranded** -- no production consumer. It is machinery without
   a delivery path; effort beyond the backtest is currently unobservable to any user.
5. **`dispersion` (NB r) for props is never set / never fit.** `prop_distribution`
   defaults to Poisson; nothing fits a per-stat r from realized prop outcomes. The
   one widening lever the engine has is unused for props.
6. **League baseline pooling is coarse.** `_league_per_exposure` pools ALL prior rows
   (across all parks, opponents, handedness) into one per-exposure number; no
   park, opponent-pitcher, or platoon (L/R) adjustment exists in the rate. For a
   sport where park and opposing-pitcher effects are large, this is a real ceiling.
7. **No correlation / joint structure for props.** Each stat is priced
   independently; HR and Total Bases (or H+R+RBI components) are correlated, but
   there is no joint model -- so any same-player parlay would be mispriced.
8. **SP lever not delivered in the predictor.** `sp_elo_offset` is validated in the
   proof layer but `MLBPredictor.predict()` uses pure MOV-Elo; the measured SP signal
   never reaches the live number. (The biggest single-game variable in MLB -- who is
   pitching -- is absent from the delivered win-prob.)
9. **In-sample shape choices in the team layer.** The per-inning run curve
   (`repricer._INNING_SHARES`) and the F5 fraction (`markets.F5_FRACTION=0.521`) are
   fit on the same corpus they score; the code flags this and defers OOS to
   `proof_mlb/curve_oos.py`, but the delivered live number still uses the in-sample
   curve.
10. **Two-corpus team-name mapping is brittle.** `ingest_current.NAME_TO_CODE` hand-maps
    full names to non-standard SBR 3-letter codes; a franchise rename or a name the
    map misses silently drops games (the `Athletics` rebrand is handled, but the map
    is a manual list).
11. **Thinning approximation in the repricer** (scale lam, reuse full-game r): a
    thinned NegBinom is not NegBinom with the same r, so the partial-inning tail is
    slightly mis-specified (flagged as a modeling assumption, not a leak).

---

## 6. PLAN TO GET BETTER (prioritized)

### Quick wins (days)
1. **Backfill the player gamelog corpus to a full season+ via
   `ingest_player_stats.ingest_range`** (statsapi is keyless). Going from 17 days to
   1-2 seasons is the prerequisite for ANY prop calibration number. This single step
   unblocks items 2-5.
2. **Re-run `props_eval_mlb` and publish the per-stat Brier/ECE/BSS scoreboard.** Get
   the first honest calibration verdict per stat. Expect K/Hits/Walks/Outs to be
   reasonable and Total Bases/RBIs/Runs to be poor -- report it either way.
3. **Demote or relabel the rough stats.** Based on (2), mark Total Bases/RBIs/Runs/
   H+R+RBI as "shape-uncalibrated, display-only" in the engine output until a better
   model exists. Honest scoping beats a pretty-but-wrong number.
4. **Fit a per-stat NegBinom r from realized outcomes** and wire it as the default
   `dispersion` per stat (the lever already exists; it is just never set). This is the
   cheapest correctness fix for the over-tight Poisson tails.

### Medium (weeks)
5. **Wire the SP lever into `MLBPredictor`.** Promote the validated
   `sp_elo_offset` (Elo logit + w*z_sp) into the predictor's win-prob so the delivered
   number reflects who is pitching. Re-score vs the close to confirm it does not hurt
   calibration.
6. **Compound model for Total Bases** (and the correlated H+R+RBI): model hit COUNT x
   base-value mixture (or a per-event categorical 1B/2B/3B/HR) rather than one Poisson
   on the weighted sum. Validate the tail calibration.
7. **Add park + opposing-pitcher + platoon adjustments to the rate.** Multiply the
   per-PA rate by a leak-free park factor and an opponent-SP factor (the team domain
   already has `asof_park.py` and SP form). This is the analog of soccer's opponent
   strength and is where the bulk of remaining prop signal lives.
8. **Give the prop engine a delivery path** (a `props_read` analog of `live_read`, or
   an API surface) so it stops being stranded and gets exercised on live slates with a
   paper CLV ledger.

### Bigger bets (months)
9. **Season-priors layer (the soccer-club-priors analog).** Pull statsapi SEASON
   stats (season per-PA/per-BF rates, splits) as a strong, low-variance prior to shrink
   toward -- replacing the coarse all-rows league pool. MLB's full season makes this
   genuinely informative (unlike NBA recency-beats-volume). This is the highest-ceiling
   structural improvement for the rate model.
10. **Joint same-player prop model** (copula or shared-latent) so correlated props
    (HR/TB, H+R+RBI) are priced coherently and parlays are not mispriced.
11. **Replace in-sample shape constants** (inning curve, F5 fraction) with the
    leak-free OOS-validated versions from `proof_mlb/curve_oos.py` before they drive a
    live number.

---

## 7. HOW GOOD CAN IT GET (honest ceiling)

**Realistic best:** a **well-calibrated** MLB prop and team predictor whose
probabilities match realized frequencies (low ECE, positive BSS vs base rate) on the
soundest markets, and that **matches the devigged close within noise** on team
moneyline/totals. MLB is the most favourable sport in this system for honest
calibration BECAUSE it has a full 162-game season: per-player and per-team rate
estimates converge, season priors are informative, and there is enough volume to
actually measure ECE per stat with statistical power. That is a real, defensible,
recruiter-grade outcome.

**What it will NOT become:** a profit edge. MLB markets -- especially mainline
totals, run lines, and the liquid star props -- are efficient and sharp; the books
see the same statsapi data, the confirmed lineup, the starting pitcher, and the
weather. The honest ceiling is "as good as the closing number, occasionally as fresh
on a late lineup/pitcher scratch," not "beats the close."

**What limits the ceiling:**
- **Data freshness, not history.** As elsewhere in this system, the unpriced gap is
  same-day information (confirmed lineup, scratch, weather, bullpen availability) the
  model cannot see faster than the book. History is at-ceiling once a season is loaded.
- **Stat structure.** Total Bases / RBIs / Runs will always be harder to calibrate
  than K / Hits / Outs because they are context-driven sums, not independent-event
  counts. The compound/joint models in Section 6 raise their floor but not to the
  level of the clean per-opportunity stats.
- **Current state vs ceiling.** Today the prop engine is at ~0% of that ceiling
  (zero scored predictions on a 17-day corpus). The team model is much closer:
  leak-free, coherent, parity-with-close on ML, honest NULL in-game. The fastest path
  to realizing the ceiling is the corpus backfill + first calibration scoreboard
  (Section 6 items 1-2), after which the structural model improvements (SP lever,
  season priors, compound TB) can be measured rather than asserted.
