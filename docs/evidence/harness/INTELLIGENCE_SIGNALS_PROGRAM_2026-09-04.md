# Intelligence -> Signals program: person / game / matchup grain (2026-09-04)

Scope: turn the intelligence pool into PREREGISTERABLE SIGNAL FAMILIES at player, game and matchup grain -- in-game
moments (close games, clutch, longshots/comebacks, foul trouble, lineup-on-floor, hot-scorer persistence, runs),
TAIL events (comeback probability in the 1-10 pct bins, blowout-margin tails, top-scorer upsets), pregame player and
matchup props, specific player-vs-defender matchups, and the WEIGHTING/COMBINATION of everything that screens.
Calibration language only (Q6): Brier, log-loss, ECE, CRPS, pinball, reliability bins. No dollar, ROI, profit or
edge word appears; no retracted figure is reprinted. An honest REJECT or NULL is the expected and valid result of
most rows below.

Ids: this memo allocates **S223..S232** only. S199-S212 are other lanes'; S213-S222 are the in-game DATA census /
latency / capture / engine-vs-price lane and are not duplicated. Numbers measured this session are marked **[m]**;
everything else is a cited read of a committed artifact. No file over 300 MB was opened.

---

## 1. The pool on disk

The decisive structural fact **[m]**: the pool splits into an AS-OF SAFE half and a SNAPSHOT-ONLY half, and every
family's feasibility turns on which half it draws from.

### 1a. AS-OF SAFE -- per-row `game_date` / `asof_date`, leak-safe by construction **[m]**

| store (under `data/intelligence/` unless noted) | rows | grain | date range | conditions |
|---|---|---|---|---|
| `momentum_signals.parquet` | **673,204** | player_id, asof_date, stat | 2022-10-27 .. 2026-05-24 | hot/cold: L3-vs-L20 momentum z + bucket. Largest clean as-of signal store on disk |
| `confidence_ensemble.parquet` | 307,643 | player_id, asof_date, stat | 2023-11-24 .. 2026-04-12 | per-signal confidence multipliers + coverage_class -- a ready-made WEIGHTING layer |
| `per_player_calibration.parquet` | 307,643 | player_id, asof_date, stat | 2023-11-24 .. 2026-04-12 | rolling bias + `sigma_resid` -- the tail WIDTH a CRPS score needs |
| `player_def_archetype_sidecar.parquet` | 99,498 | player_id, game_date | 2022-10-18 .. 2026-05-24 | player vs HELP_DEF / PACE_CONTROL / SWITCH_HEAVY diffs = "how players react to a scheme"; ships a null-control twin `_null.parquet` |
| `player_opp_splits_sidecar.parquet` | 99,498 | player_id, game_date | 2022-10-18 .. 2026-05-24 | player-vs-opponent career/L5 splits = person-to-team matchup |
| `per_archetype_residual_v1` / `atlas_features_sidecar` | 101,765 each | player_id, date | 2022-10-18 .. 2026-05-24 | archetype-scoped residual heads (pts/reb/ast); 6 atlas z-features + 2 interaction terms per player-game |
| `gt_weighted_forms` / `non_gt_forms_sidecar` | 99,157 each | player_id, game_date | 2022-10-18 .. 2026-05-24 | garbage-time-stripped and non-GT L5/L10/EWMA form |
| `cv_pace_features_sidecar.parquet` | 102,131 | player_id, game_date | 2022-10-18 .. 2026-05-24 | team/opp CV pace L5/L10 + matchup z |
| `schedule_strength_7d.parquet` | 99,498 | player_id, game_date | 2022-10-18 .. 2026-05-24 | rolling 7 d opponent-defense strength |
| `matchup_grid.parquet` | 4,900 | game_id, game_date, team_id, opp_team_id | 2024-10-22 .. 2026-04-12 | team offense-z vs defense-z per SCHEDULED game -- same window as the in-play checkpoints |
| `garbage_time_segments.parquet` | **1,226,606** | game_id, period, game_clock_sec, margin_abs | build 2026-05-29 | is_garbage_time at EVERY clock tick = blowout state at tick grain |
| `data/cache/inplay_foul_state.parquet` | 5,010 | game_id, period | -- | team foul totals: real foul-trouble state |
| `data/cache/ingame/possession_states_{2024_25,2025_26}` | 30,383 / 30,199 | game, seconds_remaining | 2 seasons | pace and `run_diff` = run / momentum state |

