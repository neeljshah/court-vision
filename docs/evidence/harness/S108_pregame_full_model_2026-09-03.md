# S108 -- the first FULL-FEATURE regularised pregame model, screened against the incumbent (2026-09-03)

## VERDICT: NULL in all four sports -- 0 of 8 arms clear +0.004, and the nested inner CV chose ZERO features in 20 of 23 outer folds

The gap row's question was "what happens when you stop adding ONE feature to logit(close) and fit
EVERYTHING at once?". Answered, on the pod, over every numeric as-of column the gate corpus and the
domain as-of tables supply (178 / 22 / 54 / 178 columns for nba / mlb / soccer / tennis), with
logit(incumbent) as a TRUE OFFSET, nested walk-forward on the SCREEN partition only.

**No arm clears the bar. No arm's unit-clustered CI excludes zero on the good side at a magnitude
anywhere near +0.004. No prereg DRAFT is written.** The load-bearing finding is not the size of the
misses -- it is *what the penalty grid selected*: given the whole feature set and an inner
walk-forward to choose the penalty with, the elastic net drove **every coefficient to zero in 20 of
the 23 outer folds**, so its prediction collapsed to an intercept-only recalibration of the
incumbent (measured directly from the archived per-event CSV: the per-fold standard deviation of
`logit(p_enet) - logit(p_incumbent)` is exactly 0.0 in those folds, and the per-fold Spearman
correlation between the two is 1.0). Out of sample, the best thing the model could do with 178
columns was *not use them*.

Uncharged: no prereg sealed, no ledger read, no ledger write, `_charge_ledger` never called,
`data/cache/eval_gate/backtest_fwer.jsonl` never opened (still 18 rows locally, md5
`a4ae7c13995672e478d59770591b83ba` -- byte-identical to the value S79 recorded -- and still absent
on the pod), `data/registry/` untouched, no flag flipped, no bar moved (`IMPROVEMENT_BAR == 0.004`, asserted
by the per-file test). The VERDICT partition was never built into a states list and never read.
Calibration language only; no retracted figure appears. **NOT VERIFIED** -- this is the lane's own
report; no independent verifier has re-run it.

---

## 0. STEP 0 -- the premise, measured before anything was built (Q8)

### 0.1 Does a multi-feature pregame model already exist on the screen partition?

`grep -rln "LogisticRegression\|GradientBoosting\|HistGradientBoosting\|lightgbm\|xgboost"
scripts/platformkit/eval_gate scripts/platformkit/foundry` returns four modules. None falsifies the
row:

| module | what it fits | on the screen partition? | scored vs the close? |
|---|---|---|---|
| `eval_gate/combo_search.py` | an NBA elastic-net over the `domains.basketball_nba` signal catalog with `logit(close_prob)` as a declared anchor FEATURE | **no** -- it never calls `tiers.partition_corpus`; its rows are the adapter's catalog frame, not a gate corpus | **never run**: its canonical ledger `data/cache/eval_gate/combo_fwer.json` does not exist, so no cumulative K was ever charged and no result artifact exists |
| `eval_gate/pbo.py` | the same elastic net, as the CSCV PBO fixture | no | no (a diagnostic) |
| `eval_gate/s94_nba_early_shrinkage.py`, `s96_nba_overreaction.py` | `LogisticRegression(C=1e6)` = an UNPENALISED 1-2 term recalibration null for an in-game tick arm | no | in-game, vs the raw line |

**PREMISE HOLDS**, with one scope correction worth stating plainly: `combo_search.py` is the closest
prior art -- a real multi-feature elastic net anchored on a real close -- but it is NBA-only, it
lives on a different corpus, it has no nested inner selection (its lambda is picked by the lowest
Brier of the OOF predictions themselves), and **it has never been executed on real data**. S108 is
still the first full-feature pregame model screened on the frozen screen partition, and the first in
any sport other than NBA.

### 0.2 The corpora, per sport

Rows are `screen_predictor.corpus_states(sport)` -> `tiers.partition_corpus(states, seed=20260903)`
-> the SCREEN side only. The screen partition SHAs recomputed here are **byte-equal to the S58c /
S79 artifacts'**, so this lane scored the same rows those did:

