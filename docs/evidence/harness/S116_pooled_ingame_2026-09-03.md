# S116 -- a sport-blind in-game residual model with partial pooling (NBA + MLB)

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` line 210 (signals-ingame, gap map L18).
The in-game arms are fit per sport; a sport-blind residual model over normalised state
with hierarchical shrinkage "may lower fold drift on the low-n sport".

Verdict: **SCREEN NULL on the bar -- partial pooling does NOT clear +0.004 with a CI
excluding zero on MLB (improvement +0.012837, game-clustered CI95 [-0.002273, +0.027948],
crossing zero on 63 real-game clusters / n_eff 103.1). NO prereg DRAFT was written.**
The row's own mechanism claim, however, MEASURES POSITIVE and under-powered: partial
pooling cut MLB's mean across-fold coefficient standard deviation from **0.276306 to
0.206281 (-25.3 pct)** and beat the per-sport fit by **+0.001032 Brier**, CI
[-0.0000446, +0.002108] -- a CI that only just crosses zero, over **2 folds**.

**The NBA half of the bar is answered by construction, not by a test** (section 4).

Uncharged: no prereg seal, no ledger read, no ledger write, no K consumed. **SINGLE-WINDOW**
(one window per sport; the sports do not replicate each other, they are ordered in time).
Calibration measurement only -- tick-weighted Brier. No dollar, ROI, profit or edge claim.
No bar moved (`IMPROVEMENT_BAR = 0.004`, asserted byte-identical by the per-file test, Q3).
ASCII only.

Modules (both new and additive; nothing existing was edited):
`scripts/platformkit/eval_gate/s116_pooled_ingame.py` (300 LOC),
`scripts/platformkit/eval_gate/s116_corpus.py` (120 LOC -- split only to hold the
300-LOC rail, the same reason `foundry/run_ingame_screen.py` exists).
Test: `python -m pytest tests/platformkit/ingame/test_s116_pooled_ingame.py -q` = **8 passed**
Archive (Q9): `data/cache/eval_gate/s116_pooled_ingame_2026-09-03.json` +
`...csv` (202,304 per-tick rows x 23 columns: sport, cluster, date, ts_utc, fold, y,
margin, frac_elapsed, margin_sigma, gap, all five arm probabilities, all five losses and
the three paired differentials).

---

## 0. STEP 0 -- premise re-measured first (Q8)

| the row says | measured 2026-09-03 | verdict |
|---|---|---|
| in-game arms are fit per sport; no pooled cross-sport in-game model exists | `grep -rniE "pooled\|hierarch"` over `scripts/platformkit/eval_gate/`, `ingame/`, `foundry/`: 30 non-test hits, **every one within-sport** (per-cell / per-regime / OOF pooling: `s101_aci_coverage` pooled quantile, `s97_nba_sensor_fusion` pooled noise, `stacker.fit_meta` pooled regime weights, `s58_*` pooled units). `close_join.py:43` says ATP/WTA "stay two corpus_units and are **never pooled**". **No module fits one model over two sports.** | CONFIRMED, row stands |
| MLB 392 real games after S106 | **392 is the whole joined store** (227 game_ids). After the e4 walk-forward and the S82 screen partition the reachable set is **145 real games / 72 game_ids / 28,886 ticks**; 63 of those clusters are actually SCORED (section 3) | CONFIRMED with a correction |
| NBA 673 screen games | the S86 SCREEN side is **797 games / 232,951 ticks**; **673** is the number that survives the walk-forward's train-only seed block -- identical to S94's 673 | CONFIRMED |

### Tick columns available, and the normalisation used

| | NBA | MLB |
|---|---|---|
| source | `data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv` (S86 SCREEN side; verdict side never read) | `data/cache/ingame_grade_joined/mlb` via `hedge_trial_arms.load_corpus` + `stacker.e4_gd_series`, then the S82 ISO-week partition (`foundry.ingame_screen.partition`, seed 0) |
| columns read | game_id, game_date, ts, period, elapsed, margin, model, market, y | game, timestamp, market_prob, outcome, state_summary (-> inning, half, home_score, away_score) |
| model / prior | `price_checkpoint(p0_asof, score, period, clock)` over `ratings.replay(until=game_date)` | the incumbent **e4 blend** `arm_b_prob` (game-first-date walk-forward) |
| market | in-play Kalshi line at the tick | in-play Kalshi line at the tick |
| cluster | `nba:<game_id>` | `mlb:<ticker>#<real_game_seq>` (S106 `real_game_split`, NOT the re-used ticker) |
| `frac_elapsed` | `elapsed / (48 + 5 * max(0, period - 4))`, clipped to [0,1] -- **OT-aware**, and period is known at the tick | `(inning - 1 + half) / max(9, inning)`, clipped to [0,1] -- **extras-aware**; half = 0.0 top / 0.5 bottom |
| `margin_sigma` | `margin / 13.5` -- `price_checkpoint`'s own `margin_sigma` default (S86/S98), a constant, never fit | `margin / sd(run differential on TRAIN)`, refit every fold: **3.3286** (fold 3), **3.6701** (fold 4) |
| `gap` | `logit(model) - logit(market)` | same |
| ticks / real-game clusters on the SCREEN side | **232,951 / 797** (2024-10-22..2026-06-10) | **28,886 / 145** over 72 game_ids (2026-06-30..2026-07-05) |

