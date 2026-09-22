# S347 four-arm MLB baseline -- RESULT (sealed prereg, one charged attempt, read after an independent output audit)

Run: 2026-09-21 23:01:15Z to 23:58:36Z from the repo root with the landed runner (row S359, c2c7c791d) on corpus
data/cache/ingame_grade_joined/mlb_segmented_r3 (manifest f3b5e3f9364f7627...), prereg docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md
(seal 18b45d85...), attempt 1 of 2. Charge: canonical ledger row k_cumulative = 19 (prior max 18), family ingame_four_arm_mlb_r3.
Audit (row S379, 5ec57d7d0, run 2026-09-22 00:39Z from master): verdict_release = True; 22 checks PASS, 1 NOT_AUDITABLE (C.means, non-critical:
the saved summary carries no per-arm means), 0 FAIL. The cells below were read only after that release.

## Verdict

EVERY comparison is UNDERPOWERED: UNDERPOWERED = 96.
No cell is AHEAD (so no SINGLE-WINDOW label is needed) and no cell is BEHIND. Under the sealed bars (95 percent game-clustered
bootstrap interval must lie wholly on one side of zero; at least 30 scored games) this window does not distinguish any arm from
the market. The prereg stated in advance that one corpus authorizes no AHEAD conclusion; the corrected baseline is the deliverable.

Scored population: 15 folds, 9968 warm-up keys excluded identically from all arms; scored ticks 19919 in 135 games (all_tick), 9318 in 135 games
(state_transition_tick). Arms: A = market, B = recalibrated market, C = market + state, D = C + model. Differences are candidate
loss minus A loss; negative means the candidate had lower loss than the market on this window.

## Every cell (verbatim from summary.json; point, 95 percent interval, verdict, largest single-game absolute share, leave-one-game-out range)

### all_tick / overall -- n_ticks 19919, n_games 135

| weighting | comparison | point | ci95 low | ci95 high | verdict | share (game) | concentration | LOO low | LOO high |
|---|---|---|---|---|---|---|---|---|---|
| tick | B_brier | -0.003363 | -0.010776 | +0.004000 | UNDERPOWERED | 0.429 | pass | -0.004443 | -0.001955 |
| tick | C_brier | -0.000021 | -0.007722 | +0.007875 | UNDERPOWERED | 67.277 | FAIL | -0.001417 | +0.001215 |
| tick | D_brier | +0.002593 | -0.006018 | +0.011221 | UNDERPOWERED | 0.637 | FAIL | +0.000951 | +0.004173 |
| tick | B_logloss | -0.008416 | -0.026189 | +0.008883 | UNDERPOWERED | 0.453 | pass | -0.010705 | -0.004684 |
| tick | C_logloss | +0.000767 | -0.018464 | +0.020502 | UNDERPOWERED | 4.470 | FAIL | -0.002693 | +0.003960 |
| tick | D_logloss | +0.007444 | -0.014231 | +0.028543 | UNDERPOWERED | 0.549 | FAIL | +0.003398 | +0.010934 |
| equal_game | B_brier | -0.002430 | -0.008223 | +0.003104 | UNDERPOWERED | 0.294 | pass | -0.003167 | -0.001757 |
| equal_game | C_brier | +0.000498 | -0.005739 | +0.006998 | UNDERPOWERED | 2.038 | FAIL | -0.000520 | +0.001189 |
| equal_game | D_brier | +0.002696 | -0.004368 | +0.010045 | UNDERPOWERED | 0.409 | pass | +0.001605 | +0.003435 |
| equal_game | B_logloss | -0.007629 | -0.021167 | +0.005518 | UNDERPOWERED | 0.219 | pass | -0.009285 | -0.006000 |
| equal_game | C_logloss | +0.001154 | -0.014699 | +0.017601 | UNDERPOWERED | 2.517 | FAIL | -0.001763 | +0.002552 |
| equal_game | D_logloss | +0.006857 | -0.011383 | +0.025913 | UNDERPOWERED | 0.524 | FAIL | +0.003286 | +0.008438 |

