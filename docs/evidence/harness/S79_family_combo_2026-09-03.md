# S79 -- FAMILY-LEVEL COMBINATION screen: no family clears the screen bar (2026-09-03)

## VERDICT: NO FAMILY CLEARS +0.004 ON THE SCREEN SIDE -- and combining made things WORSE in 11 of 12

0 of 12 screenable families reach the register row's `+0.004` screen bar. 0 of 12 have a DM 95 pct
CI whose lower end is above 0. The best combination is `nba_boxdetail` at `+0.000979` against
`p_base` (Elo, NOT a close), which is BELOW its own single best feature (`+0.002244`). Adding the
family's 2nd-5th ranked features to the 1st HURT the paired Brier in 11 of 12 families; the single
exception is `tennis_hold` (`+0.001881` better than its k=1 arm, but still only `+0.000138` against
the devigged close, CI `[-0.005031, +0.005306]`).

No prereg draft is written: the register row conditions ONE on a family clearing `+0.004`, and none
does. Nothing was charged (the FWER ledger is 18 rows, md5 `a4ae7c13995672e478d59770591b83ba`,
byte-identical before and after this lane). No verdict-partition row was materialised. No prereg was
sealed. `data/registry/` was not touched. Calibration language only.

## THE HONESTY HEADLINE, FIRST: THIS IS AN IN-SAMPLE CEILING, NOT A VERDICT

The top-k are chosen BY their screen-side improvement and then scored on that SAME screen partition.
That is selection and evaluation on one set of rows. Every improvement in the table below is
therefore a CEILING that flatters the combination, and the honest reading of a null result under a
flattering procedure is that the real out-of-sample number is no better. The fact that the ceiling
itself is negative in 10 of 12 families is the load-bearing sentence of this memo.

## PREMISE (Q8) -- HELD on the claim, CORRECTED on the scope

The S79 row's claim -- "No family-level COMBINATION has been screened" -- is TRUE. Re-measured at
HEAD before any work:

- `grep -niE "combination|stack|multi" scripts/platformkit/foundry/*.py` returns three hits, all
  unrelated (`np.column_stack` twice, the word "multi-row" in a docstring). The foundry screens one
  feature per hypothesis and nothing else; `screen_predictor.RealScreenPredictor` takes a single
  `feature` string and `ScreenBinder.__call__` binds exactly one.
- `scripts/platformkit/combo/` DOES hold a combination lane (`combination_families.py`,
  `combination_enum.py`), but its five COMB_* families are transforms over IN-GAME detail signals
  with their own ledger (`data/cache/eval_gate/combo_fwer.json`); it has never touched the 37 frozen
  FWER families or any foundry-screened feature. Likewise `eval_gate/stacker.py` stacks OOF GAP
  ARMS, not family members. So the premise stands.

SCOPE CORRECTION, stated because the row says "the 37 families": only 12 families have ANY screened
single, so only 12 can have >= 2. The other 25 produced ZERO screens in S58c and still do -- every
`live_tick` family is refused by name (in-game state columns on a pregame corpus) and the
player/pitcher/referee-grain families are refused as unavailable (>1 row per event, or WTA event_ids
that never join the gate spine). This lane did not change that; it is the same 25 the S58c memo
already recorded. Per-family screened counts (denominator = every T1 SCREEN row in the four S58c
DBs, nothing dropped): nba_boxdetail 250, tennis_setdetail 293, tennis_hold 134, nba_team_adv 112,
nba_gate 88, soccer_gate 82, soccer_xg_proxy 75, nba_defender_rollup 72, nba_carryover 50,
tennis_gate 33, mlb_gate 24, mlb_inning 24.

## WHAT WAS RUN

`scripts/platformkit/foundry/family_combo_screen.py` (298 LOC), test
`tests/platformkit/foundry/test_family_combo_screen.py` = **3 passed in 4.25s**.

For each of the 12 families:

