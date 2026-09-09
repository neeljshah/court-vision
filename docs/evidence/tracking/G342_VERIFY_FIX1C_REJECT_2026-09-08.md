VERDICT: REJECT
Candidate: `7475d564ab6d9803d567da4c78c9740efd64de75`; full 7-file diff audited, including all CSV rows.
PREMISE PASS: no calibration import of the new registry; hard-coded geometry remains at `keypoint_calib.py:21-22`, `basketball_sampler.py:13-18`, `g196_homography_from_labelled_corners.py:26-29,104`, `court_detector.py:195-196`, `config.py:256-270`, `court_transform.py:7-8,71,197`, `g233_basketball_seeded_court_coordinates.py:17`, and `g253_line_conic_calibration.py:116`.
ACCEPTANCE metric PASS: four sourced templates/render, selector, both arm matrices, separations, and hook exist (`test_g342_court_templates.py:33-48`; `g342_court_templates_2026-09-08.md:28-42`).
ACCEPTANCE values PASS: all 13 numeric fields/template are asserted and official NBA/FIBA sources independently support their cited dimensions (`test_g342_court_templates.py:17-48`).
ACCEPTANCE bar FAIL: claimed and reproduced arm-A true/wrong shares are 0.000000/0.000000 for every template at n=200; true share requires >=0.950000 (`confusion.csv:2-5`; `G342_spec.md:64-71`).
ACCEPTANCE scope/LOC PASS: no `src/`, protected tracking file, flag, or registry change; LOC runner/selector/templates/test = 248/73/64/116 (`g342_synthetic_run.py:1-248`; `template_select.py:1-73`; `templates.py:1-64`; `test_g342_court_templates.py:1-116`).
ACCEPTANCE evidence/memo FAIL: all paths and hashes match and NOT VERIFIED exists, but line 1 is neither the specified PARTIAL status nor Q3's terminal status (`g342_court_templates_2026-09-08.md:1,42,52-55`).
A1 PASS: spec test rerun at candidate HEAD as directed (`test_g342_court_templates.py:1-116`).
A2 PASS: headline and separations independently recomputed from CSVs (`confusion.csv:2-9`; `separation.csv:2-7`).
A3 PASS: all 320 decisions and all 800 base renders audited, not a head slice (`decisions.csv:2-321`; `observed_polylines.csv:2-284937`).
A4 PASS: 320/320 decision keys, 6,400/6,400 archive keys, and 800 frame keys are unique (`decisions.csv:1-321`; `archive.csv:1-6401`).
A5 PASS: reader/import census found only the spec test for the relevant modules; no CSV reader exists (`test_g342_court_templates.py:10-11,74,99`).
A6 PASS: only this verification path is staged and committed (`G342_VERIFY_2026-09-08.md:1-40`).
A7 PASS: every memo-named path exists; 13 LF-normalized hashes and the hook hash match (`g342_court_templates_2026-09-08.md:42,54`).
B1 PASS: every generated frame is retained in the 200-frame rows (`g342_synthetic_run.py:148-159,165-176`; `confusion.csv:2-9`).
B2 PASS: archive/confusion/separation headers and keys equal the parent; two new CSV schemas are additive (`archive.csv:1`; `confusion.csv:1`; `separation.csv:1`; `decisions.csv:1`; `observed_polylines.csv:1`).
B3 PASS: ambiguity returns UNKNOWN and the mandated quadrilateral assertion remains (`template_select.py:52-53,72-73`).
B4 PASS: this isolated selector has no claim/reclaim path (`template_select.py:50-73`).
B5 PASS: measurement is local-only (`g342_court_templates_2026-09-08.md:4`).
B6 PASS: no module moved or retired; package exports resolve (`court_templates/__init__.py:3-6`).
B7 PASS: all frame ids 0..199 were audited for every arm/true/scored cell (`archive.csv:2-6401`).
B8 FAIL: wrong-template H is chosen on FIT at `g342_synthetic_run.py:101-108,126-132`, then the headline selector scores those same FIT markings at `:165-175`; held-out costs at `:136,171` do not determine the reported winner.
B9 PASS: 40 non-overlapping decisions each cover five distinct frames, exhausting n=200 (`g342_synthetic_run.py:148,165-175`).
B10 PASS: gates remain 5 frames/2 shots, 0.8 ratio, 2 groups, and 90/100 bootstraps (`template_select.py:52,65-73`; `G342_spec.md:36-40`).
Q1 PASS: all three seals match and commits `1556dce3a`, `6094dc2c9`, `0d9ec5b69` precede their scored commits (`g342_prereg_fix1c_2026-09-08.md:5-7,45`).
Q2 PASS: no charged-trial ledger applies to this synthetic geometry run (`g342_prereg_fix1c_2026-09-08.md:18-30`).
Q3 FAIL: bars are unchanged, but the failed bar is not reported with the required terminal status (`g342_court_templates_2026-09-08.md:1,35`; `VERIFIER_CONTRACT.md:36`).
Q4 PASS: no OOS forecast or meta-learner is scored (`g342_synthetic_run.py:1-20`).
Q5 PASS: no AHEAD claim is made (`g342_court_templates_2026-09-08.md:1,47-52`).
Q6 FAIL: candidate memo lines 52 and 55 contain prohibited market-outcome vocabulary (`VERIFIER_CONTRACT.md:39`).
Q7 PASS: 40 scored decisions/template/arm and 200 distinct frames each exceed the rail (`decisions.csv:2-321`; `VERIFIER_CONTRACT.md:45-48`).
Q8 PASS: premise re-measured across the specified calibration/template trees (`g342_court_templates_2026-09-08.md:6-13`).
REPRO PASS: 6,400 archive rows; held-out medians match decisions; ratios 0.903757..0.954434, mean 0.927824; separations a=0.015000/0.010000/0.000000, b=0.015000/0.000000/0.000000, exactly claimed (`archive.csv:2-6401`; `decisions.csv:2-321`; `separation.csv:2-7`).
TEST PASS: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_g342_court_templates.py -q -p no:cacheprovider --confcutdir=tests/platformkit --basetemp=.g342_codexsol_final_908a` -> 8 passed in 6.86s.
TEST PASS: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests/platformkit --basetemp=.g342_codexsol_final_908b` -> 1 passed in 0.52s.
CORRECTION: seal first, then change `g342_synthetic_run.py:167` to `segments: validation_by_frame[i]`; add `selection_cost_*` while retaining `fit_cost_*` aliases, rerun n=200, and regenerate all artifacts.
CORRECTION: set memo line 1 to the contract/spec-compatible status, delete memo line 55, and rewrite line 52 with calibration-only wording.
RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G342 | arm A true-win 0.000000 and wrong-winner 0.000000 for all four templates at n=200 each; B8/Q3/Q6 fail | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: six-decimal archived H values reproduce only 3,042/6,400 stored held-out costs within 1e-5 (max absolute discrepancy 0.049998); archive needs enough precision for exact recomputation.
