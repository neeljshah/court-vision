# S98 -- a better as-of pregame prior, and a state-dependent margin sigma, for the NBA tick surface

Row: every NBA tick arm (S86 S94 S96 S97) priced the as-of prior as Elo `p0` through
`price_checkpoint(p0, home_score, away_score, period, clock, margin_sigma=13.5)`. That prior
trails the line pooled (-0.004857) while matching in 16/27 cells. S98 asks which half is the
crude one: the PRIOR, or the fixed sigma.

Verdict: **PREMISE HALF-FALSIFIED and the answer is the SIGMA, not the prior. No better as-of
pregame prior exists on disk** -- the NBA gate corpus has no `p_model` column, its `p_base`
and `p_elo` are the SAME number and byte-identical to `walk_forward_elo(games).p_home_elo`, and
that number is BEHIND the S86 `p0` at the first tick (0.223386 vs 0.222833 on 668 games). The
**state-dependent sigma is real and large**: fitting `margin_sigma` per phase cell on TRAIN
folds only cuts the pooled gap to the raw line roughly in half, **-0.004805 -> -0.002378, and
the fitted-sigma arm's CI now INCLUDES zero** ([-0.004904, +0.000148]) where the incumbent's
excludes it. **The bar (+0.004 vs the raw market, CI excluding zero, beating the recal null) is
NOT MET in any of the 27 cells nor pooled, so NO prereg DRAFT was written.** Uncharged: no
prereg seal, no ledger read, no ledger write, no K consumed. **SINGLE-WINDOW** (one corpus,
the S86 SCREEN side restricted to bridged games, NBA 2024-12-03..2026-04-06). Verdict side
never read.

Calibration measurement only. No dollar, ROI, profit or edge language. No bar moved (Q3:
`IMPROVEMENT_BAR` is imported from S94 so there is exactly one definition, and the per-file test
asserts `s98.IMPROVEMENT_BAR == s94.IMPROVEMENT_BAR == 0.004`). ASCII only.

Module: `scripts/platformkit/eval_gate/s98_nba_better_prior.py` (300 LOC)
Test: `python -m pytest tests/platformkit/ingame/test_s98_nba_better_prior.py -q` = **11 passed**
Archive (Q9): `data/cache/eval_gate/s98_nba_better_prior_2026-09-03.json` +
`...csv` (162,171 per-tick rows, 33 columns: fold, cell, y, market, both priors, both fitted
sigmas, the blend base arm and w, all six arm probabilities, all seven losses, all six paired
differentials, `cluster_id` = game).

---

## 0. STEP 0 -- the premise, measured before anything was built (Q8)

**Question the row asks: which better as-of pregame probabilities exist on disk for the 1,593
priced games?** Three candidates were named. All three were checked.

| candidate | what is actually on disk | verdict |
|---|---|---|
| NBA gate corpus `p_model` | `data/cache/combo/gate_corpus_nba.parquet` has 15 columns: `event_id, corpus_unit, event_date, y, p_base, p_elo` + 9 `*_asof` box features. **There is no `p_model` column** (`has_p_model_column: false`). | ABSENT |
| gate corpus `p_base` / `p_elo` | 1,814 rows, 2024-10-22..2026-04-12. **`max_abs(p_base - p_elo) = 0.0`** -- they are the same column. Both are **byte-identical** to `domains.basketball_nba.ratings.walk_forward_elo(games).p_home_elo`: `max_abs = 0.0` on all 1,814 matched rows. So this is the SAME Elo family as the S86 `p0` (a sequential pre-game snapshot instead of a per-date `replay(until=game_date)`), not a different model. | SAME FAMILY |
| S05 calibrated pregame probability | `docs/evidence/calibration/nba_reliability_2026-09-03.json` publishes bin tables, ECE and Murphy terms only -- **no per-event probability is archived**. Reproduced here as a walk-forward recalibration of the Elo `p0` fit on TRAIN games only (isotonic and logistic), scored at each game's first tick on 664 games: **isotonic 0.229176, logistic 0.228559 vs raw Elo `p0` 0.228058** -- both WORSE out of sample. | REPRODUCED, WORSE |
| any other pregame model artifact under `data/cache` with as-of dates | swept: `combo/`, `eval_gate/` (S58/S79/S84/S86/S94/S96/S97 series carry losses, not pregame p), `ingame/nba_logistic_prior_v1.json` (an in-game ladder fit, not a pregame prior), `benchmarks/`, `probe_*`. **None carries a per-game pregame probability with an as-of date.** | NONE |

