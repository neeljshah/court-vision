VERDICT: REJECT
Candidate: 25209809644ba0b78b6c8eaad723259c444891d7.
ACCEPTANCE-1 PASS - 30/30 retained-source hashes bind to 30 unique draw rows; 1,984/1,984 anomaly rows are unique; 30 integer streams and 30 cards exist (`source_receipts.csv:1`, `anomalies.csv:1`, `eye_index.csv:1`).
ACCEPTANCE-2 PASS - independent exact replay gives containment 30/30, first-excluded 30/30, last-admitted 30/30 and UNKNOWN 0 under the unchanged bar (`g411_integer_pts_extent_audit_2026-09-12.md:23`).
ACCEPTANCE-3 PASS - 32/32 exhaustive constructs and both fresh reproductions match all 39 delivered entries, apart from the declared summary tag (`construct_cases.csv:1`, `repeats.json:1`).
B1 PASS - all 30 draw rows enter the denominator; absent retained evidence becomes an explicit UNKNOWN (`scripts/platformkit/tracking/g411_run.py:137`).
B2 FAIL - malformed PTS after one admission loses parent state: G408 `[50, missing]` has read/admitted 1/1, deadline 150, last PTS 50, span 0 and gap 100; G411 has 0/None and blanks, and renames the parent missing reason (`g408_stop.py:70`, `g408_tables.py:78`, `g411_measure.py:48`, `g411_measure.py:63`, `g411_rows.py:43`).
B3 PASS - missing retained evidence remains an explicit UNKNOWN row, not a silent exclusion (`scripts/platformkit/tracking/g411_run.py:137`).
B4 PASS - this diagnostic performs no claim-state mutation (`g411_integer_pts_extent_audit_2026-09-12.md:38`).
B5 PASS - PC only; no pod or deployment was exercised (`g411_integer_pts_extent_audit_2026-09-12.md:38`).
B6 PASS - no module moved; the sole test importer resolves full package paths (`scripts/platformkit/tracking/g411_run.py:21`, `tests/platformkit/test_g411_integer_pts_extent.py:8`).
B7 PASS - cards cover draw positions 0-29; verifier sampled 0, 7, 15, 22 and 29 (`eye_index.csv:1`).
B8 PASS - exact rational replay uses no fitted residual as independent evidence (`g411_integer_pts_extent_audit_2026-09-12.md:17`).
B9 PASS - denominator is 30 distinct source timelines; shared games remain named in the draw (`draw.csv:1`).
B10 PASS - the bar remains exactly `abs(extent-100) <= 1/validated_fps` (`scripts/platformkit/tracking/g411_measure.py:87`, `prereg.md:17`).
Q1 PASS - seal recomputes to f7d5b33dc3ec131b744244f97597a9ffc950e3af99b6b893733d679a9414923b and predates measurement (`prereg.md:26`, `g411_integer_pts_extent_audit_2026-09-12.md:7`).
Q2 PASS (N/A) - this diagnostic is not a charged trial (`prereg.md:5`).
Q3 PASS - preregistered and measured bars are identical (`prereg.md:17`, `summary.json:4`).
Q4 PASS (N/A) - no model or OOS comparison is exercised (`g411_integer_pts_extent_audit_2026-09-12.md:38`).
Q5 PASS (N/A) - no AHEAD classification is made (`g411_integer_pts_extent_audit_2026-09-12.md:1`).
Q6 PASS - current G411 scan is 182 paths / 0 hits; the 1,244 candidate-added lines independently scan 0 (`q6_scan.json:8`, `q6_scan.json:73`).
Q7 PASS - four observed rate pairs each enumerate all eight declared cases, 32/32 correct (`summary.json:7`, `construct_cases.csv:1`).
Q8 PASS - premise independently replays at 30/30 containment, 30/30 first-excluded, 26/30 last-admitted, with four exact 1/3000000 s excesses (`g411_integer_pts_extent_audit_2026-09-12.md:11`).
MEMO PASS - an explicit NOT VERIFIED list is present (`g411_integer_pts_extent_audit_2026-09-12.md:54`).
LOC PASS - touched Python files are 209, 160, 280, 235 and 236 lines, all at most 300 (`g411_measure.py:209`, `g411_rows.py:160`, `g411_run.py:280`, `g411_seal.py:235`, `test_g411_integer_pts_extent.py:236`).
TEST PASS - `python -m pytest tests/platformkit/test_g411_integer_pts_extent.py -q` -> 20 passed in 0.75s; importer census found no other test file.
REPRODUCED - claimed premise 30/30, 30/30, 26/30 plus four 0.000000333333 s excesses; measured the same, with excess exactly 1/3000000 s. Claimed exact 30/30 both endpoints and eight changes; measured the same.
CORRECTION (minimal diff) - pass origin, deadline, admitted prefix, last PTS and extents into `_unknown`; derive first-admitted from retained state instead of hard-coding 0 (`g411_measure.py:48-64`, `g411_rows.py:46`).
CORRECTION (minimal diff) - retain the G408 `unknown_reason` value and add a G411-specific alias; change the UNKNOWN fixture to compare every parent field after one admitted PTS, then regenerate tables, repeats, scans and sums (`test_g411_integer_pts_extent.py:216`).
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G411 | premise 30/30 containment, 30/30 first-excluded, 26/30 last-admitted; exact PTS 30/30 both endpoints; malformed PTS loses admitted parent state and renames its reason | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Contract A1 cannot run on master because master lacks `tests/platformkit/test_g411_integer_pts_extent.py`; candidate-worktree execution is the only available run (`VERIFIER_CONTRACT.md:11`).
NEW GAP: the memo reports older scan sizes 169 and 174, while the current fix1c receipt reports 182 (`g411_integer_pts_extent_audit_2026-09-12.md:38`, `q6_scan.json:73`).
