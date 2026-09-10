VERDICT: REJECT
Candidate: b0420bc76a241d3554279d46490d8b2e7e56b831; verification date 2026-09-10.
ACCEPTANCE PASS - premise: full rebuild reproduced 1,391 named, 1,378 off-pod, 13 missing; memo:6-16.
ACCEPTANCE PASS - snapshot: claimed/reproduced 177,007,159 bytes and 1,377/1,378 applicable checks; memo:13-18.
ACCEPTANCE PASS - decisions: claimed/reproduced G363 9/9, G364 12/12, G367 8/10, G370 7/7; memo:19-26.
ACCEPTANCE PASS - missing/rails: all 13 name required_by and disables; zero replenishment/deletions; missing.csv:2, summary.json:96-102.
ACCEPTANCE FAIL - eye: measured 6 JPEGs plus 2 SVG text strips, not 8 native-pixel files; g377_manifest.py:149, g377_restore.py:184, eye_manifest.csv:8-9.
B1 PASS - the named denominator includes restored and missing entries; g377_restore_receipt_2026-09-10.md:12-16.
B2 PASS - only new schemas/modules plus an appended ledger row; no field/status removal or reader change; g377_manifest.py:33.
B3 PASS - absent entries remain named and do not become adverse evidence; missing.csv:2-14.
B4 PASS - no claim workflow or failure-path ownership changed; g377_restore_receipt_2026-09-10.md:38.
B5 PASS - pod implementation is read-only hashing; g377_restore.py:107-115.
B6 PASS - candidate has no moved or retired module; g377_restore.py:20.
B7 PASS - all eight committed selections reproduce index 0 plus midpoint; g377_restore.py:167-173.
B8 PASS - archived-data recomputes are not presented as independent fits; g377_restore_receipt_2026-09-10.md:50-55.
B9 PASS - all 1,391 file-status entries form the denominator; g377_restore_receipt_2026-09-10.md:12.
B10 PASS - no bar or threshold changed; summary.json:94-102.
Q1 PASS - seal 627133fc... verifies and its sole-file commit c35db2ae0 predates metrics; g377_prereg_2026-09-10.md:11-13,251.
Q2 PASS - not invoked: this restore receipt has no charged trial; g377_restore_receipt_2026-09-10.md:3.
Q3 PASS - sealed bars and stop rule are unchanged; g377_prereg_2026-09-10.md:199-214.
Q4 PASS - not invoked: no new OOS comparison is claimed; g377_restore_receipt_2026-09-10.md:55.
Q5 PASS - not invoked: no AHEAD result is claimed; g377_restore_receipt_2026-09-10.md:55.
Q6 PASS - full candidate-text scan found no non-opaque vocabulary hit; test_g377_restore_receipt.py:85-99.
Q7 PASS - all four construct closures were rebuilt exhaustively; G377_spec.md:42.
Q8 PASS - off-pod premise remeasured first; current bytes were 177,023,914 because the disclosed ledger grew 16,755 bytes; memo:6-18.
TEST PASS - `python -m pytest tests/platformkit/test_g377_restore_receipt.py -q` - 7 passed.
TEST PASS - `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` - 1 passed.
LOC PASS - g377_manifest.py 247; g377_restore.py 299; g377_recompute.py 208; test 99; memo 56 lines.
ADDITIVITY PASS - 20 added paths, one append-only ledger modification, zero rename/removal; candidate diff.
MEMO PASS - NOT VERIFIED list exists at g377_restore_receipt_2026-09-10.md:50-56.
CORRECTION: g377_manifest.py:149 and g377_restore.py:184 remove `.svg`; test_g377_restore_receipt.py:82 assert `.jpg`/`.png`; supply two G370 raster sources and regenerate affected eye evidence.
CORRECTION: g377_restore_receipt_2026-09-10.md:28 change `Eight are POD_ABSOLUTE` to `Nine are POD_ABSOLUTE`.
2026-09-10 | tracking | G377 | PARTIAL receipt counts and decisions reproduced; required eye set is 6 JPEGs plus 2 SVG text strips | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: dependency_manifest.csv omits preregistered source/presence/digest columns; g377_manifest.py:33, g377_prereg_2026-09-10.md:93-95.
NEW GAP: required_by is truncated to six references despite the sealed all-reference rule; g377_manifest.py:204, g377_prereg_2026-09-10.md:82-85.