The MLB partition reproduces S82's byte-for-byte:
`screen_sha256 = 79f90ff9eed18ae67929293ed50d474d099c2e19d7fbdd1a75f3cee710486269`,
`verdict_sha256 = d8953537a6c8f91676170370954aa8a36afee48fd86b522e106eab69a0179e4e`
(**never read**). The scored MLB e4 Brier reproduces `s58_clamp_family_trial.REPRO_INCUMBENT`
exactly: `0.206785778212713` on 47,104 ticks / 158 game_ids before the partition.

Premise **HOLDS** -- proceed.

## 1. The model, the three fits and the null

Per tick, with `logit(market)` as a fixed OFFSET (never a fitted coefficient):

```
logit(p) = logit(market) + a_sport
         + b . [frac_elapsed, margin_sigma, margin_sigma * (1 - frac_elapsed),
                logit(prior) - logit(market)]
```

Fitted three ways on the **same** TRAIN rows by penalised IRLS
(`fit_offset`, ridge 1e-6 identical on every fit):

- **PER-SPORT** -- own intercept + own `b`, that sport's train rows only (`lambda = 0`).
- **POOLED** -- one shared `b` plus one intercept column per sport present in train.
- **PARTIAL** -- the per-sport fit penalised by `lambda * ||b - b_pooled||^2`, with
  `lambda` chosen on an **inner TRAIN split** (hold out the sport's last train date,
  purge the inner train by cluster settlement) over the grid
  `(0, 1, 10, 100, 1000, 10000, 1e12)`. The two ends of that grid are the two reference
  fits exactly, not approximately -- the per-file test asserts
  `lambda = 0` reproduces the per-sport fit to 1e-8 and `lambda = 1e12` reproduces the
  pooled coefficients to 1e-6.

**NULL** = the S94 global recalibration `[1, logit(market)]`, fit per sport on the
identical TRAIN rows and applied to the identical TEST rows. It exists because a plain
recalibration of the line already moves Brier, and that movement is not the residual
model's.

## 2. Leak contract (Q4) -- ONE shared, strictly causal calendar

Fold blocks are per sport (`s94.fold_dates`, 5 folds, ordered by game-first date), but the
TRAIN set for **any** fold of **either** sport is every cluster of **both** sports whose
**last tick** precedes the fold's first tick by the 1-day embargo:

```
cut   = test.ts_utc.min() - 1 day
train = rows whose cluster's max(ts_utc) < cut          # both sports
```

Purge is on **settlement**, not first date -- the S82 rule, because this Kalshi store
quotes a game market up to ~2 days before first pitch. Two asserts run per fold and are
exercised by the test with a planted un-settling cluster:

