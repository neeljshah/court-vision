VERDICT: REJECT
Candidate: `48854d6740052466810685b0864aa72a96ac8155`; verification date 2026-09-08.
ACCEPTANCE PASS: census has 122 unique games matching all 122 tracked positive-row snapshot games, with zero missing/extra games, zero unusable rows, and required per-game/per-resolution diagnostics (`g325_offframe_boxes_census_2026-09-07.csv:1-123`; `track_daemon_ledger_snapshot.jsonl:1-147`).
PREMISE PASS: claimed/reproduced `wnba_06` 150/3606 at 1920/1020, `wnba_04` 160/6189 at 1280/660, and `0022500575_s7200` 12/2620 at 640/300 (`g325_offframe_boxes_attempt2_2026-09-07.md:6-7`; census:55,93,123).
REPRODUCTION PASS: claimed/reproduced 23408/480158 wholly outside, 113/122 games at least 1/100, median 4.2141539213e-02, 23408/23408 coasting, and 0/269174 matched (`g325_offframe_boxes_attempt2_2026-09-07.md:1,9-19,36-42`).
DIAGNOSTICS PASS: claimed/reproduced 22666/480158 naive-height, 134998/480158 partial, 24952/480158 PAD-removed, zero height disagreements, all side totals, extremes, and all three resolution cells (`g325_offframe_boxes_attempt2_2026-09-07.md:9-19`; census:2-123).
ADDITIVITY FAIL: headers, keys, counts, statuses, and non-share cells are unchanged, but all 488 per-game and six resolution share cells changed from float-readable notation to fraction strings without alias columns (`g325_offframe_boxes.py:125-161,186-189`; census:1-123; by-resolution:1-4).
LOC PASS: touched Python files are 278 and 191 lines, both within 300 (`g325_offframe_boxes.py:278`; `test_g325_offframe_boxes.py:191`).
NOT VERIFIED PASS: memo names visual, downstream, width-source, daemon-config, repeatability, mutation, and population limits (`g325_offframe_boxes_attempt2_2026-09-07.md:46-50`).
B1 PASS: every row enters `rows_total`; unusable rows are counted, and measured `rows_bad` is zero (`g325_offframe_boxes.py:74-122`; census:2-123).
B2 FAIL: persisted share-field representation and the test reader expectation changed without backward-compatible aliases; repository search finds no other checked reader (`g325_offframe_boxes.py:125-161`; `test_g325_offframe_boxes.py:102-160`; contract:21).
B3 PASS (N/A): correction adds no absent-evidence gate or quarantine (`g325_offframe_boxes.py:125-161`; contract:22).
B4 PASS (N/A): correction adds no claim/retry path (`g325_offframe_boxes.py:125-161`; contract:23).
B5 PASS: candidate contains no deployed-tree change and records no deployment (`g325_offframe_boxes_attempt2_2026-09-07.md:61`; contract:24).
B6 PASS: no module moved or retired; the sole importer remains (`test_g325_offframe_boxes.py:23-27`; contract:25).
B7 PASS: evidence is the complete sorted construct, not a head slice; no render set exists (`g325_offframe_boxes.py:205-245`; census:2-123; contract:26).
B8 PASS (N/A): direct inequalities use no fitted points (`g325_offframe_boxes.py:94-109`; contract:27).
B9 PASS: denominators are each table's usable observations and vary across 122 unique games (`g325_offframe_boxes.py:118,164-190`; census:2-123; contract:28).
B10 PASS: 1/1000, 1/100, and 9/10 integer tests are unchanged from the parent and match the acceptance bar (`g325_offframe_boxes.py:193-202`; `G325_spec.md:104-109`; contract:29).
Q1 PASS: prereg-only commit `eceac0b89` predates metric commit `967e181d2`; the declared LF-normalized seal reproduces when the trailing pre-heading newline is excluded (`g325_prereg_attempt2_2026-09-07.md:229-230`; contract:34).
Q2 PASS (N/A): no charged trial or launch K exists (`g325_prereg_attempt2_2026-09-07.md:1-103`; contract:35).
Q3 PASS: candidate does not alter the fixed bars (`g325_offframe_boxes.py:193-202`; `G325_spec.md:104-109`; contract:36).
Q4 PASS (N/A): no OOS comparison or meta-learner is scored (`g325_offframe_boxes_attempt2_2026-09-07.md:9-42`; contract:37).
Q5 PASS (N/A): no AHEAD result is asserted (`g325_offframe_boxes_attempt2_2026-09-07.md:1-50`; contract:38).
Q6 FAIL: the implementation literally contains the standalone restricted sequence, and census line 94 repeats it inside a share fraction; memo line 49's claimed exclusion is not in Q6 (`g325_offframe_boxes.py:146`; census:94; contract:39-43).
Q7 PASS: complete construct is exhaustive: snapshot and census each contain the same 122 unique eligible game ids (`track_daemon_ledger_snapshot.jsonl:1-147`; census:2-123; contract:45-47).
Q8 PASS: the three-game premise recount precedes the pooled census and reproduces (`g325_offframe_boxes_attempt2_2026-09-07.md:6-9`; contract:49).
TEST: `python -B -m pytest tests/platformkit/test_g325_offframe_boxes.py -q --confcutdir=tests/platformkit -p no:cacheprovider` -> 10 passed in 0.12s.
TEST: `python -B -m pytest tests/platformkit/test_loc_rail_scope.py -q --confcutdir=tests/platformkit -p no:cacheprovider` -> 1 passed in 0.41s.
IMPORTER PASS: repository search finds only `tests/platformkit/test_g325_offframe_boxes.py`; covered above (`test_g325_offframe_boxes.py:23-27`).
CORRECTION DIFF: construct the standalone regex from separate digit tokens; keep every share field float-readable through checked notation; assert `_collides` is false for every share cell; regenerate CSVs and memo hashes; append a correction row.
RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G325 | 23408/480158 wholly outside; 113/122 games at or above 1/100; 23408/23408 coasting; 0/269174 matched; Q6 artifact scan fails | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: candidate memo is 61 physical lines although the evidence instruction caps it at 60 (`g325_offframe_boxes_attempt2_2026-09-07.md:61`).
NEW GAP: A7 reference `g323_nonplayer_boxes_attempt2_2026-09-07.md` is absent from candidate `48854d674`; the memo points to another revision (`g325_offframe_boxes_attempt2_2026-09-07.md:46-47`).
NEW GAP: A1 cannot run the candidate test on master because that path is absent there; candidate and LOC-rail commands were run in this worktree (`VERIFIER_CONTRACT.md:9`; `test_g325_offframe_boxes.py:1`).
NEW GAP: the 122 source tables are not retained in the candidate, so raw-row recount is not independently rerunnable; this verification recomputed from the committed census and snapshot (`g325_offframe_boxes_attempt2_2026-09-07.md:4`).
NEW GAP: proposed change remains under `docs/evidence/tracking/`, not the spec-named research path (`g325_offframe_boxes_attempt2_2026-09-07.md:43-44`).
