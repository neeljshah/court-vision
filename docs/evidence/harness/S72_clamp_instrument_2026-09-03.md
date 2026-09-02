# S72 -- clamp-family inner runner: a purged-empty CPCV test state no longer disables a config

## VERDICT: INSTRUMENT REPAIRED (no verdict, no charge, no bar moved)

This row repairs the INSTRUMENT that produced the S58 batch-2 trial-A NULL (6afb8fed1). It
does NOT re-score, re-verdict or re-charge that family. Nothing in this lane read a K, sealed a
prereg, charged the FWER ledger, or wrote `data/cache/eval_gate/`.

CORRECTION (measured after the landing commit): `backtest_fwer.jsonl` was 17 rows at this lane's
start and is 18 rows now. The 18th row -- `foundry:d65df2a9...`, family `soccer_gate`, at
2026-09-02T17:27:21Z -- was charged by a CONCURRENT foundry lane, not by S72. S72's charge count
is 0. Any statement in this memo or in the S72 results-ledger line that the ledger "stays at 17
rows" is scoped to this lane's own writes and is corrected here.

## STEP 0 -- the defect reproduced on window 1 (before any change)

Reproduced live from the archived folds artifact plus a fresh instrumented run of
`cpcv_evaluate` on the same MLB corpus (52,558 ticks / 178 games; scored set 47,104 / 158).

The named failing state, outer fold `2026-06-30` (the first scored fold), inner CPCV split 0:

    state game_id KXMLBGAME-26JUN271910CHCMIL  state_ts 2026-06-28T01:30:36+00:00
    purged train states 0   purged train ticks 0
    -> np.concatenate([]) in _predictor raises "need at least one array to concatenate"
    -> inner_score returns status FAILED for the WHOLE config, for ALL 9 configs

and the short-train variant, outer fold `2026-07-07`:

    state game_id KXMLBGAME-26JUN281410COLMIN  state_ts 2026-06-28T20:35:23+00:00
    purged train states 4   purged train ticks 735  (< MIN_TRAIN 1000)
    -> "inner train infeasible" -> the same whole-config failure

Per-fold status in the landed artifact (`s58_trialA_clamp_family_folds_2026-09-03.json`),
recomputed here rather than quoted: **8 of 13 outer folds had 0/9 configs OK**, so the
preregistered fallback clause handed those folds to the incumbent.

| outer fold | configs OK (before) | error on all 9 |
|---|---|---|
| 2026-06-30 | 0/9 | need at least one array to concatenate |
| 2026-07-01 | 0/9 | need at least one array to concatenate |
| 2026-07-02 | 0/9 | inner train infeasible |
| 2026-07-03 | 0/9 | inner train infeasible |
| 2026-07-04 | 0/9 | need at least one array to concatenate |
| 2026-07-05 | 0/9 | need at least one array to concatenate |
| 2026-07-06 | 0/9 | need at least one array to concatenate |
| 2026-07-07 | 0/9 | inner train infeasible |
| 2026-07-08 .. 2026-07-12 | 9/9 | -- |

CORRECTION to the S58 trial-A memo: it records the split as "6 folds / 2 folds". The measured
split is **5 concatenate / 3 infeasible**. The 8/13 headline is unchanged.

The scarcity explanation is confirmed false as a cause: every one of the 8 fallback folds had
at least 5,454 outer-train ticks and at least 20 outer-train games. The failure is entirely
CPCV's symmetric 1-calendar-day embargo plus the 48 h same-team purge emptying the train set
for individual inner TEST STATES, and one such state killing the whole config.

Usable inner test states per fold (probe over the same purge rules, before any change):

