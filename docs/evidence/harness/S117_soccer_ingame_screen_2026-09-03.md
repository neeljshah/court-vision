# S117 -- the in-game screen tier on soccer (its first sport outside MLB/NBA)

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S117. Prior rows: S82 (the tier), S104 (soccer
structured state), S99 (the soccer corpus and its lopsided iso_week partition).
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q, self-checked below.
No prereg, no seal, no charge, no K read. `_charge_ledger` never imported;
`data/cache/eval_gate/backtest_fwer.jsonl` still 18 rows, mtime 2026-09-02 12:27 (before this
lane). No flag flipped, no bar moved, `data/registry/` untouched, nothing read or written under
`src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/`. No pod contact, no external fetch.
Calibration language only; ASCII only.

## Verdict

**SCREEN NULL.** 0 of 7 soccer in-game state features clear the +0.004 bar in either arm, and
every DM interval straddles zero. No prereg DRAFT was written. Against the raw in-play line the
whole tier is BEHIND on this corpus by a wide margin (market Brier 0.157753 vs the walk-forward
candidate's best 0.258641 in the sensitivity arm), which is the honest reading: the live soccer
model is well behind its own market and no state feature recovers that.

The binding constraint is the corpus, not the features. The screen side is 1,277 ticks over 13
games; the tier's own verbatim train floor (`MIN_TRAIN = 1000`, sized for a ~50k-tick MLB store)
consumes 87 pct of it and leaves **163 ticks over 2 game clusters** scored. A DM interval on 2
clusters is not a measurement, so a labelled sensitivity arm is reported beside it.

## STEP 0 -- premise, re-measured (Q8)

Reproduce: `python -m scripts.platformkit.foundry.ingame_screen_soccer` (prints the census).

| Fact the row rests on | Measured |
|---|---|
| soccer_intl joined store | 51 `.jsonl` files, **9,003 ticks** |
| ticks with structured `home_score`/`away_score` | 4,354 (4,649 are the legacy bare `"live"` sentinel -- the 22 pre-cutover files, S104) |
| ... AND a `minute` | **3,658** (696 structured ticks carry score but no minute -- honest absence, S104) |
| ... AND a market line AND a settled outcome | **3,658** (every tick in the store carries `market_prob`, `model_prob` and a settled `outcome`; 0 lost here) |
| games surviving all three | **29** (of 51; the other 22 are 100 pct bare) |
| the >= 15 usable-game floor | **PASS (29)** -- the lane proceeds past the premise |
| tick window | 2026-06-28T00:37:46Z .. 2026-07-12T02:58:40Z |
| outcome mix on the 29 | 15 home wins, 9 home losses, **5 draws graded y = 0.5** by `soccer_outcome` |
| S99's "47 games with a line, 25 usable" | 29 usable here, not 25: S99 additionally required a multi-market Kalshi key; this tier needs only moneyline |

**Incumbent column.** `model_prob` from the joined store -- the live soccer model, which really
does move within a game (42 to 89 distinct values per game, so it is a state-conditioned series,
not a frozen pregame number). **There is no e4 for soccer**; `stacker.e4_gd_series` is MLB-only.
The market line is reported beside the incumbent in every row and is never used as the incumbent.

**Pregame prior -- PREMISE FALSIFIED.** The row asks for "soccer gate corpus p_close / devigged
close by event via the S99 game_keys". `load_gate_corpus("soccer")` is **25,834 club-league rows,
2015-08-07 to 2026-05-24, corpus_unit in {D1, E0, E1, F1, I1, SP1}**; it has **no `p_close`
column at all**, **zero** event_ids containing `KXWC`, and **zero** rows after 2026-06-01. It
cannot supply a prior for a June/July international tournament under any keying. Substitute used,
and labelled everywhere: **the game's own first captured `model_prob`**, which is causal (a value
observed at t0 <= t) and feeds the `prior_vs_line_gap` feature. This is a weaker prior than the
row assumed and the memo does not claim otherwise.

**Minute coverage on the 29 usable games**: 3,658 of 4,354 structured ticks = 84.0 pct. Per game
it ranges from 100 pct (13 of the 29) down to 69.9 pct (`26JUN27DZAAUT`).

## What was built

`scripts/platformkit/foundry/ingame_screen_soccer.py` (294 LOC), additive, zero edits to any
other module. Reused **verbatim** from `foundry/ingame_screen.py` (imported, never copied):
`BAR` (+0.004, the S58 in-game bar -- Q3, byte-identical), `assert_tick_asof`,
`walk_forward_feature`, `screen_rows`, `score_feature`, `partition`. This module supplies only
the soccer loader and the soccer state grammar.

Seven features, each a function of that game's rows with a stamp <= the tick's own:
`minute`, `score_diff`, `goals_total`, `score_diff_decayed`
(`score_diff * exp(-max(0, 90 - minute) / 30)`), `minute_x_score_diff`,
`prior_vs_line_gap` (`logit(prior) - logit(market)`), `minutes_since_last_goal`.

