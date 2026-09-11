VERDICT: REJECT
Candidate: 93b23cf56ef25a0808512066b1fcaadc8955f22e.
ACCEPTANCE-1 PASS - 30/30 unique source binds, all 30 integer streams, 1,984/1,984 unique anomaly rows, and all 30 cards are retained (`source_receipts.csv:1`, `anomalies.csv:1`, `eye_index.csv:1`).
ACCEPTANCE-2 PASS - independent exact replay gives containment 30/30, first-excluded 30/30, last-admitted 30/30, UNKNOWN 0 under the unchanged bar (`g411_integer_pts_extent_audit_2026-09-12.md:23`).
ACCEPTANCE-3 PASS - 32/32 exhaustive constructs and both saved-input reproductions match all 37 tables/cards (`construct_cases.csv:1`, `repeats.json:1`).
B1 PASS - every one of the 30 draw rows enters the denominator; absent retained evidence becomes an explicit UNKNOWN (`scripts/platformkit/tracking/g411_run.py:93`, `scripts/platformkit/tracking/g411_run.py:96`).
B2 FAIL - parent `read_frames` changes from consumed reads to full retained-stream length on 90/90 rows, and parent `contained` changes meaning on 31/90 rows (`scripts/platformkit/tracking/g408_tables.py:73`, `scripts/platformkit/tracking/g408_tables.py:78`, `scripts/platformkit/tracking/g411_rows.py:38`, `scripts/platformkit/tracking/g411_rows.py:55`).
B3 PASS - missing retained evidence remains UNKNOWN and is not silently dropped (`scripts/platformkit/tracking/g411_run.py:96`).
B4 PASS - the row is diagnostic only and performs no claim-state mutation (`g411_integer_pts_extent_audit_2026-09-12.md:38`).
B5 PASS - PC only; no pod or deployment was exercised (`g411_integer_pts_extent_audit_2026-09-12.md:38`).
B6 PASS - no module moved, and the sole direct test importer resolves by full package path (`scripts/platformkit/tracking/g411_run.py:19`, `tests/platformkit/test_g411_integer_pts_extent.py:187`).
B7 PASS - 30 cards cover draw positions 0-29; verifier sampled positions 0, 7, 15, 22, 29 (`eye_index.csv:1`).
B8 PASS - exact rational replay uses no fitted residual as independent evidence (`g411_integer_pts_extent_audit_2026-09-12.md:17`).
B9 PASS - the denominator is 30 distinct source timelines (`draw.csv:1`).
B10 PASS - the bar remains exactly `abs(extent-100) <= 1/validated_fps` (`scripts/platformkit/tracking/g411_measure.py:86`, `g411_integer_pts_extent_audit_2026-09-12.md:17`).
Q1 PASS - prereg seal recomputes to the declared f7d5b33dc3ec131b744244f97597a9ffc950e3af99b6b893733d679a9414923b and predates measurement (`prereg.md:26`, `g411_integer_pts_extent_audit_2026-09-12.md:7`).
Q2 PASS (N/A) - this diagnostic is not a charged trial (`prereg.md:5`).
Q3 PASS - the preregistered bar and measured bar are identical (`prereg.md:17`, `g411_integer_pts_extent_audit_2026-09-12.md:17`).
Q4 PASS (N/A) - no model or OOS comparison is exercised (`g411_integer_pts_extent_audit_2026-09-12.md:38`).
Q5 PASS (N/A) - no AHEAD classification is made (`g411_integer_pts_extent_audit_2026-09-12.md:1`).
Q6 PASS - candidate-added lines scan with zero vocabulary hits; delivered-path scan also reports zero (`q6_scan.json:1`).
Q7 PASS - 4 observed rate pairs each enumerate all 8 declared cases, 32/32 correct (`construct_cases.csv:1`).
Q8 PASS - independent premise replay is 30/30 containment, 30/30 first-excluded, 26/30 last-admitted, with four exact 1/3000000 s excesses (`g411_integer_pts_extent_audit_2026-09-12.md:11`).
MEMO PASS - an explicit NOT VERIFIED list is present (`g411_integer_pts_extent_audit_2026-09-12.md:54`).
LOC PASS - touched Python files are 152, 234, 234 and 196 lines, all at most 300 (`scripts/platformkit/tracking/g411_rows.py:1`, `scripts/platformkit/tracking/g411_run.py:1`, `scripts/platformkit/tracking/g411_seal.py:1`, `tests/platformkit/test_g411_integer_pts_extent.py:1`).
TEST PASS - `python -m pytest tests/platformkit/test_g411_integer_pts_extent.py -q` -> 18 passed in 1.28s; importer survey found no other test file.
REPRODUCED - claimed premise 30/30, 30/30, 26/30 and four 0.000000333333 s excesses; measured 30/30, 30/30, 26/30 and four exact 1/3000000 s excesses. Claimed exact 30/30 both endpoints, 32/32 constructs and two 37-file reproductions; measured the same.
CORRECTION (minimal diff) - in `g411_rows.py:38`, derive `read_frames` as admitted plus the boundary read; at `:48` retain absolute deadline semantics; at `:55` restore parent last-admitted-before-deadline `contained`, adding a new field if boundary reach must remain explicit.
CORRECTION (minimal diff) - extend `test_g411_integer_pts_extent.py:186` to compare all parent field meanings across all 90 keyed rows and add nonzero-origin plus UNKNOWN fixtures.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G411 | premise 30/30 containment, 30/30 first-excluded, 26/30 last-admitted; exact PTS 30/30 both endpoints; parent read_frames differs 90/90 and contained 31/90 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Contract A1 cannot run on master because master does not contain `tests/platformkit/test_g411_integer_pts_extent.py`; the candidate-worktree copy is the only executable copy (`VERIFIER_CONTRACT.md:11`).
NEW GAP: the Q6/input-identity `OWNED` list omits touched `g411_rows.py`, so it is absent from both manifests (`scripts/platformkit/tracking/g411_seal.py:24`).
NEW GAP: linked-worktree Git metadata is outside the writable root; targeted `git add` and the sanctioned path-filtered `lane_commit.py` both failed at `index.lock`, so no verifier commit object was created.
