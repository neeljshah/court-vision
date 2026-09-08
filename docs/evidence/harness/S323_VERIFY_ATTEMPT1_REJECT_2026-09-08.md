VERDICT: REJECT
Candidate: 1e2e9bd48; scope is S323 acceptance plus B1-B10 and Q1-Q8. A6 PASS: REJECT means no candidate landing.
PREMISE PASS: pre-row git grep found strict-redaction machinery but no adapter contract/validator/planted contract test; spec:20-23 and memo:4.
ACCEPTANCE FAIL: the fixed unknown-flag rule at preregistration.md:19 is not enforced; adapter_contract.py:137-142 accepts `unknown_flags=("sport",)` with status ACCEPT and 0 violations.
ACCEPTANCE FAIL: preregistration.md:31 requires all 12 discovered parquets, but memo:16 covers 5 (235/564 field-rows); five exact soccer field-rows are also misclassified by ingame_census_adapter.py:11-30.
ACCEPTANCE PASS: 5/5 planted behaviors and isolated test bodies pass, full NBA counts reproduce, and walkforward.py:127 remains false; spec:55-65.
A2 PASS: claimed NBA 465249 ticks/1593 games/0 violations reproduced exactly by full batch validation; 0 source nulls and 0 time violations; memo:7-8.
A4 PASS: 465249 unique state keys; census found 235 rows but 220 unique store-fields versus required 564/528; memo:6,16.
REPRODUCED tests: 5/5 planted behaviors and 21 total test cases pass; memo:1's "all 10 tests" conflicts with memo:28's 6+8+6+1=21.
A7 PASS: NOT VERIFIED exists at memo:30-34; every named path exists; memo is 46 lines and CSVs are below 5 MB.
B1 FAIL: the census headline excludes 7/12 preregistered stores without naming the excluded set; preregistration.md:31 and memo:4,16-24.
A5 PASS; B2 PASS: additions only; reader/import survey found only ingame_adapter.py:11, ingame_census_adapter.py:9, and test_s323_adapter_contract.py:8-15.
B3 PASS: required absence is reported directly, with no quarantine path; adapter_contract.py:108-123.
B4 PASS: validation returns terminal ACCEPT/REJECT and require_accepted raises; adapter_contract.py:157-168.
B5 PASS: candidate reports local execution only; memo:3,36.
B6 PASS: no moved/retired modules and all three imports resolve; ingame_adapter.py:11 and test_s323_adapter_contract.py:8-15.
B7 PASS: full-frame/full-census evidence, not a leading slice; memo:7-24.
B8 PASS: no fitted or scored comparison is claimed; memo:34.
B9 PASS: denominators are source rows and unique games; ingame_adapter.py:85-110 and ingame_census_adapter.py:38-43.
B10 PASS: no existing file changed and the landed default remains false; memo:25-26.
Q1 PASS: seal recomputes to 7262bbfaf65eab3709d864fbac88a972bb72d83de633c0c949494da18c61bd67; preregistration.md:37 precedes code/result commits.
Q2 PASS: no charged or scored comparison; preregistration.md:33-35.
Q3 FAIL: the sealed all-parquet census bar was narrowed from 12 discovered stores to 5; preregistration.md:31 and memo:4,16.
Q4 PASS: no OOS score; replay uses strict walk_forward; adapter_contract.py:171-180. Q5 PASS: no AHEAD result; memo:34.
Q6 PASS: row-artifact vocabulary scan is clean; S323_adapter_contract_2026-09-08.md:1-46.
Q7 PASS: all five construct cases are enumerated and the NBA corpus is full; test_s323_adapter_contract.py:51-88.
Q8 PASS: the binding premise was re-measured over the pre-row scripts/platformkit/eval_gate and domains trees; spec:20-23.
A1 PASS: master cwd `python -m pytest scripts/platformkit/eval_gate/test_walkforward.py -q -p no:cacheprovider` -> 8 passed; same command for test_leak_contract.py -> 6 passed; new S323 test is absent on master.
LOC PASS: adapter_contract.py=180, ingame_adapter.py=118, ingame_census_adapter.py=82, test_s323_adapter_contract.py=97; repository LOC rail passed.
TEST SETUP: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_s323_adapter_contract.py -q -p no:cacheprovider` -> 6 setup errors; `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_s323_adapter_contract.py -q -p no:cacheprovider --basetemp=.pytest-verify-s323` -> died without result; `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_s323_adapter_contract.py -q -p no:cacheprovider -p no:tmpdir` -> 6 setup errors (sandbox fixtures, not test bodies).
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_s323_adapter_contract.py -q -p no:cacheprovider -p no:tmpdir --confcutdir=tests/platformkit` -> 6 passed.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest scripts/platformkit/eval_gate/test_walkforward.py -q -p no:cacheprovider -p no:tmpdir` -> 8 passed.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest scripts/platformkit/eval_gate/test_leak_contract.py -q -p no:cacheprovider -p no:tmpdir` -> 6 passed.
TEST: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider -p no:tmpdir --confcutdir=tests/platformkit` -> 1 passed.
A3 PASS: Q7 replaces eye check with full reproduction; EYE CHECK NONE at memo:29.
NOT VERIFIED: a materialized full-frame AdapterFrames run; low-memory batch reproduction covered the full source and candidate construction invariants.
CORRECTION: adapter_contract.py:137-145 minimally reject flags outside FEATURE_FIELDS or flags whose named field is non-None; add a present-field flag regression.
CORRECTION: ingame_census_adapter.py:25 add exact-name AVAILABLE fallback, test the real soccer schema, regenerate all 12 stores, and change 13 to 14 and 10 tests to 21.
2026-09-08 | harness | S323 | 465249 NBA ticks/1593 games/0 validator violations and 5/5 planted cases reproduced; unknown-flag enforcement absent and soccer checkpoint census misclassified | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: `/c/Users/neelj/bin/pod_run a19 -- python -m pytest tests/platformkit/test_s323_adapter_contract.py -q -p no:cacheprovider` could not start because Git Bash failed CreateFileMapping; isolated local results are not pod results. Full materialization exited 15; batch reproduction passed. Direct git commit and lane_commit.py failed on the read-only worktree index.