### 1b. SNAPSHOT-ONLY -- one `as_of`, or no date column at all

`data/cache/atlas_*.parquet`, 45 NBA stores (28 by `player_id`, 16 by `team_tricode`) plus a WNBA block, hold the
richest conditioning axes in the repo: `atlas_player_score_margin_splits` (540: leading/tied/trailing),
`_clutch_scoring` (439), `_form_streak_dynamics` (706), `_vs_scheme_splits` (701), `_matchup_splits` (106:
vs_notable_defenders, vs_specific_defenders_recent, vs_position, vs_size), `_isolation_profile` (492:
defender_quality, vs_set_defense, late_clock), `_foul_tendency` (465: early_trouble, foul_out_risk),
`_quarter_shape_fatigue` (497), `_rest_b2b_splits` (722), `_shot_clock_scoring` (722), `_usage_role` (722),
`_spacing_gravity` (979); `atlas_team_defensive_scheme`, `_offensive_scheme`, `_rotation_patterns` (closing_lineup,
star_rest, q4_patterns, stagger_times), `_clutch_team`, `_pace_identity` and 11 more at 30 rows each.

**On 8 stores sampled evenly, every one carries a SINGLE `as_of` = `2026-05-31`, min == max [m].** A snapshot, not a
series. Consequence **[m]**: of the 1,593 games in the NBA in-play checkpoint corpus, **5** fall after 2026-05-31
(915 ticks); 1,588 do not. An atlas join to that corpus is look-ahead on 1,588 of 1,593 games. Row **S223**.

~20 further `data/intelligence/` stores have **no date column at all** (`defensive_schemes` 30,
`archetype_scheme_interactions` 108, `position_scheme_interactions` 315, `pos_vs_pos_matchups` 84,
`matchup_deviations` 581, `lineup_chemistry` 6,123, `pair_chemistry` 998, `teammate_correlation` 71,001,
`similarity_matrix` 26,335, `quarter_profiles` 559, `possession_type_profiles` 503, `clutch_cv_split` 199,
`coaching_adjustments` 58 ...); their mtimes are build times, not data as-of, so freshness cannot be checked and a
walk-forward join is unavailable. Below any usable floor: `q1_extrapolation_signals` and
`officials_player_sensitivity` **0 rows**; `star_absence_effects` 2 stars; `absence_cv_impact` **5**;
`atlas_team_matchup_adjustments` 2; `atlas_player_turnover_profile` 18; `atlas_player_pace_fit` 28;
`clutch_rankings` 43 players at n_games 2-4; `atlas_player_matchup_splits` 106 -- and that last is exactly the
person-to-person table the matchup family wants.

### 1c. The served surface

`data/cache/profiles/` long format (`entity_id, entity_name, window, attribute, raw_value, percentile, rating_2k, n,
ingredients, status, sources`) **[m]**: `nba_player_profiles` 75,053 rows, `nba_lineup_profiles` 40,408 (five-man
lineup grain), `nba_team_profiles` 2,908, plus MLB, tennis, soccer, WNBA; NBA as_of 2026-07-26. Exercised live:
`scouting_report(nba, Nikola Jokic)` returns 8/8 concept axes (clutch percentile 98.1 n 124; gravity 92.3 n 2118.92;
versatility 92.6), a 10-axis shooting facet and 8 raw attributes, each separately cited, never collapsed to one
number; `staleness_days` 39.32. `matchup_preview(nba, OKC, DEN)` returned 5/8 blocks ok, 3 absent -- `home_profile`
no_data ("OKC" resolves to 0 candidates) and BOTH injury reports **refused** at 48.8 d / 49.7 d against a 7 d bound.
Its `style_matchup` block states it is "sport-level style-pairing statistics ... not filtered to these two specific
teams -- no team/player-to-style-category resolver is wired in this composer" -- that absent resolver is why no
matchup-grain signal is served today, and supplying it is part of S229. `data/registry/signal_registry.parquet`
(read only): **86 rows x 11 cols**; entity player 59 / team 19 / lineup 8; **status folded 72, deferred 14, zero
shipped**; `coverage_pct` **null on all 86**. `INTELLIGENCE_GAPFINDER_2026-09-03.md` section 3 measured, on 30 of
the 151 `data/intelligence/` files sampled evenly, zero readers on 15 of 30 and "Nothing in the MCP surface reads
`data/intelligence`".

