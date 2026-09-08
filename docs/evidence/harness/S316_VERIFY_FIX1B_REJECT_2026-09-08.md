VERDICT: REJECT
Candidate: `7cfecae9bf078e240dfd4e56f6bf4acd95e7fb54`; scope is S316 acceptance plus B1-B10/Q1-Q8 only.
ACCEPTANCE FAIL: the alternate-local arm is n=0 (`S316_mc_cross_env_2026-09-08.md:19,51-52`), so DONE at :1 conflicts with required PARTIAL (`S316_spec.md:66-67`); memo otherwise has 59 lines, eye check NONE, and a NOT VERIFIED list.
B1 PASS: all compared sets retain 180/180 unique state keys; comparer rejects duplicates and unequal keys (`s316_mc_cross_env.py:27-31`).
B2 FAIL: `_compact` removes established field `fills` and substitutes `fills_csv` (`s316_mc_cross_env.py:90-92`); the new test requires removal (`test_s316_mc_cross_env.py:34-38`). Parent/current schema recomputation found removed [`fills`], so this is non-additive.
B3 PASS: no quarantine or absent-evidence gate was added (`s316_mc_cross_env.py:101-130`).
B4 PASS: no claim lifecycle or retry state was added (`s316_mc_cross_env.py:173-213`).
B5 PASS: pod work is recorded as scratch-only under `/workspace/wt/a2` (`S316_mc_cross_env_2026-09-08.md:7`).
B6 PASS: no module moved; the touched module remains imported by its only test reader (`test_s316_mc_cross_env.py:9`).
B7 PASS: comparisons enumerate the complete 180-state construct (`S316_mc_cross_env_2026-09-08.md:16-23`).
B8 PASS: scoring uses the existing CPCV route, not a same-points residual (`s287_sim_full_pod.py:75`).
B9 PASS: denominator is 180 distinct evaluator states, independently counted (`s316_mc_cross_env.py:27-31`).
B10 PASS: BAR=0.004 and EMBARGO_DAYS=3 are unchanged (`s287_sim_full_pod.py:18`); 1e-9 is the spec threshold (`S316_spec.md:55`).
Q1 PASS: seal recomputed and its commit at 16:12:49Z predates rerun clocks from 16:42:52Z (`S316_mc_cross_env_2026-09-08_preregistration.md:39`; memo:4-5).
Q2 PASS: no charged trial; no ledger read/write and K is N/A (`S316_mc_cross_env_2026-09-08_preregistration.md:33`).
Q3 PASS: no implemented bar/default change; the cross-environment bar is only proposed (`S316_mc_cross_env_2026-09-08.md:42-43`).
Q4 PASS: 8-group CPCV uses strict redaction and the existing symmetric 3-day embargo (`s287_sim_full_pod.py:75`).
Q5 PASS: no comparison is labelled AHEAD (`S316_mc_cross_env_2026-09-08.md:43`).
Q6 PASS: prose/code vocabulary and standalone-number scans are clean; longer raw decimal cells are distinct measurements (`S316_mc_cross_env_2026-09-08.md:57-59`).
Q7 PASS: n=180 is an exhaustive 30-by-6 construct, and all six completed pairs independently counted 180 unique keys (`S316_mc_cross_env_2026-09-08.md:16-23`).
Q8 PASS: premise independently remeasured before adjudication as max p_simulator delta 0.0 on 180/180 unique states (`S316_mc_cross_env_2026-09-08.md:11,16`).
LOC PASS: touched Python files are 216 and 44 lines; repo rail passed (`s316_mc_cross_env.py:216`; `test_s316_mc_cross_env.py:44`).
EVIDENCE PASS: all memo-named paths exist; all arm CSVs are under 54 KB; hashes at memo:47 independently reproduce.
TEST `python -m pytest tests/platformkit/test_s316_mc_cross_env.py -q -p no:cacheprovider`: 3 passed in 3.65s.
TEST `python -m pytest scripts/platformkit/ingame/test_s287_sim_full_pod.py -q -p no:cacheprovider`: 1 passed, 1 xfailed in 2.76s.
TEST `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider`: 1 passed in 0.64s.
TEST `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_s316_mc_cross_env.py -q -p no:cacheprovider`: 3 setup errors from sandbox temp-lock permission; no test body ran.
TEST same conda command plus `--basetemp=.codex_s316_pytest_tmp`: died without counts at sandbox-denied temp cleanup.
TEST `/c/Users/neelj/bin/pod_run a2 -- python -m pytest tests/platformkit/test_s316_mc_cross_env.py -q -p no:cacheprovider`: no pod result; Git Bash exited before launch with Win32 error 5.
REPRODUCED: premise claimed/measured 0.0 max, 0 ticks above 1e-9, Brier/ECE deltas 0.0; local Brier/ECE 0.25590413411458335/0.13515624999999992.
REPRODUCED: cross-environment claimed/measured max p delta 0.359375 on 171/180; Brier delta 0.006218804253472238; ECE delta 0.04175347222222213.
REPRODUCED: three audit CSVs are byte-equal with 180 unique rows and zero seed/n_poss mismatches; local/pod probes agree on rand8/lineup advancement and differ on categorical choice/advancement (`S316_mc_cross_env_2026-09-08.md:38-39`).
CORRECTION MINIMAL DIFF: `summary.pop("fills", [])` -> `summary.get("fills", [])`; change `test_s316_mc_cross_env.py:37` to require both `fills` and additive `fills_csv`; restore the deleted compatibility comparison JSON.
CORRECTION MINIMAL DIFF: memo `DONE` -> `PARTIAL`, including its proposed ledger status, until the n=0 alternate-local arm completes.
2026-09-08 | in-game calibration | S316 | n=180 premise exact and cross-environment max p delta 0.359375 on 171 ticks, but the established fills field was removed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: same-hardware Torch 2.1.2 and 2.2.0 probes match at one thread with deterministic mode; the divergent 2.8.0 probe is pod-only, so version versus hardware/build remains unisolated.
NEW GAP: verifier pod routing is unavailable in this sandbox because Git Bash cannot start; the required file still has a valid local 3-pass result.
NEW GAP: this linked worktree's Git index is outside the writable sandbox; direct `git add` and `lane_commit.py` both fail on `index.lock`, so the verifier memo remains uncommitted.
