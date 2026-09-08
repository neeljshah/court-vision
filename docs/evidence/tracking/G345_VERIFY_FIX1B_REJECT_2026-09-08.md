VERDICT: REJECT
Candidate: 1e9e766e7; scope is G345 ACCEPTANCE RULE plus B1-B10 and Q1-Q8.
ACCEPTANCE FAIL - required premise prints are absent from the candidate memo; G345_spec.md:22-25,56-59; g345_tracklet_continuity_2026-09-08.md:4-16.
PREMISE PASS - measured nba_0081 180 frames/1304 unique detections, median/p10/p90 7/4/9; wnba_5l4 180/1714, 10/6/13; both fixed-box schemas have no id field; nba_0081.csv:1, wnba_5l4.csv:1.
REPRODUCTION PASS - claimed vs measured ARM_C start changes -47.62%/-44.20% vs -47.619048%/-44.200627%; coverage +2.30/+8.23pp vs +2.300613/+8.226371pp; memo:17-23, arms.csv:2-7.
REPRODUCTION PASS - claimed/measured 200 unique cases, 600 unique rows, ARM_C reconnect 69/100, all crossing merge totals 0; memo:24-27, injections.csv:2-601.
EVIDENCE PASS - six arm rows carry n, per-section digests agree, reserved channel is NOT RUN with reason, decision is NOT REACHABLE, and NOT VERIFIED exists; memo:17-42.
LOC PASS - candidate touches no .py; supporting files are 259/137 lines and the spec test is 51, all <=300; g345_associate.py:1, g345_inject.py:1, test_g345_associate.py:1.
IMPORTER TEST SURVEY PASS - candidate touches no module; the sole G345 test imports both supporting modules; test_g345_associate.py:4-9.
B1 PASS - all available rows and all failed reconnect cases remain in named denominators; g345_associate.py:142-152, injections.csv:2-601.
B2 PASS - CSV headers are unchanged, the prior status row remains, and frame/obs_key retain additive tick aliases; arms.csv:1, injections.csv:1, g345_associate.py:154-183.
B3 PASS - absent sections and frame evidence produce PARTIAL/NOT RUN, not quarantine; memo:1,28-29,40-42.
B4 PASS - no claim or retry state exists in the candidate paths; candidate diff: four evidence-only modifications.
B5 PASS - execution is LOCAL and no deployment is claimed; memo:2-3.
B6 PASS - no file is moved or retired; candidate diff: four modifications.
B7 PASS - every available detection and every seeded case is used; eye check is NONE; memo:17-35.
B8 PASS - no fitted residual is claimed independent; ARM_C reference dependence is stated; memo:36-39.
B9 PASS - denominators vary by section and uniqueness is 3018/3018 detections plus 200/200 cases; arms.csv:2-7, injections.csv:2-601.
B10 PASS - 30 source frames, 0.30 gates, seed 3450908, 100+100 cases, and decision bars match the seal; g345_prereg_fix1b_2026-09-08.md:5-7,20.
Q1 PASS - seal 2fd3f720b209edb4ac96caa99d4717d7db24b767cd4a1feb89c8d78c2aec8454 recomputes and commit cec4e9ad3 predates scoring; g345_prereg_fix1b_2026-09-08.md:29.
Q2 PASS - this row has no charged trial or launch K; g345_prereg_fix1b_2026-09-08.md:1-29.
Q3 PASS - every numeric bar remains byte-identical to the sealed amendment; g345_prereg_fix1b_2026-09-08.md:5-7,20; memo:30-34.
Q4 PASS - no OOS or meta-learner result is claimed; memo:1-42.
Q5 PASS - no AHEAD result is claimed; memo:1,30-34.
Q6 FAIL - candidate memo lines 54-56 contain prohibited Q6 prose tokens; VERIFIER_CONTRACT.md:39-41.
Q7 PASS - 100 gap and 100 crossing cases each exceed n=30 and are fully enumerated; injections.csv:2-601.
Q8 PASS - premise remeasurement found only 2x180 frames, and the memo reports PARTIAL rather than the sealed 4x240; memo:1,36-42.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_g345_associate.py -q -p no:cacheprovider --confcutdir=tests/platformkit` - 2 passed in 9.35s.
MINIMAL DIFF: after memo line 9, restore two premise lines with the independently measured frame/detection and median/p10/p90 values above.
MINIMAL DIFF: delete memo lines 54-56; the scan result need not name prohibited Q6 vocabulary in prose.
RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G345 | 2x180 frames; ARM_C start changes -47.619048%/-44.200627%, coverage +2.300613/+8.226371pp, reconnect 69/100, crossing merges 0; premise memo omitted and Q6 prose fails | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: The sealed direct association command exits ModuleNotFoundError for src; `python -m scripts.platformkit.tracking.g345_associate` reproduces all six arm rows.
NEW GAP: A1 master rerun is unavailable before landing because master contains neither the G345 module nor its spec test; the candidate-worktree test passed.
