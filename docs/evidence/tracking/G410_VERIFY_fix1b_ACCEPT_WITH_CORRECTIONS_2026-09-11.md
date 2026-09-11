VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 92f32f7b0; full 29-path stat/diff reviewed, including row-wise generated-artifact changes.
ACCEPTANCE-1 PASS: premise, 30 distinct exact-even ticks/class by spec draw_order/frame, 241 selected rows, 238 predecessors, and 60/60 sealed render coverage reproduced (G410_spec.md:20; g410_measure.py:146).
ACCEPTANCE-2 PASS: 279 same-invocation rows independently classify 2 consistent, 107 frame mismatch, 36 stale, 124 branch mismatch, 10 UNKNOWN; all rows retained (G410_spec.md:21; g410_report.py:122).
ACCEPTANCE-3 PASS: 2/2 table/card rebuilds match; 31/39 pre-launch identities are complete and the memo correctly closes NOT VALIDATED (G410_spec.md:22; memo:1).
B1 PASS: pre/post boxes are distinct inputs; missing pre-call boxes remain 10 UNKNOWN and no outcome rows are excluded (g410_report.py:122; g410_report.py:187).
B2 PASS: CSV/JSON schema comparison found zero removed fields; 11 contract-check fields and two identity fields are additive (contract_checks.csv:1; summary.json:8).
B3 PASS: missing bindings are retained as UNKNOWN or named failures and the row remains PARTIAL (g410_report.py:112; unknowns.csv:1).
B4 PASS: no claim or retry mechanism is added by the three touched helpers (g410_repeats.py:1).
B5 PASS: receipts describe observer computation and no deployed-tree write is introduced (launch_receipts.json:3).
B6 PASS: the candidate has zero deleted or renamed paths and no orphan module reference (test_g410_position_box_frame_consistency.py:1).
B7 PASS: exact-even selection spans both full ordered populations; render checks used j=0,15,29/class (g410_measure.py:146; eye_index.csv:1).
B8 PASS: projection is direct matrix arithmetic; the 3-matrix x 3-box CONSTRUCT set is exhaustive (g410_report.py:196; construct_cases.csv:1).
B9 PASS: denominators are distinct: 60 class-ticks, 241 selected rows, 279 checks, 469 emitted rows (summary.json:171; memo:34).
B10 PASS: fixed PAD 15, TOPCUT 60, jump 250, pipeline clamp 350, and 30/class sampling are unchanged (g410_measure.py:18; G410_spec.md:20).
Q1 PASS: prereg seal 497659f96001e23d148af3f3358839afd8051efd2f19d97fe52722d790a795d5 reproduces and predates measurement (prereg.md:74).
Q2 PASS: no charged comparison is performed (prereg.md:63).
Q3 PASS: the acceptance bars and thresholds are unchanged (G410_spec.md:20; G410_spec.md:22).
Q4 PASS: no OOS comparison or meta-learner is scored (prereg.md:63).
Q5 PASS: no comparative-ahead result is claimed; closure is PARTIAL + NOT VALIDATED (memo:1).
Q6 PASS: independent 29-path scan found only permitted historical-context pattern index 3 count 24 (q6_scan.json:1).
Q7 PASS: sampled n is 30/class and all 9 CONSTRUCT cases are present (draw.csv:1; construct_cases.csv:1).
Q8 PASS: whole-set premise was measured before replay and independently reproduced here (premise.json:1; memo:2).
PREMISE reproduced vs claimed: 19,087 rows; CLAMP 9,354; SUBPIXEL 1,399; DETECTION 3,075; PREDICTION 5,259; blank routes 0; 60 receipts (memo:3).
HEADLINES reproduced vs claimed: offset n=235 min/median/max 15.0/15.0/15.987 with 6 clipped; emitted differences 245/469; classification 2/107/36/124/10 of 279 (memo:19; memo:34).
REPRODUCTION PASS: 2 rounds, 177 compared keys, 78 cards, zero digest mismatches; all 39 retained sources rehashed with matching bytes/dimensions (repeats.json:179; source_receipts.csv:1).
RENDER PASS: sealed coverage 30/30 per class; six exact-even visual checks were legible and showed named frame parameters (eye_index.csv:1).
EVIDENCE PASS: every named path exists and root SHA256SUMS verifies with zero mismatches (SHA256SUMS:1).
TEST PASS: `python -m pytest tests/platformkit/test_g410_position_box_frame_consistency.py -q` -> 17 passed in 0.72s; import survey found no other test file (test_g410_position_box_frame_consistency.py:1).
LOC PASS: g410_finalize.py 299, g410_repeats.py 92, g410_report.py 296, test 205; all <=300 (g410_finalize.py:1).
ADDITIVITY PASS: old fields/statuses and reader behavior remain; the only importing test reader passed (g410_finalize.py:159; test_g410_position_box_frame_consistency.py:106).
NOT VERIFIED PASS: physical registration, cross-run identity, incomplete pre-launch identity, and defect attribution are listed (memo:54).
CORRECTION: memo:59 replace same-set claim with `lexical prereg overlap is 3/30 CLAMP and 2/30 SUBPIXEL; executed draw follows spec draw_order/frame`.
CORRECTION: test:85 replace self-set comparison with whole-parent recomputation of both orders and the measured 3/30, 2/30 overlap.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking geometry | G410 | PARTIAL + NOT VALIDATED: premise 19087 rows; 279 checks classify 2/107/36/124/10; pre-launch identity 31/39; draw-note correction required | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: G410-V1 consistency_by_class omits branch-mismatch and UNKNOWN columns, so displayed categories omit 134/279 rows though contract_checks retains them (consistency_by_class.csv:1).
NEW GAP: G410-V2 pre_fix1b/SHA256SUMS says verify from its directory but references uncopied sibling assets (pre_fix1b/SHA256SUMS:2).
NEW GAP: G410-V3 a pytest temporary trace is committed and absent from the delivered scan manifest; independent scan found zero pattern hits (.pytest_tmp_g410/test_parse_trace_reads_matrice0/t.trace.txt:1).
