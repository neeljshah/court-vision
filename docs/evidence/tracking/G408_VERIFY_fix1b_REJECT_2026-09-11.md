VERDICT: REJECT
Candidate: 3245691f748ab4057623af5dd007be310fe5e8ad.
ACCEPTANCE temporal containment: PASS; raw schedules give 30/30 DEADLINE and 30/30 last PTS < deadline <= first excluded PTS (summary.json:14; paired_stops.csv:1).
ACCEPTANCE endpoint honesty: FAIL; G401 defines extent from first excluded PTS, but G408 assigns first_boundary_extent_s from last-admitted span (scripts/platformkit/tracking/g401_measure.py:142; scripts/platformkit/tracking/g408_tables.py:65).
ACCEPTANCE complete proposal: FAIL; positive infinity becomes DEADLINE, not UNKNOWN, and an explicit-cap/deadline tie is classified DEADLINE (PROPOSED_g408_pts_duration.diff:230; PROPOSED_g408_pts_duration.diff:349).
ACCEPTANCE controls/evidence: PASS; 30 unique sources, 30 unique 5x6 controls, all 30 j00-j29 cards inspected, and the proposal applies cleanly (construct_cases.csv:1; eye_index.csv:1).
MEMO NOT VERIFIED list: PASS (g408_pts_duration_stop_proposal_2026-09-11.md:40).
B1 PASS: all 30 source rows remain scored and UNKNOWN/EOF_SHORT counts are explicit (summary.json:5; summary.json:15).
B2 FAIL: source receipt fields, endpoint_gap_s, and contiguous were removed or renamed without aliases (pre_fix1b/source_receipts.csv:1; source_receipts.csv:1; pre_fix1b/admitted_indices.csv:1; admitted_indices.csv:1).
B3 PASS: absent timestamps terminate UNKNOWN (scripts/platformkit/tracking/g408_stop.py:67).
B4 PASS: this mechanics-only row has no claim/retry state (g408_pts_duration_stop_proposal_2026-09-11.md:5).
B5 PASS: the proposal is applied nowhere (summary.json:22).
B6 PASS: no module was moved or retired (proposal_checks.json:18).
B7 PASS: all 30 evenly ordered cards were inspected, including j02 (eye_index.csv:1; renders/j02_nba__1rZZ_7buX_Y_s5474.txt:1).
B8 PASS: no fitted quantity is used (prereg.md:15).
B9 PASS: denominator is 30 unique source schedules, with controls separate (summary.json:5; summary.json:7).
B10 FAIL: the inherited first-excluded extent bar was replaced by last-admitted extent (scripts/platformkit/tracking/g401_timebase.py:55; scripts/platformkit/tracking/g408_tables.py:65).
Q1 PASS: seal a419e4c00ec9936bc5eefd036f822c044936a7bf82004b55bc3b276f7e90ed88 and amendment seal e48f0c184e4cb09f98956ee117cf5826287d7b582dd3411f483d70e803dc0fdc predate scoring (prereg.md:26; prereg_amendment_A1.md:12).
Q2 PASS: this is an uncharged mechanics comparison (prereg.md:5).
Q3 FAIL: G401 uses first-excluded extent; the candidate uses last-admitted extent (scripts/platformkit/tracking/g401_measure.py:142; scripts/platformkit/tracking/g408_tables.py:65).
Q4 PASS: no OOS model comparison is made (prereg.md:15).
Q5 PASS: no comparative promotion is claimed (g408_pts_duration_stop_proposal_2026-09-11.md:1).
Q6 PASS: 213 evidence texts plus the added memo/ledger text have 0 non-opaque prohibited-pattern hits (q6_scan.json:7).
Q7 PASS: the 5 timestamp classes x 6 endpoints are exhaustive and unique (construct_cases.csv:1; summary.json:7).
Q8 PASS: same-day row; premise was nevertheless remeasured over all 30 sources (G408_spec.md:1; source_receipts.csv:1).
TEST PASS: `python -m pytest tests/platformkit/test_g408_pts_stop_proposal.py -q` -> 17 passed in 0.73s.
IMPORT CENSUS PASS: this is the only existing test file importing a touched G408 module (tests/platformkit/test_g408_pts_stop_proposal.py:7).
LOC PASS: touched Python files are 246, 115, 212, 125, and 222 lines; max 246 <= 300 (scripts/platformkit/tracking/g408_build.py:1).
ARTIFACT PASS: 213/213 SHA256SUMS paths exist and match; largest listed file is 113,472 bytes (SHA256SUMS:1).
PREMISE REPRODUCED: streamed 1,719,699,126 bytes; 30/30 source digests and 30/30 G401 endpoints match; named source has 26 duplicate/26 dropped and boundary 100.088489 (source_receipts.csv:4).
HEADLINE CORRECTED: claimed A 0/30, B 29/30, C containment 30/30 and gaps 0.000100..0.016667 reproduce; inherited first-boundary bar is 30/30, while 26/30 is last-admitted extent (paired_stops.csv:1).
CORRECTION: - first_boundary_extent = span; + first_boundary_extent = receipt.first_boundary_pts - first_pts (scripts/platformkit/tracking/g408_tables.py:65).
CORRECTION: retain endpoint_gap_s, contiguous, and prior source-receipt fields or aliases while adding the new names (scripts/platformkit/tracking/g408_tables.py:19; scripts/platformkit/tracking/g408_build.py:22).
CORRECTION: - `_pts is None or _pts != _pts`; + `_pts is None or not np.isfinite(_pts)`, with positive-infinity coverage (PROPOSED_g408_pts_duration.diff:230).
CORRECTION: check the explicit cap before the next read and update last_admitted_pts only for processed frames; add the cap/deadline tie case (PROPOSED_g408_pts_duration.diff:338).
2026-09-11 | tracking | G408 | 30/30 temporal containment; inherited first-boundary bar 30/30, not claimed 26/30; proposal mishandles positive infinity and explicit-cap tie; schemas removed without aliases | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: none.
