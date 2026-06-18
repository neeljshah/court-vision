# 11 -- Live / In-Game Conditioning Layer

> Deep-dive for a human reader. READ-ONLY analysis; no code changed.
> Binding frame: markets are efficient. The honest win here is CALIBRATION
> (sharper, well-calibrated forecasts once the realized score is known), NOT a
> dollar edge. A live book also sees the score, so any "in-game advantage" is
> forecaster QUALITY, not realized profit. No $-edge is claimed anywhere below.

The in-game layer is the project's most-cited "decisive combinable edge": the
pregame line is efficient and we only match the devigged close, but once a game
is underway the realized score is genuinely NEW information that the pregame
close never had. Conditioning on it produces a measurably sharper, better-
calibrated forecast. That is a real, defensible improvement -- but it is a
calibration win, and the dollar edge is gated separately and not claimed.

There are effectively TWO parallel in-game stacks in this repo:

1. The **platform / multi-sport repricer stack** (clean, sport-blind, <=300 LOC
   per file, additive, gated): `GameState -> get_repricer(sport).reprice()` and
   the per-sport `predictor.predict_live()` wrappers + the eval-gate blend core.
   This is the maintained, honest, cross-sport frontier.
2. The **legacy NBA live_engine stack** (`src/prediction/live_engine.py`, 2719
   lines): the original cycle-88..R10 player-prop in-game projector with ~20
   stacked override heads, almost all gated default-OFF. Production-wired into
   the FastAPI live page but largely a research surface now.

---

## 1. INVENTORY -- components that exist and are used

### Platform repricer stack (sport-blind, the maintained frontier)

- `scripts/platformkit/live_repricer.py` -- `GameState` dataclass + `Repricer`
  Protocol + `get_repricer(sport)` factory; concrete `SoccerRepricer`; generic
  `_SportStub` for unwired sports.
- `domains/basketball_nba/repricer.py` -- `NBARepricer`: Gaussian score-anchor
  remaining-points model (margin/total Normal with Brownian variance collapse).
- `domains/mlb/repricer.py` -- `MLBRepricer`: over-dispersed NegBinom run engine,
  per-inning run-share curve, extra-innings residual lambda.
- `domains/tennis/repricer.py` -- `TennisRepricer`: analytic race-to-N-sets
  conditional match-win probability (Brier-graded, no re-sim).
- `domains/soccer/scoreline_engine.py` -- consumed by `SoccerRepricer`
  (`scoreline_matrix`, `markets_from_matrix`; Dixon-Coles bivariate Poisson).
- `domains/<sport>/predictor.py::predict_live(...)` -- the CALIBRATED wrappers
  (NBA `predictor.py:202`, MLB `:229`, soccer `:250`, soccer_intl `:157`,
  tennis `:161`). Each anchors the repricer to the same Elo/MOV win-prob the
  pregame `predict()` reports, then applies a fitted recalibrator.
- `scripts/platformkit/live_read.py` -- `build_live_read(sport, state)`: fuses
  the calibrated `predict_live` surface (graceful fallback to raw repricer) with
  the brain's in-game concept families; `render_markdown`.
- `scripts/platformkit/live_read_cli.py` -- CLI for `live_read`.
- `scripts/platformkit/frontend/live_board.py` -- `todays_live_games(sport)`:
  pulls today's real ESPN keyless scoreboard, normalizes each game, feeds
  in-progress games through `predict_matchup.build_result` (-> `predict_live`).

### Eval-gate / blend reference cores (validation machinery)

- `scripts/platformkit/eval_gate/ingame_blend.py` -- the reference blend core:
  `blend()`, `fit_weight_surface()`, `WeightSurface`, `blended_predictions()`,
  `exp_smooth()`, `time_bucket()`, `margin_bucket()`.
- `domains/basketball_nba/ingame_blend_plive.py` -- `build_state_features`,
  `fit_plive`, `predict_plive` (logistic P_live on score_diff/sec_remaining/
  foul_diff/bonus/time_pressure).
