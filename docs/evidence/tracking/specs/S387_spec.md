GAP S387 | sport nba (scorer amendment) | worktree harness-h47 (master-based) | log cx_s387_nba_eligibility_amendment
# Scorer eligibility + features amendment for the NBA corpus (the MLB verdict is read; the MLB result artifact is frozen at its commit)

SINGLE PROBLEM: the NBA prereg draft (row S382) cannot be sealed because the landed scorer (a) does not map the corpus name
nba_checkpoints_r1, (b) parses ts / close_ts with datetime.fromisoformat (refuses four- and five-digit fractions), (c) accepts a
fractional quarter or score (a fractional quarter bypasses the post-final rule), and (d) rejects a missing model_prob for EVERY arm,
while the draft requires A / B / C on the full eligible population and D on its paired subset. The sealed MLB trial has been run,
audited and read (2026-09-22), so scorer edits are unblocked; the MLB output stays frozen at the scorer commit the seal pinned.

BINDING BEFORE-CONDITION: `python -m scripts.platformkit.ingame.baseline_four_arm --census-only --corpus-dir
data/cache/ingame_grade_joined/nba_checkpoints_r1 --manifest <any> --out <tmp>` fails with `unmapped corpus` (quote it; the
builder may reproduce this with an EMPTY synthetic directory named nba_checkpoints_r1, never the real one). Read on master and
quote: baseline_four_arm_features.py (CORPORA, FEATURES['nba'], timestamp(), state_fields(), state_eligibility()),
baseline_four_arm_eligibility.py (select_rows, the 'market_prob' / 'model_prob' loop near line 100, the census dict),
baseline_four_arm.py (predict_rows: arms and the D arm's use of features['model']; _cell; summarize), and the S382 draft's
eligibility section. The S347 result memo and its output directory are NOT inputs and must not be opened.

CHANGE (owned files: baseline_four_arm_features.py, baseline_four_arm_eligibility.py, baseline_four_arm.py, the four landed
test files tests/platformkit/ingame/test_baseline_four_arm*.py, NEW tests/platformkit/ingame/test_baseline_four_arm_nba.py, memo):
1. CORPORA maps 'nba_checkpoints_r1' -> 'nba' (and the generic '_r<N>' suffix rule if you can express it without loosening
   anything else; state which).
2. timestamp() routes through scripts.platformkit.execution.venue_time.parse_venue_time (four- and five-digit fractions accepted;
   naive strings refused; NOTHING else about the returned value changes: same UTC canonicalization, same microsecond fidelity; a
   test proves byte-identical isoformat output for every six-digit input the MLB corpus shape uses).
3. state_eligibility for nba: quarter, home_score, away_score must be finite INTEGRAL numbers (bool refused; 3.5 refused with a
   counted reason `non_integral_state`); the post-final rule (quarter >= 4 and seconds_remaining == 0) is unchanged.
4. MODEL-OPTIONAL ARM D: a missing, null, non-finite or out-of-(0,1) model_prob makes a tick ineligible for arm D ONLY, counted
   as `model_prob_missing_for_d`; arms A / B / C are compared on the full eligible population; arm D is compared against A / B / C
   RECOMPUTED on D's paired subset (a new comparison block `d_subset` in the cell, holding B / C / D differences on that subset),
   never D's subset against another arm's full population. For MLB and soccer corpora, where every eligible tick carries a model,
   the full-population cells must be BYTE-IDENTICAL to today's (a test builds a small corpus with model on every tick and asserts
   the summary JSON is unchanged against a golden file the test itself writes from the pre-change code path -- i.e. compute the
   expected once with model-complete rows and assert the d_subset block equals the full block).
5. The census reports the new counts (non_integral_state, model_prob_missing_for_d, ticks eligible for D) as strict ints.
6. Tests: all four landed test files pass UNCHANGED except where they assert the exact CORPORA set (say which lines changed and
   why); the new test file covers 1-5 with synthetic corpora; the S355 self-check still passes.
7. Memo docs/evidence/harness/S387_nba_eligibility_amendment_2026-09-22.md, including a statement that the MLB result artifact
   (summary.json at the sealed scorer commit) is FROZEN and is not re-audited by this change.

CONTROLS: construct tests only, no real corpus, no network, no score. ACCEPTANCE: every touched test file passes one at a time;
--help and --self-check work; <= 300 LOC per file; ASCII; contract Q6 vocabulary (assemble retracted-figure literals from single
digits); the memo ends with a NOT VERIFIED list. The pod is OFF.

AMENDMENT 1 (2026-09-22 01:5xZ; binding; the first verifier round found a contract B2 break: model-optional NBA rows no longer
carry D at top level, and two LANDED READERS require A / B / C / D -- scripts/platformkit/ingame/baseline_four_arm_period.py (row
S383) and four_arm_output_audit_checks.py (row S379)). Rules: (1) ROW SHAPE IS ADDITIVE: every paired row keeps the keys A, B, C, D
and paired_losses for all four arms; on a tick ineligible for D the value of D and of paired_losses['D'] is null (never a
fabricated number, never the market), and a new boolean `d_eligible` says so. (2) OWNERSHIP EXTENDS to the two readers and their
tests for exactly this tolerance: the period module evaluates A / B / C from every scored row and D only from rows with
d_eligible true (its own d_subset comparisons B / C / D on that subset, mirroring the scorer's block); the auditor's population
check requires finite predictions for A / B / C on every scored row and for D on every d_eligible row, requires the scorer's
d_subset counts to equal the count of d_eligible scored rows, and reconstructs the d_subset points and intervals the same way it
reconstructs the full ones; both readers must be byte-identical in behaviour on a model-complete corpus (test). (3) WARM-UP NAMING
(contract B1): the summary lists `d_subset_warmup_keys` (rows eligible for D but in a fold with no D-eligible training rows) and
the memo and tests assert, globally and per cell, D-eligible rows = D-warm-up rows + D-scored rows. (4) The three landed test files
of the readers and the four of the scorer pass with only the assertions this amendment names changed.

AMENDMENT 2 (2026-09-22 02:4xZ; binding; found by the FIRST real census run from master after landing: ALL 465,249 NBA ticks were
excluded as invalid_outcome). The landed eligibility added, for nba only, `type(outcome) is not int` -> invalid_outcome; the
converter (row S360) and the corpus schema store the outcome as a JSON FLOAT 1.0 / 0.0 (as does the MLB corpus, which the scorer
accepts by value). This is the label-vs-count mistake of S379 AMENDMENT 2 repeated: OUTCOME IS A LABEL. Rule: an outcome is valid
when it is a non-boolean finite number whose value is exactly 0 or 1 (int or float), compared by value, for every sport; anything
else (bool, 0.5, NaN, string, null) is invalid_outcome. The new NBA test file must carry a fixture whose rows are the REAL shape
(the verbatim first row of the corpus from the S377 spec: outcome 1.0, state_summary as a key=value string, model_prob null) and
prove those rows are eligible. The census run that found this (eligible_ticks 0, invalid_outcome 465,249, post_final 244,183,
model_prob_missing_for_d 348,757, non_integral_state 0) is recorded in the ledger as the reason for this amendment.

