VERDICT: CLOSED AT LIMIT
Candidate: 1aa32aa074b7c220c519e53c82d418534f42070a; scope is G398_spec.md:24-29 plus B1-B10 and Q1-Q8.
ACCEPTANCE-1 PASS: 1,071/1,071 unique DEV keys, 530/530 unique boxes over 27 games, 549/549 held-out keys, and zero key/game/section overlap (split_assertions.json:5-46).
ACCEPTANCE-2 PASS: every fixed continuation component fails, so the specified outcome is CLOSED AT LIMIT (summary.json:106-143; G398_spec.md:28).
ACCEPTANCE-3 PASS: one spent paired launch covered both 1,071-key arms in 42.854 seconds; two saved-output rescores are identical and held-out calls are zero (launch_accounting.json:34-72; summary.json:121-143).
PREMISE PASS: independent source-table recount = DEV 1,071 unique, labels 531/425/115, boxes 530 unique/27 games; held-out 549 unique and overlaps 0/0/0 (split_assertions.json:5-46).
REPRODUCTION PASS: independent paired-table arithmetic gives 960 = 251/198/280, C0 0.234360410831, Wilson lower 0.512786961147, FP/425 0.465882352941; 1920 = 121/310/410, C0 0.112978524743, lower 0.240399403026, FP/425 0.729411764706; claimed values match (summary.json:2-105).
RENDERS PASS: 30/30 unique keys exactly match the even-spacing formula; labels 16/8/6 and sampled cards are coherent (eye_index.csv:1-31; g398_score.py:161-186).
TEST PASS: `python -m pytest tests/platformkit/test_g398_a8_high_resolution_dev_shadow.py -q --basetemp=.pytest_tmp_g398/verify_codex_sol_20260911` -> 10 passed in 1.68s (test_g398_a8_high_resolution_dev_shadow.py:1-166).
READER CENSUS PASS: the sole existing test importing a touched module is the spec test above; no test imports the two new modules (test_g398_a8_high_resolution_dev_shadow.py:21).
LOC PASS: g398_q6_scan.py 31, g398_run.py 293, g398_score.py 254, test file 166; each touched Python file <=300 (g398_q6_scan.py:31; g398_run.py:293; g398_score.py:254; test_g398_a8_high_resolution_dev_shadow.py:166).
ADDITIVITY PASS: schemas/statuses are additions, the scan callable remains, and its sole reader passed; no renamed/removed field, status, or reader contract (g398_score.py:31-37; g398_q6_scan.py:22-31).
MEMO PASS: measured numbers and limitations are present, including a four-item NOT VERIFIED list (g398_a8_high_resolution_dev_shadow_2026-09-11.md:17-38).
B1 PASS: all planned rows remain in the full denominator; silence is explicit (g398_run.py:232; g398_score.py:103-139).
B2 PASS: additive schema and checked reader census as above (g398_score.py:31-37; test_g398_a8_high_resolution_dev_shadow.py:21).
B3 PASS: unavailable inference is retained, not treated as adverse evidence (g398_prepare.py:109-117).
B4 PASS: the launch token refuses a second claim and ends spent (g398_prepare.py:120-130; g398_run.py:286).
B5 PASS: the sealed route is a scratch shadow and changes no production setting (preregistration.md:16-18).
B6 PASS: no module moved or retired; full-package imports resolve in the passing test (test_g398_a8_high_resolution_dev_shadow.py:10-21).
B7 PASS: render positions span the full sorted decision set by formula (g398_score.py:161-163).
B8 PASS: DEV reuse is disclosed and no independent or held-out claim is made (g398_a8_high_resolution_dev_shadow_2026-09-11.md:26-30).
B9 PASS: denominators are 1,071 unique DEV keys and 425 ABSENT states, not recycled identifiers (paired_scores.csv:1-1072; summary.json:2-105).
B10 PASS: historical bars remain 0.25/0.90/0.01 and untested (summary.json:122-127; G398_spec.md:28).
Q1 PASS: preregistration seal is valid and its separate commit predates launch/scoring (preregistration.md:36; split_assertions.json:40).
Q2 PASS: the sole paired allowance is charged before traversal and reports one launch (g398_run.py:263-277; launch_accounting.json:34-38).
Q3 PASS: fixed continuation and historical bars match the spec byte-for-value (summary.json:106-127; G398_spec.md:28).
Q4 PASS: this is explicitly a training-contaminated DEV diagnostic, not an OOS score (g398_a8_high_resolution_dev_shadow_2026-09-11.md:26).
Q5 PASS: no AHEAD result is claimed; the fixed option closes (summary.json:143).
Q6 PASS: the complete G398 text scan reports zero non-opaque hits (q6_scan.json:2-7; g398_q6_scan.py:22-31).
Q7 PASS: the scored set is exhaustive at 1,071 and the eye sample contains 30 evenly distributed unique frames (paired_scores.csv:1-1072; eye_index.csv:1-31).
Q8 PASS: the premise was recorded before inference and independently remeasured above (g398_a8_high_resolution_dev_shadow_2026-09-11.md:5-13; split_assertions.json:5-46).
CORRECTIONS: none.
RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G398 | paired DEV diagnostic: 960 C0 0.234360, Wilson lower 0.512787, FP/425 0.465882; 1920 C0 0.112979, lower 0.240399, FP/425 0.729412; all continuation components fail | CLOSED AT LIMIT (verified: codex-sol, contract A/B/Q)
NEW GAP: SHA256SUMS verifies all 44 commit blobs, but checkout line-ending conversion changes 13 text-artifact byte hashes; declare the blob-versus-worktree byte domain (SHA256SUMS:1).
