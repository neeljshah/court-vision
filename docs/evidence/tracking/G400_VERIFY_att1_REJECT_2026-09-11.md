VERDICT: REJECT
Candidate review PASS: commit 6b1a7601a stat and full diff inspected; worktree was clean before verification.
PREMISE FAIL: 530 unique old boxes/27 games, 60 frame-table ids, 12 context ids and 67 union ids reproduce, but 62/67 old ids lack title resolution, so 34 genuinely new games is not established (memo:7,40; G400_spec.md:5-6).
ACCEPTANCE identity FAIL: 300/300 unique states, 30 drawn video ids, zero exact old-id overlap and 30/30 receiver digest agreement reproduce, but zero old-game overlap is unverified (source_receipts.csv:1-31; memo:40; G400_spec.md:23).
ACCEPTANCE reliability FAIL: round 1 is n=29 and pooled is n=299, not the required n=30/n=300; round 8 kappa 0.3605 and median gap 24.021 px vs 13.75 px also fail (kappa.csv:2,9,12; usability.json:2-10; G400_spec.md:24).
ACCEPTANCE yield PASS: 116 unique additions/300 = 0.3867 across 30 games, so the fixed uniform route closes at limit and no next stage is permitted (yield.csv:2-7; G400_spec.md:25).
REPRODUCED: claimed/measured old 530/27, eligible artifact rows 34, draw 30, states 300; yield 116/300 = 0.3867; round-8 0.3605; pooled 0.7505 at n=299; gap 24.021/13.75 px (premise.json:2-20; summary.json:2-52).
EVIDENCE PASS: every memo-named path exists; all 95 SHA256SUMS entries match current bytes and both saved digest maps agree (SHA256SUMS:1-96; repeats.json:2-113).
RENDERS PASS: 30 unique all-state entries reproduce the even-index formula; conflict strips 1, 10 and 20 were inspected across the decision order (eye_index.csv:1-31; g400_controls.py:79-112).
MEMO PASS: NOT VERIFIED exists with eight limitations, including incomplete alternate-upload checking and the missing judgment (memo:37-45).
TEST PASS: `python -m pytest tests/platformkit/test_g400_ball_reference_growth.py -q` -> 12 passed in 0.95s (test_g400_ball_reference_growth.py:1-245).
TEST IMPORTERS PASS: no existing test imports touched g400_controls or g400_finish; the required spec test above is the complete per-file list.
LOC PASS: g400_controls.py 231, g400_finish.py 139, test file 245; every touched Python file is <=300 lines.
ADDITIVITY FAIL: conflict-index `position` and crop-centre fields were removed/renamed and default settled-row behavior changed; q6 `findings` values changed from lists to objects (g400_controls.py:143-213; g400_finish.py:93-97).
B1 PASS: all 300 planned states remain in the yield denominator and the single missing judgment is named (yield.csv:2-3; memo:15,44).
B2 FAIL: the non-additive fields and behavior above meet the automatic reject condition (g400_controls.py:143-213; g400_finish.py:93-97).
B3 PASS: the missing judgment remains explicit and is resolved separately, not converted into adverse evidence (kappa.csv:2,12; memo:44).
B4 PASS: completed-answer uniqueness is enforced and no reclaimable failure state is introduced (g400_prepare.py:108-127; test_g400_ball_reference_growth.py:70-83).
B5 PASS: pod activity used row scratch/receiver paths; no production deployment or setting change is claimed (memo:11,33).
B6 PASS: no module was moved or retired, and the spec import surface resolves in the passing test (test_g400_ball_reference_growth.py:8-22).
B7 PASS: draw and eye rows use full-set even formulas; conflict renders cover all 115 conflicts (g400_prepare.py:56-65; g400_controls.py:79-83,158-203).
B8 PASS: controls are planted and no fitted residual is represented as independent evidence (prereg.md:16,22).
B9 PASS: denominator units are 300 unique frame keys and 116 unique additions, not recycled ids (native_summary.json:2-7; yield.csv:2-3).
B10 PASS: 0.60, 0.5, 120 and 300 remain fixed between spec, preregistration and code (G400_spec.md:23-25; g400_prepare.py:11-17).
Q1 PASS: seal eda637cb... recomputes and separate commit 6256cb133 predates measurement; no scored comparison is claimed (prereg.md:22-24).
Q2 PASS: no charged trial or model metric exists (prereg.md:22; memo:33).
Q3 PASS: fixed bars match the spec and failures were not lowered (kappa.csv:1-12; yield.csv:1-7).
Q4 PASS: no OOS comparison or meta-learner was run (prereg.md:22; memo:1).
Q5 PASS: no AHEAD claim is made and no next stage is allocated (memo:1,33).
Q6 PASS: independent scan of 85 row evidence/code/test/memo inputs plus the added ledger text found 0 non-opaque reserved-language hits (q6_scan.json:41-42; g400_finish.py:70-97).
Q7 FAIL: sampled reliability includes round 1 at n=29 and pooled n=299, below the binding n>=30 unit rail and explicit n=300 bar (kappa.csv:2,12; G400_spec.md:24).
Q8 FAIL: independent recount matches exact ids, but the binding genuinely-new-game premise was not established before dispatch (memo:7,40; G400_spec.md:5-6).
CORRECTION DIFF: preserve conflict-index `position`, `crop_centre_x`, `crop_centre_y` aliases and prior default inclusion behavior; preserve q6 `findings[path]` lists and add classification under a new field.
CORRECTION DIFF: memo/ledger status -> PARTIAL + NOT VALIDATED + CLOSED AT LIMIT; say 30 new video ids with alternate-upload relation unresolved, and retain n=299 without replacement.
CORRECTION DIFF: memo:28 `byte-identical` -> `row-identical`; memo:47 `82` -> `83` to match the committed scan artifact.
RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G400 | reproduced 116/300 = 0.3867, round-8 kappa 0.3605, pooled n=299 kappa 0.7505, median centre gap 24.021 px vs 13.75 px; new-game premise unresolved and one paired judgment missing | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: `audited_at_native_zoom` is derived from settled label/coordinates; 48 agreed additions appear in neither delivered render index, so a future row needs a separate all-box audit receipt (g400_score.py:179-187; eye_index.csv:1-31; conflict_index.csv:1-116).