```
assert not (set(train["cluster"]) & set(test["cluster"]))   # cluster-disjoint
assert train["ts_utc"].max() < cut <= test["ts_utc"].min()  # embargo / ordering
```

Cluster ids are sport-prefixed strings on purpose: a bare-integer NBA `game_id` re-types
per chunk when the archived CSV is read back with default dtypes and silently split 673
clusters into 676 in the first run of this lane. `s116_corpus.prepare` now REFUSES a bare
integer cluster id, and the per-file test plants one.

## 3. Folds actually scored

| sport | fold | test | status | test ticks / clusters | train ticks (all sports) | train ticks (own sport) | lambda |
|---|---|---|---|---|---|---|---|
| mlb | 1 | 2026-07-01 | NO_TRAIN | -- | -- | 0 | -- |
| mlb | 2 | 2026-07-02 | NO_TRAIN | -- | -- | 0 | -- |
| mlb | 3 | 2026-07-04 | OK | 7,972 / 52 | 245,257 | 12,306 | 0.0 |
| mlb | 4 | 2026-07-05 | OK | 1,697 / 11 | 247,941 | 14,990 | 100.0 |
| nba | 1 | 2024-12-09..2025-01-25 | OK | 38,179 / 138 | 38,966 | 38,966 | 0.0 |
| nba | 2 | 2025-01-27..2025-11-04 | OK | 38,838 / 123 | 78,495 | 78,495 | 1000.0 |
| nba | 3 | 2025-11-05..2025-12-26 | OK | 38,628 / 137 | 116,246 | 116,246 | 0.0 |
| nba | 4 | 2026-01-02..2026-02-25 | OK | 38,280 / 135 | 155,961 | 155,961 | 1.0 |
| nba | 5 | 2026-02-26..2026-06-10 | OK | 38,710 / 140 | 193,353 | 193,353 | 0.0 |

