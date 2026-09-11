VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 0bfbe595ba3e66a495cba2755c1744f580e2d269.
PREMISE PASS: independently re-read G388/G387 inputs: original joint/terra/sol 10/11/28 of 30, LIMIT 13/14/28 of 30, real 0/30, natives 49, contexts 30, successors 0; claimed identical (input/premise_receipt.json:3).
REPRODUCTION PASS: raw truth plus 120 raw responses independently give practice sol 29/30, terra 17/30, joint 17/30; qualification sol 30/30, terra 20/30, joint 20/30; claimed identical (qualification/summary.json:7).
REPRODUCTION PASS: qualification terra p50/p90/max 0.975/2.826/26.628 px and sol 0.390/1.431/2.450 px; claimed identical (qualification/summary.json:21).
ACCEPTANCE-1 PASS: 20/30 terra fails the fixed 27/30 per-rater and joint bar, so PARTIAL/protocol not qualified is required (g392_per_rater_paint_qualification_2026-09-11.md:19).
ACCEPTANCE-2 PASS: real dispatch false, no real files, and no recovery scored (eligibility.json:16; summary.json:143).
ACCEPTANCE-3 PASS: independently hashed 180/180 tiles, 30/30 contexts, 49/49 natives, and 60/60 control images; practice/qualification share 0 pixels, truth tuples, or context-tile pairs (input/control_build_receipt.json:29).
EYE CHECK PASS WITH CORRECTION: opened all five ordered sheets for each rater, covering all 30 controls per rater; the memo's example IDs need the minimal correction below (g392_per_rater_paint_qualification_2026-09-11.md:36).
EVIDENCE PASS: all 16 concrete memo paths checked exist; 10 qualification sheets, 10 practice sheets, and 30 responses per rater exist (g392_per_rater_paint_qualification_2026-09-11.md:46).
LOC PASS: touched Python files are 89 and 96 lines, both <=300 (scripts/platformkit/tracking/g392_finish.py:1; scripts/platformkit/tracking/g392_q6_scan.py:1).
ADDITIVITY PASS: candidate has additions/modifications only, no renamed/removed field or status, and repository census found no reader/importer of either touched module (scripts/platformkit/tracking/g392_finish.py:19).
TEST PASS: `python -m pytest tests/platformkit/test_g392_per_rater_paint.py -q` -> 10 passed in 0.74s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 0.67s.
B1 PASS: all 30 unique controls per rater remain in the denominator, including failures (qualification/scores.csv:1).
B2 PASS: output keys/statuses remain additive; touched-module reader census is empty (eligibility.json:1).
B3 PASS: missing control output is explicitly a failed control, while real work is conditionally undispatched (scripts/platformkit/tracking/g392_score.py:66).
B4 PASS: no claim/reclaim path exists; the failed gate terminates dispatch (eligibility.json:16).
B5 PASS: PC-only record states no deployed-system action (g392_per_rater_paint_qualification_2026-09-11.md:46).
B6 PASS: no file was moved or retired; candidate contains only A/M paths (scripts/platformkit/tracking/g392_finish.py:1).
B7 PASS: all ordered sheets were checked, not a head slice (g392_per_rater_paint_qualification_2026-09-11.md:36).
B8 PASS: qualification pixels/truth are disjoint from practice and no offset was fitted on qualification (input/control_build_receipt.json:29).
B9 PASS: denominator is 30 unique control identities per rater, independently confirmed (qualification/truth.csv:2).
B10 PASS: fixed 27/30, 3 px, 6 px, 60 px, and 8/9 values match the sealed rule (scripts/platformkit/tracking/g392_protocol.py:8).
Q1 PASS: seal 399de158742953dddd80cb195e4799173503e80127553bde96ef39de23106e9a verifies; commit 78f691799 predates scoring (g392_prereg_2026-09-11.md:84).
Q2 PASS: no charged trial or launch-K claim is present (g392_per_rater_paint_qualification_2026-09-11.md:46).
Q3 PASS: no bar or threshold moved (scripts/platformkit/tracking/g392_protocol.py:8).
Q4 PASS: no OOS score or meta-learner is claimed (summary.json:143).
Q5 PASS: no AHEAD result is claimed; this is a failed qualification gate (g392_per_rater_paint_qualification_2026-09-11.md:29).
Q6 PASS: independent review found 0 prohibited prose/claim hits; recorded scan also reports 0 non-opaque hits (q6_scan.json:118).
Q7 PASS: qualification enumerates 30 distinct controls per rater and all were reproduced (qualification/truth.csv:2).
Q8 PASS: premise receipt was committed before practice and qualification dispatch (input/premise_receipt.json:3).
CORRECTION (minimal memo diff): at memo:36 replace `(001, 002, 014, 020) ... (024)` with `finite-band overruns 003, 004, 010, 011, 017, 021; displaced trace 020` (qualification/scores.csv:4).
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G392 | per-rater qualification sol 30/30, terra 20/30, joint 20/30 against fixed 27/30; protocol not qualified and real task not issued | PARTIAL (verified: codex-sol, contract A/B/Q)
NEW GAP: SHA256SUMS:185 lists a stale self-digest; exclude SHA256SUMS from its own manifest.
NEW GAP: scripts/platformkit/tracking/g392_q6_scan.py:37 and :78 change opacity/output handling but no existing test imports that module; add direct unit coverage.
NEW GAP: linked-worktree Git metadata is outside the writable root; the required targeted commit failed at index.lock, so an external path-specific committer must commit only this memo.
