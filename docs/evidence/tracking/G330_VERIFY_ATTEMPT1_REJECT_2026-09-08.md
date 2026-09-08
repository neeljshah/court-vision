VERDICT: REJECT
Candidate: `39ee52eb0`; verification date 2026-09-08; verifier codex-sol.
PREMISE PASS: independent CSV recount = 268 files (263 pod + 5 local), 81 sha256 values, fallback group 184 files / 179 claimed videos; claimed 268 / 81 / 184 / 179 (`census.csv:1-269`).
HEADLINES PASS: all 6 proxy rows reproduce from `proxies.csv:2-7`; valid-H shares 0/40, 0/40, 39/40, NOT BUILDABLE, 35/40, NOT BUILDABLE; feet shares 0/0, 0/0, 13/199, -, 14/288, -.
HEADLINE FAIL: claimed 181/199 ledger mapping is not reproducible from committed evidence; `g330_run.py:95-103` consumes an uncommitted `ledger_stems.txt`.
ACCEPTANCE FAIL: the memo omits duplicate group ce975e8e58438d71 (2 files, 0 claimed videos) present at `census.csv:2,265`; the rule requires every sha256 group (`G330_spec.md:63-78`).
ACCEPTANCE PASS: producer cause is supported by cache key/load and fallback write (`unified_pipeline.py:834-840,858-870,969-988`; memo:11-15).
ACCEPTANCE FAIL: proxy code runs a bespoke stateless SIFT block (`g330_panorama_identity.py:144-173`), not the route's stateful matcher with cut reuse, EMA and first-frame bootstrap (`unified_pipeline.py:1262-1309`).
ACCEPTANCE PASS: 3 sections x 2 arms and every available denominator are retained; two V cells say NOT BUILDABLE (`proxies.csv:2-7`); eye check NONE and NOT VERIFIED exist (`memo:29-38`); proposed diff exists and is 39 lines.
B1 PASS: excluded feet are named and arm-specific; numerator and denominator are archived (`memo:26`; `proxies.csv:1-7`).
B2 PASS: code/schema changes are additive; four new sidecar fields have no pre-existing readers (`g330_panorama_identity.py:98-124`; `test_g330_panorama_identity.py:7-9`).
B3 PASS: premise false stops before arms; no absent-evidence quarantine was added (`g330_run.py:177-179`).
B4 PASS: no claim lifecycle was added or changed (`g330_run.py:170-188`).
B5 PASS: candidate changes contain no deploy path and report pod read-only (`memo:2`).
B6 PASS: both modules and their sole importing test remain present; no module was moved (`g330_run.py:47-51`; `test_g330_panorama_identity.py:7-10`).
B7 FAIL: selection takes the first three sorted game prefixes (`g330_prereg_2026-09-08.md:30-35`), a prohibited head slice.
B8 FAIL: RANSAC inliers are counted on the same correspondences used to fit the homography (`g330_panorama_identity.py:167-173`; `proxies.csv:1-7`).
B9 PASS: 40 decoded frames and per-arm feet evaluated are non-constant, named units (`g330_run.py:110-138`; `memo:26`).
B10 PASS: no threshold-bearing route file changed; copied 0.7 / 5.0 values match master (`g330_panorama_identity.py:162-170`; `unified_pipeline.py:1294-1299`).
Q1 FAIL: valid embedded seal 9d3951a325ebb5cd72084c00c520ac6029ed1ec448a08ce0783bf3766951ce35 names fixed S1 s1588, but scored S1 was s4453 (`g330_prereg_2026-09-08.md:33-35,131`; `memo:32`).
Q2 PASS (not applicable): no charged trial or K is claimed (`memo:1-2`).
Q3 PASS: no bar or threshold moved (`memo:2`; `G330_spec.md:69-76`).
Q4 PASS (not applicable): this is a registration screening proxy, not an OOS model comparison (`memo:28-30`).
Q5 PASS (not applicable): no AHEAD verdict is claimed (`memo:1`).
Q6 PASS: automated scan found 0 prohibited-vocabulary hits in candidate additions (`memo:48`).
Q7 PASS: census enumerates all 268 rows; the 3-section proxy is explicitly screening (`memo:3,30`; `census.csv:1-269`).
Q8 PASS: premise independently re-measured TRUE as 184 files / 179 claimed videos (`census.csv:1-269`).
TEST PASS: `python -m pytest tests/platformkit/test_g330_panorama_identity.py -q` -> 7 passed in 0.83s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 0.74s; importer survey found only the G330 test.
LOC PASS: touched Python files are 285, 191 and 94 lines, all <= 300; no renamed/removed field, status or reader behavior.
MINIMAL DIFF: add memo census row `ce975e8e58438d71 | 000002 | 000000 | 1641303 | identical general pair`.
MINIMAL DIFF: archive the 213 ledger stems beside the census or remove the unreproducible 181/199 headline.
REQUIRED FIX PASS: seal an evenly distributed selection naming realized inputs, run the route's full stateful matcher per arm, then regenerate memo/CSV before review.
2026-09-08 | tracking | G330 | premise 184/268 group with 179 claimed videos reproduced; 3x2 table reproduced; B7, B8 and Q1 failed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: `g330_panorama_identity.py:101` says three sidecar field names, but `:107-112` returns four.