**MLB gets 2 usable folds, not 5, and the cause is named:** the MLB screen side spans six
dates, and under the settlement purge with a 1-day embargo the first two test blocks have
**zero** settled MLB train ticks (a 06-30 US game is still ticking after 07-01T00:00Z).
`MIN_TRAIN = 1000` (the S82 tier's own minimum) then records them `NO_TRAIN` rather than
fitting on nothing. This is the binding limit on the MLB half of this row.

## 4. The NBA direction is CLOSED BY CONSTRUCTION, not tested

The two screen corpora are **date-disjoint and ordered**: NBA 2024-10-22..2026-06-10, MLB
2026-06-30..2026-07-05. Under a strictly causal shared calendar, no NBA fold can have an
MLB row in its train set (`sports_in_train == ["nba"]` on all five NBA folds, table above),
so the pooled design collapses to the per-sport design and all three arms are **identical**:

| NBA arm | Brier (n 192,635 ticks / 673 games) |
|---|---|
| in-play line | 0.078611 |
| null (recalibrated line) | 0.078931 |
| per-sport residual | 0.078953 |
| pooled residual | 0.078953 |
| partially pooled residual | 0.078953 |

`partial_vs_persport = +0.000000` with a DM CI of `[-9.8e-18, +2.4e-17]` -- floating-point
noise, not a measurement. **"The pooled fit must not hurt NBA" is satisfied trivially and
must not be read as evidence that cross-sport pooling is safe for NBA.** Information in
this corpus can only flow NBA -> MLB. Testing the other direction needs an MLB window that
precedes some NBA window; no such pair exists on disk today.

Separately and honestly: the residual model does not help NBA either. `partial_vs_line` is
**-0.000343**, CI [-0.001124, +0.000438] (crosses zero), consistent with S86's finding that
the state repricer trails the in-play line, and with S94's NULL.

## 5. MLB -- the row's actual question

n 9,669 ticks / **63 real-game clusters** / 2,622 informative ticks;
ICC by real game 0.6087, design effect 93.82, **n_eff 103.1**.

| arm | Brier |
|---|---|
| in-play line | 0.215528 |
| null (recalibrated line) | 0.210827 |
| pooled residual | 0.211336 |
| per-sport residual | 0.203722 |
| **partially pooled residual** | **0.202690** |

| comparison | improvement | real-game-clustered DM CI95 | clears the +0.004 bar? |
|---|---|---|---|
| partial vs the raw line | **+0.012837** | [-0.002273, +0.027948] | **NO -- the CI crosses zero** |
| partial vs the null | +0.008137 | [-0.006820, +0.023094] | crosses zero |
| partial vs per-sport | +0.001032 | [-0.0000446, +0.002108] | crosses zero (just) |
| per-sport vs the raw line | +0.011806 | [-0.003706, +0.027318] | crosses zero |
| per-sport vs the null | +0.007106 | [-0.007898, +0.022109] | crosses zero |
| fully pooled vs the raw line | +0.004192 | [-0.012303, +0.020687] | crosses zero |
| fully pooled vs the null | -0.000508 | [-0.011504, +0.010488] | behind |
| fully pooled vs per-sport | -0.007614 | [-0.021432, +0.006205] | behind |

Informative-tick re-quote (S87): `partial vs line` CI on the 2,622 informative ticks only
is [-0.003503, +0.022244] -- same sign, same conclusion.

**Read the ordering, not the point estimate.** Fully pooled is the WORST residual arm on
MLB (-0.007614 vs per-sport): a single sport-blind coefficient vector dominated by 245k NBA
ticks does not transfer. Partial pooling is the best arm, and it beats both ends of its own
grid -- which is what "partial" is supposed to mean -- but every interval here includes
zero at 63 clusters, so **nothing is established**.

## 6. Fold drift of the coefficients -- the mechanism the row asked about

Across-fold standard deviation of each fitted coefficient (MLB, 2 folds; NBA, 5 folds):

| coefficient | MLB per-sport sd | MLB partial sd | NBA per-sport sd | NBA partial sd |
|---|---|---|---|---|
| intercept | 0.1655 | 0.1692 | 0.0969 | 0.0969 |
| frac_elapsed | 0.3456 | 0.3570 | 0.0703 | 0.0703 |
| margin_sigma | 0.2531 | **0.0407** | 0.2137 | 0.2137 |
| margin_late | 0.4883 | **0.1886** | 0.1453 | 0.1453 |
| gap | 0.1291 | 0.2758 | 0.0636 | 0.0636 |
| **mean** | **0.276306** | **0.206281** | 0.117953 | 0.117953 |

**Drift reduction on MLB: +0.070025 (-25.3 pct)**, concentrated exactly where the theory
says it should be -- the two margin terms, which the 245k-tick NBA prefix estimates far
better than 12k MLB ticks. It is NOT uniform: the `gap` coefficient's spread more than
doubled (0.1291 -> 0.2758), because the pooled `gap` is estimated against a different
prior (an as-of Elo state price for NBA, the e4 blend for MLB) and shrinking toward it
pulls MLB's `gap` in a direction its own folds disagree with.

**This drift number is under-powered and must not be quoted as a result:** an sd over
**2 folds** with `ddof=1` is a single paired difference. It is a direction, not a
measurement. NBA's zero row is the construction of section 4, not a null.

## 7. Verdict, and what would settle it

**SCREEN NULL. The bar is not met and no prereg DRAFT was written.** `prereg_draft_warranted`
is `false` in the artifact. Nothing was charged: `backtest_fwer.jsonl` was never opened,
`_charge_ledger` was never called, no K was read, no seal was written, `data/registry/` was
never touched, nothing was copied to the pod, and the S82 and S86 VERDICT sides were never
read.

The binding limit is MLB cluster count: 63 scored real games / n_eff 103.1 gives a
half-width of about 0.0151 on the vs-line comparison. Reaching the +0.004 bar with a CI
excluding zero needs roughly `63 * (0.0151 / 0.004)^2` -- about **900 scored real games** on
the screen side, i.e. roughly 1,800 scored MLB real games in total. The joined store holds
392. This is the same wall S93 measured from the other side and recorded CLOSED AT LIMIT.

Two things that would move it without new capture:
1. The first two MLB folds are lost to the settlement purge, not to missing data. A
   longer capture window (more MLB dates) converts them straight into folds.
2. The `gap` term is the one coefficient partial pooling makes worse, because the two
   sports' priors are different objects. Pooling `logit(prior) - logit(market)` only
   across sports whose prior is built the same way is the obvious next variant.

## 8. Contract self-check (sections B and Q)

- **B1** no rows excluded after scoring; the scored set is exactly the walk-forward's OK folds, and the excluded ones are NAMED in section 3 with their reason.
- **B2** additive only: two new modules, one new test, one new archive. Nothing renamed, nothing removed, no reader of any existing field touched. `git status` shows no modification to any existing `.py`.
- **B3** missing is not bad: a tick with no parsed inning or score is dropped from the MLB frame before any fit and is never quarantined; a fold with no settled train set is `NO_TRAIN`, reported, and the other folds still score.
- **B4** no claimable state exists; nothing is written back to any store.
- **B5** nothing deployed to the pod.
- **B6** no module moved or retired; no orphaned import or `-m` reference.
- **B7** not a head slice: NBA folds cover 2024-12 to 2026-06 and MLB covers both usable dates; the coefficient table spans every OK fold.
- **B8** the residual arms are scored ONLY on held-out folds; every coefficient, every `lambda` and every sigma is fit on TRAIN rows strictly earlier than the fold.
- **B9** the denominator is not recycled: MLB clusters are S106 REAL games (145 in the corpus, 63 scored), not the re-used Kalshi ticker; NBA clusters are game ids.
- **B10** no bar or threshold differs from the spec: `IMPROVEMENT_BAR = 0.004`, `N_FOLDS = 5`, `EMBARGO_DAYS = 1`, `NBA_SIGMA = 13.5`, `MIN_TRAIN = 1000` (the S82 value), all asserted by the per-file test.
- **Q1** nothing scored here is a charged comparison; no prereg seal is claimed and none is needed for a SCREEN.
- **Q2** no ledger row appended; no K read.
- **Q3** no bar moved. The 2-fold MLB drift number is reported as under-powered rather than being backed by a lowered bar.
- **Q4** walk-forward with settlement purge and a symmetric 1-day embargo on ONE shared causal calendar; both asserts run every fold; no meta-learner is used.
- **Q5** labelled **SINGLE-WINDOW** in the artifact and in the register row. The two sports are NOT two corpora for this claim -- they are the two arms of it, and they are ordered in time.
- **Q6** calibration language only; no dollar, ROI, profit or edge word appears outside the artifact's own disclaimer, and no retracted figure appears anywhere.
- **Q7** every metric is a SCORED metric with n well above 30 ticks; the fold table is an exhaustive enumeration of all 9 fold slots.
- **Q8** premise re-measured first (section 0) and CONFIRMED with one correction (392 is the whole store, 145 is the screen side).
- **Q9** the per-tick paired-loss series is archived beside the summary and **independently reproduces the headline from the artifact alone**: reading the CSV back with default dtypes gives MLB 63 clusters, Brier line 0.215528 / partial 0.202690, improvement +0.012837, CI [-0.002273, +0.027948]; NBA 673 clusters, Brier line 0.078611, improvement -0.000343, CI [-0.001124, +0.000438] -- every figure identical to the JSON.

## 9. Independent cross-check (A2)

The NBA line Brier recomputed here on the walk-forward's scored rows is
**0.07861073077971294** on 192,635 ticks / 673 games, which is the S94 artifact's
`overall.brier.market` to the last digit -- an independent reproduction of the incumbent
denominator, from a different module and a different fold construction.

---
Written by the S116 lane, not by a verifier. Nothing here has been re-derived by a second
party. No number in this memo is a dollar, ROI, profit or edge claim; an honest NULL is a
success.
