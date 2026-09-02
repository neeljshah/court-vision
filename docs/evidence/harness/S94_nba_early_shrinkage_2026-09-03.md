# S94 -- phase-conditioned shrinkage of the NBA in-play line toward the as-of state price

Row: S86 measured the in-play market's OWN reliability and found it worst early in close
games (P1|close ECE 0.0556, P2|close ECE 0.0647, one-directional). S94 asks the obvious
follow-up: does shrinking the line back toward the pregame-prior state price repair it?

Verdict: **NO -- SCREEN NEGATIVE. The candidate is BEHIND the raw market on the target
cell (-0.002807, game-clustered CI95 [-0.006055, +0.000440], crossing zero) and the bar
(+0.004) is NOT met.** So are both nulls. **No prereg DRAFT was written.** Uncharged:
no prereg seal, no ledger read, no ledger write, no K consumed. **SINGLE-WINDOW**
(one corpus, the S86 SCREEN side, NBA 2024-11-12..2026-06-10). Verdict side never read.

Calibration measurement only. No dollar, ROI, profit or edge claim. No bar moved (Q3:
`IMPROVEMENT_BAR = 0.004`, asserted byte-identical by the per-file test). ASCII only.

Module: `scripts/platformkit/eval_gate/s94_nba_early_shrinkage.py` (296 LOC)
Test: `python -m pytest tests/platformkit/ingame/test_s94_nba_early_shrinkage.py -q` = **6 passed**
Archive (Q9): `data/cache/eval_gate/s94_nba_early_shrinkage_2026-09-03.json` +
`...csv` (192,635 per-tick rows: fold, cell, y, market, model, w_c, all three fitted
probabilities, all four losses, both paired-loss differentials, `cluster_id` = game).

---

## 0. STEP 0 -- premise re-measured first (Q8)

Recomputed independently from the S86 archive
`data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv` (232,951 ticks / 797 games).

| the row says | measured 2026-09-03 | verdict |
|---|---|---|
| P1-P2 close, > 12 min: 27,591 screen ticks / 20,631 informative | 27,591 ticks / 797 games; 20,631 informative on S86's market-only rule; 23,256 informative under `tick_informative.flag_ticks` (market OR model moved) | CONFIRMED |
| market ECE 0.056-0.065 in those cells | P1|close **0.055593** (identical to the S86 JSON), P2|close **0.064157** vs the memo's 0.064718 -- see the note below | CONFIRMED |
| one-directional: 0.4-0.5 realises ~0.55, 0.8-0.9 ~0.73 | P1 0.4-0.5 bin 1,678 ticks mean 0.4478 realises **0.5501**; P2 0.4-0.5 bin 2,019 mean 0.4501 realises **0.5612**; P1 0.8-0.9 mean 0.8451 realises **0.7255**; P2 0.8-0.9 mean 0.8378 realises **0.7328** | CONFIRMED |
| the cell is P1-P2 x close x > 12 min | every P1 and P2 close tick has rem > 12 by construction (rem = (4 - period) * 12 + clock), so `P1|close` == `P1|close|rem_gt12` | CONFIRMED |

Reproduced bin tables (market prices, 10 equal-width `calib_decomp.bin_edges(10)` bins):

```
P1 | close_le5  n 14,047                    P2 | close_le5  n 13,544
 bin      n    mean    obs      gap          bin      n    mean    obs      gap
 0.0-0.1   151 0.0794 0.0000 -0.0794         0.0-0.1    33 0.0804 0.0000 -0.0804 (INSUFFICIENT)
 0.1-0.2   669 0.1591 0.1510 -0.0081         0.1-0.2   498 0.1683 0.1406 -0.0277
 0.2-0.3  1232 0.2561 0.2873 +0.0313         0.2-0.3  1005 0.2536 0.2129 -0.0407
 0.3-0.4  1736 0.3509 0.3975 +0.0466         0.3-0.4  1999 0.3520 0.4252 +0.0732
 0.4-0.5  1678 0.4478 0.5501 +0.1023         0.4-0.5  2019 0.4501 0.5612 +0.1111
 0.5-0.6  2072 0.5513 0.5994 +0.0481         0.5-0.6  2150 0.5544 0.5991 +0.0447
 0.6-0.7  2427 0.6532 0.6403 -0.0129         0.6-0.7  2589 0.6516 0.6562 +0.0047
 0.7-0.8  2158 0.7471 0.6826 -0.0645         0.7-0.8  2019 0.7461 0.6365 -0.1097
 0.8-0.9  1603 0.8451 0.7255 -0.1196         0.8-0.9  1059 0.8378 0.7328 -0.1050
 0.9-1.0   321 0.9229 0.9564 +0.0335         0.9-1.0   173 0.9181 0.9191 +0.0009
```

