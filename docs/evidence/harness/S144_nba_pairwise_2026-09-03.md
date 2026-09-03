# S144 NBA systematic pairwise grammar - SCREEN NULL

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
This is an uncharged, SINGLE-WINDOW SCREEN on the S86 SCREEN side. No ledger was
opened or changed, no K was read, and no preregistration trial is asserted.

## Premise and frozen construction

Step 0 confirmed the S102 grammar has 16 bases, precisely two pre-existing combined
forms (`margin_x_rem` and `margin_over_sqrt_rem`), and no systematic pair enumerator.
The S86 CSV is present. S144 excludes those two combined forms, leaving 14 bases:
91 unordered pairs x product and source-ordered safe ratio x unconditional plus phases
1 through 5 = **1,092** semantic-hash-deduplicated hypotheses.

Each operand is standardised with its own game's expanding causal history. The safe-ratio
denominator is sign-preservingly floored at 1e-3 standardised units. The builder passed
tick-time truncation invariance at eight evenly spaced probes and label-blindness.

The family `ingame_nba_pairs` was frozen before scoring in
`docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md`: pin
`6e7878ae5978150246cef4c706b5a05ef5275591` (VERIFIER CORRECTION: the lane's
memo printed `5e1a96b04...`, which is not the blob of any revision of this file) ->
`9e05a449ed313feb08dd54559d1e9328ed1dbbb7`, one additive amendment, no bar moved.
The pre-screen freeze commit is `f9bfb9d1d`.

## Screen result

The gated NBA tier used `incumbent=market`; its null is the walk-forward S94 global
recalibration `[1, logit(market)]`, fit on the identical train rows. It scored all S86
SCREEN rows from five purged, game-disjoint, one-day-embargoed test folds.

| item | result |
|---|---:|
| frozen family count | 1,092 |
| SCREENED / UNSCORED | 1,076 / 16 |
| frozen denominator clearing +0.004 | 0 / 1,092 |
| screened denominator clearing +0.004 | 0 / 1,076 |
| within-family BH q | 0.05 |
| BH discoveries / positive discoveries | 4 / 4 |
| BH threshold | 0.0000634111 |
| throughput | 3,433.6 screens/hour |
| elapsed | 1,144.9 seconds |

The 16 UNSCORED forms are all phase-1 forms involving `pace_ratio_p1`; that base is
undefined during period 1. They remain named in the SQLite archive and are not omitted
from the frozen-family denominator.

### Best 10, SCREEN side

Every row below has n = 192,635 ticks, n_informative = 68,925, and 673 game clusters.
The interval is the game-clustered 95 percent interval for improvement versus the
identical-row recalibration null.

| rank | hypothesis | n_eff | improvement | 95 percent interval | p raw |
|---:|---|---:|---:|---|---:|
| 1 | pair__margin__rem__product\|raw | 8,881.3 | +0.000154 | [-0.000023, +0.000332] | 0.0878 |
| 2 | pair__rem__tdm_h60__product\|raw | 8,746.5 | +0.000124 | [-0.000039, +0.000287] | 0.136 |
| 3 | pair__rem__tdm_h180__product\|raw | 8,355.3 | +0.000099 | [-0.000067, +0.000264] | 0.242 |
| 4 | pair__margin__lead_changes__product\|raw | 9,737.1 | +0.000087 | [-0.000052, +0.000226] | 0.222 |
| 5 | pair__rem__tdm_h600__product\|raw | 5,980.2 | +0.000079 | [-0.000180, +0.000338] | 0.551 |
| 6 | pair__lead_changes__tdm_h600__product\|raw | 5,997.6 | +0.000078 | [-0.000160, +0.000317] | 0.519 |
| 7 | pair__margin__rem__product\|raw@p3 | 9,249.2 | +0.000076 | [-0.000030, +0.000183] | 0.161 |
| 8 | pair__rem__tdm_h600__product\|raw@p3 | 7,074.6 | +0.000074 | [-0.000087, +0.000234] | 0.368 |
| 9 | pair__lead_changes__tdm_h60__product\|raw | 8,854.9 | +0.000069 | [-0.000071, +0.000210] | 0.332 |
| 10 | pair__margin__rem__safe_ratio\|raw@p3 | 9,726.4 | +0.000067 | [-0.000039, +0.000172] | 0.216 |

Verdict: **NULL**. The best point estimate is +0.000154, below the fixed +0.004
bar, and its game-clustered interval includes zero. No preregistration draft is warranted.

## Reproduction and archive

Scratch archive (never written under `data/`):

- `C:/Users/neelj/AppData/Local/Temp/cx_s144/s144_nba_pairs.sqlite`
- `C:/Users/neelj/AppData/Local/Temp/cx_s144/s144_nba_pairs_summary.json`
- `C:/Users/neelj/AppData/Local/Temp/cx_s144/s144_nba_pairs_top10_series.csv`

The CSV has 1,926,350 rows: hypothesis id, label, game cluster, timestamp, fold, outcome,
market, null and candidate probabilities, feature value, both losses, and their paired
differential. Rebuilding the top ten from their causal fold fits reproduced all stored
point estimates, interval endpoints, Brier values, and p-values with maximum absolute
difference 0.0.

## Verifier self-check

- B1: all 1,092 frozen members are counted; the 16 unscored forms are named above.
- B2/B3/B4/B6: additive family and builder; no renamed field, dropped row, claim loop, or
  retired module. Missing feature values use the existing null fallback on both arms.