- **Rows**: `screen_predictor.corpus_states(sport)` -> `tiers.partition_corpus(states, seed=20260903)`
  -> the SCREEN side only, last 800 states (the S58c window, unmoved). The verdict side is never
  built into a states list, so a leak onto it is not reachable from this module. Screen partition
  shas recomputed here and byte-equal to the S58c memo's: soccer `5c8d63970b08ce97`, tennis
  `c8dde4f3a44c8e58`, nba `1a32541d44aa7fcb`, mlb `ad743c924c7c4547`.
- **Picks**: the family's top-5 by STORED screen improvement (`brier_close - brier_model`, read from
  the S58c sqlite; nothing re-ranked). Two picks whose as-of value VECTORS are identical collapse to
  one -- `p_base` and `p_home_elo` are one column under two names, and without the dedup a "k=5"
  would be a k=3 plus two ridge-shrunk copies. Feature keys carry the params (`feature__transform__
  halflife3`), because `feature__transform` alone collides across the four `ew` halflives.
- **Model**: ONE L2-regularised logistic on `[1, logit(p_ref), z(f_1..f_k)]`, refit every 50 train
  rows, ridge 1e-3, >= 30 complete fit rows else fall back to the incumbent (missing != bad, B3);
  mu/sd computed inside each train fold only. Fit and served by `eval_gate.walkforward.walk_forward`
  -- expanding window in `state_ts` order, purge 48 h same-team, embargo 3 days same-matchup (the
  harness's own constants; the row asked for a 1-day embargo and the harness's 3 days is STRICTER,
  so nothing was loosened), vintage asserted per row.
- **Score**: paired Brier against the incumbent on the walk-forward records; cluster-robust DM with
  the sport's declared SF-10 key (`tiers._cluster_ids`: team / div / player), which is the SAME
  clustering the single-feature screens used, so the combo and k=1 arms are comparable. `d =
  loss_incumbent - loss_model`, the `dm_test` contract, so `mean_diff` IS the improvement and the CI
  reads in that direction.
- **k=1 arm**: the same machinery on the family's top single feature alone -- the control that says
  whether combining added anything.

**Incumbent, labelled**: soccer and tennis are scored against the DEVIGGED CLOSE. nba and mlb have
no close in the gate corpus; their incumbent is `p_base` (Elo). An nba/mlb number in the table is
NOT a close-relative number and must not be read as one.

## RANKED TABLE (12 families, ordered by combo improvement)

| rank | family | sport | incumbent | k | n_events | Brier incumbent | Brier k=1 | Brier combo | improvement combo | DM CI 95 (combo) | DM p | n_eff | clears +0.004 | combo - k=1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | nba_boxdetail | nba | p_base | 5 | 800 | 0.205118 | 0.202874 | 0.204139 | +0.000979 | [-0.005297, +0.007254] | 0.7520 | 800.0 | no | -0.001265 |
| 2 | tennis_hold | tennis | devig_close | 5 | 800 | 0.197611 | 0.199355 | 0.197473 | +0.000138 | [-0.005031, +0.005306] | 0.9582 | 608.6 | no | +0.001881 |
| 3 | nba_team_adv | nba | p_base | 5 | 800 | 0.205118 | 0.202937 | 0.205257 | -0.000139 | [-0.006705, +0.006428] | 0.9659 | 637.9 | no | -0.002319 |
| 4 | nba_carryover | nba | p_base | 5 | 800 | 0.205118 | 0.203635 | 0.205877 | -0.000759 | [-0.008353, +0.006835] | 0.8395 | 800.0 | no | -0.002242 |
| 5 | nba_gate | nba | p_base | 5 | 800 | 0.205118 | 0.202363 | 0.205920 | -0.000803 | [-0.006833, +0.005228] | 0.7874 | 800.0 | no | -0.003557 |
| 6 | nba_defender_rollup | nba | p_base | 5 | 800 | 0.205118 | 0.202370 | 0.206585 | -0.001467 | [-0.008249, +0.005315] | 0.6615 | 800.0 | no | -0.004214 |
| 7 | mlb_gate | mlb | p_base | 5 | 800 | 0.249660 | 0.252637 | 0.253533 | -0.003874 | [-0.008698, +0.000951] | 0.1114 | 800.0 | no | -0.000896 |
| 8 | tennis_gate | tennis | devig_close | 5 | 800 | 0.197611 | 0.200958 | 0.201956 | -0.004345 | [-0.012920, +0.004230] | 0.3192 | 427.2 | no | -0.000998 |
| 9 | tennis_setdetail | tennis | devig_close | 5 | 800 | 0.197611 | 0.198488 | 0.202197 | -0.004586 | [-0.009846, +0.000674] | 0.0872 | 728.3 | no | -0.003709 |
| 10 | soccer_xg_proxy | soccer | devig_close | 5 | 800 | 0.241896 | 0.243341 | 0.247369 | -0.005473 | [-0.024161, +0.013214] | 0.3347 | 280.3 | no | -0.004028 |
| 11 | mlb_inning | mlb | p_base | 5 | 800 | 0.249660 | 0.254280 | 0.257778 | -0.008118 | [-0.015179, -0.001056] | 0.0257 | 731.1 | no | -0.003497 |
| 12 | soccer_gate | soccer | devig_close | 5 | 800 | 0.241896 | 0.242864 | 0.250269 | -0.008374 | [-0.026212, +0.009465] | 0.1808 | 667.7 | no | -0.007405 |