### all_tick / phase 1-3 -- n_ticks 8085, n_games 134

| weighting | comparison | point | ci95 low | ci95 high | verdict | share (game) | concentration | LOO low | LOO high |
|---|---|---|---|---|---|---|---|---|---|
| tick | B_brier | -0.007300 | -0.017295 | +0.002783 | UNDERPOWERED | 0.242 | pass | -0.008893 | -0.005627 |
| tick | C_brier | -0.002418 | -0.013348 | +0.007591 | UNDERPOWERED | 0.826 | FAIL | -0.004458 | -0.000431 |
| tick | D_brier | +0.002702 | -0.012277 | +0.015800 | UNDERPOWERED | 1.412 | FAIL | +0.000218 | +0.006614 |
| tick | B_logloss | -0.015390 | -0.037213 | +0.006643 | UNDERPOWERED | 0.281 | pass | -0.018979 | -0.011257 |
| tick | C_logloss | -0.004894 | -0.030363 | +0.017287 | UNDERPOWERED | 1.019 | FAIL | -0.009097 | +0.000096 |
| tick | D_logloss | +0.006465 | -0.026765 | +0.035626 | UNDERPOWERED | 1.400 | FAIL | +0.001290 | +0.015744 |
| equal_game | B_brier | -0.003406 | -0.011068 | +0.004112 | UNDERPOWERED | 0.226 | pass | -0.004161 | -0.002658 |
| equal_game | C_brier | -0.000011 | -0.009004 | +0.008068 | UNDERPOWERED | 111.347 | FAIL | -0.001205 | +0.001002 |
| equal_game | D_brier | +0.004009 | -0.007384 | +0.013753 | UNDERPOWERED | 0.487 | pass | +0.002542 | +0.006005 |
| equal_game | B_logloss | -0.007420 | -0.024416 | +0.009059 | UNDERPOWERED | 0.257 | pass | -0.009398 | -0.005584 |
| equal_game | C_logloss | +0.001404 | -0.019037 | +0.020497 | UNDERPOWERED | 2.084 | FAIL | -0.001533 | +0.003984 |
| equal_game | D_logloss | +0.010402 | -0.015629 | +0.033712 | UNDERPOWERED | 0.445 | pass | +0.007355 | +0.015142 |

### all_tick / phase 4-6 -- n_ticks 6988, n_games 135

| weighting | comparison | point | ci95 low | ci95 high | verdict | share (game) | concentration | LOO low | LOO high |
|---|---|---|---|---|---|---|---|---|---|
| tick | B_brier | -0.001457 | -0.010440 | +0.007557 | UNDERPOWERED | 1.380 | FAIL | -0.003534 | +0.000333 |
| tick | C_brier | +0.002356 | -0.007189 | +0.012596 | UNDERPOWERED | 1.213 | FAIL | -0.000511 | +0.004150 |
| tick | D_brier | +0.003354 | -0.006109 | +0.013530 | UNDERPOWERED | 0.848 | FAIL | +0.000521 | +0.004751 |
| tick | B_logloss | -0.006397 | -0.028606 | +0.015535 | UNDERPOWERED | 0.823 | FAIL | -0.011181 | -0.001147 |
| tick | C_logloss | +0.006568 | -0.019104 | +0.032804 | UNDERPOWERED | 1.007 | FAIL | -0.000050 | +0.011820 |
| tick | D_logloss | +0.010227 | -0.015311 | +0.036680 | UNDERPOWERED | 0.644 | FAIL | +0.003713 | +0.014467 |
| equal_game | B_brier | -0.004469 | -0.010729 | +0.001652 | UNDERPOWERED | 0.235 | pass | -0.005291 | -0.003445 |
| equal_game | C_brier | -0.001981 | -0.009059 | +0.005118 | UNDERPOWERED | 0.561 | FAIL | -0.003117 | -0.000964 |
| equal_game | D_brier | -0.001436 | -0.008771 | +0.005789 | UNDERPOWERED | 0.771 | FAIL | -0.002561 | -0.000654 |
| equal_game | B_logloss | -0.013915 | -0.029623 | +0.001008 | UNDERPOWERED | 0.223 | pass | -0.015811 | -0.010899 |
| equal_game | C_logloss | -0.004968 | -0.024054 | +0.014390 | UNDERPOWERED | 0.733 | FAIL | -0.008672 | -0.001980 |
| equal_game | D_logloss | -0.003022 | -0.023168 | +0.017641 | UNDERPOWERED | 1.271 | FAIL | -0.006914 | +0.000121 |

