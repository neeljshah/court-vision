# 08 - NBA Monte Carlo Possession Sim + Role-Aware Ratings

Area owner: `src/sim/basketball_sim.py`, `src/sim/fast_sim.py`, `scripts/team_system/build_*`,
`data/cache/team_system/`.

Scope: the player-level possession Monte Carlo that turns per-player rates + role-aware ratings
into a coherent joint distribution over every box-score stat, and the 2K-style ratings / recency /
PBP-knowledge layers that parameterize it. This is the engine behind the (deferred) MC-sim prop
ladder + SGP vertical.

Honesty rails up front: markets are efficient. The honest, defensible win here is CALIBRATION and
COHERENCE (the joint structure), not a dollar edge. No ROI is claimed. The rate inputs are
full-season in-sample, so accuracy backtests are mild-leak; treat them as fidelity checks, not OOS
edge. Everything below is paper-only.

---

## 1. INVENTORY (exists + used)

### Engine (`src/sim/`)
- `basketball_sim.py` (39.6 KB) -- the reference (CPU) possession engine. `TeamModel.from_cache` +
  `simulate_game` + shared `_finalize`/`_apply_dispersion`/`apply_context`/`_matchup_mult`. The
  authoritative spec; every mechanic is documented in-file.
- `fast_sim.py` (12.4 KB) -- GPU/torch-vectorized clone of the IDENTICAL possession chain;
  `simulate_game_fast`. Runs all N sims in parallel, shares `basketball_sim._finalize` so output is
  structurally identical. Measured ~0.46 ms/sim on CUDA (RTX, 20k sims in 9.2 s); ~3.4 s for a
  ~7500-sim board run, matching the brief's cost figure. This is the engine production actually calls.
- `sgp_from_sim.py` (9.8 KB) -- same-game-parlay joint pricer. `Leg`, `joint_prob`, `leg_prob`,
  `describe`, `validate_joint_calibration`. Reads joint hit-prob directly off the coherent samples and
  reports correlation lift vs the independence product.
- `game_clock_sim.py` (16.9 KB) -- TIME-RESOLVED sibling that reuses `TeamModel` + chain primitives to
  play the game in clock order (quarter scores, live win-prob curve, foul-out, fatigue). Marginal-engine
  consistent; trajectory is the point.
- `clutch_adjust.py` -- thin wrapper that runs `simulate_game_fast` then applies a clutch tilt.

### Builders (`scripts/team_system/`) -- the parameter pipeline feeding `TeamModel`
- `build_player_rates.py` -> `player_rates.parquet` (507 rows x 28 cols) + `team_rates.json` (all 30
  teams). Per-player season rates (use_per_min, shot/tov/ft_share, zone shares z_rim/paint/mid/3, zone
  FG%, per-min reb/ast/stl/blk/pf, pts_pg, ft_pts_share) and per-team pace / ast_rate_on_make /
  oreb_per_miss / ortg / def_rtg + the empirical 5-man lineup minute distribution.
- `build_player_ratings.py` -> `player_ratings.parquet` (927 x 20). The 2K-style role-aware ratings:
  87 attributes -> 13 category ratings -> impact-weighted OVERALL + INTERIOR_D / PERIMETER_D used by
  the sim's defense.
- `build_recency_rates.py` -> `recency_rates.parquet` (39 rows -- NYK/SAS only). Exponentially
  recency-weighted pts/reb/ast/mpg (half-life ~10 games) for the regime/form blend.
- `build_pbp_knowledge.py` -> `pbp_player_knowledge.parquet` (30 rows, NYK/SAS) + `assist_network.parquet`
  (428 passer->scorer pairs). Real unassisted-make share + the real assist network mined from PBP.
- `build_player_roles.py` -> `player_roles.parquet` (507 x 17). Archetype + creation/self_create/playmaking
  propensities (usage + assist routing).
- `build_player_attributes.py` / `build_attribute_vault.py` -> `player_attributes.parquet` (850),
  `attribute_vault.parquet` (927 x 90). Physical attrs + the 87-attribute vault that ratings consume.
- `build_team_defense.py` -> `team_defense.parquet` (2 rows -- NYK/SAS). tov_force / ft_force /
  oreb_strength defensive environment multipliers.
- secondary targets + defender suppression: `secondary_targets.parquet` (304) feeds the count-stat
  recalibration; `defender_suppression.parquet` (515) feeds the gated CV_AGENT_DEF_SUPP lever.

