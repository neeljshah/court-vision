VERDICT: REJECT
Candidate: 7d9edaaf1; scope checked against G353_spec.md:59-81 and VERIFIER_CONTRACT.md:20-55.
ACCEPTANCE FAIL: the PARTIAL bar outcome reproduces, but the premise count is wrong and census.csv:1-4 reports three gate groups, not each image-space gate.
PREMISE FAIL: source enumeration is 18 rows = 14 GATES + 3 REPORT_ONLY + any_gate; prereg:19-36 classifies 16 image-space and 2 court-only, claimed 15/18 and 3 court-only (memo:5).
HEADLINE PASS: gates.csv:2-73 has 72 unique gate-arm cells; 12/18 A0 gates evaluate 30/30, 2/12 clear <=0.05; claimed bar result 2, while ledger:641 incorrectly says 3 gates evaluate.
CENSUS PASS totals only: census.csv:2-4 recomputes 653 tables, 644 declared image_px, 0 with both frame dimensions; claimed totals match.
B1 FAIL: A5 uses 27/30 but the three excluded fixture IDs and exclusion reason are absent (arms.csv:5; memo:9).
B2 PASS: new row fields and statuses are additive (image_space_gates.py:26-38); only test_g353_image_space_gates.py:9 imports the new module.
B3 FAIL: native frame dimensions are absent 30/30, yet g325 rejects 4/30 using an unstable estimate (memo:15; gates.csv:66).
B4 PASS: no claim/retry state exists in the additive evaluator (image_space_gates.py:79-165).
B5 PASS: only metadata was read remotely and no deployed-tree write is reported (memo:13,25).
B6 PASS: branch diff adds files and removes or moves none; module reader remains present (test_g353_image_space_gates.py:9).
B7 PASS: all 30 fixtures were used; master fixtures.csv:2-31 has 30 unique IDs and 30 unique path-window triples.
B8 PASS: no fit or fitted residual is used (image_space_gates.py:104-163).
B9 PASS: gate denominators are explicit and nonconstant (gates.csv:1-73); A5 applicable n=27 is separately recorded (arms.csv:5).
B10 PASS: no harness/schema/threshold file changed; thresholds are imported (image_space_gates.py:9-14,97,152,161).
Q1 PASS: sealed prereg commit 0d816f4c4 at 16:08:40 precedes metric commit at 16:25:22; seal test passes (prereg:53).
Q2 PASS: this fixed construct/census is not a charged trial and makes no K claim (spec:59-70).
Q3 PASS: bars match spec:65-68 and prereg:45-49; none moved.
Q4 PASS: no predictive OOS score or meta-learner is present (memo:7-15).
Q5 PASS: no AHEAD claim is made (memo:1-25).
Q6 FAIL: memo:25 contains four forbidden claim-language tokens; delete the line.
Q7 PASS: n=30 rail holds; master fixtures.csv:2-31 is exhaustive and unique; gates.csv has 30 per arm-gate before named applicability.
Q8 FAIL: independent premise recount is 16/18, not the claimed 15/18 (g343_attack_test.py:14-21,106-117; prereg:19-36).
LOC PASS: image_space_gates.py 165; test_g353_image_space_gates.py 64; candidate 7d9edaaf1 touches no .py; all <=300 (spec:81).
EVIDENCE PASS: memo:19 has NOT VERIFIED; named G353 paths exist; LF hashes for gates/arms/census reproduce memo:23.
TEST candidate> C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g353_image_space_gates.py -q -p no:cacheprovider --basetemp=C:\Users\neelj\nba-track-a10\.tmp_g353_verify_20260908 -> 3 setup errors (sandbox temp cleanup).
TEST candidate> C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g353_image_space_gates.py -q -p no:cacheprovider -p no:tmpdir -> 3 setup errors (shared conftest requires tmp_path).
TEST candidate> C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g353_image_space_gates.py -q -p no:cacheprovider --confcutdir=tests\platformkit -> 3 passed.
TEST candidate> C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g233_basketball_seeded_court_coordinates.py -q -p no:cacheprovider --confcutdir=tests\platformkit -> 1 passed.
TEST master> C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g233_basketball_seeded_court_coordinates.py -q -p no:cacheprovider --confcutdir=tests\platformkit -> 1 passed.
TEST master> C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g348_gate_execution.py -q -p no:cacheprovider --confcutdir=tests\platformkit -> 4 passed.
CORRECTION: memo:5, prereg:38-39, ledger:641: 15/18 -> 16/18, 3 court-only -> 2, and 3 evaluated -> 12 evaluated with 2 clearing both bars.
CORRECTION: name the three A5 exclusions; mark g325 NOT_APPLICABLE when decoded dimensions are absent; regenerate affected gates.csv rows.
CORRECTION: add an explicit 13-core/2-ball/1-containment gate-to-census mapping and delete memo:25.
2026-09-08 | tracking | G353 | premise 16/18 image-space-computable; 12/18 A0 gates evaluated 30/30, 2/12 meet false-rejection <=0.05; identifiable detections 30/30, 30/30, 27/27; census 653 tables, 644 image_px, 0 with both frame dimensions | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: candidate-specific test and module are absent from master, so contract A1 cannot be completed before staging the candidate.
NEW GAP: fixture-level G353 statuses and scratch translation are not archived; aggregates cannot identify A5 exclusions or regenerate gates.csv.
