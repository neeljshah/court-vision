GAP S379 | sport mlb (four-arm baseline) | worktree harness-h38 (master-based) | log cx_s379_four_arm_output_audit
# Four-arm OUTPUT auditor: three checks on the saved output before anyone reads the verdict (design: docs/evidence/harness/ASTRA_ROUND13_2026-09-21.md section 2 + section 1 row 8)

SINGLE PROBLEM: the sealed MLB four-arm trial runs exactly ONCE. A plausible summary.json can hide invalid evidence (a changed
denominator, unequal arm populations, a held-out game in its own training set, a sign or weighting slip, a missing or non-canonical
ledger charge). There must be a tool that audits the OUTPUT -- never re-running the fit -- and blocks verdict release on any failure.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/ingame/four_arm_output_audit.py` fails. Read, on master:
scripts/platformkit/ingame/baseline_four_arm.py (predict_rows, summarize, _cell and the exact keys of a paired row and of
summary.json), baseline_four_arm_eligibility.py, docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md (the frozen denominators: 176
games, 31433 ticks, 29887 eligible ticks, 12339 transition ticks, 15 folds of which 4 are warm-up; the seal line; the manifest pin).
The trial runner (row S359) is not on master yet: an UNCOMMITTED reference copy is placed at the root of this worktree as
_reference_s359_four_arm_trial.py -- read it for the exact artifact names and shapes it writes into the output directory
(attempt.json, charge.json {ledger_row, k_at_launch, ...}, paired_rows.json, summary.json, trial_summary.json, failure.json). Quote
every schema you rely on in the memo. Never commit or import the reference copy.

CHANGE (NEW files only; the scorer, the runner and the prereg are NOT edited):
1. scripts/platformkit/ingame/four_arm_output_audit.py (<= 300 LOC; a second NEW helper module is allowed if needed for the cap):
   `--out-dir <trial output> --prereg <sealed md> --manifest <json> --corpus-dir <dir> [--ledger <canonical jsonl, READ ONLY>]
   --audit-out <json>`. It NEVER fits, never calls predict_rows, never writes into --out-dir and never writes the ledger. Checks,
   each reported PASS / FAIL / NOT_AUDITABLE with counts and a one-line reason:
   A. PROVENANCE + ACCOUNTING: the prereg seal line matches the SHA-256 of the sealed content exactly as the runner computes it;
      the manifest SHA-256 equals the prereg pin; charge.json exists, carries k_at_launch as a strict int, and (when --ledger is
      given) exactly ONE ledger row matches its hypothesis / prereg hash with k_cumulative == k_at_launch + 1; attempt.json is
      attempt 1 or 2 only; failure.json is absent; the eligibility census inside summary.json equals every frozen denominator in the
      prereg (parse them from the prereg text; a denominator that cannot be parsed is NOT_AUDITABLE, never assumed).
   B. KEYS + CHRONOLOGY: every scored paired row has a finite prediction in (0,1) for EVERY arm (identical populations); keys are
      unique; each game's outcome is constant and equals the corpus file's outcome; warm-up rows are exactly the rows of the warm-up
      folds; fold order is non-decreasing in first-tick date; for every scored fold the recorded training size is > 0; if the saved
      rows do not carry training game ids, the check "a held-out game never trains itself" is reported NOT_AUDITABLE with that
      reason (absent evidence is explicit, never a pass).
   C. RECONSTRUCTION without refitting: recompute from paired_rows.json alone, with an INDEPENDENT implementation (no import of
      _cell / summarize for the point estimates), each arm's mean Brier and log-loss, every candidate-minus-A difference and its
      SIGN, per-population and per-phase cell counts, the largest single-game absolute share and the leave-one-game-out range;
      compare with summary.json to 1e-12 (counts exactly). An interval that contains zero must be labelled UNDERPOWERED in the
      summary and never MATCH; a favourable interval must be labelled SINGLE-WINDOW.
   `verdict_release` is true only if no check is FAIL and no check in the declared CRITICAL set (all of A; identical populations,
   unique keys and outcome consistency in B; signs and counts in C) is NOT_AUDITABLE. The tool's stdout and audit JSON contain
   check names, statuses, counts and absolute discrepancies ONLY -- never a loss value, a difference or an interval -- so that it
   can be run BEFORE anyone looks at the result. Strict-int counts; math.isfinite on every float read; every except clause counts
   or re-raises; results independent of row order.
2. tests/platformkit/ingame/test_four_arm_output_audit.py: a small synthetic output directory built in the test that passes, then
   one seeded defect per check (changed denominator, wrong manifest pin, missing charge, two matching ledger rows, k mismatch,
   attempt 3, failure.json present, an arm missing on one row, a non-finite prediction, a duplicate key, an outcome flip, a warm-up
   row scored, a flipped difference sign in the summary, a count off by one, an interval spanning zero labelled MATCH) -- each
   must flip verdict_release to false and name the check; plus: no loss value ever appears in stdout or the audit JSON.
3. Memo docs/evidence/harness/S379_four_arm_output_audit_2026-09-21.md.

CONTROLS: PREPARE only, NEW files only, construct tests, no real trial output (none exists yet), no real ledger, no network.
ACCEPTANCE: per-file test passes; --help works; diff = NEW files only; <= 300 LOC per file; ASCII; contract Q6 vocabulary
(assemble retracted-figure literals from single digits); the memo ends with a NOT VERIFIED list. The pod is OFF.

AMENDMENT 1 (2026-09-21; binding; the orchestrator's original text of check A was WRONG about the runner's K convention -- the
builder correctly refused to hide the conflict). The trial runner (row S359) defines k_at_launch as the k_cumulative of the row it
just charged, and separately saves prior_max_k_cumulative. Check A therefore requires ALL of: charge.json ledger_row.k_cumulative
== charge.json k_at_launch (strict ints); k_at_launch == prior_max_k_cumulative + 1; and, when --ledger is given, exactly ONE row
of that ledger matches the embedded row's hypothesis_hash + prereg_sha256, is identical to the embedded row, and no ledger row has
a larger k_cumulative with an EARLIER `at` time than it (the charge is the newest row at launch). The words "k_cumulative ==
k_at_launch + 1" in the body are withdrawn. Check C: the landed summary schema carries candidate-minus-A differences (`point`)
per comparison and no per-arm means; the CRITICAL reconstruction is each `point` and its SIGN, the cell counts, the largest
single-game share and the leave-one-game-out range, recomputed independently from paired_rows.json to 1e-12; per-arm means are
compared only if present and their absence is a NON-critical NOT_AUDITABLE. Add tests for: k_at_launch != ledger_row.k_cumulative,
k_at_launch != prior + 1, an unchanged reference-shaped output PASSING check A, and a `point` altered by 1e-9 failing check C.

AMENDMENT 2 (2026-09-21 23:5xZ; binding; found by the FIRST RUN of the landed auditor on the real sealed trial output). The
corpus schema and the scorer's paired rows carry `outcome` as a JSON FLOAT (1.0 / 0.0); the scorer accepts it by value
(`row['outcome'] in (0, 1)`). The auditor's `integer()` helper (strict `type(value) is int`) was applied to `outcome`, so B.keys,
B.outcomes, C.signs, C.reconstruction and C.intervals each raised on the first row and were counted as one refusal -- a FALSE
BLOCK, not a defect of the trial output. Rule: `outcome` is a LABEL, not a count: accept a non-boolean finite number whose value is
exactly 0 or 1 (int or float), compare by value, refuse everything else; strict-int typing stays for every COUNT field. Add a test
whose synthetic corpus and paired rows carry float outcomes 1.0 / 0.0 (the real shape) and must PASS, and a test that a boolean
or 0.5 outcome still FAILS. No other change. The trial output stays unread until this fix is verified, landed and re-run.

AMENDMENT 3 (2026-09-22 00:1xZ; binding; found by the second real run, after fix 2a, on the sealed trial output: 21 of 23 checks
PASS; C.reconstruction FAILED with an absolute discrepancy of 2.1e-12 against the 1e-12 tolerance the orchestrator wrote into
check C). That tolerance was set before the row count was known: a float64 mean over 29,887 tick losses accumulates rounding of
order N x machine epsilon (about 7e-12), so two correct implementations with different summation order cannot be expected to
agree to 1e-12. This is a reproduction tolerance inside the auditor, not a prereg bar (contract Q3 governs the AHEAD / BEHIND /
UNDERPOWERED thresholds, which are untouched). Rule: point estimates and interval endpoints reconstruct to an ABSOLUTE tolerance
of 1e-9 (three orders of magnitude below the smallest interval width that could matter and 1,000x the observed rounding);
counts stay exact. Add tests: a seeded 5e-10 discrepancy PASSES, a seeded 2e-9 discrepancy FAILS, and the tolerance is one named
constant. No other change. The observed 2.1e-12 is recorded here as a reproduction discrepancy; it says nothing about any cell.

