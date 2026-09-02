# S97 -- the NBA in-play line and the as-of state price as two noisy sensors

Row: S86 priced every screen-side tick with an as-of prior and found the market itself
miscalibrated early in close games. S94 tried a fixed per-cell shrinkage between the two
series and found no stable weight. S97 asks the next question: stop picking a weight and
FILTER -- treat the market tick series and the prior series as two noisy readings of one
latent win probability, and let a Kalman filter set the weight tick by tick.

Verdict: **NULL on Brier and a measured NEGATIVE on the interval claim.** The posterior is
statistically indistinguishable from the raw line (overall +0.000003, game-clustered CI95
[-0.0000091, +0.0000148]); the bar (+0.004) is **NOT MET** by three orders of magnitude. The
novel deliverable -- the interval -- fails loudly and in a way worth recording: the filter's
nominal **90 pct intervals achieve 8 pct grouped coverage overall** (P1 19 pct, P2 12 pct,
P3 22 pct, P4 8 pct, OT 0 pct). **No prereg DRAFT was written.** Uncharged: no prereg seal,
no ledger read, no ledger write, no K consumed. **SINGLE-WINDOW** (one corpus, the S86 SCREEN
side, NBA 2024-11-12..2026-06-10). Verdict side never read.

Calibration measurement only. No dollar, ROI or profit claim. No bar moved (Q3:
`IMPROVEMENT_BAR = 0.004`, `NOMINAL_COVERAGE = 0.90`, `COVERAGE_TOL = 0.02`, all asserted
byte-identical by the per-file test, and the bar is asserted equal to S94's). ASCII only.

Module: `scripts/platformkit/eval_gate/s97_nba_sensor_fusion.py` (300 LOC)
Test: `python -m pytest tests/platformkit/ingame/test_s97_nba_sensor_fusion.py -q` = **9 passed**
Archive (Q9): `data/cache/eval_gate/s97_nba_sensor_fusion_2026-09-03.json` +
`...csv` (192,635 per-tick rows: fold, cell, phase, y, market, prior, **posterior mean and
posterior variance on the logit**, lo90/hi90, both nulls, all four losses, all three paired-loss
differentials, `cluster_id` = game).

---

## 0. STEP 0 -- premise re-measured first (Q8), and the stop rule

The row rests on one premise: that the two series are not the same sensor. Measured
independently on all 232,951 screen ticks / 797 games of
`data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv`, per S86 phase cell. Innovations are
within-game first differences of the logit; `corr_inn` is the cross-correlation of the two
sensors' innovations, `corr_lvl` of their levels; `share>0.1` is the share of ticks where the
market probability and the prior probability differ by more than 0.1.

| cell | n | games | var(dz market) | var(dz prior) | prior resid MS vs y | market resid MS vs y | corr_inn | corr_lvl | share>0.1 |
|---|---|---|---|---|---|---|---|---|---|
| P4\|blowout_gt12\|rem_le02 | 49171 | 379 | 0.0208 | 0.0162 | 0.0000 | 0.0006 | 0.2232 | 0.9977 | 0.0031 |
| P4\|mid_06_12\|rem_le02 | 41423 | 355 | 0.0645 | 0.2502 | 0.0004 | 0.0004 | 0.3735 | 0.9983 | 0.0007 |
| P4\|close_le5\|rem_le02 | 29739 | 314 | 0.1852 | 1.1157 | 0.0123 | 0.0122 | 0.3896 | 0.9948 | 0.0380 |
| P1\|close_le5\|rem_gt12 | 14047 | 797 | 0.0133 | 0.0553 | 0.2293 | 0.2191 | **0.4657** | 0.8403 | **0.3614** |
| P2\|close_le5\|rem_gt12 | 13544 | 621 | 0.0149 | 0.0542 | 0.2298 | 0.2265 | **0.5495** | 0.8337 | **0.3481** |
| P2\|mid_06_12\|rem_gt12 | 12799 | 716 | 0.0177 | 0.0645 | 0.2102 | 0.1963 | 0.5227 | 0.9248 | 0.4193 |
| P3\|mid_06_12\|rem_gt12 | 8326 | 654 | 0.0432 | 0.1624 | 0.1815 | 0.1721 | 0.5389 | 0.9368 | 0.4024 |
| P2\|blowout_gt12\|rem_gt12 | 8307 | 391 | 0.0280 | 0.1303 | 0.1166 | 0.1029 | 0.3164 | 0.9713 | 0.2670 |
| P3\|close_le5\|rem_gt12 | 8299 | 519 | 0.0356 | 0.1143 | 0.2235 | 0.2269 | 0.6052 | 0.8330 | 0.3227 |
| P3\|blowout_gt12\|rem_gt12 | 8088 | 464 | 0.0921 | 0.4488 | 0.0642 | 0.0612 | 0.2777 | 0.9722 | 0.1335 |
| P1\|mid_06_12\|rem_gt12 | 6935 | 688 | 0.0183 | 0.0703 | 0.2123 | 0.1937 | 0.5520 | 0.8873 | 0.4313 |
| OT\|close_le5\|rem_le02 | 5667 | 41 | 0.1904 | 1.4555 | 0.0734 | 0.0119 | 0.0652 | 0.6092 | 0.8991 |
| P4\|blowout_gt12\|rem_06_12 | 5069 | 438 | 0.1925 | 0.9733 | 0.0257 | 0.0253 | 0.2776 | 0.9801 | 0.0247 |
| P4\|mid_06_12\|rem_06_12 | 4072 | 505 | 0.0924 | 0.3679 | 0.1510 | 0.1394 | 0.5546 | 0.9687 | 0.3298 |
| P4\|close_le5\|rem_06_12 | 3801 | 387 | 0.0753 | 0.2060 | 0.2331 | 0.2316 | 0.6378 | 0.8717 | 0.3360 |
| P4\|blowout_gt12\|rem_02_06 | 3339 | 416 | 0.3317 | 1.7299 | 0.0036 | 0.0058 | 0.3231 | 0.9855 | 0.0087 |
| P4\|close_le5\|rem_02_06 | 2511 | 335 | 0.1535 | 0.4849 | 0.2354 | 0.2307 | 0.6099 | 0.9131 | 0.3803 |
| P4\|mid_06_12\|rem_02_06 | 2467 | 409 | 0.2736 | 1.4744 | 0.0779 | 0.0712 | 0.4717 | 0.9694 | 0.1654 |
| OT\|mid_06_12\|rem_le02 | 1968 | 19 | 0.1156 | 1.0157 | 0.0059 | 0.0009 | 0.1522 | 0.8581 | 0.0864 |
| P1\|blowout_gt12\|rem_gt12 | 1310 | 178 | 0.0331 | 0.1175 | 0.1623 | 0.1387 | 0.4646 | 0.9482 | 0.3649 |
| P3\|blowout_gt12\|rem_06_12 | 683 | 255 | 0.0953 | 0.1985 | 0.0213 | 0.0203 | 0.1764 | 0.9521 | 0.0469 |
| P3\|mid_06_12\|rem_06_12 | 443 | 223 | 0.0585 | 0.0918 | 0.1665 | 0.1584 | 0.4753 | 0.9612 | 0.4176 |
| P3\|close_le5\|rem_06_12 | 441 | 206 | 0.0339 | 0.0522 | 0.2406 | 0.2347 | 0.5561 | 0.8916 | 0.2290 |
| OT\|close_le5\|rem_02_06 | 333 | 43 | 0.2064 | 0.5629 | 0.2481 | 0.2462 | 0.6579 | 0.8901 | 0.3514 |
| OT\|blowout_gt12\|rem_le02 | 134 | 1 | 0.0397 | 0.2779 | 0.0000 | 0.0000 | 0.0075 | -0.3441 | 0.0000 |
| OT\|mid_06_12\|rem_02_06 | 34 | 10 | 0.5619 | 2.4072 | 0.2790 | 0.2558 | 0.5255 | 0.9807 | 0.1471 |
| OT\|blowout_gt12\|rem_02_06 | 1 | 1 | -- | -- | 0.9998 | 0.9545 | -- | -- | 0.0000 |

**Stop rule NOT triggered.** The row's stop condition was innovation correlation above 0.98 in
every cell; the measured maximum is **0.6579** and the minimum 0.0075, so **0 of 27 cells** are
collinear and the two series carry genuinely different tick-to-tick information. Pooled, the
market and the prior differ by more than 0.1 on **16.79 pct** of all screen ticks, and by more
than 0.1 on **34.8-43.1 pct** of ticks in the live early cells. The premise HOLDS -- proceed.

Two facts in that table set up everything below. First, the prior's innovation variance is
**3-5x the market's in every live cell** -- the state repricer jumps around far more than the
line does. Second, level correlation is 0.99+ in the decided P4 cells purely because the state
has already settled the game there.

## 1. The filter, and how q and r were fitted

Per game, in tick order, resetting at every game boundary:

```
predict   x_t|t-1 = x_t-1,            P_t|t-1 = P_t-1 + q_c
update 1  with z_market,t = logit(market),  variance r_m,c
update 2  with z_prior,t  = logit(prior),   variance r_p,c
arm       p_t = sigmoid(x_t|t),  interval = sigmoid(x_t|t -/+ 1.6449 * sqrt(P_t|t))
```

`c` is the tick's S86 phase cell. The initial state is diffuse (`x = 0`, `P = 100`), so the
first tick of every game is set by its own two observations and nothing else.

**Method, stated as the row requires: INNOVATION VARIANCE (method of moments), not maximum
likelihood.** For a local-level model observed with noise, the first difference of the observed
series has `gamma0 = q + 2r` and `gamma1 = -r`, so both `q_c` and `r_m,c` are read off the
MARKET series' own within-game innovations on TRAIN rows: `r_m = -gamma1`, `q = gamma0 + 2*gamma1`.
The prior's observation variance is the two-sensor discrepancy net of the market's, since
`E[(z_p - z_m)^2] = r_p + r_m` under independent sensor noise: `r_p = E[(z_p - z_m)^2] - r_m`.
The MEAN SQUARE is used rather than the variance on purpose -- a prior with a systematic offset
is charged for that offset and downweighted, never trusted. **Nothing in the noise fit reads an
outcome.** All three are floored at 1e-4; a cell with fewer than 200 train ticks inherits the
pooled estimate.

Design: expanding walk-forward by game-first date on the S86 SCREEN side; 5 held-out blocks
after a train-only seed block; **purged by game** (asserted disjoint) and a **1-day embargo**
(`train_date_max < embargo_cut <= test_start`, asserted per fold). 192,635 ticks / 673 games
are scored; the 40,316-tick seed block is train-only and never scored. The fold windows are
byte-identical to S94's, which is the point -- the two rows are scored on the same rows.

| fold | test window | train ticks / games | test ticks / games | pooled q | pooled r_m | pooled r_p | null-2 w |
|---|---|---|---|---|---|---|---|
| 1 | 2024-12-09..2025-01-25 | 38,698 / 118 | 38,179 / 138 | 0.070118 | 0.008926 | 25.7726 | 0.285 |
| 2 | 2025-01-27..2025-11-04 | 78,495 / 262 | 38,838 / 123 | 0.070258 | 0.004367 | 24.0399 | 0.050 |
| 3 | 2025-11-05..2025-12-26 | 116,246 / 381 | 38,628 / 137 | 0.071070 | 0.003488 | 23.9906 | 0.090 |
| 4 | 2026-01-02..2026-02-25 | 155,961 / 522 | 38,280 / 135 | 0.072599 | 0.002121 | 23.4859 | 0.115 |
| 5 | 2026-02-26..2026-06-10 | 193,353 / 654 | 38,710 / 140 | 0.073057 | 0.000872 | 23.3094 | 0.250 |

Fitted `(q, r_m, r_p)` per cell per fold, for the cells that matter (the full 27-cell x 5-fold
table is in the artifact under `folds[].noise_by_cell`):

| cell | fold 1 | fold 2 | fold 3 | fold 4 | fold 5 |
|---|---|---|---|---|---|
| P1\|close_le5\|rem_gt12 | 0.0108, 0.0032, 0.2699 | 0.0116, 0.0023, 0.3115 | 0.0114, 0.0024, 0.3266 | 0.0112, 0.0018, 0.3094 | 0.0108, 0.0015, 0.3227 |
| P2\|close_le5\|rem_gt12 | 0.0158, 0.0007, 0.2134 | 0.0145, 0.0008, 0.2556 | 0.0139, 0.0012, 0.2563 | 0.0141, 0.0007, 0.2473 | 0.0140, 0.0005, 0.2619 |
| P3\|close_le5\|rem_gt12 | 0.0359, 0.0003, 0.1760 | 0.0348, 0.0016, 0.1925 | 0.0351, 0.0011, 0.2032 | 0.0347, 0.0010, 0.2008 | 0.0342, 0.0009, 0.2186 |
| P2\|mid_06_12\|rem_gt12 | 0.0143, 0.0023, 0.5181 | 0.0169, 0.0011, 0.5029 | 0.0163, 0.0017, 0.5168 | 0.0170, 0.0010, 0.5108 | 0.0164, 0.0008, 0.5363 |
| P4\|close_le5\|rem_le02 | 0.1305, 0.0272, 42.401 | 0.1428, 0.0188, 40.543 | 0.1611, 0.0119, 39.778 | 0.1646, 0.0093, 39.482 | 0.1687, 0.0058, 39.124 |
| P4\|blowout_gt12\|rem_le02 | 0.0219, 0.0001, 41.066 | 0.0162, 0.0001, 39.803 | 0.0175, 0.0006, 39.998 | 0.0243, 0.0001, 39.992 | 0.0230, 0.0001, 39.952 |

Across all 127 cell-folds: `q` 0.0108-0.3565, `r_m` 0.0001-0.0449 (**at the 1e-4 floor in 23 of
127**), `r_p` 0.151-42.40. **In every cell `r_p / r_m` is between 60 and 400,000.** Unlike S94's
`w_c` (which swung 0.000-0.885 across folds on its own target cell), the fitted noise ratios are
stable fold to fold -- the filter's problem is not instability, it is what the stable answer says.

Two NULL arms fitted on the identical train rows: **recal**, the S94 global unregularised
logistic recalibration on `[1, logit(market)]`; and **blend1**, the S94 shrinkage form collapsed
to a SINGLE global weight `w` (fitted 0.050-0.285 across folds).

## 2. Result -- held-out folds, tick-weighted

Improvement is `loss(arm) - loss(posterior)`; positive means the posterior lost less. CI95 is
Diebold-Mariano clustered by game.

### Overall (all 27 cells, all folds) -- this is the gate slice

n 192,635 ticks / 673 games / **78,761 informative** / n_eff 68,148.7 (ICC by game 0.0064,
design effect 2.83). Informative-only DM CI95 [-0.0000214, +0.0000317], p 0.704.

| arm | Brier | ECE | posterior improvement vs it | DM CI95 |
|---|---|---|---|---|
| raw market | **0.078611** | 0.012746 | **+0.000003** | [-0.0000091, +0.0000148] |
| recal null (global) | 0.078974 | 0.010513 | +0.000366 | [-0.000288, +0.001020] |
| blend1 null (single w) | 0.078721 | 0.013938 | +0.000113 | [-0.000466, +0.000692] |
| **posterior (Kalman)** | **0.078608** | 0.012749 | -- | -- |

**Bar +0.004 vs the raw market: NOT MET (+0.000003, and the CI includes zero).** The posterior
is nominally ahead of both nulls but both of those CIs also include zero, so all three
comparisons are null. `prereg_draft_warranted = False`; **no prereg DRAFT was written.**

### The S94 target cell -- P1-P2 | close_le5 | rem_gt12, reported for continuity

n 23,561 ticks / 673 games / 19,776 informative / n_eff 10,861.3.

| arm | Brier | ECE | posterior improvement vs it | DM CI95 |
|---|---|---|---|---|
| raw market | **0.220173** | 0.059651 | **+0.000017** | [-0.0000338, +0.0000681] |
| recal null | 0.221658 | 0.051951 | +0.001503 | [-0.000564, +0.003569] |
| blend1 null | 0.220609 | 0.056187 | +0.000454 | [-0.001117, +0.002025] |
| posterior | 0.220156 | 0.059546 | -- | -- |

The cell where S94's shrinkage was BEHIND the line by -0.002807 is the cell where S97's filter
is level with it to five decimal places. The filter does not repeat S94's damage; it also does
not do anything.

### Per cell (n >= 1000), posterior vs raw market, sorted

Every improvement is smaller than 0.00011 in absolute value. One cell has a CI excluding zero
(`P3|close_le5|rem_gt12`, +0.000099, CI [+0.000035, +0.000164]) -- a 0.0001 Brier gain on one of
20 cells is a multiplicity artifact, is 40x below the bar, and is recorded here only so it is
not later mistaken for a finding.

| cell | n | n_eff | market | posterior | improvement | DM CI95 |
|---|---|---|---|---|---|---|
| P4\|close_le5\|rem_06_12 | 3130 | 876.0 | 0.232224 | 0.232116 | +0.000108 | [-0.000004, +0.000220] |
| P3\|close_le5\|rem_gt12 | 6990 | 1732.8 | 0.227061 | 0.226962 | +0.000099 | [+0.000035, +0.000164] |
| P1\|close_le5\|rem_gt12 | 11890 | 7326.5 | 0.216076 | 0.216046 | +0.000030 | [-0.000050, +0.000110] |
| P1\|blowout_gt12\|rem_gt12 | 1126 | 652.8 | 0.126808 | 0.126784 | +0.000025 | [-0.000063, +0.000112] |
| P2\|blowout_gt12\|rem_gt12 | 7104 | 3762.0 | 0.105339 | 0.105327 | +0.000012 | [-0.000020, +0.000045] |
| P4\|blowout_gt12\|rem_02_06 | 2893 | 2893.0 | 0.006639 | 0.006632 | +0.000007 | [-0.000008, +0.000023] |
| P2\|close_le5\|rem_gt12 | 11671 | 4739.7 | 0.224346 | 0.224342 | +0.000004 | [-0.000034, +0.000042] |
| P4\|blowout_gt12\|rem_le02 | 42266 | 39229.3 | 0.000685 | 0.000683 | +0.000002 | [-0.000001, +0.000005] |
| P4\|blowout_gt12\|rem_06_12 | 4412 | 4398.1 | 0.027790 | 0.027788 | +0.000002 | [-0.000001, +0.000004] |
| P4\|mid_06_12\|rem_le02 | 32473 | 998.1 | 0.000396 | 0.000396 | +0.000001 | [-0.000000, +0.000001] |
| OT\|mid_06_12\|rem_le02 | 1837 | 38.0 | 0.000995 | 0.000998 | -0.000003 | [-0.000009, +0.000003] |
| P2\|mid_06_12\|rem_gt12 | 10574 | 6594.8 | 0.195890 | 0.195897 | -0.000007 | [-0.000045, +0.000031] |
| P1\|mid_06_12\|rem_gt12 | 5860 | 5730.3 | 0.195310 | 0.195319 | -0.000008 | [-0.000025, +0.000008] |
| P3\|blowout_gt12\|rem_gt12 | 6865 | 1957.4 | 0.063975 | 0.063984 | -0.000009 | [-0.000025, +0.000007] |
| P4\|mid_06_12\|rem_06_12 | 3422 | 2181.8 | 0.144208 | 0.144223 | -0.000016 | [-0.000035, +0.000004] |
| P4\|close_le5\|rem_le02 | 22338 | 5746.2 | 0.013210 | 0.013229 | -0.000019 | [-0.000053, +0.000015] |
| P3\|mid_06_12\|rem_gt12 | 7053 | 3859.8 | 0.171562 | 0.171585 | -0.000023 | [-0.000075, +0.000030] |
| P4\|mid_06_12\|rem_02_06 | 2030 | 923.4 | 0.069222 | 0.069246 | -0.000024 | [-0.000096, +0.000047] |
| OT\|close_le5\|rem_le02 | 4817 | 3946.7 | 0.012898 | 0.012957 | -0.000060 | [-0.000139, +0.000020] |
| P4\|close_le5\|rem_02_06 | 2071 | 733.1 | 0.223545 | 0.223636 | -0.000091 | [-0.000334, +0.000151] |

## 3. Interval coverage -- the deliverable, and it is a NEGATIVE

**The literal reading of the claim is degenerate and is recorded as such:** a binary outcome
can never lie inside a probability interval, so "share of outcomes inside the 90 pct interval"
is 0.0 by construction and measures nothing. The measurable form, which the module implements
and the artifact stores, is grouped: within a phase, ticks are cut into equal-count groups
(>= 400 ticks each, capped at 50 groups) ordered by posterior mean, and a group is COVERED when
its realised outcome frequency lies inside that group's mean `[lo90, hi90]`. `n_groups` is the
resolution of the share and is reported with it.

| phase | n | groups | group size | coverage | deviation from 0.90 | mean interval width | mean miss distance |
|---|---|---|---|---|---|---|---|
| P1 | 18,876 | 47 | 401 | **0.1915** | -0.7085 | 0.0221 | 0.0407 |
| P2 | 29,349 | 50 | 586 | **0.1200** | -0.7800 | 0.0179 | 0.0423 |
| P3 | 22,259 | 50 | 445 | **0.2200** | -0.6800 | 0.0174 | 0.0208 |
| P4 | 115,035 | 50 | 2,300 | **0.0800** | -0.8200 | 0.0033 | 0.0023 |
| OT | 7,116 | 17 | 418 | **0.0000** | -0.9000 | 0.0049 | 0.0047 |
| ALL | 192,635 | 50 | 3,852 | **0.0800** | -0.8200 | 0.0091 | 0.0106 |

**Not one phase is within the 2-point tolerance; every phase misses by 68 to 90 points, all in
the same direction.** The filter's posterior variance is wildly over-confident. The mean miss
distance (how far outside the interval the group frequency actually lands) is 0.0106 overall
against a mean interval width of 0.0091 -- the truth sits roughly one whole interval width
outside the interval.

**How much wider would they have to be?** In-sample diagnostic on the scored rows (a
size-of-the-gap number, NOT an arm and NOT scored -- it is fitted on the very rows it is
evaluated on): scaling the posterior standard deviation on the logit by a constant `k`,

| phase | coverage at k=1 | width at k=1 | smallest k reaching 0.90 | coverage there | width there |
|---|---|---|---|---|---|
| P1 | 0.191 | 0.0221 | **15** | 0.936 | 0.3152 |
| P2 | 0.120 | 0.0179 | **15** | 0.900 | 0.2639 |
| P3 | 0.220 | 0.0174 | none up to k=200 | -- | -- |
| P4 | 0.080 | 0.0033 | none up to k=200 | -- | -- |
| OT | 0.000 | 0.0049 | none up to k=200 | -- | -- |
| ALL | 0.080 | 0.0091 | none up to k=200 | -- | -- |

Early in games the deficit is a pure scale error: the posterior standard deviation is about
**15x too small**, and a 90 pct interval that honestly covered would be about 0.26-0.32 wide in
probability -- which is to say, at that phase the latent win probability is barely pinned down
at all. Late in games no scalar inflation fixes it, because there the posterior variance is so
small (r_m at its floor) that even a 200x-wider interval is still narrower than the residual
bias between the group's price and its realised frequency. The deficit there is a location
error, not a width error.

## 4. Why the filter did nothing -- the mechanism, measured

| phase | n | mean \|posterior - market\| | p95 | share moved > 0.01 | mean \|prior - market\| | mean posterior sd (logit) |
|---|---|---|---|---|---|---|
| P1 | 18,876 | 0.001604 | 0.006215 | 0.0123 | 0.098634 | 0.034277 |
| P2 | 29,349 | 0.000908 | 0.003270 | 0.0024 | 0.089168 | 0.033274 |
| P3 | 22,259 | 0.000725 | 0.002898 | 0.0022 | 0.076977 | 0.042884 |
| P4 | 115,035 | 0.000208 | 0.000762 | 0.0034 | 0.011687 | 0.042426 |
| OT | 7,116 | 0.000412 | 0.001677 | 0.0111 | 0.173057 | 0.109032 |
| ALL | 192,635 | **0.000519** | 0.002729 | 0.0043 | **0.045517** | 0.042746 |

The posterior sits on average **0.0005** away from the line while the prior sits **0.0455** away
-- the filter puts about one part in ninety of its weight on the prior. That is not a bug, it is
what the fitted noise says: `r_p / r_m` is 60 to 400,000, so the prior is admitted almost not at
all. And `r_m` itself is near zero because the in-play line's own innovations have essentially no
lag-1 mean reversion -- **the line behaves like a martingale, which is exactly the series a
local-level filter has nothing to smooth.** A Kalman filter can only add information when at
least one sensor is noisy relative to the state's own drift; here the sharp sensor is not
measurably noisy and the noisy sensor is not measurably sharp.

That is the honest content of this row. The two sensors are NOT collinear (section 0 proves it),
so information-in-principle exists; but under a linear-Gaussian random-walk model with
moment-fitted variances, none of it is recoverable. The disagreement between the two series is
not sensor noise around a common latent state -- it is the prior being wrong in a way the model
has no term for.

## 5. Independent reproduction of the incumbent numbers (A2)

Scored on the same rows through a separately written module, the shared quantities come out
bit-identical to S94's published table:

| quantity | S94 published | S97 measured |
|---|---|---|
| scored ticks / games | 192,635 / 673 | 192,635 / 673 |
| overall Brier, raw market | 0.078611 | 0.078611 |
| overall Brier, global recal null | 0.078974 | 0.078974 |
| target-cell n / informative | 23,561 / 19,776 | 23,561 / 19,776 |
| target-cell Brier, raw market | 0.220173 | 0.220173 |
| target-cell Brier, global recal null | 0.221658 | 0.221658 |
| target-cell market ECE | 0.059651 | 0.059651 |
| fold windows and train/test sizes | 5 folds, 2024-12-09..2026-06-10 | identical row for row |

**One number is deliberately NOT comparable: `n_eff`.** S94 reports 875.6 on the target cell and
S97 reports 10,861.3 on the same rows. Both are correct: ESS is computed on the paired loss
DIFFERENTIAL, and S97's differential is near zero everywhere, so its by-game ICC collapses
(0.034 here vs 0.762 there) and the design effect with it. **A near-identical arm mechanically
inflates its own n_eff.** The large n_eff in section 2 is therefore not evidence of power to
detect a real difference; it is a restatement of the fact that there is no difference. Read the
CI, not the ESS.

## 6. Rails self-check (VERIFIER_CONTRACT B + Q)

- **B1** no circular metric -- no row is excluded after scoring; every screen tick in a test
  block is scored, and the only unscored rows are the train-only seed block named in section 1.
- **B2** additive -- one new module, one new test, one new archive stem. Nothing renamed,
  removed or re-signatured; S94 and S86 are imported read-only.
- **B7** no head-slice -- all five held-out blocks span the corpus end to end, and the earliest
  block is train-only rather than the scored one.
- **B8** no self-fit as independent -- q, r and both nulls are fitted on TRAIN rows only, proved
  by the outcome-flip test (flipping the last fold's own held-out outcomes moves its posterior
  by exactly 0.0). The k-inflation table in section 3 IS an in-sample fit and is labelled as a
  diagnostic, not a result, in the same sentence that reports it.
- **B9** denominator -- units reported three ways (n ticks, n_informative, game-clustered n_eff)
  and the n_eff caveat is stated explicitly in section 5.
- **B10 / Q3** no bar moved -- `IMPROVEMENT_BAR = 0.004`, `NOMINAL_COVERAGE = 0.90`,
  `COVERAGE_TOL = 0.02`, asserted byte-identical by the per-file test and asserted equal to
  S94's bar. The coverage tolerance is reported MISSED for this arm, never widened.
- **Q1 / Q2** -- no prereg seal and no ledger charge, because nothing is charged.
  `_charge_ledger` is not imported; `backtest_fwer.jsonl` is never opened; it stands at 18 rows.
- **Q4** leak contract -- walk-forward with purging by game and a symmetric 1-day embargo,
  asserted per fold; no meta-learner; the strictly-before guard is a property of the filter
  itself (reset per game, updated only from state t-1 and tick t) and is tested by truncation:
  cutting a game after tick 12 leaves its first 12 posteriors and posterior variances
  bit-identical (`np.array_equal`, not a tolerance).
- **Q5** one corpus (the S86 screen side) -> labelled **SINGLE-WINDOW**; `n_corpora_eff` is not
  claimed and `replication_gate` was not run.
- **Q6** calibration language only; no dollar, ROI or profit language; none of the retracted
  figures appears.
- **Q7** every scored metric carries n >= 30 except the deliberately published thin cells
  (`OT|blowout_gt12|rem_02_06` n = 1 in the premise table, shown with its n so it cannot be read
  as a measurement).
- **Q8** premise re-measured FIRST, before any build -- section 0. It held, and the row's own
  stop rule was checked and not triggered.
- **Q9** per-tick differential archived (192,635 rows with the posterior mean AND posterior
  variance, both interval ends, all four losses, all three differentials, `cluster_id`, fold and
  cell), so every CI and every coverage number here recomputes from the artifact alone.

## NOT VERIFIED

- This memo is the lane's own report; a verifier has not re-run it.
- **SINGLE-WINDOW.** One corpus, one venue (Polymarket throughout, a traded mid rather than a
  devigged close), 673 scored games. The verdict side (796 games) is untouched and unscored.
- **The coverage measure is grouped, not per-tick, by necessity** (a binary outcome has no
  per-tick interval coverage). Its resolution is `1 / n_groups` -- 2 points at 50 groups, 5.9
  points in OT where only 17 groups of 400 exist -- so the OT row in particular is coarse. The
  group frequency also carries its own sampling error, which is not differenced out here; at
  400-2,300 ticks per group and an ICC of 0.006-0.034 that error is well inside the reported
  miss distances, but it is not zero and no CI is attached to a coverage share.
- **The negative is about THIS model class, not about fusion in general.** A linear-Gaussian
  random walk with moment-fitted variances is the simplest sensor-fusion model there is. A
  richer one (state-dependent q, a bias term on the prior sensor, or a non-Gaussian observation
  model) is not tested here and is not refuted by this row.
- **`VAR_FLOOR = 1e-4` is load-bearing for the late-game interval result.** `r_m` sits on that
  floor in 23 of 127 cell-folds, all of them late/decided, and that is precisely where no scalar
  inflation reaches nominal coverage. The floor is a knob, it is reported, and a different floor
  would move the P4 and OT rows of the coverage table (it would not move the Brier rows, which
  are null by four orders of magnitude).
- **OT pricing is a known model artifact** inherited from S86 (`nba_checkpoint_benchmark.py:17-21`),
  so the OT rows measure the repricer's OT handling, not the OT market.
- No charge, no seal, no ledger row, no flag flipped, no push. A null Brier and a measured
  interval failure are honest results.
