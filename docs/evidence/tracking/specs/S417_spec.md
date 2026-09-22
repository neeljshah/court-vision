GAP S417 | sport nba | worktree harness-h72 (master-based) | log cx_s417_c_minus_b_primary
# C-minus-B as the declared primary contrast, plus the lagged-mid arm B_lag as a standing secondary

SINGLE PROBLEM: the landed period module computes EVERY cell against arm A (baseline_four_arm_period.py:193,
`r[arm][metric] - r["A"][metric]`) and the landed NBA runner hardcodes the A-referenced C cell as the primary
(nba_four_arm_trial.py:43-44: `brier = _cell(comparisons["C_brier"])`, `comparison="period-first C-minus-A"`). The
amended NBA prereg declares C-minus-B -- the state residual on top of a RECALIBRATED mid -- as the only quantity the
trial claims, with the lagged-mid arm B_lag as its standing control. Neither is producible by the landed chain, so the
seal cannot license its own primary (nba_prereg_amendments_2026-09-22.md section 2 (a)-(b), do-not-seal items 9-11).

BINDING BEFORE-CONDITION: quote from master (a) baseline_four_arm_period.py:190-196 (the A-hardcoded loop), :123-161
(_primary: the period point, the seed-13 draw stream, discard-and-count, the diagnostics), :38 and :163-196 (arms
"ABCD"), :198-221 (stratified_cells, the d_subset recompute); (b) nba_four_arm_trial.py:41-51 (_primary, the C_brier
selection, the C-minus-A string, the secondaries block), :21-33 (_label: SECONDARY, SECONDARY DESCRIPTIVE,
interval_verdict); (c) baseline_four_arm.py:110-126 (arms per fold), :141-144 (paired_losses over 'ABCD'); (d)
baseline_four_arm_features.py:12-17; (e) gate_a0_ingame_vs_market.py:24, :84-87; (f) amendments (a)-(b) VERBATIM from
nba_prereg_amendments_2026-09-22.md section 2; (g) S405_spec.md AMENDMENT 1(a)-(e), S395_spec.md AMENDMENT 3.

CHANGE (this row MODIFIES landed modules ADDITIVELY -- the S405 rule: every pre-existing output key byte-identical on
the same input. Owned: baseline_four_arm_period.py, baseline_four_arm_features.py, baseline_four_arm.py,
nba_four_arm_trial.py, NEW tests/platformkit/ingame/test_nba_four_arm_primary_contrast.py, memo
docs/evidence/harness/S417_c_minus_b_primary_2026-09-22.md; nba_four_arm_trial_guards.py,
baseline_four_arm_eligibility.py and every landed test file stay byte-identical):
1. REFERENCE-ARM CONTRASTS. Beside the landed `<arm>_<metric>` keys and without touching them, the period module writes
   `C_minus_B_<metric>` and `D_minus_B_<metric>` for metric in (brier, logloss), from the SAME grouped game-period
   structure, saved paired_losses, `_primary` machinery, weighting and seed-13 whole-game draw stream the reported cells
   use. Assert the consequence: `C_minus_B.point` equals the reported `C_<metric>.point` minus `B_<metric>.point` to
   1e-12, and the interval is the paired-delta interval under that one stream, not a difference of two drawn intervals.
2. LAGGED MID. baseline_four_arm_features.py declares `mid_lag`: the market probability of the PREVIOUS eligible tick of
   the same game, strictly earlier in timestamp order, under the identical eligibility and duplicate-key policy; never
   imputed, never back-filled from the contemporaneous mid, never carried across games. A game's first eligible tick is
   ineligible for B_lag ONLY and is counted `no_prior_tick_for_b_lag`. FEATURES['nba'] is unchanged: mid_lag is an arm
   input, not a state feature.
3. THE ARM. The scorer fits `B_lag` on intercept + logit(mid_lag) with the same fixed ridge, step limit and tolerance as
   the other arms, on training rows only; `paired_losses` gains key `B_lag` (null with no prior eligible tick) and a
   `b_lag_subset` mirroring `d_subset`, in which A, B and C are RECOMPUTED on the B_lag-eligible rows with identical
   keys, folds, training populations and weights; `summarize` counts `no_prior_tick_for_b_lag`. stratified_cells gains a
   `b_lag_subset` block mirroring the d_subset block, with `C_minus_Blag_<metric>` and `B_minus_Blag_<metric>` computed
   exactly as item 1. Landed A-D values unchanged.
4. THE RUNNER. `_primary` selects `C_minus_B_brier`, `comparison="period-first C-minus-B"`, `C_minus_B_logloss` as the
   SECONDARY logloss. The A-referenced `C_brier` / `C_logloss` cells are preserved VERBATIM under
   secondaries.comparisons labelled SECONDARY; B_lag cells carry SECONDARY and are never promoted; D cells keep verdict
   DESCRIPTIVE with interval_verdict beside it. Exactly two output changes are intended -- the `comparison` string and
   which cell fills `brier` / `logloss`; everything else byte-identical, and the memo names both.
5. TESTS (construct fixtures, no corpus): (a) a small synthetic primary_rows fixture through stratified_cells and
   trial._primary before and after, asserting every pre-existing key byte-identical plus the new keys present; (b) the
   1e-12 equality of item 1 for both metrics; (c) canonical sort by (game_id, phase, key) -- reversing the fixture
   yields byte-identical diagnostics; (d) a non-finite, boolean or out-of-(0,1) B probability refuses with a counted
   reason before any cell, and a saved paired loss disagreeing with the loss recomputed from the row to 1e-12 refuses
   `inconsistent_paired_loss`; (e) B_lag: each game's first eligible tick counted once, mid_lag never carried across
   games, C_minus_Blag on the subset with A/B/C recomputed there; (f) a one-game fixture is UNDERPOWERED, no exception.
6. MEMO: before-condition quotes; each new key with one worked example; the two intended runner changes; that this row
   unblocks draft amendments (a) and (b) and closes do-not-seal items 9 and 10, while item 11 also needs S405 and S395
   landed with the auditor's primary reconstruction pointed at C_minus_B; ends with NOT VERIFIED.

CONTROLS: PREPARE only -- no real corpus, no charged trial, no seal, no ledger row, no network; construct fixtures only;
per-file tests one at a time; never write data/registry or data/cache; never touch a live capture or a STOP file; never
edit the S382 draft or the sealed MLB prereg. ACCEPTANCE: per-file tests pass one at a time; contract_preflight FAIL=0;
<= 300 LOC per file; ASCII; contract Q6 vocabulary; the landed test files pass unchanged; memo ends NOT VERIFIED.