- `domains/basketball_nba/ingame_blend_prior.py` -- `derive_p0()` from the
  black-box pregame MC sim margin distribution.
- `domains/basketball_nba/ingame_blend_surface.py` -- 2D weight surface +
  `garbage_clamp()` (late-blowout hard clamp).
- `domains/basketball_nba/ingame_blend_eval.py` -- leak-free A->B / B->A harness;
  DM test clustered by game_id; `REAL_OOS_VALIDATION_PENDING = True` (SYNTHETIC).
- `scripts/platformkit/proof_nba/ingame_accuracy.py` (+ `proof_mlb`,
  `proof_soccer/ingame_ht_accuracy.py`, `proof_tennis`) -- per-sport leak-free
  in-game accuracy proofs scoring Brier(conditional) vs Brier(pregame) on the
  real linescore corpus.

### Legacy NBA player-prop in-game stack (production-wired, mostly OFF heads)

- `src/prediction/live_engine.py` -- consolidated entry point
  (`project_from_snapshot`, `project_full_slate`, `edge_vs_pregame`,
  `write_ledger`); wraps `scripts/predict_in_game.project_snapshot` plus ~20
  override heads.
- `scripts/predict_in_game.py` -- the validated cycle-88b core (pace
  extrapolation + foul/blowout/bench factors).
- `src/prediction/inplay_winprob.py` -- LightGBM in-play home win-prob boosters
  (`data/models/inplay_winprob_endq{1,2,3}*.lgb`, with v6_hp / v7_bag5 / isotonic
  / dual-cal variants on disk).
- `src/prediction/win_probability.py` -- the XGBoost win-prob model (pregame +
  the model the in-play stack is benchmarked against).
- `src/prediction/minute_trajectory.py`, `minute_trajectory_foul_residual.py`,
  `blowout_residual.py`, `heat_check_shrinkage_residual.py`,
  `period_specific_heads.py`, `live_quantile_bands.py`, `live_factors.py` --
  the endQ1/Q2/Q3 head + residual + quantile-band artifacts.
- `src/ingame/` (24 modules) -- the newer consolidated SBS shadow stack:
  `unified_projector.py`, `routed_ensemble.py`, `score_ensemble.py`,
  `universal_winprob.py`, `live_state_hook.py`, `bayes_player_update.py`,
  `trust_curve.py`, `rest_of_game_sim` (in `src/sim`), enrichers, etc.
- `scripts/team_system/pbp_replay.py` -- replays played Finals games PBP through
  the projector, grading on RMSE+signed-bias (the keystone validator).

### Consumers / endpoints

- `api/courtvision_router.py`, `api/main.py`, `api/_cv_live.py`, `api/_cv_ws.py`
  -- FastAPI live page + websocket (legacy NBA stack).
- `scripts/platformkit/frontend/serve.py` + `snapshot_writer.py` -- platform
  board server consuming `live_board` / `live_read`.
- `scripts/platformkit/pm_trading/live_ingame.py`, `run_live.py`,
  `run_paper_today.py`, `paper_today_support.py` -- paper-trading live loop.
- `scripts/platformkit/grade_paper.py` -- grades paper picks (CLV-gated).
- `scripts/execute_loop/L16_live_trader.py` -- live trader executor.
- `scripts/platformkit/system_map.py` -- exercises `live_read` per sport.

---

## 2. HOW IT WORKS -- data flow + key algorithms

### Sport-agnostic container + factory

`live_repricer.py:29` defines `GameState(sport, elapsed_minutes, home_score,
away_score, pregame_params: dict, extra: dict)`. A `Repricer` Protocol
(`:63`) requires `reprice(state) -> Dict`. `get_repricer(sport)` (`:236`)
dispatches: `soccer -> SoccerRepricer`, `mlb -> MLBRepricer`,
`nba -> NBARepricer`, `tennis -> TennisRepricer`, else a graceful
`_SportStub` returning `{"status": "not_wired", ...}` (never crashes).

