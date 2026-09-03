# S81 -- the OPEN-to-close move, the one pregame target the close cannot contain (2026-09-03)

## VERDICT: NULL, and the soccer arm is CLOSED AT LIMIT ON THE BAR ITSELF

S108 found the devigged close already contains every as-of feature we hold, so the register's
question was whether a target the close cannot contain by construction -- the OPEN-to-close move
`logit(p_close) - logit(p_open)` -- is reachable instead. It is measurable on exactly two corpora,
and on neither does it produce a claim:

- **soccer (n = 6,562 scored, 3 divisions):** the model recovers **0.41 %** of the move variance
  (sign accuracy 0.5393) and the calibration consequence is **+0.000024 Brier** over the raw open,
  CI [-0.000058, +0.000105]. More decisive than the miss: **the whole prize is only +0.001311
  Brier**. Replacing the open with the TRUE close -- perfect foresight of the entire move -- buys
  0.001311, which is **less than a third of the frozen +0.004 bar**. On soccer totals the bar is
  **unreachable by construction**, not merely unmet. Reported CLOSED AT LIMIT; the bar was NOT lowered (Q3).
- **mlb (n = 257 scored over 33 days, 25 team clusters):** the model recovers 85.2 % of the move and
  the raw improvement over the open is +0.008550 Brier, but the binding cluster CI is
  **[-0.007206, +0.024306]** -- it straddles zero, so no prereg DRAFT is written. And the number is
  not what it looks like: the fitted mean-reversion coefficient is **c = 0.987 .. 1.021 in every
  fold**, i.e. the honest best estimate of the close is *the base rate with the open thrown away*.
  The Kalshi "open" is a single traded tick a median **71.15 hours** before first pitch, correlated
  **-0.843** with its own subsequent move. Beating that is beating a stale quote, not the market.

**No prereg DRAFT.** The bar for one is "the move-adjusted open beats the raw open by >= +0.004
Brier with the CI excluding zero". soccer misses by 170x with the CI straddling zero; mlb clears the
point estimate but its CI straddles zero, and its own ceiling window is a single 33-day slice of one
venue -- **SINGLE-WINDOW** under Q5, so it could not carry an AHEAD even if the CI had cleared.

Uncharged: no prereg sealed, no ledger read, no ledger write, `_charge_ledger` never called,
`data/cache/eval_gate/backtest_fwer.jsonl` never opened (still **18 rows**, md5
`a4ae7c13995672e478d59770591b83ba` -- byte-identical to what S79, S85 and S108 recorded),
`data/registry/` untouched, no flag flipped, no bar moved (`IMPROVEMENT_BAR == 0.004`, asserted by
the per-file test). The VERDICT partition was never built and never read. Nothing was read or
written under `src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/`, or `foundry/`.
Calibration language only; no retracted figure appears. **NOT VERIFIED** -- this is the lane's own
report; no independent verifier has re-run it.

---

## 0. STEP 0 -- the premise, measured before anything was built (Q8)

The register row asks "which corpora carry an opening line beside the close". Answer: **two of the
seven candidates**, and one of those two only after a filter that had to be discovered.

