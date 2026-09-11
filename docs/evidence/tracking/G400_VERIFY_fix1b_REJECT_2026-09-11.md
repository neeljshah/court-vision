VERDICT: REJECT
Candidate PASS: e2e3fb68f stat and full diff inspected; worktree clean before verification.
PREMISE FAIL: old 530 unique boxes/27 games, 60 frame ids, 12 context ids, 67 union ids, and census 184 sections/35 ids/34 eligible rows reproduce; 62/67 old identities remain title-unresolved, so 30 genuinely new games is unproved (memo:7,40; dev_boxes_v3.csv:1-531; frames_v3.csv:1-1621).
ACCEPTANCE identity FAIL: 300 unique states, 30 drawn video ids, zero exact old-id overlap, and 30/30 receiver digest agreement reproduce, but alternate-upload disjointness is NOT VALIDATED; PARTIAL is correct (memo:21; native_summary.json:2-7; source_receipts.csv:1-31).
ACCEPTANCE reliability FAIL: round 1 n=29, pooled n=299, round 8 kappa 0.3605, and median gap 24.021 px vs 13.75 px fail the stated completeness/reliability bars (kappa.csv:2,9,12; usability.json:2-10).
ACCEPTANCE yield PASS: 116 unique additions/300 = 0.3867 across 30 video ids; the fixed sampling route is CLOSED AT LIMIT and no next stage is permitted (yield.csv:2-7; memo:27,33).
REPRODUCED claimed/measured: old 530/27; states 300; receiver 30/30; round-8 0.3605; pooled 0.7505 at n=299; gap 24.021/13.75 px; yield 116/300=0.3867 (summary.json:2-52).
EVIDENCE PASS: all 23 spec-named paths exist; 95/95 SHA256SUMS entries match; largest opened row artifact is 657758 bytes (SHA256SUMS:1-96).
RENDERS PASS: draw and 30-card indices reproduce the full-set even formulas; all 115 conflict keys are indexed; cards and conflict sheets 1/10/20 inspected (eye_index.csv:1-31; conflict_index.csv:1-116).
MEMO PASS: NOT VERIFIED lists eight limitations, including unresolved upload identity and missingness (memo:37-45).
TEST PASS: `python -m pytest tests/platformkit/test_g400_ball_reference_growth.py -q` -> 12 passed in 1.50s (test_g400_ball_reference_growth.py:1-256).
TEST IMPORTERS PASS: repository search finds only the spec test importing touched g400_controls; no test imports g400_finish (test_g400_ball_reference_growth.py:188).
LOC PASS: g400_controls.py 250, g400_finish.py 143, test file 256; all touched Python files are <=300 lines.
ADDITIVITY FAIL: candidate adds the three requested aliases but changes all 115 prior nonempty `reason` values to empty (g400_controls.py:165-170; conflict_index.csv:1-116).
B1 PASS: all 300 planned states remain in the yield denominator and the omitted judgment is named (yield.csv:2-3; memo:44).
B2 FAIL: `_write_conflict_index` reads `reason` from ratings rows whose field is `adjudication_reason`, erasing an existing field's behavior (g400_controls.py:150,165-170; g400_score.py:17-19).
B3 PASS: the absent judgment remains explicit and is separately resolved, not converted into adverse evidence (kappa.csv:2,12; memo:44).
B4 PASS: completed-answer uniqueness is enforced and no claim/retry path is introduced (g400_prepare.py:108-127; test_g400_ball_reference_growth.py:84-88).
B5 PASS: candidate reports scratch/receiver activity only and no deployed-tree change (memo:11,33).
B6 PASS: no module moved or retired; the full-package import resolves in the passing test (test_g400_ball_reference_growth.py:188).
B7 PASS: draw/cards use even full-set formulas and conflict coverage is 115/115 (memo:9; eye_index.csv:1-31; conflict_index.csv:1-116).
B8 PASS: planted controls are identified as scorer controls, not independent detector evidence (prereg.md:17; transform_controls.csv:1-31).
B9 PASS: denominator is 300 unique frame keys and 116 unique additions (native_summary.json:2-7; yield.csv:2-3).
B10 PASS: candidate changes no bar; 0.60, 0.5, 120, and 300 remain fixed (g400_prepare.py:11-17; G400_spec.md:23-25).
Q1 PASS: seal eda637cb7eba86bce3b2a9b4b5850c47e140cf5f5bd08e6778bd8bf856c1bfca recomputes; commit 6256cb133 predates first metric commit ff1a70faf (prereg.md:3-25).
Q2 PASS: no charged trial or model metric is authorized or claimed (prereg.md:5,21).
Q3 PASS: fixed bars match the spec and failed bars were not lowered (prereg.md:17-19; memo:21-27).
Q4 PASS: no OOS comparison or meta-learner is present (prereg.md:5,21).
Q5 PASS: no AHEAD claim is made and no next stage is allocated (memo:1,33).
Q6 PASS: independent scan of 87 row evidence/code/test/memo inputs plus the candidate ledger addition found 0 non-opaque hits (q6_scan.json:22-32; g400_finish.py:89-102).
Q7 FAIL: kappa.csv still marks round 1 PASS at n=29 and pooled PASS at n=299 despite the explicit n=30/n=300 rail (kappa.csv:2,12; G400_spec.md:24).
Q8 FAIL: exact ids reproduce, but the binding genuinely-new-game premise was not established before rating dispatch (memo:7,15,40; G400_spec.md:5-6).
CORRECTION MINIMAL DIFF: map output `reason` from `adjudication_reason` in `_write_conflict_index`; assert all reasons are nonempty in the spec test (g400_controls.py:161-170; test_g400_ball_reference_growth.py:208-215).
CORRECTION MINIMAL DIFF: keep kappa values descriptive but mark round 1 and pooled INCOMPLETE/PARTIAL, and change memo:22-23 from PASS/MET language accordingly.
RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G400 | reproduced 116/300 = 0.3867, round-8 kappa 0.3605, pooled n=299 kappa 0.7505, median gap 24.021 px vs 13.75 px; upload identity unresolved and 115/115 conflict reasons erased | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: repeats.json:15,68 does not match the delivered conflict index; five current tables differ from both saved repeat maps, so memo:29 is no longer reproduced after fix 1b.
NEW GAP: 48 agreed additions have no delivered all-box render index; a future row needs a separate audit receipt (g400_score.py:179-187; eye_index.csv:1-31).
NEW GAP: candidate rewrites 764 existing ledger lines and regenerated text artifacts to CRLF, obscuring the one-line logical ledger change; preserve LF in future evidence commits.
