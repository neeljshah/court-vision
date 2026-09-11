VERDICT: REJECT
Candidate: 250e3f126edd01e908ccc12c78bacfb123041310; full text/binary diff and 67-file stat inspected.
PREMISE PASS: 1,620/1,620 unique native rows, 549 held-out, labels 302/188/59, 530 unique dev boxes/27 games, zero key/game overlap; readiness.json:2-23.
HEADLINE PASS: claimed/reproduced A8 TP/FP/FN 90/169/212, C0 0.16393442622950818, Wilson95 lower 0.29211016505655896, ALL FP/188 0.898936170212766, ABSENT-only 50/188 0.26595744680851063; memo:8.
REPRODUCTION PASS: fresh archived-prediction score reproduced 1,098 rows byte-for-byte; A0 0/8/302 and A8 90/169/212; summary.json:23-47.
TEST PASS: C:\Users\neelj\anaconda3\python.exe -B -m pytest tests/platformkit/test_g390_ball_a8_sealed_pass.py -q --basetemp=.pytest_tmp_g390/verify_base_05 -> 5 passed in 0.81s.
TEST SCOPE PASS: sole existing importer is the spec test file; tests/platformkit/test_g390_ball_a8_sealed_pass.py:14.
LOC PASS: scripts/platformkit/tracking/g390_render_archived.py:77 = 77; tests/platformkit/test_g390_ball_a8_sealed_pass.py:64 = 64; both <=300.
ACCEPTANCE-1 FAIL: sealed readiness fe8bcbe... differs from launched d11a1c8c..., and compute used the wrong scratch route; memo:5,11.
ACCEPTANCE-2 PASS: 549 unique rows/arm, fixed bars all missed, and NOT VALIDATED is the specified disposition; summary.json:23-47.
ACCEPTANCE-3 FAIL: score bytes/weights/renders reproduce, but the scratch route is wrong and current render hashes conflict with sha256_manifest.txt:16-46; weights_manifest.json:8-14.
B1 PASS: every held-out row remains in each arm; summary.json:43-47.
B2 FAIL: current renders_index removed n_predictions and distance_720p instead of retaining aliases; renders/renders_index.csv:1.
B3 PASS: no queue fall-through changed; required archived inputs are refused explicitly; g390_render_archived.py:34-37.
B4 PASS: the used token is latched at SCORING_STARTED and is not reclaimable; candidate_token.json:2-9.
B5 FAIL: compute ran at /workspace/g390_scratch, outside required /workspace/wt/a11; weights_manifest.json:8.
B6 PASS: no module was moved/retired; the new module has a live full-package importer; test_g390_ball_a8_sealed_pass.py:14.
B7 PASS: 30 unique keys equal the deterministic even selection over 549; g390_render_archived.py:43-50; renders_index.csv:2-31.
B8 PASS: scores use the separately settled reference hash, not fitted points; summary.json:56-58.
B9 PASS: denominators are 549 unique held-out and 188 ABSENT, not recycled units; summary.json:43-47.
B10 PASS: bars remain 0.25/0.90/0.01 byte-identical to the spec; summary.json:26-28; G390_spec.md:20.
Q1 FAIL: seal predates scoring and recomputes, but the scored memo names neither preregistration path nor seal and its readiness identity mismatches; preregistration.md:21,49; memo:5.
Q2 PASS: one token is charged and latched before scorer work; g390_a8_run.py:232; candidate_token.json:2-9.
Q3 PASS: all three immutable bars are unchanged; G390_spec.md:20; summary.json:26-28.
Q4 PASS: 7,686 paired CPCV records, 28 splits, equal arm keys, feature_ts before state_ts; g390_score.py:99; summary.json:49-54.
Q5 PASS: no AHEAD claim is made; the candidate reports NOT VALIDATED; memo:1,8.
Q6 PASS: independent scan of all added prose found 0 prohibited-language/figure hits; q6_scan.json:1.
Q7 PASS: scored n=549 and render n=30; summary.json:47; renders_index.csv:2-31.
Q8 PASS: premise was independently remeasured before verdict and remains numerically true apart from the disclosed identity mismatch; readiness.json:2-23.
NOT VERIFIED PASS: memo includes an explicit list covering repeatability, A0 re-inference, external weights, and pod state; memo:13-16.
CORRECTION DIFF 1: -case,a0_predictions,a8_predictions,render; +case,n_predictions,distance_720p,a0_predictions,a8_predictions,render; populate restored values from paired_frame_scores.csv.
CORRECTION DIFF 2: +name the preregistration path and c27ad65d... seal; +restore exact frames/reference/dev-box hashes and expected-versus-actual readiness hashes in the memo.
CORRECTION DIFF 3: +regenerate sha256_manifest.txt for current renders and add pre_fix1c artifacts; no measurement changes.
UNCORRECTABLE: no documentation diff can repair B5 or the scored readiness identity after the one candidate allowance was spent.
2026-09-11 | tracking | G390 | 1,620 native unique reference keys; 549 unique held-out; A8 TP 90 / FP 169 / FN 212, C0 0.16393442622950818, Wilson95 lower 0.29211016505655896, ALL FP/N_absent 169/188 = 0.898936170212766; A0 TP 0 / FP 8 / FN 302; readiness identity and scratch-route requirements unmet | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: g390_render_archived.py:38-41 accepts an empty A0 archive, so a wrong empty input is indistinguishable from valid no-detection output.
NEW GAP: g390_render_archived.py:18-19 keeps the last duplicate rank without enforcing rank 0; the current A0 archive has one rank-0/rank-1 duplicate, though none of the 30 render keys is affected.
NEW GAP: linked-worktree Git metadata is outside the writable sandbox; targeted git add and lane_commit.py both failed on index.lock, so no commit object was created.
