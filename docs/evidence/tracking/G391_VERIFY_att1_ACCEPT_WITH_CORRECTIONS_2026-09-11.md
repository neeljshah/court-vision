VERDICT: ACCEPT WITH CORRECTIONS
Candidate PASS: cdde13ca1 stat and full two-line diff inspected; only test_g391_ball_false_call_audit.py:118-119 changed.
ACCEPTANCE blind accounting PASS: 259/259 unique calls have two ratings, 191 AGREED + 68 ADJUDICATED, 169/169 false calls classified, and 30+30 exact even cards have zero duplicates (summary.json:2-24; eye_check_index.csv:2-61).
ACCEPTANCE raw reproduction PASS: two fresh read-only processes each reproduce 549 unique states, TP/FP/FN 90/169/212, and oracle TP/FP 90/0 with C0 0.163934 below fixed 0.25 (g391_ball_false_call_audit_2026-09-11.md:28-29).
ACCEPTANCE causal feasibility FAIL: census reproduces 0/549 eligible targets, minimum gap 244 frames, and 25 DEV pairs, but renders contain only fp/all samples; the required 30 even timeline cards with MISSING shown are absent (context_census.csv:1-550; eye_check_index.csv:1-61).
B1 PASS: all 169 false calls and 90 controls remain in the 259-row class denominator; no post-exclusion metric (object_ledger.csv:2-260).
B2 PASS: candidate adds assertions only; the source inputs and their fields/status values are unchanged, and no test imports the touched test module (test_g391_ball_false_call_audit.py:118-119).
B3 PASS: absent or incomplete causal history retains the raw call (g391_prepare.py:99-111; test_g391_ball_false_call_audit.py:58-62).
B4 PASS: this finite audit has no claim queue; all 518 ratings resolve to 259 completed packets (blind_ratings.csv:2-519; summary.json:5-8).
B5 PASS: memo records PC-only work with no pod job or deployment (g391_ball_false_call_audit_2026-09-11.md:34-36).
B6 PASS: no file is renamed or removed across the G391 commit range; all six new modules retain their sole importing test (test_g391_ball_false_call_audit.py:8-18,83).
B7 PASS: both existing 30-card sequences exactly equal independent even-index recomputation; start/middle/end images inspected (g391_finish.py:213-238; eye_check_index.csv:2-61).
B8 PASS: blind judgments precede unblinding, and raw scoring is independently reimplemented without importing the prior scorer (preregistration.md:27-39; g391_reproduce.py:1-7).
B9 PASS: independently counted 549/549 unique states and 259/259 unique call keys (premise.json:18-24).
B10 PASS: 0.25/0.90/0.01 constants equal the fixed specification values (g391_reproduce.py:26-28; G391_spec.md:22).
Q1 PASS: seal 94878be3b837b2231f8ed4931cdaa6a21f8eb8d5f3543a1320ff248dd4fa48a3 recomputes; seal-only f31377f2e predates measurement (preregistration.md:69).
Q2 PASS: no charged trial or K claim is introduced by this descriptive audit (g391_ball_false_call_audit_2026-09-11.md:34-36).
Q3 PASS: fixed bars are byte-consistent between preregistration, code, and spec (preregistration.md:43-48; g391_reproduce.py:26-28; G391_spec.md:22).
Q4 PASS: no learned OOS comparison or meta-learner is introduced; this row only replays fixed detection accounting (g391_reproduce.py:1-7).
Q5 PASS: no AHEAD claim is made; suppression is CLOSED AT LIMIT and causal work is NOT MEASURED (g391_ball_false_call_audit_2026-09-11.md:28-31).
Q6 PASS: fresh read-only scan reproduces 0 findings over the same 62 text artifacts (q6_scan.json:2-5).
Q7 PASS: scored n=549 and the two existing visual samples each have n=30; both censuses are exhaustive (premise.json:18-24; eye_check_index.csv:2-61).
Q8 PASS: premise remeasured before verdict as 549 unique states, 259 unique calls, TP/FP 90/169, FP split 100/50/19 (premise.json:18-32).
EVIDENCE PASS: all spec-named non-optional paths exist; all 20 memo receipt digests match, with 375 files and maximum file size 325004 bytes (g391_ball_false_call_audit_2026-09-11.md:37-59).
NOT VERIFIED PASS: memo explicitly lists the missing a11 disposition, six reference suspicions, 18 uncertain locations, unseen-data behavior, and unrun operations (g391_ball_false_call_audit_2026-09-11.md:34-35).
LOC PASS: candidate-touched test_g391_ball_false_call_audit.py has 120 lines, <=300 (test_g391_ball_false_call_audit.py:120).
TEST SCOPE PASS: repository test-import search finds only the spec test importing G391 modules and no importer of the touched test module (test_g391_ball_false_call_audit.py:8-18,83).
TEST PASS: python -m pytest tests/platformkit/test_g391_ball_false_call_audit.py -q -> 10 passed in 0.75s.
REPRODUCED premise: claimed 549/259/90/169, FP 100/50/19, 530 DEV boxes; measured identical, with all four cited LF digests identical.
REPRODUCED headline: claimed C0 0.163934, precision 0.347490, Wilson lower 0.292110, ALL FP/188 0.898936; measured 0.1639344262, 0.3474903475, 0.2921101651, 0.8989361702.
REPRODUCED audit: claimed/measured kappa 0.708661/0.783338, 68 disagreements, non-ball false calls 154/169 = 0.911243, six suspected reference errors.
CORRECTION: add 30 evenly spaced 549-target timeline cards/index rows with both unavailable prior slots marked MISSING; then refresh memo receipts and the 62-file scan count.
2026-09-11 | tracking | G391 | blind audit 259/259 twice; 169 false calls classified, 90 controls; raw 90/169/212; C0 0.163934 under fixed 0.25; causal supply NOT MEASURED (0/549, 25 DEV pairs) | DONE WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: preregistration.md:25 says the missing a11 disposition keeps the package diagnostic-only, while memo:1 and the existing ledger row use DONE; this premise clause is outside the acceptance-only rejection scope.
NEW GAP: linked-worktree Git metadata is outside the writable sandbox; direct git and lane_commit.py both failed on index.lock, so this verifier report remains uncommitted.