### all_tick / phase 7-9+ -- n_ticks 4846, n_games 124

| weighting | comparison | point | ci95 low | ci95 high | verdict | share (game) | concentration | LOO low | LOO high |
|---|---|---|---|---|---|---|---|---|---|
| tick | B_brier | +0.000456 | -0.003547 | +0.004847 | UNDERPOWERED | 2.407 | FAIL | -0.000650 | +0.000978 |
| tick | C_brier | +0.000551 | -0.004673 | +0.006487 | UNDERPOWERED | 3.254 | FAIL | -0.001258 | +0.001372 |
| tick | D_brier | +0.001312 | -0.004584 | +0.008306 | UNDERPOWERED | 1.695 | FAIL | -0.000923 | +0.002188 |
| tick | B_logloss | +0.000306 | -0.011943 | +0.014220 | UNDERPOWERED | 13.489 | FAIL | -0.003867 | +0.001532 |
| tick | C_logloss | +0.001850 | -0.015627 | +0.023900 | UNDERPOWERED | 4.096 | FAIL | -0.005797 | +0.003548 |
| tick | D_logloss | +0.005063 | -0.016089 | +0.033300 | UNDERPOWERED | 2.087 | FAIL | -0.005573 | +0.007123 |
| equal_game | B_brier | +0.000454 | -0.003147 | +0.004226 | UNDERPOWERED | 1.604 | FAIL | -0.000276 | +0.000911 |
| equal_game | C_brier | +0.001389 | -0.003245 | +0.006465 | UNDERPOWERED | 0.855 | FAIL | +0.000203 | +0.001999 |
| equal_game | D_brier | +0.001275 | -0.003532 | +0.006995 | UNDERPOWERED | 1.155 | FAIL | -0.000199 | +0.001919 |
| equal_game | B_logloss | -0.003707 | -0.014170 | +0.007637 | UNDERPOWERED | 0.737 | FAIL | -0.006493 | -0.002759 |
| equal_game | C_logloss | -0.000439 | -0.014867 | +0.016939 | UNDERPOWERED | 11.426 | FAIL | -0.005502 | +0.000790 |
| equal_game | D_logloss | +0.000379 | -0.017006 | +0.021612 | UNDERPOWERED | 18.475 | FAIL | -0.006675 | +0.001674 |

### state_transition_tick / overall -- n_ticks 9318, n_games 135

