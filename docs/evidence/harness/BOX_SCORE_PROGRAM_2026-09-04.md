# Box-score program: per-player distributions, not point estimates (2026-09-04)

User directive (verbatim, 20:20): "not just predicting games but the FULL BOX SCORE; every game is
different, every player has different tendencies." Rows allocated **S240..S246**. Calibration
language only (Q6). Builds on, does not duplicate, S227 (margin tails), S228 (prop close), S229
(player-vs-defender) -- those are still OPEN rows in the register; S246 consumes S228's tidy table
once it lands rather than re-parsing `closing_props`.

---

## (a) What exists

**7 prop models**, `src/prediction/player_props.py` (`_PROP_STATS` L2561): pts, reb, ast, fg3m,
stl, blk, tov -- point estimates only, no minutes. `predict_props` (L2235-2384) assembles them;
`train_props` / `train_props_lightgbm` / `train_props_catboost` (L2749-3028) fit them. Features:
`_build_player_features` (L1034-2176, the single largest function in the module) -- season avgs,
opponent def rating, recent form, matchup/synergy/tracking/shot-dashboard splits, schedule
hardship, ATS context. `src/prediction/prop_model_stack.py` stacks base learners
(`predict_base_learner`), applies a `CalibrationLayer` (isotonic-style `fit`/`transform` plus a
separate `train_win_prob`/`win_prob` that answers P(actual > line) for a given line).

**Honest MAEs -- two legitimate measurements, never mixed** (feedback_mae_measurement_labeling):
- **Production holdout** (`scripts/verify_production_mae.py`, 20,354-row chronological 80/20,
  last-20%-by-date): PTS **4.83**, REB 1.92, AST 1.39, FG3M 0.89, STL 0.71, BLK 0.44, TOV 0.89.
  This is the label to cite in every new artifact unless the OOF set is explicitly named.
- **Walk-forward OOF** (`data/cache/pregame_oof.parquet`, gitignored, ~51K rows/stat = 50,954):
  PTS **4.58**, REB 1.90, AST 1.34, FG3M 0.88, STL 0.71, BLK **0.515**, TOV 0.88, PTS bias ~-0.45.
  A `4.83/0.44` pairing must never cite `pregame_oof.parquet`; BLK on that frame is 0.515.

**Minutes -- point estimates exist, no distribution.** Four separate modules touch minutes:
`minutes_predictor.py`, `minutes_floor_model.py`, `minutes_aware_props.py`, `pts_minutes_model.py`
(all in `src/prediction/`, unread this session beyond `graft grep`). `data/intelligence/` has no
minutes store; `opp_minutes_predictions.parquet` is opponent-facing only. No quantile/CRPS minutes
target exists on disk **[m]**.

**Quantile infrastructure exists but is thin.** `src/prediction/quantile_props.py`
(`build_quantile_models`, same 7 stats) and `quantile_calibration.py` (`_CQR_STATS = {pts, reb,
ast}`, conformalized). `data/models/quantile_pergame_metrics.json` is a 4 KB summary (not raw
rows) reporting a q50 head at PTS MAE 4.651 / BLK 0.440 over 99,818 rows per
feedback_mae_measurement_labeling -- NOT VERIFIED this session (cited from memory, file too small
to hold row-level quantile output, so a true 10/50/90 quantile surface is not confirmed live).

**Prop-line corpus (NBA): 77 files, confirmed [m].** `data/cache/cv_fix/closing_props/` = 77 JSON
files (`ls | wc -l`), one per game, odds-API payload (`commence_time, home_team, away_team,
bookmakers`). `prop_calibration_history.parquet` = 4,942 rows (`player_id, stat, n, mean_pred,
mean_actual, bias, mae, rmse, n_interval, interval_coverage, interval_nominal`) -- own-baseline
only, no market column (S228 spec). S228 (open) is the row that parses these 77 files into a tidy
table; S246 below reads that table rather than re-deriving it.

**Other sports -- measured [m], via `wc -l` / parquet metadata only, no full loads:**

