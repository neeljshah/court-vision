VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 8c83473cb8b6447fc05bcb017a1d0d7818cc92e5.
Paths: memo=docs/evidence/tracking/g304_proposal_verify_attempt2_2026-09-07.md; prereg=docs/evidence/tracking/g304_proposal_verify_prereg_2026-09-07.md.
ACCEPTANCE FAIL (correctable presentation): the valid limit closure is shown, but memo:1 omits the required 60/40/20, 2-broadcast, 2-arena, 2-rater and per-broadcast shot/split denominators from its verdict line (G304_spec.md:80-109,138-145,181-187).
PREMISE PASS: streamed originals independently match A=2841750689 bytes, h264 1920x1080 30/1, 5814.333333 s, SHA256 f2421bc24e5cbb28f41fa79f9ea755b2eeff4daebd48dc5496cc97e5617cf9d3 and B=1114349874 bytes, h264 1920x1080 30/1, 3193.666667 s, SHA256 1331fba8c2544e3ef3f44ceb7ff2886d67faa3027cc07c4d6f1919d4d53dc166; both contact sheets show visibly distinct courts (G304_spec.md:15-34; memo:52).
HEADLINE REPRO PASS: claimed vs measured = 756/756 unique proposals, 63/63 unique frames (29+34), 0/756 jointly accepted, 0/240 landmarks, and 0/40 E1-ready (0/29 Gateway Center; 0/34 Climate Pledge) (memo:1,6-18,27-34).
AGREEMENT REPRO PASS: claimed vs measured raw 743/756=0.982804 and kappa -0.007380; arena values 335/348=0.962644/-0.016173 and 408/408=1.000000/undefined; family values also reproduce (memo:17-22).
ADJUDICATION REPRO PASS: 13/13 disagreements covered, 10 REJECT + 3 UNRESOLVED + 0 ACCEPT; generous maximum is 2 landmarks on one frame (memo:27-34; test_g304_adjudication2.py:78-127).
HASH/BURDEN REPRO PASS: both rater sheets match their source commits and all three LF hashes reproduce; 55+31=86 self-reported rater minutes, not independently timed (memo:35-42).
B1 PASS: all 756 proposals and all 63 frames remain in the census; no post-rating exclusion (memo:6,16,27-34).
B2 PASS: commit is additive except one appended ledger row; the six-column schema is pinned and its only reader was checked (test_g304_adjudication2.py:12-45).
B3 PASS: no absent-evidence gate was added; absence leaves G306-G308 blocked rather than misclassified (memo:43-60).
B4 PASS: this terminal two-attempt closure adds no claim/reclaim path (memo:54-60).
B5 PASS: no deployment path is touched and the memo reports no route measurement (memo:2-4).
B6 PASS: no module, import or command target was moved or retired (test_g304_adjudication2.py:1-17).
B7 PASS: the construct enumerates every proposal and both full rating sheets; no head slice (memo:4-18).
B8 PASS: no fitting or same-point residual is used (memo:4,43-52).
B9 PASS: 756 proposal IDs and 63 frame IDs are unique; every frame has 12 proposals (memo:6,16).
B10 PASS: candidate changes only memo, test and appended ledger row; the sealed cap remains 12 and bars remain unchanged (prereg:181-192).
Q1 PASS: original seal 78f1a4f2...41335 and amended seal 3d60dcda...2696 independently reproduce and commits d625f272d then 7ca3a692a precede all ratings (prereg:163-192; memo:2-4).
Q2 PASS: this construct has no charged trial or launch K (memo:4).
Q3 PASS: no acceptance bar or harness threshold moved (prereg:134-160,181-192).
Q4 PASS: no OOS score, learner or model route was run (memo:4,43-52).
Q5 PASS: no AHEAD result is claimed (memo:1-4,54-60).
Q6 PASS: the candidate memo and added ledger row use calibration-only language (memo:1-60; RESULTS_LEDGER.md:465).
Q7 PASS: 756/756 proposals, 63/63 frames and both 756-row rating sheets are exhaustively reproduced as CONSTRUCT data (memo:4-18).
Q8 PASS: source identity and arena distinctness were remeasured before adjudicating the result (G304_spec.md:15-34; memo:52).
ADDITIVITY PASS: no field, status value, reader behavior or path is renamed/removed; reader census finds only this test for the new CSVs (test_g304_adjudication2.py:12-45).
EVIDENCE PASS: prereg, proposal/manifest/rating/adjudication files, 756/756 crop paths, two source videos and both external eligibility CSVs exist (memo:2-3,29,38-42,50-52).
LOC PASS: candidate-touched test_g304_adjudication2.py is 127 lines <= 300; related g304_proposals.py is 263 (test_g304_adjudication2.py:127; g304_proposals.py:263).
NOT VERIFIED PASS: model rater/adjudicator status, missing independent truth, semantic abstention, local renders and transcribed arena identities are explicit (memo:43-52).
TEST PASS: `python -m pytest tests/platformkit/tracking/test_g304_adjudication2.py -q -p no:cacheprovider` -> 5 passed in 0.48s.
TEST PASS: `python -m pytest tests/platformkit/tracking/test_g304_proposals.py -q -p no:cacheprovider` -> 5 passed in 1.97s; it is the sole importer of g304_proposals.py.
TEST NOTE: the same relative spec-test command in master -> 0 collected because the candidate is not yet landed there; no master file was created.
CORRECTION memo:1: replace with `INSTRUMENT NOT VALIDATED; CLOSED AT LIMIT -- E1 packet 0/60 complete: 0/2 broadcasts meet 20 eligible from >=4 shots plus 10 negatives in 4/3/3; 0/40 E1-ready, 0/20 packet-negative rows, 0/240 correspondences, 2/2 distinct arenas, 2/2 model raters; 0/756 jointly accepted on 63 candidate-eligible frames; kappa -0.007380.`
CORRECTION memo:23-25: replace SE 0.276984 and interval [-0.550269,0.535509] with independently reproduced asymptotic SE 0.002670 and interval [-0.012614,-0.002146], or delete this unregistered extra.
CORRECTION RESULTS_LEDGER.md:465: change the status prefix to `CLOSED AT LIMIT (INSTRUMENT NOT VALIDATED; attempt 2 of 2; ...)`.
2026-09-07 | tracking | G304 | sealed E1 packet remains incomplete (target 60=40 eligible+20 negatives, 240 correspondences, 2 broadcasts, 2 arenas, 2 raters); 756/756 unique proposals on 63/63 candidate-eligible frames, 0/756 jointly accepted, 0/240 landmarks, 0/40 E1-ready, kappa -0.007380; attempt 2 of 2 spent and G306-G308 blocked | CLOSED AT LIMIT (verified: codex-sol, contract A/B/Q)
NEW GAP: test_g304_adjudication2.py:1-127 does not pin the spec-test requirements for 60/40/20, 4/3/3, >=4 shots, >4 px adjudication, or p90<=12 AND max<=24.
NEW GAP: prereg:12 contains one restricted prose token outside opaque identifiers; candidate memo and added ledger row are clean.
