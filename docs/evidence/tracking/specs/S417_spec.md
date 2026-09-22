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

AMENDMENT 1 (2026-09-22 22:5xZ; binding; the first codex build lane stopped correctly on a contradiction between CHANGE item
(the primary becomes C-minus-B) and the byte-identical rule for every landed test: tests/platformkit/ingame/
test_nba_four_arm_trial.py:75-78 computes C-minus-A and asserts the primary equals it). RULING: this row is the one deliberate,
pre-seal change of the PRIMARY contrast, so the additivity rule is restated precisely: (a) every existing cell VALUE stays
byte-identical -- the C-minus-A contrasts keep their numbers and are re-emitted under the keys C_minus_A_<metric> labelled
SECONDARY; (b) the primary cells brier / logloss are computed as C-minus-B through the same machinery, and C_minus_B_<metric>
keys carry the same values (so an auditor can check either name); (c) the B_lag arm and its C_minus_Blag_<metric> cells are added
as specified; (d) EXACTLY ONE landed test assertion may change: tests/platformkit/ingame/test_nba_four_arm_trial.py:75-78 (the
expectation that the primary equals C-minus-A becomes C-minus-B, with the C-minus-A value asserted under its new secondary
key), quoted before / after in the memo; any golden fixture that pins the old primary is regenerated once and its diff quoted;
every other landed test file and nba_four_arm_trial_guards.py stay byte-identical; (e) the S395 auditor reconstructs the primary
per the prereg's DECLARED arms (C versus B after this row) -- recorded as the auditor's next amendment, not this row's scope;
(f) the memo names the draft-prereg amendments (a) and (b) this row unblocks and the do-not-seal items 9-11 it closes.

AMENDMENT 2 (2026-09-22 23:1xZ; binding; the third codex lane stopped correctly: tests/platformkit/ingame/
test_baseline_four_arm_period.py:277 asserts the comparisons key set EQUALS {B_*, C_*} for every metric, so any added
C_minus_B_* key fails it). RULING: a SECOND landed assertion is authorized to change, and only this one: the equality at
test_baseline_four_arm_period.py:277 becomes a superset assertion -- every landed key {B_*, C_*} must still be present with
its landed value, and the new keys are asserted separately by their own names; the before / after is quoted in the memo. No
other landed assertion changes; the ownership check compares against the lane's own HEAD (differences that exist only because
master gained spec commits during the run are not the lane's).

AMENDMENT 3 (2026-09-22 23:1xZ; binding; the fourth codex lane stopped correctly on a third exact-key-set assertion:
tests/platformkit/ingame/test_baseline_four_arm_nba.py:90 asserts set(r['paired_losses']) == set('ABCD'), which adding the B_lag
arm necessarily fails). RULING, general for this row: adding an arm to a landed producer cannot leave every landed test
byte-identical, so the rule is stated by CLASS instead of by line -- any landed assertion that pins an EXACT key set of arms,
comparisons or paired_losses (an equality against a fixed set of names) may become a SUPERSET assertion: every landed key must
still be present with its landed value, and the new keys (B_lag, C_minus_B_*, C_minus_Blag_*, C_minus_A_*, D_minus_B_*) are
asserted separately by name; the memo lists every touched landed test file and line with the before / after text. No landed
assertion of any other kind may change, no landed VALUE may change, nba_four_arm_trial_guards.py stays byte-identical, and the
primary switch of AMENDMENT 1 stands. Enumerate the exact-set assertions BEFORE editing (grep for "== set(" and "== {" across
tests/platformkit/ingame/test_baseline_four_arm*.py and test_nba_four_arm_trial*.py) and report the list.

