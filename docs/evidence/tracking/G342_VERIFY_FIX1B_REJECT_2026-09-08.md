VERDICT: REJECT
Candidate: `86988e67bc5b276f19348913fcc0e230a881cb08`; full non-archive diff read and all 6,401 archive additions audited (`archive.csv:1-6401`).
PREMISE PASS: no multi-league registry is imported by calibration code; NBA-only/hard-coded geometry remains at `keypoint_calib.py:21-22`, `basketball_sampler.py:10-19`, `g196_homography_from_labelled_corners.py:26-29,104-110`, `court_detector.py:195-196`, and `config.py:252-270`.
ACCEPTANCE metric FAIL: templates, selector, CSVs, and hook exist, but matrices use n=20 decisions (`g342_court_templates_2026-09-08.md:28-39`) instead of n=200 frames (`G342_spec.md:64-71`); FIBA URL is unavailable (`fiba.json:2-3`).
ACCEPTANCE values FAIL: tests mirror rather than validate wrong values: FIBA restricted radius 1.25 vs cited 2024 Rule 2.5.7 1.30 (`fiba.json:5`; `test_g342_court_templates.py:24-26`); `basket_offset=4.0` is used as basket centre instead of 5.25 ft for NBA/WNBA/NCAA (`templates.py:46`; `nba.json:4`; `wnba.json:4`; `ncaa.json:4`).
ACCEPTANCE arm A FAIL: reproduced true share 0.000000 and wrong share 0.000000 for NBA/WNBA/FIBA/NCAA, claimed 0.0000/0.0000 (`g342_court_templates_2026-09-08.md:30-44`); required true share >=0.95 (`G342_spec.md:67-70`).
ACCEPTANCE tests/LOC PASS: isolated logic 7/7 and LOC 214/73/107 <=300 (`g342_synthetic_run.py:1-214`; `template_select.py:1-73`; `test_g342_court_templates.py:1-107`).
ACCEPTANCE scope/memo/evidence PASS: no `src/`, `data/`, flag, G334, or protected tracking-file diff; NOT VERIFIED exists (`g342_court_templates_2026-09-08.md:51-54`); all named local paths and hashes exist/match (`:20-22,47,60`).
B1 PASS: all 6,400 rows retained; no failing row exclusion (`g342_synthetic_run.py:147-149`; `archive.csv:2-6401`).
B2 PASS: CSV schemas retained, JSON fields only added, and reader census found `templates.py:47`, runner `:36`, package export `__init__.py:3-6`, and the sole importing test `test_g342_court_templates.py:10,73`.
B3 PASS: ambiguity returns UNKNOWN, not loss (`template_select.py:72-73`; `G342_spec.md:69`).
B4 PASS: no claim/reclaim path exists in this isolated selector (`template_select.py:50-73`).
B5 PASS: local-only run, no deployed-tree path (`g342_court_templates_2026-09-08.md:6`).
B6 PASS: removed private helper has no remaining reference; runner calls selector directly (`g342_synthetic_run.py:155-160`).
B7 PASS: archive covers frame ids 0..199 for every arm/true/scored combination (`archive.csv:2-6401`).
B8 FAIL: wrong H is selected by cost on `observed` then scored again on the same `observed` (`g342_synthetic_run.py:97-104,127,131`), so the refit residual is not independent (`VERIFIER_CONTRACT.md:27`).
B9 PASS: 20 groups are non-overlapping and consume all 200 renders once (`g342_prereg_fix1b_2026-09-08.md:23-37`).
B10 PASS: selector gates remain 5 frames/2 shots, 0.8 ratio, 2 groups, 90/100 bootstraps (`template_select.py:52,65-73`; `G342_spec.md:36-40`).
Q1 PASS: seals independently match; original `prereg.md:17` predates 092d1accc and amendment `g342_prereg_fix1b_2026-09-08.md:60` predates 86988e67b.
Q2 PASS: no charged-trial ledger applies; this is a sealed synthetic geometry run (`g342_prereg_fix1b_2026-09-08.md:1-7`).
Q3 FAIL: amendment evaluates the bar on n=20 decisions (`g342_prereg_fix1b_2026-09-08.md:29-37`) while spec requires n=200 frames (`G342_spec.md:67-71`).
Q4 PASS: no OOS forecast or meta-learner is scored (`g342_synthetic_run.py:1-25`).
Q5 PASS: no AHEAD claim is made (`g342_court_templates_2026-09-08.md:1,44`).
Q6 PASS: candidate prose, labels, and added ledger text use calibration-only language (`RESULTS_LEDGER.md:592`).
Q7 FAIL: the scored confusion unit is n=20, below 30 (`g342_court_templates_2026-09-08.md:30-39`; `VERIFIER_CONTRACT.md:45-48`).
Q8 PASS: premise independently re-measured over the specified trees (`g342_court_templates_2026-09-08.md:9-18`).
REPRO PASS: archive 6,400 rows/6,400 unique keys; arm counts 3,200 each; 800/800 generating H unique; no nonfinite or negative costs (`archive.csv:1-6401`).
REPRO PASS: archived median ratios imply 20 UNKNOWN per template/arm (minimum 0.867060 >0.8); pairwise arm a=0.010000/0.015000/0.010000 and arm b=0.010000/0.010000/0.005000, exactly claimed (`separation.csv:2-7`).
TEST INFO: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_g342_court_templates.py -q -p no:cacheprovider` -> 0 passed, 7 setup errors from sandbox temp ACL.
TEST PASS: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_g342_court_templates.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 7 passed in 15.91s.
TEST PASS: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -B -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 1 passed in 0.60s.
TEST INFO: same G342 command in master `a7bd93728` -> 0 tests; candidate path absent. Importer census found no second test file.
CORRECTION: restore the specified n=200 frame metric; do not substitute n=20 decisions. If the selector gate requires pooled frames, specify a new compliant decision population before scoring, with n>=30.
CORRECTION: set FIBA `restricted_radius` 1.25 -> 1.30 and use the official 2024 rules PDF; set NBA/WNBA/NCAA `basket_offset` 4.0 -> 5.25; update cited-value tests, then rerun both arms.
CORRECTION: NCAA sideline offset must be `width/2 - corner_distance`, not a baseline-point Pythagorean solve (`ncaa.json:4-5`); using the spec-stated 21 ft 7.375 in gives 3.385416667 ft.
RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G342 | arm A archive reproduces 0/20 true and 0/20 wrong for all four templates; required n=200-frame bar not evaluated; B8/Q3/Q7 fail | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: premise table omits NBA `court_transform.py:8,71,197`, NBA `g233_basketball_seeded_court_coordinates.py:17-21`, and high-school `g253_line_conic_calibration.py:115-120` hard-coded geometry.
NEW GAP: `archive.csv` omits observed polylines and decision-level group/bootstrap values, so stored costs cannot be recomputed from archived inputs alone.
NEW GAP: memo `g342_court_templates_2026-09-08.md:52` calls synthetic inputs real frames, contradicting its own limitation at line 54.