| sport | incumbent | partition basis | screen sha256 (16) | n states | **n SCREEN** | n SCORED (outer test folds) | outer folds |
|---|---|---|---|---|---|---|---|
| nba | **`p_base` = Elo, NOT a close** (S98: `p_base == p_elo` byte-identically) | iso_week | `1a32541d44aa7fcb` | 1,814 | **867** | 619 | 5 |
| mlb | **`p_base` = Elo, NOT a close** | iso_week | `ad743c924c7c4547` | 39,162 | **19,589** | 16,791 | 6 |
| soccer | devigged close | corpus_unit | `5c8d63970b08ce97` | 16,322 | **7,656** | 6,562 | 6 |
| tennis | devigged close | iso_week | `c8dde4f3a44c8e58` | 33,685 | **17,352** | 14,873 | 6 |

An nba or mlb number in this memo is **Elo-relative, not close-relative**, and must never be read as
a close-relative one. The scored count is below the screen count because the first chunk is training
data for every design (it is never a test fold), and nba loses one further fold whose train window
fell under the 120-row minimum after the date gap.

### 0.3 The columns: as-of features vs labels vs market

| sport | gate-corpus columns | of which label / spine / market | domain as-of tables joined (one row per event) | **real feature columns** | + missing indicators | **total p** | refused |
|---|---|---|---|---|---|---|---|
| nba | 15 | `event_id, corpus_unit, event_date` (spine), `y` (label), `p_base`/`p_elo` (the incumbent itself) | `asof_box_extra(_ext)` 12, `asof_defender_rollup` 18, `asof_features(_ext)` 11, `asof_team_adv` 27, `boxdetail_asof` 30, `carryover_asof` 6 | **103** | 75 | **178** | 38 |
| mlb | 9 | spine + `y` + `p_base`/`p_home_elo` | `asof_features(_current)` 3, `asof_inning` 6, `asof_park_current` 1 | **11** | 11 | **22** | 16 |
| soccer | 33 | spine + `y` | `asof_features` 18, `asof_xg_proxy` 11 | **29** | 25 | **54** | 0 |
| tennis | 11 | spine + `y` + `p_base`/`p_elo` | `asof_features(_ext2026)` 15, `asof_hold(_wta)` 16, `asof_meta` 3, `asof_return(_ext2026)` 18, `asof_setdetail(_wta)` 36 | **90** | 88 | **178** | 31 |

The MARKET column is the incumbent and enters only as the offset. For nba / mlb the corpus's own
`p_base` and `p_elo` / `p_home_elo` were measured byte-identical to the offset vector on the screen
side and DROPPED as features (they would be a second copy of the offset); for soccer / tennis
`p_base` is a genuinely different number from the close and is kept as a feature. Three nba
`def_switches_per_game` columns were dropped as constant on the screen side.

**Refusals.** Every candidate name passed through `screen_predictor.check_feature_name`, so a
same-game or in-game column is refused BY NAME before any value is read. 85 refusals in total, and
**every one of them is `unavailable`, not `leaky`** -- i.e. the guard never had to reject a
same-game quantity because none reached it; what it rejected were prior-count columns whose names
carry no `asof` marker (`home_n_prior`, `away_sp_starts_prior`, `p1_n_prior`, ...) plus whole tables
refused for grain (`asof_player_adv.parquet`, `carryover_asof__2023/2024.parquet`: >1 row per key)
or for zero overlap with the screen side. The refusal list is archived verbatim in the summary JSON.

---

## 1. MODEL SPEC

Both arms carry **logit(incumbent) as a TRUE OFFSET** -- its coefficient is fixed at exactly 1, so
the model can only learn the residual the incumbent misses. Neither arm can re-weight or discard the
incumbent.

