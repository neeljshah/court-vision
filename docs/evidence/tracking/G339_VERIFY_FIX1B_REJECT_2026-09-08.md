VERDICT: REJECT
Candidate: `f2a65ab36762782995fcba2268cf78679866b1e4`; verifier: codex-sol; 2026-09-08.
Refs: M=`docs/evidence/tracking/g339_ball_table_consumers_2026-09-08.md`; R=`.../readers.csv`; J=`.../join_report.csv`; P=`docs/evidence/tracking/g339_prereg_2026-09-08.md`; S=`docs/evidence/tracking/specs/G339_spec.md`.
ACCEPTANCE premise PASS: feature reads inline columns and `src/sim/` has no table/join call site (`src/features/feature_engineering.py:69-79`; M:7).
ACCEPTANCE census FAIL: R omits direct semantic readers `scripts/platformkit/coverage_recovery.py:23-25,190`, `scripts/platformkit/render_tracking_demo.py:40-41`, `scripts/platformkit/tracking_contract.py:69,126`, and the new harness at `scripts/platformkit/tracking/ball_join.py:34-47`; this violates S:58.
ACCEPTANCE writer PASS: both outputs and schemas are named at M:23-30.
ACCEPTANCE join PASS: independent raw-input recomputation and harness reports match J:2-3; test passes (M:34-41).
ACCEPTANCE proposal PASS: concrete consumer and columns are named at M:44 and `docs/research/organization-sprint/G339_PROPOSED_ball_join_consumer.md:3-17`.
ACCEPTANCE limitations PASS: M:52-58 is a NOT VERIFIED list; memo is 60 lines and evidence files exist except the prior-verifier copy named at M:51.
A1 FAIL: master lacks the module/test (also disclosed M:58); exact master command below ran zero tests.
A2 PASS: headline counts were recomputed from R:2-67 and the four named inputs behind J:2-3.
A3 PASS: eye check is explicitly NONE at S:62 and M:41; A4 PASS: 66/66 reader file-line keys and 1,000/1,000 unique frames per table.
A5 PASS: verifier census exposed the omitted readers above; A6 PASS (not triggered): rejected candidate was not landed.
A7 FAIL: M:51 names `G339_VERIFY_ATTEMPT1_REJECT_2026-09-08.md`, absent at verification time.
B1 PASS: exclusions are named at M:21 and no metric is conditioned on passing rows.
B2 PASS: R:1 header is unchanged, all prior reader paths/class values remain, and no Python changed; no field, status value, or reader behavior was removed.
B3 PASS: no gate was added (M:42-45); B4 PASS: no claim lifecycle exists (M:42-45).
B5 PASS: no deployed tree was written (M:5,9); B6 PASS: no module moved or retired (M:34,51).
B7 PASS: no head slice or render claim (M:41); B8 PASS: no fitted comparison (M:45).
B9 PASS: independent counts are 1,000 unique frames per table, not recycled units (J:2-3).
B10 PASS: fixed bar remains byte-identical at P:11 and S:58-60.
Q1 PASS: seal `c7076a...` recomputes at P:14; prereg commit `dc2939d48` precedes report commit `fbbab4784`.
Q2 PASS: no charged trial (P:13); Q3 PASS: no bar or threshold moved (P:11; S:58-60).
Q4 PASS: no OOS score (P:13); Q5 PASS: no AHEAD claim (P:13).
Q6 PASS: automated vocabulary scan over memo, artifacts, harness, test, proposal, and row found 0 violations (M:60).
Q7 FAIL: the construct is not exhaustive because the census omissions above contradict M:21,47.
Q8 PASS: binding premise independently holds (`src/features/feature_engineering.py:69-79`; M:7).
TEST master `C:\Users\neelj\nba-ai-system> set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g339_ball_join.py -q -p no:cacheprovider` -> 0 ran, exit 4 (file absent).
TEST candidate `C:\Users\neelj\nba-track-a13> set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g339_ball_join.py -q -p no:cacheprovider` -> 1 passed in 1.57s.
TEST/LOC: import scan found only the spec test importing `ball_join`; candidate touched 0 `.py`; G339 harness/test are 100/31 LOC, each <=300 (M:34,41).
PREMISE NUMBER: current local full census is 9/361 zero-detected tables, median detected share 0.4747, and 0/357 tracking headers with `cls`; quoted premise is 10/485 and 0.8667 (S:17-19).
HEADLINE READERS: claimed 66 = 28/17/1/2/18 and 9 frame joins (M:15-20); R recomputes 66 unique file-line rows across 63 files, but verifier lower bound is >=70 readers and >=10 joins after four omissions.
HEADLINE JOIN: claimed 907/1000 and 803/1000 (M:1); independently reproduced 907/1000 and 803/1000, distance n=904/803, with all saved quantiles exact (J:2-3).
MINIMAL DIFF: add the four cited readers to R with their actual classes/frame flags, then repeat the same whole-scope census and recompute M:15-21 plus the G339 ledger totals.
MINIMAL DIFF: until that recount is exhaustive, change M:1 `DONE` to `PARTIAL`; do not alter the reproduced join report.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G339 | premise holds; census 66 rows/63 files but omits direct readers; joins 907/1000 and 803/1000 reproduced | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Master cannot run the required G339 test because `scripts/platformkit/tracking/ball_join.py` and `tests/platformkit/test_g339_ball_join.py` are absent there (M:58).
NEW GAP: The prior-verifier copy asserted at M:51 is absent, so that named evidence path is not validated.
NEW GAP: The available local premise corpus is 361 tables, not the quoted 485; archive a corpus manifest before comparing the premise statistics (S:17-19).
NEW GAP: Linked-worktree Git metadata is outside the writable root; direct targeted Git and `lane_commit.py` both failed on `index.lock`, so an external path-specific commit is required.
