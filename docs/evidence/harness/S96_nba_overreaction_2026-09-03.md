# S96 -- overreaction at tick resolution: does the NBA in-play line overshoot a scoring event?

Row: the 465,249-tick NBA corpus carries the score per tick, so a scoring event is visible
between consecutive ticks. Does the line OVERSHOOT the event and revert (mean reversion), or
UNDERSHOOT it and drift?

Verdict: **PREMISE DIRECTION FALSIFIED, ARM SCREEN NEGATIVE.** There is no overshoot anywhere.
Every phase, every horizon, every event threshold shows a **positive** slope of the subsequent
move on the event-tick move -- the line DRIFTS in the direction of the event, it does not
revert. The arm built to exploit it (which was free to pick either sign, and did pick the
drift sign) is **BEHIND the raw market on the primary arm (-0.000138, game-clustered CI95
[-0.000301, +0.000025], crossing zero)**; the bar (+0.004) is NOT met on any of the six arms.
**No prereg DRAFT was written.** Uncharged: no prereg seal, no ledger read, no ledger write,
no K consumed. **SINGLE-WINDOW** (one corpus, the S86 SCREEN side, NBA 2024-11-12..2026-06-10).
Verdict side never read.

Calibration measurement only. No dollar, ROI, profit or edge claim. No bar moved (Q3:
`IMPROVEMENT_BAR = 0.004`, asserted byte-identical by the per-file test). ASCII only.

Module: `scripts/platformkit/eval_gate/s96_nba_overreaction.py` (300 LOC)
Test: `python -m pytest tests/platformkit/ingame/test_s96_nba_overreaction.py -q` = **8 passed**
Archive (Q9): `data/cache/eval_gate/s96_nba_overreaction_2026-09-03.json` +
`...csv` (153,941 per-tick rows across the six arms: fold, phase, j, event_move, adj,
lambda_c, y, market, model, both fitted probabilities, all three losses, both paired-loss
differentials, `cluster_id` = game).

---

## 0. STEP 0 -- premise re-measured first (Q8)

Source: the S86 SCREEN archive `data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv`
(232,951 ticks / 797 games; `partition_corpus(seed=0)` on game blocks). Ticks are sorted by
`(game, ts)`; **0 duplicate `(game_id, ts)` pairs** on this side. `margin` is signed
(-60 .. +61), so a scoring event has a direction.

| the row says | measured 2026-09-03 | verdict |
|---|---|---|
| the corpus carries the score per tick so scoring events are visible | `margin`, `score_home`, `score_away` present on every screen tick; consecutive-tick margin changes exist in every game | CONFIRMED |
| events are countable per phase | **14,354 events at `|dmargin| >= 3`** (797 of 797 games) and **2,093 at `>= 5`** (734 games) -- both far above the 500-event stop rule | CONFIRMED |
| the question is overshoot vs drift | measurable, and **answered against the row's overshoot hypothesis** -- see below | **DIRECTION FALSIFIED** |

Event counts per phase:

| threshold | P1 | P2 | P3 | P4 | OT | total | games |
|---|---|---|---|---|---|---|---|
| `>= 3` | 3,537 | 3,674 | 3,639 | 3,422 | 82 | **14,354** | 797 |
| `>= 5` | 595 | 525 | 548 | 418 | 7 | **2,093** | 734 |

### The regression the row asks for

`m1 = logit(market_event) - logit(market_pre_event)` (the move AT the event tick);
`fk = logit(market_{t+k}) - logit(market_event)` (the cumulative move over the following k
ticks). OLS of `fk` on `m1`, one-way cluster-robust (sandwich) CI95 by game.
**slope < 0 = overshoot / mean reversion; slope > 0 = drift.**

`|dmargin| >= 3`:

| phase | n | k=3 slope [CI95] | k=5 slope [CI95] | k=10 slope [CI95] |
|---|---|---|---|---|
| P1 | 3,537 | +0.1613 [+0.1172, +0.2054] | +0.1788 [+0.1255, +0.2321] | +0.2067 [+0.1237, +0.2896] |
| P2 | 3,674 | +0.1206 [+0.0571, +0.1840] | +0.1518 [+0.0822, +0.2214] | +0.1815 [+0.1039, +0.2591] |
| P3 | 3,639 | +0.1883 [+0.1353, +0.2413] | +0.2897 [+0.2283, +0.3510] | +0.4422 [+0.3483, +0.5362] |
| P4 | 3,422 | +0.2424 [+0.1547, +0.3302] | +0.3130 [+0.1982, +0.4279] | +0.5180 [+0.3706, +0.6655] |
| OT | 82 | +0.3774 [+0.0009, +0.7540] | +0.3455 [-0.0625, +0.7535] | +0.5118 [-0.1120, +1.1357] |
| **ALL** | **14,354** | **+0.2314 [+0.1703, +0.2925]** | **+0.2966 [+0.2184, +0.3748]** | **+0.4768 [+0.3757, +0.5778]** |