Counts: clears +0.004 = **0 of 12**. Combo improvement > 0 = 2 of 12 (k=1 > 0 = 5 of 12). CI lower
above 0 = **0 of 12**. Combo better than its own k=1 = **1 of 12** (`tennis_hold`). The one CI that
EXCLUDES zero is `mlb_inning`, and it excludes it on the WRONG side (`[-0.015179, -0.001056]`): that
combination is measurably worse than Elo. `mlb_inning` is also frozen as (period, total) while this
corpus is pregame ML, the same label mismatch the S58c memo flagged -- its row is a throughput
number, not a market-matched one.

## WHY COMBINING ADDS NOTHING HERE: THE TOP-K ARE NEAR-DUPLICATES

The mechanical reason is visible in the picks. In 6 of the 12 families the top-5 by screen
improvement are mostly ONE column at several `ew` halflives, or one column under two transforms:

- `nba_gate`: `dreb_x_pace_asof` at halflives 3, 5, 10, 20 plus `p_elo/rank_in_league` -- 4 of 5
  slots are one signal smoothed four ways.
- `nba_defender_rollup`: `def_matchup_min_diff_asof` at all four halflives, plus one sibling.
- `nba_team_adv`: `away_ts_pct_asof` at three halflives plus `away_efg_pct_asof` (TS pct and eFG pct
  are near-collinear by construction).
- `soccer_gate`: `diff_shots_for_asof` at three halflives plus `away_sot_for_l10` at two.
- `soccer_xg_proxy`, `tennis_setdetail`: same shape.

Ranking by screen improvement selects the SAME signal repeatedly, so the "combination" spends its
extra parameters on redundant columns and pays the variance without buying information. That is a
concrete, named lever for a future row (diversify the pick rule by SOURCE COLUMN rather than by
hypothesis), not a claim that combinations cannot work.

## REPRODUCTION (A2) AND THE ARCHIVED DIFFERENTIAL (Q9)

- **The k=1 arm reproduces the stored S58c screen EXACTLY.** For all 12 families
  `|brier_model(k=1 arm) - brier_model(stored T1 row)| = 0.000e+00`. That is the check that this
  lane's machinery is the same machinery, not a re-derivation: same window, same partition, same
  purge/embargo, same ridge, same refit cadence.
- Per-event paired-loss series, one CSV per family (`event_id, ts, cluster, loss_model,
  loss_incumbent, d`), 800 rows and 800 UNIQUE event_ids each:
  `data/cache/eval_gate/s79_family_combo_2026-09-03_<family>.csv` (12 files).
- Summary + every refit's train size, coefficients, mu and sd for both arms of every family:
  `data/cache/eval_gate/s79_family_combo_2026-09-03.json`.
- The headline recomputes from the CSV alone: mean of `loss_model` over
  `..._nba_boxdetail.csv` = 0.204139, mean of `loss_incumbent` = 0.205118, difference +0.000979 --
  identical to the table.
- Reproduce end to end: `python -m scripts.platformkit.foundry.family_combo_screen`
  (`FOUNDRY_PORTABLE_CORPUS` unset; this box has the domain sources).