**Join coverage to the 1,593 priced games.** The bridge is the incumbent's own crosswalk,
`nba_mechanism_ladder.build_crosswalk` (frozenset of `market_ticker` tricodes + date within
+/-1 day, kept only when the corpus outcome agrees with `games.parquet` `home_win`), exactly as
S84 used it:

| step | games | note |
|---|---|---|
| priced corpus (`nba_checkpoints_full.parquet`) | **1,593** | |
| bridged to `games.parquet` by the crosswalk | **1,331** (83.6 pct) | 262 unbridged |
| ... of those, present in the gate corpus | 960 | the gate corpus itself drops 366 bridged games |
| **candidate prior available (walk_forward_elo direct)** | **1,331** | so the module uses `walk_forward_elo` directly, NOT the gate-corpus row set -- same numbers, 371 more games |
| on the S86 SCREEN side | **668 of 797** (83.8 pct) | 195,161 of 232,951 screen ticks |
| actually SCORED (after the train-only seed fold) | **571 games / 162,171 ticks** | 2024-12-03..2026-04-06 |

The 262 unbridged games are **not random**: `games.parquet` ends **2026-04-12**, so every
2026-04/05/06 game is unbridgeable (69 + 25 + 5), as are 2025-04/05/06 (28 + 37 + 7) and 63
games in 2025-10. **This scored frame therefore contains no 2025 or 2026 playoffs**, and that is
the single largest difference from S86's 797-game screen.

### First-tick table (SCREEN side, each game's first traded tick, 668 games)

| series | Brier at the first tick |
|---|---|
| Elo `p0_asof` (the S86 incumbent prior) | **0.222833** |
| candidate `walk_forward_elo p_home_elo` | 0.223386 |
| Elo `p0` state-priced at that tick (`price_checkpoint`) | 0.222010 |
| **first traded market price** | **0.209205** |

`candidate_beats_elo_p0 = false`. The two priors differ by `mean_abs 0.001283`, `max_abs
0.047127` -- the same rating system read two ways.

**ANSWER TO STEP 0, stated plainly: no candidate prior on disk beats Elo `p0` at the first
tick.** Per the row, the sigma part was run anyway, and the candidate prior is carried through
every table below rather than dropped, so the null is visible rather than asserted.

## 1. Method

Four model arms, all priced by the same closed form, plus the market and one null:

| arm | definition |
|---|---|
| `elo` | `price_checkpoint(p0_asof, state, margin_sigma=13.5)` -- the S86 incumbent |
| `elo_sig` | same prior, `margin_sigma` fit per phase cell on TRAIN folds |
| `cand` | `price_checkpoint(walk_forward_elo p_home_elo, state, margin_sigma=13.5)` |
| `cand_sig` | candidate prior, `margin_sigma` fit per phase cell on TRAIN folds |
| `blend` | `sigmoid((1-w) logit(market) + w logit(base))`, ONE global `w` on TRAIN; `base` is whichever of the four arms has the lowest TRAIN Brier that fold (a TRAIN-only selection) |
| `recal` | the S94 global unregularised logistic recalibration on `[1, logit(market)]` -- the NULL |

**Pricing is vectorised and proved to be the same function.** `price_vec` evaluates the
NBARepricer closed form row-wise (`final_margin ~ Normal(margin + sigma*Phi^-1(p0)*rem_frac,
(sigma*sqrt(rem_frac))^2)`, with the deterministic buzzer surface at `rem_frac <= 0`). Against
the scalar `price_checkpoint` on 2,000 EVENLY spaced scored rows (not a head slice, B7):
`max_abs_delta = 2.22e-16` -- one ulp, from `scipy.special.erf` vs `math.erf`. The per-file test
repeats the check at a NON-default sigma (7.5), where the fitted arms live, and gets the same
scale.

