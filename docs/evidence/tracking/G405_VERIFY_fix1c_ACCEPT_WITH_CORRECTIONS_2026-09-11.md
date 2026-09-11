VERDICT: ACCEPT WITH CORRECTIONS
Candidate 051d2f5a6: full 342-path diff reviewed; patch-id 8a27f043fe642f5c76d2564703fad7f42e5ffae0.
ACCEPTANCE-1 PASS: 30 unique sealed ids; discovery precedes all probes; 60/60 inventories complete; no replacements (premise_snapshot.json:32).
ACCEPTANCE-2 PASS: raw listing plus metadata recomputation gives 11 YES / 19 NO / 0 UNKNOWN and the 30-only branch is false (summary.json:2).
ACCEPTANCE-3 PASS: 30 additive sidecar rows retain inherited fields, trace to 60 receipts, and reproduce twice (g405_build.py:129; repeats.json:2).
B1 PASS: all 30 planned ids remain in the denominator (summary.json:57).
B2 PASS: no table or sidecar field was removed versus the parent; all readers were surveyed (g405_formats.py:87; test_g405_discovery_formats.py:204).
B3 PASS: absent, incomplete, or one-inventory evidence remains UNKNOWN (g405_formats.py:57).
B4 PASS: the shadow export has no claim path or non-test consumer (g405_discovery_format_admission_2026-09-11.md:55).
B5 PASS: only owned scratch-route code and evidence changed; no deployed route or live feeder write (g405_discovery_format_admission_2026-09-11.md:54).
B6 PASS: no module moved; the sole test importer is package-qualified (test_g405_discovery_formats.py:15).
B7 PASS: all 30 paired cards are indexed in even draw order and raw states agree 30/30 (g405_discovery_format_admission_2026-09-11.md:48).
B8 PASS (not applicable): no model fit or residual comparison exists (prereg.md:64).
B9 PASS: 30 rows are 30 unique source ids; the N=30 formula reproduces indices 0..29 (premise_snapshot.json:33).
B10 PASS: 2400-second and run-wide-30 gates match the archived live recipe; format bars match the seal (g405_pod_probe.py:28; g405_formats.py:38).
Q1 PASS: seal independently recomputes to 4bceb8457a4cf4a43bb08969610f69c446122c391e9071ba61524fad5a073097 and is ancestral (prereg.md:65).
Q2 PASS (not applicable): no charged trial or launch K exists (prereg.md:64).
Q3 PASS: HLS/h264/720..1080/29..31 and 30/30 decision bars are unchanged (prereg.md:39; g405_formats.py:38).
Q4 PASS (not applicable): no OOS scoring or meta-learner is claimed (prereg.md:64).
Q5 PASS (not applicable): no AHEAD result is claimed (g405_discovery_format_admission_2026-09-11.md:1).
Q6 PASS: independent opaque-index scan found 0 hits in 355 owned text artifacts and all G405 ledger lines (q6_scan.json:31; q6_scan.json:32).
Q7 PASS: sampled n=30; all ids, inventories, cards, receipts, and rows are present (summary.json:57; test_g405_discovery_formats.py:127).
Q8 PASS: premise was rerun before discovery, draw, and probes (premise_snapshot.json:125).
PREMISE reproduced vs claimed: discovery probe calls 0 and non-default queue format values 0 vs 0 and 0 (premise_snapshot.json:147).
HEADLINE reproduced vs claimed: 11 YES / 19 NO / 0 UNKNOWN vs 11 / 19 / 0; 0/30 raw-inventory state mismatches (summary.json:2).
INTEGRITY PASS: 346/346 manifest entries exist and match; every spec evidence path exists; route hash matches (SHA256SUMS:1).
ADDITIVITY PASS: zero table/sidecar fields removed; ytid/dur remain aliases; YES/NO/UNKNOWN behavior remains supported (g405_build.py:13; g405_formats.py:10).
READER SURVEY PASS: only tests/platformkit/test_g405_discovery_formats.py imports a touched module; g405_finish has no test importer (test_g405_discovery_formats.py:15).
LOC PASS: g405_finish.py 188; g405_pod_probe.py 271; test_g405_discovery_formats.py 223.
TEST: `python -m pytest tests/platformkit/test_g405_discovery_formats.py -q` -> 21 passed in 1.12s.
MEMO PASS: an explicit NOT VERIFIED list is present (g405_discovery_format_admission_2026-09-11.md:57).
CORRECTION DIFF: memo:51 replace `354 ... 0 claim-field and 0 data-field hits` with `355 ... 0 owned/current-row hits; shared ledger has 26 opaque pattern_2 hits` (q6_scan.json:15; q6_scan.json:31).
2026-09-11 | tracking | G405 | raw census reproduces 11 YES / 19 NO / 0 UNKNOWN over 30; 30-only admission not supported; memo scan scope corrected | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: three sealed ids have titles naming other sports, so basketball-family membership is not established (draw.csv:18; draw.csv:20; draw.csv:28).
NEW GAP: the Q6 owned-file list omits the candidate-added prior verifier memo; independent scan found 0 hits there (g405_finish.py:105).
NEW GAP: test docstring says 8 sources at 25 fps while the current reproduced count is 17 (test_g405_discovery_formats.py:89; summary.json:13).
NEW GAP: full diff check reports one trailing space in runtime_receipts/premise_raw.txt:30.