| weighting | comparison | point | ci95 low | ci95 high | verdict | share (game) | concentration | LOO low | LOO high |
|---|---|---|---|---|---|---|---|---|---|
| tick | B_brier | -0.002415 | -0.008196 | +0.003207 | UNDERPOWERED | 0.343 | pass | -0.003098 | -0.001602 |
| tick | C_brier | +0.000324 | -0.005889 | +0.006763 | UNDERPOWERED | 2.709 | FAIL | -0.000559 | +0.001047 |
| tick | D_brier | +0.002481 | -0.004516 | +0.009593 | UNDERPOWERED | 0.432 | pass | +0.001419 | +0.003364 |
| tick | B_logloss | -0.007370 | -0.021348 | +0.006294 | UNDERPOWERED | 0.303 | pass | -0.008936 | -0.005186 |
| tick | C_logloss | +0.000423 | -0.015330 | +0.016788 | UNDERPOWERED | 5.180 | FAIL | -0.001784 | +0.002394 |
| tick | D_logloss | +0.005823 | -0.012614 | +0.024185 | UNDERPOWERED | 0.569 | FAIL | +0.002532 | +0.007773 |
| equal_game | B_brier | -0.002025 | -0.007663 | +0.003360 | UNDERPOWERED | 0.341 | pass | -0.002723 | -0.001344 |
| equal_game | C_brier | +0.000883 | -0.005337 | +0.007482 | UNDERPOWERED | 1.010 | FAIL | -0.000009 | +0.001576 |
| equal_game | D_brier | +0.002952 | -0.004185 | +0.010083 | UNDERPOWERED | 0.369 | pass | +0.001877 | +0.003707 |
| equal_game | B_logloss | -0.006705 | -0.020273 | +0.006798 | UNDERPOWERED | 0.264 | pass | -0.008339 | -0.004970 |
| equal_game | C_logloss | +0.001729 | -0.014193 | +0.018096 | UNDERPOWERED | 1.756 | FAIL | -0.001317 | +0.003300 |
| equal_game | D_logloss | +0.007031 | -0.010992 | +0.025443 | UNDERPOWERED | 0.467 | pass | +0.003776 | +0.008699 |

### state_transition_tick / phase 1-3 -- n_ticks 3479, n_games 134

| weighting | comparison | point | ci95 low | ci95 high | verdict | share (game) | concentration | LOO low | LOO high |
|---|---|---|---|---|---|---|---|---|---|
| tick | B_brier | -0.003017 | -0.010703 | +0.004563 | UNDERPOWERED | 0.323 | pass | -0.003856 | -0.002064 |
| tick | C_brier | +0.001551 | -0.007327 | +0.009423 | UNDERPOWERED | 0.860 | FAIL | +0.000218 | +0.002795 |
| tick | D_brier | +0.006538 | -0.005024 | +0.016869 | UNDERPOWERED | 0.354 | pass | +0.004903 | +0.008929 |
| tick | B_logloss | -0.006734 | -0.023825 | +0.010191 | UNDERPOWERED | 0.375 | pass | -0.009349 | -0.004369 |
| tick | C_logloss | +0.004178 | -0.016245 | +0.022268 | UNDERPOWERED | 0.738 | FAIL | +0.001169 | +0.007320 |
| tick | D_logloss | +0.015325 | -0.011023 | +0.038814 | UNDERPOWERED | 0.360 | pass | +0.011482 | +0.021024 |
| equal_game | B_brier | -0.002755 | -0.010194 | +0.004691 | UNDERPOWERED | 0.278 | pass | -0.003499 | -0.002004 |
| equal_game | C_brier | +0.001195 | -0.007770 | +0.009034 | UNDERPOWERED | 1.000 | FAIL | -0.000000 | +0.002305 |
| equal_game | D_brier | +0.005201 | -0.006214 | +0.015093 | UNDERPOWERED | 0.399 | pass | +0.003729 | +0.007329 |
| equal_game | B_logloss | -0.006296 | -0.023042 | +0.009981 | UNDERPOWERED | 0.316 | pass | -0.008346 | -0.004436 |
| equal_game | C_logloss | +0.003847 | -0.016838 | +0.023121 | UNDERPOWERED | 0.771 | FAIL | +0.000889 | +0.006655 |
| equal_game | D_logloss | +0.012831 | -0.013237 | +0.035964 | UNDERPOWERED | 0.385 | pass | +0.009772 | +0.017910 |

### state_transition_tick / phase 4-6 -- n_ticks 3470, n_games 135

