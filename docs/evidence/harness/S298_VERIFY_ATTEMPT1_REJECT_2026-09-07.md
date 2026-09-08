VERDICT: REJECT
Candidate: 99d4e78c959aa294ad8bac11979acb4ed7434616.
PREMISE PASS: claimed 40520/53267 and 669/799; independently reproduced exactly from the two sources named at S298_rare_count_mixture_2026-09-04.md:25-32.
REPRODUCTION FAIL: the memo claims no scored headline, and no scored headline can be reproduced; only the premise is reproducible (S298_rare_count_mixture_2026-09-04.md:47-53).
ACCEPTANCE FAIL: all six fixed comparisons, adjusted lower bounds, secondary diagnostics, per-fold n rail, RSS, and replay archives are absent (S298_spec.md:15-29; S298_rare_count_mixture_2026-09-04.md:47-53).
DURABILITY FAIL: only the preregistration exists; the required PMF, paired-loss, and JSON artifacts do not (S298_rare_count_mixture_2026-09-04.md:52-53,79-80).
TEST PASS: focused test exercises all four PMF families and strict-prior timestamps (test_s298_rare_count_mixture.py:9-22).
IMPORT/ADDITIVITY PASS: sole Python importer is test_s298_rare_count_mixture.py:6; the new module renames/removes no existing field, status, or reader behavior.
LOC PASS: s298_rare_count_mixture.py=264 and test_s298_rare_count_mixture.py=22; repository LOC rail passed.
NOT VERIFIED PASS: candidate memo contains an explicit list (S298_rare_count_mixture_2026-09-04.md:74-82).
B1 PASS: all loaded rows are retained before outcome scoring (s298_rare_count_mixture.py:64-78,196-218).
B2 PASS: schema is additive and the sole reader/importer was checked (s298_rare_count_mixture.py:1; test_s298_rare_count_mixture.py:6).
B3 PASS: absent score evidence is reported absent, not treated as adverse evidence (S298_rare_count_mixture_2026-09-04.md:47-53).
B4 PASS: no claim/status loop is introduced; the memo stops at no scored result (S298_rare_count_mixture_2026-09-04.md:3-6).
B5 PASS: no pod process or deployed-tree write occurred (S298_rare_count_mixture_2026-09-04.md:59-64).
B6 PASS: no module was moved or retired; S298 adds a new route (s298_rare_count_mixture.py:1).
B7 PASS: no row or render sample is offered as evidence (S298_rare_count_mixture_2026-09-04.md:47-53).
B8 PASS: the unexecuted route predicts from outer-train states strictly before each test time (s298_rare_count_mixture.py:143-165).
B9 PASS: independently measured 78767 rows, 78767 unique player-games, 0 duplicates (s298_rare_count_mixture.py:75-77,81-93).
B10 PASS: the fixed six-comparison bar matches the spec (S298_rare_count_mixture_2026-09-04.md:41-45; S298_spec.md:17-20).
Q1 PASS: seal recomputed equal to stored 906ef129f74c860192046e1c60d21fffb2dd9c98a780efc766f2b30597be082b and prereg commit 287ae3aca predates candidate (S298_rare_count_mixture_2026-09-07_prereg.md:97).
Q2 PASS: no metric ran, so no charged metric was reported (S298_rare_count_mixture_2026-09-04.md:49-64).
Q3 PASS: the bar is unchanged (S298_rare_count_mixture_2026-09-07_prereg.md:67-73).
Q4 PASS: no OOS score is claimed; the route is wired to purged CPCV with a symmetric one-day embargo (s298_rare_count_mixture.py:244-245).
Q5 PASS: no AHEAD result is claimed for the single window (S298_rare_count_mixture_2026-09-07_prereg.md:73).
Q6 PASS: candidate prose and labels use calibration-only language (S298_rare_count_mixture_2026-09-04.md:35-45).
Q7 PASS: no SAMPLED or SCORED metric was emitted; the n rail therefore cannot be claimed or failed (S298_rare_count_mixture_2026-09-04.md:49-53).
Q8 PASS: the premise was measured first and independently reproduced (S298_rare_count_mixture_2026-09-04.md:19-37).
TEST: python -m pytest tests/platformkit/test_s298_rare_count_mixture.py -q -p no:cacheprovider -> 1 passed.
TEST: python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider -> 1 passed.
CORRECTION: s298_rare_count_mixture.py:247-258 must emit secondary summaries and per-fold cluster counts/assertions, then the sealed pod run must add PMF/loss/JSON and the full memo table.
CORRECTION: S298_rare_count_mixture_2026-09-04.md:14-17,81-82 must state that prereg commit 287ae3aca and candidate commit 99d4e78c9 now exist.
2026-09-07 | rare-count calibration | S298 | premise reproduced; comparison not run and score archive absent | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Candidate 99d4e78c9 also replaces unrelated prior contents of findings.md and task_plan.md; this is outside the S298 acceptance rule and did not affect the verdict.