**Sigma fit.** For each S86 phase cell (period x |margin| x time-remaining), `margin_sigma` is
the point of a fixed grid `6.0 .. 24.0 step 0.5` minimising that cell's TRAIN Brier. A cell with
fewer than 200 train ticks keeps 13.5 (missing evidence is not a fitted value, B3). Nothing else
is fit; the priors read no outcome.

**Strictly-before guard**, two parts, both asserted at run time and tested:

1. the prior must be **CONSTANT within a game** (`max_prior_values_per_game = 1` for both
   priors) -- a "prior" that moves tick to tick is carrying tick-time information;
2. re-pricing each game's **first 4 ticks with every later tick of that game withheld** must
   reproduce the full-frame price exactly: 2,672 ticks re-priced, `max_abs_delta = 0.0`
   (exactly zero, not a tolerance), for both priors.

The test plants the classic leak (a within-game-varying `groupby.transform("cummax")` prior) and
asserts the guard raises. **It also records the guard's LIMIT in a named test**
(`test_guard_limit_a_per_game_constant_future_read_is_NOT_detectable_here`): a per-game constant
prior built from future data (e.g. the game's LAST market price) is invisible to a row-wise
guard. The as-of property of the prior VALUES is inherited, not re-proved here -- S86's
`replay(games, until=game_date)` for `p0_asof` (strictly-before, guarded there) and
`walk_forward_elo`'s documented strictly-pre-game snapshot for the candidate.

**Design.** Expanding walk-forward by game-first date on the S86 SCREEN side, 5 held-out blocks
after a train-only seed block, **purged by game** (train games asserted disjoint from test games)
and a **1-day embargo** (`train_date_max < embargo_cut <= test_start`, asserted per fold). The
per-file test flips the LAST fold's own held-out outcomes and proves no fitted arm on that fold
moves by one bit.

| fold | test window | embargo cut | train ticks / games | test ticks / games | blend base arm | w |
|---|---|---|---|---|---|---|
| 1 | 2024-12-03..2025-01-12 | 2024-12-02 | 32,467 / 95 | 32,291 / 118 | cand_sig | 0.645 |
| 2 | 2025-01-13..2025-11-08 | 2025-01-12 | 63,913 / 210 | 32,932 / 115 | cand_sig | 0.330 |
| 3 | 2025-11-09..2025-12-23 | 2025-11-08 | 97,140 / 326 | 32,806 / 116 | elo_sig | 0.275 |
| 4 | 2025-12-25..2026-02-19 | 2025-12-24 | 131,019 / 446 | 32,402 / 116 | elo_sig | 0.255 |
| 5 | 2026-02-20..2026-04-06 | 2026-02-19 | 162,014 / 557 | 31,740 / 106 | elo_sig | 0.475 |

TRAIN Brier by arm, per fold (this is what picks the blend base -- a TRAIN-only decision):

| fold | elo | elo_sig | cand | cand_sig |
|---|---|---|---|---|
| 1 | 0.072479 | **0.068747** | 0.072386 | **0.068625** |
| 2 | 0.074895 | 0.072190 | 0.074848 | **0.072132** |
| 3 | 0.077022 | **0.074729** | 0.077121 | 0.074833 |
| 4 | 0.081579 | **0.078560** | 0.081754 | 0.078747 |
| 5 | 0.082113 | **0.079030** | 0.082254 | 0.079181 |

In every fold the fitted sigma beats the fixed 13.5 on TRAIN by 0.0027-0.0038 Brier, and the two
priors are within 0.0002 of each other -- the same reading as the first-tick table.

## 2. Pooled result (SCREEN side, tick-weighted)

n 162,171 ticks / 571 games / **67,534 informative** / **n_eff 2,129.6** (ICC by game 0.2655,
design effect 76.15). Improvement is `loss(market) - loss(arm)`; positive means the arm lost
less than the raw in-play line. CI95 is Diebold-Mariano clustered by game.

| arm | Brier | improvement vs the raw market | DM CI95 |
|---|---|---|---|
| **raw market** | **0.074457** | -- | -- |
| `elo` (the S86 incumbent) | 0.079262 | **-0.004805** | [-0.007737, -0.001873] (excludes 0) |
| **`elo_sig`** | **0.076835** | **-0.002378** | **[-0.004904, +0.000148]** (INCLUDES 0) |
| `cand` | 0.079438 | -0.004980 | [-0.007909, -0.002052] (excludes 0) |
| `cand_sig` | 0.077027 | -0.002569 | [-0.005087, -0.000052] (just excludes 0) |
| `blend` | 0.074667 | -0.000209 | [-0.001285, +0.000866] |
| `recal` (the S94 null) | 0.074544 | -0.000087 | [-0.000874, +0.000700] |

`ci95_informative` on the headline differential (informative ticks only, S87):
[-0.009622, +0.000880].

**Bar: +0.004 vs the raw market with a CI excluding zero AND a lower Brier than the recal null.
NOT MET by any arm pooled** (the best arm pooled is the `recal` null itself, at -0.000087).
`prereg_draft_warranted = False`; **no prereg DRAFT was written.**

Two things this table says that the row did not know:

1. **The prior is not the crude half.** `cand` is 0.000175 Brier WORSE than `elo`, and
   `cand_sig` is 0.000191 worse than `elo_sig`. Swapping one Elo replay for another changes
   nothing, in the direction of slightly worse.
2. **The sigma IS the crude half.** Fitting it per cell moves the incumbent from
   -0.004805 (CI excluding zero, i.e. significantly BEHIND the line) to -0.002378 (CI including
   zero, i.e. **statistically indistinguishable from the raw in-play line pooled**). Half the
   measured model-vs-market gap on this surface was a single hard-coded constant.

## 3. The 27-cell table (SCREEN side)

`inf` = informative ticks (`attach_informative_summary`), `n_eff` = game-clustered ESS.
Improvement is vs the RAW market; positive = the arm lost less.

| cell | n | inf | n_eff | market Brier | elo | elo_sig | cand | cand_sig | blend |
|---|---|---|---|---|---|---|---|---|---|
| P4\|blowout_gt12\|rem_le02 | 34,858 | 418 | 1,787.4 | 0.000757 | +0.000757 | +0.000757 | +0.000757 | +0.000757 | +0.000576 |
| P4\|mid_06_12\|rem_le02 | 28,302 | 1,185 | 370.3 | 0.000297 | +0.000016 | +0.000016 | +0.000016 | +0.000015 | +0.000016 |
| P4\|close_le5\|rem_le02 | 19,063 | 2,030 | 2,045.8 | 0.011690 | -0.000404 | -0.000338 | -0.000407 | -0.000342 | +0.000159 |
| P1\|close_le5\|rem_gt12 | 9,968 | 9,156 | 642.7 | 0.211510 | -0.012693 | -0.012864 | -0.013218 | -0.013386 | -0.002986 |
| P2\|close_le5\|rem_gt12 | 9,697 | 7,631 | 513.4 | 0.217278 | -0.005932 | -0.006285 | -0.006764 | -0.007115 | -0.001735 |
| P2\|mid_06_12\|rem_gt12 | 9,014 | 6,824 | 549.8 | 0.184737 | -0.015579 | **-0.010117** | -0.015887 | -0.010509 | -0.003148 |
| P3\|close_le5\|rem_gt12 | 5,907 | 5,294 | 423.2 | 0.218106 | +0.002047 | **+0.002442** | +0.001387 | +0.001723 | +0.001282 |
| P3\|mid_06_12\|rem_gt12 | 5,843 | 5,329 | 532.5 | 0.163729 | -0.006907 | **-0.003484** | -0.007011 | -0.003674 | +0.000114 |
| P2\|blowout_gt12\|rem_gt12 | 5,842 | 4,438 | 297.8 | 0.089670 | -0.005763 | **-0.002497** | -0.005820 | -0.002587 | -0.000436 |
| P3\|blowout_gt12\|rem_gt12 | 5,814 | 5,303 | 395.4 | 0.054327 | +0.000023 | **+0.002106** | +0.000021 | +0.002095 | +0.001797 |
| P1\|mid_06_12\|rem_gt12 | 4,939 | 4,476 | 520.6 | 0.192403 | -0.019262 | **-0.009220** | -0.020221 | -0.010275 | -0.002687 |
| OT\|close_le5\|rem_le02 | 3,893 | 344 | 82.0 | 0.011693 | -0.066424 | **-0.025277** | -0.066683 | -0.025350 | -0.001573 |
| P4\|blowout_gt12\|rem_06_12 | 3,679 | 3,065 | 386.8 | 0.022519 | +0.000336 | +0.000602 | +0.000330 | +0.000586 | +0.000370 |
| P4\|mid_06_12\|rem_06_12 | 2,883 | 2,684 | 483.2 | 0.132379 | -0.008192 | **+0.001570** | -0.008347 | +0.001336 | +0.000758 |
| P4\|close_le5\|rem_06_12 | 2,619 | 2,454 | 346.2 | 0.226914 | -0.001974 | **+0.003433** | -0.002340 | +0.002904 | +0.001681 |
| P4\|blowout_gt12\|rem_02_06 | 2,392 | 1,771 | 407.3 | 0.003968 | +0.002303 | +0.002284 | +0.002303 | +0.002284 | +0.001865 |
| P4\|mid_06_12\|rem_02_06 | 1,756 | 1,667 | 392.4 | 0.063162 | -0.005057 | **+0.001136** | -0.005082 | +0.001054 | +0.001201 |
| P4\|close_le5\|rem_02_06 | 1,730 | 1,651 | 411.5 | 0.220619 | -0.004249 | **+0.006111** | -0.004354 | +0.005932 | +0.003210 |
| OT\|mid_06_12\|rem_le02 | 1,557 | 53 | 93.6 | 0.000569 | -0.005397 | -0.001870 | -0.005336 | -0.001809 | +0.000000 |
| P1\|blowout_gt12\|rem_gt12 | 872 | 796 | 125.6 | 0.118089 | -0.007422 | -0.001197 | -0.007589 | -0.001416 | +0.000708 |
| P3\|blowout_gt12\|rem_06_12 | 511 | 316 | 183.5 | 0.019540 | -0.001211 | -0.000917 | -0.001211 | -0.000959 | -0.000059 |
| P3\|close_le5\|rem_06_12 | 316 | 285 | 149.5 | 0.217901 | -0.005571 | -0.008296 | -0.005707 | -0.008431 | -0.002449 |
| P3\|mid_06_12\|rem_06_12 | 309 | 270 | 159.6 | 0.137463 | -0.001976 | +0.001607 | -0.002163 | +0.001420 | +0.002696 |
| OT\|close_le5\|rem_02_06 | 249 | 242 | 68.6 | 0.242994 | -0.005417 | +0.000779 | -0.005076 | +0.001121 | +0.001647 |
| OT\|blowout_gt12\|rem_le02 | 134 | 3 | 134.0 | 0.000002 | +0.000002 | +0.000002 | +0.000002 | +0.000002 | +0.000001 |
| OT\|mid_06_12\|rem_02_06 | 23 | 22 | 9.9 | 0.375558 | -0.036657 | -0.036657 | -0.036657 | -0.036657 | -0.017340 |
| OT\|blowout_gt12\|rem_02_06 | 1 | 1 | 1.0 | 0.954529 | -0.045293 | -0.045293 | -0.045293 | -0.045293 | -0.042154 |

The last three cells are published with their own n and are far below any sampling rail (Q7);
they are shown, not used.

**The largest positive cell is `P4|close_le5|rem_02_06`, +0.006111 for `elo_sig`, and its CI
does NOT exclude zero** ([-0.002096, +0.014318]). The ONE cell whose CI excludes zero in the
model's favour anywhere in this table is `P4|close_le5|rem_02_06` for the **blend**
(+0.003210, CI [+0.000084, +0.006336]) -- **and +0.003210 is under the +0.004 bar**, so it does
not clear. `cells_clearing_bar = []`.

The cells where the fitted sigma helps most are exactly the ones where the fixed 13.5 was worst:
mid-margin and late-clock states (`P1|mid` -0.019 -> -0.009, `P4|close|rem_02_06` -0.004 ->
+0.006, `OT|close` -0.066 -> -0.025). It does NOT help in early close games (`P1|close`
-0.012693 -> -0.012864, marginally worse) -- the cell S86 flagged and S94 failed on stays the
hardest cell on this surface for the third row running.

## 4. The fitted sigma, per cell per fold -- and its LIMIT

| cell | sigma (elo) folds 1..5 | sigma (cand) folds 1..5 |
|---|---|---|
| P4\|blowout_gt12\|rem_le02 | 6.0 6.0 6.0 6.0 6.0 | 6.0 6.0 6.0 6.0 6.0 |
| P4\|mid_06_12\|rem_le02 | 23.0 21.0 19.5 23.5 22.5 | 23.0 21.0 19.5 23.5 22.5 |
| P4\|close_le5\|rem_le02 | 24.0 21.0 20.5 23.0 21.0 | 24.0 21.0 20.5 23.0 21.0 |
| P1\|close_le5\|rem_gt12 | 11.0 12.5 14.0 19.5 17.0 | 11.0 12.5 14.0 19.5 17.0 |
| P2\|close_le5\|rem_gt12 | 10.5 13.5 16.0 20.5 18.5 | 10.5 13.5 16.0 20.5 18.5 |
| P2\|mid_06_12\|rem_gt12 | 24.0 18.5 20.0 20.0 20.0 | 24.0 18.5 20.0 20.0 20.0 |
| P3\|close_le5\|rem_gt12 | 24.0 22.0 20.0 21.5 19.0 | 24.0 22.0 19.5 21.5 19.0 |
| P3\|mid_06_12\|rem_gt12 | 24.0 24.0 20.5 21.0 21.0 | 24.0 24.0 20.5 21.0 21.0 |
| P2\|blowout_gt12\|rem_gt12 | 24.0 18.0 19.5 19.0 19.5 | 24.0 18.0 19.5 19.0 19.5 |
| P3\|blowout_gt12\|rem_gt12 | 18.5 16.0 17.5 17.5 18.5 | 18.5 16.0 17.5 17.5 18.5 |
| P1\|mid_06_12\|rem_gt12 | 19.5 18.5 20.5 24.0 24.0 | 19.5 18.5 20.5 24.0 24.0 |
| OT\|close_le5\|rem_le02 | 6.0 6.0 6.0 6.0 6.0 | 6.0 6.0 6.0 6.0 6.0 |
| P4\|blowout_gt12\|rem_06_12 | 6.0 23.5 22.0 21.5 22.0 | 6.0 23.5 22.0 21.5 22.0 |
| P4\|mid_06_12\|rem_06_12 | 18.5 19.5 20.0 22.0 22.0 | 18.5 19.5 20.0 22.0 22.0 |
| P4\|close_le5\|rem_06_12 | 23.5 24.0 21.0 23.0 23.5 | 23.5 24.0 20.5 22.5 23.5 |
| P4\|blowout_gt12\|rem_02_06 | 6.0 21.0 20.0 19.0 19.0 | 6.0 21.0 20.0 19.0 19.0 |
| P4\|mid_06_12\|rem_02_06 | 22.5 24.0 23.0 23.5 23.5 | 22.5 24.0 23.0 23.5 23.5 |
| P4\|close_le5\|rem_02_06 | 24.0 24.0 24.0 24.0 24.0 | 24.0 24.0 24.0 24.0 24.0 |
| OT\|mid_06_12\|rem_le02 | 13.5 13.5 6.0 6.0 6.0 | 13.5 13.5 6.0 6.0 6.0 |
| P1\|blowout_gt12\|rem_gt12 | 13.5 24.0 24.0 24.0 24.0 | 13.5 24.0 24.0 24.0 24.0 |
| P3\|blowout_gt12\|rem_06_12 | 13.5 13.5 13.5 17.5 18.5 | 13.5 13.5 13.5 17.0 18.5 |
| P3\|close_le5\|rem_06_12 | 13.5 13.5 13.5 24.0 24.0 | 13.5 13.5 13.5 24.0 24.0 |
| P3\|mid_06_12\|rem_06_12 | 13.5 13.5 13.5 15.5 17.0 | 13.5 13.5 13.5 15.5 17.0 |
| OT\|close_le5\|rem_02_06 | 13.5 13.5 13.5 13.5 19.5 | 13.5 13.5 13.5 13.5 19.5 |
| OT\|blowout_gt12\|rem_le02 | -- -- -- 13.5 13.5 | -- -- -- 13.5 13.5 |
| OT\|mid_06_12\|rem_02_06 | 13.5 13.5 13.5 13.5 13.5 | 13.5 13.5 13.5 13.5 13.5 |

(`13.5` with no movement = a cell under `MIN_CELL_TRAIN = 200` that fold, left at the default;
`--` = the cell had no train rows that fold.)

Three readings, all honest:

1. **The direction is one-sided and large.** Almost every live cell wants a sigma of **18-24**,
   not 13.5 -- i.e. the incumbent repricer is systematically **over-confident**: it prices the
   remaining-margin distribution too tight and therefore pushes probabilities too far from 0.5.
   The two exceptions run the other way (`P4|blowout|rem_le02` and `OT|close|rem_le02` pin at
   6.0, where the game is effectively decided).
2. **CLOSED AT LIMIT on the grid, not lowered.** `P4|close_le5|rem_02_06` sits at the grid
   MAXIMUM 24.0 in all five folds, and **21 of the 127 fitted cell-folds pin at 24.0** (15 more
   pin at the minimum 6.0). **The grid was NOT widened after seeing this** -- widening a search range to chase a result is moving a bar in
   all but name (the S96 precedent). The fitted value in those cells is a **bound, not an
   estimate**, and a wider grid is a NEW row, not a rerun of this one.
3. **It is not stable enough to call a parameter.** `P1|close` runs 11.0 -> 19.5 and `P2|close`
   10.5 -> 20.5 across folds, monotonically increasing with the training window. That is the
   same instability S94 measured in its `w_c` (0.000-0.885), milder but present, and it is why
   the pooled `elo_sig` CI still touches zero rather than clearing it.

## 5. The blend, and the recalibration null

The S94 single-`w` form, with one global `w` per fold and the base arm chosen on TRAIN:

| arm | Brier | vs the raw market | DM CI95 |
|---|---|---|---|
| raw market | **0.074457** | -- | -- |
| blend (`w` 0.255-0.645) | 0.074667 | -0.000209 | [-0.001285, +0.000866] |
| **recal null** | **0.074544** | -0.000087 | [-0.000874, +0.000700] |

**The blend is behind the raw market AND behind the recalibration null**, with a CI crossing
zero, so it fails the row's bar twice over. This is the third independent confirmation on this
corpus (S94, S96, S98) that **blending the state price into the in-play line does not beat the
line**, and the second (S94, S98) that a global recalibration fit on a past window and applied
forward is roughly free but not positive.

Note the blend's fitted `w` is much larger here (0.255-0.645) than S94's target-cell weights,
because the base arm it blends is `*_sig` -- a better-conditioned model earns more weight and
STILL does not clear the line. That is the cleanest statement in this memo.

## 6. Independent reproduction (A2)

Every headline number here recomputes from the archived per-tick CSV alone, with no access to
the JSON or the module state:

```
csv rows 162,171   games 571   2024-12-03..2026-04-06
  market    brier 0.074457
  elo       brier 0.079262   impr -0.004805   DM ci [-0.007737, -0.001873]
  elo_sig   brier 0.076835   impr -0.002378   DM ci [-0.004904, +0.000148]
  cand      brier 0.079438   impr -0.004980
  cand_sig  brier 0.077027   impr -0.002569   DM ci [-0.005087, -0.000052]
  blend     brier 0.074667   impr -0.000209   DM ci [-0.001285, +0.000866]
  recal     brier 0.074544   impr -0.000087
```

## 7. Rails self-check (VERIFIER_CONTRACT B + Q)

- **B1** no circular metric -- no row is excluded after scoring; the only exclusion (games with
  no bridged candidate prior) is applied BEFORE any arm is computed, is named, counted
  (129 of 797 screen games) and its cause is measured (`games.parquet` ends 2026-04-12).
- **B2** additive -- one new module, one new test, two new artifacts; nothing renamed, removed
  or re-typed. S94's constants are imported, not copied, so there is one definition of the bar.
- **B3** fall-through -- a cell below `MIN_CELL_TRAIN` keeps the DEFAULT sigma (13.5) rather
  than being quarantined; missing evidence is not a fitted value.
- **B7** no head-slice -- every tick of every scored game is scored; the `price_vec`
  reproduction sample is evenly spaced over the whole frame, stated in the artifact.
- **B8** no self-fit as independent -- sigma, `w` and the recalibration are fit on TRAIN rows
  only and scored on purged, embargoed held-out games; the blend's BASE ARM is also selected on
  TRAIN. The outcome-flip test proves the held-out fold's labels never reach any fitted arm.
- **B9** denominator -- units reported three ways everywhere (n ticks, n_informative, game ESS
  n_eff); ICC 0.2655 / design effect 76.15 published so no `n` is read as independent.
- **B10 / Q3** no bar moved -- `IMPROVEMENT_BAR` is imported from S94 and asserted equal to
  0.004 by the test; the sigma grid is a declared design constant and was **not** widened after
  the boundary pinning was seen (reported as CLOSED AT LIMIT instead).
- **Q1 / Q2** no prereg seal and no ledger charge, because nothing is charged.
  `_charge_ledger` is never imported, `backtest_fwer.jsonl` is never opened and is still 18 rows
  (mtime 2026-09-02 12:27, before this row ran at 15:33). K was never read.
- **Q4** leak contract -- expanding walk-forward, purged by game, symmetric 1-day embargo,
  asserted per fold; no meta-learner (the blend consumes arm probabilities computed on the same
  held-out rows, not an OOF stack).
- **Q5** one corpus -> labelled **SINGLE-WINDOW** here and in the register row.
- **Q6** calibration language only; none of the retracted figures appears.
- **Q7** every scored metric carries its own n; three cells (n 134, 23, 1) are published below
  the rail with their n visible and are used for nothing.
- **Q9** the per-tick paired-loss series is archived beside the summary with `cluster_id`, the
  fold, the cell, both priors, both fitted sigmas, all seven losses and all six differentials,
  so every CI here recomputes from the artifact alone -- demonstrated in section 6.

## NOT VERIFIED

- **This memo is the lane's own report; a verifier has not re-run it.**
- **SINGLE-WINDOW.** One corpus, one venue (Polymarket), a traded mid rather than a devigged
  close. The verdict side (796 games) is untouched and unscored.
- **The scored frame is 571 of the 1,593 priced games (35.8 pct) and contains no playoffs.**
  The crosswalk drops 262 games and `games.parquet` ends 2026-04-12, so 2025-04..06 and
  2026-04..06 are structurally absent. The 27-cell numbers here are therefore NOT
  interchangeable with S86's on the same cell names, and the pooled market Brier differs
  (0.074457 here vs 0.077065 on S86's full screen) for that reason among others.
- **The fitted sigma pins at the grid maximum in 21 of 127 cell-folds** (and at the minimum in
  15 more). Those values are bounds, not estimates. The
  pooled `elo_sig` improvement is therefore a LOWER bound on what a state-dependent sigma could
  do, and the honest next row is a wider grid -- prereged, not appended here.
- **The as-of property of the prior VALUES is inherited, not re-proved.** This module's guard
  proves row-wiseness and within-game constancy; a per-game constant future read would pass it
  (named test). `p0_asof` was guarded in S86, the candidate by `walk_forward_elo`'s contract.
- **The sigma cells reuse S86's 27-cell grid.** No search over alternative conditioning
  variables (signed margin, pace, rest, time since the last quote) was done; `margin` is
  bucketed on `|margin|` so a home-favourite asymmetry inside a bucket is invisible.
- **OT pricing remains a known repricer artifact** (documented at
  `nba_checkpoint_benchmark.py:17-21`); the OT cells measure the repricer, not the OT market.
  The fitted sigma halves the OT damage but does not fix the mechanism.
- **No charge, no seal, no ledger row, no prereg DRAFT.** An honest BEHIND-that-becomes-a-MATCH
  is a measurement, not a finding, and this row makes no claim beyond it.