## SELF-CHECK against VERIFIER_CONTRACT B and Q

- **B1** no row is excluded by any metric; the denominator is every screened family with >= 2
  singles, and the 25 families with none are named above rather than dropped silently.
- **B2** additive only: one new module, one new test, one new artifact prefix. No existing column,
  status value or field was renamed or removed; `screen_predictor` and `tiers` are imported, never
  edited.
- **B3** a missing feature value falls back to the incumbent, it never scores as bad.
- **B7** not a head slice: the served window is the LAST 800 screen-side states, the same window
  every S58c single screen used, and all 800 are scored in both arms.
- **B9** the denominator is 800 unique event_ids per family (`n_unique_events == n_events == 800`),
  not a recycled unit; cluster counts are printed (nba/mlb G=30 teams, tennis G=233 players,
  soccer G=3 divisions).
- **B10 / Q3** no bar moved: seed 20260903, window 800, ridge 1e-3, MIN_FIT 30, refit 50, purge 48h,
  embargo 3d are all the harness's existing values, and `+0.004` is quoted from the register row.
- **Q1** no prereg is sealed and no scored CLAIM is made -- a screen is a NON-FINDING.
- **Q2** nothing charged; `_charge_ledger` is never reached (this module does not import it), K was
  never read, and the real ledger is 18 rows before and after.
- **Q4** every number comes through `walk_forward` with purge + embargo + vintage; no meta-learner
  is involved.
- **Q5** not applicable -- no AHEAD is claimed. Every family is a single window by construction.
- **Q6** calibration language only; no retracted figure appears.
- **Q7** n = 800 SCORED rows per arm, above the sampling rail.
- **Q9** the per-event differential and the as-of fit state are archived, and the headline
  recomputes from the CSV alone.

## NOT VERIFIED (read this before quoting any number above)

1. **Selection is in-sample.** Top-k chosen by screen improvement, scored on the same screen
   partition. Every number is a ceiling. Nothing here says what any combination does on the VERDICT
   side, which was deliberately never opened.
2. **nba and mlb are not close-relative.** Their incumbent is `p_base` (Elo). Only the four
   soccer/tennis rows compare against a devigged close.
3. **Only k = 5 and k = 1 were run.** k = 2, 3, 4 were not swept, so "the top-2 might have helped"
   is untested. The register row caps k at 5; this lane used the cap and the control, nothing between.
4. **Only ONE combination form was screened**: a linear L2 logistic on standardised as-of features
   added to `logit(p_ref)`. Interactions, regime conditioning, residual-on-residual and non-linear
   blends are NOT screened here (the `combo/` lane's COMB_* families cover those shapes for in-game
   signals, on a different corpus and a different ledger).
5. **25 of the 37 frozen families remain unscreenable at source** -- refused by leaky name or as
   >1-row-per-event. Nothing in this lane changed that, and no statement here covers them.
6. **The screen window is the last 800 rows of each screen side**, not the whole side. Earlier
   screen-side rows were not scored.
7. **soccer's CI is very wide** (G = 3 divisions on the screen side, n_eff 280-668 of 800), so its
   two rows are the least informative in the table; a soccer null here is weak evidence, not strong.
8. **DM clustering is the sport's declared SF-10 key (team / div / player), not `corpus_unit`.**
   `corpus_unit` is carried only on soccer states, where it IS the div, so for the other three sports
   a corpus_unit clustering does not exist to use. The declared key groups games together and is the
   more conservative of the available choices, and it is what the single screens used.
9. **A finding filed rather than fixed**: `tiers._run_screen` passes `(loss_model - loss_close)` to
   `diebold_mariano`, whose documented contract is `d = loss_close - loss_model`. Every stored T1
   `dm_stat` is therefore the SIGN MIRROR of the convention (the two-tailed p-value is unaffected, so
   no stored verdict moves). This module uses the documented direction. Not repaired here -- `tiers`
   is load-bearing for charged trials and a sign change there deserves its own row.
10. **No pod measurement, no deploy, no flag flipped, no `data/registry/` write, no `--force`.**
