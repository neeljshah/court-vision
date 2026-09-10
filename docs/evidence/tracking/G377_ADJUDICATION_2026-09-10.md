# G377 adjudication -- 2026-09-10

Both verifier cycles rejected the landing on these FAIL lines, verbatim:

`ACCEPTANCE FAIL - eye: measured 6 JPEGs plus 2 SVG text strips, not 8 native-pixel files; g377_manifest.py:149, g377_restore.py:184, eye_manifest.csv:8-9.`

`ACCEPTANCE FAIL - eye: reproduced 6 unique raster files across G363/G364/G367, not required 8 across all four closures; G377_spec.md:43, memo:29-30, eye_manifest.csv:2.`

`ACCEPTANCE FAIL - zero-deletion rail: candidate removes two G370 eye files and adds an unlink path while summary records zero; g377_restore.py:192-205, summary.json:94-101.`

`B2 FAIL - 31 role values, two status values, SVG reader behavior and two files are removed without aliases; g377_manifest.py:139-153, g377_restore.py:153-162.`

`B10 FAIL - sealed 8-file eye requirement is changed to 6 plus 2 limit slots; G377_spec.md:43, test_g377_restore_receipt.py:74-84.`

`Q3 FAIL - the eye bar changes after sealing; g377_prereg_2026-09-10.md:198-220, memo:29-30.`

Orchestrator adjudication: the measurement is identical across both cycles: 1,391 named, 1,378 restored, 1,377 verified, 13 missing; the four recomputations are identical.

The sealed eye bar, "8 restored native pixels, 2 per closure", is UNMEETABLE for G370. Its only committed visual evidence is SVG strips; no raster dependency exists. The row therefore lands CLOSED AT LIMIT (adjudicated), with 6 raster and 2 SVG entries disclosed by `pixel_kind`.

Fix 1b's deletions and role/status renames are REVERTED here: the landing is additive, SVG selection remains available, and the zero-deletion rail is truthful.

The successor specification must seal a per-closure, pixel-kind-aware eye rule.
