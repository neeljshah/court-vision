VERDICT: ACCEPT
Candidate: 7903afc8b27a0496fdc4accb2cb8d9b45aa0e1f7.
ACCEPTANCE temporal containment PASS: direct replay has 30/30 contained, 30 DEADLINE, 0 UNKNOWN, 0 EOF_SHORT (g408_pts_duration_stop_proposal_2026-09-11/summary.json:5).
ACCEPTANCE endpoint honesty PASS: all 30 last-admitted and first-boundary gaps are published; inherited first-boundary bar is 30/30 (g408_pts_duration_stop_proposal_2026-09-11/paired_stops.csv:1).
ACCEPTANCE proposed integration PASS: four-file proposal, matching bases, 714 reader rows, 30/30 controls, two exact repeats, applied nowhere (g408_pts_duration_stop_proposal_2026-09-11/proposal_checks.json:14).
MEMO NOT VERIFIED PASS: runtime, decoder-route, patched behavior, and deployment limits are explicit (g408_pts_duration_stop_proposal_2026-09-11.md:50).
B1 PASS: all 30 unique schedules remain scored and all 692 anomaly rows are retained (g408_pts_duration_stop_proposal_2026-09-11/summary.json:2).
B2 PASS: candidate removes no parent or pre-fix schema key; restored summary and repeat fields are additive (g408_pts_duration_stop_proposal_2026-09-11/repeats.json:43).
B3 PASS: missing/nonfinite and backward timestamps terminate UNKNOWN before stride work (scripts/platformkit/tracking/g408_stop.py:74).
B4 PASS: this proposal-only path has no claim or reclaim state (g408_pts_duration_stop_proposal_2026-09-11.md:5).
B5 PASS: proposal_applied_anywhere=false (g408_pts_duration_stop_proposal_2026-09-11/summary.json:27).
B6 PASS: no module moved; the affected G203 iterator reader is included in the proposal (g408_pts_duration_stop_proposal_2026-09-11/reader_survey.csv:245).
B7 PASS: all 30 evenly ordered cards j00-j29 were inspected, including the mandatory gap case (g408_pts_duration_stop_proposal_2026-09-11/eye_index.csv:2).
B8 PASS: no fitted quantity or inference comparison is used (g408_pts_duration_stop_proposal_2026-09-11/prereg.md:13).
B9 PASS: 30 unique real schedules and 30 exhaustive controls are separate denominators (g408_pts_duration_stop_proposal_2026-09-11/summary.json:13).
B10 PASS: candidate changes no bar; first-excluded extent remains within one native interval (scripts/platformkit/tracking/g408_tables.py:121).
Q1 PASS: seals a419e4c0... and e48f0c18... reproduce and predate their scored runs (g408_pts_duration_stop_proposal_2026-09-11/prereg.md:26; prereg_amendment_A1.md:12).
Q2 PASS: the mechanics comparison is uncharged and has no K (g408_pts_duration_stop_proposal_2026-09-11/prereg.md:5).
Q3 PASS: the inherited one-native-interval bar and fixed 100 s interval are unchanged (scripts/platformkit/tracking/g408_tables.py:113).
Q4 PASS: no OOS model comparison or meta-learner is present (g408_pts_duration_stop_proposal_2026-09-11/prereg.md:17).
Q5 PASS: no comparative promotion is claimed (g408_pts_duration_stop_proposal_2026-09-11.md:1).
Q6 PASS: independent scan of all 225 candidate-added lines found 0 prohibited-vocabulary hits (g408_pts_duration_stop_proposal_2026-09-11/q6_scan.json:8).
Q7 PASS: five timestamp kinds x six endpoints are exhaustive, unique, and 30/30 match declarations (g408_pts_duration_stop_proposal_2026-09-11/construct_cases.csv:2).
Q8 PASS: premise remeasured over the complete 30-source set before this verdict (g408_pts_duration_stop_proposal_2026-09-11/source_receipts.csv:1).
IMPORT CENSUS PASS: only tests/platformkit/test_g408_pts_stop_proposal.py imports the G408 modules (tests/platformkit/test_g408_pts_stop_proposal.py:7).
TEST SETUP ERROR [candidate-min]: `python -m pytest tests/platformkit/test_g408_pts_stop_proposal.py -q` -> 17 passed, 2 failed because the first test archive omitted required support files; not a candidate result.
TEST PASS [candidate 7903afc8b]: `python -m pytest tests/platformkit/test_g408_pts_stop_proposal.py -q` -> 19 passed in 0.86s.
LOC PASS: candidate diff touches no .py; all seven owned helpers plus the test are <=300 lines, max 268 (scripts/platformkit/tracking/g408_build.py:1).
ARTIFACT PASS: 19/19 required paths exist; 339/339 declared hashes match; both repeat runs match all saved outputs (g408_pts_duration_stop_proposal_2026-09-11/SHA256SUMS:254).
PREMISE REPRODUCED: streamed 1719699126 bytes in 1 MiB chunks; 30/30 source and schedule hashes match; named source has 26 duplicate, 26 dropped, endpoint 100.088489 s (g408_pts_duration_stop_proposal_2026-09-11/source_receipts.csv:4).
HEADLINE REPRODUCED: claimed A 0/30, B 29/30, C containment 30/30, C inherited first-boundary bar 30/30; direct schedule arithmetic matches (g408_pts_duration_stop_proposal_2026-09-11/summary.json:3).
CORRECTIONS: none under the acceptance rule or B1-B10/Q1-Q8.
2026-09-11 | tracking | G408 | premise 30/30; A 0/30, B 29/30, C containment and inherited first-boundary extent 30/30; proposal unapplied | ACCEPT (verified: codex-sol, contract A/B/Q)
NEW GAP: master lacks tests/platformkit/test_g408_pts_stop_proposal.py; `python -m pytest tests/platformkit/test_g408_pts_stop_proposal.py -q -p no:cacheprovider` -> no tests ran in 0.00s.
NEW GAP: memo line 38 records g408_q6.py SHA-256 4d116c36..., but candidate blob SHA-256 is 28ca115a...; candidate Q6 contents still independently scan clean.
NEW GAP: source_receipts.csv:1 maps probe positions into duration/r_frame_rate/avg_frame_rate in the wrong order; identity, dimensions, schedules, and measured results are unaffected.
NEW GAP: RESULTS_LEDGER.md:779 dates the candidate row 2026-09-12 although the local commit and evidence date are 2026-09-11.