The common pattern across the discrete-score sports (soccer, MLB): scale the
pregame scoring-rate lambdas by the REMAINING fraction of the match, build a
remaining-score probability MATRIX, then SHIFT it by the score already on the
board to get the final-score distribution, and read all markets off that.

### Per-sport reprice algorithms

- **Soccer** (`live_repricer.py:88` `SoccerRepricer.reprice`):
  `remaining = max(0, 90 - elapsed)`, `frac = remaining/90`,
  `lam_rem = lam_pregame * frac` (homogeneous Poisson over 90 min).
  `P_rem = scoreline_matrix(lam_rem_h, lam_rem_a, rho)`, then
  `P_final[h0+dh, a0+da] += P_rem[dh, da]`, normalize, emit 1X2 / O-U / BTTS /
  correct-score live via `markets_from_matrix`. At FT it emits a deterministic
  `_final_state_surface`.

- **MLB** (`mlb/repricer.py:79` `MLBRepricer.reprice`):
  `_remaining_frac(innings_played)` uses an EMPIRICAL per-inning run-share curve
  `_INNING_SHARES = (0.122, 0.101, ... , 0.096)` (`:36`) linearly interpolated at
  fractional innings, NOT a flat 1/9. `P_rem = runs_matrix_nb(lam*frac, ..., r)`
  (over-dispersed NegBinom), shift by `(h0, a0)`, emit ML / run-line / totals. A
  regulation TIE is kept live with one extra-inning residual lambda
  (`_EXTRA_INNING_FRAC = 1/9`) so the over is not frozen. HONEST caveat in code
  (`:80`): the NegBinom thinning reuses the full-game dispersion `r`, so the
  remaining-runs tail is slightly mis-specified (a modeling approximation, not a
  leak). The run-curve is GLOBAL + IN-SAMPLE to the backtest corpus; the
  leak-free OOS verdict lives in `proof_mlb/curve_oos.py`, not in the engine.

- **NBA** (`basketball_nba/repricer.py:43` `NBARepricer.reprice`): NBA is
  high-scoring/continuous so a discrete matrix is the wrong shape. Uses the
  validated score-anchor KEYSTONE -- the realized score is an ever-tightening
  anchor (pooled team-score RMSE shrinks Q1~12.5 -> Q4~4.2) -- as a Gaussian
  remaining-points model:
  `margin_mean = (h0-a0) + (mu_home-mu_away)*rem_frac`,
  `margin_sd = margin_sigma * sqrt(rem_frac)` (Brownian; collapses to the
  realized score as the clock runs). `win_home = Phi(margin_mean/margin_sd)`,
  plus spread-cover and totals surfaces. `_norm_cdf` is erf-based (no scipy).

- **Tennis** (`tennis/repricer.py:44`): conditions on the completed-set score and
  computes the analytic race-to-N-sets conditional `_race_win_prob(p, need_1,
  need_2)` (`:31`) -- deliberately NOT a re-sim, to dodge the MAE-vs-RMSE
  median-shift artifact (a probability is Brier-graded). A small bounded lean
  (`_GAMES_LEAN = 0.04`) nudges `p` from a lopsided in-progress set.

### The calibrated `predict_live` wrappers (the W146/W156/W157 cohesion fix)

`live_read.build_live_read` and `live_board` do NOT call the raw repricer
directly -- they call each sport's `predictor.predict_live`, which (1) ANCHORS
the repricer's pregame win-prob to the same Elo/MOV win-prob `predict()` reports
(so pregame and in-game agree at elapsed=0), and (2) applies the validated
recalibrator. NBA (`predictor.py:227`):
`mu_diff = ndtri(p_home_win) * margin_sigma` -> `mu_home/mu_away`, reprice, then a
temperature recal (`live_temp`, ECE 0.059 -> 0.012) SKIPPED on a determined game
(raw prob 0/1 or no time left). MLB (`predictor.py:243`): NegBinom tie-split
anchor `_anchor_nb_tiesplit(...)` to the Elo target, fitted `r_home/r_away`, then
the W156 recal (a NULL/identity -- the forecaster was already calibrated).