### Validation / consumers
- `validate_sim_fidelity.py`, `validate_fast_sim.py` -- fidelity + GPU-equivalence harnesses.
- `backtest_sim_accuracy.py` -- player-pts + team-total MAE/bias with the raw<->anchor blend sweep.
- `sgp_edge_scanner.py` -- thin read-only wrapper over `sgp_from_sim.joint_prob`.
- `market_catalog.py`, `sim_derivative_markets.py`, `market_intelligence.py`,
  `scripts/courtvision/build_cv_board.py` -- price the full market menu from one sim result.
- tests: `tests/test_sim_engine.py`, `test_sim_core_robustness.py`, `test_sim_invariants_engines_audit.py`,
  `test_possession_sim.py`, `test_sgp_joint_backtest.py`, `test_sgp_cross_team_sweep.py`.

NOTE on naming collision: `src/prediction/possession_simulator.py` + `prop_pricing_engine.py` are a
SEPARATE, OLDER 7-sub-model sim (PlayTypeSelector -> ... -> SubstitutionModel). It is NOT the
basketball_sim engine documented here and is largely superseded by it.

---

## 2. HOW IT WORKS

### 2.1 TeamModel.from_cache (basketball_sim.py:94-176)
`TeamModel.from_cache(tri, rates_df=None, team_rates=None, out_ids=None) -> TeamModel`

- Filters `player_rates` to `team == tri & mpg >= MIN_MPG (6.0) & pid not in out_ids` -> per-pid rate dict.
- Layers on, by lazy-loaded singletons: physical attributes (`_attributes`), role propensities
  (`_roles`: creation/self_create/playmaking), defensive ratings (`_ratings`: int_d/perim_d/overall),
  recency rates (`_recency`), and PBP ground truth (`_pbp_knowledge`: real self_create + assist network).
- Keeps only lineups whose 5 are all eligible; sampling prob = minutes share (`lineup_p`). Fallback =
  top-5 by usage as one lineup.
- Team defensive aggregates: `rim_d = 0.5*minute-weighted-mean-int_d + 0.5*max(int_d among >=15 mpg)`
  (rim identity = best protector + depth); `perim_d = minute-weighted-mean perim_d`. Pulls tov_force /
  ft_force from `team_defense`.
- `out_ids` is the FRESHNESS lever: drop same-day-unavailable players so minutes/usage re-route. Default
  None -> byte-identical.
- Two optional gated layers, both default-OFF and byte-identical when off: CV_AGENT_DEF_SUPP (attach
  per-defender supp) and CV_LLM_SCHEME (apply bounded scout knob nudges).

### 2.2 The possession chain (`_possession`, basketball_sim.py:203-285; GPU twin fast_sim.py:94-166)
Shared scoring pie: each possession is used by exactly ONE of the 5 on-court players, sampled by
`use_per_min ** USAGE_CONCENTRATION (1.25)`. This is the fix for the old game_simulator teammate-rho bug:
the correct slightly-negative teammate correlation EMERGES (validated ~ -0.10) instead of being imposed.
Per possession (with a 4-iteration OREB continuation guard):
1. turnover at `tov_share * deff.tov_force` (+ steal at P_STEAL_ON_TOV 0.55).
2. drawn-foul FT trip at `ft_share * off.mult[ft] * deff.ft_force` (2 FTs at ft_pct).
3. else a shot: sample zone from z-shares; make prob = `_make_prob(r, zone) * base_x`.
   - `base_x` starts from per-player context xfg (home/road, B2B) then is suppressed by DEFENSE:
     rim shots face `max(int_d)` on the floor (`DEF_RIM_SLOPE 0.0024`, clip 0.78-1.12); perimeter shots
     face mean perim_d (`DEF_PERIM_SLOPE 0.0013`, clip 0.88-1.08). Optional def_supp lever folds mean
     opponent-PPP suppression in (clip 0.85-1.10).
   - on a make: assist drawn at `ast_rate_on_make * clip(1.9*(1-self_create), 0.5, 1.7)`; assister = 70%
     real PBP feeder network + 30% ast-rate floor.
   - on a miss: block (taller protector blocks more at rim, cap 0.22) -> OREB (continue) or DREB (end).