| corpus | rows / events | does it carry a PRE-GAME OPEN beside a close? | n events with BOTH | verdict |
|---|---|---|---|---|
| `data/domains/soccer/odds.parquet` | 16,322 events | **YES.** `ou_open_over` / `ou_open_under` (Pinnacle, `book_open`) beside `ou_close_over` / `ou_close_under`; `avg_*`/`avgc_*`, `b365_*`/`b365c_*`, `max_*`/`maxc_*` are the same open/close pairing per book. Market is over/under 2.5 -- the same market the gate corpus labels. | **16,320** | BUILT |
| `data/cache/inplay_odds/mlb_price_series.parquet` | 13,473,591 rows / 3,932 events (12,817,077 moneyline rows / 3,792 events) | **YES, on Kalshi only.** See the rule in 0.1. The Kalshi ticker is the only local first-pitch clock; Polymarket carries no clock and is excluded exactly as `close_join_mlb` excludes it. | **935** Kalshi (913 after the spine join; 450 on the SCREEN side) | BUILT |
| `data/domains/tennis/odds.parquet` | 33,952 events | **NO.** Every price column is a CLOSING price from a different book: `b365w/b365l`, `psw/psl`, `maxw/maxl`, `avgw/avgl` and the de-leaked `b365_p1/b365_p2`, `ps_p1/ps_p2`. There is no `*_open`/`*c_*` pairing and no second timestamp per event. | **0** | CLOSED AT LIMIT |
| `data/cache/inplay_odds/nba_checkpoints_full.parquet` | 465,249 rows / 1,593 games | **NO -- the row's own premise is FALSIFIED.** The row calls the first traded price "an open-ish". Measured: **zero rows with `period <= 0`**; the earliest tick per game sits at median `game_clock_s` = 699 s of period 1, i.e. ~21 s AFTER tip. Every row in the file is in-game. | **0** | premise FALSIFIED |
| `data/cache/inplay_odds/nba_price_series.parquet` | 8,399,632 rows / 2,572 events | **NO certified boundary.** `KXNBAGAME-26APR26BOSPHI` and `nba-ind-bos-2023-02-23` carry a DATE and no clock, so no tick can be certified pre-tip. | 0 certified | CLOSED AT LIMIT |
| `data/cache/inplay_odds/tennis_price_series.parquet` (1,854,100 / 1,864) and `soccer_price_series.parquet` (204,435 / 89) | -- | **NO certified boundary.** `KXATPMATCH-26JUL01AUGPRI`, `KXEPLGAME-26MAY02AVLTOT`: date, no clock. | 0 certified | CLOSED AT LIMIT |
| `data/cache/venue_history/nba_close_corpus.parquet` | 663 rows | **NO.** Exactly ONE close row per game (`close_kind = last_tick_before_commence`, with `commence_time` and `seconds_before_tip`), `validation_only = True`. A close without an open. | 0 | CLOSED AT LIMIT |
| the pitch tables `data/cache/ingame/mlb_pitch_states__2022..2026.parquet` | 25 columns | **NO.** Pitch state only -- no `odd`/`price`/`prob`/`market`/`open`/`close` column exists. | 0 | not a price source |
| `data/cache/pm_paper` | -- | **DOES NOT EXIST** on this box. | 0 | absent |

**Premise HOLDS on soccer and mlb** (>= 500 events with two pre-game prices), so the row does not
stop at the premise. **Premise FALSIFIED on nba** exactly as the row wrote it -- Q8's "a falsified
premise is a valid result" applies to the nba clause specifically.

### 0.1 The rule for open and close, stated per corpus

- **soccer.** open = `devig2(ou_open_over, ou_open_under)`, close = `devig2(ou_close_over,
  ou_close_under)`, both through the existing `close_join.close_column` (one devig, never two), with
  `avg_*` / `avgc_*` as the documented fallback for the 2 events missing a Pinnacle open. Orientation
  is P(over), the same side the gate corpus's incumbent already uses.
- **mlb.** The Kalshi ticker `KXMLBGAME-<yy><MON><dd><hhmm><away><home>` carries `hhmm` in ET; that is
  the only local first-pitch clock and `close_join_mlb` already certifies it (its own note verifies
  median(close_time - start_ET) = 2.85 h, a normal game length). **open = the FIRST two-sided TRADED
  quote strictly before first pitch; close = the LAST two-sided TRADED quote strictly before first
  pitch**, each devigged through `close_column`. Median open-to-close gap **71.15 h** (5th-95th
  percentile 64.9 - 71.7 h): Kalshi lists an MLB game about three days out.

**`traded` is load-bearing, not a convenience filter (B9).** On the FIRST tick regardless of
`traded`, **87.1 % of opens sit at exactly 0.500** -- the placeholder listing quote. Under that
reading `logit(open)` is a constant, the "move" is just `logit(close)`, and the whole exercise
collapses back into S108's target with extra steps; the first run of this lane produced R^2 = 0.673
that way and it was a degenerate denominator, not a result. Restricted to traded ticks only 3.2 %
sit at 0.500 (8.2 % after the two-sided pairing) and the open has sd 0.172. Every number in this
memo uses the traded rule.

### 0.2 The move itself, and whether the open alone predicts it

