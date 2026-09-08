VERDICT: REJECT
Candidate: `995863242b6c80af08c97b3fcfa83ae3dd6c4934`.
ACCEPTANCE PASS: sealed sample, blind-order commits, 60/60 labels, gate reproduction, fixed bars, and mechanical row verdicts satisfy `docs/evidence/tracking/specs/G323_spec.md:109`; rejection is Q6-only.
PREMISE: claimed medians `wnba_06=0.0862`, `wnba_04=0.0643`, `0022500575_s7200=0.1878`; independently reproduced exactly from the 71-row G322 census (`g323_nonplayer_boxes_2026-09-07.md:14`).
HEADLINE: claimed A=30/60, B=32/60, agreement=41/60, po=0.6833, pe=0.1781, kappa=0.6147, SE=0.0731; reproduced 30/60, 32/60, 41/60, 0.6833333333, 0.1780555556, 0.6147347077, 0.0730633177 (`g323_nonplayer_boxes_2026-09-07.md:19`).
GATE: claimed 58 PASS/2 REJECT and 2/23=0.0870; reproduced 58/2 and 2/23=0.0869565217 with all gate CSV fields exact (`g323_nonplayer_boxes_2026-09-07.md:24`).
B1 PASS: all 12,415 source rows were eligible, 0 malformed, all 60 sampled, and gate denominator is 60 (`g323_nonplayer_boxes_2026-09-07.md:11`).
B2 PASS: only new files/fields plus one ledger append; no rename/removal, and the sole importing test was checked (`tests/platformkit/test_g323_nonplayer_boxes.py:13`).
B3 PASS: analysis-only reproduction has no absent-evidence quarantine path (`scripts/platformkit/tracking/g323_analyze.py:117`).
B4 PASS: no claim-state or reclaim path is introduced (`scripts/platformkit/tracking/g323_analyze.py:186`).
B5 PASS: no deployed-tree file is touched and the memo records no deployment (`g323_nonplayer_boxes_2026-09-07.md:53`).
B6 PASS: no module moved/retired; the new module has one test importer (`tests/platformkit/test_g323_nonplayer_boxes.py:13`).
B7 PASS: independent hash-lowest round-robin reconstruction matched 60/60 rows (`g323_prereg_2026-09-07.md:37`).
B8 PASS: this is a descriptive label census and gate reproduction, with no fitted residual (`g323_nonplayer_boxes_2026-09-07.md:24`).
B9 PASS: denominator has 60 unique panel ids and 60 unique game/frame/player rows (`g323_sample_2026-09-07.csv:2`).
B10 PASS: code bars 10 and 0.50 equal the sealed values (`scripts/platformkit/tracking/g323_analyze.py:34`).
Q1 PASS: seal `148d3861...021a` reproduces; prereg commit precedes sample, A-label, B-label, and metric commits (`g323_prereg_2026-09-07.md:121`).
Q2 PASS (not applicable): descriptive tracking census, no charged-trial K (`RESULTS_LEDGER.md:485`).
Q3 PASS: both fixed bars are byte-consistent with preregistration (`g323_prereg_2026-09-07.md:104`).
Q4 PASS (not applicable): no OOS scored comparison or meta-learner (`g323_nonplayer_boxes_2026-09-07.md:33`).
Q5 PASS (not applicable): no AHEAD result is claimed (`RESULTS_LEDGER.md:485`).
Q6 FAIL: prohibited Q6 vocabulary occurs in G323 prose at `g323_prereg_2026-09-07.md:7` and `g323_nonplayer_boxes_2026-09-07.md:36`.
Q7 PASS: sampled n=60 clears the rail; the construct test enumerates its cases (`tests/platformkit/test_g323_nonplayer_boxes.py:28`).
Q8 PASS: premise medians were independently recomputed and the absent court mask was source-checked (`g323_nonplayer_boxes_2026-09-07.md:7`).
MEMO PASS: explicit NOT VERIFIED list exists (`g323_nonplayer_boxes_2026-09-07.md:33`).
LOC PASS: `g323_analyze.py` 214 and `test_g323_nonplayer_boxes.py` 90, both <=300 (`scripts/platformkit/tracking/g323_analyze.py:1`).
ADDITIVITY PASS: no field/status/reader behavior removed; candidate changes are additions plus ledger line 485 (`RESULTS_LEDGER.md:485`).
ARTIFACTS PASS: 18 named hashes plus prereg seal match; four sheets are 330,964-356,236 B; memo is 54 lines (`g323_nonplayer_boxes_2026-09-07.md:38`).
EYE CHECK PASS: all four sheets show P01-P60 with context/crop and both box readings; six cells are 10 each (`g323_nonplayer_boxes_2026-09-07.md:14`).
TEST ENV: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g323_nonplayer_boxes.py -q` -> 6 setup errors, 0 test bodies (sandbox temp ACL).
TEST ENV: same command plus `--basetemp .pytest_cache\g323_verify_spec` -> 6 setup errors, 0 test bodies.
TEST ENV: same command plus `--basetemp g323_pytest_tmp_spec` -> 6 setup errors, 0 test bodies.
TEST ENV: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g323_nonplayer_boxes.py::test_tercile_and_region_assignment -vv --setup-show` -> 1 setup error, 0 test bodies.
TEST COLLECT: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g323_nonplayer_boxes.py --collect-only -q` -> 6 collected.
TEST PASS: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_g323_nonplayer_boxes.py -q --confcutdir=tests\platformkit` -> 6 passed.
TEST PASS: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_loc_rail_scope.py -q --confcutdir=tests\platformkit` -> 1 passed.
CORRECTION (required retry): delete prereg lines 6-7 and memo line 36, re-seal, then repeat sample/rating/gate sequence; Q1 disallows a post-measurement prereg repair.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-07 | tracking | G323 | medians reproduced; A 30/60, B 32/60; agreement 41/60, kappa 0.614735, SE 0.073063; gate rejects 2/23=0.086957 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: sampled observations can lie wholly outside the decoded frame; corpus share and producing site remain unmeasured (`g323_nonplayer_boxes_2026-09-07.md:35`).
NEW GAP: candidate memo places its verdict on line 2 rather than line 1 (`docs/evidence/tracking/specs/G323_spec.md:138`; `g323_nonplayer_boxes_2026-09-07.md:1`).
