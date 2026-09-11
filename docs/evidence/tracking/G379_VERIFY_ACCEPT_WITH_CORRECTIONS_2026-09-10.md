VERDICT: ACCEPT WITH CORRECTIONS
Scope: candidate 1911015f7 is 630 additions only: 600 JPEG sheets and 30 rater transcripts; no Python file, schema, status, or reader changed.
ACCEPTANCE PASS (PARTIAL result): independently measured 6 sections/5 games, 360 scheduled and 352 decoded frames, 0/360 VALID, 0/6 sections meeting all three bars, >=489 feet/section, and 0/264 negative accepts over 30 sections; G379_spec.md:38, g379_broadcast_geometry_2026-09-10.md:1.
PREMISE PASS: G362 1.6516 px vs 1.0; G365-B 1.1287/1.1165/0.7636 px and wide 469.3808; G371 0 accepts; G374 precision 0.962162/recall 0.967391; G352 combined bar 0/4; g379_broadcast_geometry_2026-09-10.md:4.
HEADLINE PASS: claimed vs reproduced VALID 0/360 vs 0/360; feet_inside 094-234 vs 094-234 per mille; charged forward median 15.5679-21.8386 vs 15.5679-21.8386 px; negatives 0/264 vs 0/264; g379_broadcast_geometry_2026-09-10.md:1.
SUPPLEMENT PASS: 30x40 transcript rows equal ratings.csv exactly; 600 unique valid 720x370 JPEGs equal rated_manifest.csv keys; agreement 584/600 and kappa 0.953911; g379_broadcast_geometry_2026-09-10.md:20.
B1 PASS - all 60 scheduled frames/section stay in VALID and charged-residual denominators, including 8 decode failures; g379_broadcast_geometry_2026-09-10.md:17.
B2 PASS - candidate is additions-only; legacy margin remains and top_two_margin is additive; g379_broadcast_geometry_2026-09-10.md:7.
B3 PASS - absent evidence remains NO_CANDIDATES/NO_LINES/NO_VALIDATION or decode failure and never passes; g379_broadcast_geometry_2026-09-10.md:18; test_g379_broadcast_geometry.py:74.
B4 PASS - this descriptive measurement has no claim lifecycle or caller; g379_broadcast_geometry_2026-09-10.md:35.
B5 PASS - candidate contains evidence only and no deployment-tree write is reported; g379_broadcast_geometry_2026-09-10.md:2.
B6 PASS - no path moved or retired and no import reference was orphaned; g379_broadcast_geometry_2026-09-10.md:24.
B7 PASS - 30/30 unique renders exactly reproduce the sealed status-stratified even-spacing selection; g379_broadcast_geometry_2026-09-10.md:22.
B8 PASS - 42,663 unique stroke keys, zero cross-side reuse; FIT and VALIDATION are disjoint; g379_broadcast_geometry_2026-09-10.md:8; test_g379_broadcast_geometry.py:42.
B9 PASS - 360 unique scheduled frames, 3,310 detected feet, 42,663 unique strokes, and 398 charged template points/frame are named non-recycled units; g379_broadcast_geometry_2026-09-10.md:17.
B10 PASS - frozen bars/constants match the spec and focused assertions; g379_broadcast_geometry_2026-09-10.md:24; test_g379_broadcast_geometry.py:28.
Q1 PASS - seal 860bf25f...d0ffa holds at g379_prereg_2026-09-10.md:230; sole-file commit 24c82831 predates the first measurement commit; g379_broadcast_geometry_2026-09-10.md:3.
Q2 PASS (not applicable) - G379 is a tracking measurement, not a charged S-register trial; G379_spec.md:1.
Q3 PASS - acceptance bars and frozen constants are unchanged; G379_spec.md:42; g379_broadcast_geometry_2026-09-10.md:24.
Q4 PASS (not applicable) - no predictive OOS comparison or meta-learner is claimed; g379_broadcast_geometry_2026-09-10.md:30.
Q5 PASS (not applicable) - the result is PARTIAL and descriptive, with no AHEAD claim; g379_broadcast_geometry_2026-09-10.md:1.
Q6 PASS - independent scan of the memo plus 30 candidate transcripts found zero prohibited lexical hits; the sole numeric coincidence is explicitly contextualized; g379_broadcast_geometry_2026-09-10.md:25.
Q7 PASS - each section has 60 scheduled frames and >=489 feet, negatives n=264 across 30 sections, and the six-section result is explicitly descriptive; g379_broadcast_geometry_2026-09-10.md:19.
Q8 PASS - the premise was remeasured first and remains true; g379_broadcast_geometry_2026-09-10.md:4.
LOC PASS: candidate touches no .py; full G379 Python files are 105-250 lines and its test is 139 lines, all <=300; g379_broadcast_geometry_2026-09-10.md:24.
NOT VERIFIED PASS: the final memo section is the six-item NOT VERIFIED list; g379_broadcast_geometry_2026-09-10.md:29.
TEST PASS: `python -m pytest tests/platformkit/test_g379_broadcast_geometry.py -q` -> 7 passed in 2.07s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 1.13s.
CORRECTION (minimal diff): g379_broadcast_geometry_2026-09-10.md:1 add `The 60-decoded-frame clause is unmet in 4 sections (352/360 decoded overall).`
CORRECTION (minimal diff): g379_broadcast_geometry_2026-09-10.md:5 replace `at 60 fps` with `at 29.97003-60.0 fps`; source_identity.csv:2 has the four-rate distribution.
2026-09-10 | tracking | G379 | 6 sections/5 games; 352/360 decoded; 0/360 VALID; feet_inside 094-234 per mille; charged forward median 15.5679-21.8386 px; 0/264 negatives accepted over 30 sections | PARTIAL (verified: codex-sol, contract A/B/Q)
NEW GAP: the focused test does not assert that the 600 sheets and 30 raw rater transcripts match rated_manifest.csv and ratings.csv; this verification measured that correspondence directly.
NEW GAP: master d0099ff3 lacks the G379 modules and test, so the required candidate test could only run in this candidate worktree before landing.