| sport | store | rows | note |
|---|---|---|---|
| MLB | `data/frontend/prop_history_corpus_mlb.jsonl` | 3,000 | `strikeouts` etc.; `market_prob` **null** on the sampled row -- no real market price attached |
| Tennis | `data/frontend/prop_history_corpus_tennis.jsonl` | 3,000 | `df` (double faults) etc.; `market_prob` **null** on the sampled row |
| Soccer | `data/frontend/prop_history_corpus_soccer.jsonl` | **0** | file exists, empty -- no soccer player prop corpus on disk today |
| MLB game-level | `data/cache/combo/gate_corpus_mlb.parquet` | 39,162 | team/game grain, not player props |
| Soccer game-level | `data/cache/combo/gate_corpus_soccer.parquet` | 25,834 | team/game grain |
| Tennis game-level | `data/cache/combo/gate_corpus_tennis.parquet` | 41,886 | match grain |
| NBA game-level | `data/cache/combo/gate_corpus_nba.parquet` | 1,814 | team/game grain (S230's corpus) |

**Holdout protocol + its known leak.** `src/prediction/prop_cv_split.py`: `make_temporal_split`
(TimeSeriesSplit on `game_date`), `sort_chronologically`, `assert_no_future_leakage`,
`filter_excluded_players`. **Known leak class to avoid repeating**: a per-stat XGBoost classifier
for P(actual > line) was tested 2026-06-01 (`feedback_prob_calibration_negative`) and **lost
decisively OOS** -- the late-half realized score fell decisively below the shipped point-blend's (retraction context; see feedback_prob_calibration_negative), with a ~52pp
early/late split signature of data snooping. Any P(over line) target in S242/S246 must reuse the
point-distribution (CRPS/pinball) framing, not retrain that classifier, and must pass the same
temporal-stability bar (both halves agree in sign) if a binary arm is added at all.
**Also standing**: after any retrain, assert `pkl.n_features_in_ == len(meta['feature_columns'])`
(`feedback_prop_model_artifact_drift`) -- a past mismatch produced silent 0-bet failures that a
backtest reported as "INCONCLUSIVE" rather than a crash.

**S233's leak-free utility is the scoring spine.** `scripts/platformkit/eval_gate/
walkforward_embargo_prereg.py` (landed 2026-09-04, 63d5ec4b7): `purge_embargo_walk_forward(states,
predict_fn, embargo_days)` and `seal_prereg` / `assert_sealed`. Every scored row below (S242,
S244, S246) uses this, not a bespoke local `walk_forward` (18 duplicate definitions exist
repo-wide per S233's own count).

**Coherence tooling already exists.** `scripts/platformkit/boxscore_crosscheck.py` +
`tests/platformkit/test_boxscore_crosscheck.py` -- unread beyond the filename this session; S243
must read it before writing anything, since it may already be exactly the sum-to-team check asked
for and only need a distributional (not point) input wired in.

---

## (b) The target

Per-player **distributions**, not point estimates, for: NBA minutes / points / rebounds / assists
/ threes; MLB batter and pitcher lines (where the corpus supports it); soccer shots/goals (BLOCKED
-- 0-row corpus, see (d)); tennis aces/points (thin, 3,000 rows, no real market price, see (d)).
Conditioned on as-of player tendencies (`momentum_signals.parquet` 673,204 rows, `per_player_
calibration.parquet` 307,643 rows carrying `sigma_resid` -- the tail width a CRPS score needs,
`gt_weighted_forms` 99,157), opponent scheme and pace from AS-OF SAFE stores only
(`player_def_archetype_sidecar` / `player_opp_splits_sidecar`, 99,498 rows each, per S223 --
NEVER the snapshot-only atlas stores, single `as_of` 2026-05-31), lineup/injury context, and
in-game state for live updating. Scored by CRPS / pinball loss at the 10/50/90 quantiles /
calibrated coverage vs the closing prop line where one exists (NBA, thin MLB/tennis) and vs a
naive as-of baseline (the player's own trailing distribution) everywhere else. Leak-free
walk-forward via the S233 utility (purged embargo, sealed prereg). n >= 30 game clusters per
scored row. Every landing reproduces fresh-process (no cached numbers quoted without a rerun).

## (c) Minutes as the keystone

Points = minutes x rate (points-per-minute); the same identity holds for rebounds and assists at
their own per-minute rates. A point-estimate minutes number already exists in four separate
modules (see (a)) but no distribution does -- S241 is the correct first build target because every
downstream counting-stat distribution is gated on it: a wrong minutes *spread* silently produces
an overconfident points spread even if the rate model is honest. Box-score components must stay
coherent: the five players' minutes should not exceed 240 (5 x 48) plus overtime, and the
distribution-implied team points/rebounds/assists (summed across the roster) should track the
team-level pace/total the game engine already prices -- S243 is the row that checks this, reusing
`boxscore_crosscheck.py` rather than writing a second sum-to-team check.

## (d) What cannot be done on disk today

- **Soccer player props: BLOCKED.** `prop_history_corpus_soccer.jsonl` is 0 rows. Unblocks with a
  real capture (out of scope for S240-S246; a acquisition row, not a modeling row).
- **MLB / tennis player props: real-market-price BLOCKED.** Both 3,000-row corpora carry
  `market_prob: null` on the sampled row -- scoring against a real closing line is not possible
  without a separate market-price join; S244 scores vs the naive as-of baseline only and reports
  the market gap as NOT SCORABLE, exactly as S228 did for the team close.
- **In-game live box-score at lineup grain: partially BLOCKED.** No store on disk carries a 5-man
  on-floor stamp keyed to period+clock (confirmed in the intelligence-signals memo, section 1d);
  `possession_states_*` (30,383 / 30,199 rows) gives pace and `run_diff` at game grain only. S245
  is scoped to game-state-conditioned remaining-game distributions, not lineup-level ones, and
  says so explicitly rather than silently degrading.
- **Player-vs-defender / scheme conditioning: BLOCKED-ON-S223** for the atlas half (snapshot-only,
  single `as_of`); the as-of-safe sidecar half is open and is what S242/S244 use.

## (e) Rank by expected effect per unit of work

1. **S240** (census) -- cheapest row, unblocks every other row's denominator; must land first.
2. **S241** (NBA minutes distribution, the keystone) -- highest leverage: every counting-stat
   distribution below is gated on it.
3. **S246** (scoring harness) -- needed before S242/S244 numbers mean anything; built once, reused.
4. **S242** (pts/reb/ast conditional on minutes) -- the direct payoff of S241, scored by S246.
5. **S243** (coherence/sum-to-team) -- cheap sanity gate, likely mostly reuses existing tooling.
6. **S244** (MLB batter/pitcher) -- thinner corpus (3,000 rows, no real market price), so the
   honest expected outcome is a NOT SCORABLE census rather than a scored result, but it is fast.
7. **S245** (in-game live update) -- most work (state -> remaining-game distribution machinery)
   for a partially-blocked target (no lineup grain); lowest effect-per-effort of the seven.

## NOT VERIFIED

- `quantile_pergame_metrics.json`'s 99,818-row provenance (cited from memory, file itself is a
  4 KB summary, not re-derived this session).
- `minutes_predictor.py` / `minutes_floor_model.py` / `minutes_aware_props.py` /
  `pts_minutes_model.py` internals (mapped via `graft grep` only, not read; S241 must read them
  before building a new minutes model, to reuse rather than duplicate).
- `boxscore_crosscheck.py` internals (filename + test file located, not opened).
- `prop_calibration_history.parquet`'s full column list beyond what S228's spec already states.
- S228 / S229 landing status at the time these specs are dispatched (both OPEN in the register at
  write time; S246 must re-check before claiming S228's table exists).
- MLB/tennis `prop_history_corpus_*.jsonl` beyond the first sampled row (whether ANY row carries a
  non-null `market_prob` was not exhaustively checked -- S244's premise step must do this).
