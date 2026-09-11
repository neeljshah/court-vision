VERDICT: REJECT
Candidate 3a9258a69: full 116-file diff reviewed; rejection is limited to B2/B10/Q3 and acceptance row 3.
ACCEPTANCE-1 PASS: 30 unique IDs, even frozen draw, discovery before probe, and 60/60 complete inventories (draw.csv:1; runtime_receipts/probe_receipts.json:17).
ACCEPTANCE-2 PASS: exact full-denominator table is 11 YES / 19 NO / 0 UNKNOWN and the 30-only branch is false (summary.json:4; summary.json:179).
ACCEPTANCE-3 FAIL: inherited live fields `ytid` and `dur` are absent from every sidecar row (premise_snapshot.json:15; discovery_queue.jsonl:1).
B1 PASS: all 30 planned rows remain in the denominator, including failures by construction (g405_build.py:179; summary.json:179).
B2 FAIL: `ytid`->`source_id` and `dur`->`duration_s` are renames without preserved aliases (g405_build.py:124; premise_snapshot.json:15).
B3 PASS: incomplete or disagreeing inventories remain UNKNOWN (g405_formats.py:59; g405_formats.py:68).
B4 PASS: the export is unused and introduces no claim path (g405_discovery_format_admission_2026-09-11.md:54).
B5 PASS: the proposed feeder diff is recorded as applied nowhere (g405_discovery_format_admission_2026-09-11.md:55).
B6 PASS: no module was moved; the only test importer remains package-qualified (test_g405_discovery_formats.py:10).
B7 PASS: all 30 cards were inspected in even draw order (g405_discovery_format_admission_2026-09-11.md:45).
B8 PASS (not applicable): this diagnostic fits no model (g405_discovery_format_admission_2026-09-11.md:22).
B9 PASS: denominator is 30 unique sealed source IDs, not repeated memberships (draw.csv:1; summary.json:179).
B10 FAIL: live discovery has a 2400-second gate, while the probe helper appends every returned item without it (discovery_config_hashes.json:10; g405_pod_probe.py:75).
Q1 PASS: seal recomputed exactly as 4bceb8457a4cf4a43bb08969610f69c446122c391e9071ba61524fad5a073097 and predates probing (prereg.md:65).
Q2 PASS (not applicable): no charged trial or launch K exists (prereg.md:63).
Q3 FAIL: the frozen 2400-second discovery gate is not enforced by the measurement helper (discovery_config_hashes.json:10; g405_pod_probe.py:75).
Q4 PASS (not applicable): no OOS scoring or meta-learner is claimed (prereg.md:63).
Q5 PASS (not applicable): no AHEAD result is claimed (g405_discovery_format_admission_2026-09-11.md:1).
Q6 PASS: field-aware scan reports zero claim-field hits; the added ledger row was also checked (common_receipts/q6_scan.json:9; RESULTS_LEDGER.md:770).
Q7 PASS: this is a sampled n=30 diagnostic and every selected case is archived (summary.json:179; eye_index.csv:1).
Q8 PASS (same-day scope): premise replay found 0 discovery probe calls and 0 non-270 queue values (runtime_receipts/premise_raw.txt:48).
PREMISE reproduced vs claimed: 0 discovery probes / 0 non-270 queue values vs no existing discovery rendition evidence (premise_snapshot.json:5).
HEADLINE reproduced vs claimed: 11 YES / 19 NO / 0 UNKNOWN vs 11 / 19 / 0; 30/30 digests and table states agree (availability.csv:1; summary.json:4).
POPULATION reproduced vs claimed: 405 rows / 365 unique; sealed draw is exactly reproduced with 30 unique IDs (premise_snapshot.json:39; draw.csv:1).
SETTING CHECK: 6/30 drawn IDs are below 2400 seconds; applying only that archived gate yields 325 rows / 288 unique and just 3/30 draw overlap.
INTEGRITY PASS: 109/109 manifest entries exist and match; raw listings, metadata files, and cards are 30/30/30 (SHA256SUMS:1).
LOC PASS: g405_build.py 226, g405_finish.py 156, g405_formats.py 99, g405_pod_probe.py 162, test file 134 (g405_build.py:226).
READER SURVEY: only tests/platformkit/test_g405_discovery_formats.py imports touched modules; no consumer reads the sidecar (test_g405_discovery_formats.py:10).
TEST: `python -m pytest tests/platformkit/test_g405_discovery_formats.py -q` -> 15 passed in 0.80s.
MEMO CHECK PASS: explicit NOT VERIFIED list is present (g405_discovery_format_admission_2026-09-11.md:57).
CORRECTION DIFF: g405_build.py:124 add inherited aliases `"ytid": sid, "dur": row["duration_s"]` before rebuilding evidence.
CORRECTION DIFF: g405_pod_probe.py:75 apply the frozen seen/DENY/duration/MAX eligibility, then redraw, reprobe, and recompute the memo.
2026-09-11 | tracking | G405 | archived sample reproduced as 11 YES / 19 NO / 0 UNKNOWN, but the live 2400-second gate and inherited ytid/dur fields are absent | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: spec names root `probe_receipts.csv`, but only `runtime_receipts/probe_receipts.json` exists (G405_spec.md:26).
NEW GAP: premise rerun is timestamped 16:41:40Z after discovery at 16:35:08Z and probing at 16:38:59Z (premise_snapshot.json:3).
NEW GAP: the automated text scan omits the required ledger file from its owned path list (g405_finish.py:104).