- **(a) elastic-net logistic.** `s108_pregame_full_model.enet_logistic`: an own FISTA proximal-gradient
  solver on `sigmoid(offset + a + X @ b)` with penalty `lam * (0.5 |b|_1 + 0.25 |b|^2)`, intercept
  `a` unpenalised, 400 iterations or `1e-7` convergence, Lipschitz step from the train fold's
  spectral norm (power iteration). Written rather than borrowed because sklearn's
  `LogisticRegression` cannot take an offset and statsmodels' regularised GLM is a version risk
  across the local 0.14.4 / pod 0.15.0 split. Penalty grid `lam in (0.001, 0.003, 0.01, 0.03, 0.1,
  0.3)`, `l1_ratio = 0.5`.
- **(b) HistGradientBoosting.** `hgb_offset`: sklearn `HistGradientBoostingRegressor` fit on the
  Newton working response `z = (y - p0) / (p0 (1 - p0))` with weights `p0 (1 - p0)`, where
  `p0 = sigmoid(offset)`; the prediction is `sigmoid(offset + f(x))`. This is a glmboost-style
  **single Newton step from the offset** -- the offset is exact, the nonlinearity comes from the
  regressor's own 150 boosting rounds. Stated plainly because it is the honest limit of the sklearn
  API: `HistGradientBoostingClassifier` has no `init_score`, and lightgbm (which does) **is not
  installed on the pod** and no external fetch was permitted. Shallow + strongly regularised grid:
  `(max_depth 2, l2 10) / (max_depth 3, l2 10) / (max_depth 2, l2 100)`, `learning_rate 0.05`,
  `min_samples_leaf 50`, `max_iter 150`, `early_stopping` off, `random_state 20260903`.

**Nested walk-forward, screen side only.** Rows sorted by `state_ts`, cut into 7 contiguous chunks;
chunks 1..6 are the outer TEST folds and the train window expands. Inside each outer train window
the same routine cuts 3 inner expanding folds and the penalty / config with the lowest mean inner
Brier is the one whose outer-fold prediction is kept. **Purge and embargo** are implemented as one
blanket date gap of **2 days** applied to every train row before each test window -- a strict
superset of the row's 1-day embargo and of the harness's 48 h same-team purge, so nothing was
loosened (Q3). Asserted per fold in the per-file test and re-checked from the artifact:
`test_start - train_end >= 2 days` in all 23 folds, train indices strictly below test indices, train
windows strictly expanding. **Standardisation and median imputation are computed inside the train
fold only** (`_prep`), and a column with any missing value carries a companion `__isna` indicator
(missing != bad, B3).

Module `scripts/platformkit/eval_gate/s108_pregame_full_model.py` (247 LOC) + helper
`scripts/platformkit/eval_gate/s108_features.py` (115 LOC).
Test `python -m pytest tests/platformkit/eval_gate/test_s108_pregame_full_model.py -q` = **8 passed**
locally (6.89 s) and **8 passed** on the pod (8.15 s).

---

## 2. RESULT TABLE -- 8 arms, 0 clear the bar

`improvement = Brier(incumbent) - Brier(model)`, so positive = the model is better. The bar is
`improvement >= +0.004` AND the unit-clustered (corpus_unit) 95 pct CI excluding zero.

| sport | incumbent | arm | n | p | Brier incumbent | Brier model | **improvement** | unit CI 95 (G) | declared-key CI 95 (G, p) | PBO | clears |
|---|---|---|---|---|---|---|---|---|---|---|---|
| nba | Elo `p_base` | elastic_net | 619 | 178 | 0.202605 | 0.201245 | **+0.001360** | [-0.022932, +0.025651] (2) | [-0.003367, +0.006086] (30, p 0.5608) | 0.000 | **no** |
| nba | Elo `p_base` | hgb_offset | 619 | 178 | 0.202605 | 0.204846 | **-0.002241** | [-0.002702, -0.001781] (2) | [-0.009043, +0.004560] (30, p 0.5056) | 0.000 | **no** |
| mlb | Elo `p_base` | elastic_net | 16,791 | 22 | 0.243596 | 0.243535 | **+0.000061** | [+0.000013, +0.000108] (2) | [-0.000121, +0.000243] (32, p 0.5015) | 0.275 | **no** |
| mlb | Elo `p_base` | hgb_offset | 16,791 | 22 | 0.243596 | 0.244163 | **-0.000567** | [-0.007277, +0.006143] (2) | [-0.000923, -0.000211] (32, p 0.0028) | 0.645 | **no** |
| soccer | devigged close | elastic_net | 6,562 | 54 | 0.239657 | 0.239690 | **-0.000033** | [-0.000490, +0.000423] (3) | same as unit (div = corpus_unit), p 0.7827 | 0.004 | **no** |
| soccer | devigged close | hgb_offset | 6,562 | 54 | 0.239657 | 0.241493 | **-0.001837** | [-0.004011, +0.000337] (3) | same as unit, p 0.0681 | 0.000 | **no** |
| tennis | devigged close | elastic_net | 14,873 | 178 | 0.196062 | 0.196120 | **-0.000058** | [-0.000199, +0.000083] (2) | [-0.000122, +0.000006] (759, p 0.0767) | 0.093 | **no** |
| tennis | devigged close | hgb_offset | 14,873 | 178 | 0.196062 | 0.196926 | **-0.000865** | [-0.004808, +0.003079] (2) | [-0.001320, -0.000410] (759, p 0.0002) | 0.623 | **no** |