| corpus | n both | move mean | move sd | 1 / 5 / 25 / 50 / 75 / 95 / 99 pct | corr(move, logit(open)) | walk-forward AR(1) R^2 |
|---|---|---|---|---|---|---|
| soccer | 16,320 | -0.0079 | 0.1185 | -0.300 / -0.204 / -0.081 / -0.006 / +0.064 / +0.188 / +0.282 | **+0.071** | **+0.0033** |
| mlb (traded) | 913 | +0.0902 | 0.6894 | -1.851 / -0.971 / -0.122 / +0.048 / +0.261 / +1.286 / +2.031 | **-0.843** | **+0.6101** |

The two rows say opposite things and both are informative. The soccer open is a real price: it is
almost uncorrelated with its own subsequent move (+0.071) and a walk-forward mean-reversion null
explains 0.33 % of it -- the market's opening number on totals is already close to its closing
number. The mlb open is not: -0.843 correlation with its own move, sd 0.689 in logit (5.6x soccer),
and a one-parameter reversion null explains 61 % of it. 2.2 % of soccer moves are exactly zero.

---

## 1. WHAT WAS BUILT

`scripts/platformkit/eval_gate/s81_market_move.py` (292 LOC), additive, zero callers elsewhere.

- **Rows.** `s108_features.build(sport)` -> `screen_predictor.corpus_states` ->
  `tiers.partition_corpus(seed = 20260903)`, **SCREEN side only**, then restricted to events
  carrying both an open and a close. The screen SHA-256 is byte-equal to the S58c / S79 / S85 / S108
  artifacts' (soccer `5c8d63970b08ce97...`, mlb `ad743c924c7c4547...`), so this lane scored the same
  rows those did. The mlb partition basis is `iso_week`, the soccer basis `corpus_unit` -- unchanged.
- **Target.** `m = logit(p_close) - logit(p_open)`, clipped at 1e-3 as everywhere else in the harness.
- **Features.** every column S108 assembled (each name passed through
  `screen_predictor.check_feature_name`, imported and never modified -- S85 owns that file this
  session) **plus `logit_open`**; plus `logit_p_base` for mlb, where the incumbent is Elo rather than
  a close and S108 had dropped the base as a copy of its offset. **`p_close` is never a feature** in
  either sport: for soccer/tennis the corpus incumbent IS the close and is excluded by that rule; for
  mlb the incumbent is Elo. 55 columns for soccer, 24 for mlb.
- **Model.** elastic-net LINEAR (`sklearn.linear_model.ElasticNet`, `l1_ratio = 0.5`) on the move,
  penalty chosen by an INNER expanding walk-forward inside each outer train window
  (`alpha in 0.0003 .. 0.1`). Outer folds, the date GAP (purge + embargo), and train-fold median
  imputation + standardisation are S108's `folds` / `_prep`, imported unchanged, so the leak contract
  is the same one S108 was scored under (Q4).
- **Nulls.** (1) ZERO move. (2) an AR(1)-style mean reversion `m = c (logit(pbar) - logit(open))`
  with both `c` and the base rate `pbar` fit on the train fold only.
- **Scores.** out-of-fold R^2 and sign accuracy against each null with unit-clustered CIs, AND the
  calibration consequence -- Brier of `sigmoid(logit(open) + m_hat)` against the OUTCOME, versus the
  raw open and versus the close. **The close is reported as the CEILING, never as something beaten.**

---

## 2. RESULTS

### 2.1 The move

| sport | n scored | p | folds | move sd | enet R^2 vs zero | sign acc | AR(1) R^2 vs zero | enet R^2 vs AR(1) |
|---|---|---|---|---|---|---|---|---|
| soccer | 6,562 | 55 | 6 | 0.1230 | **+0.00412** | 0.5393 | +0.00329 | +0.00084 |
| mlb | 257 | 24 | 4 | 0.5290 | **+0.85170** | 0.7071 | +0.61008 | +0.61966 |

### 2.2 The calibration consequence (the number that decides)

| sport | Brier raw open | Brier move-adjusted open | Brier AR(1)-adjusted | Brier CLOSE (ceiling) | adj - open | binding CI95 | clears +0.004 |
|---|---|---|---|---|---|---|---|
| soccer | 0.240968 | 0.240944 | 0.240962 | 0.239657 | **+0.000024** | [-0.000058, +0.000105] | **NO** |
| mlb | 0.256005 | 0.247455 | 0.251495 | 0.241348 | **+0.008550** | [-0.007206, +0.024306] | **NO** |