- B5: no pod deployment occurred. B7/Q7: the screen evaluates all eligible rows and all
  eight causal probes are evenly spaced; this family construction is exhaustive.
- B8/Q4: fitting occurs only on strictly earlier, purged, embargoed, game-disjoint folds.
- B9: n ticks, n_informative, game clusters, and n_eff are reported.
- B10/Q3: BAR = 0.004, the S86 partition, and purge/embargo are unchanged.
- Q1/Q2: this is an uncharged SCREEN, not a trial; the family partition was committed before
  scoring, and no seal, K read, or ledger operation occurred.
- Q5: SINGLE-WINDOW; no AHEAD result is asserted. Q6: calibration language only.
- Q8: the current grammar premise and S86 archive presence were measured before changes.
- Q9: the top-ten all-row paired-loss differential and reconstructible fold state are archived
  at the paths above.

## NOT VERIFIED

- One sport and one S86 SCREEN corpus only; the VERDICT partition was not read.
- The 16 period-1 `pace_ratio_p1` forms have no fitted candidate and remain UNSCORED.
- The archived differential covers the reported top ten; the SQLite fold metadata reconstructs
  the other screened forms, but their full paired-loss rows were not separately materialised.

## Verifier corrections (Opus, 2026-09-03)

Verdict ACCEPT WITH CORRECTIONS. Everything the ACCEPTANCE RULE prices reproduced;
the corrections below are evidence-wording, not results.

1. OLD PIN. The pre-S144 blob of `FWER_FAMILIES_SPEC_2026-09-03.md` is
   `6e7878ae5978150246cef4c706b5a05ef5275591` (S102, commit 0614b78c3), not the
   `5e1a96b04...` the lane printed, which appears in no revision of the file. The
   NEW pin `9e05a449ed313feb08dd54559d1e9328ed1dbbb7` is correct and moved once.
2. REPRODUCTION TOLERANCE. "maximum absolute difference 0.0" is the lane's own
   refit from the fold coefficients. The verifier's independent recompute from the
   archived CSV ALONE, through `eval_gate.dm_test.diebold_mariano`, reproduces all
   ten point estimates, both interval endpoints, both p-values and all three Brier
   values to a maximum absolute difference of 4.97e-11 (the archived text
   precision), on 673 clusters and 192,635 rows per hypothesis.
3. n_informative 68,925 is a CORPUS constant (S102's pre-existing convention, the
   count of non-pinned market ticks), not a per-hypothesis count. Every phase
   conditioned row is scored on all 192,635 ticks with the feature zeroed outside
   its phase; the per-row in-phase share is the sqlite `coverage` column
   (0.0349 .. 0.6078 across the screened set) and the memo table does not print it.
   `n_eff` is per row and is the honest denominator.
4. The 4 within-family BH discoveries at q = 0.05 are named here rather than left
   as a count. All four are POSITIVE and all four are roughly two orders of
   magnitude below the +0.004 bar:
   `pair__dmargin_k3__lead_changes__product|raw` +0.0000431 p 9.48e-08;
   `pair__run_len_signed__lead_changes__product|raw` +0.0000246 p 2.61e-07;
   `pair__rem__run_len_signed__product|raw` +0.0000601 p 2.59e-06;
   `pair__dmargin_k5__lead_changes__product|raw` +0.0000338 p 6.34e-05.
   16 of 1,076 screened rows have a lower interval bound above zero; the largest is
   +0.0000601. None clears the bar, so the NULL verdict stands.
5. The 16 UNSCORED forms were checked against the sqlite archive and are exactly
   the 16 phase-1 `pace_ratio_p1` forms the memo names.
6. `ingame_screen_nba.py` was also edited (the pair enumerator joins the frozen set
   `sweep` gates against). Additive and required by the spec's CHANGE step, but
   outside the file list the lane's own scope line gives; it also drops two blank
   lines before `def sweep`, and `test_family_bars.py` drops two before
   `test_the_tick_grid_family_matches_its_frozen_enumerator` -- cosmetic.
7. `test_family_bars.py` gained three `pytest.skip` guards on an absent
   `data/cache/eval_gate/backtest_fwer.jsonl` (the worktree has no ledger junction).
   In master the ledger is present -- 18 rows, md5 a4ae7c13995672e478d59770591b83ba,
   unchanged by this lane -- so all 20 tests execute. The guards nonetheless turn a
   missing ledger from a hard failure into a silent skip; filed as a follow-up gap,
   not a rejection.

Verifier reproduction, all in master unless stated: the three named test files;
the top-10 recompute above; `_fit` confirmed to fit the null and the candidate on
one identical row set (`sub` after the shared finite-x mask), a zero-coefficient
candidate equal to the null at 0.0 and an identity recalibration equal to the raw
market at 1.11e-16; the truncation and label-blind guards re-run on the verifier's
own 120-game / 39,254-row S86 slice at 8 evenly spaced probes; semantic-hash
intersection with the S102 576 measured at 0; BAR 0.004, EMBARGO_DAYS 1, MIN_TRAIN
1000, MIN_UNIQUE 3 and N_FOLDS 5 byte-identical to master. Every evidence path the
memo names exists (A7). The full 1,092-member grid was screened in 1,144.9 s, so
the spec's seeded-third sampling clause was never invoked.