**Tick-time as-of, ENFORCED not asserted**: `assert_tick_asof` rebuilds the feature table from
the causal prefix `src[:k+1]` at 8 EVENLY spaced probe rows (406, 812, 1218, 1624, 2030, 2436,
2842, 3248 -- A3, never a head slice) and requires row k to match the full build. The guard is
proven live in the test: a planted builder that reads `frame["minute"].max()` raises
`TickTimeLeak`.

**Partitions -- both reported, as the row asks.** SF-1 `partition_corpus` basis `iso_week`
(three ISO weeks on this corpus, so it is lopsided exactly as S99 said): **SCREEN 13 games**
(`screen_sha256 d44d93500e308f10...`), VERDICT 16 games (`verdict_sha256 d2e599ebb59e7ebe...`,
never read). **The SCREEN side is the scored side.** Inside it, `walk_forward_feature` runs
game-first-date folds purged on SETTLEMENT with a 1-day embargo. The screen side lands in two
disjoint week blocks (W26 and W28) with the verdict week between them, so every fold trains on
the June block and tests on the July block -- a real, and conservative, gap.

## Headline arm (verbatim train floor 1000)

`data/cache/eval_gate/s117_soccer_ingame_screen_2026-09-03.json`
+ `..._series.csv` (1,141 rows x 15 cols, Q9).

Folds: `2026-07-06 UNFITTABLE (n_train 452)`, `07-07 UNFITTABLE (544)`, `07-09 UNFITTABLE (866)`,
`07-10 UNFITTABLE (866)`, `07-11 OK (n_train 1114 / 11 games, n_test 85)`,
`07-12 OK (1114 / 11, 78)`. Scored games: `26JUL11ARGSUI`, `26JUL11NORENG`.

n = 163 ticks / **2 game clusters**; incumbent Brier 0.123599, recalibration null 0.216658,
market 0.098000.

| feature | improvement vs null | DM CI95 | half-width | n_inf | n_eff | clears +0.004 |
|---|---|---|---|---|---|---|
| minute_x_score_diff | +0.025071 | [-0.337858, +0.388001] | 0.362929 | 129 | 12.7 | no (CI) |
| score_diff_decayed | +0.024032 | [-0.007170, +0.055233] | 0.031202 | 129 | 129.0 | no (CI) |
| minute | +0.011090 | [-0.296076, +0.318255] | 0.307166 | 129 | 5.6 | no (CI) |
| score_diff | +0.000074 | [-0.823119, +0.823267] | 0.823193 | 127 | 3.6 | no |
| minutes_since_last_goal | -0.019118 | [-0.386594, +0.348358] | 0.367476 | 129 | 4.0 | no |
| goals_total | -0.025190 | [-1.438071, +1.387690] | 1.412880 | 127 | 3.3 | no |
| prior_vs_line_gap | -0.058232 | [-1.283687, +1.167223] | 1.225455 | 127 | 2.8 | no |

Every `improvement_vs_market` is negative (-0.093586 for the best feature down to -0.176890).

## Sensitivity arm (train floor 200) -- LABELLED, not the headline

`--min-train 200 --tag mintrain200`; artifact
`data/cache/eval_gate/s117_soccer_ingame_screen_mintrain200_2026-09-03.json`
+ `..._series.csv` (5,775 rows x 15 cols).

`MIN_TRAIN` is the reused walk-forward's **train floor, not a bar**: `BAR` is byte-identical
+0.004 in both arms and the artifact carries `train_floor`, `train_floor_verbatim: 1000` and an
`arm` string saying which is which. This arm exists only so the CI half-width the row asks for is
computed on more than 2 clusters; it is a DEVIATION and is not the reported result.

All 6 folds OK (n_train 452 / 544 / 866 / 866 / 1114 / 1114; n_test 191 / 223 / 108 / 140 / 85 /
78). n = 825 ticks / **8 game clusters**; incumbent Brier 0.323041, null 0.273349, market
0.157753.

| feature | improvement vs null | DM CI95 | half-width | n_inf | n_eff | clears +0.004 |
|---|---|---|---|---|---|---|
| prior_vs_line_gap | +0.014708 | [-0.099443, +0.128860] | 0.114151 | 603 | 12.0 | no (CI) |
| minute_x_score_diff | +0.008298 | [-0.118256, +0.134852] | 0.126554 | 609 | 14.7 | no (CI) |
| minute | +0.001476 | [-0.019279, +0.022230] | 0.020755 | 613 | 50.5 | no |
| score_diff | -0.002290 | [-0.121211, +0.116632] | 0.118921 | 603 | 14.6 | no |
| minutes_since_last_goal | -0.005703 | [-0.031908, +0.020502] | 0.026205 | 613 | 15.7 | no |
| score_diff_decayed | -0.008644 | [-0.087521, +0.070232] | 0.078876 | 609 | 21.1 | no |
| goals_total | -0.024123 | [-0.172820, +0.124574] | 0.148697 | 603 | 14.7 | no |

