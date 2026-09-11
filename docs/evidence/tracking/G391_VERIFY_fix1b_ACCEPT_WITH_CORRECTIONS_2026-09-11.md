VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 696acfec1e232efc08ff161ca10dce0b1e58e8ae; full text/binary diff and 35-file stat inspected.
PASS ACCEPT-1 - 259/259 unique calls rated twice; 169 FP and 90 TP reconciled, 68 adjudicated, 0 unresolved; 30 even FP plus 30 even all-call renders, each set unique (summary.json:2-24; eye_check_index.csv:2-61).
PASS ACCEPT-2 - two archived reproductions are byte-identical at 549 unique states and TP/FP/FN 90/169/212; oracle suppression is 90/0 with C0 0.163934, so the unchanged 0.25 bar is CLOSED AT LIMIT (premise.json:18-35; suppression_limit.json:46-57).
PASS ACCEPT-3 - causal census is 0/549 targets, minimum gap 244 frames, and 25 DEV pairs; 30 exact k*549//30 timeline rows show both prior slots MISSING and raw pass-through (premise.json:39-45; timeline_index.csv:2-31).
PASS PREMISE - fresh CSV census and four LF-normalized input hashes reproduced 549 unique keys, 259 unique calls, TP/FP 90/169, FP split VISIBLE/ABSENT/UNKNOWN 100/50/19, and 530 DEV boxes (premise.json:3-35).
PASS HEADLINE - claimed 549/259/90/169/212/C0 0.163934 and 0/549/244/25; reproduced 549/259/90/169/212/C0 0.163934426 and 0/549/244/25 (g391_ball_false_call_audit_2026-09-11.md:3-4).
PASS TEST SURVEY - only tests/platformkit/test_g391_ball_false_call_audit.py imports the G391 modules; all timeline-field readers were checked (test_g391_ball_false_call_audit.py:9-18,124-127).
PASS TEST - `python -m pytest tests/platformkit/test_g391_ball_false_call_audit.py -q -p no:cacheprovider` -> 11 passed in 1.49s.
PASS LOC/ADDITIVITY - sole touched .py is 127 LOC <=300; no field/status/reader removal or rename, and all new timeline columns retain the existing context names (timeline_index.csv:1; g391_build.py:119; test_g391_ball_false_call_audit.py:124-127).
FAIL MEMO - the replacement memo has no NOT VERIFIED list (g391_ball_false_call_audit_2026-09-11.md:1-42); correction below is documentation-only.
PASS B1 - all 549 rows remain in the raw and oracle denominators (suppression_limit.json:6-7,56-57).
PASS B2 - schema is additive and the reader survey is complete (timeline_index.csv:1; test_g391_ball_false_call_audit.py:124-127).
PASS B3 - absent causal history retains the raw call (preregistration.md:50-55; g391_ball_false_call_audit_2026-09-11.md:4).
PASS B4 - the result terminates as CLOSED AT LIMIT / NOT MEASURED, with no claim queue (g391_ball_false_call_audit_2026-09-11.md:1-4).
PASS B5 - candidate paths are evidence and one test only; no deployed tree is touched (g391_ball_false_call_audit_2026-09-11.md:1).
PASS B6 - no module is moved or retired; the only new reader is exercised (test_g391_ball_false_call_audit.py:124-127).
PASS B7 - FP, all-call, and causal cards are even samples, not head slices (eye_check_index.csv:2-61; timeline_index.csv:2-31).
PASS B8 - the scorer independently reimplements matching and does not import the prior scorer (g391_reproduce.py:1-6).
PASS B9 - denominators are 549 held-out states, 259 calls, 188 ABSENT states, and 169 FP (premise.json:18-35).
PASS B10 - sealed bars remain C0>=0.25, precision lower>=0.90, ALL FP/188<=0.01 (preregistration.md:45-48; suppression_limit.json:51-54).
PASS Q1 - seal 94878be3b837b2231f8ed4931cdaa6a21f8eb8d5f3543a1320ff248dd4fa48a3 reproduced; seal commit f31377f2e predates measurement commits (preregistration.md:3-5,69).
PASS Q2 - no charged trial or K is used (preregistration.md:66-68).
PASS Q3 - bars are unchanged and the unmet coverage result is CLOSED AT LIMIT (preregistration.md:45-48; suppression_limit.json:46-54).
PASS Q4 - N/A: fixed detection audit, no forecast or meta-learner comparison (preregistration.md:45-48).
PASS Q5 - no AHEAD claim is made (g391_ball_false_call_audit_2026-09-11.md:1-4).
PASS Q6 - independent scan found 0 hits across 64 row text/test artifacts; the added ledger line is clean (q6_scan.json:1-6; RESULTS_LEDGER.md:753).
PASS Q7 - sampled eye checks use n=30 and exact even ordinals (timeline_index.csv:2-31; eye_check_index.csv:2-61).
PASS Q8 - premise and full causal set were remeasured before verdict (premise.json:18-45).
PASS PATHS/RECEIPTS - every memo-named path exists and all 34 checkout-byte SHA-256 receipts match (g391_ball_false_call_audit_2026-09-11.md:5-42).
CORRECTION minimal diff after memo line 7: `+## NOT VERIFIED`
CORRECTION minimal diff: `+- A11 handoff/disposition; six suspected reference errors; 18 BALL_UNCERTAIN reviews; behavior on unseen data.`
2026-09-11 | tracking | G391 | reproduced 549 unique states, 259 calls, TP/FP/FN 90/169/212, C0 0.163934; blind audit 259/259 twice with 0 unresolved; causal archive 0/549 and 25 DEV pairs, so suppression is CLOSED AT LIMIT and causal SHADOW NOT MEASURED; restore NOT VERIFIED list | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: The A11 handoff and verifier disposition remain absent (premise.json:36); this is outside the acceptance/B/Q gates.