`|dmargin| >= 5`:

| phase | n | k=3 | k=5 | k=10 |
|---|---|---|---|---|
| P1 | 595 | +0.2692 [+0.1890, +0.3493] | +0.2881 [+0.1903, +0.3860] | +0.3354 [+0.1915, +0.4793] |
| P2 | 525 | +0.2106 [+0.1369, +0.2843] | +0.2589 [+0.1612, +0.3566] | +0.3147 [+0.1936, +0.4359] |
| P3 | 548 | +0.3040 [+0.2104, +0.3975] | +0.3792 [+0.2730, +0.4854] | +0.5945 [+0.4247, +0.7642] |
| P4 | 418 | +0.3259 [+0.1736, +0.4782] | +0.3835 [+0.1568, +0.6102] | +0.7536 [+0.4419, +1.0653] |
| **ALL** | **2,093** | **+0.2985 [+0.2123, +0.3848]** | **+0.3480 [+0.2232, +0.4727]** | **+0.6196 [+0.4447, +0.7946]** |

**Not one negative slope anywhere.** 31 of the 33 cells have a CI excluding zero, all on the
positive side (the two exceptions are the 82-event OT cell at k=5 and k=10), and the slope grows monotonically with k in every phase. The bigger event
(`>= 5`) drifts harder than the smaller one. The row's stated hypothesis -- the line
overshoots a scoring event and reverts -- is **falsified in direction on this corpus**.

### Brier of the post-event market at the event tick vs k ticks later

Same event set, market prices only (no arm involved):

| threshold | k | Brier at the event tick | Brier at t+k | change |
|---|---|---|---|---|
| `>= 3` | 3 | 0.15974 | 0.15539 | -0.00435 |
| `>= 3` | 5 | 0.15974 | 0.15320 | -0.00654 |
| `>= 3` | 10 | 0.15974 | 0.14671 | -0.01303 |
| `>= 5` | 3 | 0.15706 | 0.15107 | -0.00599 |
| `>= 5` | 5 | 0.15706 | 0.14820 | -0.00886 |
| `>= 5` | 10 | 0.15706 | 0.14339 | -0.01367 |

The line is better k ticks after the event than at it. That is consistent with drift, but it is
**not evidence of it**: t+k is simply later in the game, and any in-play line improves with
time. It is reported because the row asks for it, and it gates nothing.

### The adversarial check that matters -- PLACEBO on non-event ticks

The same regression on ticks that are NOT events (identical horizon, identical clustering):

| threshold | k | placebo n | placebo slope [CI95] | event slope (ALL) |
|---|---|---|---|---|
| `>= 3` | 3 | 215,409 | +0.0661 [+0.0403, +0.0919] | +0.2314 |
| `>= 3` | 5 | 213,815 | +0.1420 [+0.1086, +0.1754] | +0.2966 |
| `>= 3` | 10 | 209,830 | +0.2865 [+0.2438, +0.3293] | +0.4768 |
| `>= 5` | 3 | 227,670 | +0.0871 [+0.0622, +0.1121] | +0.2985 |
| `>= 5` | 5 | 226,076 | +0.1621 [+0.1301, +0.1940] | +0.3480 |
| `>= 5` | 10 | 222,091 | +0.3091 [+0.2684, +0.3499] | +0.6196 |

**A third to two thirds of the "event drift" is not event-specific.** The line's move at ANY
tick predicts its move over the next k ticks with a positive slope. Events carry roughly 2-3x
the generic slope at k=3-5 and only ~1.6-2x at k=10, so the event-specific component is real
but much smaller than the headline event slope alone suggests. Any reading of the event table
that ignores this placebo overstates the effect. (Positive tick-to-tick autocorrelation of the
quoted mid is also exactly what a laggy or slowly-updating quote produces -- see NOT VERIFIED.)

Premise **HOLDS as measurable** (14,354 >> 500 events) and is **FALSIFIED in direction**
(drift, not overshoot). Per Q8 a falsified premise is a valid result; the arm was still run,
with a symmetric grid so the data could choose the sign.

## 1. Method

