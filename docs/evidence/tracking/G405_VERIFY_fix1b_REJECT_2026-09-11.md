VERDICT: REJECT
Candidate ed876f9b3: full changed-path diff reviewed; rejection is limited to ACCEPTANCE-1, B10/Q3, and Q6.
ACCEPTANCE-1 FAIL: the draw is complete and even, but 18 discover.log-only ids were excluded by a gate stricter than the archived live recipe (premise_snapshot.json:60; premise_snapshot.json:87).
ACCEPTANCE-2 PASS: raw listing/metadata recomputation gives 17 YES / 12 NO / 1 UNKNOWN; the 30-only branch is false (summary.json:2; summary.json:128).
ACCEPTANCE-3 PASS: 30 sidecar rows retain inherited fields and aliases, trace to 60 receipts, and reproduce twice (g405_build.py:130; repeats.json:2).
B1 PASS: every planned source remains in the denominator, including the failed probe (summary.json:3; summary.json:124).
B2 PASS: parent-to-candidate schema comparison removed zero fields; ytid/dur are additive aliases (g405_build.py:13; g405_build.py:130).
B3 PASS: absent, incomplete, or disagreeing evidence remains UNKNOWN (g405_formats.py:62; g405_formats.py:72).
B4 PASS: the shadow export is unused and introduces no claim path (g405_discovery_format_admission_2026-09-11.md:55).
B5 PASS: no deployed-tree change, download, restart, enqueue, or automatic policy action is claimed (g405_discovery_format_admission_2026-09-11.md:54).
B6 PASS: no module moved; the only test importer is package-qualified (test_g405_discovery_formats.py:10; test_g405_discovery_formats.py:14).
B7 PASS: all 30 paired cards exist in even draw order and independently match their states (eye_index.csv:1; common_receipts/eye_recompute.txt:1).
B8 PASS (not applicable): this diagnostic fits no model (prereg.md:63).
B9 PASS: 30 rows are 30 unique ids and the exact even draw reproduces from 161 unique population ids (draw.csv:1; premise_snapshot.json:30).
B10 FAIL: helper seen = ledger|queue|log and adds a per-query cap, while the archived live gate is ledger|queue with a run-wide cap (g405_pod_probe.py:69; premise_snapshot.json:87).
Q1 PASS: seal independently recomputes to 4bceb8457a4cf4a43bb08969610f69c446122c391e9071ba61524fad5a073097 and predates probing (prereg.md:65).
Q2 PASS (not applicable): no charged trial or launch K exists (prereg.md:63).
Q3 FAIL: the scored population uses the stricter post-seal eligibility definition (premise_snapshot.json:88; premise_snapshot.json:94).
Q4 PASS (not applicable): no OOS scoring or meta-learner is claimed (prereg.md:63).
Q5 PASS (not applicable): no AHEAD result is claimed (g405_discovery_format_admission_2026-09-11.md:1).
Q6 FAIL: both committed scan receipts emit restricted vocabulary as non-opaque JSON labels (common_receipts/q6_scan.json:6; att1_ungated/common_receipts/q6_scan.json:8).
Q7 PASS: sampled n=30; all selected cases, two inventories, cards, and receipts are present (summary.json:124; probe_receipts.csv:1).
Q8 PASS: premise snapshot is timestamped before discovery and probing (premise_snapshot.json:109).
PREMISE reproduced vs claimed: 0 discovery probe calls / 0 non-default queue fmt values vs 0 / 0 (runtime_receipts/premise_raw.txt:41; runtime_receipts/premise_raw.txt:42).
HEADLINE reproduced vs claimed: 17 YES / 12 NO / 1 UNKNOWN vs 17 / 12 / 1; 0/30 state mismatches from raw inventories (summary.json:2).
POPULATION reproduced: 405 returned / 163 eligible rows / 161 unique; sealed draw reproduces exactly as 30 unique ids, minimum duration 2771 s (premise_snapshot.json:17; premise_snapshot.json:30).
INTEGRITY PASS: 235/235 manifest entries exist and match; all named evidence paths exist; 30/30 cards match independent states (SHA256SUMS:1).
ADDITIVITY PASS: zero CSV/JSON fields removed versus parent; YES/NO remain and UNKNOWN is additive; no sidecar consumer exists (g405_build.py:13; g405_discovery_format_admission_2026-09-11.md:56).
READER SURVEY PASS: only tests/platformkit/test_g405_discovery_formats.py imports touched modules; no test imports g405_finish.py (test_g405_discovery_formats.py:10).
LOC PASS: g405_build.py 234, g405_finish.py 175, g405_pod_probe.py 246, test_g405_discovery_formats.py 190 (g405_pod_probe.py:246).
TEST: `python -m pytest tests/platformkit/test_g405_discovery_formats.py -q` -> 19 passed in 0.78s.
MEMO PASS: explicit NOT VERIFIED list is present (g405_discovery_format_admission_2026-09-11.md:57).
CORRECTION DIFF: g405_pod_probe.py:69 use ledger|queue only and enforce the run-wide cap; rerun discovery, redraw, reprobe, and regenerate dependent evidence.
CORRECTION DIFF: g405_finish.py:124 emit opaque pattern indices in scan receipts; regenerate both scan receipts and SHA256SUMS without restricted labels.
2026-09-11 | tracking | G405 | raw census reproduces 17 YES / 12 NO / 1 UNKNOWN, but the sampled population uses a stricter gate than the live recipe and scan receipts emit restricted labels | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: exact seen-set contents are not archived, only counts and digests, so the live-gate draw cannot be independently rebuilt from committed evidence (premise_snapshot.json:61).