### Eval-gate blend core (the blueprint N3 lever)

`eval_gate/ingame_blend.py`: `final = w(time,margin)*P_live + (1-w)*P0`. `P0`
is the black-box pregame MC sim prior (`ingame_blend_prior.derive_p0`), `P_live`
is the logistic on realized state (`ingame_blend_plive`). `fit_weight_surface`
minimizes per-cell Brier on a coarse (4 time x 5 margin) grid with a `min_cell`
floor; sparse cells fall back to `default=0.0` (trust pregame). The
`garbage_clamp` (`ingame_blend_surface.py:52`) hard-clamps the late blowout that
a linear blend cannot express. `ingame_blend_eval.evaluate` fits on season A,
evaluates on B (and B->A), reports per-quarter Brier/ECE, the in-sample-vs-OOS
overfit gap, and a game-id-clustered Diebold-Mariano.

### Legacy NBA live_engine -- the override cascade

`live_engine.project_from_snapshot(snap)` (`live_engine.py:704`) calls
`predict_in_game.project_snapshot` (cycle-88b: pace extrapolation + foul-trouble
+ blowout + bench), then layers, in order, ~20 transforms each gated either by a
module flag or an env var, almost all default-OFF or boundary-gated:
SBS routed overlay (`CV_INGAME_SBS`), period-specific heads (endQ1/endQ2),
endQ2 residual heads, PTS minute-calib (`CV_PTS_MIN_CALIB`), generalized
heat-check, learned-Q4-minutes (endQ3), stratified foul/blowout/heat-check
residuals, endQ3 residual heads, bonus-FT bump, on/off + matchup tilts, quantile
bands, in-play win-prob stamping, Q4 sim-WP promotion, STAT CAPS + floor-at-
current guards, defender-matchup, vac-ast, and the consolidated `CV_INGAME_STATE`
Bayesian update. A critical correctness note in-code (`:819`): the endQ3 heads
were once firing on EVERY period-4 snapshot (all of mid-Q4 AND the 0:00 buzzer),
not just the endQ3 BOUNDARY they were trained against; this was gated to
`snapshot_point_for(period, clock) == "endQ3"`.

### The newer `src/ingame/` consolidation (SBS shadow)

`unified_projector.project_unified` assembles the ROUTED player-line ensemble
(`routed_ensemble`) + the possession-sim score ensemble (`score_ensemble` ->
`rest_of_game_sim`). Default-OFF behind `CV_INGAME_SBS`; flag OFF is a
byte-identical pass-through to `project_snapshot`. `universal_winprob.py`
computes win% from the PROJECTED-FINAL margin + `sigma_full*sqrt(rem_frac)`
(never the raw live margin -- that is the shrink artifact), gated to Q4+ and
sim-coverable matchups. `trust_curve.py` / `bayes_player_update.py` /
`live_state_hook.py` are the consolidated parametric posterior whose DEFAULT
trust curve is IDENTITY (trust_w=0 -> posterior==prior -> no-op).

---

## 3. HOW IT IS USED

- **FastAPI live page** (`api/courtvision_router.py`, `api/_cv_live.py`,
  `api/_cv_ws.py`, `api/templates/tonight.html`): the legacy NBA stack; polls box
  snapshots (`scripts/box_snapshot_poller.py`) and serves
  `live_engine.project_from_snapshot` per-(player,stat) projections + in-play
  win-prob + quantile bands.
- **Platform board** (`scripts/platformkit/frontend/serve.py`,
  `snapshot_writer.py`): consumes `live_board.todays_live_games(sport)` which
  feeds ESPN live state through `predict_matchup.build_result` -> `predict_live`.
  This is how live state reaches the React/board UI for ALL sports.
- **Cohesive in-game read** (`scripts/platformkit/live_read.py`): used by
  `system_map.py` (per-sport in-game section) and the CLI; fuses the calibrated
  surface with brain concepts.
