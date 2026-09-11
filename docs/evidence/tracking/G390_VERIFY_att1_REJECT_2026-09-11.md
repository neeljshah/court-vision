VERDICT: REJECT
ACCEPTANCE-1 FAIL: preregistration.md:21 seals readiness as fe8bcbe..., but G389 memo:51 and the file remeasure d11a1c8c...; source identity was not met although memo:3 says row 1 passed.
ACCEPTANCE-2 PASS: summary.json:23-47 uses all 549 unique keys and reproduces TP 90 / FP 169 / FN 212; every immutable quality bar is missed, so NOT VALIDATED is correct.
ACCEPTANCE-3 FAIL: g390_a8_run.py:160-194 renders reference plus A8 only, not both A0 and A8 outputs required by G390_spec.md:21; memo:3 incorrectly says row 3 passed.
A1 PASS (caller-scoped candidate worktree): the sole importer test was rerun at candidate HEAD; tests/platformkit/test_g390_ball_a8_sealed_pass.py:9-14.
A2 PASS: independent raw frames/reference/prediction scoring reproduced memo:16-21 exactly; fresh archive reproduction returned 1,098 rows.
A3 PASS: all 30 renders were viewed; g390_a8_run.py:166-170 samples evenly over sorted 549-row A8 decisions and includes failures/empty outputs.
A4 PASS: summary.json:43-47 has 549 keys; independent counts found 1,620/1,620 unique source/reference keys, 530/530 dev-box keys, and 1,098 unique arm-key pairs.
A5 PASS: repository reader search found only the G390 modules and tests/platformkit/test_g390_ball_a8_sealed_pass.py:9-14; no other test imports a touched module.
A6 PASS (caller override): no landing was attempted; only this verifier memo is committed and the requested proposed system line is below; RESULTS_LEDGER.md:747.
A7 PASS: all 50 manifest entries exist and rehash; memo:26-30 contains a NOT VERIFIED list and identifies external-only facts.
B1 PASS: fixed denominators include every held-out key and all prediction failures; summary.json:23-47.
B2 PASS: aggregate diff is additive with no removed/renamed field or status; all eight touched Python files are 24-243 LOC, and reader behavior is unchanged.
B3 PASS: absent or unsettled evidence raises before scoring rather than classifying a row; g390_sealed_input.py:69-90.
B4 PASS: one token advances irreversibly and repeat scoring refuses; g390_receipt.py:22-47 and candidate_token.json:2-9.
B5 FAIL: g390_a8_run.py:16 and memo:33 use /workspace/g390_scratch, outside the required /workspace/wt/a11 path in G390_spec.md:3 and the exception in VERIFIER_CONTRACT.md:140.
B6 PASS: no moved/retired module and no orphan; the only test importer resolves; tests/platformkit/test_g390_ball_a8_sealed_pass.py:9-14.
B7 PASS: render selection is linspace over the full sorted decision set, not a head slice; g390_a8_run.py:166-170.
B8 PASS: training uses development only with zero held-out links and disjoint games; memo:6,10.
B9 PASS: independent denominators are 549 held-out and 188 ABSENT, with 549 unique per arm; summary.json:43-47.
B10 PASS: bars in g390_score_run.py:17-19 equal G390_spec.md:20 and summary.json:26-28.
Q1 PASS: preregistration.md:49 seal recomputes and commit 9196b6de8 at 01:50 predates first result commit ebffba925 at 02:15.
Q2 PASS (not applicable): no family-K claim is made; the single execution allowance is explicit at candidate_token.json:2-9.
Q3 PASS: all three bars are byte-identical and reported missed; summary.json:24-41.
Q4 PASS: g390_score.py:99-105 invokes CPCV with symmetric embargo/purge; 7,686 archived records reproduce summary.json:49-54.
Q5 PASS (not applicable): memo:3 is NOT VALIDATED and makes no AHEAD claim.
Q6 PASS: independent scan of 29 row text files plus RESULTS_LEDGER.md:747 found only the four documented opaque data/census files; q6_scan.json:14-18.
Q7 PASS: scored n=549 and 30 deterministic even renders; memo:16-24.
Q8 PASS: premise remeasurement reproduced 1,620, 1,071/549, 302/188/59, 530, 27, and zero split-game overlap; memo:5-7.
TEST: python -m pytest tests/platformkit/test_g390_ball_a8_sealed_pass.py -q -> 4 passed in 0.68s (only existing test importer; one file, one command).
REPRODUCED: claimed A8 90/169/212, 0.16393442622950818, 0.29211016505655896, 0.898936170212766; measured values identical. A0 claimed/measured 0/8/302.
CORRECTION memo:3: - "Row 1 ... and row 3 ... passed"
CORRECTION memo:3: + "Rows 1 and 3 failed: sealed readiness identity mismatched and paired renders omitted A0; overall NOT VALIDATED remains."
CORRECTION memo:33: - "Pod scratch /workspace/g390_scratch cleaned after export."
CORRECTION memo:33: + "Compute ran outside the required /workspace/wt/a11 scratch path; no second candidate run is permitted."
2026-09-11 | tracking | G390 | A8 90 TP / 169 FP / 212 FN over 549; C0 0.163934, Wilson95 lower 0.292110, ALL FP/188 0.898936; sealed readiness mismatch and B5 scratch-path violation | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: G390_spec.md:23 names context exclusion, coordinate conversion, UNKNOWN handling, missing-frame denominator, and second-inference tests absent from test_g390_ball_a8_sealed_pass.py:32-57.
NEW GAP: G390_spec.md:7 requires dependency versions and no implicit defaults, but preregistration.md:30-34 omits versions and the archived args contain additional unsealed defaults.