Counts: clears the bar **0 of 8**. Improvement above zero at all: 2 of 8 (nba and mlb elastic net,
both against Elo, neither against a close). Best improvement anywhere: **+0.001360**, a third of the
bar, on the smallest corpus (619 events), against Elo. Against a real devigged close, **every one of
the four arms is negative**.

**Two CIs are reported, and the reason matters.** The row asks for a `corpus_unit`-clustered CI, but
nba, mlb and tennis have exactly **two** corpus units, which gives the DM statistic 1 degree of
freedom and a t critical value of 12.71. Those CIs are therefore both very wide (nba elastic net,
+/-0.024) and occasionally very narrow for the wrong reason (mlb elastic net, whose two era means
happen to land close together). The declared SF-10 key (`tiers._cluster_ids`: team / div / player --
the same clustering the S58c single-feature screens and S79 used) is printed beside it and is the
comparable number. Read together they agree on the verdict: mlb's elastic-net unit CI excludes zero
on the good side, but its improvement is **1/65th of the bar** and its 32-cluster CI contains zero
at p = 0.5015. Nothing here is a finding.

**Where a CI does exclude zero, it excludes it on the WRONG side.** The mlb and tennis boosted arms
are measurably WORSE than their incumbents on the declared key (p = 0.0028 and p = 0.0002), and they
carry the two highest PBO values in the table (0.645 and 0.623) -- the overfit probability of the
config grid is where you would expect it to be for a tree model handed 178 columns.

---

## 3. THE ACTUAL FINDING: THE PENALTY GRID CHOSE "NO FEATURES"

Per-outer-fold selections (`lambda`, non-zero coefficients at that lambda, chosen HGB config):

| sport | fold 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| nba (5 folds) | 0.3 / **0** nz | 0.3 / **0** | 0.3 / **0** | 0.3 / **0** | 0.3 / **0** | -- |
| mlb | 0.1 / **0** | 0.1 / **0** | 0.1 / **0** | 0.1 / **0** | 0.01 / 3 nz | 0.01 / 6 nz |
| soccer | 0.3 / **0** | 0.1 / **0** | 0.03 / 2 nz | 0.1 / **0** | 0.1 / **0** | 0.1 / **0** |
| tennis | 0.3 / **0** | 0.1 / **0** | 0.1 / **0** | 0.03 / **0** | 0.1 / **0** | 0.1 / **0** |

**20 of 23 outer folds selected a penalty that zeroes every coefficient.** In those folds the
elastic-net arm is not a feature model at all -- it is `sigmoid(logit(p_incumbent) + a)`, a
single-parameter recalibration of the incumbent. Verified directly from the archived per-event CSV,
which is the only evidence that matters here: the per-fold standard deviation of
`logit(p_enet) - logit(p_incumbent)` is **exactly 0.0** in all 5 nba folds, all 6 tennis folds, 5 of
6 soccer folds and 4 of 6 mlb folds, and the per-fold Spearman correlation between `p_enet` and
`p_incumbent` is **1.000000** in those same folds.