**close - open (the whole prize): soccer +0.001311, mlb +0.014658.**

The soccer line is the load-bearing one. The gap between the opening and the closing price on
over/under 2.5 is worth **+0.001311 Brier in total**. A model that predicted the entire move
perfectly would still miss the +0.004 bar by a factor of three. That is why the soccer arm is
CLOSED AT LIMIT rather than merely NULL: no amount of feature work on this corpus can reach the bar,
because the target does not contain that much.

### 2.3 What the fits chose

| sport | fold | n_train | alpha | nonzero coefs | AR(1) c |
|---|---|---|---|---|---|
| soccer | 0 / 1 / 2 | 1,085 / 2,180 / 3,257 | 0.1 / 0.03 / 0.1 | **0 / 0 / 0** | -0.023 / -0.015 / -0.017 |
| soccer | 3 / 4 / 5 | 4,367 / 5,457 / 6,544 | 0.01 / 0.0003 / 0.0003 | 3 / 29 / 31 | -0.023 / -0.029 / -0.028 |
| mlb | 0 / 1 / 2 / 3 | 184 / 232 / 313 / 359 | 0.1 / 0.1 / 0.1 / 0.1 | 4 / 4 / 4 / 3 | **+1.021 / +1.009 / +1.005 / +0.987** |

Two readings, both honest:

- On soccer the inner walk-forward drove **every coefficient to zero in the first three of six outer
  folds** -- the same behaviour S108 measured against the outcome, now reproduced against the move.
  The folds that did select features (29-31 of 55) bought +0.00412 R^2 and a Brier consequence
  indistinguishable from zero.
- On mlb the AR(1) coefficient is **1.0 to within 2 %** in every fold. `c = 1` means the fitted
  best estimate of the close is the base rate with the open discarded entirely. Combined with the
  -0.843 correlation in 0.2, the finding is about the *venue*, not about forecasting: **a single
  traded Kalshi tick three days before first pitch carries essentially no information about the
  pre-first-pitch close.** The +0.008550 "improvement" is the cost of that stale quote being
  recovered, not information the market lacked.

### 2.4 The limits on the mlb arm, stated plainly

`n_with_both_prices` on the screen side is 450 and only **257** survive into scored outer folds
(the first chunk is always training data). The scored window is **2026-06-02 to 2026-07-05 -- 33
days**, one venue, one season, one `corpus_unit` (`era_2022_2026`), so the unit-clustered CI is
undefined and the binding CI is the DECLARED cluster key (`team`, 25 clusters). Only 4 outer folds
form. This is **SINGLE-WINDOW** under Q5 and could not carry an AHEAD verdict even had the CI
excluded zero.

---

## 3. SELF-CHECK against VERIFIER_CONTRACT sections B and Q

