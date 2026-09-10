VERDICT: REJECT
Candidate: 7d48c60024f524b323e6f5c12622715d9b40b5bb.
ACCEPTANCE PASS (LIMIT outcome): G363_spec.md:41; 881 unique frames, 63 sections, 60 games, 3 competitions, 2 primary raters plus 295 adjudications, 0 unadjudicated; held-out 285 VISIBLE / 243 ABSENT / 21 UNKNOWN.
REPRODUCED vs claimed PASS: g363_ball_coverage_2026-09-09.md:1; C0 0/549=0.000000; A7 2/549=0.003642987; Wilson lower 0.003052375; FP/N_absent 178/243=0.732510288; recall 0.007017544; abstention 0.672131148.
PAIRED PASS: frame_scores.csv:1; 32 games, mean 0.00390625, min 0, max 0.0625, 2 improved, matching memo:34.
PREMISE PASS: survival_fix1b.csv:1 independently gives any_ball_row 505/1860=271.505 per mille and detected_ball 358/1860=192.473 per mille versus claimed rounded 272 and 192; C0=0 triggers LIMIT at memo:14.
REFERENCE/EYE PASS: ratings.csv:1 gives kappa 0.640120432; eye_check_manifest.csv:1 has 30/30 unique exact even-selector rows, all 1920x1080, valid hashes; spread renders 00/14/29 inspected.
EVIDENCE/MEMO PASS: G363_spec.md:52 named paths exist; memo:55 is under NOT VERIFIED and the memo is 60 lines.
TEST PASS: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g363_ball_coverage.py -q -p no:cacheprovider` -> 10 passed in 0.84s.
TEST PASS: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed in 0.87s.
IMPORTER PASS: test_g363_ball_coverage.py:10 is the only existing test importing the touched module; it was run above.
LOC PASS: g363_ball_coverage.py:1=287 and test_g363_ball_coverage.py:1=122; both <=300.
B1 PASS: g363_score.py:132 scores every sealed frame with a resolved reference; measured 881/881 and no outcome exclusion.
B2 FAIL: predictions.csv:1 removes physical field `score` and renames it `score_e6`; g363_ball_coverage.py:149 reconstructs it only after the schema change, violating no-renames additivity.
B3 PASS: g363_score.py:134 has no new absent-evidence quarantine or fall-through change.
B4 PASS: g363_ball_coverage_2026-09-09.md:42 adds no retry or reclaim path.
B5 PASS: g363_ball_coverage_2026-09-09.md:42 records scratch compute and no deployed-tree write; candidate touches no deployed path.
B6 PASS: G363_ADJUDICATION_2026-09-10.md:1; candidate moves/removes no module, test, import, or -m target.
B7 PASS: g363_eyecheck.py:31 and eye_check_manifest.csv:2 implement and archive an even whole-set sample, not a head slice.
B8 PASS: frames.csv:1 has zero game overlap between development and held-out; winner selection and scoring use separate splits.
B9 PASS: g363_ball_coverage_2026-09-09.md:14 treats 3 x zero as undefined and reports LIMIT.
B10 PASS: G363_spec.md:45 and g363_score.py:24 preserve 3.0, 0.90, 0.01, 150/150, and 0.50; candidate changes none.
Q1 FAIL: g363_prereg_amendment_2026-09-09.md:32 has no embedded SHA-256 seal although lines 13-21 change the scored reference.
Q2 FAIL: RESULTS_LEDGER.md:691-692 contains only post-metric rows; ledger_snapshot.jsonl has no G363 pre-metric charge or launch K.
Q3 PASS: G363_spec.md:45 and summary.json:551 preserve every specified bar unchanged.
Q4 FAIL: g363_score.py:121 scores one held-out split without walk_forward or cpcv_evaluate, purging, or symmetric embargo.
Q5 PASS: g363_ball_coverage_2026-09-09.md:1 reports LIMIT, so the two-corpus condition is not invoked.
Q6 FAIL: memo:52 claims an empty full-evidence scan, but an independent scan found 65 non-exempt forbidden-token lines across 25 files, including ratings.csv:26 and ledger_snapshot.jsonl:240; sealed-file exemption is absent from Q6.
Q7 PASS: frames.csv:1 has 881 unique scored frames, above the sampled-score rail.
Q8 PASS: g363_ball_coverage_2026-09-09.md:11 remeasures C0 first on all 549 held-out references and closes at LIMIT.
CORRECTION DIFF 1: predictions.csv:1 `- ...,h,score_e6,...` -> `+ ...,h,score,score_e6,...`; populate both with numerically equivalent clean encodings and assert both fields in test_g363_ball_coverage.py:118.
CORRECTION DIFF 2: memo:45 `- a2b342577d80078515e1ee843b05513caa718251edd9c92855a6a53565db9b0c ratings.csv` -> `+ 2080aa6ca210bfd81e217f1bcd51c474cfba9bec34bdbf4b679b1c93f22060b8 ratings.csv`.
CORRECTION: no memo-only diff cures Q1/Q2/Q4; rerun after a newly sealed amendment, pre-metric charge with launch K, and the required OOS evaluation route; clean all Q6 hits without renaming fields.
2026-09-10 | tracking | G363 | C0 0/549; A7 2/549, Wilson lower 0.003052, FP/N_absent 0.732510; B2/Q1/Q2/Q4/Q6 failed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: g363_ball_coverage_2026-09-09.md:45 claims the wrong LF-normalized ratings.csv SHA-256; measured 2080aa6ca210bfd81e217f1bcd51c474cfba9bec34bdbf4b679b1c93f22060b8.
NEW GAP: VERIFIER_CONTRACT.md:9 master rerun was impossible without landing: master lacks both candidate 7d48c6002 and the spec test; the candidate worktree test result is reported above.