| outer fold | inner test states | usable | purged-empty or short |
|---|---|---|---|
| 2026-06-30 | 140 | 0 | 140 |
| 2026-07-01 | 252 | 83 | 169 |
| 2026-07-02 | 343 | 147 | 196 |
| 2026-07-03 | 357 | 153 | 204 |
| 2026-07-04 | 455 | 425 | 30 |
| 2026-07-05 | 609 | 569 | 40 |
| 2026-07-06 | 644 | 621 | 23 |
| 2026-07-07 | 686 | 662 | 24 |
| 2026-07-08 | 847 | 847 | 0 |
| 2026-07-09 | 931 | 931 | 0 |
| 2026-07-10 | 945 | 945 | 0 |
| 2026-07-11 | 1,071 | 1,071 | 0 |
| 2026-07-12 | 1,239 | 1,239 | 0 |

Seven of the eight fallback folds had between 83 and 662 perfectly usable inner test states
that the old runner discarded. Fold 2026-06-30 has 0 usable states and is a GENUINE fallback:
its 20 outer-train games all fall inside a 2-calendar-day span, so the 1-day embargo purges
every train state against every test state. No bar can fix that fold, and nothing was moved to
try (Q3).

## The change (additive, one module; no shared module touched)

`scripts/platformkit/eval_gate/s58_clamp_family_trial.py` only. `cpcv_engine.py` is UNCHANGED
-- the purge, the embargo and the leak contract are byte-identical.

1. `_predictor` -- a test state whose PURGED train set is empty, under `MIN_TRAIN`, or single
   -class is recorded in `predictor.skipped` and scored as MISSING for that state alone. It
   returns 0.5 solely to satisfy `cpcv_evaluate`'s [0,1] record contract; that record is never
   scored (only `predictor.stash` is). It no longer raises.
2. `inner_score` -- a config's inner score is the tick-weighted mean over its NON-EMPTY inner
   test states, with `n_states_scored` and `n_states_empty` recorded. A config is `FAILED` only
   on a genuine exception, and `NO_SCORED_STATE` when every one of its inner test states was
   purged empty.
3. `select_configs` -- the outer fallback clause fires only when NO config has a valid inner
   score. Every fold record now carries `inner_selection: operative|fallback`,
   `inner_selection_reason` and `n_configs_scored` beside the pre-existing `fallback` flag
   (additive; no field renamed or removed, B2).
4. `main()` is BLOCKED (`RECHARGE_BLOCKED`): `PREREG_SHA256` seals a prereg that describes the
   PRE-repair instrument, so re-running it would charge a different candidate under a stale
   seal (Q1). The block lifts only with a new prereg.

No bar changed: `BAR` 0.004, `ALPHA` 0.05, `MIN_TRAIN` 1000, `MIN_STAMPS` 8, `CONFIGS`,
`SCORED` (47,104 / 158) and `REPRO_INCUMBENT` are byte-identical to master (Q3). The OUTER
walk-forward (`outer_series` -> `gap_blend_arm._walk_forward`) is untouched, so every
per-config outer series in the landed S58 artifact still reproduces exactly.

## DRY RUN -- selection only, no verdict (window 1)

Operative inner selection on **12 of 13 outer folds** (was 5 of 13). The one remaining
fallback is fold 2026-06-30, which has 0 usable inner test states by construction and is a
CORRECT fallback, not an instrument failure -- its reason is recorded in the fold record.

| outer fold | inner_selection | selected config | configs scored | empty inner states | reason |
|---|---|---|---|---|---|
| 2026-06-30 | fallback | e4_w1.0_d0.15 (incumbent) | 0/9 | 140 | no config scored: every inner test state had a purged-empty or short train set |
| 2026-07-01 | operative | e4_w2.0_d0.10 | 9/9 | 169 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-02 | operative | e4_w2.0_d0.10 | 9/9 | 196 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-03 | operative | e4_w2.0_d0.10 | 9/9 | 204 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-04 | operative | e4_w0.5_d0.10 | 9/9 | 30 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-05 | operative | e4_w0.5_d0.10 | 9/9 | 40 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-06 | operative | e4_w0.5_d0.10 | 9/9 | 23 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-07 | operative | e4_w0.5_d0.10 | 9/9 | 24 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-08 | operative | e4_w0.5_d0.10 | 9/9 | 0 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-09 | operative | e4_w0.5_d0.10 | 9/9 | 0 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-10 | operative | e4_w0.5_d0.10 | 9/9 | 0 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-11 | operative | e4_w0.5_d0.10 | 9/9 | 0 | 9/9 configs scored on non-empty purged inner test states |
| 2026-07-12 | operative | e4_w0.5_d0.10 | 9/9 | 0 | 9/9 configs scored on non-empty purged inner test states |