Arm, applied to the k ticks after an event (j = 1 .. k; the event tick itself is never
re-priced):

```
p = sigmoid(logit(market_t) - lambda_c * m1 * decay(j / k)),   decay = 1 - (j - 1) / k
```

`m1` is the event-tick move as defined above. **lambda_c > 0 shrinks the line back toward the
pre-event line** (the repair for overshoot the row asks for); **lambda_c < 0 pushes it further**
(the repair for drift). The grid is symmetric, `[-1.0, +1.0]` step 0.02, so the TRAIN folds pick
the sign; nothing constrains it to the row's hypothesis. `lambda_c` is fit per PHASE cell
(P1/P2/P3/P4/OT) by minimising that cell's tick-weighted Brier on TRAIN rows only; a phase with
fewer than 200 train ticks keeps `lambda_c = 0` (the raw market).

A tick inside two windows belongs to the NEAREST preceding event, so a new event restarts the
adjustment.

NULL, fit on the **identical** train rows: the S94 global unregularised logistic recalibration
on `[1, logit(market)]`. S94's lesson is that a recalibration null must be beaten, or the
effect is recalibration and not the mechanism.

Design: expanding walk-forward by game-first date on the S86 SCREEN side; 5 held-out blocks of
roughly equal tick count after a train-only seed block; **purged by game** (train games
asserted disjoint from test games) and a **1-day embargo** (`train_date_max < embargo_cut <=
test_start`, asserted per fold). Six arms are run: thresholds {3, 5} x k {3, 5, 10}. The
primary is **threshold 3, k 5**.

Folds of the primary arm:

| fold | test window | train ticks / games | test ticks / games |
|---|---|---|---|
| 1 | 2024-12-14..2025-01-27 | 7,697 / 128 | 7,884 / 136 |
| 2 | 2025-01-28..2025-11-08 | 15,443 / 262 | 7,754 / 131 |
| 3 | 2025-11-09..2026-01-03 | 23,325 / 395 | 8,034 / 132 |
| 4 | 2026-01-04..2026-03-05 | 31,367 / 527 | 7,731 / 133 |
| 5 | 2026-03-06..2026-06-10 | 39,077 / 659 | 7,765 / 133 |

The per-file test plants a distortion of known size and BOTH signs and checks `fit_lambda`
recovers it, checks the window tagging and the nearest-event rule, checks the purge/embargo
assertions, and flips the **last fold's own held-out outcomes** to prove the arm on that fold
does not move by a single bit.

## 2. Result -- held-out folds, tick-weighted

Improvement is `loss(arm_being_compared) - loss(S96 arm)`; positive means the S96 arm lost
less. CI95 is Diebold-Mariano clustered by game.

### All six arms (post-event ticks only)

| arm | n ticks | games | informative | n_eff | Brier market | Brier recal | Brier arm | vs market | DM CI95 | vs recal | bar met |
|---|---|---|---|---|---|---|---|---|---|---|---|
| thr3 k3 | 26,544 | 665 | 23,071 | 11,944.8 | 0.157823 | 0.158531 | 0.157973 | -0.000149 | [-0.000331, +0.000032] | +0.000559 | **no** |
| **thr3 k5 (primary)** | **39,168** | **665** | **33,231** | **12,191.6** | **0.156677** | **0.157370** | **0.156815** | **-0.000138** | **[-0.000301, +0.000025]** | **+0.000554** | **no** |
| thr3 k10 | 59,390 | 664 | 48,087 | 13,245.5 | 0.152927 | 0.153280 | 0.153071 | -0.000144 | [-0.000294, +0.000007] | +0.000210 | **no** |
| thr5 k3 | 5,028 | 614 | 4,370 | 2,331.3 | 0.157400 | 0.157672 | 0.157409 | -0.000009 | [-0.001183, +0.001166] | +0.000263 | **no** |
| thr5 k5 | 8,218 | 614 | 7,045 | 2,430.5 | 0.156096 | 0.156293 | 0.156113 | -0.000017 | [-0.001075, +0.001040] | +0.000180 | **no** |
| thr5 k10 | 15,593 | 612 | 13,058 | 2,542.1 | 0.154459 | 0.154631 | 0.154577 | -0.000118 | [-0.001047, +0.000812] | +0.000054 | **no** |

**Bar +0.004 vs the raw market: NOT MET on any arm**, by two orders of magnitude, and every CI
includes zero. The arm beats only the recalibration null (which is itself behind the raw
market on every arm, the same pattern S94 measured). `prereg_draft_warranted = False`;
**no prereg DRAFT was written.**

