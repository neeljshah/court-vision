# S115 -- MORE MODELS, SAME OFFSET (NBA in-game, SCREEN)

Row: "every in-game arm is a single logistic term; untested are non-linear residual models
over the tick state with logit(market) as OFFSET so the model learns only what the line misses."

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` (B1-B10, Q1-Q9).
Tier: SCREEN -- uncharged. No prereg seal, no K read, `_charge_ledger` never called,
`data/cache/eval_gate/backtest_fwer.jsonl` never opened (18 rows, md5
`a4ae7c13995672e478d59770591b83ba`, unchanged before and after). `data/registry/**` untouched.
No flag flipped. Nothing read or written under `src/`, `kernel/`, `api/`, `intel/`,
`scripts/team_system/`. The S86 VERDICT side was never built or read. SINGLE-WINDOW.
Calibration language only (tick-weighted Brier, game-clustered DM CI). ASCII only.

---

## PREMISE (step 0) -- HOLDS

Store present: `data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv`, 232,951 rows x 23
columns, 797 games, `game_date` 2024-10-22..2026-06-10 (the S86 SCREEN side; partition
`foundry.tiers.partition_corpus(seed=0)` on game blocks). Not NO STORE.

`grep -rlE "HistGradientBoosting|MLPClassifier|MLPRegressor" scripts/platformkit/eval_gate/`
returns exactly one module, `s108_pregame_full_model.py`, which is a PREGAME game-level
screen and never opens the tick CSV. The only readers of the tick CSV are
`s94_nba_early_shrinkage.py` (per-cell logit shrinkage + two logistic recalibrations),
`s97_nba_sensor_fusion.py` and `s98_nba_better_prior.py`; none imports a non-linear learner
(their imports are numpy / pandas / scipy / the shared DM + informative-tick helpers).
So no module fits HistGradientBoosting or an MLP on the NBA tick CSV with the market as an
offset. Premise HOLDS -- not FALSIFIED.

## LIMIT (step 1)

n/a (screen row).

## CHANGE (step 2)

`scripts/platformkit/eval_gate/s115_ingame_models.py` (299 LOC) and
`tests/platformkit/ingame/test_s115_ingame_models.py`.

Model: `p = sigmoid( logit(market) + f(state) )`. `logit(market)` is a TRUE offset -- its
coefficient is fixed at 1 and never fit -- so `f == 0` reproduces the raw line exactly and
each arm can only add a correction.

Features (8): `period`, `clock_frac` (= `game_clock_s`/720), `margin`, `dmargin_3`,
`dmargin_5`, `dmargin_10`, `logit_market`, `logit_model` (the S86 `model` column, the
price_checkpoint over the as-of Elo prior). The lagged margins come from `past_delta()`,
which shifts within the game and carries a LEAK GUARD: the borrowed row's `ts` must be
strictly less than the row's own `ts`, otherwise it raises `ValueError("leak guard: ...")`.
It never degrades silently to a same-tick or later read.

Three arms, each fit by ONE Newton step on the logistic working response `z = (y - p0)/w`,
`w = clip(p0(1-p0), floor)`, `p0 = sigmoid(offset)` -- the S108 trick:

| arm | learner | grid (inner-CV picks) |
|---|---|---|
| `hgb` | `HistGradientBoostingRegressor`, `max_depth=3`, `max_iter=150`, `lr=0.05`, `min_samples_leaf=200`, `sample_weight=w` | `l2_regularization` in {10, 100} |
| `mlp` | `MLPRegressor`, `hidden_layer_sizes=(16,)`, `early_stopping=True` on a TRAIN-internal 15 pct split, `max_iter=60`, `batch_size=4096` | `alpha` in {1e-3, 1e-1} |
| `hgb_mono` | the `hgb` arm with `monotonic_cst` = margin increasing | `l2_regularization` in {10, 100} |

NULL = the S94 global recalibration, `LogisticRegression` on `[1, logit(market)]`, fit on the
IDENTICAL train rows of every fold (`s94_nba_early_shrinkage._recal`, imported, not copied).

Design: the S94 design, reused rather than re-derived -- `fold_dates` imported from S94;
expanding walk-forward by game-first date, train = all ticks with `date < (block start - 1
day)`, test = the block; purge by game (asserted game-disjoint each fold), 1-day embargo,
5 outer folds; 2 inner folds of the same construction pick each arm's config on train only.
Train-fold median imputation + standardisation via `s108_pregame_full_model._prep`
(imported). Standardisation is a positive affine map, so the monotone constraint direction is
preserved.

TWO DOCUMENTED DEVIATIONS from the spec text, neither touching the bar or the design:

1. The spec names `MLPClassifier`. `MLPClassifier` admits only class labels, so it cannot
   regress the continuous working response that keeps the offset exact. `MLPRegressor` is
   used instead; the arm's intent (a tiny neural correction with `logit(market)` held exact)
   is unchanged. `MLPRegressor` also takes no `sample_weight`, so that arm minimises
   unweighted MSE on a leverage-bounded working response (`w` floored at 5e-2 instead of the
   HGB arms' S108 floor of 1e-3). Both floors are in the module as named constants.
2. The spec's TEST line says a zero-capacity offset arm "reproduces the null exactly". With
   `logit(market)` as the offset, a zero-capacity arm reproduces the RAW MARKET, not the
   recalibration null. Both facts are tested separately (below): `f == 0` equals the market
   to < 1e-12, and the null is `_recal` fit on the identical train rows of each fold.

## TEST

`python -m pytest tests/platformkit/ingame/test_s115_ingame_models.py -q` -> **5 passed in
4.50 s**.

- `test_leak_guard_raises_on_same_tick_read` -- both a same-tick and a later-tick borrow raise.
- `test_zero_capacity_arm_reproduces_the_offset_exactly` -- `apply_offset(0, logit(market))`
  equals `market` to max abs 1e-12.
- `test_null_arm_is_s94_recal_on_identical_rows` -- the null is fit on the fold's own train
  rows and those rows are game-disjoint from the test rows.
- `test_fold_windows_equal_s94` -- fold `(test_start, test_end, embargo_cut)` and the train /
  test tick counts are identical to `s94_nba_early_shrinkage.walk_forward` on the same frame.
- `test_series_length_equals_scored_ticks` -- the archived series length equals
  `n_scored_ticks` equals the sum of held-out block sizes, no duplicate `(game, ts)`,
  the bar is still 0.004, and every paired-differential column is present (Q9).

## RESULT

`python -m scripts.platformkit.eval_gate.s115_ingame_models`
Scored 192,635 held-out ticks over 673 games in 5 folds (block 0 is the train-only seed).
ICC by game 0.2050, design effect 59.5, **n_eff 3,239.8**; `n_informative` 78,761 of 192,635
(0 duplicate `(game, ts)`; 123,710 held market quotes, 130,894 held model quotes).

| arm | Brier | vs RAW market | game-clustered 95 pct CI | p | vs recal null |
|---|---|---|---|---|---|
| raw market | 0.078611 | -- | -- | -- | -- |
| recal null (S94) | 0.078974 | -0.000363 | -- | -- | -- |
| `hgb` | 0.080022 | **-0.001411** | [-0.002918, +0.000096] | 0.066 | -0.001048 |
| `mlp` | 0.079160 | **-0.000549** | [-0.001476, +0.000378] | 0.245 | -0.000185 |
| `hgb_mono` | 0.080066 | **-0.001455** | [-0.002982, +0.000073] | 0.062 | -0.001091 |

Best arm (lowest Brier) = `mlp`. **Headline = -0.000549** tick-weighted Brier vs the raw
market, CI [-0.001476, +0.000378] straddling zero. On informative ticks only the same paired
losses give -0.001238, CI [-0.003156, +0.000680], p 0.205 -- same side of zero, so the S87
re-quote does not rescue it.

**PBO 0.071** across the 6-config grid (`cscv_pbo` over the OOF prediction matrix in
chronological order).

Per-fold chosen config (inner CV, train only):

| fold | test window | embargo cut | train ticks | test ticks / games | hgb | mlp | hgb_mono |
|---|---|---|---|---|---|---|---|
| 1 | 2024-12-09..2025-01-25 | 2024-12-08 | 38,698 | 38,179 / 138 | l2 100 | alpha 1e-3 | l2 100 |
| 2 | 2025-01-27..2025-11-04 | 2025-01-26 | 78,495 | 38,838 / 123 | l2 100 | alpha 1e-1 | l2 100 |
| 3 | 2025-11-05..2025-12-26 | 2025-11-04 | 116,246 | 38,628 / 137 | l2 100 | alpha 1e-1 | l2 100 |
| 4 | 2026-01-02..2026-02-25 | 2026-01-01 | 155,961 | 38,280 / 135 | l2 100 | alpha 1e-1 | l2 100 |
| 5 | 2026-02-26..2026-06-10 | 2026-02-25 | 193,353 | 38,710 / 140 | l2 100 | alpha 1e-3 | l2 100 |

Both HGB arms picked the STRONGEST available l2 in all 5 folds -- the inner CV asked for the
least capacity the grid offered, which is the same shape S108 and S111 reported when their
inner walk-forward drove every coefficient to zero.

## ACCEPTANCE RULE applied

- metric = tick-weighted Brier improvement of the best arm vs the RAW market on the held-out
  folds; denominator = 3 arms. **-0.000549.**
- before = no non-linear in-game arm exists (0/3). after = 3/3 exist and are scored.
- bar = +0.004 with the game-clustered CI excluding zero AND beating the recal null.
  Not met on any count: the point estimate is NEGATIVE, the CI straddles zero, and all three
  arms are also behind the recal null. **VERDICT = NULL** (a NULL is a PASS of the process).
- n = 3 arms x 5 folds = 15 arm-folds.
- Q3: `IMPROVEMENT_BAR = 0.004`, byte-identical to the spec and to S94/S108; NOT lowered.
- eye check n/a (Q7); reproduction below.

## NON-TAUTOLOGY

The null is fit on the identical train rows of each fold and applied to the identical test
rows. A zero-capacity correction equals the raw market to < 1e-12 (tested), so the arms
cannot be scored against a straw baseline: they are compared to the very line they offset.
The market's own Brier (0.078611) is computed from the archived `market` column, not from any
fitted quantity. Every fold's train set is game-disjoint from its test set (asserted at run
time) and separated by a 1-day embargo.

## EVIDENCE / Q9 ARCHIVE

- `data/cache/eval_gate/s115_ingame_models_2026-09-03.json` -- the summary (8.5 KB).
- `data/cache/eval_gate/s115_ingame_models_2026-09-03.csv` -- 192,635 rows, one per scored
  tick: `game, game_date, ts, fold, y, market, model, p_null, p_hgb, p_mlp, p_hgb_mono`,
  all five loss columns, `d_<arm>_vs_market`, `d_<arm>_vs_null`, `cluster_id = game`.
- A2 reproduction from the archived CSV ALONE recovers every headline number to the printed
  digits: market 0.078611, null 0.078974, hgb 0.080022, mlp 0.079160, hgb_mono 0.080066,
  headline mlp vs market -0.000549, 192,635 rows.

## NOT VERIFIED

- This is the lane's own report; no independent verifier re-run.
- SINGLE-WINDOW: one corpus (the S86 NBA screen side), one season-and-a-bit, one venue's
  price series. Q5 is not satisfied and no AHEAD is claimed -- the verdict is NULL.
- The `mlp` arm minimises unweighted MSE on the working response (see deviation 1); a
  weighted fit could in principle move it, but it would have to move +0.0045 to clear the bar
  from where it sits.
- The feature block is the tick state only. Nothing here says a richer state (lineups,
  possession, book depth) is also null; it says these 8 columns, through three non-linear
  learners with the line held exact, add nothing the line misses.
- The three arms are correlated (same offset, same features, same folds), so "3 arms" is a
  denominator, not three independent tests.
