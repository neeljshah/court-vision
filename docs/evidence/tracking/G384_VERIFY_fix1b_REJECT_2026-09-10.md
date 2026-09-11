VERDICT: REJECT
Candidate: fb3e1952a9cb5ac8d2dab67d98fff29acad7ac09.
ACCEPTANCE metric FAIL: the sealed amendment retains all prior decisions except for supply inference, but the builder keeps only 30 old plus 30 new; 30 settled held-out keys vanish, so additive completeness is 1,114/1,620, not 1,084/1,620 (g384_prereg_amendment_A1_2026-09-10.md:5; g384_build.py:61-71,131-149; memo:5).
ACCEPTANCE before PASS: independently reproduced A0 0 TP/8 FP over 549, agreement median 17.33/p90 287.09 px at n=715, 283 unique boxes/27 games, and no candidate execution (binding_replay.json:8; reference_v2_summary.json:15; dev_boxes_summary.json:2; arm_readiness.json:26).
ACCEPTANCE bar PASS: no scoring occurred while reference, time, and 500-box requirements remain unmet; the inherited bars were not changed (G384_spec.md:20; memo:1,9).
ACCEPTANCE n FAIL: the 596 queue keys are unique, but the after-state omits 30 retained decisions and reports 536 rather than 506 unsettled keys (queue_reconciliation.csv:1-597; g384_build.py:61-71,149; memo:3,5).
ACCEPTANCE eye check FAIL: the inspected 30-frame render has 15 VISIBLE/12 ABSENT/3 UNKNOWN, but index rows 8 and 13 are absent from the candidate's declared current reference because the old held-out decisions were dropped (eye_check_index.csv:8,13; g384_build.py:131-145; G384_spec.md:22).
ACCEPTANCE must-not-move PASS: the diff changes no protected route, weight, split, matcher, daemon, flag, or historical seal (G384_spec.md:23; memo:9).
ACCEPTANCE verdict PASS WITH CORRECTION: PARTIAL and zero candidate executions are valid, but A8/A9/A10 accounting must use the additive reference counts (arm_accounting.csv:2-5; arm_readiness.json:9-24; G384_spec.md:24).
MEMO NOT VERIFIED PASS: explicit exclusions name absent training, scoring, complete reference, quota, receipt, and deployment checks (memo:9).
B1 PASS: all 60 A1 outcomes, including ABSENT and UNKNOWN, enter the 29/60 denominator (g384_build.py:58-71; memo:1).
B2 FAIL: parent fields allocation and verdict are renamed to allocation_g384 and verdict_g384 without aliases, and load(root) becomes a required two-argument call (g384_build.py:17-21,28-32; g384_adjudicate.py:29-33).
B3 PASS: UNKNOWN remains explicit and no missing reference is converted to ABSENT (g384_build.py:138-145; memo:9).
B4 PASS: completed keys are excluded and duplicate append keys raise; the focused regression passes (g384_adjudicate.py:19-39,90-95; test_g384_ball_phase2_receipt.py:58).
B5 PASS: only evidence, platformkit helpers, and the focused test changed; no deployed tree was written (memo:9).
B6 PASS: no module moved or retired, and all touched imports resolve in the focused test (g384_adjudicate.py:9-12; g384_build.py:8-12).
B7 PASS: A1 uses unique queue ordinals 1,11,...,591, spanning the 596-key set (g384_prereg_amendment_A1_2026-09-10.md:5; memo:3).
B8 PASS: no fitted residual or independent-performance claim exists (memo:1,9).
B9 PASS: the sampled denominator is 60 unique frame keys, not recycled identifiers (g384_build.py:67-70; memo:1).
B10 PASS: the candidate does not change the spec, matcher, or any threshold (G384_spec.md:20,23; g384_build.py:74-105).
Q1 PASS: both embedded seals validate, and amendment commit 9e72c5e preceded measured commit fb3e1952a (g384_execution_prereg_2026-09-10.md:31; g384_prereg_amendment_A1_2026-09-10.md:8).
Q2 PASS: no charged trial or scored metric was launched (memo:1,9; arm_readiness.json:26).
Q3 PASS: no acceptance bar was changed (G384_spec.md:20; arm_readiness.json:15-24).
Q4 PASS: no OOS score or meta-learner result exists (memo:1,9).
Q5 PASS: no AHEAD result is claimed (memo:1,9).
Q6 PASS: artifact scan reports 0 non-opaque hits over 109 files/85 logs; independent scan of the other 13 touched files and the added ledger row also found 0 (q6_scan.json:2-5; memo:7).
Q7 PASS: the sampled development result uses n=60; held-out n=0 is explicitly not estimated (memo:1,5; g384_prereg_amendment_A1_2026-09-10.md:5-7).
Q8 PASS: full joins reproduce 596=361 development+235 held-out, no settled overlap, 1,620 keys with both primaries, and 283 boxes/27 games (queue_summary.json:2-12; memo:3).
EVIDENCE PASS: all 15 memo-named paths exist and every stated SHA-256 matches (memo:11-25).
REMEASURE: claimed/reproduced A1 29/60=0.483333, Wilson [0.361750,0.606922], projection 457 [414,502], and 312 current development boxes; 30/30 new sheets exist at 1920x1080 (memo:1-5).
REMEASURE: candidate-artifact union 1,084/1,620 and held-out 139 VISIBLE/158 ABSENT/17 UNKNOWN; additive old-plus-new union 1,114/1,620, 506 unsettled, and held-out 157/161/26 (arm_readiness.json:9-14; g384_build.py:61-71,131-149).
LOC PASS: g384_adjudicate.py 101, g384_build.py 158, g384_q6_scan.py 40, test_g384_ball_phase2_receipt.py 70; all <=300.
TEST PASS: `python -m pytest tests/platformkit/test_g384_ball_phase2_receipt.py -q -p no:cacheprovider` -- 7 passed in 0.86s; `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -- 1 passed in 0.68s.
IMPORTER SURVEY PASS: only the focused test imports a touched module; it was run, while no existing test imports g384_build.py or g384_q6_scan.py (test_g384_ball_phase2_receipt.py:7).
CORRECTION: - use a1_decisions() as the complete delta; + use it only for inference and merge all 60 prior decisions with 30 new decisions by frame_key for reference/accounting, yielding 1,114 settled, 506 unsettled, held-out 157/161/26, and no held-out quota failures (g384_build.py:58-71,131-149).
CORRECTION: + retain allocation and verdict beside status/allocation_g384/verdict_g384; + preserve a safe one-argument load(root) call that defaults to the completed-decision artifact (g384_build.py:17-32,76-104; g384_adjudicate.py:29).
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G384 | premise and A1 projection reproduced; additive reference is 1,114/1,620 with 506 unsettled; candidate drops 30 prior held-out decisions and renames two fields | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: spec-listed G384 reference_v2.csv, dev_boxes.csv, weights/, predictions.csv, paired_frame_scores.csv, and summary.json are absent (G384_spec.md:25).
NEW GAP: the focused test does not exercise native roundtrip, UNKNOWN-as-FP, or full missing-reference prohibition, and no test imports g384_build.py or g384_q6_scan.py (G384_spec.md:26; test_g384_ball_phase2_receipt.py:15-70).
