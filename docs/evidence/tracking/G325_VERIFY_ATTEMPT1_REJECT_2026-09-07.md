VERDICT: REJECT
Candidate: `2009236d6b9cf34041a27b719fe18310c183252c`; verification date 2026-09-07.
ACCEPTANCE PASS: all 110 tracked games in the sealed manifest are present once; raw table hashes, sizes, row counts, resolutions, and heights match the census (`g325_offframe_boxes_2026-09-07.md:9-19`).
PREMISE PASS: raw recount `wnba_06` 150/3606, `wnba_04` 160/6189, `0022500575_s7200` 12/2620, matching claimed (`g325_offframe_boxes_2026-09-07.md:6-7`).
REPRODUCTION: claimed/reproduced pooled 20560/424895; 101/110 games at least 1/100; coasting 20560/20560; matched 0/238033 (`g325_offframe_boxes_2026-09-07.md:1,16-17,24`).
DIAGNOSTICS PASS: reproduced secondary 19918/424895, partial 122200/424895, PAD-removed 21972/424895, and resolution cells 1692/34428, 9033/191074, 9835/199393 (`g325_offframe_boxes_2026-09-07.md:13-19`).
B1 PASS: every row increments total; unusable rows and excluded games are named (`scripts/platformkit/tracking/g325_offframe_boxes.py:83-89,179-193`); raw recount found 0 unusable and 0 excluded.
B2 PASS: commit has no delete/rename; schema is new and additive (`scripts/platformkit/tracking/g325_offframe_boxes.py:26-43`); sole importer is `tests/platformkit/test_g325_offframe_boxes.py:11-15`.
B3 PASS (N/A): no gate or quarantine path is added; absent tables are explicitly reported (`scripts/platformkit/tracking/g325_offframe_boxes.py:179-187`).
B4 PASS (N/A): no claim/retry workflow is added (`scripts/platformkit/tracking/g325_offframe_boxes.py:170-243`).
B5 PASS: diff contains only docs, the additive script, and its test; memo records no deployment (`g325_offframe_boxes_2026-09-07.md:44`).
B6 PASS: no module was moved or retired; the new module has its test importer (`tests/platformkit/test_g325_offframe_boxes.py:11-15`).
B7 PASS: this is a complete sorted enumeration with no render sample (`scripts/platformkit/tracking/g325_offframe_boxes.py:178-180`; memo:9,31-32).
B8 PASS (N/A): direct geometric counts use no fitted points (`scripts/platformkit/tracking/g325_offframe_boxes.py:73-121`).
B9 PASS: denominator is each table's usable observations; 110 unique games and 110 unique table hashes reproduce (`scripts/platformkit/tracking/g325_offframe_boxes.py:117,129-155`).
B10 PASS: sealed 1/1000, 1/100, and 9/10 integer bars are unchanged (`scripts/platformkit/tracking/g325_offframe_boxes.py:158-167`).
Q1 PASS: prereg commit `d2241004c` contains only the prereg and predates scoring; seal `678742194723f1e3155391940c2dc54ae478a8b0e9917c25254741577c6d16b9` reproduces (`g325_prereg_2026-09-07.md:216-217`; memo:3).
Q2 PASS (N/A): this construct has no charged trial or K (`scripts/platformkit/tracking/g325_offframe_boxes.py:170-176`).
Q3 PASS: preregistered bars equal the spec and implementation (`scripts/platformkit/tracking/g325_offframe_boxes.py:158-167`).
Q4 PASS (N/A): no OOS comparison or meta-learner is present (`scripts/platformkit/tracking/g325_offframe_boxes.py:73-167`).
Q5 PASS (N/A): no AHEAD result is asserted (`g325_offframe_boxes_2026-09-07.md:1-32`).
Q6 FAIL: automated scan finds three prohibited-token hits at `g325_prereg_2026-09-07.md:87` and one at `g325_producer_trace_2026-09-07.md:46`; memo line 33 incorrectly reports zero. Q6 is an automatic reject.
Q7 PASS: sealed manifest and census each contain the same 110 games with zero missing, extra, or mismatched entries (`g325_prereg_2026-09-07.md:104-214`; script:50-59).
Q8 PASS: premise is reported before the corpus headline and reproduces from raw tables (`g325_offframe_boxes_2026-09-07.md:6-9`).
LOC PASS: touched Python files are 243 and 116 lines, both at most 300 (`g325_offframe_boxes.py:243`; `test_g325_offframe_boxes.py:116`).
NOT VERIFIED PASS: limitations list is present (`g325_offframe_boxes_2026-09-07.md:31-33`).
CLAIM CORRECTION: memo:17 claims median ~4.1597e-02; raw per-game shares reproduce median ~4.1248e-02.
TEST: `python -m pytest tests/platformkit/test_g325_offframe_boxes.py -q --confcutdir=tests/platformkit` -> 7 passed.
TEST: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q --confcutdir=tests/platformkit` -> 1 passed.
CORRECTION DIFF 1: new attempt: prereg:87 -> `Vocabulary follows contract Q6; automated scan required.`; reseal and commit alone before rerunning the raw census.
CORRECTION DIFF 2: producer trace:46 -> `(a local crop tensor for the`; memo:17 median -> `~4.1248e-02`; memo:33 must report the corrected scan.
2026-09-07 | tracking | G325 | raw recount 20560/424895 wholly outside; 20560/20560 coasting; 0/238033 matched; Q6 scan 4 hits and median corrected to 4.1248e-02 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: A7 reference `g323_nonplayer_boxes_attempt2_2026-09-07.md` at memo:7 is absent from candidate commit and the current tree.
NEW GAP: the proposal is at `docs/evidence/tracking/PROPOSED_g325_drop_wholly_offframe_2026-09-07.md` (memo:29), not the spec-named quarantine path; this is outside acceptance/B/Q and is not a rejection basis.
