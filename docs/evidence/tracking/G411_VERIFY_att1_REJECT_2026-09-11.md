VERDICT: REJECT
Candidate: 8573a34be0c29cc27b889f65dc516ac73cfe3661.
ACCEPTANCE-1 PASS - 30/30 unique source binds, every timestamp array retained, 1,984 anomaly rows, and 30/30 cards (`source_receipts.csv:1`, `anomalies.csv:1`, `eye_index.csv:1`).
ACCEPTANCE-2 PASS - exact PTS gives containment 30/30, first-excluded 30/30, last-admitted 30/30, UNKNOWN 0 under the unchanged bar (`summary.json:41`, `scripts/platformkit/tracking/g411_measure.py:86`).
ACCEPTANCE-3 PASS - 32/32 exhaustive constructs and two saved-input reproductions match all 37 tables/cards per run (`summary.json:8`, `repeats.json:42`).
B1 PASS - the summary counts all 30 arm-C rows; absent sources become UNKNOWN rather than being excluded (`scripts/platformkit/tracking/g411_run.py:94`, `scripts/platformkit/tracking/g411_run.py:186`).
B2 FAIL - G411 removes seven G408 parent columns: endpoint_gap_s, first_excluded_pts, last_admitted_gap_s, last_admitted_pts, native_frame_interval_s, overshoot_s, span_s (`scripts/platformkit/tracking/g408_tables.py:19`, `scripts/platformkit/tracking/g411_run.py:29`).
B3 PASS - absent retained input produces an explicit UNKNOWN row (`scripts/platformkit/tracking/g411_run.py:94`).
B4 PASS - this is a read-only diagnostic with no claim-state mutation (`g411_integer_pts_extent_audit_2026-09-12.md:36`).
B5 PASS - PC only; no pod or deployment (`g411_integer_pts_extent_audit_2026-09-12.md:36`).
B6 PASS - no module was moved; the sole importing test and internal full-package imports resolve (`tests/platformkit/test_g411_integer_pts_extent.py:7`, `scripts/platformkit/tracking/g411_run.py:19`).
B7 PASS - cards cover all draw positions 0-29, not a head slice (`eye_index.csv:1`, `g411_integer_pts_extent_audit_2026-09-12.md:36`).
B8 PASS - exact rational replay uses no fitted points or residual claim (`g411_integer_pts_extent_audit_2026-09-12.md:17`).
B9 PASS - denominator is 30 distinct source timelines (`summary.json:9`, `draw.csv:1`).
B10 PASS - the bar remains exactly abs(extent-100) <= 1/validated_fps (`scripts/platformkit/tracking/g411_measure.py:86`, `g411_integer_pts_extent_audit_2026-09-12.md:17`).
Q1 PASS - prereg f207c8360 predates measurement and its embedded seal recomputes (`prereg.md:26`, `g411_integer_pts_extent_audit_2026-09-12.md:7`).
Q2 PASS (N/A) - this diagnostic is not a charged trial (`prereg.md:3`).
Q3 PASS - exact inherited bar is unchanged, with no added tolerance (`g411_integer_pts_extent_audit_2026-09-12.md:17`).
Q4 PASS (N/A) - no model or OOS comparison is exercised (`g411_integer_pts_extent_audit_2026-09-12.md:36`).
Q5 PASS (N/A) - no AHEAD classification is made (`g411_integer_pts_extent_audit_2026-09-12.md:1`).
Q6 PASS - scanner reports zero hits and all fixtures pass; the added ledger row is also clean (`q6_scan.json:8`, `RESULTS_LEDGER.md:783`).
Q7 PASS - 32 rows exhaust 8 cases across all 4 observed rate pairs (`construct_cases.csv:1`, `summary.json:8`).
Q8 PASS - premise independently replays as containment 30/30, first-excluded 30/30, last-admitted 26/30, with four exact 1/3000000 s excesses (`g411_integer_pts_extent_audit_2026-09-12.md:9`).
MEMO PASS - explicit NOT VERIFIED list is present (`g411_integer_pts_extent_audit_2026-09-12.md:53`).
LOC PASS - touched Python files are 113-226 lines; test is 182 lines (`scripts/platformkit/tracking/g411_run.py:1`, `tests/platformkit/test_g411_integer_pts_extent.py:1`).
TEST PASS - `python -m pytest tests/platformkit/test_g411_integer_pts_extent.py -q` -> 17 passed in 0.83s; importer survey found no other test file.
REPRODUCED - claimed premise 30/30,30/30,26/30 and 4 x 0.000000333333 s; measured 30/30,30/30,26/30 and 4 x 1/3000000 s. Claimed exact 30/30 both endpoints, 8 changed rows, 32/32 constructs; measured the same.
CORRECTION (minimal diff) - append the seven legacy fields to `g411_run.py:29`, populate same-semantics seconds aliases in `g411_rows.py:32`, and assert the G408 header is a subset of the G411 header in `test_g411_integer_pts_extent.py:115`.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G411 | premise 30/30 containment, 30/30 first-excluded, 26/30 last-admitted; exact PTS 30/30 both endpoints; B2 drops 7 parent fields | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Q6 receipt omits the touched shared ledger from its scan manifest; the added row is independently clean (`scripts/platformkit/tracking/g411_seal.py:131`, `q6_scan.json:74`).
NEW GAP: linked-worktree Git metadata is outside the writable root; targeted `git add` and the sanctioned path-filtered commit helper both failed at `index.lock`, so no verifier commit object was created.
