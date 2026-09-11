VERDICT: REJECT
ACCEPTANCE-1 FAIL: preregistration.md:21 seals readiness as fe8bcbe..., but G389 memo:51 and direct SHA-256 give d11a1c8c...; memo:3 now correctly reports the identity failure.
ACCEPTANCE-2 PASS: summary.json:23-47 covers 549 unique keys and reproduces A8 TP 90 / FP 169 / FN 212; all three fixed bars miss, so NOT VALIDATED is correct.
ACCEPTANCE-3 FAIL: g390_a8_run.py:160-194 renders reference plus A8 only, not both A0 and A8 required by G390_spec.md:21; memo:3 now reports this.
B1 PASS: all 549 held-out rows and all 188 ABSENT rows remain in the fixed denominators; summary.json:23-47.
B2 PASS: 5dda1c7eb changes prose only; no field, status, or reader behavior is renamed/removed. No .py is touched; row .py files are 24-243 LOC.
B3 PASS: absent or unsettled evidence refuses scoring rather than classifying an item; g390_sealed_input.py:69-90.
B4 PASS: the token advances irreversibly and repeat scoring refuses; g390_receipt.py:22-47 and candidate_token.json:2-9.
B5 FAIL: compute used /workspace/g390_scratch at g390_a8_run.py:16, outside the only allowed /workspace/wt/a11 path in VERIFIER_CONTRACT.md:140; memo:33 confirms it.
B6 PASS: no module moved or retired; the sole G390 importer resolves at test_g390_ball_a8_sealed_pass.py:9-14.
B7 PASS: 30 unique render keys equal the deterministic even selection over all 549 sorted decisions; g390_a8_run.py:166-170.
B8 PASS: development-only training has 0 held-out box links and split-game overlap; g390_a8_run.py:48-87 and memo:10.
B9 PASS: independent denominators are 549 held-out and 188 ABSENT, with 549 unique keys per arm; summary.json:43-47.
B10 PASS: 0.25, 0.90, and 0.01 match G390_spec.md:20 exactly; g390_score_run.py:17-19.
Q1 PASS: preregistration.md:49 seal recomputes c27ad65d...; commit 9196b6de8 at 01:50 predates first result commit ebffba925 at 02:15.
Q2 PASS (not applicable): no family-K claim; the sole token is charged before inference at g390_a8_run.py:230-238.
Q3 PASS: the three bars are unchanged and reported missed; summary.json:24-41.
Q4 PASS: g390_score.py:99-105 calls CPCV with purge and symmetric embargo; 7,686 archived records reproduce both arm means.
Q5 PASS (not applicable): memo:3 reports NOT VALIDATED and makes no AHEAD claim.
Q6 PASS: independent scan found 0 non-opaque hits in 30 row text files and 0 in the two G390 ledger rows; q6_scan.json:14-18.
Q7 PASS: scored n=549 and 30 unique renders are evenly selected; renders_index.csv:2-31.
Q8 PASS: direct premise remeasure gives 1,620 unique source/reference keys, 1,071/549 split, 302/188/59 held-out, 530 boxes/27 games, and zero overlaps; memo:5-7.
TEST: python -m pytest tests/platformkit/test_g390_ball_a8_sealed_pass.py -q -> 4 passed in 0.77s.
TEST IMPORTERS: repository search found only tests/platformkit/test_g390_ball_a8_sealed_pass.py:9-14 for the aggregate G390 modules; candidate 5dda1c7eb touches no module.
REPRODUCED: claimed/measured A8 90/169/212, C0 0.16393442622950818, Wilson95 lower 0.29211016505655896, ALL FP/188 0.898936170212766; A0 claimed/measured 0/8/302.
ARTIFACT PASS: all 50 manifest entries rehash, all 30 renders decode, and a fresh process reproduces 1,098 per-arm frame rows; sha256_manifest.txt:1-50.
NOT VERIFIED PASS: memo:26-30 contains the required list and identifies archived A0, the latched evaluator path, single-run repeatability, and external weight handling.
CORRECTION memo:33 already applied: - "Pod scratch /workspace/g390_scratch cleaned after export." + "Compute ran outside the required /workspace/wt/a11 scratch path ...; no second candidate run is permitted."
2026-09-11 | tracking | G390 | A8 90 TP / 169 FP / 212 FN over 549; C0 0.163934, Wilson95 lower 0.292110, ALL FP/188 0.898936; readiness identity and scratch-path failures; no second run | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: G390_spec.md:23 names quota, split/context, coordinate, UNKNOWN, missing-frame, and second-inference tests absent from test_g390_ball_a8_sealed_pass.py:32-57.
NEW GAP: G390_spec.md:7 requires dependency versions and no implicit defaults, but preregistration.md:30-34 omits versions and args.yaml includes additional unsealed defaults.