| rule | self-check |
|---|---|
| B1 circular metric | No row is excluded by the metric. The soccer denominator is every screen-side event with both prices (7,656 of 7,656); the mlb denominator is stated at each stage: 970 tickers -> 935 two-sided traded -> 913 spine-joined -> 450 screen-side -> 257 scored, every drop named. |
| B2 non-additive schema | Nothing renamed or removed; one new module, one new test, no existing signature touched. `screen_predictor` and `s108_*` are imported, never edited (S85 owns `foundry/`). |
| B3 fall-through loss | Missing != bad: an event without an open or a close is EXCLUDED from the move corpus and counted, never scored as a failure; missing feature values get S108's train-fold median plus an `__isna` indicator. |
| B4 re-claim loop | Not a queue; no claimable item exists. |
| B5 pre-verification deploy | Nothing copied to the pod. Local only. |
| B6 orphans | No module moved or retired. |
| B7 head-slice evidence | The scored rows are the 4-6 walk-forward outer TEST folds spanning the whole corpus tail (soccer 2020-09-20 .. 2026-05-24), not a head slice; fold sizes 1,093-1,094 (soccer) and 64-65 (mlb) are even by construction. |
| B8 self-fit as independent | Every reported number is out-of-fold. The penalty is chosen by an INNER walk-forward inside the outer train window and never sees a test row; the AR(1) `c` and base rate are fit on train only. |
| B9 degenerate denominator | **Caught and fixed in this lane.** The untraded first tick made `logit(open)` constant on 87.1 % of mlb events; the traded rule removes it (3.2 %). `open_at_half_frac` is written into the summary JSON for both sports (soccer 0.0094, mlb 0.0506) so the check is re-runnable. |
| B10 / Q3 moved bar | `IMPROVEMENT_BAR == 0.004`, byte-identical to S108's and asserted by `test_bar_is_not_moved`. The soccer arm is reported CLOSED AT LIMIT rather than scored against a lowered bar. |
| Q1 prereg sealed | No scored CLAIM is made, so no seal is required and none is asserted. This is a SCREEN and a NON-FINDING. |
| Q2 ledger charged | Nothing charged. `backtest_fwer.jsonl` never opened; 18 rows, md5 `a4ae7c13995672e478d59770591b83ba`, unchanged. `_charge_ledger` never called. |
| Q4 leak contract | Outer + inner expanding walk-forward with S108's date GAP (a superset of the harness's 48 h same-team purge and the 1-day embargo), imported unchanged. `p_close` is never a feature. Feature names pass `check_feature_name`, so a same-game column is refused BY NAME before any value is read. |
| Q5 two corpora | Two corpora carry the target and BOTH are NULL, so no AHEAD is claimed. The mlb arm is labelled **SINGLE-WINDOW** (33 days, one venue, one corpus_unit) here and in the register row. |
| Q6 calibration language | Calibration only. No dollar / ROI / profit / edge word. None of +18.38, 0.119, +54, 78.11, 8.94, 54.57 appears. |
| Q7 sampling rail | Both scored metrics are SAMPLED with n >= 30 (6,562 and 257). The premise table is `n = 9 (CONSTRUCT)` -- every local price corpus on disk is enumerated. |
| Q8 premise first | Done before any code: soccer and mlb HOLD, **nba's "first traded price = an open-ish" is FALSIFIED** (zero pregame rows; first tick is ~21 s after tip), tennis has no open column at all. |
| Q9 archive the differential | `data/cache/eval_gate/s81_soccer_2026-09-03.csv` (6,562 rows, 6,562 unique event_ids) and `s81_mlb_2026-09-03.csv` (257 / 257) carry per-event `p_open`, `p_close`, `y`, `m_true`, `m_hat_enet`, `m_hat_ar1`, `p_adj`, all four loss columns, the paired differential, `fold`, `corpus_unit` and `cluster_id`. **A2 reproduction from the CSVs alone: ceiling, adj-open, R^2 and sign accuracy all recompute to the printed digits for both sports.** |

---

## 4. ARTIFACTS

| path | what |
|---|---|
| `scripts/platformkit/eval_gate/s81_market_move.py` | the screen (292 LOC) |
| `tests/platformkit/eval_gate/test_s81_market_move.py` | per-file test, **6 passed in 3.68 s** |
| `data/cache/eval_gate/s81_market_move_2026-09-03.json` | summary for both sports |
| `data/cache/eval_gate/s81_soccer_2026-09-03.csv` | 6,562 per-event rows (Q9) |
| `data/cache/eval_gate/s81_mlb_2026-09-03.csv` | 257 per-event rows (Q9) |

Reproduce:

    python -m scripts.platformkit.eval_gate.s81_market_move --sports soccer,mlb
    python -m pytest tests/platformkit/eval_gate/test_s81_market_move.py -q

## 5. WHAT WOULD UNBLOCK THE CLOSED ROWS

- **tennis:** `odds.parquet` would need an opening-price column. tennis-data.co.uk publishes closing
  odds only; an opening line needs a second source (a book's own open, or a timestamped quote feed).
  Nothing local supplies it.
- **nba:** `nba_checkpoints_full.parquet` starts at tip. `nba_close_corpus.parquet` proves a
  `commence_time` CAN be recovered for the polymarket NBA slate (663 games) -- extending that clock
  to `nba_price_series.parquet` would certify pre-tip ticks and give nba the same open/close rule mlb
  has. That is the single named acquisition for this row.
- **soccer:** no acquisition helps. The prize is +0.001311 Brier and the bar is +0.004.