- **Paper-trading loop** (`scripts/platformkit/pm_trading/live_ingame.py`,
  `run_live.py`, `run_paper_today.py`) + `scripts/execute_loop/L16_live_trader.py`
  -- the live arm of the self-improving paper loop; picks graded by
  `grade_paper.py` (CLV-gated, real-money never auto-placed).
- **Validation harnesses**: `proof_nba/ingame_accuracy.py` (+ mlb/soccer/tennis)
  and `pbp_replay.py` consume the repricer / projector to grade leak-free.
- **Calibration / backtest scripts**: `scripts/ingame/repricer_calibration.py`,
  `scripts/calibrate_live_quantiles_v2.py`, `scripts/backtest_inplay_*`.

---

## 4. STRENGTHS -- what is genuinely solid

1. **The core claim is real and principled.** Conditioning on the realized score
   is genuinely new information, and the score-anchor + Brownian-variance-collapse
   construction (NBA repricer; `universal_winprob`) is mathematically clean: the
   forecast provably tightens onto the realized outcome as the clock runs. This is
   the cleanest, most defensible "improvement" in the whole project, precisely
   because it is a calibration win and not a market-beating claim.

2. **Honest framing is wired into the code, not just the docs.** Every repricer
   and predict_live carries an `EDGE_CLAIMED = False` / `_honest_note` stating "a
   live book also sees the score; forecaster quality, not a price edge." The
   retracted-number discipline is respected throughout.

3. **The platform stack is clean and uniform.** One `GameState`, one `Repricer`
   Protocol, one factory; per-sport engines are <=300 LOC, pure math (erf-based
   normal CDF, no scipy), duck-typed so they work without importing GameState.
   Unwired sports degrade to a graceful stub. `live_board` never fabricates a
   score or prediction -- feed-down -> `status="unavailable"`, unresolved team ->
   skipped with a logged note.

4. **Sharpness is measured leak-free where data exists.** The per-sport
   `ingame_accuracy` proofs reconstruct mid-game states from the real linescore
   corpus (NBA: 1313 games x per-quarter splits) and score Brier(conditional) vs
   Brier(pregame) + ECE + reliability slope, with the recalibrator fit on TRAIN
   only and applied to held-out. RMSE+signed-bias, NEVER MAE, per the keystone.

5. **The MAE-vs-RMSE artifact is internalized.** Tennis uses an analytic
   probability (not a re-sim), `universal_winprob` uses projected-final not raw
   live margin, `pbp_replay` grades RMSE+bias -- all explicitly to avoid the
   "shrink-toward-current wins MAE as a median trick" trap that fooled earlier
   cycles.

6. **Coherence fix (W146/W156/W157).** `predict_live` anchors the repricer to the
   same pregame Elo win-prob `predict()` reports, so pregame and in-game numbers
   agree at tip-off and the live number does not drift toward a possessions
   margin. Calibrators are fit on all-prior history.

7. **Default-OFF safety on the legacy stack.** The ~20 live_engine heads and the
   entire `src/ingame/` SBS surface are gated; flag-OFF is byte-identical to the
   cycle-88 core, and every override is wrapped so a failure falls back to the
   production rows ("never break the hot path"). The trust curve defaults to
   identity.

---

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS (brutally honest)

1. **The NBA blend's real-corpus OOS validation is PENDING.** The flagship
   blueprint lever (`ingame_blend_eval.py`) ships with
   `REAL_OOS_VALIDATION_PENDING = True` and `corpus = SYNTHETIC`. The A->B / B->A
   numbers are from a synthetic two-season generator whose latent strength drives
   BOTH P0 and the realized state -- i.e. it is CONSTRUCTED so P_live can add
   information. That proves the wiring/pattern, NOT a real-data calibration gain.
   The honest in-game blend BSS on REAL NBA data is unproven here.

2. **PBP replay validation was largely negative / thin.** Per the project memory
   (`project_pbp_replay_validation_2026-06-10`): replaying Finals G1-G3 PBP, only
   the baseline + foul-out modifier validated; the pooled win-prob came out WORSE
   than a coin flip. The replay corpus is 3 games (`finals_replay_eval.parquet`,
   ~21KB) with a documented rate-anchor leak on G1/G2 (pregame rates fit through
   G2; only G3 is fully leak-free). N=3 is far too thin to promote anything, and
   the headline per-player wins are single-corpus.