### 1d. In-game corpora: price, clock, player

`nba_checkpoints_full.parquet` 465,249 ticks / 1,593 games, 2024-10-22 .. 2026-06-13, columns `game_id, game_date,
ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win,
venue` **[m]**; `traded` 1.0 on every row; venue polymarket. **No player or lineup column** (S80: 0.00 pct).
`nba_price_series.parquet` 8,399,632 rows has prices but no period/clock. `ingame_eval_cache.parquet` 2,476,544 rows
/ 1,987 games / 707 players has `player_id, stat, cur, truth, l5, period, game_elapsed_sec, score_margin` and **no
market column**; its ids are NBA Stats (`0022200523`) against the checkpoints' ESPN ids (`401704627`) -- raw game_id
overlap **0**, 11 common dates / 40 common games **[m]** -- and it stops at 2025-10-24. That path is closed. **No
store on disk carries an explicit 5-man on-floor stamp keyed to period+clock**: `lineup_chemistry` has `lineup_id`
but no clock, `garbage_time_segments` has clock but no players. **`data/shadow/` (10,406,478 rows) is NOT a price
corpus** -- its only `book` value is `l5_proxy`, synthetic; the only genuine in-play prices are under
`data/cache/inplay_odds/`.

**The bridge that is open.** `data/domains/basketball_nba/espn_nba_game_bridge.parquet`, 1,299 rows,
`match_confidence` `exact` on 1,299/1,299, seasons 2024-25 (1,225) + 2025-26 (74), holding both `event_id` and
`game_id`. Its `event_id` joins the checkpoint corpus on **635 of 1,593 games = 187,203 of 465,249 ticks [m]**.

### 1e. Two in-game conditioning layers exist and were never scored against the market

`ingame_hypothesis_{hot_night,scheme_fit}.json` + row parquets: hot_night 7,350 rows / 1,225 games (2024-25) and
444 / 74 (2025-26), keyed by ESPN event_id, columns `game_id, period, seconds_remaining, score_diff, p_live,
outcome, cond_delta, cond_prior, team, layer, season` **[m]**; `cond_delta` non-zero on 100 pct of rows; **579 of
the 1,225 hot_night games are in the checkpoint corpus [m]**. Own caveats: "IN-SAMPLE LEAK: the prior
(QUALIFY_SEASON=2024-25) is fit on the SAME season it is scored against"; "No in-play odds -> verdict is
CALIBRATION (held-out Brier), never a market edge"; and for hot_night "PLANTED NULL SURVIVED: the shuffled
conditioning prior ALSO beat BASE (delta CI excludes 0) -- a flexibility artifact. Downgraded SHIP -> REJECT".
Recorded: hot_night brier_base 0.1723 vs brier_prior 0.1689, delta 0.00345, DM CI [0.00201, 0.0049]; scheme_fit
brier_prior 0.1726, delta -0.00027, CI [-0.00052, -0.00002], `fold_sign_consistent` false, n_clusters 919. The "no
in-play odds" caveat is now false on disk. Row **S225**.

### 1f. A pregame player-prop close exists and has never entered the harness

`data/cache/cv_fix/closing_props/*.json`, **77 files**, one per game, each an odds-API payload `id, sport_key,
commence_time, home_team, away_team, bookmakers` **[m]**. `prop_calibration_history.parquet` holds 4,942 rows keyed
`player_id, stat` with `n, mean_pred, mean_actual, bias, mae, rmse, n_interval, interval_coverage, interval_nominal`
**[m]** -- own-baseline only, no market column. Nothing in the S-register references `closing_props`. Row **S228**.

