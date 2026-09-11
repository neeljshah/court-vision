VERDICT: ACCEPT
Candidate: e4ce13df2eb726b0474037f4e23db8149e633e70; full five-path diff reviewed.
Paths: G399=docs/evidence/tracking/g399_qualified_paint_larger_sample_2026-09-11; G396=docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11; memo=G399 sibling .md.
PREMISE PASS: reproduced G396 astra 30/30, sol/joint 27/30 and three audit passes; independently streamed 30/30 source hashes, all 30 unique and <=100578787 bytes; 30/30 bounds are 1920x1080 (G396/qualification/scores.csv:2; G396/audit_clicks.csv:2; source_receipts.csv:2; pts_bounds.csv:2).
HEADLINE PASS: claimed=reproduced: 60 planned/unique, 60 decoded, 42 visible, 153 fragments, 3 pairs, 1 recovered (G399_031); rates 1/60 planned, 1/60 decoded, 1/42 visible versus bar 30 (selection.csv:2; per_frame.csv:2; pairing.csv:2; audit_points.csv:2).
ACCEPTANCE-1 PASS: 30 unique sources and (video,section) identities, 21 videos, 60 unique frames and 360 unique tiles; configurations and identities hold (selection.csv:2; native_manifest.csv:2; runtime_receipts.json:2).
ACCEPTANCE-2 PASS: all three pairs have two nine-point audits; only G399_031 passes both, so 1 is below 30 and CLOSED AT LIMIT is correct (pairing.csv:2; audit_points.csv:2).
ACCEPTANCE-3 PASS: 120/120 answers are explicit, every candidate is audited, and five landed canonical tables match two recorded runs (per_frame.csv:2; pairing.csv:2; repeats.json:39).
EYE PASS: native cards 001/011/021/031/041/051/060 sampled evenly; all six candidate fragment grids inspected and judgments agree (renders/index.json:2; pairing.csv:2).
EVIDENCE PASS: all 15 spec-named paths exist; 251/251 SHA-256 entries independently rehash (memo:3; SHA256SUMS:1).
TEST SCOPE PASS: candidate touches no module; repository census finds the spec file is the only test containing G399 imports (test_g399_qualified_paint_larger_sample.py:4).
TEST PASS: `python -m pytest tests/platformkit/test_g399_qualified_paint_larger_sample.py -q` -> 22 passed in 1.53s.
LOC PASS: candidate touches zero .py files; the 300-line rail is unchanged (candidate diff; test_g399_qualified_paint_larger_sample.py:1).
MEMO LIMITS PASS: substantive NOT VERIFIED list is present (memo:49).
B1 PASS: planned, decoded and visible denominators remain separate; no failing row was excluded (summary.json:22).
B2 PASS: no field/status removal or rename; runs retain returncode/stdout and new provenance is additive; no repository reader of the touched schema was found (repeats.json:6; repeats.json:64).
B3 PASS: ABSENT/UNKNOWN/NO_ANSWER remain explicit and are not adverse recovery (summary.json:9; per_frame.csv:2).
B4 PASS (N/A): static scoring has no claim/reclaim path (g399_score.py:201).
B5 PASS: PC-only memo names no deployment, and candidate changes evidence text only (memo:3).
B6 PASS: candidate moves/removes no path or module; existing full-package imports remain live (test_g399_qualified_paint_larger_sample.py:4).
B7 PASS: exhaustive index is ordered G399_001..060 and verifier sampling was even (renders/index.json:2; selection.csv:2).
B8 PASS: finisher visibility and pair audits are independent of rater fragments (memo:17; pairing.csv:2).
B9 PASS: 60 unique contexts, 30 source/section identities and three named denominators are non-degenerate (selection.csv:2; summary.json:22).
B10 PASS: candidate moves no bar; 3 px, 6 px, 60 px and 8/9 match the seal (g399_protocol.py:7; g399_prereg_2026-09-11.md:39).
Q1 PASS: seal verifies; prereg commit 92a921e36 predates first summary commit b7fa84f3a (g399_prereg_2026-09-11.md:69; summary.json:8).
Q2 PASS (N/A): no charged trial or K is introduced (memo:19).
Q3 PASS: all bars remain byte-identical to the preregistration (g399_protocol.py:7; g399_prereg_2026-09-11.md:39).
Q4 PASS (N/A): no OOS comparison or meta-learner is scored (memo:24).
Q5 PASS (N/A): no AHEAD result is reported (memo:24).
Q6 PASS: independently rescanned all 182 receipt paths at 0 hits; candidate memo and prior verifier memo also scan clean; candidate ledger row is compliant (q6_scan.json:2; RESULTS_LEDGER.md:767).
Q7 PASS: n=60 sampled contexts exceeds 30; the index exhausts the same set in even order (selection.csv:2; renders/index.json:2).
Q8 PASS: same-day premise independently remeasured and holds (G396/qualification/scores.csv:2; source_receipts.csv:2).
ADDITIVITY PASS: direct parent fields `identical`, `runs`, process aliases and statuses remain readable; candidate only adds provenance/restores run output (repeats.json:2; repeats.json:64).
CORRECTIONS: none under the applied acceptance/B/Q rules.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G399 | premise holds; 60 planned/60 decoded, 42 visible, 3 candidate pairs, 1 recovered; 1/60 planned, 1/60 decoded, 1/42 visible; bar 30 not met | CLOSED AT LIMIT (verified: codex-sol, contract A/B/Q)
NEW GAP: memo:41-42 splices the Fix 1d note inside the Fix 1c sentence; move the Fix 1d sentence to its own paragraph.
