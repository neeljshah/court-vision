VERDICT: ACCEPT WITH CORRECTIONS
Candidate review PASS: commit 77e0e2bff stat and full diff inspected; worktree was clean before verification.
ACCEPTANCE completeness PASS: 506/506 pending keys reviewed, 1,620/1,620 unique states settled, and all 1,114 prior labels retained (g389_ball_reference_completion_2026-09-11.md:12; summary.json:50-73).
ACCEPTANCE supply PASS: 530 unique valid development boxes from 27 games, one causal neighbour removed, and zero held-out game/section overlap (g389_ball_reference_completion_2026-09-11.md:13; summary.json:40-43).
ACCEPTANCE usability PASS: median 17.33 px <= 18.50 px at n=715; controls 30/30 on each split and held-out quotas 302/188 (g389_ball_reference_completion_2026-09-11.md:14; controls.json:39-67).
B1 PASS: denominators are the full 1,620-key and 1,071-development-key censuses; excluded causal set is named as one key (summary.json:40-73).
B2 PASS: reference schema adds review_state, frames retain all prior fields and values, and surveyed readers are G389-local (reference_v3.csv:1; g389_controls.py:156-170).
B3 PASS: missing decisions remain UNVISITED while reviewed UNKNOWN remains explicit (g389_finish.py:137-143; test_g389_ball_reference_completion.py:33-37).
B4 PASS: restart allocation excludes completed keys and duplicate append is refused (g389_prepare.py:62-75; test_g389_ball_reference_completion.py:27-31).
B5 PASS: no pod use or candidate execution occurred (g389_ball_reference_completion_2026-09-11.md:8,32).
B6 PASS: no module was moved or retired; the only importing test was run (test_g389_ball_reference_completion.py:5-6).
B7 PASS: the sealed permutation and audit positions reproduce exactly; eye index has 60 unique keys and two disjoint 30-key roles (sweep_permutation.csv:1; eye_check_index.csv:1).
B8 PASS: transform rows are planted controls and descriptive agreement is not represented as independent truth (g389_ball_reference_completion_2026-09-11.md:17,28-30).
B9 PASS: 530 boxes are unique by key and section/frame pair across 27 games (context_audit.csv:2; g389_ball_reference_completion_2026-09-11.md:13).
B10 PASS: fixed 500/5, 150/150, and inherited median bars match the spec (G389_spec.md:19-21; g389_finish.py:18-19).
Q1 PASS: seal 15684f9c... recomputes and commit 4719604dd predates all judgments; no scored comparison exists (preregistration.md:34-37).
Q2 PASS: no charged trial or candidate execution exists (readiness.json:2; preregistration.md:34).
Q3 PASS: all acceptance bars are byte-consistent with the preregistration/spec (preregistration.md:28-30; G389_spec.md:19-21).
Q4 PASS: no OOS comparison or meta-learner was run (g389_ball_reference_completion_2026-09-11.md:8,28).
Q5 PASS: the result permits only a G390 premise check and makes no AHEAD claim (g389_ball_reference_completion_2026-09-11.md:3,28).
Q6 PASS: independent rescan reproduces 0 non-opaque findings over the same 97 inputs; the added ledger row has 0 findings (q6_scan.json:106; RESULTS_LEDGER.md:739).
Q7 PASS: audit and transform samples each have n=30; the 506-key and 1,071-key censuses are exhaustive (controls.json:4-37; summary.json:50-73).
Q8 PASS: premise independently remeasured before verdict and matches 1,620/1,114/506 = 301+205, 312, 157/161/26, zero executions (premise.json:2-14).
EVIDENCE PASS: all memo-named paths exist; all 24 listed artifact digests match current bytes (g389_ball_reference_completion_2026-09-11.md:33-57).
RENDER PASS: inspected the even 60-key sheet and 29-conflict montage; no missing tile or duplicate key (eye_check_index.csv:1-61).
LOC PASS: g389_controls.py 215; g389_finish.py 216; g389_q6_redact.py 69; g389_receipts.py 122; g389_reconcile.py 210.
TEST PASS: python -m pytest tests/platformkit/test_g389_ball_reference_completion.py -q -> 3 passed.
TEST PASS: python -m pytest tests/platformkit/test_loc_rail_scope.py -q -> 1 passed.
REPRODUCED premise: claimed 1,620/1,114/506, 301/205, 312, 157/161/26, 506 sheet hashes and 96,460,210 bytes; measured identical.
REPRODUCED headline: claimed 506/506, 1,620/1,620, 530 boxes/27 games, held-out 302/188/59; measured identical.
REPRODUCED usability: claimed median 17.33, threshold 18.50, n=715, p90 285.50; measured 17.33, 18.50, 715, inherited p90 287.09.
CORRECTION: g389_controls.py:102 replace int(0.9*(n-1)) with min(n-1,int(0.9*n)); regenerate controls.json:56,67 and change memo:14 p90 285.50 -> 287.09.
CORRECTION: memo:18 change eye split 36 development / 24 held-out -> 34 development / 26 held-out; eye_check_index.csv measures 34/26.
2026-09-11 | tracking | G389 | queue 506/506 and census 1,620/1,620 complete; 530 development boxes across 27 games; usability 17.33 px vs 18.50 px at n=715; p90 287.09 px | DONE WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: the prefix-refusal test name is not enforced; its first-30 prefix is accepted and only bins_covered is asserted (test_g389_ball_reference_completion.py:50,62-63).
NEW GAP: non-acceptance evidence text names dev_boxes.csv, while the candidate exports only dev_boxes_v3.csv (G389_spec.md:13,23).
