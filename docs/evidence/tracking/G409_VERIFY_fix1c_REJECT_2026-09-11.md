VERDICT: REJECT
Candidate: 21ea954845a439d972b79af313d5cf1bf1d513c4; acceptance plus B1-B10/Q1-Q8 only.
ACCEPTANCE input/export PASS: reproduced 60/60 unique ticks, 30/kind over 53 windows, 206 rows, 592 comparator boxes, 5 silences, 206/206 exact joins, and 60/60 retained source hashes (tick_accounting.csv:2; export_join.csv:2; source_receipts.csv:2).
ACCEPTANCE causal trace PASS AS PARTIAL: unfitted +60 transform covers 206 rows and identifies crop/export sites; the memo retains separate mismatches and avoids a universal correction (g409_box_coordinate_cause_2026-09-12.md:6-8).
ACCEPTANCE identity/reproduction PASS AS NOT VALIDATED: missing stage identities are explicit and two saved-output repeats match (g409_box_coordinate_cause_2026-09-12.md:20-25; repeats.json:528).
PREMISE PASS: direct G406 recount = 60 unique ticks, 30/kind, 53 windows, 206 rows, 592 boxes, 51 producer/comparator pairs, 5 silences; direct pair median dx=0.000, dy=-58.203 px (g406_masked_target_pixel_audit_2026-09-11/draw.csv:2; associations.csv:2).
HEADLINE PASS: claimed -58.2 to 1.8 px; reproduced -58.203 to 1.797 px, n=51; within 15 px 0/51 to 44/51; horizontal median 0.0 unchanged (residuals.csv:2; g409_box_coordinate_cause_2026-09-12.md:7).
EYE CHECK PASS: inspected all 60 cards, 30/kind, and all seven construct rows; every card has separate stored/mapped/comparator and labelled detector-input panels (renders/1080p30_00.jpg; renders/720p60_29.jpg; construct_cases.csv:2).
EVIDENCE PASS: all 17 spec-named entries and 60 renders exist; 209/209 checksums reproduce (SHA256SUMS:1).
LOC PASS: g409_fix1b.py 209; test_g409_box_coordinate_cause.py 225; both <=300 (g409_fix1b.py:1; test_g409_box_coordinate_cause.py:1).
ADDITIVITY FAIL: all seven accepted control_route values change from copied_statement to a longer replacement, and its test reader changes from exact vocabulary to any nonempty value (construct_cases.csv:2; g409_fix1b.py:125; test_g409_box_coordinate_cause.py:205).
MEMO PASS: explicit NOT VERIFIED list covers historical inference equality, court geometry, training suitability, and missing identities (g409_box_coordinate_cause_2026-09-12.md:20-25).
READER CHECK PASS: the named test is the only existing test importing g409_fix1b (test_g409_box_coordinate_cause.py:105).
TEST PASS: `python -m pytest tests/platformkit/test_g409_box_coordinate_cause.py -q` -> 19 passed in 1.33s.
B1 PASS: all rows, silences, 51 residuals, and 64 non-improvements remain (g409_box_coordinate_cause_2026-09-12.md:5-8).
B2 FAIL: control_route removes its established categorical value without an alias and the reader assertion is weakened (g409_fix1b.py:125; test_g409_box_coordinate_cause.py:205).
B3 PASS (not applicable): no absent-evidence gate is introduced (g409_box_coordinate_cause_2026-09-12.md:20-25).
B4 PASS (not applicable): no claim/retry state is introduced (g409_box_coordinate_cause_2026-09-12.md:28-33).
B5 PASS: receipts name isolated scratch paths; the correction is PC-only (launch_receipts.json:3; g409_box_coordinate_cause_2026-09-12.md:28).
B6 PASS: no module is moved or retired and the touched module import resolves in the test (test_g409_box_coordinate_cause.py:105).
B7 PASS: all 60 exact-even cards were inspected, not a head slice (card_panel_manifest.csv:2).
B8 PASS: TOPCUT=60 is code-derived before residual comparison and is unfitted (g409_box_coordinate_cause_2026-09-12.md:6-7).
B9 PASS: denominators are 60 unique ticks, 206 unique joined rows, and 51 frozen pairs (tick_accounting.csv:2; export_join.csv:2; residuals.csv:2).
B10 PASS: no acceptance threshold or gate value moves (prereg.md:29; G409_spec.md:21-23).
Q1 PASS: seal fa227df1c8aecd6f46fbc779f71c3f5bedb0f76bdf252317e95b76e87668d697 recomputes and predates measurement (prereg.md:36).
Q2 PASS (not applicable): this diagnostic is uncharged and reports no K (prereg.md:33).
Q3 PASS: bars remain byte-identical; unmet identity is NOT VALIDATED (prereg.md:29; G409_spec.md:23).
Q4 PASS (not applicable): no OOS score or learner is introduced (G409_spec.md:21-23).
Q5 PASS (not applicable): no AHEAD result is asserted (g409_box_coordinate_cause_2026-09-12.md:1).
Q6 PASS: independent character-code scan of nine language-bearing touched paths and the appended shared-log line found zero hits (q6_scan.json:1; RESULTS_LEDGER.md:781).
Q7 PASS: sampled n=60 and all seven construct cases are retained (draw.csv:2; construct_cases.csv:2).
Q8 PASS: the accepted G406 premise was remeasured from its full tables before trace adjudication (g409_box_coordinate_cause_2026-09-12.md:4-7).
CORRECTION: in g409_fix1b.py:121-125 keep control_route="copied_statement", put detailed status in new control_route_v2, and restore the exact-vocabulary assertion at test_g409_box_coordinate_cause.py:205; rebuild only owned receipts.
RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G409 | 60 ticks and 206 rows bind; vertical median -58.203 to 1.797 px (n=51), identity incomplete; control_route value replaced without alias | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: g409_fix1b.py:102-108 caches one import attempt, while g409_box_coordinate_cause_2026-09-12.md:32 states seven attempts.
NEW GAP: g409_fix1b.py:105 targets a Kalman initializer rather than the crop/export boundary; current controls execute the copied statement on 0/7 archived-function routes (construct_cases.csv:2).
