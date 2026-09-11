VERDICT: ACCEPT
Candidate: requested G403 HEAD; stat and full diff inspected; verification applies only G403_spec.md:19-25 and VERIFIER_CONTRACT.md:19-49.
ACCEPTANCE raw PASS - external-original replay accounts for 300 unique keys, 20 archives, 600 answers, 299 pairs, all rounds, no duplicate/missing ids, and the one retained invalid coordinate (summary.json:2-5,53-68; confusion_by_round.csv:2,9,12).
REPRODUCED vs claimed PASS - pooled kappa 0.750519064713 vs 0.750519; round-8 19/30 and 0.360465116279 vs 0.360465; round-1 29 and 0.7568134/incomplete; 125 gaps, median 24.020824 vs 24.021, p90 nearest-rank 292.138666 vs 292.139, p90 linear 287.385474 vs 287.385, 288 diameters and median 27.5 (memo:3-5; summary.json:28,33,53-68).
ACCEPTANCE centre/object PASS - all 125 raw pairs retained; all 115 reasons use the sealed categories or UNRESOLVED; claimed/reproduced binding counts are round-8 4 slipped/2 aligned and other rounds 3/53; 20 supplied strips show no contradiction (memo:7-14; reason_categories.csv:1,116).
ACCEPTANCE controls PASS - exact 6x5 grid, 30 unique render/answer bindings, 20 VISIBLE centres, 5 ABSENT, 5 UNKNOWN, native dimensions/scale, and two identical regenerations with zero current digest differences (control_catalogue.csv:1-31; control_answers.csv:1-31; repeats.json:2-3,68,134).
EYE PASS - inspected all 30 controls, all 30 round-8 cards, 30 evenly indexed audit cards, and all 115 disputed crops; active and spare bench balls are separated by the sideline (memo:10,14,17,27).
B1 PASS - primary centre population retains every large gap and fixed denominator (memo:14; gaps.csv:1-126).
B2 PASS - no field/status removal: legacy settled_label is unchanged 30/30 and additive final_state preserves the prior landed result 30/30; all touched-module test importers checked (shot_claim_audit.csv:1; test_g403_ball_rater_controls.py:33-44).
B3 PASS - no evidence gate or fall-through path is introduced (memo:1; summary.json:21,71).
B4 PASS - no claim/retry mechanism is introduced (memo:1; prereg.md:3).
B5 PASS - no pre-verification deployment occurred; pod_jobs, registry_writes and flag_changes are zero (summary.json:21,24,34,71).
B6 PASS - candidate has no deleted/renamed module or orphaned test/import reference (g403_package.py:1; test_g403_ball_rater_controls.py:12-18).
B7 PASS - audit cards are evenly indexed across all 300 and every required decision image was inspected (memo:10,14,17).
B8 PASS - replay and exhaustive designed controls are not presented as independent fitted evidence (memo:22-23,50).
B9 PASS - denominators are unrecycled whole populations: 299 pairs, 125 gaps, 288 usable diameters, 115 reasons, 30 controls (summary.json:53-68; test_g403_ball_rater_controls.py:94-100,123-131).
B10 PASS - 13.75 px/0.5-diameter rule and failed G400 bars remain unchanged (G403_spec.md:23-25; memo:4,14,20).
Q1 PASS - prereg and A1 seals independently hash correctly and precede measurement (prereg.md:33; amendment_A1.md:36-50).
Q2 PASS - this is an uncharged diagnostic/CONSTRUCT row with no scored comparison (prereg.md:3,24-26).
Q3 PASS - no threshold moved; native centre rule and inherited bars are unchanged (instructions.md:15-18; memo:20).
Q4 PASS - no OOS score or meta-learner is claimed (prereg.md:3; memo:22-23).
Q5 PASS - no AHEAD claim is made (memo:22-23).
Q6 PASS - independent field-aware scan of all 16 candidate-touched text files found 0 non-opaque hits (q6_scan.json:3-10; memo:29).
Q7 PASS - all 30 CONSTRUCT cases are exhaustively enumerated, not sampled (control_catalogue.csv:2-31; G403_spec.md:25).
Q8 PASS - premise was independently replayed first from the landed external originals (memo:3-5; summary.json:35,53-68).
ADDITIVITY PASS - 30/30 frame-key order preserved; no changed reader behavior; importer census found only the focused test (shot_claim_audit.csv:1-31; test_g403_ball_rater_controls.py:18,33-44).
EVIDENCE PASS - 357/357 input size/digests and 106/106 package digests independently match; largest opened input was 657758 bytes; every memo-named path exists (input_hashes.csv:1-358; SHA256SUMS:1-107; G403_spec.md:26).
LOC PASS - touched Python files are 223, 135, 225, 110, 142 and 153 lines, each <=300 (g403_build.py:223; g403_controls.py:135; g403_package.py:225; g403_q6_scan.py:110; g403_render.py:142; test_g403_ball_rater_controls.py:153).
TEST PASS - `python -m pytest tests/platformkit/test_g403_ball_rater_controls.py -q` -> 11 passed in 0.74s; importer census identified no additional test file (test_g403_ball_rater_controls.py:1-153).
MEMO PASS - explicit six-item NOT VERIFIED list is present (memo:45-51).
CORRECTIONS: none.
2026-09-11 | tracking | G403 | independent replay reproduced 300 keys, 299 pairs, pooled kappa 0.750519, round-8 kappa 0.360465, 125 centre gaps median 24.021 px, 288 diameters; 30/30 constructed controls bound and two reproductions identical | ACCEPT (verified: codex-sol, contract A/B/Q)
NEW GAP: master does not contain tests/platformkit/test_g403_ball_rater_controls.py, so the contract-A1 master-side run cannot be performed; candidate-only run is reported above.
NEW GAP: saved q6_scan.json scans 35 files but omits candidate-added G403_VERIFY_att2_REJECT_2026-09-11.md; the independent touched-text scan includes it and remains clean.
