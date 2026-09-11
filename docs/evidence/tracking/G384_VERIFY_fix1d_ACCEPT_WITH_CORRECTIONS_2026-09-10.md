VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 09f87bf3654f53eb8993cdafb535c2b64b52b9d2.
ACCEPTANCE metric PASS: direct union gives 1,114/1,620 settled, 506 unsettled, 312 audited development boxes, and zero candidate executions (queue_summary.json:2-18; arm_readiness.json:2-26).
ACCEPTANCE before PASS: direct replay gives A0 0 TP/8 FP over 549; primary rows give median 17.33/p90 287.09 px at n=715; dev_boxes.csv gives 283 unique boxes/27 games (G384_spec.md:19; reference_v2_summary.json:15-29).
ACCEPTANCE bar PASS: held-out quotas are 157 VISIBLE and 161 ABSENT, but incomplete reference, time, and 312/500 boxes prohibit scoring (G384_spec.md:20; arm_readiness.json:2-24).
ACCEPTANCE n PASS: 881 original and 549 held-out keys are preserved; all 596 queue keys are unique and accounted as 90 settled plus 506 pending (G384_spec.md:21; queue_reconciliation.csv:1-597).
ACCEPTANCE eye check PASS: the 30 unique native frames are exact even indices 0..332 of all 344 settled held-out keys; labels are 15 VISIBLE/12 ABSENT/3 UNKNOWN, and the render shows reference readiness only (G384_spec.md:22; eye_check_index.csv:2-31).
ACCEPTANCE must-not-move PASS: candidate changes no historical seal, v1 reference, split, matcher, bar, route, weight, constant, daemon, or flag (G384_spec.md:23; candidate diff).
ACCEPTANCE verdict PASS: PARTIAL with unrun A8/A9/A10 at scoped limits follows the ladder; no winner is claimed (G384_spec.md:24; arm_accounting.csv:2-5; memo:1).
MEMO NOT VERIFIED PASS: candidate, training, scoring, complete reference, quota, receipt, deployment, route, weight, flag, and data writes are explicitly excluded (memo:7).
B1 PASS: every one of the 60 sealed A1 keys enters 29/60, including non-VISIBLE outcomes (g384_build.py:64-74).
B2 PASS: parent allocation/verdict fields and aliases remain, prior statuses remain, load(root) remains callable, and its only importer test was run (g384_build.py:17-23; test_g384_ball_phase2_receipt.py:82-96).
B3 PASS: UNKNOWN remains explicit and no missing evidence is converted to ABSENT (g384_build.py:47-60; adjudications_g384.csv:1-91).
B4 PASS: load(root) returns 506 keys disjoint from all 90 completed keys; duplicate append keys still raise (g384_adjudicate.py:19-36,93-104; test_g384_ball_phase2_receipt.py:65-87).
B5 PASS: no deployed tree, route, daemon, or flag file changed (memo:7; candidate stat).
B6 PASS: no module moved or retired; the touched module import resolves in its sole importer test (g384_adjudicate.py:9-12; test_g384_ball_phase2_receipt.py:9).
B7 PASS: A1 ordinals are 1,11,...,591 and render keys are the exact 30 even full-population selections (g384_build.py:64-74,136-142; eye_check_index.csv:2-31).
B8 PASS: no fitted residual is presented as independent evidence (memo:1,7).
B9 PASS: A1 uses 60 unique frame keys and the baseline replay uses 549 unique held-out keys (g384_build.py:64-74; G384_spec.md:19-21).
B10 PASS: candidate changes no harness threshold or gate value (G384_spec.md:20,23; candidate diff).
Q1 PASS: no scored comparison was launched, so the scoring seal condition is not invoked (memo:1,7).
Q2 PASS: no charged trial or candidate metric launch occurred (arm_readiness.json:25-26; memo:1).
Q3 PASS: candidate changes none of the binding bars (G384_spec.md:20; candidate diff).
Q4 PASS: no OOS or meta-learner result exists (memo:1,7).
Q5 PASS: no AHEAD result is claimed (memo:1,7).
Q6 PASS: independent character-code scan of 52 semantic added lines finds 0 non-opaque hits; maximum character code is 125 (memo:9; candidate diff).
Q7 PASS: sampled inference has 60 unique keys and eye review has 30 even unique keys (g384_build.py:64-74,136-142; eye_check_index.csv:2-31).
Q8 PASS: direct full-table premise replay gives 283/283 unique boxes across 27 games and queue 596=361 development+235 held-out with zero reference/adjudication overlap (G384_spec.md:4-5; dev_boxes.csv:1-284).
REMEASURE: claimed/reproduced A1 29/60=0.483333, Wilson [0.361750,0.606922], projection 457 [414,502]; current reference 1,114/1,620; held-out 157/161/26; audited boxes 312 (memo:1-3).
ADDITIVITY PASS: no field, status, row, module, explicit completed-path behavior, or importer was removed; the default reader now excludes completed keys as required (g384_adjudicate.py:19-42; test_g384_ball_phase2_receipt.py:65-96).
LOC PASS: g384_adjudicate.py 104 and test_g384_ball_phase2_receipt.py 96; both <=300.
TEST PASS: `python -m pytest tests/platformkit/test_g384_ball_phase2_receipt.py -q -p no:cacheprovider` -- 10 passed in 1.00s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -- 1 passed in 0.75s.
IMPORTER SURVEY PASS: test_g384_ball_phase2_receipt.py is the only existing test importing the touched module; it was run (test_g384_ball_phase2_receipt.py:9).
EVIDENCE CORRECTION: all 10 SHA-named paths exist, but the three files changed by fix 1d retain stale digests (memo:11-20).
CORRECTION: memo:18-20 replace g384_adjudicate.py digest with e2c52b7555ea0d35afb86d5577393793c883412fcc6f62e0aab76c3ad947020b, test digest with dc016e7dc75c6184e2667462fba828105a946551e9b31e5642b3263536bd359c, and ledger digest with 01bf4466f6041c146ee29a1120fd0f3d5389c4da18be8d2dfe4c28e4f51f2a33.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G384 | premise 283 unique dev boxes/27 games; 1,114/1,620 settled; default loader returns 506 unsettled disjoint from 90 completed; refresh 3 receipt digests | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: spec-listed G384 reference_v2.csv, dev_boxes.csv, weights/, predictions.csv, paired_frame_scores.csv, and summary.json remain absent (G384_spec.md:25; memo:22).
NEW GAP: the focused test lacks direct native-roundtrip, UNKNOWN-FP, and full missing-reference assertions (G384_spec.md:26; test_g384_ball_phase2_receipt.py:28-96).
