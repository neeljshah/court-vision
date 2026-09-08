VERDICT: REJECT
Candidate `0a6fded99`; verifier codex-sol; scope: S316 ACCEPTANCE RULE plus B1-B10/Q1-Q8.
ACCEPTANCE PASS (honest PARTIAL) - local premise/thread arms are complete; unavailable arms and unattributed cause are disclosed (`docs/evidence/tracking/specs/S316_spec.md:54`, `docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:14`).
PREMISE PASS - independently read 180 rows/180 unique states; all eight frozen-column max deltas, simulator Brier delta, and ECE delta versus S266 are 0.0 (`docs/evidence/harness/S316_mc_cross_env_2026-09-08/local_premise/S287_selected_tick_series.csv:1`).
REPRODUCTION PASS - claimed/reproduced local thread-1: n=180, max p_simulator delta 0.0, 0 above 1e-9, Brier/ECE deltas 0.0/0.0; prior cross-environment: n=180, max p delta 0.359375, 171 above 1e-9, Brier delta -0.006218804253472238, absolute ECE delta 0.04175347222222213 (`docs/evidence/harness/S287_repeatability_2026-09-08/S287R_pod_run1_tick_series.csv:1`).
B1 PASS - all 180 fixed states are retained; no post-score exclusion (`scripts/platformkit/ingame/s316_mc_cross_env.py:27`).
B2 PASS - commit only adds files/fields; state-key and tick readers are checked (`scripts/platformkit/ingame/s316_mc_cross_env.py:29`).
B3 PASS - no absent-evidence quarantine or gate is introduced (`scripts/platformkit/ingame/s316_mc_cross_env.py:25`).
B4 PASS - no claim lifecycle is introduced (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:29`).
B5 PASS - no deployed-tree write; pod launch did not start (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:23`).
B6 PASS - no module is moved or retired; diff-filter D/M/R is empty (`scripts/platformkit/ingame/s316_mc_cross_env.py:1`).
B7 PASS - the complete 180-state construct is compared, not a head slice (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:16`).
B8 PASS - repeatability deltas use sealed fixed states; scored records traverse CPCV (`scripts/platformkit/ingame/s287_sim_full_pod.py:75`).
B9 PASS - 180 unique state keys across 30 clusters (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:11`).
B10 PASS - 1e-9 and all S287 bars/defaults are unchanged (`docs/evidence/tracking/specs/S316_spec.md:59`).
Q1 FAIL - prereg commit `c834e10b7` is 2026-09-08T16:12:49Z, after scored sidecars at 16:02:34Z and 16:06:16Z; valid recomputed seal `d03ef82c52efc9d9b5b23e2f227c8e178deaffe9b5a9e3a522770f84ffc56064` was not committed before scoring (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:5`).
Q2 PASS - prereg states no charged trial, no ledger read/write, K N/A (`docs/evidence/harness/S316_mc_cross_env_2026-09-08_preregistration.md:33`).
Q3 PASS - no bar is lowered or re-specified (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:29`).
Q4 PASS - completed arms use 8-group CPCV, strict redaction, and symmetric 3-day embargo (`scripts/platformkit/ingame/s287_sim_full_pod.py:75`).
Q5 PASS - no comparison is labelled AHEAD (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:30`).
Q6 PASS - prose/code scan is clear and language is calibration-only (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:1`).
Q7 PASS - exhaustive construct is 30 clusters x 6 ticks = 180 unique states (`docs/evidence/tracking/specs/S316_spec.md:62`).
Q8 PASS - the local premise is remeasured and reported before adjudication (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:11`).
LOC PASS - touched Python files are 90/34 lines; repository LOC rail passed in candidate (`scripts/platformkit/ingame/s316_mc_cross_env.py:90`, `tests/platformkit/test_s316_mc_cross_env.py:34`).
ADDITIVITY PASS - no renamed/removed field, status, module, or reader behavior; sole importer is the focused test (`tests/platformkit/test_s316_mc_cross_env.py:8`).
EVIDENCE PASS - every memo-named path exists; candidate has a NOT VERIFIED list (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:37`).
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_s316_mc_cross_env.py -q -p no:cacheprovider` -> 2 setup errors from local temp permissions; no test failure.
TEST: same command plus `--basetemp=C:\Users\neelj\nba-track-a2\.pytest_tmp_s316_verify` -> no completed result; session cleanup permission error.
TEST: `/c/Users/neelj/bin/pod_run a2 -- python -m pytest tests/platformkit/test_s316_mc_cross_env.py -q -p no:cacheprovider` -> no pod result; Git Bash CreateFileMapping error prevented launch.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_s316_mc_cross_env.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 2 passed in 1.65s (local result).
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest scripts/platformkit/ingame/test_s287_sim_full_pod.py -q -p no:cacheprovider --confcutdir=scripts/platformkit` -> 1 passed, 1 xfailed in 1.89s (candidate); master 1 passed, 1 xfailed in 6.74s.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 1 passed in 1.48s (candidate); master baseline-only timing rail failed at 6.346s. Master has no S316 test path.
CORRECTION (minimal): memo:5 `- before the first S316 measurement` / `+ prereg commit postdates scored artifacts`; a new scored run must follow an immutable sealed prereg commit.
NOT VERIFIED: current pod thread-1 arm, alternate-version arm, Torch=128 arm, and the lower-level cross-environment cause; candidate lists the same limits (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:37`).
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | in-game calibration | S316 | n=180 local replay max delta 0.0 and thread-1 max delta 0.0; prereg commit postdated scored artifacts | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: The required RNG audit table is prose, and its fast_sim categorical call-site references are inaccurate; draw sites themselves are covered (`docs/evidence/harness/S316_mc_cross_env_2026-09-08.md:25`).
NEW GAP: Two new summary JSON files have 1,498 and 1,503 lines despite the spec's non-acceptance file cap (`docs/evidence/tracking/specs/S316_spec.md:74`).
