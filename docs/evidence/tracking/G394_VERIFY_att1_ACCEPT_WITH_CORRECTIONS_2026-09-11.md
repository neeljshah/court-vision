VERDICT: ACCEPT WITH CORRECTIONS
Candidate: `87a497e9428de2090a17edd3979593f631c60157`; full seven-file stat and diff inspected.
ACCEPTANCE SUPPLY PASS - claimed/measured 386 eligible, 55 selected, 49 jointly accepted unique parents across 15 games, 6 exclusions retained, game/context overlap 0/0 (`G394_spec.md:22`; `audit_counts.json:2`; `split_assertions.json:13`).
ACCEPTANCE QUALITY PASS - claimed/reproduced A10 misses all fixed bars, so NOT VALIDATED is the specified disposition (`G394_spec.md:23`; memo:19,23).
ACCEPTANCE DISCIPLINE PASS - one training launch and one charged 549-key candidate pass; final weights were sealed before the inference charge (`G394_spec.md:24`; `launch_accounting.json:2-5,18-20`; memo:14).
PREMISE PASS - fresh full joins measured 530 boxes/27 games, 425 DEV ABSENT, 386 in those games, and held-out 302/188/59; all 1,620 reference keys join uniquely (`G394_spec.md:4`; memo:8).
HEADLINE PASS - claimed/reproduced A10 TP/FP/FN 84/156/218, C0 0.15300546448087432, Wilson95 lower 0.29244980923302405, ALL FP/188 0.8297872340425532; A8 90/169/212 and A0 0/8/302 also match (`paired_frame_scores.csv:1`; memo:19-21).
TEST PASS - `python -m pytest tests/platformkit/test_g394_ball_person_negatives.py -q` -> 10 passed in 2.35s.
IMPORTERS PASS - candidate touches no non-test Python module; the sole test importing G394 modules is the spec test above (`test_g394_ball_person_negatives.py:10-23,103`).
LOC PASS - sole touched Python file is 140 LOC <= 300; all nine G394 helpers are 28-246 LOC (`test_g394_ball_person_negatives.py:140`).
ADDITIVITY PASS - only documentation, a rater comment, scan receipts, and additive tests changed; no field, status, reader behavior, or module was renamed or removed (candidate name-status; `q6_redaction_manifest.csv:1-2`).
NOT VERIFIED PASS - the memo explicitly lists repeatability, causality, generalisation, archived baselines, selector accuracy, and operational adoption (`g394_ball_person_negatives_2026-09-11.md:34-40`).
EVIDENCE PASS - every specified repo artifact exists; 106/106 manifest entries reproduce under the documented LF transform, and the manifest self-digest reproduces (`sha256_manifest.txt:1-106`; memo:42-55).
B1 PASS - all 549 unique keys remain per arm, including 309 A10 no-detection states (`paired_frame_scores.csv:1`; memo:23).
B2 PASS - schema and reader behavior are additive; the focused reader survey is complete (`test_g394_ball_person_negatives.py:120-140`).
B3 PASS - missing inference remains in the fixed denominator rather than being quarantined (`test_g394_ball_person_negatives.py:81-86`; `heldout_states.csv:1`).
B4 PASS - spent training/inference states refuse restart and the row terminates (`test_g394_ball_person_negatives.py:89-99`; memo:1).
B5 PASS - compute used lane scratch only; no deployed tree was written (`checkpoint_receipt.json:23`; memo:14,40).
B6 PASS - no module moved or retired; full-package imports resolve in the passing test (`test_g394_ball_person_negatives.py:10-23,103`).
B7 PASS - exact even selection reproduced for 30/549 renders and 30/55 cards; endpoints are included and five exclusions appear in cards (`renders_index.csv:1-31`; `cards_index.csv:1-31`).
B8 PASS - training used DEV only and scoring used disjoint held-out games; the memo limits the result to one reused benchmark (`split_assertions.json:13-16`; memo:26,37).
B9 PASS - denominators are 549 unique keys, 302 VISIBLE, 188 ABSENT, 59 UNKNOWN; none is recycled or constant by construction (`summary.json:24-44`).
B10 PASS - bars remain C0 >= 0.25, Wilson95 lower >= 0.90, ALL FP/188 <= 0.01 (`G394_spec.md:23`; `test_g394_ball_person_negatives.py:94-99`).
Q1 PASS - seal `6fdfa08ab1ce9f95db51f3bbdc9e6eb789b7f4027d03ad15b8dde61dabde90d5` reproduces; seal-only commit `1e2b57d2f` precedes every rating and score commit (`preregistration.md:81`; memo:5).
Q2 PASS - no multiplicity K applies; local receipts charge training at 11:32:32Z and inference at 11:43:22Z before the 11:45:50Z score commit (`launch_accounting.json:4,19`; memo:13-16).
Q3 PASS - all three bars are byte-identical to the spec and the missed result is NOT VALIDATED, not lowered (`G394_spec.md:23`; memo:23).
Q4 PASS - 7,686/7,686 saved loss rows reproduce through CPCV with eight groups and one-day embargo; no meta-learner exists (`g390_score.py:99-101`; `g394_finish.py:83-88`).
Q5 PASS - no AHEAD or second-corpus claim is made (`g394_ball_person_negatives_2026-09-11.md:1,25-26`).
Q6 PASS - focused test independently scans the current 48-file text surface and returns 0 hits (`test_g394_ball_person_negatives.py:133-140`).
Q7 PASS - scored n=549 and both eye-check samples use n=30 with exact even unique selections (`G394_spec.md:22-24`; memo:29).
Q8 PASS - the premise was independently remeasured from all three source tables before verdict (`G394_spec.md:4`; memo:7-8).
CORRECTION MINIMAL DIFF memo:32: `- Q6 scan over all 44 text artifacts` / `+ Q6 scan over 47 then-existing text artifacts; verifier test covers 48 including q6_scan.json`.
2026-09-11 | tracking | G394 | premise 530/27, 425/386, held-out 302/188/59; A10 84/156/218, C0 0.15300546448087432, Wilson95 lower 0.29244980923302405, ALL FP/188 0.8297872340425532; all bars missed, result NOT VALIDATED; correct scan census 47 then-existing/48 current | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: master@7fdafd0e has no G394 test or module paths, so contract A1 cannot run there before landing; the candidate-snapshot test is the only runnable G394 test.
NEW GAP: 42 JPEG manifest entries identify LF-transformed byte streams rather than raw binary files; add raw-file SHA-256 receipts without changing this row's disposition.
NEW GAP: linked-worktree Git metadata is outside the writable root; targeted `git add` and the narrowed `lane_commit.py` helper both failed at `index.lock`, so an external path-specific committer must commit this sole memo.