| weighting | comparison | point | ci95 low | ci95 high | verdict | share (game) | concentration | LOO low | LOO high |
|---|---|---|---|---|---|---|---|---|---|
| tick | B_brier | -0.003571 | -0.010184 | +0.002637 | UNDERPOWERED | 0.321 | pass | -0.004456 | -0.002445 |
| tick | C_brier | -0.000751 | -0.008151 | +0.006577 | UNDERPOWERED | 1.550 | FAIL | -0.001806 | +0.000416 |
| tick | D_brier | -0.000254 | -0.007670 | +0.007048 | UNDERPOWERED | 4.543 | FAIL | -0.001423 | +0.000663 |
| tick | B_logloss | -0.011381 | -0.027396 | +0.004627 | UNDERPOWERED | 0.294 | pass | -0.013657 | -0.008105 |
| tick | C_logloss | -0.001632 | -0.021082 | +0.017990 | UNDERPOWERED | 2.057 | FAIL | -0.004825 | +0.001740 |
| tick | D_logloss | +0.000257 | -0.020489 | +0.020741 | UNDERPOWERED | 12.942 | FAIL | -0.003095 | +0.002984 |
| equal_game | B_brier | -0.004286 | -0.010534 | +0.001875 | UNDERPOWERED | 0.245 | pass | -0.005165 | -0.003258 |
| equal_game | C_brier | -0.001896 | -0.009043 | +0.005234 | UNDERPOWERED | 0.564 | FAIL | -0.002948 | -0.000834 |
| equal_game | D_brier | -0.001297 | -0.008461 | +0.005973 | UNDERPOWERED | 0.798 | FAIL | -0.002349 | -0.000463 |
| equal_game | B_logloss | -0.012912 | -0.028738 | +0.002277 | UNDERPOWERED | 0.238 | pass | -0.015174 | -0.009918 |
| equal_game | C_logloss | -0.004368 | -0.023425 | +0.014422 | UNDERPOWERED | 0.809 | FAIL | -0.007959 | -0.001294 |
| equal_game | D_logloss | -0.002256 | -0.022412 | +0.018185 | UNDERPOWERED | 1.651 | FAIL | -0.006024 | +0.000291 |

### state_transition_tick / phase 7-9+ -- n_ticks 2369, n_games 124

| weighting | comparison | point | ci95 low | ci95 high | verdict | share (game) | concentration | LOO low | LOO high |
|---|---|---|---|---|---|---|---|---|---|
| tick | B_brier | +0.000162 | -0.004032 | +0.004457 | UNDERPOWERED | 5.512 | FAIL | -0.000737 | +0.000639 |
| tick | C_brier | +0.000098 | -0.004805 | +0.005413 | UNDERPOWERED | 14.188 | FAIL | -0.001312 | +0.000735 |
| tick | D_brier | +0.000530 | -0.005163 | +0.006511 | UNDERPOWERED | 3.158 | FAIL | -0.001156 | +0.001203 |
| tick | B_logloss | -0.002431 | -0.015071 | +0.010646 | UNDERPOWERED | 1.395 | FAIL | -0.005885 | -0.001311 |
| tick | C_logloss | -0.002080 | -0.018559 | +0.016548 | UNDERPOWERED | 2.806 | FAIL | -0.007999 | -0.000644 |
| tick | D_logloss | +0.000021 | -0.019978 | +0.023324 | UNDERPOWERED | 385.582 | FAIL | -0.007973 | +0.001714 |
| equal_game | B_brier | +0.000487 | -0.003165 | +0.004139 | UNDERPOWERED | 1.397 | FAIL | -0.000195 | +0.000904 |
| equal_game | C_brier | +0.001339 | -0.003137 | +0.006441 | UNDERPOWERED | 0.797 | FAIL | +0.000274 | +0.001902 |
| equal_game | D_brier | +0.000848 | -0.003944 | +0.006099 | UNDERPOWERED | 1.508 | FAIL | -0.000434 | +0.001435 |
| equal_game | B_logloss | -0.003576 | -0.014165 | +0.008203 | UNDERPOWERED | 0.725 | FAIL | -0.006218 | -0.002684 |
| equal_game | C_logloss | -0.001359 | -0.015411 | +0.015093 | UNDERPOWERED | 3.282 | FAIL | -0.005865 | -0.000220 |
| equal_game | D_logloss | -0.001643 | -0.018020 | +0.018183 | UNDERPOWERED | 3.678 | FAIL | -0.007750 | -0.000462 |

## Reading the table honestly (calibration language only)