So the honest reading of the nba `+0.001360` is that it is **an intercept recalibration of Elo, not
a feature model** -- Elo's base rate is slightly off on this corpus and shifting it helps a little.
That is a calibration observation about Elo, not evidence that the as-of feature set carries
anything. And on the two sports that have a real close, the same intercept shift is worth
**-0.000033** and **-0.000058**: the devigged close needs no recalibration.

The three folds that did keep coefficients (mlb folds 4-5 at lambda 0.01 with 3 and 6 non-zero, and
soccer fold 2 at lambda 0.03 with 2) are the exception that keeps the result from being a solver
artifact -- the grid CAN and does select non-zero solutions when the inner folds prefer them. It
just usually does not. Penalty stability is otherwise high: nba chose 0.3 in 5/5, tennis 0.1 in 4/6,
soccer 0.1 in 4/6, mlb 0.1 in 4/6. The HGB grid chose `max_depth 2 / l2 100` in 20 of 23 folds --
the most conservative config offered, in every sport.

---

## 4. POD PARITY, TIMING, ARTIFACTS

**Deploy.** `git -c core.autocrlf=false archive HEAD -- <3 paths> | ssh -F ~/.ssh/config.pod pod
'tar -x --no-same-owner -C /workspace/nba-ai-system'`, from commit `55f71c000`. Per-file md5 parity,
`git show HEAD:<f> | md5sum` vs `md5sum` on the pod, **3 of 3 PARITY**:

| file | md5 (local == pod) |
|---|---|
| `scripts/platformkit/eval_gate/s108_pregame_full_model.py` | `8aa8e8cf9dcc8d6aad0671691ff25f21` |
| `scripts/platformkit/eval_gate/s108_features.py` | `26196ed40198aead6ef0eacf6f600d67` |
| `tests/platformkit/eval_gate/test_s108_pregame_full_model.py` | `7055ef09ded580c6539b0207a31d599c` |

**No data was shipped** -- the four gate corpora, their sidecars and every domain as-of table this
lane reads were already on the pod from S75/S78. One honest parity gap: `data/domains/mlb/
asof_espn_box.parquet` exists locally and does NOT exist on the pod. It contributes **nothing** in
either place (40 rows, zero overlap with the 39,162-row mlb corpus), so the pod's mlb feature set is
identical to the local one; the file is named here so the difference is on the record rather than
discovered later.

**Run.** `FOUNDRY_PORTABLE_CORPUS=1 nohup python -m scripts.platformkit.eval_gate.
s108_pregame_full_model --sports nba,mlb,soccer,tennis > /workspace/s108.log`, polled to the
`summary` line. Pod clock: nba artifact 23:42:49, mlb 23:43:11, soccer 23:43:31, tennis + summary
23:44:20 -- under 3 minutes of wall time for all four sports and both arms (RTX 3090 pod, CPU-only
workload). Pod stack: python 3.12, pandas 3.0.5, numpy 2.1.2, sklearn 1.8.0 (local: pandas 2.x,
sklearn 1.6.1); the nba arm was also run locally before deploy and reproduces the pod to the printed
precision (`brier 0.201245`, `improvement +0.001360` identical; the hgb unit CI agrees to ~1e-16),
which is the cross-stack check that the version split changed nothing.

**Artifacts (Q9 -- the per-event paired-loss series).** `scp`'d back to
`data/cache/eval_gate/`:

| file | rows | columns |
|---|---|---|
| `s108_nba_2026-09-03.csv` | 619 | `event_id, event_date, corpus_unit, cluster_id, fold, y, p_incumbent, p_enet, p_hgb, loss_incumbent, loss_elastic_net, d_elastic_net, loss_hgb_offset, d_hgb_offset` |
| `s108_mlb_2026-09-03.csv` | 16,791 | same |
| `s108_soccer_2026-09-03.csv` | 6,562 | same |
| `s108_tennis_2026-09-03.csv` | 14,873 | same |
| `s108_pregame_full_model_2026-09-03.json` | 4 sports | per-fold picks, per-arm stats, every refusal verbatim, source column counts, screen SHAs |