Premise **HOLDS** -- the miscalibration reproduces in shape, direction and magnitude.

**One honest discrepancy found while reproducing (A2).** Eight of the ten bins match the
S86 JSON tick-for-tick; the 0.2-0.3 / 0.3-0.4 pair does not (P1 1,232/1,736 here vs
1,198/1,770 stored; P2 1,005/1,999 vs 961/2,043), and market ECE moves by 0.0006. Cause,
measured: `nba_checkpoints_full.parquet` stores that price as `0.30000000000000004`
(480 rows) while `s86_..._2026-09-03.csv` writes it as `0.3`, and `calib_decomp.bin_index`
splits exactly at the `np.linspace` edge `0.30000000000000004`. It is a CSV float-rendering
artifact, not a data difference: 34 (P1) / 44 (P2) ticks cross one bin edge. Brier, the DM
differentials and every number in section 3 below are unaffected at the 1e-16 level, since
none of them is bin-counted. Recorded in `load_screen`'s docstring so the next reader of
the S86 archive does not re-derive it.

## 1. Method

Candidate, per tick:

```
p = sigmoid((1 - w_c) * logit(market) + w_c * logit(prior_state))
```

`prior_state` is the S86 `model` column -- `price_checkpoint(p0_asof, score, period, clock)`
over `ratings.replay(games, until=game_date)`, strictly before the tick's own game date --
so nothing new is fit on outcomes except the scalar `w_c`.

`c` is the S86 phase cell: period bucket x |margin| bucket x time-remaining bucket
(27 cells present). `w_c` is chosen on the TRAIN rows of that cell only, as the grid point
in [0, 1] (step 0.005) minimising the cell's tick-weighted Brier. A cell with fewer than
200 train ticks keeps `w_c = 0`, i.e. the raw market line.

Two NULL arms, fit on the **identical** train rows:

- **recal** -- one global unregularised logistic recalibration on `[1, logit(market)]`.
- **cellrecal** -- the same recalibration fit **per cell** (falling back to the global fit
  for a cell under 200 train ticks). This is the arm that decides the question: if the
  candidate cannot beat it, the effect is recalibration, not shrinkage.

Design: expanding walk-forward by game-first date on the S86 SCREEN side; 5 held-out
blocks of roughly equal tick count after a train-only seed block; **purged by game**
(train games asserted disjoint from test games) and a **1-day embargo** (`train_date_max <
embargo_cut <= test_start`, asserted per fold). 192,635 ticks / 673 games are scored
(the 40,316-tick seed block is train-only and never scored).

| fold | test window | train ticks / games | test ticks / games |
|---|---|---|---|
| 1 | 2024-12-09..2025-01-25 | 38,698 / 118 | 38,179 / 138 |
| 2 | 2025-01-27..2025-11-04 | 78,495 / 262 | 38,838 / 123 |
| 3 | 2025-11-05..2025-12-26 | 116,246 / 381 | 38,628 / 137 |
| 4 | 2026-01-02..2026-02-25 | 155,961 / 522 | 38,280 / 135 |
| 5 | 2026-02-26..2026-06-10 | 193,353 / 654 | 38,710 / 140 |

The per-file test plants a known blend and checks `fit_w` recovers it, checks the
purge/embargo assertions hold, checks a sub-threshold cell degenerates to the raw market,
and flips the **last fold's own held-out outcomes** to prove the candidate on that fold does
not move by a single bit.

## 2. Result -- held-out folds, tick-weighted

Improvement is `loss(arm) - loss(candidate)`; positive means the candidate lost less.
CI95 is Diebold-Mariano clustered by game.

### Target cell -- P1-P2 | close_le5 | rem_gt12

n 23,561 ticks / 673 games / 19,776 informative / **n_eff 875.6** (ICC by game 0.7618,
design effect 26.91).

| arm | Brier | ECE | candidate improvement vs it | DM CI95 |
|---|---|---|---|---|
| raw market | **0.220173** | 0.059651 | **-0.002807** | [-0.006055, +0.000440] |
| recal null (global) | 0.221658 | 0.051951 | -0.001322 | [-0.004217, +0.001574] |
| cellrecal null (per cell) | 0.226244 | 0.028750 | +0.003264 | [-0.000978, +0.007507] |
| **candidate (shrinkage)** | **0.222980** | 0.053518 | -- | -- |

