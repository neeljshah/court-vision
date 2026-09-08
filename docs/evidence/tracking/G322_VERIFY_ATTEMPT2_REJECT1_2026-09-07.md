VERDICT: REJECT
Candidate: `dba94d527`; verification date 2026-09-07; scope is the G322 acceptance rule plus B1-B10 and Q1-Q8.
ACCEPTANCE PASS: prereg and census enumerate the same 107 unique games; 412124/412124 rows usable, 0 excluded; `g322_prereg_attempt2_2026-09-07.md:102-210`, census:1-108.
PREMISE PASS: claimed/reproduced 1112/5580, 1086/4736, 0/1653; frame_h 1080/720/720 from table columns matching ledger fields; census:99,107,100.
HEADLINE PASS: claimed/reproduced 73/107 games and 80060/412124; secondary cuts 166410/412124 and 295559/412124; memo:1,10-18.
RESOLUTION PASS: claimed/reproduced 4127/34428 (7), 32094/178303 (45), 43839/199393 (55); by-resolution CSV:2-4.
PANELS PASS: 20 unique keys, five per sealed game, exact odd-decile ranks; labels 6/5/5/3/1 and sealed set 11/20; panels CSV:2-21, labels CSV:2-21.
TRACE PASS: detector call, TOPCUT, absent size gate, PAD, constant-height coast and footpoint fallback verified; trace:8-44, advanced_tracker.py:104-127,1225-1228,1332-1339,1409-1426.
NOT VERIFIED PASS: explicit list exists at `g322_oversized_boxes_attempt2_2026-09-07.md:40-43`.
ARTIFACT PASS: all nine named paths exist and independently match claimed byte sizes and SHA-256 values; memo:44-56; both sheets are below 500 KB and were visually checked.
B1 PASS: all 412124 rows are retained and no exclusion is hidden; census:1-108; script:60-105.
B2 PASS: no field/status is renamed or removed; the sole internal share reader was updated and no other test imports a touched module; script:28-37,148-169.
B3 PASS: no absent-evidence quarantine is introduced; script:199-270.
B4 PASS: no claim lifecycle or reclaim path is introduced; script:1-274.
B5 PASS: candidate changes only local code/evidence/test paths; no deployed-tree write is present; memo:59.
B6 PASS: no module is moved or retired; candidate diff and scripts:1-274, renderer:1-145.
B7 PASS: exact and rounded ordering reproduce the same three resolution medians plus corpus maximum; odd-decile rows span each set; script:148-194, panels CSV:2-21.
B8 PASS: descriptive row arithmetic has no fitted residual; script:60-105.
B9 PASS: denominators are each table's varying own row count; census:2-108; script:121-142.
B10 PASS: 0.50/0.33/0.25, 0.10 and 15/20 match the spec and seal; script:21-26; prereg:33-40,83-86.
Q1 PASS: seal recomputed as `60dea2d35090f443c550064742863e797b229abb30f51f6290275985a55bd92c`; prereg:1-5,212-213; prereg-only commit precedes candidate by 19 minutes.
Q2 PASS: this enumerated census is not a charged trial; memo:6-18.
Q3 PASS: all fixed bars match the spec and sealed prereg; prereg:33-40,83-86.
Q4 PASS: no OOS comparison or meta-learner claim is made; memo:40-43.
Q5 PASS: no AHEAD claim is made; memo:1,40-43.
Q6 FAIL: prohibited vocabulary is visibly present inside the inline self-check pattern; memo:58.
Q7 PASS: the 107-game construct is exhaustive and the 20 panels are an eye check reported as counts; memo:10-18,21-27.
Q8 PASS: premise was independently recomputed before the headline from census rows 99,107,100 and clears the fixed rule.
TEST PASS: `python -m pytest tests/platformkit/test_g322_oversized_boxes.py -q` -> 5 passed in 0.77s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 0.65s.
IMPORT/LOC PASS: only `tests/platformkit/test_g322_oversized_boxes.py` imports a touched module; renderer has none; touched Python LOC = 274/145/82.
CORRECTION: `g322_oversized_boxes_attempt2_2026-09-07.md:58` replace the inline pattern command with `four-token vocabulary scan`; no measurement rerun is required.
RESULTS_LEDGER_SYSTEM: 2026-09-07 | tracking | G322 | premise 1112/5580 and 1086/4736; census 80060/412124; Q6 text gate failed at memo:58 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the named local ledger snapshot is absent at verification time; prereg:9-16 and memo:4. Outside the requested rejection scope.
NEW GAP: prereg:69-70 requires no-offset rerenders on its trigger; memo:42 says all four games triggered and were not rerendered. Outside the acceptance rule.
NEW GAP: contract A1 cannot run because master `dce917b36` does not contain the candidate test; outside the requested rejection scope.