Informative-only CIs (S87, in the artifact) agree in sign with every full-series CI.
Scored games: MEXENG, PORESP, ARGEGY, SUICOL, FRAMAR, ESPBEL, ARGSUI, NORENG (all July).

## Power: half-width achieved, and the games needed for 0.002

Extrapolation is `n_games * (half_width / 0.002)^2`, i.e. the 1/sqrt(n) rule -- **LABELLED as an
extrapolation, not a measurement**; it assumes the per-game differential variance stays put, which
on 2 (or 8) clusters is itself barely estimated.

- Headline: best half-width **0.031202** on **2 games** (`score_diff_decayed`) -> **~487 games**.
  Median feature half-width 0.367; the same rule then asks for ~67,500 games.
- Sensitivity: best half-width **0.020755** on **8 games** (`minute`) -> **~862 games**.
  The best feature by improvement (`prior_vs_line_gap`, half-width 0.114151) -> ~26,061 games.

The store holds 29 usable games. Even the most favourable reading is **1.5 to 2 orders of
magnitude short** of resolving +0.002 on this corpus. That is the row's real answer: the tier
runs on soccer, and soccer cannot yet power it.

## Contract self-check

- **B1** no row is excluded after a metric is seen; the drop set is the census, printed and
  archived (files/ticks/no_state/no_minute/no_market/no_outcome/kept/games).
- **B2** additive: one new module, one new test, no column, status or field renamed anywhere.
  `ingame_screen.py` is imported, never edited (`git diff` over it is empty; its own test still
  passes, 6 passed).
- **B3** a tick with no structured state or no minute is dropped from the DENOMINATOR at load and
  counted; nothing is quarantined and nothing is guessed or carried forward.
- **B7** the as-of probes are 8 evenly spaced rows across all 3,658, not a head slice.
- **B8** the null arm is the same walk-forward recalibration `[1, logit(p_model)]` fitted on the
  IDENTICAL rows; the two arms differ only by the `c*z(x)` term.
- **B9** the denominator is 29 real games / 3,658 real ticks; `n_eff` is reported per feature
  precisely because 163 ticks over 2 clusters is a degenerate cluster count, and it is called out.
- **B10 / Q3** `BAR` = +0.004 imported from `ingame_screen`, byte-identical, both arms.
  `EMBARGO_DAYS` = 1 unchanged. `MIN_TRAIN` is a train floor, not a bar; the headline uses the
  verbatim 1000 and the 200 run is labelled SENSITIVITY in the artifact and here.
- **Q1/Q2** no prereg, no seal, no ledger row, no K read -- nothing here is scored as a charged
  trial, and nothing clears the bar to make one worth writing.
- **Q4** walk-forward with purge on settlement and a symmetric 1-day embargo; folds asserted
  game-disjoint and `train.ts.max() < test.ts.min()` inside the reused function.
- **Q5** not applicable: no AHEAD is claimed. SINGLE-WINDOW (one tournament, one store).
- **Q6** calibration language only; no retracted figure appears.
- **Q7** the metrics are SCORED, so `n >= 30` binds: n_ticks is 163 / 825 and n_games is 2 / 8.
  The 2-cluster headline is reported as under-powered, never as a result.
- **Q9** the per-tick differential is archived for both arms: game, timestamp, y, p_model,
  p_null, p_candidate, market, x, and the four loss/delta columns. **A2 re-check**: recomputing
  from the CSVs alone reproduces `minute` +0.001476, `prior_vs_line_gap` +0.014708 (sensitivity)
  and `score_diff_decayed` +0.024032 (headline) to the printed digits.

## Evidence paths (all exist at write time)

- `scripts/platformkit/foundry/ingame_screen_soccer.py` (294 LOC)
- `tests/platformkit/foundry/test_ingame_screen_soccer.py` -- `python -m pytest
  tests/platformkit/foundry/test_ingame_screen_soccer.py -q` = **4 passed in 1.50s**
  (truncation invariance; the guard fires on a planted peeking builder;
  `minutes_since_last_goal` resets on a score change; the loader's bare-`live` census)
- `python -m pytest tests/platformkit/foundry/test_ingame_screen.py -q` = **6 passed** (S82
  unchanged)
- `data/cache/eval_gate/s117_soccer_ingame_screen_2026-09-03.json` + `..._series.csv`
- `data/cache/eval_gate/s117_soccer_ingame_screen_mintrain200_2026-09-03.json` + `..._series.csv`

## NOT VERIFIED

This is the lane's own report; no verifier re-run. SINGLE-WINDOW: one tournament corpus, one
store, 29 games, two weeks. The pregame prior is a substitute (the game's own first model
probability), not a devigged close. The draw-as-y=0.5 grading is the store's convention and makes
the Brier levels non-comparable with a two-outcome sport's; the paired comparison is unaffected
because both arms score the same labels. The verdict side (16 games) was never read.