**Bar +0.004 vs the raw market: NOT MET (-0.002807, and the CI includes zero).** The
candidate beats only the per-cell recalibration null, and that null is itself the worst arm
of the four. `prereg_draft_warranted = False`; **no prereg DRAFT was written.**

Split by period (both fail the same way):

| cell | n | inf | n_eff | market | cand | vs market | DM CI95 |
|---|---|---|---|---|---|---|---|
| P1 close > 12 min | 11,890 | 10,851 | 756.4 | 0.216076 | 0.217049 | -0.000973 | [-0.002703, +0.000758] |
| P2 close > 12 min | 11,671 | 9,037 | 600.5 | 0.224346 | 0.229022 | -0.004676 | [-0.009767, +0.000414] |

### Overall (all 27 cells, all folds)

n 192,635 ticks / 673 games / 78,761 informative / n_eff 4,029.3 (ICC 0.1641, deff 47.81).

| arm | Brier | ECE | candidate improvement vs it | DM CI95 |
|---|---|---|---|---|
| raw market | **0.078611** | 0.012746 | -0.000243 | [-0.000999, +0.000513] |
| recal null | 0.078974 | 0.010513 | +0.000121 | [-0.000772, +0.001013] |
| cellrecal null | 0.079952 | 0.006252 | +0.001098 | [+0.000050, +0.002147] |
| candidate | 0.078854 | 0.012906 | -- | -- |

## 3. Is w stable across folds? No.

`w_c` on the two target cells, refit on each fold's train rows:

| fold | P1 close > 12 min | P2 close > 12 min |
|---|---|---|
| 1 | 0.365 | 0.885 |
| 2 | 0.000 | 0.000 |
| 3 | 0.130 | 0.185 |
| 4 | 0.105 | 0.185 |
| 5 | 0.225 | 0.450 |
| **spread** | **0.000 - 0.365** (mean 0.165) | **0.000 - 0.885** (mean 0.341) |

An 0-to-0.885 swing on the very cell the arm was built for is the whole story: there is no
stable weight to learn. Two other cells behave the same way (`P3|close|rem_gt12` 0.165-0.825,
`P4|blowout|rem_02_06` 0.300-1.000); the only cells whose `w` is stable are ones where the
prior contributes nothing anyway (`P1|blowout` 0.000-0.090). The full 27-cell spread table
is in the artifact under `w_spread_across_folds`.

## 4. What this actually says

The S86 measurement stands: **the in-play line is measurably miscalibrated early in close
games, and the miss is one-directional -- the line overreacts to early margins.** S94 tested
the natural repair and it does not hold up out of sample.

1. **Shrinkage toward the as-of prior does not repair it.** The candidate is behind the raw
   market on the target cell and the CI crosses zero. The fitted weight is not stable across
   folds, so the fold-1 weight (0.885) is fitting that window, not a property of the market.
2. **Neither does recalibration.** The global recalibration null is ALSO behind the raw
   market (0.221658 vs 0.220173). The reliability gap measured in-sample on all 797 screen
   games does not survive being fit on a past window and applied forward.
3. **The ECE / Brier divergence is textbook.** The per-cell recalibration null more than
   halves the target cell's ECE (0.0597 -> 0.0288) while posting the WORST Brier of all four
   arms (0.2262). `scoring.ece`'s own docstring warns not to optimise ECE directly; this is a
   measured instance. Any future arm on this defect must be scored on Brier, with ECE as a
   diagnostic only.
4. **The honest reading of the defect.** A one-directional reliability gap of 0.056-0.065 on
   a cell whose Brier is 0.22 is small relative to the noise at n_eff ~876, and the ICC in
   this cell is 0.76 -- 23,561 ticks are worth about 876 independent observations. The gap is
   real as a measurement and not, on this corpus, a stable conditioning rule.

An honest NULL is a success. Nothing was charged, so nothing is spent.

## 5. Invariants

- No prereg seal was created and none was needed (nothing scored is charged) -- Q1 not engaged.
- The FWER ledger was neither read nor written; no K consumed -- Q2 not engaged.
- `IMPROVEMENT_BAR = 0.004` byte-identical to the register row, asserted by the test -- Q3.
- Walk-forward, purged by game, 1-day embargo, every fit on TRAIN rows only, asserted per
  fold and proved by the outcome-flip test -- Q4.
- One corpus (the S86 screen side): labelled **SINGLE-WINDOW** -- Q5.
- Calibration language only; none of the retracted figures appears -- Q6.
- Per-tick paired-loss series archived beside the summary, with `cluster_id`, both
  differentials and the fold, so every CI here is recomputable from the artifact alone -- Q9.

**NOT VERIFIED** -- this memo is the lane's own report; a verifier has not yet re-run it.