Every row count equals its unique `event_id` count (A4: 619 / 16,791 / 6,562 / 14,873 unique, no
recycled unit). **A2 reproduction:** every Brier, improvement and CI in the table above was
recomputed from the CSVs alone with `dm_test.diebold_mariano` and matches the JSON to the printed
precision. The model side is reconstructible from the artifact: the per-fold `lambda`, HGB config,
`n_train`, `train_end`, `test_start` and non-zero-coefficient count are all archived.

---

## 5. WHAT THIS DOES AND DOES NOT SETTLE

**Settles.** With the whole as-of feature set, a true offset, an honest nested penalty selection and
purge + embargo, there is no measurable residual in the devigged close on soccer or tennis, and none
worth the bar against Elo on nba or mlb. This closes the "we only ever tried one feature at a time"
objection to S58c and S79: fitting all of them together, with the selection done properly, does not
change the answer -- and the selection itself says the features are not worth carrying.

**Does not settle.** (1) Both arms are **SINGLE-WINDOW**: one gate corpus per sport, one screen
side, one seed (Q5 -- an AHEAD would have needed a second corpus, and none was needed because
nothing was AHEAD). (2) nba's 619 scored events is a small corpus and its CIs are correspondingly
wide; a real +0.004 on nba would not reliably be detected here. (3) The HGB arm is a single Newton
step from the offset, not a fully iterated offset-boosting; a lightgbm `init_score` arm would be the
stricter test and needs a package the pod does not have. (4) Only ONE hypothesis class was tried per
arm -- linear-in-features and shallow trees; interactions beyond depth 3, per-sport feature
engineering and pooled cross-sport fits are untouched. (5) The refusal guard is conservative: 85
columns were refused as `unavailable` on a naming rule, and some of them (prior-game counts) are
almost certainly safe. Loosening it is a separate row, and would have to loosen it BEFORE seeing a
result, not after.

**Prereg DRAFT: NOT WRITTEN.** The row conditions one on `improvement >= +0.004` with the CI
excluding zero. The best arm reaches +0.001360 with a CI spanning +/-0.024. Nothing qualifies.

---

## 6. SELF-CHECK (contract sections B and Q)

- **B1** no rows excluded after scoring: the scored set is every outer-test-fold row, fixed by the
  fold geometry before any model ran; the 2-day gap and the 120-row train minimum are the only
  exclusions and both are named with their counts (screen 867/19,589/7,656/17,352 -> scored
  619/16,791/6,562/14,873).
- **B2** additive: two new modules and one new test; no existing column, status value or field
  renamed or removed; no existing reader touched.
- **B3** missing != bad: a missing feature value gets the train-fold median plus an `__isna`
  indicator, never a dropped row; a source with no overlap is refused with a reason, not silently
  skipped.
- **B5** the pod copy went out AFTER the code was committed and its per-file test passed, at md5
  parity, and the run is a measurement -- nothing was promoted, charged or flagged.
- **B6** no module moved or retired; no orphan test or import.
- **B10 / Q3** no bar moved: `IMPROVEMENT_BAR == 0.004` byte-identical to the register row and
  asserted by the per-file test. The purge/embargo gap is STRICTER than the row asks (2 days vs 1),
  which cannot flatter a result.
- **Q1 / Q2** no seal and no charge because nothing was scored on the verdict side and K was never
  read; `_charge_ledger` is not imported by either module.
- **Q4** leak contract: expanding train windows, strictly-earlier rows only, a blanket 2-day gap
  that dominates the harness's 48 h purge and 3-day matchup embargo, standardisation and imputation
  inside the train fold, penalty selection inside the train window. Asserted by the per-file test
  and re-checked from the artifact's `train_end` / `test_start` in all 23 folds.
- **Q5** SINGLE-WINDOW, stated in section 5 and in the register row; no AHEAD was claimed.
- **Q6** calibration language only; no dollar, ROI, profit or edge word; no retracted figure.
- **Q7** the headline is a SCORED metric with n = 619 / 16,791 / 6,562 / 14,873, all above 30.
- **Q8** premise re-measured first (section 0) and it HOLDS, with the `combo_search.py` scope
  correction stated.
- **Q9** the per-unit paired-loss series is archived per sport and the headline recomputes from the
  CSV alone.