**operative folds 12/13** (before: 5/13). The lane's brief anticipated 13/13; the honest measured
number is 12/13, and 13/13 is not reachable without moving `MIN_TRAIN` or the embargo, which Q3
forbids. Every one of the 12 operative folds selects a d=0.10 config -- descriptive only, and
NOT evidence about the family: no outer series was scored here.


The dry run calls `select_configs` ONLY. It writes no ledger row, seals no prereg, reads no K,
and never calls `score()` -- **no Brier and no verdict exists for it anywhere**, by
construction. Its artifact is labelled `"DRY_RUN": true` and lives in the session scratchpad,
never under `data/cache/eval_gate/`. It is an instrument check, not a result, and nothing in it
may be quoted as one.

## Tests

`tests/platformkit/eval_gate/test_s58_clamp_family_trial.py` -- 6 passed (3 pre-existing, 3 new):

- `test_planted_empty_state_does_not_disable_the_config` -- a planted empty purged train set is
  recorded as skipped and the SAME predictor keeps scoring the next state; `inner_score` over a
  state set built so that some CPCV splits purge to empty returns `status OK` with
  `n_states_empty > 0` and `n_states_scored > 0`. This test fails on master (the old
  `_predictor` raises).
- `test_all_states_empty_falls_back_with_the_reason` -- 40 train games on ONE calendar day:
  feasible (at least MIN_TRAIN ticks and MIN_STAMPS stamps, so not a scarcity fallback), every
  config `NO_SCORED_STATE`, fold `inner_selection == "fallback"`, `n_configs_scored == 0`,
  reason recorded, selection falls back to `CONFIGS[0]`.
- `test_operative_fold_records_the_selection_reason` -- a well-spread fold records `operative`
  with all 9 configs scored and the reason string.

## The re-prereg + re-charge plan (NOT executed by this lane)

The clamp family's verdict is still the landed S58 trial-A NULL (SINGLE-WINDOW), measured with
the broken instrument. It is NOT superseded, re-scored or withdrawn by this row. Re-running the
family is a NEW trial, in this order:

1. **Window 2 first.** S55 must have at least 30 MLB games of a second, disjoint window before
   any re-run, so the re-run can name a second corpus_unit and print `min_corpora_eff` at the K
   it reads (Q5). Window 1 alone would only reproduce a SINGLE-WINDOW label.
2. **New prereg**, committed ALONE, sealing: the same 9 configs and the same four AHEAD
   conditions with the same bars (0.004 / CI lower bound above 0 / deflated_p below alpha /
   fdr_bh q=0.05 over 10 p-values) -- byte-identical, never relaxed; plus the repaired fallback
   clause and the two windows. Its SHA-256 replaces `PREREG_SHA256` and `RECHARGE_BLOCKED` is
   cleared in the same commit.
3. **One charge** for the whole family, appended BEFORE any metric, with the K read from the row
   at launch (Q2). The 2026-09-03 charge is spent and is never reused.
4. Q4 reproduction gate on the incumbent, Q9 per-tick differential archived, calibration
   language only.

Until step 2 lands this module cannot charge: `main()` asserts on `RECHARGE_BLOCKED`.

## NOT VERIFIED

- Any outer Brier, improvement, CI, deflated_p or verdict for the repaired instrument. The dry
  run deliberately computed none, and none may be inferred from the selection table.
- Whether the clamp family is AHEAD, NULL or BEHIND with a working inner runner. Unknown until
  the re-prereg'd, re-charged trial runs on window 2.
- The per-config outer table in the S58 trial-A memo remains descriptive and unselected-on; this
  row does not license reading a verdict off it.
- Window 2 itself: S55's game count was not measured by this lane.
- The repaired runner on any corpus other than the MLB window-1 corpus.