---

## 2. Family design

**The prior every family is priced against.** The NBA tick surface is recorded "exhaustively NULL at +0.004 with
data on disk" over 24 uncharged screens S79-S105 (`INGAME_WAVE_VERDICT_2026-09-03.md`): S94 early shrinkage
NEGATIVE, S96 drift-following -0.000138, S97 Kalman +0.000003, S102 576-hypothesis sweep SCREEN_NULL, S103 sigma
grid +0.000261, S114 nested ensemble best arm -0.000400 CI [-0.000934, +0.000133]. S82: 0 of 14 MLB in-game features
clear +0.004. S80 player-grain: SCREEN_NULL. **The honest expected effect for every family below is NULL or
UNDERPOWERED.** What is new is that they condition on as-of-safe intelligence (1a) and on state PARTITIONS and TAILS
never scored separately, and each is built so the NULL is informative.

**F1 -- tail calibration by state: comeback / longshot in the 1-10 pct bins (S224).** Target: home win at tick t.
Partition **[m]**: trailing-side `market_prob <= 0.10` is **136,809 ticks / 775 games**, realized `outcome_home_win`
**0.006652**; two-sided extreme (<= 0.10 or >= 0.90) 308,756 ticks / 1,590 games. Metric: reliability table over the
1-10 pct bins AND its 90-99 pct mirror reported symmetrically, market and incumbent ECE/Brier restricted to those
bins, game-clustered CI, and the 80 pct-power minimum detectable delta per bin. `garbage_time_segments` (1,226,606
rows) separates a true comeback state from a decided game -- without it the longshot bin is contaminated. The cell
is defined on `market_prob`, tick-observable, so it cannot leak; walk-forward by game-first-date. Expected: the
market is calibrated in the extremes and the cells are UNDERPOWERED at +0.004 -- the finding that stops later lanes
chasing comebacks.

**F2 -- intelligence conditioning re-run, leak-free, vs the in-play line (S225).** Conditioning: the hot_night and
scheme_fit layers, with `momentum_signals` (673,204 as-of rows) as the honest hot-scorer replacement for hot_night's
in-sample prior. Construction: prior fit strictly on data EARLIER than the scored game, walk-forward by
game-first-date, truncation invariance at 8 evenly spaced probes as `foundry/ingame_guards.assert_tick_asof` already
does. Corpus: the bridged ticks, 187,203 / 635 games, 579 carrying a hot_night row. Metric: Brier and ECE vs (a) the
S123 leak-free NBA incumbent and (b) `market_prob` at the same tick, with the **planted-null (shuffled prior) arm
beside every real arm** -- that control killed the original result and must never be dropped
(`signals/planted_nulls.py` and `player_def_archetype_sidecar_null.parquet` both exist). FWER: family
`ingame_intel_nba` declared before any charge; screen side first. Expected: the planted null survives again ->
REJECT, published as confirmation of the original honest downgrade.

**F3 -- clutch / foul-trouble / rotation state (S226).** Partition **[m]**: the CLUTCH cell (period 4, |margin| <=
5, `game_clock_s` <= 300) is **62,465 ticks / 702 games**; period 4 overall 284,586. As-of-safe conditioning on
disk: `inplay_foul_state` (5,010 rows, team foul totals by game+period) and `possession_states_*` (30,383 / 30,199
rows, `seconds_remaining`, pace, `run_diff`); the atlas foul/rotation stores are SNAPSHOT-ONLY, so the row reports
that join BLOCKED-ON-S223 rather than silently doing it. Construction: a NEW sibling beside
`foundry/ingame_grammar_nba.py`, never an edit to it. Metric: market ECE and incumbent Brier inside the clutch cell,
then improvement over the S123 incumbent at +0.004 with a game-clustered DM CI and BH within the family.

