VERDICT: REJECT
Candidate: 02daa0580120049cf2149debbda4a2ccfb176f03; full 276-path diff reviewed.
PREMISE PASS: population.json independently gives 121/121 unique terminal ORIGINAL sections (111 tracked, 10 thin), with requested formats 270=109 and 232=12; source_format_join.csv has zero independent delivered-format receipt fields.
REPRO PASS: claimed/reproduced native classes = 720p30 26, 1080p60 24, 1080p30 22, 720p25 11, 720p60 5, UNKNOWN 33; retention/digest/probe = 88/88/88; memo:9-15.
REPRO PASS: claimed/reproduced reads = 100491/511485, evaluated/suspended = 97065/3426, held = 296072/353842 and 3317/3832, cap-loss count = 29/88, regeneration = 265/265; memo:19-29.
REPRO FAIL: memo claims 1760 scanned record fields; q6_scan.json independently reports 2002 record fields and 177 file records; memo:29.
ARTIFACT PASS: all 22 named evidence paths exist, 121 traces and 118 cards exist, 266/266 SHA256SUMS entries match, largest delivered file is 167044 bytes, and 88/88 named receiver files exist; SHA256SUMS:1.
TEST PASS: `python -m pytest tests/platformkit/test_g407_rendition_boundary.py -q --basetemp=C:\Users\neelj\AppData\Local\Temp\g407_codex_verify_20260911` -> 21 passed in 0.88s; this is the only existing test importer of a touched module; tests/platformkit/test_g407_rendition_boundary.py:10.
LOC PASS: g407_cards.py 117, g407_census.py 203, g407_probe.py 170, g407_receipts.py 94, g407_repeats.py 71, g407_report.py 298, g407_tables.py 169, test 239; g407_report.py:1.
ACCEPTANCE-1 FAIL: bind_rendition copies requested_format_id into actual_format_id after a compatibility check; requested ID plus dimensions is not exact delivered-format binding; g407_tables.py:66-73. UNRESOLVED is also marked COMPLETE; provenance_counts.csv:14.
ACCEPTANCE-2 FAIL: ten ball_table_absent rows are numeric zeros and reads_reconcile=1, so UNKNOWN is scored as a successful zero-equals-zero reconciliation; coverage.csv:41 and g407_report.py:150-151. Correct known-schedule result is 111/111, plus 10 UNKNOWN, not 121/121.
ACCEPTANCE-3 PASS: 12 asset receipts predate the observed window, two saved-input processes match 265/265, and zero scratch launches are explicitly NOT VALIDATED; memo:29,45.
B1 PASS: excluded native/schedule unknown sets are named; memo:13,19.
B2 PASS: diff has additions/modifications only, no rename/removal, and the sole test reader imports full package paths; tests/platformkit/test_g407_rendition_boundary.py:10-18.
B3 PASS: absent sources remain explicit UNKNOWN/PARTIAL rather than being rejected; memo:13-15.
B4 PASS: zero-launch state is terminal and not claimable; launch_receipts.csv:2.
B5 PASS: pod work used /workspace/wt/a10 and scratch output only; runtime_receipts/stage1_pod_census.log.txt:2-6.
B6 PASS: no module was moved or retired; tests/platformkit/test_g407_rendition_boundary.py:10-18.
B7 PASS: 118 unique cards cover all 88 retained and an exact-even 30 of 33 missing-source rows; eye_index.csv:1.
B8 PASS: no fitted comparison is claimed; memo:48.
B9 PASS: section IDs are unique and held denominators are shared consecutive evaluated-tick pairs; memo:9,21.
B10 FAIL: the sealed total draw cap is 180, but the report calls even_draw with 1000000; prereg.md:12 and g407_report.py:218.
Q1 PASS: independently recomputed LF seal matches a411f5905fbce243d2198889752e40c5025a9b1abff74105976bbdd82606978c, and commit 050d633bc is an ancestor predating census computation; prereg.md:23.
Q2 PASS: no charged/scored trial or scratch launch exists; launch_receipts.csv:2.
Q3 FAIL: the 180 total-cap bar is not byte-identical at execution; g407_report.py:218.
Q4 PASS: no OOS comparison or meta-learner is claimed; memo:45-50.
Q5 PASS: no AHEAD claim is made; memo:1.
Q6 PASS: independent field-aware rescan gives zero prohibited prose hits across 177 delivered file records; q6_scan.json:1.
Q7 PASS: every under-30 measured class is descriptive PARTIAL, while the retained card set is exhaustive; memo:1,29.
Q8 PASS: whole-set premise recomputation gives 121 unique sections and confirms the native mix, but not actual rendition identity; population.json:2 and source_format_join.csv:1.
CORRECTION: g407_tables.py:66-73 must require a digest-bound delivered-format receipt and must never derive actual_format_id from requested_format_id; absent such receipts, actual renditions remain UNRESOLVED/PARTIAL.
CORRECTION: g407_report.py:74-96,124-151 must emit UNKNOWN counts and reconciliation for a non-KNOWN schedule; summary/memo must say 111/111 known plus 10 UNKNOWN.
CORRECTION: g407_report.py:218 must restore total_cap=180; g407_tables.py:108-109 and draw output must force residual strata PARTIAL; regenerate tables, repeats, scan, and SHA256SUMS.
CORRECTION: memo:29 must replace 1760 with 2002 record fields and name 177 delivered file records.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G407 | 121 unique terminal ORIGINAL sections; 88 retained native probes (720p30 26, 1080p60 24, 1080p30 22, 720p25 11, 720p60 5, UNKNOWN 33); no independently receipt-bound delivered rendition; 111 known schedules reconcile and 10 are UNKNOWN; saved-input regeneration 265/265 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: The focused test passes without asserting independent delivered-format receipt binding, residual-PARTIAL status, the sealed 180 total cap, or schedule-absent UNKNOWN propagation.