AMENDMENT 4 (2026-09-22 23:2xZ; binding; the fifth codex lane stopped correctly: tests/platformkit/ingame/test_nba_four_arm_trial.py:79
asserts the primary's period-first mean DIFFERS from the tick mean (the FIX 1c invariant), and on the landed fixture the C-minus-B
period-first mean equals the tick mean within 1.5e-16 for Brier and 2.9e-16 for logloss -- a fixture artifact, not a machinery
defect: the fixture's per-game tick counts make the C-minus-B deltas average identically). RULING: the inequality assertion STAYS
(it protects the period-first machinery); the lane is authorized to EXTEND that test's fixture with additional scored ticks so
that per-game tick counts differ across games and the primary's period-first mean differs from the tick mean under C-minus-B by
more than the assertion's tolerance -- the extension must keep every other assertion in that file passing, and the memo quotes
the fixture rows added and the two means before / after. If the inequality still cannot be made to hold without weakening it,
STOP and report the arithmetic. No other landed assertion changes beyond AMENDMENTS 1-3.

AMENDMENT 5 (2026-09-22 23:3xZ; binding; the sixth codex lane stopped correctly: extending the fixture breaks the landed count
assertions at tests/platformkit/ingame/test_nba_four_arm_trial.py:63 (exactly 15 paired rows), :65 (11 scored ticks), :66 (15
input ticks)). RULING, for that ONE landed test file only: tests/platformkit/ingame/test_nba_four_arm_trial.py may be updated in
its fixture AND in every assertion whose expected value is DERIVED from that fixture (row, tick and game counts; the primary-equals-
contrast expectation of AMENDMENT 1(d); the exact-key-set assertions of AMENDMENT 3), provided the INVARIANTS those assertions
protect are still asserted (the primary's period-first mean differs from the tick mean; the primary equals the declared contrast
computed by the test's own arithmetic; the count assertions match the extended fixture exactly; every landed key present). Before
editing, the lane enumerates every assertion in that file that references a fixture-derived constant and lists them in the memo
with before / after text. Every OTHER landed test file stays byte-identical except the exact-key-set class of AMENDMENT 3; guards
byte-identical; no landed VALUE in any producer output changes.

AMENDMENT 6 (2026-09-23 00:4xZ; binding; the seventh codex lane (attempt g) stopped correctly: the landed S402 auditor
scripts/platformkit/ingame/four_arm_output_audit_checks.py:68 requires set(paired_losses) == {A,B,C,D} and its NBA test asserts
the same, so a B_lag arm cannot pass the auditor). RULING: the auditor's exact-ABCD assertions are the exact-key-set class of
AMENDMENT 3. four_arm_output_audit_checks.py may be widened ADDITIVELY for the single key B_lag: A, B, C, D stay required; B_lag is
the only permitted additional key; when present its paired loss is None exactly when the row's B_lag probability is None (the lag
subset excluded the tick) and otherwise a number in (0, 1) consistent with the row's outcome; the per-arm range loop covers B_lag
the same way; every other auditor check is byte-identical in behaviour (the landed S402 fixtures audit to the same verdicts; an
output without B_lag still passes). The auditor's test file takes the superset assertion plus one construct with B_lag present
and one with a stale B_lag loss refused. S402's real audit was run before B_lag existed; the orchestrator re-runs it after S417
lands and records the result in the S402 memo. ALSO BINDING: S405 landed on master (b66352c69 + fix) and changed
nba_four_arm_trial.py under this row (D-minus-C contrast, all-arm loss consistency, contrast test file (fifty-four tests) whose size pin reads
git show b66352c69). The S417 candidate rebases onto master first (stash, ff, pop); every S405 value and check is kept; the
S405 contrast test file passes unchanged. If a conflict cannot be resolved without changing a landed S405 value, the lane stops.

AMENDMENT 7 (2026-09-23 01:1xZ; binding; the orchestrator rebased the attempt-g candidate onto the landed S405 runner (the codex
sandbox cannot write git metadata) and ran S405's contrast test file on the merged code: 8 of fifty-four FAIL --
test_additive_output, test_corrupted_d_row_moves_only_d_contrast, test_one_game_or_empty_has_exact_keys_and_serializes[g1,g2],
test_every_runner_output_is_additive[3 cases], test_powered_descriptive_convention). Two distinct causes. (a) A DEFECT, not a
test to update: on S405's own 30-game construct (no B_lag anywhere) the merged code REFUSES every row -- Refused
inconsistent_paired_loss 150 of 150 -- so rows without B_lag no longer validate as landed. RULING: rows without a B_lag
probability or loss validate exactly as the landed S405 code (byte-identical verdicts on S405's fixtures); B_lag's loss is
validated only when the row carries it; the lane names the line that caused the refusal in the memo. (b) THE EXACT-KEY-SET /
GOLDEN CLASS, for that ONE landed test file only: tests/platformkit/ingame/test_nba_four_arm_trial_contrast.py may be updated in
exactly the assertions that pin the landed primary's identity and the exact key sets -- the primary is now period-first
C-minus-B (its cell equals the landed C_minus_B comparison), the landed C-minus-A cell is preserved VERBATIM under the
C_minus_A_{brier,logloss} aliases, and the additive keys b_lag_subset / B_lag / C_minus_A_* are the only permitted differences in
the golden byte comparison against the landed runner (every other byte identical). Before editing, the lane enumerates every
assertion it changes with before / after text in the memo; every other S405 test stays byte-identical; the S405 validation
(all-arm both-metric loss consistency), the D-minus-C contrast at 1e-12 and the DESCRIPTIVE / interval_verdict convention keep
their landed behaviour and values.