Primary arm ECE: market 0.030613, recal 0.027120, arm 0.032033 -- the arm is slightly worse
calibrated as well as slightly worse on Brier. ICC by game 0.0382, design effect 3.21.
`attach_informative_summary` (S87 bar): n 39,168 / n_informative 33,231 (84.8 pct) /
`ci95_informative` [-0.000338, +0.000021], mean informative differential -0.000158 -- the
informative-only interval says the same thing as the headline interval.

### Primary arm by phase

| phase | n | games | informative | n_eff | mean lambda_c | Brier market | Brier arm | vs market | DM CI95 | vs recal |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 | 8,390 | 661 | 7,459 | 2,508.4 | -0.299 | 0.205932 | 0.205919 | **+0.000013** | [-0.000313, +0.000340] | +0.001284 |
| P2 | 10,855 | 663 | 9,425 | 3,067.3 | -0.075 | 0.190576 | 0.190745 | -0.000169 | [-0.000403, +0.000065] | +0.000248 |
| P3 | 9,198 | 661 | 8,324 | 2,744.5 | -0.265 | 0.149088 | 0.149373 | -0.000285 | [-0.000812, +0.000243] | +0.000733 |
| P4 | 10,411 | 660 | 7,942 | 4,263.1 | +0.044 | 0.087495 | 0.087595 | -0.000100 | [-0.000284, +0.000084] | +0.000377 |
| OT | 314 | 33 | 269 | 309.2 | -0.055 | 0.184826 | 0.184862 | -0.000036 | [-0.000933, +0.000861] | -0.007685 |

P1 is the only phase where the arm is not behind, and its improvement is +0.000013 with a CI
straddling zero -- indistinguishable from doing nothing, which is what a mean lambda of -0.3
applied to a genuinely drifting line amounts to at this magnitude.

## 3. Is lambda stable across folds? Partly -- and it is negative, as the premise predicts.

`lambda_c` refit on each fold's train rows, primary arm (thr3 k5):

| fold | P1 | P2 | P3 | P4 | OT |
|---|---|---|---|---|---|
| 1 | -0.44 | -0.32 | -0.72 | +0.22 | 0.00 |
| 2 | -0.22 | -0.22 | -0.24 | +0.10 | 0.00 |
| 3 | -0.24 | +0.20 | -0.20 | +0.04 | 0.00 |
| 4 | -0.24 | +0.08 | -0.06 | -0.04 | -0.18 |
| 5 | -0.36 | -0.12 | -0.10 | -0.10 | -0.06 |
| **spread** | **-0.44 .. -0.22** (mean -0.300) | **-0.32 .. +0.20** (mean -0.076) | **-0.72 .. -0.06** (mean -0.264) | **-0.10 .. +0.22** (mean +0.044) | -0.18 .. 0.00 |

**P1 is the one stable cell: negative in all five folds, range -0.44 .. -0.22.** That is the
fitted parameter agreeing with the premise -- extrapolate the event move, do not shrink it. P2
and P4 flip sign across folds; P3 is negative in all five but swings 12-fold in magnitude.

On the `>= 5` arms the fit pins at the **grid boundary**: P1 lambda is -1.00 .. -0.86 (mean
-0.972) at k=10 and -1.00 .. -0.88 at k=5, i.e. the optimiser wants to undo the entire event
move and extrapolate a whole one again. Even there the arm is -0.000118 behind the raw market
with a CI crossing zero. **A parameter that runs to the edge of its grid and still cannot beat
the market is the clearest statement in this memo**: the drift is real in the regression and
worth essentially nothing in Brier at these magnitudes. The grid was NOT widened to chase it
(that would be moving a bar in all but name).

## 4. What this actually says

1. **There is no overreaction.** Every slope is positive. The in-play line under-reacts to a
   scoring event and keeps moving in the same direction for several ticks. The row's premise
   is falsified in direction, which per Q8 is a valid result.
2. **Most of that drift is not event-specific.** The placebo on non-event ticks carries a third
   to two thirds of the same slope. The line's move at any tick predicts its next moves.
3. **The drift is not worth anything in calibration terms.** The arm, free to pick the drift
   sign and given a 101-point grid, is -0.000138 behind the raw market on the primary arm and
   never better than -0.000009 on any of the six. The bar is +0.004; the measured effects are
   ~30x smaller than the bar and their CIs include zero.
4. **The recalibration null loses too**, on every arm, exactly as in S94. Two independent
   arms on this corpus have now found that a global recalibration fit on a past window and
   applied forward is BEHIND the raw in-play line. That is a property of the corpus worth
   carrying forward: on NBA in-play ticks, recalibration is not free.
