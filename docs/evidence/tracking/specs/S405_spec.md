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

AMENDMENT 2 (2026-09-22 21:3xZ; binding; from the astra round-2 critique on fix 1b; the paired sol contract verdict
for round 2 was never produced and this amendment does not wait on it). (a) THE CANONICAL SORT NEVER REACHES A
PRE-EXISTING OUTPUT: MEASURED -- the AMENDMENT 1(b) sort is applied at nba_four_arm_trial.py:172 before predictions
are saved and again at :178 for primary predictions, so the saved row list reorders (g2:6, an OT row, moves from
after g2:5 to before g2:1) and existing fold_training_sizes reorders (January 1,6,11 becomes 6,11,1 for games
z0,a1,b2) -- a pre-existing output changed, which the B2 rule forbids. RULING: the canonical (game_id, phase, key)
sort is applied ONLY to the rows the S405 contrast consumes, in a local copy; every pre-existing writer keeps
insertion order byte for byte. Test: capture every output of the landed runner and of the candidate on the synthetic
fixture containing OT, remove ONLY the S405 fields, and compare serialized bytes -- the current golden test compares
_primary alone and must be widened.
(b) A POWERED CONTRAST KEEPS THE DESCRIPTIVE CONVENTION: MEASURED -- on 30 synthetic games spanning all four periods
the existing D cell reports verdict="DESCRIPTIVE" with interval_verdict="BEHIND", while the contrast inserted at
nba_four_arm_trial.py:104 (after _label has run) reports "BEHIND" in BOTH fields, though both labels remain
"SECONDARY DESCRIPTIVE". RULING: the contrast cell carries the same two-field convention as every existing secondary
cell -- verdict stays DESCRIPTIVE and only interval_verdict carries the direction -- whether the contrast is powered
or underpowered. Test: a 30-game fixture (the fixture's complete scored game replicated across 30 distinct ids)
asserts verdict="DESCRIPTIVE" and the directional value in interval_verdict; the existing tests exercise only
UNDERPOWERED, which AMENDMENT 1(e) required.
(c) THE DIAGNOSTICS ARE ASSERTED INDEPENDENTLY: MEASURED -- the leave-one-game-out range and the concentration value
reproduce, but only through the interval assertions, which would also pass if either diagnostic were wrong in a way
the interval absorbs. RULING: leave_one_game_out_range and largest_absolute_share each carry their OWN assertion
against an independently computed expectation, not against the interval. Tests: the fixture asserts both values
directly and a planted single-game perturbation moves each one in the expected direction.
(d) ONE-GAME KEYS ARE KEPT: MEASURED -- the complete one-game fixture preserves five scored keys with UNDERPOWERED
and serializes successfully, and empty input produces []; this follows AMENDMENT 1(e) and contradicts the reviewer's
requested one-game []. RULING: AMENDMENT 1(e) STANDS -- scored_keys lists exactly the rows scored and is never
emptied by an underpowered verdict; the one-game [] expectation is withdrawn and the memo records the adjudication.
Test: the one-game fixture asserts five keys with verdict UNDERPOWERED and a byte-identical repeat serialization.
(e) THE MEMO'S SOURCE SIZE IS RE-MEASURED: MEASURED -- the memo at S405_four_arm_contrast_2026-09-22.md:131 claims
12,994 bytes while the current test file is 13,085 bytes, and the historical figure cannot be reproduced from this
candidate. RULING: a size recorded in a memo is measured against the candidate at the moment the memo is written and
is re-measured whenever the file changes; an unreproducible historical size is removed rather than carried. Test:
the memo's stated size equals the byte size of the named file in the candidate tree.

AMENDMENT 3 (2026-09-22 23:2xZ; binding; from the astra round-3 critique on fix 1c -- every round-2 item reproduced closed; one
new blocker). LOSS CONSISTENCY COVERS EVERY ARM: MEASURED -- the AMENDMENT 1(d) validation recomputes only the C and D losses, so
a stale REFERENCE-arm loss contaminates both reported subset cells and cancels in their difference: changing
g2:1.d_subset.paired_losses.A.brier from 0.25 to 0.35 with probabilities and outcome unchanged was ACCEPTED, subset-C moved
0.06 -> 0.035 and D 0.14 -> 0.115 while the contrast stayed 0.08 (nba_four_arm_trial.py:33, 100-103); the same passes for
logloss. RULING: every saved arm loss in the subset rows (A, B, C, D; both metrics) is recomputed from the row's probability and
outcome and must agree to 1e-12, else inconsistent_paired_loss names the arm, the row key and the metric; a test plants the A
corruption above and one per other arm. NOTED, unchanged: the reported cells are computed immediately before the contrast by the
normal runner path, so the equality assertion proves the difference, not each cell's agreement with the rows -- the arm-loss
validation is what ties the cells to the rows.
