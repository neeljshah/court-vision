VERDICT: REJECT
Candidate: edbea90c5945da8309cc651f7147b0cec55be466.
ACCEPTANCE metric PASS: independent union gives 1,114/1,620 settled, 506 unsettled, and 312 audited development boxes; no candidate rank-0 score exists (queue_summary.json:13-18; arm_readiness.json:2-14,26).
ACCEPTANCE before PASS: independently reproduced A0 0 TP/8 FP over 549, agreement median 17.33/p90 287.09 px at n=715, 283 unique boxes/27 games, and no candidate execution (binding_replay.json:3-9; reference_v2_summary.json:15-29; dev_boxes_summary.json:2-40; arm_readiness.json:26).
ACCEPTANCE bar PASS: held-out quotas reproduce at 157 VISIBLE and 161 ABSENT, while incomplete reference, time, and 312/500 boxes correctly prevent scoring (arm_readiness.json:2-24; G384_spec.md:20).
ACCEPTANCE n PASS: 881 original keys and 549 held-out are preserved; all 596 unique queue keys are accounted as 90 settled plus 506 pending (queue_reconciliation.csv:1-597; queue_summary.json:2-18; G384_spec.md:21).
ACCEPTANCE eye check PASS: inspected render has 30 unique native frames at exact even sorted positions 0..332 of 344, with 15 VISIBLE/12 ABSENT/3 UNKNOWN and unmarked panels (eye_check_index.csv:2-31; G384_spec.md:22).
ACCEPTANCE must-not-move PASS: the diff changes no protected seal, reference v1, split, matcher, bar, route, weight, daemon, flag, or constant (G384_spec.md:23; memo:7).
ACCEPTANCE verdict PASS: PARTIAL with zero candidate executions is the required outcome while prerequisites remain unmet (memo:1; arm_accounting.csv:2-5; G384_spec.md:24).
MEMO NOT VERIFIED PASS: explicit exclusions name training, scoring, complete reference, quota, receipt, deployment, route, weight, flag, and data writes (memo:7).
B1 PASS: all 60 sealed A1 outcomes enter the 29/60 denominator, including non-VISIBLE labels (g384_build.py:64-74; memo:1).
B2 PASS: allocation/verdict aliases and prior status values remain; old rows/fields/readers are preserved, and load(root) remains callable (g384_build.py:17-23,30-38,101-132; g384_adjudicate.py:29-33).
B3 PASS: UNKNOWN remains explicit and no absent evidence is converted to ABSENT (g384_build.py:47-60,192-199; adjudications_g384.csv:1-91).
B4 FAIL: load(root) substitutes an empty completed set, returning all 596 keys including all 90 completed keys; the explicit completed path returns 506 with zero overlap (g384_adjudicate.py:29-33; test_g384_ball_phase2_receipt.py:82-84).
B5 PASS: only evidence, platformkit helpers, and the focused test changed; no deployed route or runtime file changed (memo:7; candidate stat).
B6 PASS: all 11 touched paths are modifications, no module moved or retired, and imports resolve (g384_adjudicate.py:9-12; g384_build.py:8-12).
B7 PASS: A1 uses unique ordinals 1,11,...,591 over all 596 queue keys; the 30-frame render is also exactly even (g384_prereg_amendment_A1_2026-09-10.md:5; eye_check_index.csv:2-31).
B8 PASS: no fitted residual or independent-performance claim exists (memo:1,7).
B9 PASS: the inference denominator is 60 unique frame keys (g384_build.py:70-73; memo:1).
B10 PASS: the candidate changes no harness threshold or gate value (G384_spec.md:20,23; g384_build.py:145-165).
Q1 PASS: both embedded seals validate, and amendment commit 9e72c5eae is an ancestor of the first A1 measurement commit fb3e1952a (g384_execution_prereg_2026-09-10.md:31; g384_prereg_amendment_A1_2026-09-10.md:8).
Q2 PASS: no charged trial or candidate metric launch occurred (memo:1,7; arm_readiness.json:26-27).
Q3 PASS: all acceptance bars remain byte-identical to the spec (G384_spec.md:20; g384_build.py:153-165).
Q4 PASS: no OOS score or meta-learner result exists (memo:1,7).
Q5 PASS: no AHEAD result is claimed (memo:1,7).
Q6 PASS: independent character-code scan of candidate additions found 0 non-opaque hits; all touched files are ASCII (memo:9).
Q7 PASS: sampled inference uses n=60; transform and render checks each use 30 evenly spaced unique keys (g384_build.py:64-74,136-142,202-203; eye_check_index.csv:2-31).
Q8 PASS: full joins reproduce 596=361 development+235 held-out, no settled overlap, 1,620 paired keys, and 283 boxes/27 games (queue_summary.json:2-12; memo:3).
EVIDENCE PASS: all 10 memo-named paths exist and every recorded SHA-256 matches (memo:11-20).
REMEASURE: claimed/reproduced A1 29/60=0.483333, Wilson [0.361750,0.606922], projection 457 [414,502]; claimed/reproduced current reference 1,114/1,620, held-out 157/161/26, and 312 boxes (memo:1; arm_readiness.json:2-14).
ADDITIVITY PASS EXCEPT B4: every prior CSV/JSON field and status value remains, all 60 old adjudication rows are unchanged, 30 are added, and both artifact aliases agree rowwise (g384_build.py:17-23,90-96; queue_reconciliation.csv:1-597).
LOC PASS: g384_adjudicate.py 101, g384_build.py 213, test_g384_ball_phase2_receipt.py 93; each <=300.
TEST PASS: `python -m pytest tests/platformkit/test_g384_ball_phase2_receipt.py -q -p no:cacheprovider` -- 10 passed in 0.96s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -- 1 passed in 0.92s.
IMPORTER SURVEY PASS: the focused test is the only existing test importing either touched module; it was run (test_g384_ball_phase2_receipt.py:9-10).
CORRECTION: g384_adjudicate.py:29-33: + DEFAULT_COMPLETED = Path("docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/adjudications_g384.csv"); - empty set default; + completed_keys(completed_path or DEFAULT_COMPLETED).
CORRECTION: test_g384_ball_phase2_receipt.py:82-84: + assert load(G373) returns 506 keys disjoint from completed_keys(OUT / "adjudications_g384.csv").
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G384 | premise and headline reproduced at 1,114/1,620 settled and held-out 157/161/26; default loader reclaims 90 completed keys | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: spec-listed G384 reference_v2.csv, dev_boxes.csv, weights/, predictions.csv, paired_frame_scores.csv, and summary.json are absent (G384_spec.md:25).
NEW GAP: the focused test still lacks direct native-roundtrip, UNKNOWN-FP, full missing-reference, and default completed-key exclusion assertions (G384_spec.md:26; test_g384_ball_phase2_receipt.py:28-93).
