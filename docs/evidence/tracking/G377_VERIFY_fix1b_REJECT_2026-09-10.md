VERDICT: REJECT
Candidate: e56c0467d2d930eca0df27a800e5eda5ead8502d; verification date 2026-09-10.
ACCEPTANCE FAIL - eye: reproduced 6 unique raster files across G363/G364/G367, not required 8 across all four closures; G377_spec.md:43, memo:29-30, eye_manifest.csv:2.
ACCEPTANCE FAIL - zero-deletion rail: candidate removes two G370 eye files and adds an unlink path while summary records zero; g377_restore.py:192-205, summary.json:94-101.
PREMISE PASS - exhaustive current recount is not 100 pct: 1,375/1,391 present off-pod, 169,242,156 bytes, 16 missing; claimed 1,378, 177,007,159, 13; memo:6-12.
HEADLINE PASS - cached artifacts reproduce 1,378 restored, 1,377 verified, 13 missing and 177,007,159 bytes; summary.json:104-122.
HEADLINE PASS - decisions reproduce claimed G363 9/9, G364 12/12, G367 8/10 plus 2/5 memo digests, G370 7/7; decision_diff.csv:2.
B1 PASS - 1,391 file-status rows are unique and missing rows remain in the denominator; memo:12, missing.csv:2-14.
B2 FAIL - 31 role values, two status values, SVG reader behavior and two files are removed without aliases; g377_manifest.py:139-153, g377_restore.py:153-162.
B3 PASS - absent files remain named with required_by and disables; missing.csv:2-14.
B4 PASS - no claim or retry workflow is changed; g377_restore.py:123-145.
B5 PASS - pod access remains read-only hashing and no deployment path is added; g377_restore.py:96-116.
B6 PASS - no module is moved or retired and the only importing test remains; test_g377_restore_receipt.py:9.
B7 PASS - retained selections use sorted index 0 and midpoint, not a head-only slice; g377_restore.py:145-162.
B8 PASS - archived recomputes are identity checks, not independent fits; memo:50-56.
B9 PASS - denominator is 1,391 unique named files across four exhaustive closures; memo:6-12.
B10 FAIL - sealed 8-file eye requirement is changed to 6 plus 2 limit slots; G377_spec.md:43, test_g377_restore_receipt.py:74-84.
Q1 PASS - seal 627133fc... verifies; sole-file commit c35db2ae0 predates measurements; g377_prereg_2026-09-10.md:198-205,251.
Q2 PASS - not invoked: no charged trial exists; memo:3.
Q3 FAIL - the eye bar changes after sealing; g377_prereg_2026-09-10.md:198-220, memo:29-30.
Q4 PASS - not invoked: no new OOS comparison is claimed; memo:55.
Q5 PASS - not invoked: no AHEAD result is claimed; memo:55.
Q6 PASS - added-line scan found only 81 opaque-digest bare-integer hits; test_g377_restore_receipt.py:86-101.
Q7 PASS - all four construct closures are enumerated; G377_spec.md:42, summary.json:2-79.
Q8 PASS - premise remains non-vacuous under the current 1,375/1,391 recount; memo:6-12.
TEST PASS - `python -m pytest tests/platformkit/test_g377_restore_receipt.py -q` - 7 passed in 0.82s.
TEST PASS - `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` - 1 passed in 0.71s.
LOC PASS - g377_manifest.py 272; g377_restore.py 296; touched test 101; memo 56; memo:37.
ADDITIVITY FAIL - two files deleted, 31 roles and two statuses changed, and SVG selection behavior removed; g377_manifest.py:150, g377_restore.py:161, test_g377_restore_receipt.py:74-84.
MEMO PASS - NOT VERIFIED list exists; memo:50-56.
CORRECTION: retain the two deleted SVG artifacts; remove g377_restore.py:192-205 and the `--eye-only` path at :219-224.
CORRECTION: add two byte-verified G370 raster sources and restore the sealed 8-file assertion at test_g377_restore_receipt.py:74-84.
CORRECTION: remeasure the three now-absent PC sources, then update memo:6-18 and the receipt artifacts to 1,375 present and 16 missing.
2026-09-10 | tracking | G377 | current off-pod 1375/1391 (169242156 bytes), 16 missing; decisions 64/69; eye 6/8; 2 deletions | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the test validates cached receipt consistency but not current memo-named source existence; test_g377_restore_receipt.py:22-71.
NEW GAP: prereg labels SVG as native_pixels but permits rendered-artifact substitution without defining a raster identity rule; g377_prereg_2026-09-10.md:91,216-220.