3. **Two divergent in-game stacks.** The legacy `live_engine` (2719 lines, ~20
   stacked heads) and the platform repricer stack are separate codebases with
   different math, different validation, and different consumers (FastAPI vs
   board). This is maintenance debt and a parity risk: the player-prop projector
   feeding the live page is NOT the same engine as the calibrated team-level
   repricer the board uses.

4. **Heavy stranded / parallel artifact sprawl.** `data/models/` holds dozens of
   in-game artifact families (`residual_heads`, `_big`, `_blow`, `_close`,
   `_endq1/2`, `_pos_*`, `_seeds`, `_stage2`, `_v2..v7`, `_xgb`, multiple
   `inplay_winprob` v4/v6_hp/v7_bag5/isotonic/dual-cal). Most are research
   variants; only a handful are wired. `data/models/ingame/trust_curve.json` does
   NOT exist (only `sbs_v2/`), so the consolidated Bayesian update is a permanent
   identity no-op until that gated artifact is fit -- it is DATA-BLOCKED
   (fit corpus 2022-23 PBP vs live 2025-26, RED-A A4 / RED-B B10).

5. **The legacy heads are single-corpus, in-sample-risk, boundary-fragile.** The
   cycle-88..R10 SHIP verdicts (PTS MAE -0.23, etc.) are on a single ~1508-game
   backtest with WF 4/4 folds, but they are NOT cross-corpus and many were trained
   against the very heuristic factor they then replace. The endQ3-boundary bug
   (heads firing across all of Q4) is the kind of train/serve-window mismatch the
   project's own memory repeatedly flags as the most expensive bug class.

6. **`SBS` / `unified_projector` is built-but-OFF in production.** Its routed
   player-line MAE (1.01 vs 1.87) and score-ensemble totals (MAE ~10 vs ~21) look
   strong on the held-out grid (`.planning/ingame/eval_routed.json`), but it is
   default-OFF, so production still serves the older cycle-88 projector. The
   measured win is not the served value. And on pooled win-prob BRIER the sim is
   0.1772 vs production 0.1706 (a loss until late Q4) -- honestly reported, but it
   means the "sharper" claim is stat- and game-time-specific, not blanket.

7. **MLB run-curve + NegBinom thinning are acknowledged approximations.** The
   per-inning curve is in-sample to the backtest corpus; thinned NegBinom does not
   stay NegBinom with the same `r`. Both are flagged in-code as modeling
   assumptions, but they cap MLB in-game tail accuracy until the OOS curve proof
   and a proper inning-conditional dispersion land.

8. **soccer_intl (World Cup) has no `predict_live` re-pricing model** beyond the
   club soccer engine path; `live_board` emits an explicit `ingame_note` that only
   pregame is predicted for such predictors. Tennis in-game is set-level only (no
   game/point-level engine).

9. **Live data plumbing is the practical ceiling, not the math.** The board reads
   ESPN's keyless scoreboard (period/clock/score only); the legacy stack needs box
   snapshots. There is no injury/lineup/possession feed, so the in-game model sees
   strictly less than a live book (which prices substitutions and pace shifts in
   real time). This is the structural reason the edge is calibration, not profit.

---

## 6. PLAN TO GET BETTER (prioritized)

**Quick wins (days):**

1. **Run the real-corpus NBA in-game blend OOS, end the PENDING flag.** Wire
   `ingame_blend_eval` to the real linescore corpus (1313 games) instead of the
   synthetic generator: fit weight surface on season A, evaluate on B (and B->A),
   report per-quarter Brier/ECE + clustered DM vs pregame-only. Record the honest
   verdict (even BSS<=0 / market-efficient is a SUCCESS). This converts the
   flagship lever from "pattern proven" to "real-data measured."