### 2.3 Finalize: anchor + matchup + dispersion + count recal (`_finalize`, basketball_sim.py:582-683)
Raw chain output is minutes-consistent but under-disperses individuals and under/over-counts totals, so
`_finalize` re-shapes the per-sim samples while preserving the joint rank structure:
- ANCHOR (line 585+): per-player pts target = recency-blended season pts (`RECENCY_W 0.6`) x context xfg x
  `_matchup_mult` (opponent rim/perim/FT defense, weighted by the player's shot profile, clip 0.85-1.12).
  Top-8 "core" pinned to their target; bench absorbs `max(raw_tot, core_sum*1.02) - core_sum`. reb/ast
  also recency-blended; secondary counts (stl/blk/pf/tov/fg3m/ftm) anchored to per-min*mpg.
  `_anchor` rescales samples to hit the mean with clip [0.4, 2.5] (keeps shape + correlation).
- DISPERSION (`_apply_dispersion`, line 327): adds a per-player right-skewed lognormal shock
  (`DISP_BASE 0.20`, `DISP_MINUTE 0.60` for low-minute uncertainty), HOLDS the team total per sim, then
  re-pins each marginal mean -> fixes the under-dispersed individual pts (cov q10-q90 66% vs 80% target)
  without breaking the well-calibrated team total.
- COUNT-STAT RECAL (line 633+): low-frequency counts (blk/fg3m/ftm, +stl under CV_COUNT_STL) are
  re-sampled at the real per-game mean from `secondary_targets` because the chain produces zero-clumped
  counts (sim P(Wemby>=1 blk) 60% vs 95% real). Default Poisson; CV_COUNT_NB upgrades genuinely
  over-dispersed counts (var > 1.5*mean) to a Negative Binomial at the real (mean, var).

### 2.4 Output (GameSimResult, basketball_sim.py:305) -- the full joint sample
`players[pid] = {name, team, mean:{14 stats}, reb_mean, q10/q50/q90 pts, samples:{pts,fga,fgm,fg3a,fg3m,
fta,ftm,oreb,dreb,ast,stl,blk,tov,pf,reb}}` plus `home_total`, `away_total` (per-sim arrays),
`home_win_prob`. Verified live: every player carries 15 per-sim sample arrays. Because every prop is read
off the SAME N simulated games, any single prop, combo, threshold, milestone ladder, DD/TD, alt-line, or
SGP is derivable coherently from one run.

### 2.5 Role-aware 2K ratings (build_player_ratings.py)
`_cat` aggregates 87 vault attributes into 13 categories (CAT, line 28). Skill INTERACTIONS modulate
them (size x rim-protection line 103; efficiency x volume 106; usage x efficiency 108; shooting gravity
amplifies finishing/creation 110). Role weights (ROLE_W, 15 archetypes) define WHICH skills make a
player good, with a 22% uniform floor penalizing one-dimensionality. Convex two-way + unicorn-height
premiums + impact (offensive load) + minutes-trust multipliers, then a FIXED corpus-independent
raw->OVERALL curve (CURVE_X/Y) calibrated to anchors (Wemby 99, SGA/Kawhi 98, Brunson 92 >> Fox 86).
Only INTERIOR_D / PERIMETER_D / OVERALL flow into the sim; the rest is scouting display.

### 2.6 Recency + PBP knowledge
- Recency (build_recency_rates.py): exponentially weighted (0.5^(age/half_life), HL=10) pts/reb/ast/mpg;
  walk-forward-validated to cut the +0.98/player playoff over-prediction to +0.11 and lower playoff MAE
  4.18->4.05. Blended at RECENCY_W 0.6 in the anchor.
- PBP knowledge (build_pbp_knowledge.py): real unassisted-make share (overrides the role estimate) +
  the directed assist network (assister->scorer counts), both fed straight into the chain's assist logic.

---

## 3. HOW IT IS USED

- Board / market pricing: `scripts/courtvision/build_cv_board.py` calls `TeamModel.from_cache` +
  `simulate_game_fast(n_sims=20000, anchor=True, defense=True)`, applies the CV_MIN_VAR joint corrector,
  then prices DD/TD/blocks/longshots/tiers into `market_board_*.json` for the live CourtVision board.
- Full market menu: `market_catalog.py` / `market_intelligence.py` / `sim_derivative_markets.py` price
  singles, combos, alt-lines, exotics, team totals, spreads, moneylines, game totals -- all from one sim
  result's samples.
- SGP: `sgp_from_sim.joint_prob` is the joint pricer; `sgp_edge_scanner.py` is a read-only wrapper; tests
  `test_sgp_joint_backtest.py` / `test_sgp_cross_team_sweep.py` grade it.
- In-game: `domains/basketball_nba/ingame_blend_prior.py` consumes the sim-shaped output;
  `game_clock_sim.py` reuses TeamModel + primitives for the trajectory/win-prob surface;
  `clutch_adjust.py` post-processes a fast_sim run.
- Validation loop: `validate_fast_sim.py` (fidelity + defense + GPU==CPU equivalence),
  `validate_sim_fidelity.py`, `backtest_sim_accuracy.py` (anchor sweep).
- API: `api/main.py` exposes a `simulate_game` endpoint, but it dispatches to `_simulator` (the loop
  AsOfContext simulator), NOT directly to basketball_sim -- so the FastAPI surface and the board builder
  reach the engine through different paths.

---

## 4. STRENGTHS

- Coherent joint distribution from first principles. The shared-pie design makes teammate correlation
  EMERGE (~ -0.10, matching real) rather than being imposed by a fragile rho-matrix. This is the single
  most defensible property and is exactly what an SGP/derivative menu needs.
- One run prices the entire market surface. 15 per-sim arrays per player => every prop/combo/threshold/
  milestone/alt-line/DD/TD/SGP is read off the same simulated games, so they are internally consistent.
- Real-data parameterization, not hand-tuned: rates from boxscores, zones + assist network + self-create
  from PBP ground truth, defense from the attribute-vault ratings. PBP overrides estimates where available.
- GPU twin is fast and faithful: ~0.46 ms/sim measured; `validate_fast_sim` asserts per-player pts MAE
  (ref vs fast) < 0.6 -- the two engines are statistically equivalent, so calibration sweeps are interactive.
- Careful, documented calibration discipline: dispersion holds the team total then re-pins marginals;
  count stats re-sampled to fix zero-clumping; gated levers (def_supp, scheme, freshness, NB counts) are
  default-OFF and byte-identical when off, preserving test/oracle reproducibility.
- Honest, in-file accounting of failed fixes (the anchor docstring at line 596 records two reverted
  total-bias fixes) -- low risk of silently re-introducing them.

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS

- Rates are FULL-SEASON / in-sample. Every accuracy backtest (`backtest_sim_accuracy.py`,
  `validate_sim_fidelity.py`, `sgp_from_sim.validate_joint_calibration`) is season-anchored, so the game
  being graded sits inside its own baseline -> a mild ~1/100-game mean leak. These are FIDELITY checks,
  not OOS edge. No leak-free walk-forward of the sim's prop predictions exists in this area; the season
  backtest elsewhere shows the team-strength layer does NOT beat the close (CLV ~0). Do not read any of
  these numbers as a dollar edge.
- Coverage is NYK/SAS-deep, league-shallow. `recency_rates` (39 rows) and `pbp_player_knowledge` /
  `assist_network` exist ONLY for NYK/SAS; `team_defense` has 2 rows. `player_rates`/`ratings` cover the
  league, but for any non-NYK/SAS matchup the recency blend, real assist network, and team tov/ft_force
  silently fall back to defaults -- the engine's deepest signal is effectively a two-team artifact.
- Documented residual team-total bias: the anchor over-predicts team totals ~+4.5 on a playoff-weighted
  eval (line 596). Shipped anchor is s=1.0 (stars exact); the backtest shows s=0.5 zeroes the bias but
  haircuts correctly-anchored stars. Guidance in-file: "trust spread not total."
- Slope/curve constants are calibrated on ONE in-sample season (NYK/SAS backtest): DEF_RIM_SLOPE,
  RIM_ANCHOR_SLOPE, DISP_BASE/MINUTE, the rating CURVE/ROLE_W/interaction coefficients. The defense
  slopes are deliberately conservative (~1.5x) to avoid overfitting, but they are not cross-season /
  multi-corpus validated; the rating curve anchors are hand-set to a handful of star names.
- Joint structure is validated; ROI is NOT. `sgp_from_sim` itself states ROI needs real SGP price capture
  (none in the repo). Same-player cross-stat joint is only PARTIALLY modeled (CV_MIN_VAR gap: realized
  pts-reb correlation runs +0.2..0.35 above the raw sim) -- hence the min_var corrector is bolted on at
  board time rather than emerging from the chain.
- Minutes are implicit, not simulated. There is no real minutes/foul-out model in basketball_sim (that
  lives in game_clock_sim); low-minute dispersion is a lognormal patch (DISP_MINUTE) rather than a
  modeled rotation. Injuries/availability only enter via the manual `out_ids` freshness lever.
- Two parallel sim stacks exist (basketball_sim/fast_sim vs the older possession_simulator +
  prop_pricing_engine). The API endpoint reaches yet a third (loop AsOfContext) simulator. Risk of
  confusion about which engine is authoritative; prop_pricing_engine appears stranded/superseded.
- 4-iteration OREB cap and several hard clips (anchor [0.4,2.5], defense clips) are pragmatic guardrails
  that bias tails; the engine cannot represent extreme blowout/garbage-time regimes structurally.

## 6. PLAN TO GET BETTER (prioritized)

Quick wins:
1. Extend recency + PBP knowledge + team_defense to all 30 teams (re-run the builders over the full
   game cache, not just `nyk_sas_games.json`). This is the single highest-leverage fix: it makes the
   deepest signals real for every matchup instead of NYK/SAS-only. Approach: generalize the game-list
   source in build_recency_rates / build_pbp_knowledge / build_team_defense.
2. Stand up a genuinely leak-free walk-forward of the sim's PROP predictions: build rates as-of each game
   date (exclude the game being graded), score pts/reb/ast/blk/3PM calibration (Brier/pinball/CRPS)
   against realized box scores. Until this exists, no prop-calibration claim is defensible. Reuse the
   eval-gate scoring already in the repo.
3. Cross-season / multi-corpus validation of the defense + dispersion + rating constants (>=2 seasons or
   >=2 team-sets). Promote a slope only if it improves on FIT and a holdout and is seed-stable -- exactly
   the gate `gate_def_supp.py` already encodes; reuse that pattern for the ungated constants.

Bigger bets:
4. Replace the bolt-on CV_MIN_VAR same-player corrector with a chain mechanism that produces the observed
   +0.2..0.35 pts-reb correlation natively (e.g. a per-game per-player form/usage common factor sampled
   once per sim), so the joint is right by construction and the SGP menu needs no post-hoc patch.
5. Model minutes/rotation + foul-out explicitly (fold the validated game_clock_sim minutes engine back
   into the marginal path), retiring the DISP_MINUTE lognormal patch and making availability a first-class
   input rather than a manual out_ids list.
6. Resolve the anchor total-bias honestly: either a calibrated raw<->anchor blend learned per-regime
   (regular vs playoff) walk-forward, or an ortg*pace total constraint that does not haircut stars --
   chosen by OOS team-total bias, not in-sample MAE.
7. Consolidate the sim stacks: make basketball_sim/fast_sim the single authoritative engine, route the API
   `simulate_game` endpoint through it, and deprecate the older possession_simulator/prop_pricing_engine
   path to remove the stranded code and naming confusion.

## 7. HOW GOOD CAN IT GET (honest ceiling)

Realistic best: a genuinely well-CALIBRATED, fully-COHERENT NBA box-score joint simulator that, for any
of the 30 teams, prices the entire prop + combo + SGP + derivative surface from one ~3-4 s GPU run and
matches the devigged market within noise on team totals / spreads while being demonstrably better-shaped
on the JOINT (correlation lift) than any independence-product or marginal model. That joint coherence is
the real, durable asset -- it is the thing a marginal prop model structurally cannot do, and it is the
honest basis for an SGP/derivative product.

What limits it:
- Market efficiency. Pregame prop and team-strength markets are efficient; the sim will match, not beat,
  the close on level. The honest edge is calibration + coherent joint pricing, plus whatever the manual
  freshness (out_ids) and in-game conditioning layers can see that the close cannot -- not a static
  pregame dollar edge.
- Data depth, not algorithm. The chain is already near the ceiling of what season boxscore + PBP rates
  can express (consistent with the broader project finding that PTS/REB are at the historical-data
  ceiling). Further gains come from same-day freshness (lineups/minutes/injuries) and in-game state, not
  from more chain mechanics.
- Validation honesty. The ceiling is only reachable IF the in-sample slopes/curves survive a real
  leak-free, multi-corpus, walk-forward gate. Single-fold/in-sample lifts here should be treated as
  artifacts until they clear that bar. The product framing remains: calibrated coherent predictor,
  paper-only, no profit-edge claim.
