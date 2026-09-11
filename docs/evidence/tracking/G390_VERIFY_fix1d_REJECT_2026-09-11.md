VERDICT: REJECT
Candidate: a74d8b857f8921dbe1f43d368a0639716867aa9a; 5-file full diff and stat inspected.
PREMISE PASS: remeasured 1,620/1,620 unique native rows, 549 held-out (302 VISIBLE/188 ABSENT/59 UNKNOWN), 530 unique dev boxes/27 games, 0 held-out box overlap, historical A8 executions 0; readiness.json:2-23.
HEADLINE PASS: claimed/reproduced A8 TP/FP/FN 90/169/212, C0 0.16393442622950818, Wilson95 lower 0.2921101650565589 (claim 0.29211016505655896), ALL FP/188 0.898936170212766, ABSENT-only 50/188 0.26595744680851063; A0 0/8/302; memo:9, summary.json:23-47.
ACCEPTANCE-1 FAIL: sealed readiness fe8bcbe... differs from actual d11a1c8c..., so source identity moved despite the numeric premise passing; preregistration.md:21, memo:6.
ACCEPTANCE-2 PASS: 549 unique rows per arm, all three fixed bars missed, and the memo reports NOT VALIDATED with no follow-up tuning; summary.json:23-47, memo:1-9.
ACCEPTANCE-3 FAIL: score bytes, checkpoint hash/decode, manifests and 30 render keys reproduce, but compute used the wrong scratch route and the renderer cannot reproduce the additive index schema; weights_manifest.json:8-14, g390_render_archived.py:71-74.
REPRODUCTION PASS: 1,098 score rows, 81 manifest entries and 36 memo hashes independently checked with 0 missing/0 mismatches; paired_frame_scores.csv:1, sha256_manifest.txt:1-81.
TEST PASS: C:\Users\neelj\anaconda3\python.exe -B -m pytest tests\platformkit\test_g390_ball_a8_sealed_pass.py -q --basetemp=.pytest_tmp_g390_a74_verify -> 6 passed in 1.40s.
TEST SCOPE PASS: the candidate touches no non-test Python module; the sole applicable spec/importer test is the file above; test_g390_ball_a8_sealed_pass.py:14-15.
LOC PASS: sole touched .py is tests/platformkit/test_g390_ball_a8_sealed_pass.py:71 = 71, <=300.
B1 PASS: each arm retains all 549 unique held-out rows, including 188 ABSENT and 59 UNKNOWN; paired_frame_scores.csv:2-1099.
B2 FAIL: current index retains all 7 parent fields plus 2 restored fields, but its generator still omits n_predictions/distance_720p, so regeneration removes them; renders_index.csv:1, g390_render_archived.py:71-74.
B3 PASS: missing archived inputs are refused before rendering; test_g390_ball_a8_sealed_pass.py:68-71.
B4 PASS: one charged execution is latched at SCORING_STARTED and the second-pass refusal test passes; candidate_token.json:2-9, test_g390_ball_a8_sealed_pass.py:45-52.
B5 FAIL: compute ran under /workspace/g390_scratch, outside the permitted /workspace/wt/a11 scratch route; g390_a8_run.py:16, weights_manifest.json:8.
B6 PASS: no module was moved or retired and the renderer has a live full-package import; test_g390_ball_a8_sealed_pass.py:14.
B7 PASS: 30/30 unique keys exactly match the deterministic even selection over 549 and include 12 no-detection cases; g390_render_archived.py:50, renders_index.csv:2-31.
B8 PASS: development training excludes held-out keys and scoring uses the separately settled reference; train_report.json:7, summary.json:56-59.
B9 PASS: denominators are 549 unique held-out frames and 188 ABSENT frames, not recycled units; summary.json:43-47.
B10 PASS: bars remain 0.25/0.90/0.01 byte-identical to the spec; preregistration.md:44, summary.json:26-28.
Q1 PASS: memo names the preregistration, embedded seal and sealing commit; seal recomputes and commit 9196b6de8 predates scoring; memo:5, preregistration.md:49.
Q2 PASS: token charge precedes inference and the latched K is 1 before scoring; g390_a8_run.py:232-238, candidate_token.json:2-9.
Q3 PASS: all three immutable bars are unchanged; preregistration.md:44, summary.json:26-28.
Q4 PASS: 3,843 unique records per arm across 28 CPCV splits have equal keys, causal timestamps and exact archived mean losses; g390_score.py:99-100, summary.json:49-54.
Q5 PASS: no AHEAD claim is made; the measured disposition is NOT VALIDATED; memo:1-9.
Q6 PASS: fresh scan of 31 text artifacts found 0 non-opaque reserved-language hits; q6_scan.json:2-18.
Q7 PASS: scored n=549 and the even visual sample has n=30; summary.json:47, renders_index.csv:2-31.
Q8 PASS: premise was independently remeasured before verdict; readiness.json:2-23.
NOT VERIFIED PASS: memo explicitly lists repeatability, A0 re-inference, external weights and pod state; memo:17-20.
CORRECTION DIFF: g390_render_archived.py:71 add n_predictions=row["n_predictions"] and distance_720p=row["distance_720p"] before a0_predictions; assert the generated header, then refresh its memo hash.
UNCORRECTABLE: no documentation-only diff can repair the scored readiness identity or B5 route after the single candidate allowance was spent.
2026-09-11 | tracking | G390 | 1,620 native unique reference keys; 549 unique held-out; A8 TP 90 / FP 169 / FN 212, C0 0.16393442622950818, Wilson95 lower 0.2921101650565589, ALL FP/N_absent 169/188 = 0.898936170212766; readiness identity and scratch route unmet | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: master@60b6225e has no G390 test or module paths, so contract A1 cannot run before landing; the candidate-snapshot test is the only runnable G390 test.
NEW GAP: linked-worktree Git metadata is outside the writable sandbox; targeted git, lane_commit.py and object-store writes all failed, so no commit object was created.