**F4 -- blowout-margin tails, CRPS (S227).** Target: final home margin and P(|margin| >= m) on a frozen ladder;
every existing in-game arm is binary and therefore blind to this tail. Metric: CRPS of the margin distribution plus
tail coverage at the ladder points, against the module's fixed sigma -- S58 trial B and S103 record that the
constant 13.5 sigma "over-states confidence at halftime" and was "half the model-vs-line gap", with a per-cell
fitted sigma bringing the state-priced prior to -0.0021 vs the line (CI including zero). Corpus: 465,249 ticks /
1,593 games, `garbage_time_segments` supplying the blowout label and the spread/total ladders `matchup_preview`
already emits supplying the frozen m ladder.

**F5 -- the player-prop close and the top-scorer upset (S228).** As-of-safe conditioning: `momentum_signals`
(673,204), `per_player_calibration` (307,643 -- rolling bias and `sigma_resid`, the tail WIDTH a CRPS score needs),
`gt_weighted_forms` (99,157), `schedule_strength_7d` (99,498). Targets: (i) a player's stat for the game -- CRPS and
pinball on the distribution, Brier with reliability bins on P(over the closing line); (ii) the WILD outcome -- P(a
given player outscores the pregame favourite scorer in that game), log-loss vs a base rate, a tail event by
construction never forecast here. Corpus: the 77 `closing_props` payloads, first parsed to a tidy `(game, player,
stat, line, over_price, under_price, book, capture_ts)` table. Expected: 77 games is thin, so the honest first
deliverable is the census with an exact n and a NOT SCORABLE / UNDERPOWERED label, as S204 produced for the team close.

**F6 -- specific player vs specific defender / scheme (S229).** The row for "the holes are in SPECIFIC matchups and
SPECIFIC players", feasible only because of two as-of-safe sidecars: `player_def_archetype_sidecar` (99,498
leak-safe rows of player-vs-HELP_DEF / PACE_CONTROL / SWITCH_HEAVY deviation, with a null-control twin) and
`player_opp_splits_sidecar` (99,498 leak-safe player-vs-opponent rows). BLOCKED until S223 because snapshot-only:
`atlas_player_matchup_splits` (106, vs_notable_defenders, vs_specific_defenders_recent),
`atlas_player_isolation_profile` (defender_quality), `atlas_player_vs_scheme_splits` (701) x
`atlas_team_defensive_scheme`. Target: the player's stat residual vs his own as-of expectation in that game. Metric:
RMSE / MAE and a game-clustered CI on the INTERACTION term ONLY against a main-effects-only baseline -- base and
candidate differing only by the interaction (`feedback_gate_baseline_comparability_2026_07_04`). Deliverables: the
defender-join coverage table plus the sidecar-only interaction result, atlas half labelled BLOCKED-ON-S223.

**F7 -- pregame matchup scheme interaction (S230).** Corpus: `matchup_grid.parquet` (4,900 team-game rows with
`game_date`, 2024-10-22 .. 2026-04-12) joined to `gate_corpus_nba` (1,814 rows). Conditioning: the offense-z x
defense-z pairing, plus the UNDATED `archetype_scheme_interactions` (108) / `position_scheme_interactions` (315)
grids used only as a FROZEN hypothesis list, never as a fitted value. Metric: ECE / Brier / log-loss vs `p_close` on
the 563 rows carrying it, of which only 220 are `pregame_last_tick_before_commence` (S204). Proposed KNOWING S108
fit every numeric as-of column (178 for NBA) with logit(incumbent) as offset and the inner CV drove every
coefficient to zero in 20 of 23 outer folds; only the pairwise INTERACTION is untested. Expected NULL.

