VERDICT: REJECT
Candidate: b4cf9be71c877906745c902e01084de06cc351ac (full diff reviewed: memo plus additive ledger row).
ACCEPTANCE FAIL: spec:39 requires before 1.6516/1.33/1.78/1.89 px; memo:7,60 measures 1.6516/469.2083/2.0160/1.8003 on one required and three replacement quads.
PREMISE REMEASURE: direct archived-path run = 1.651641/469.208252/2.015967/1.800281 px vs memo 1.6516/469.2083/2.0160/1.8003; only the first is the spec premise.
HEADLINES PASS: direct B rerun = 1.1287/469.3808/1.1165/0.7636 px; recovery_b.csv:2-5 claims the same.
HEADLINES PASS: sweep_b.csv recompute at sigma 0.5 = baseline 0.517861, B 0.433783, n=160, worst geometry 0.4495155; exact baseline/B = 0/0 at n=160; memo:24-28 agrees.
BAR RECOMPUTE: all-four <=1.0 FALSE; sigma-0.5 TRUE; exact TRUE; no-worsening FALSE because G2 changes 469.2083 -> 469.3808; memo:33 agrees.
B1 FAIL: summary_b.json:184,187 still computes bars after excluding G2, the row that fails both all-four clauses.
B2 PASS: RESULTS_LEDGER.md:698 is additive; no schema field, status value, or reader behavior was renamed or removed.
B3 PASS: insufficient-support paths return unchanged status at g365_refine_b.py:116-118; no absent-evidence gate was added.
B4 PASS: candidate touches evidence text only; no claiming path exists in RESULTS_LEDGER.md:698.
B5 PASS: memo:4,59 records scratch-worktree measurement and no deployed-tree write.
B6 PASS: memo:59 records zero deletions; candidate has no move, retirement, import, or -m change.
B7 PASS: all 8 renders were inspected across the complete four-geometry set; prereg:192 defines that exhaustive set.
B8 PASS: held-out supports remain separate and are exercised at test_g365_fitter_refinement.py:74-90.
B9 PASS: recovery uses the fixed TEMPLATE_POINTS denominator at g365_sweep.py:75.
B10 FAIL: spec:40-41 requires all four/no worsening, but summary_b.json:184,187 and g365_sweep_b.py:211-217 retain the later exclusion.
Q1 PASS: both seals independently hold at base-prereg:248 and amendment-prereg:120; git chronology places each before its scored attempt.
Q2 PASS (N/A): this synthetic geometry row has no charged trial or launch K; memo:59 limits its scope.
Q3 FAIL: the committed summary artifact retains exclusion-based bar fields contrary to spec:40-41 and memo:33.
Q4 PASS (N/A): no OOS model score or meta-learner is claimed; memo:59 is synthetic geometry only.
Q5 PASS (N/A): no AHEAD verdict or second-corpus claim appears; memo:1,59.
Q6 PASS: candidate memo scan reports 0 controlled-vocabulary hits; the added ledger line at RESULTS_LEDGER.md:698 is clean.
Q7 PASS: g365_sweep_b.py:38,167 enumerates 40 draws per geometry/sigma; sweep_b.csv has 640 unique rows and exact is exhaustive.
Q8 FAIL: memo:60 admits three required G362 premise geometries were never archived and were not remeasured.
EVIDENCE PASS: every memo path exists; all 17 listed attempt-2 digests match, including corrected G2 render digests at memo:50.
LOC PASS: candidate touches 0 .py; row Python files are 164-300 lines, with g365_sweep.py exactly 300.
NOT VERIFIED PASS: memo:58-60 names synthetic-only scope, missing G362 quads, real-footage limits, and conditional hand-off.
TEST PASS: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g365_fitter_refinement.py -q -p no:cacheprovider` -> 11 passed in 1.58s.
TEST PASS: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g365_candidate_b.py -q -p no:cacheprovider` -> 16 passed in 1.44s.
IMPORT TEST SCAN PASS: the two G365 importer tests are the two commands above; candidate b4cf9be71 touches no module.
CORRECTION minimal diff: g365_sweep_b.py:211-217 must evaluate `names`, rename fields to `b_within_bar_all_four`/`no_geometry_worsens`, and regenerate summary_b.json with FALSE/FALSE.
CORRECTION minimal diff: update memo:48 summary digest after regeneration; the required three G362 quads/known_h artifact must be supplied and rerun, not replaced.
2026-09-09 | tracking | G365 | premise 1/4 spec geometries reproducible; B 1.1287/469.3808/1.1165/0.7636 px; all-four and no-worsening bars fail; committed summary still scores an exclusion | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: local numpy/scipy/cv2 2.2.6/1.15.1/4.11.0 reproduced distances but G4 n_fev=16 versus archived 17 from 2.1.2/1.18.1/4.14.0; iteration-count portability is untested.
NEW GAP: repository-wide controlled-vocabulary scan reports 42 pre-existing hits outside candidate-added G365 content; candidate-added content reports 0.
