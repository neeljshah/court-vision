GAP S405 | sport nba | worktree harness-h66 (master-based) | log cx_s405_four_arm_contrast
# S394 follow-up: the landed NBA trial runner emits the D-minus-C contrast and the D-subset scored keys (additive)

SINGLE PROBLEM: the landed S394 runner (scripts/platformkit/ingame/nba_four_arm_trial.py, landed 2026-09-22) emits NO
D_minus_C_<metric> contrast cell and NO d_subset.scored_keys, both named in the S395 auditor's CHANGE clause; S395 AMENDMENT 3
therefore audits them as NOT_AUDITABLE producer gaps (reason producer_field_absent). The NBA trial is ONE charge (K = 20): the
runner must emit both BEFORE the seal so the audit of the charged trial has no producer gap.

BINDING BEFORE-CONDITION: quote from master (a) nba_four_arm_trial.py: the _primary(...) function and the secondaries block it
writes (secondaries.comparisons keys B_* / C_* / D_*, secondaries.d_subset, secondaries.game_first, the PRIMARY / SECONDARY /
SECONDARY DESCRIPTIVE labels, interval_verdict); (b) baseline_four_arm.py _comparison_cell (point, ci95, verdict, leave_one_
game_out_range, largest_absolute_share, concentration_pass) and cluster_bootstrap in gate_a0_ingame_vs_market; (c) the S382 draft
prereg's stated secondaries (docs/evidence/ingame/, the D-vs-C contrast sentence) -- quote it verbatim; (d) S395 AMENDMENT 3.

CHANGE (this row MODIFIES the landed module nba_four_arm_trial.py; owned files: nba_four_arm_trial.py, NEW
tests/platformkit/ingame/test_nba_four_arm_trial_contrast.py, memo docs/evidence/harness/S405_four_arm_contrast_2026-09-22.md;
nba_four_arm_trial_guards.py and every landed test file stay byte-identical):
1. secondaries.comparisons gains D_minus_C_<metric> for metric in (brier, logloss): the paired-loss contrast of arm D against arm
   C over the D-subset rows (the SAME rows and folds the D_* cells use), computed through the landed _comparison_cell machinery
   with C as the reference arm (never a re-declared bootstrap; N_BOOT / SEED / N_MIN_GAMES imported), carrying point, ci95,
   verdict, leave_one_game_out_range, largest_absolute_share, concentration_pass, labelled SECONDARY like the D_* cells.
2. secondaries.d_subset.scored_keys: the sorted list of the row keys scored in the D subset (excluding warm-up rows), exactly the
   population the D_* and D_minus_C_* cells were computed over; d_subset.n_scored equals its length.
3. Nothing existing changes: every key the runner wrote before this row is byte-identical on the same input (B2 additive); the
   primary cells, labels and interval_verdict are untouched. A construct test runs the runner on a small synthetic primary_rows
   fixture before and after (the landed output captured as a fixture) and asserts equality of every pre-existing key plus the
   two new fields; a second test corrupts one D-subset row and shows D_minus_C_brier.point moves while C_brier does not.
4. Memo: before-condition quotes, the exact new fields with one worked example, the S395 checks they satisfy (D.contrast_d_minus_c,
   D.scored_keys), ends with NOT VERIFIED.

CONTROLS: PREPARE only -- no real corpus, no charged trial, no seal, no ledger row; construct tests only; per-file tests one at a
time; no network; never write data/registry; never edit the S382 draft. ACCEPTANCE: per-file tests pass; contract_preflight FAIL=0;
<= 300 LOC per file; ASCII; contract Q6 vocabulary; the landed test files pass unchanged; memo ends with NOT VERIFIED.


AMENDMENT 1 (2026-09-22 19:0xZ; binding; from the codex sol round-1 verdict and the astra round-1 critique on the terra build).
(a) THE CONTRAST MATCHES THE REPORTED CELLS: the build computed D_minus_C through the tick-weighted helper while the reported D_*
and C_* subset cells use period weighting over the SAVED paired_losses, so the contrast point (0.07285714285714283) did not equal
reported D minus reported subset-C (0.07999999999999996) and its interval differed. RULING: D_minus_C_<metric> is computed with
EXACTLY the machinery, weighting and saved paired_losses the reported D_* and C_* subset cells use, so that D_minus_C.point equals
D.point minus C.point on the subset to 1e-12 and the interval is the paired-delta interval under the same bootstrap; a test asserts
that equality on the fixture. (b) ORDER INDEPENDENCE: the scored rows are canonically sorted by (game_id, phase, key) before any
cell is computed; reversing the fixture yields byte-identical diagnostics (leave_one_game_out_range, largest_absolute_share).
(c) FINITENESS: a non-numeric, boolean, non-finite or out-of-range C or D probability in the subset refuses (exit 3, reason)
before any cell; test with D = inf. (d) LOSS CONSISTENCY: a saved paired_loss that does not equal the loss recomputed from the
row's probability and outcome (to 1e-12) refuses inconsistent_paired_loss -- the contrast never silently uses one while the
reported cell uses the other. (e) ONE-GAME AND EMPTY SUBSETS: scored_keys lists exactly the rows scored (never emptied by an
underpowered verdict); the contrast cell carries verdict UNDERPOWERED with finite or null estimates and no exception; a repeat
serialization of the same input is byte-identical (a permanent assertion).