**F8 -- shrinkage-weighted combination of screened families (S231).** What exists: `signal_ensemble.py` (166 lines)
is a TRACKING-arm ensemble (`tracking_arm_columns`, `build_ensemble_features`, `evaluate_ensemble(frame,
weak_columns, folds=4)`) and does not combine screened families; `foundry/family_combo_screen.py` (S79) picks top-k
from the STORED screen improvement of a pregame family and scores on the same partition -- its own memo calls that
"an in-sample ceiling, not a verdict"; `eval_gate/stacker.py` stacks OOF gap ARMS; `signal_foundry.combine_pool` is
the legacy battery lane. S114 is the one nested-SELECTION result: best arm k=5 at -0.000400 vs the raw line, CI
[-0.000934, +0.000133]; k=5 beats k=1 by +0.0000830, CI [+0.0000027, +0.0001634], p 0.0429 -- "the one CI in this
memo that excludes zero", 48x below the bar. **So selection has been tested and WEIGHTING has not.** Proposed:
inverse-variance and James-Stein-shrunk weights over screened members, plus a ridge/logit stack with the penalty
chosen in an inner fold, **weights fitted on strictly earlier windows only**, walked forward by game-first-date,
scored by Brier and log-loss against (a) the incumbent and (b) the devigged price at the SAME timestamp;
`confidence_ensemble` (307,643 as-of rows of per-signal multipliers + `coverage_class`) is an existing weighting
prior to test as one arm rather than reinvent. Two mandatory guards: the **bundle-widening guard** (memory
`feedback_bundle_widening_regression_2026_07_11`: adding 2 as-of columns to `feature_bundle()` regressed the tuned
NBA improved-ECE 0.01755 -> 0.03113, worse than the 0.02614 naive baseline, via an unlisted consumer at
`scripts/platformkit/nba_winprob_model.py:143`) -- every new column OPT-IN, every caller grepped and listed,
existing callers bit-identical; and the **FWER budget**, the combination counted as its OWN frozen family, never a
free re-read of charged members. Expected NULL at the bar; the informative secondary result is whether shrinkage
weighting beats S114's k=5 selection by more than its +0.0000830.

**F9 -- post-game refreshed feeds, and the family each unblocks.** (i) **MLB Statcast pitch-level** (velocity, spin,
release, per-pitch outcome): the MLB grammar's `pitch_velocity`, `pitch_loc_x/y`, `velo_decline_vs_early`,
`atbat_pitch_number` have **no pitch-grain feed joined to the tick store (S119)**; a refresh keyed `(game_pk,
at_bat, pitch)` unblocks the MLB player-grain family S80 could only run with one pitcher run-prevention residual
(99.14 pct coverage, 8,309 scored ticks / 53 games). (ii) **Full PBP refreshed after the game**, keyed through the
ESPN bridge: supplies the 5-man on-floor stamp NO store on disk has, unblocking F3 (foul trouble, lineup-on-floor)
and F6 (defender pairing) at real lineup grain. (iii) **Workload / rest / availability refreshed daily**: converts
the snapshot-only `atlas_player_durability_load` / `_rest_b2b_splits` into the as-of series S223 requires, and stops
the injury blocks returning `refused` at 48.8 d. Acquisition rows belong to S213-S222; naming what each buys belongs
here.

---

## 3. Fast test plan: families -> foundry candidates -> pod batch (S232)

**The queue is a SQLite table, not a file format**: `results_db_sql.py:29-31` `queue(hash PRIMARY KEY, tier,
enqueued_at, claimed_at, lease_until, claimer)`, default `data/cache/eval_gate/hypotheses.sqlite` (0 bytes today),
trials sidecar `data/cache/eval_gate/trials`; `hash` is `grammar.semantic_hash`, joined to a `hypothesis` table
(`family, sport, feature, transform, params, conditioning, horizon, market, runtime_available, grammar_version`).
Written by `ResultsDB.upsert_hypothesis` + `enqueue(hashes, tier)`, consumed by `claim(n, tier=)` under a 900 s
lease. Worked examples on disk: `s102_nba_sweep.sqlite` (2.36 MB), `s85_screen_2026-09-03.sqlite` (1.36 MB).