2. **Publish a single in-game calibration scoreboard.** Run `proof_nba`,
   `proof_mlb`, `proof_soccer`, `proof_tennis` `ingame_accuracy` and pin the
   Brier(conditional)-vs-Brier(pregame) + ECE table per game-time into the
   evidence packet. One table, all four sports, leak-free, no $.
3. **Prune the stranded artifact families.** Catalog which of the ~20
   `residual_heads*` / `inplay_winprob*` variants are actually loaded by the
   serving path; archive the rest under a clearly-labeled experiments dir. This
   removes the biggest source of "what is real?" confusion.

**Medium (weeks):**

4. **Reconcile the two stacks behind one interface.** Make the legacy player-prop
   projector consume the platform `predict_live` team surface for win-prob /
   totals so the live page and board agree, and so there is ONE calibrated
   team-level number. Keep the prop heads, but stop them re-deriving win-prob.
5. **Fit the gated `trust_curve.json` on a same-era held-out fold.** Unblock the
   consolidated Bayesian update by sourcing 2025-26-era PBP for the fit corpus, so
   `CV_INGAME_STATE` can move off identity with a real RMSE+bias-gated trust curve.
6. **Promote SBS where it is measured-best, gated per game-time.** Flip
   `CV_INGAME_SBS` ON only for the (stat, game-time) cells where the routed/score
   ensemble strictly beats production on RMSE+bias AND Brier, fail-closed
   elsewhere -- exactly what `universal_eligible` already encodes for win-prob.

**Bigger bets (months):**

7. **Build a real possession/event live feed for NBA.** The math ceiling is
   data-bound; ingesting live PBP (substitutions, pace, foul state) instead of box
   snapshots is the single largest lever on in-game sharpness.
8. **In-game props as a first-class repricer output.** Extend the per-sport
   repricers to emit calibrated player-prop distributions conditioned on realized
   minutes/usage (see ceiling note below), validated leak-free on the linescore +
   box corpus, RMSE+bias only.
9. **Expand the leak-free corpus.** N=3 Finals replay is the binding constraint on
   PBP-level validation; ingest multi-season PBP so per-player in-game modifiers
   can be tested cross-corpus before any promotion.

---

## 7. HOW GOOD CAN IT GET (honest ceiling)

**Realistic best (team-level win-prob / totals):** a well-calibrated in-game
forecaster whose Brier strictly improves over the pregame prior at every
game-time, with ECE ~0.01-0.02, converging to a near-deterministic step late.
This is achievable and partly already demonstrated (the score-anchor RMSE shrinks
from ~12.5 in Q1 to ~4.2 in Q4; NBA combined Brier ~0.159 vs ~0.209 pregame on
the cited corpus). The honest framing holds firmly: this is forecaster QUALITY.

**Ceiling on a DOLLAR edge: essentially zero, structurally.** A live book prices
the same realized score in real time AND sees substitutions, pace, and injury
news we do not. The only place a live mispricing could persist is latency or
illiquid in-play markets -- not a model edge. The project is right to gate the $
question separately and claim nothing. The PBP-replay finding (pooled win-prob
worse than a coin flip on N=3) is a sober reminder that even the calibration win
is fragile on thin data.

**Ceiling for in-game PROPS:** higher upside than team markets, because realized
minutes and usage massively reduce per-player variance, and in-play prop markets
are thinner/slower than the moneyline. The routed-ensemble player MAE (1.01 vs
1.87 production) suggests real sharpness is attainable. BUT: (a) it must be proven
cross-corpus, not on a single backtest; (b) the same "book sees the score"
caveat applies; (c) the binding constraint is again DATA -- a live minutes/usage
feed and a multi-season leak-free corpus. With those, calibrated in-game prop
DISTRIBUTIONS (not point picks) are the most credible frontier -- as a
calibration product, never as a claimed profit edge.

**What limits it, in one line:** the math is solved and clean; the ceiling is set
by (1) live data depth (box snapshots vs true PBP/lineups), (2) leak-free corpus
size (N=3 PBP replay is the bottleneck), and (3) the hard fact that the live
market already conditions on everything we condition on, plus more.
