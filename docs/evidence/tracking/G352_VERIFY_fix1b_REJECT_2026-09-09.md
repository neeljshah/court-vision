VERDICT: REJECT
Candidate: `eb9eb5c592bcc96016dba863a721a6c3d8e6ef24`; verification is read-only except this memo.
ACCEPTANCE FAIL - the evidence memo is 70 lines, above the 60-line limit (`G352_spec.md:81`; `g352_calibration_whole_template_2026-09-08.md:70`).
ACCEPTANCE FAIL - S1/S2 lack even-rank per-arm renders; S3/S4 use bytes unequal to scored sources, and S4 rank57/58 shows seating but no court floor (`g352_calibration_whole_template_2026-09-08.md:47-50,55,57`; `renders_fix1b/sources.csv:2-5`).
ACCEPTANCE PASS - PARTIAL names 4/6 selected sections and the 15/6-frame A/B thinning (`g352_calibration_whole_template_2026-09-08.md:1,43`; `G352_spec.md:79-80`).
PREMISE PASS - recomputed from `premise.csv:2-797`: survivor 77/398 in frame, mean 39.405925 px; whole-template 398/398, mean 3.909050 px; claimed direction reproduced.
HEADLINE PASS - recomputed `metrics.csv:2-13`: A/B/ROUTE each 0/4; A+B valid 84/84; A+B in-frame 975-1000 per-mille; forward medians 26.557-44.305 px; ROUTE feet 0/489; all claims match (`g352_calibration_whole_template_2026-09-08.md:1,34`).
UNIQUENESS PASS - `perframe.csv:2-320` has 319/319 unique section-arm-frame keys; `residuals.csv` has 126962/126962 unique section-arm-frame-point keys.
TEST PASS - `python -m pytest tests/platformkit/test_g352_whole_template_objective.py -q` -> 4 passed in 38.15s (`G352_spec.md:86-88`).
TEST PASS - `python -m pytest tests/platformkit/test_g334_court_line_registration.py -q` -> 11 passed in 8.83s (`G352_spec.md:88`).
IMPORT SURVEY PASS - the only test importing a G352 module is the 4-test file above (`test_g352_whole_template_objective.py:10`).
LOC PASS - candidate touches 0 Python files; row Python files are 88, 175, 196, 202, and 269 LOC, all <=300 (`G352_spec.md:89`).
B1 PASS - thinning is named before interpretation and no failing row is excluded (`g352_calibration_whole_template_2026-09-08.md:43`).
B2 PASS - status remains PARTIAL; no field or reader changed; new CSVs are additive and have no readers (`g352_calibration_whole_template_2026-09-08.md:1,48`).
B3 PASS - no gate or absent-evidence behavior changed (`g352_calibration_whole_template_2026-09-08.md:2`).
B4 PASS - no claim lifecycle changed (`g352_calibration_whole_template_2026-09-08.md:2`).
B5 PASS - compute is reported only in pod scratch; deployed tree stayed read-only (`g352_calibration_whole_template_2026-09-08.md:59`).
B6 PASS - candidate moves or removes no module, test, import, or command reference (`g352_calibration_whole_template_2026-09-08.md:2`).
B7 FAIL - original S1/S2 renders remain ranks 5-11; replacement S3/S4 frames are not tied to the scored source bytes (`g352_calibration_whole_template_2026-09-08.md:47-50,57`; `VERIFIER_CONTRACT.md:26`).
B8 PASS - the reported forward result uses reserved physical supports and is not presented as independent accuracy (`g352_prereg_2026-09-08.md:29-37`; `g352_calibration_whole_template_2026-09-08.md:52`).
B9 PASS - premise uses all 398 distinct template points and frame metrics retain detected-foot counts (`premise.csv:2-797`; `metrics.csv:2-13`).
B10 PASS - bar remains feet share >=0.60 at n>=100, validH >=0.50, median <=8 px (`G352_spec.md:72-74`; `g352_calibration_whole_template_2026-09-08.md:34`).
Q1 PASS - embedded seal recomputes to `3c70dc86667bf44f6639f3d9d45cae3bdad88b6aa8a4418984287bfdff292155` and its commit precedes measurement (`g352_prereg_2026-09-08.md:71`; `g352_calibration_whole_template_2026-09-08.md:2`).
Q2 PASS - the acceptance rule defines no charged-trial or launch-K claim (`G352_spec.md:68-80`).
Q3 PASS - no bar changed after the seal (`G352_spec.md:72-74`; `g352_calibration_whole_template_2026-09-08.md:2,34`).
Q4 PASS - this is a geometric calibration measurement, with no OOS predictive or meta-learner claim (`G352_spec.md:69-76`).
Q5 PASS - no AHEAD verdict is claimed; the memo is PARTIAL (`g352_calibration_whole_template_2026-09-08.md:1`).
Q6 PASS - scanner reproduced 0 hits across the candidate's 39 added text lines (`g352_calibration_whole_template_2026-09-08.md:68-70`).
Q7 FAIL - sampled scored cells report A n=15 and B n=6 per section, both below 30 (`metrics.csv:2-13`; `VERIFIER_CONTRACT.md:45-48`).
Q8 PASS - the older-than-one-day premise was remeasured first and remains true (`premise.csv:2-797`; `VERIFIER_CONTRACT.md:49-53`).
NOT VERIFIED PASS - explicit list exists and names ground truth, source identity, and missing/ambiguous renders (`g352_calibration_whole_template_2026-09-08.md:51-57`).
MINIMAL DIFF - regenerate three renders per arm for all four sections from files matching `sections_sealed.csv:2-5` SHA-256 values; otherwise remove scored-frame content claims and relabel S4 rank57/58 as no visible court floor.
MINIMAL DIFF - raise each sampled scored arm to n>=30 and compress the evidence memo from 70 to <=60 lines without changing the sealed bar or archived values.
2026-09-09 | tracking calibration | G352 | premise 77/398 vs 398/398 reproduced; 0/4 sections met for each arm; render correction not tied to sealed source bytes | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: `docs/evidence/tracking/RESULTS_LEDGER.md:641` still says all four selected sections show no court, contradicting the corrected memo; append an authorized correction outside this verifier commit.
NEW GAP: linked-worktree Git metadata is outside the writable root; targeted `git add` and `lane_commit.py a6 G352` both failed on `index.lock`, so no verifier commit object could be created here.