**Three extension points that need NO shared-module edit** -- what makes S232 additive: (1) a parquet matching
`catalogue.GLOBS` (`*states*.parquet`, `opp_allowed_asof_*.parquet`) is enumerated with zero code change, since
`seed_queue.hypotheses()` reads each present catalogue parquet's columns and `grammar.enumerate_family` fans them
over the frozen alphabet (a NAMED path costs one line in `catalogue.NAMED`); (2) a new FWER family is one `### fam:
<name>` block appended to the tracked, git-blob-pinned `docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md`,
parsed by `family_bars._parse_families_spec` -- the intended spec-writer surface, explicitly amendable ("nothing
removed, no bar moved"), as S89/S102/S144 all did; (3) a new predictor may live in a new file, since
`backtest_runner._load_callable` takes a `"module:callable"` string with signature `(train, test, select_inside) ->
float`. `foundry/asof_supply.REGISTRY` and `signals/runtime_registry.REGISTRY` DO require a shared edit and are
PROPOSED-only here; `eval_gate/ledger.py`, `eval_gate/backtest_runner.py` and `combo/fwer_budget.py` (note
`scripts/platformkit/combo/`, NOT `eval_gate/combo/`) are gated by `docs/evidence/SHARED_MODULE_TOKEN.md`.

**Charging** goes only through `tiers.charge_tier(tier, ledger_path=, family=, hypothesis_hash=, prereg_sha256=,
sport=, start=, end=)`, which refuses T0/T1, plus `ledger.next_k_family`, `fwer_budget.{eps_eff, min_corpora_eff,
bh_within_family, across_families}` and `family_bars.dual_bar_verdict` (an AHEAD must clear BOTH the global
Bonferroni and the within-family BH bar). T0/T1 are NEVER reportable: T1's verdict is `SCREEN`, a non-finding.
**Caveat for any arm row:** there is **no arm-registration wiring in production** -- `ingame/arm_registry.ArmSpec`
exists but nothing instantiates it (`gap_leadoff_arm.py:6`: "This module is offline and does not register or enable
an arm"), and `enabled=True` makes `run_shadow` return `promotion_flags_must_remain_off`. A row adding an ARM must
define that mechanism, not reuse one.

**What runs where.** No `--pod` flag exists; the pod adaptation is `FOUNDRY_PORTABLE_CORPUS=1` (`tiers.py:215`,
`screen_predictor.py:248`), and batching is `foundry_runner.main()` with `--sport a,b,c --batch --minutes
--idle-exit --predictor p_base|real --allow-charge` (charge OFF by default), supervised via `launch_all.sh:49`
rather than an ad-hoc nohup job. **Recorded throughput (`S16b_pod_factory_head_2026-09-03.md`): 2,168 T1 SCREEN rows
across all four sports in the first 15 minutes, 0 StaleCorpusError, 0 charges** -- the only real anchor, and it says
the screening tier is not the bottleneck. S58 trial B separately records the NBA as-of replay at "0.1 s per date"
and that "the '~7 h' of S63 was the subprocess dispatch path, not the computation"; S114 ran the nested ensemble on
the pod with artifacts byte-identical to local. **These families are CPU-bound; the pod buys parallelism across
candidates, not GPU throughput.** PAUSE the runner before a large seed -- seeding while it was live killed it with
"database is locked", fixed by `timeout=30` in `results_db` (S110); the pod catalogue was seeded at 46,476
hypotheses. No per-family runtime is quoted because none has been run. **LOC rail**: `LOC_CAP = 300` on every
non-test `*.py` under `scripts/platformkit/` recursively (`tests/platformkit/test_loc_rail_scope.py`), with a
~139-entry ratchet ALLOWLIST; every new helper these rows add must land <= 300 lines.

---

## 4. What the pool CANNOT support today

1. **No as-of history in the atlas or in ~20 undated intelligence stores.** Single as_of 2026-05-31 on 8/8 sampled;
   5 of 1,593 checkpoint games post-date it, so every family drawing on `atlas_*` or an undated store is
   look-ahead. **Unblocked by:** S223 naming the exact producers, then a walk-forward rebuild from the source game
   logs (F9 iii feeds it). The 1a sidecars are NOT affected -- they carry per-row `game_date`.
2. **No 5-man on-floor stamp anywhere keyed to period+clock.** NBA ticks 0.00 pct (S80); `lineup_chemistry` has
   `lineup_id` but no clock; `garbage_time_segments` has clock but no players; the only player-grain in-game store
   has no market column, a disjoint id space (0 game overlap **[m]**) and stops at 2025-10-24. **Unblocked by:** a
   post-game PBP refresh keyed through `espn_nba_game_bridge.parquet` (1,299 exact) -- F9(ii).
3. **No player-level market except 77 pregame files**, and no in-play player market at all; `data/shadow/` (10.4 M
   rows) is NOT a substitute -- `book` is `l5_proxy` only, synthetic. **Unblocked by:** capture, a decision row.
4. Also absent: no in-play close for tennis (18 priced rows of 1,255) or soccer (S117 CLOSED AT LIMIT at 2 scored
   game clusters); no MLB pitch-grain feed joined to the tick store (S119); no team/player-to-style resolver in
   `compose_matchup`; no production arm-registration wiring; and the stores below any usable floor listed in 1b.

---

## 5. Ranked by expected calibration effect per unit of work

| rank | id | sport | slug | why here |
|---|---|---|---|---|
| 1 | S223 | all | intel_pool_asof_census | one measurement decides which half of the pool any family may use; 5-of-1,593 is already the answer for the atlas, and the row makes it exact over all 45 stores and names the producers to rebuild |
| 2 | S224 | nba | ingame_tail_calibration | the longshot / comeback question in the metric that answers it; 136,809 ticks / 775 games in the extreme cell, with garbage-time separation available; cannot produce a false positive |
| 3 | S225 | nba | ingame_intel_conditioning_rerun | two conditioning layers already built, a market anchor now reachable on 187,203 ticks, a 673,204-row as-of momentum store to replace the in-sample prior, and a planted-null control that already killed the result once |
| 4 | S232 | all | intel_foundry_queue_wiring | without it every family is a one-off script; with it they are queue rows the pod screens in batch at 2,168 screens / 15 min |
| 5 | S229 | nba | matchup_player_vs_defender | the "specific matchups, specific players" hole, and the ONLY matchup family with as-of-safe inputs already on disk (two 99,498-row leak-safe sidecars plus a null twin) |
| 6 | S228 | nba | pregame_prop_close_upset | the only player-level market on disk (77 games) has never met the harness; adds the top-scorer-upset tail target and has `sigma_resid` on hand for CRPS |
| 7 | S231 | all | signal_combination_shrinkage | selection was tested (S114) and weighting was not; an existing 307,643-row confidence layer to test as an arm, and the bundle-widening guard that already caught one regression |
| 8 | S227 | nba | margin_tail_crps | every existing in-game arm is binary and blind to the margin tail; asks the fixed-sigma question in the metric that sees it |
| 9 | S226 | nba | ingame_clutch_foul_rotation | prices the clutch cell (62,465 / 702) with real foul state, and establishes the sibling-grammar pattern every later family reuses |
| 10 | S230 | nba | pregame_scheme_interaction | S108 already zeroed every single-column coefficient in 20/23 folds; only the pairwise interaction is untested, on 220 pregame close rows |

---

## NOT VERIFIED

- Nothing here was scored. Every family is a proposal with its before-measurement.
- Direct measurements **[m]**: the atlas schema / row / as_of table (8 of 45 stores), the profiles row counts, the
  checkpoint schema and its clutch / longshot / post-atlas censuses, the checkpoint x eval-cache zero overlap, the
  bridge x checkpoint 635-game / 187,203-tick join, the hot_night and scheme_fit counts and their 579-game
  intersection, the 77 closing_props files, and the prop_calibration_history schema. Sections 1a/1b/1d and section 3
  come from two read-only mapping passes in this session; the S16b throughput figure is quoted, not re-run.
- No file over 300 MB was opened. `eval_gate/spa_catalog_report.txt` is absent at that path.
- The atlas as_of finding rests on 8 stores of 45; S223 must enumerate all 45. Absence of a date column is not proof
  a build was leak-free -- only that freshness cannot be checked from the file.
- The 635-game bridge join was verified on the KEY only; whether the bridged rows align in TIME (tick clock vs
  `seconds_remaining`) was not checked, and S225's premise step must check it first.
- The longshot cell's 0.006652 is the HOME-side outcome under a home-side `market_prob` filter -- a raw census
  figure, not a calibration verdict. S224 reports both sides.
- `garbage_time_segments` carries a build date, not a data as-of, and its join key to the checkpoint corpus (ESPN vs
  NBA Stats id space) was NOT verified; that is S224's step 0.
- Rank order in section 5 is my judgement of effect-per-work, not a measurement.
