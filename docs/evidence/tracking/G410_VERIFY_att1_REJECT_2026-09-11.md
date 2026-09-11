VERDICT: REJECT
Candidate: 92f5894fc; full stat/diff and all 198 changed paths reviewed.
ACCEPTANCE-1 PASS: premise, exact even 30/class draw, 241 selected rows, 238 predecessors, 60 native-frame checks, and parent labels retained (G410_spec.md:20; memo:4).
ACCEPTANCE-2 FAIL: 279 same-invocation checks exist, but branch/box mismatch inputs are passed as identical pairs, so all serialized mismatch classes are not independently exposed (g410_report.py:186; G410_spec.md:21).
ACCEPTANCE-3 FAIL: two reproductions match, but 8/39 launch receipts have blank pre-launch route digests and the aggregate is false; the rule requires NOT VALIDATED, not PARTIAL (launch_receipts.json:17; launch_receipts.json:395; G410_spec.md:22).
B1 FAIL: the 133/133 and 13/13 exact-match cohorts are defined by exact equality itself; they cannot support the claimed independent exact reproduction headline (g410_report.py:100; g410_report.py:102; memo:21).
B2 PASS: diff has zero deleted/renamed paths; new fields/statuses are additive, and the only importing test reader was checked (g410_report.py:158; test_g410_position_box_frame_consistency.py:150).
B3 PASS: absent positions/boxes and unevaluated ticks are serialized as unknowns and the memo remains PARTIAL (g410_report.py:132; g410_report.py:272; memo:1).
B4 PASS: no claim/retry mechanism is introduced (g410_measure.py:251).
B5 PASS: receipts describe scratch computation only; no deployed-tree write is present in the candidate (launch_receipts.json:10; VERIFIER_CONTRACT.md:140).
B6 PASS: zero moved/retired paths and no orphan import or module reference found (test_g410_position_box_frame_consistency.py:1).
B7 PASS: the class-specific exact-even selector spans each ordered population; all 60 selected ticks have native renders (g410_measure.py:137; test_g410_position_box_frame_consistency.py:71).
B8 PASS: matrix projection is direct reproduction, not a residual against fitted points; 9 construct cases are exhaustive (g410_report.py:194; test_g410_position_box_frame_consistency.py:178).
B9 PASS: reported units remain distinct: 60 unique class-ticks, 241 selected rows, 279 checks, 58 matrices, and 469 emitted rows (memo:8; memo:21; memo:36).
B10 PASS: candidate keeps the source jump threshold at 250 and the fixed 30/class sampling bar (g410_measure.py:20; prereg.md:58).
Q1 PASS: seal 497659f96001e23d148af3f3358839afd8051efd2f19d97fe52722d790a795d5 reproduces and predates measurement (prereg.md:74).
Q2 PASS: no charged comparison is performed (prereg.md:63).
Q3 PASS: fixed 30/class and binding-aware PARTIAL bars are unchanged (prereg.md:58).
Q4 PASS: no OOS comparison is scored (prereg.md:63).
Q5 PASS: no AHEAD result is claimed (memo:1).
Q6 PASS: candidate prose and proposed line use calibration-only language; the delivered scan records zero new-path hits (q6_scan.json:1).
Q7 PASS: sampled draw is 30/class; the 3 matrices x 3 boxes construct set is exhaustive (g410_report.py:197; test_g410_position_box_frame_consistency.py:178).
Q8 PASS: premise was independently remeasured before headline review (premise.json:1).
PREMISE reproduced vs claimed: 19,087 rows; CLAMP 9,354; SUBPIXEL 1,399; DETECTION 3,075; PREDICTION 5,259; blank route labels 0; receipts 60 (memo:4).
HEADLINES reproduced vs claimed: offset unclipped n=235 min/median/max 15.0/15.0/15.99 with 6 clipped; classification 146 consistent, 89 frame mismatch, 44 stale; staleness CLAMP 118/118 and SUBPIXEL 37/38; emitted differences 245/469 (memo:19; memo:31; memo:38).
REPRODUCTION PASS: repeats 2/2 identical, 175 delivered keys, 78 cards; all 225 manifest hashes and 39 source hashes/dimensions independently matched; evenly inspected cards j=0,15,29/class (repeats.json:181; memo:10).
TEST PASS: `python -m pytest tests/platformkit/test_g410_position_box_frame_consistency.py -q` -> 16 passed in 1.93s. Import survey found no other test file importing a touched module (test_g410_position_box_frame_consistency.py:19).
LOC PASS: touched Python files are 79-299 lines; maximum g410_finalize.py:299, all <=300. Memo NOT VERIFIED list PASS (memo:52).
ADDITIVITY PASS: no field, status, reader behavior, or path was removed/renamed; all candidate code/evidence additions remain opt-in (g410_finalize.py:292).
MINIMAL DIFF: memo:21 replace the cohort headline with `146/279 consistent, 89/279 frame mismatch, 44/279 stale; exact-match-named subgroups are descriptive, not independent validation`.
MINIMAL DIFF: memo:46 replace `All 39 ... route digest identical` with `31/39 nonblank route digests matched; 8/39 pre-launch digests are absent; aggregate false`.
MINIMAL DIFF: memo:1 replace `VERDICT: PARTIAL` with `VERDICT: REJECT -- independent mismatch classification and complete pre-launch identity are not established`.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking geometry | G410 | 19087-row premise reproduced; exact-match grouping circular and pre-launch identity incomplete (31/39 proven) | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: G410-1 prereg orders by draw_kind/section/frame while implementation orders sections by launch draw_order (prereg.md:36; g410_measure.py:257).
NEW GAP: G410-2 memo says the full delivered scan has zero hits, while its artifact records historical-ledger pattern index 3 count 24; distinguish new prose from permitted historical context (memo:47; q6_scan.json:4).