5. **Where a future arm should not go.** Not at the post-event window with a scalar per phase.
   If the drift is to be exploited at all it is a horizon/latency question -- how stale the
   quote is at the moment the score changes -- not a shrinkage-coefficient question, and it
   would need the quote timestamp against the score timestamp, which this corpus does not
   carry (see NOT VERIFIED).

An honest NULL is a success. Nothing was charged, so nothing is spent.

## 5. Invariants (VERIFIER_CONTRACT B + Q)

- **B1** no circular metric -- no row is excluded after scoring; the only exclusions are
  structural (a tick with no k-th successor in its own game cannot have an `fk`) and are named
  with their counts in the tables above.
- **B2** additive -- one new module, one new test; nothing renamed, removed or re-typed. The
  module only READS the S86 archive and only WRITES its own two `s96_*` artifacts.
- **B7** no head-slice -- every post-event tick of every screen game is scored; the premise
  regressions run over all 14,354 / 2,093 events, and the placebo over all 209k-227k non-event
  ticks.
- **B8** no self-fit -- `lambda_c` and the recalibration null are fit on TRAIN rows only,
  proved by the outcome-flip test on the last fold.
- **B9** denominator -- units reported three ways (n ticks, n_informative, game-clustered ESS
  n_eff) on every scored row; no recycled unit.
- **B10 / Q3** -- no bar moved. `IMPROVEMENT_BAR = 0.004` is byte-identical to the register
  row and asserted by the test. The lambda grid was deliberately NOT widened when the fit hit
  its boundary.
- **Q1 / Q2** -- no prereg seal and no ledger charge, because nothing is charged.
  `_charge_ledger` is never imported, `backtest_fwer.jsonl` is never opened (still 18 rows);
  the per-file test asserts the module source contains no `_charge_ledger`, no `backtest_fwer`,
  no `prereg_seal` and no `sha256`.
- **Q4** -- walk-forward, purged by game, 1-day embargo, every fit on TRAIN rows only, asserted
  per fold and proved by the outcome-flip test. No meta-learner.
- **Q5** -- one corpus (the S86 screen side) -> labelled **SINGLE-WINDOW** here and in the
  register row.
- **Q6** -- calibration language only; no dollar, ROI, profit or edge word; none of the
  retracted figures appears.
- **Q7** -- every scored metric has n >= 30. The only thin cell published is OT (82 events in
  the premise, 314 arm ticks / 33 games), which carries its own n everywhere it appears.
- **Q8** -- premise re-measured first and reported before any arm ran; **FALSIFIED in
  direction** and reported as such.
- **Q9** -- the per-tick paired-loss series is archived beside the summary (153,941 rows over
  the six arms) with `cluster_id`, the fold, both differentials and every input the arm reads,
  so every CI here recomputes from the artifact alone.

## NOT VERIFIED

- **This memo is the lane's own report; a verifier has not re-run it.**
- **The drift may be a quote-latency artifact, and this corpus cannot tell.** The tick carries
  one timestamp for the row, not separate timestamps for the score update and the quote. If
  the recorded price at the event tick was quoted slightly before the score landed, the
  "drift" over the next few ticks is the market absorbing the score, not under-reacting to it.
  The positive PLACEBO slope on non-event ticks is consistent with a generally slow-updating
  mid. Distinguishing the two needs a quote timestamp this store does not have.
- **The event definition is a proxy for a scoring play**, not a play-by-play join. A margin
  change of >= 3 between two ticks can be one 3-pointer, or several plays if the tick gap is
  wide; the tick cadence is not uniform and is not conditioned on here.
- **SINGLE-WINDOW.** One corpus, one venue (Polymarket), one traded mid -- not a devigged
  close. The 796 verdict games are untouched and unscored; nothing here may be promoted
  without going through them.
- **5 expanding folds and the phase cell (period only) were chosen for readability**, not by a
  preregistered rule. A finer cell (period x margin x time remaining, S86's 27) was not tried,
  and would fit 27 scalars on the same rows.
- **The premise Brier-at-t vs Brier-at-t+k comparison conflates information arrival with
  elapsed time** and is reported descriptively only; it gates nothing.
- **`decay = 1 - (j-1)/k` is one shape, chosen a priori.** Exponential or flat decay is
  untested; given the size of the measured effects it is very unlikely to matter.
- **The OT cells are thin and inherit S86's known OT repricer artifact** in the `model` column,
  which this arm does not use except as an informative-tick input.
