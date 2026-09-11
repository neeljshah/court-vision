VERDICT: REJECT
Candidate: 632b14c75e6f2c4792b3d6f6b06499a88fc8daaf.
ACCEPTANCE-1 PASS - 30/30 source binds, 30 distinct timelines, 1,984/1,984 unique anomaly rows, 30 integer streams and 30 cards; cards 0, 7, 15, 22 and 29 were evenly checked (`source_receipts.csv:1`, `anomalies.csv:1`, `eye_index.csv:1`).
ACCEPTANCE-2 PASS - independent replay gives exact containment 30/30, first-excluded 30/30, last-admitted 30/30 and UNKNOWN 0 under the unchanged bar (`summary.json:41`).
ACCEPTANCE-3 PASS - 32/32 exhaustive constructs cover all four observed rate pairs; two saved-input runs reproduce every delivered table/card (`summary.json:7`, `repeats.json:43`).
B1 PASS - all 30 draw rows enter the measured denominator; no failed row is filtered after scoring (`scripts/platformkit/tracking/g411_run.py:124`).
B2 FAIL - the zero-frame reader path calls `_row(..., -1, ...)`, then subscripts that integer; G408 returns EOF_SHORT with `start_outside_schedule`, while G411 raises TypeError (`scripts/platformkit/tracking/g411_measure.py:38`, `scripts/platformkit/tracking/g411_measure.py:90`, `scripts/platformkit/tracking/g408_stop.py:52`).
B3 PASS - absent retained evidence becomes an explicit UNKNOWN row (`scripts/platformkit/tracking/g411_run.py:136`).
B4 PASS - this diagnostic performs no claim-state mutation (`g411_integer_pts_extent_audit_2026-09-12.md:37`).
B5 PASS - PC only; no pod or deployment was exercised (`g411_integer_pts_extent_audit_2026-09-12.md:37`).
B6 PASS - no module moved; the sole test importer uses the full package path (`tests/platformkit/test_g411_integer_pts_extent.py:7`).
B7 PASS - all 30 cards exist and the verifier sampled positions 0, 7, 15, 22 and 29 (`eye_index.csv:1`).
B8 PASS - exact rational replay uses no fitted residual as independent evidence (`g411_integer_pts_extent_audit_2026-09-12.md:16`).
B9 PASS - the denominator is 30 distinct source timelines; 1,984 anomaly rows are unique (`summary.json:3`, `anomalies.csv:1`).
B10 PASS - the bar remains exactly `abs(extent-100) <= 1/validated_fps` (`scripts/platformkit/tracking/g411_measure.py:106`, `prereg.md:17`).
Q1 PASS - the seal recomputes to f7d5b33dc3ec131b744244f97597a9ffc950e3af99b6b893733d679a9414923b and its one-file commit predates measurement (`prereg.md:26`, `g411_integer_pts_extent_audit_2026-09-12.md:6`).
Q2 PASS (N/A) - this diagnostic is not a charged trial (`prereg.md:5`).
Q3 PASS - preregistered and measured bars are identical (`prereg.md:17`, `summary.json:4`).
Q4 PASS (N/A) - no model or OOS comparison is exercised (`g411_integer_pts_extent_audit_2026-09-12.md:37`).
Q5 PASS (N/A) - no AHEAD classification is made (`g411_integer_pts_extent_audit_2026-09-12.md:1`).
Q6 PASS - 186 delivered paths report 0 non-opaque findings; all 995 candidate-added lines independently scan 0 (`q6_scan.json:8`, `q6_scan.json:73`).
Q7 PASS - four observed rate pairs each enumerate all eight declared cases, 32/32 correct (`construct_cases.csv:1`, `summary.json:7`).
Q8 PASS - premise independently replays at 30/30 containment, 30/30 first-excluded, 26/30 last-admitted, with four excesses of 0.000000333333333334 s (`summary.json:19`).
MEMO PASS - an explicit NOT VERIFIED list is present (`g411_integer_pts_extent_audit_2026-09-12.md:53`).
LOC PASS - touched Python files are 228, 164, 279, 231 and 245 lines, all at most 300 (`g411_measure.py:228`, `g411_rows.py:164`, `g411_run.py:279`, `g411_seal.py:231`, `test_g411_integer_pts_extent.py:245`).
IMPORTER PASS - the importer census found only the spec test file (`tests/platformkit/test_g411_integer_pts_extent.py:7`).
TEST PASS - `python -m pytest tests/platformkit/test_g411_integer_pts_extent.py -q` -> 20 passed in 0.90s.
REPRODUCED - claimed premise 30/30, 30/30, 26/30 plus four 0.000000333333 s excesses; measured 30/30, 30/30, 26/30 plus four 0.000000333333333334 s excesses. Claimed exact 30/30 both endpoints and eight changed rows; measured the same (`summary.json:19`).
CORRECTION (minimal diff) - at `g411_measure.py:38`, pass an empty admitted list and preserve parent `unknown_reason=start_outside_schedule` while retaining any G411 alias; add an empty-schedule parent-field comparison at `test_g411_integer_pts_extent.py:216`.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G411 | premise 30/30 containment, 30/30 first-excluded, 26/30 last-admitted; exact PTS 30/30 both endpoints; zero-frame schedule raises instead of retaining parent EOF_SHORT state | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Contract A1 cannot run on master because master lacks `tests/platformkit/test_g411_integer_pts_extent.py`; candidate-worktree execution is the only available run (`VERIFIER_CONTRACT.md:11`).
NEW GAP: The retained-source receipt records height but not width, so it does not state full resolution per A9 (`source_receipts.csv:1`).