- Arm B (recalibrated market) has a negative point difference in most cells (tick-weighted overall Brier -0.003363, log-loss -0.008416) with a
  leave-one-game-out range that stays negative overall, but every interval contains zero: UNDERPOWERED, not AHEAD.
- Arm C (market + state) sits at zero in the overall cells (tick-weighted Brier -0.000021): on this window the declared state features
  add nothing the market mid does not already carry. Its concentration ratios blow up (the total difference is near zero, so a single
  game dominates the ratio); the concentration check therefore FAILS for most C cells and the point is not interpretable.
- Arm D (C + model) has a positive point difference in every overall cell (tick-weighted Brier +0.002593, log-loss +0.007444) with a
  leave-one-game-out range wholly positive overall: adding the model probability made the fit WORSE than the market on this window,
  though the interval still spans zero. This is the opposite direction from an in-game conditioning claim and is recorded as such.
- Phase 7-9+ (late game) differences are the smallest in magnitude and the most concentrated; nothing there is interpretable.
- Nothing here is a fill, a markout or a fee-netted figure; nothing here is a forward measurement. The market is not beaten.

## What this result does and does not license

- It DOES: fix the corrected MLB baseline the prereg asked for; show that on 135 scored games the recalibrated market is the only arm
  whose point sits below the market, and that the model arm sits above it; close the S347 question at UNDERPOWERED under Q3.
- It DOES NOT: license any AHEAD statement, any in-game conditioning claim, or any change to the bars; a second powered corpus is
  still required for any directional claim (row S382 draft, NBA), and the model arm has unknown parameter provenance there (S385).
- No re-run is permitted. Attempt 2 exists only for a crash and was not needed.

## NOT VERIFIED

- Any second window or second corpus; any forward game; any fill-conditional figure.
- Per-arm means (the summary schema carries differences only; the audit reports C.means NOT_AUDITABLE, non-critical).
- The concentration diagnostics for cells whose total difference is near zero (ratios above 1 are a division artifact, not evidence).

## CORRECTION (2026-09-22 01:2xZ, after an independent attestation by a codex gpt-5.6-sol lane; supersedes the four prose sentences named below -- the numbers, tables, accounting and audit statements were attested as exact)

The attestation compared every cell, the accounting sentence and the audit file against the saved output: 96 of 96 cells match at
printed precision, no cell is missing or extra, all 96 verdict strings are UNDERPOWERED, accounting and audit statements match. Four
sentences in "Reading the table honestly" overstate what intervals that span zero can say and are WITHDRAWN as written:
1. "B is the only arm whose point sits below the market in the overall cells" -- NOT SUPPORTED: all_tick / overall / tick /
   C_brier is also below zero (-0.000021). Correct statement: B is the only arm whose point is below zero in EVERY overall cell.
2. "C sits at zero ... the declared state features add nothing the market mid does not already carry" -- NOT SUPPORTED as a
   conclusion: no overall C point equals zero (the tick-weighted Brier point is -0.000021 and the largest-magnitude overall C point
   is +0.001729 log-loss on transitions), and an interval spanning zero does not license "adds nothing". Correct statement: on
   this window the data do not distinguish arm C from the market in any overall cell.
3. "concentration fails where the total difference is near zero (ratio artifact)" -- NOT SUPPORTED as a criterion: the concentration
   flag is set by the preregistered share rule (largest single-game absolute share <= 0.5) and by nothing else. Correct statement:
   the share rule fires in most C and D cells and in every late-game cell; several ratios exceed 1, which happens when the summed
   difference is small relative to a single game's contribution; that is an observation about the ratio, not a rule.
4. "adding the model probability made the fit WORSE than the market on this window" -- WITHDRAWN as a conclusion: D's point is above
   the market in every overall cell and every overall leave-one-game-out range is wholly positive (attested), but every interval
   spans zero, so the window does not establish that D is worse; it establishes only that D is not AHEAD and not BEHIND here.
Nothing in this memo is an AHEAD or in-game conditioning conclusion. The tables stand unchanged.

