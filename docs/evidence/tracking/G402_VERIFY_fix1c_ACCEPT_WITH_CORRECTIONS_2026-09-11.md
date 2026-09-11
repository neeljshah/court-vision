VERDICT: ACCEPT WITH CORRECTIONS
Candidate 1927ba82a: full diff reviewed; 133 additive paths, no rename or deletion.
PREMISE PASS: G380 raw receipts reproduce 85,333 CLAMP / 2,749 SUBPIXEL = 0.968790, transport 30/30, identity 0/30; receipts.csv:2, receipts_trace_a3.csv:2, identity.csv:2.
PREMISE PASS: whole-set census independently gives 40 unique 1080p30 sections and 79 unique 720p60 sections; both sealed 30-section draws reproduce exactly; census.csv:2, draw.csv:2.
REPRODUCTION PASS: claimed 19,087 sealed rows and 3,075 candidates vs reproduced 9,146+9,941 and 1,565+1,510; forbidden admissions claimed 0, reproduced 0; memo:16-31.
ACCEPTANCE replay/accounting PASS as PARTIAL: 29/30 and 30/30 complete unique windows, all 60 retained, one UNKNOWN, and receipt/trace 59/59; coverage_per_section.csv:2, evaluated_ticks.csv:2.
ACCEPTANCE mask/coverage PASS: full denominators reproduce as decoded 9,000/18,000 and evaluated 2,500/2,810; frozen-mask violations 0; summary.json:14.
ACCEPTANCE traceability PASS: 60/60 source files stream-hash equal; 508/508 manifest entries match; two runs reproduce 8 tables and 60 renders exactly; repeats.json:1, SHA256SUMS:1.
B1 PASS: all 2,347 excluded overrun rows, including 317 formerly admitted rows, are named before the sealed result; memo:5,16.
B2 PASS: changed CSV and JSON schemas are supersets, status sets remain additive, and every repository reader was checked; g402_tables.py:35.
B3 PASS: the failed window is retained as UNKNOWN with full decoded denominator; g402_tables.py:199,274.
B4 PASS: the one failed section occurs once and remains INCOMPLETE without replacement; launch_receipts.csv:6.
B5 PASS: the memo states no deployment, and route receipts retain one unchanged deployed-tree digest; memo:45, route_hashes.json:1.
B6 PASS: no module/path retirement exists and no reader imports the removed private helper name; g402_audit.py:34.
B7 PASS: independent draw reconstruction matches all 30 cards per kind and 60 unique section/frame pairs; g402_audit.py:34,43,120.
B8 PASS: this is a descriptive provenance diagnostic with no fitted residual or independence claim; memo:45.
B9 PASS: decoded frames, evaluated ticks, rows, and shared-player pairs are distinct measured denominators; memo:20-31.
B10 PASS: candidate changes no threshold; preregistered bars match the spec and remain sealed; prereg.md:18.
Q1 PASS: seal 0bfd1363cc6df3796e11894c7973062c2078ee9aa2c0951961b114d238cd4955 recomputes and commit 6120fc58f predates measurement; prereg.md:23.
Q2 PASS: no charged trial or K-dependent metric exists in this diagnostic; prereg.md:6.
Q3 PASS: the sealed bars and the candidate constants remain unchanged; prereg.md:18, g402_audit.py:14.
Q4 PASS: no OOS score or meta-learner is present; memo:1,45.
Q5 PASS: no comparative AHEAD status is claimed; memo:1,45.
Q6 PASS: independent claim-token scan of all candidate-added text is 0; all 12 changed text files are ASCII.
Q7 PASS: sampled audit size is 30 unique evaluated ticks per kind; all smaller units remain descriptive; eye_index.csv:2.
Q8 PASS with correction: premise was measured before scoring and independently rechecked here; the binding supply condition is SATISFIED, not falsified; summary.json:74-85.
EYE PASS: verifier inspected even card ordinals 0,6,12,18,24,29 per kind; native overlays include silence and retain visible mapping faults; eye_index.csv:2-61.
LOC PASS: g402_audit.py 183, g402_repeat.py 139, g402_tables.py 300, test file 222; all <=300.
ADDITIVITY PASS: target_mask 15->19 fields, eye_index 16->19, pixel_audit 20->20; no removed field/status/reader behavior.
TEST PASS: `python -m pytest tests/platformkit/test_g402_mixed_provenance_mask.py -q` -> 17 passed in 2.60s.
IMPORTER PASS: the spec test is the sole existing test importing touched modules, and it was run alone; test_g402_mixed_provenance_mask.py:1-222.
NOT VERIFIED PASS: explicit list covers the missing window, post-hoc model receipt, single-run scope, boundary crossings, and no target qualification; memo:39-45.
CORRECTION (minimal additive diff after summary.json:85): `+ "binding_supply_before_condition": "SATISFIED by 40/79 eligible unique sections"`.
2026-09-11 | tracking | G402 | 59/60 sealed windows measured; 3,075/19,087 candidate rows; 0 forbidden admissions; diagnostic PARTIAL | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: g402_repeat.py:88 treats every CSV/JSON value as opaque, broader than Q6's identifier-only exception; current added claim-bearing text independently scans clean.
