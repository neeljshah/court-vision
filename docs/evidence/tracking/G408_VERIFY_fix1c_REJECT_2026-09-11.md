VERDICT: REJECT
Candidate: dfc96c3f717b0ccf45c78d1ce5fe6a32ae07702b.
ACCEPTANCE temporal containment: PASS; raw schedules reproduce 30/30 contained, 30 DEADLINE, 0 UNKNOWN, 0 EOF_SHORT (g408_pts_duration_stop_proposal_2026-09-11/summary.json:13).
ACCEPTANCE endpoint honesty: PASS; all 30 last/boundary gaps are published and the inherited first-excluded bar is 30/30 (g408_pts_duration_stop_proposal_2026-09-11/paired_stops.csv:1).
ACCEPTANCE complete proposal: PASS; 30/30 controls, base hashes, 714 reader rows, clean validation, two repeats, and applied nowhere (g408_pts_duration_stop_proposal_2026-09-11/proposal_checks.json:14).
MEMO NOT VERIFIED list: PASS (g408_pts_duration_stop_proposal_2026-09-11.md:50).
B1 PASS: every one of 30 unique schedules remains in the metric; anomaly outcomes are explicit (g408_pts_duration_stop_proposal_2026-09-11/summary.json:13).
B2 FAIL: summary removes sport, worktree, last_admitted_gap_descriptive_n, not_verified; repeats removes scope, sealed_inputs, delivered_sha256, and runs[].identical (g408_pts_duration_stop_proposal_2026-09-11/pre_fix1c/summary.json:3; g408_pts_duration_stop_proposal_2026-09-11/pre_fix1c/repeats.json:2).
B3 PASS: absent or nonfinite timestamps terminate UNKNOWN (scripts/platformkit/tracking/g408_stop.py:74).
B4 PASS: this mechanics-only row has no reclaim state (g408_pts_duration_stop_proposal_2026-09-11.md:5).
B5 PASS: proposal_applied_anywhere is false (g408_pts_duration_stop_proposal_2026-09-11/summary.json:8).
B6 PASS: no module is moved or retired; proposed modules are parsed only (g408_pts_duration_stop_proposal_2026-09-11/proposal_checks.json:20).
B7 PASS: all 30 evenly ordered j00-j29 cards were inspected, including the mandatory j02 gap case (g408_pts_duration_stop_proposal_2026-09-11/eye_index.csv:1).
B8 PASS: no fitted quantity or inference comparison is used (g408_pts_duration_stop_proposal_2026-09-11/prereg.md:17).
B9 PASS: denominator is 30 unique real schedules; 30 exhaustive controls stay separate (g408_pts_duration_stop_proposal_2026-09-11/summary.json:3).
B10 PASS: first-excluded extent and one-native-interval bar match G401 (scripts/platformkit/tracking/g401_timebase.py:55; scripts/platformkit/tracking/g408_tables.py:68).
Q1 PASS: seal a419e4c00ec9936bc5eefd036f822c044936a7bf82004b55bc3b276f7e90ed88 verifies and predates the first metric commit (g408_pts_duration_stop_proposal_2026-09-11/prereg.md:26).
Q2 PASS: this is an uncharged mechanics comparison (g408_pts_duration_stop_proposal_2026-09-11/prereg.md:5).
Q3 PASS: the preregistered and inherited bars are unchanged (scripts/platformkit/tracking/g401_measure.py:142; scripts/platformkit/tracking/g408_tables.py:113).
Q4 PASS: no OOS model comparison is made (g408_pts_duration_stop_proposal_2026-09-11/prereg.md:17).
Q5 PASS: no comparative promotion is claimed (g408_pts_duration_stop_proposal_2026-09-11.md:1).
Q6 PASS: 341 scanned texts plus independently scanned candidate additions have 0 forbidden-pattern hits; memo and ledger addition are included (g408_pts_duration_stop_proposal_2026-09-11/q6_scan.json:8; g408_pts_duration_stop_proposal_2026-09-11/q6_scan.json:414).
Q7 PASS: five timestamp classes x six endpoints are exhaustive, unique, and all match declarations (g408_pts_duration_stop_proposal_2026-09-11/construct_cases.csv:1).
Q8 PASS: premise remeasured before verdict over the complete 30-source set (g408_pts_duration_stop_proposal_2026-09-11/source_receipts.csv:1).
IMPORT CENSUS PASS: only tests/platformkit/test_g408_pts_stop_proposal.py imports a touched module (tests/platformkit/test_g408_pts_stop_proposal.py:7).
TEST PASS [a11]: `python -m pytest tests/platformkit/test_g408_pts_stop_proposal.py -q -p no:cacheprovider` -> 19 passed in 1.04s.
TEST GAP [master]: `python -m pytest tests/platformkit/test_g408_pts_stop_proposal.py -q -p no:cacheprovider` -> 0 tests in 0.00s; path absent.
LOC PASS: touched Python files are 268, 212, 129, and 246 lines; max 268 <= 300 (scripts/platformkit/tracking/g408_build.py:1).
ARTIFACT PASS: 339/339 SHA256SUMS entries match; all required paths exist; largest artifact 113472 bytes; 127/127 archived files equal the parent bytes (g408_pts_duration_stop_proposal_2026-09-11/SHA256SUMS:1).
PREMISE REPRODUCED: streamed 1719699126 bytes in 1 MiB batches; 30/30 source hashes and G401 numeric cap endpoints match; named source has 26 duplicate, 26 dropped, boundary 100.088489 (g408_pts_duration_stop_proposal_2026-09-11/source_receipts.csv:4).
HEADLINE REPRODUCED: claimed A 0/30, B 29/30, C containment 30/30, and inherited first-boundary bar 30/30 all match direct raw-schedule arithmetic (g408_pts_duration_stop_proposal_2026-09-11/paired_stops.csv:1).
CORRECTION: summary.json add back sport="basketball", worktree="a11", last_admitted_gap_descriptive_n=30, and the unchanged not_verified array (g408_pts_duration_stop_proposal_2026-09-11/pre_fix1c/summary.json:3).
CORRECTION: repeats.json add back scope, sealed_inputs, delivered_sha256 with current digests, and runs[*].identical=true; then refresh scan and hashes (g408_pts_duration_stop_proposal_2026-09-11/pre_fix1c/repeats.json:2).
2026-09-11 | tracking | G408 | premise 30/30; A 0/30, B 29/30, C containment and inherited first-boundary bar 30/30; summary and repeat fields removed without aliases | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: current master lacks tests/platformkit/test_g408_pts_stop_proposal.py, so the required pre-landing master invocation cannot execute the lane test.
