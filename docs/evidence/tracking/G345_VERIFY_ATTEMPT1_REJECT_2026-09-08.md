VERDICT: REJECT
Candidate: 1686f0502; verification scope is G345 acceptance plus B1-B10 and Q1-Q8.
ACCEPTANCE FAIL - PARTIAL is honestly reported, but the sealed 30-frame gate was reinterpreted after scoring began; G345_spec.md:56-68, g345_associate.py:150-178.
PREMISE PASS - independent CSV census: nba_0081 180 frames/1304 unique detections, median/p10/p90 7/4/9; wnba_5l4 180/1714, 10/6/13; stride 3 and no id field; memo:10-18.
REPRODUCTION PASS - claimed vs measured ARM_C start changes: -50.79%/-48.28% vs -50.7936508%/-48.2758621%; coverage +2.45/+8.98pp vs +2.4539877/+8.9848308pp; memo:23-27.
REPRODUCTION PASS - claimed and rerun: 200 unique cases, 600 rows, ARM_C reconnect 44/100, all six merge totals 0; memo:28-30, injections.csv:2.
EVIDENCE PASS - six arm cells carry n and one digest per section; ZNCC is explicitly NOT RUN; decision is NOT REACHABLE; NOT VERIFIED exists; memo:23-47.
LOC PASS - g345_associate.py is 247 lines, within 300; g345_associate.py:1-247.
B1 PASS - every committed detection is counted and denominators are named; g345_associate.py:136-148.
B2 FAIL - read_detection_csv replaced source frame and obs_key semantics with evaluated ticks, without preserving an alias; its reader g345_inject.py:127 is not covered by the test; g345_associate.py:150-178.
B3 PASS - unavailable sections and crop evidence pass to PARTIAL/NOT RUN, not quarantine; memo:1,32-34.
B4 PASS - no claim/reclaim path exists in the touched module; g345_associate.py:224-247.
B5 PASS - evidence states local execution and no deployed-tree write; memo:3-8.
B6 PASS - no module was moved or retired; g345_associate.py:1.
B7 PASS - eye check is NONE and no render sample is claimed; memo:38.
B8 PASS - no fitted residual is evidence; ARM_C reference dependence is stated; g345_prereg_2026-09-08.md:11-15.
B9 PASS - detection and supported-pair denominators vary by section and unique rows equal rows; arms.csv:2-7.
B10 FAIL - parent read frame values directly; candidate maps stride-3 source frames 540..1077 to ticks 0..179, making age 30 equal 90 source frames; g345_associate.py:150-178.
Q1 PASS - seal recomputed exactly as 6b1c9e94305f575f641f760c775e5fe68ca217ec6d28f10b901a2e7585112709 and commit 510b480df predates scoring; g345_prereg_2026-09-08.md:18.
Q2 PASS - no charged trial or K applies to this tracking comparison; g345_prereg_2026-09-08.md:1-18.
Q3 FAIL - constant text stayed 30, but its unit changed post-seal from CSV frame to evaluated tick; g345_prereg_2026-09-08.md:5,9; g345_associate.py:166-178.
Q4 PASS - no OOS or meta-learner claim is made; memo:1-47.
Q5 PASS - no AHEAD claim is made; memo:35-37.
Q6 PASS - candidate prose and artifacts use calibration language; memo:1-56.
Q7 PASS - 100 gap and 100 crossing cases each clear n=30 and rerun completely; injections.csv:2-601.
Q8 PASS - premise was remeasured before verdict; committed inputs are 2 sections x 180 evaluated frames, not 4 x 240; memo:10-18.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g345_associate.py -q -p no:cacheprovider --basetemp=.g345_verify_test_tmp` - 0 passed; infrastructure PermissionError.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g345_associate.py -q -p no:cacheprovider -p no:tmpdir` - 0 passed, 1 setup error (tmp_path unavailable).
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g345_associate.py -q -p no:cacheprovider --noconftest` - 1 passed in 4.67s.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_loc_rail_scope.py -q -p no:cacheprovider --noconftest` - 1 passed in 1.40s.
MINIMAL DIFF: preserve `frame` and its source-based obs_key; add a separate `evaluated_tick` field rather than overwriting reader output.
MINIMAL DIFF: seal the intended tick unit in a new preregistration before scoring, then regenerate arms.csv, injections.csv, memo, and ledger row.
RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G345 | 2/4 sections x 180 frames reproduced; ARM_C changes -50.7937%/-48.2759%, reconnect 44/100, merges 0; post-seal frame-unit rewrite fails B2/B10/Q3 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: A1 master rerun is unavailable before landing because current master contains neither the candidate module nor its spec test.
NEW GAP: The two raw JSONL sources cited by basename are absent at verification, so their source bytes and raw schema cannot be independently rechecked.
NEW GAP: Direct targeted git add and lane_commit.py both failed on the external worktree index.lock ACL; no verifier commit SHA was created.
