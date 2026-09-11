VERDICT: REJECT
Candidate: 23c73fb2420fbfac7e73701b850b86aeb46afb2c; full seven-path diff reviewed.
Paths: G399=docs/evidence/tracking/g399_qualified_paint_larger_sample_2026-09-11; G396=docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11; memo=G399 sibling .md; unprefixed evidence basenames are under G399.
PREMISE PASS: reproduced G396 astra 30/30, sol/joint 27/30, three audit passes; 30/30 sources rehash and decode at 1920x1080 (G396/qualification/scores.csv:2-61; G396/audit_clicks.csv:2-7; source_receipts.csv:2-31; pts_bounds.csv:2-31).
HEADLINE PASS: claimed = reproduced: 60 planned/decoded, 42 visible, 153 fragments, 3 pairs, 1 recovered; 1/60 planned, 1/60 decoded, 1/42 visible vs bar 30 (summary.json:2-48; pairing.csv:2-4).
ACCEPTANCE-1 PASS: 30 sources, 21 videos, 60 unique frames and 360 unique tiles; identities/configurations hold (selection.csv:2-61; native_manifest.csv:2-361; runtime_receipts.json:2-50).
ACCEPTANCE-2 PASS: all three pairs have two nine-point audits; only G399_031 passes both, below 30 (pairing.csv:2-4; audit_points.csv:2-55).
ACCEPTANCE-3 PASS: 120/120 answers present, all candidates audited, and five canonical tables match twice (blind_ratings.csv:2-154; repeats.json:2-61).
EYE PASS: inspected native cards 001/011/021/031/041/051/060 and all six fragment point grids; counts agree (renders/index.json:2-365; pairing.csv:2-4).
EVIDENCE PASS: all 15 named evidence paths exist and 251/251 SHA-256 entries rehash (memo:3-47; SHA256SUMS:1-251).
TEST SCOPE PASS: repository census finds the spec file is the only test importing G399 modules (test_g399_qualified_paint_larger_sample.py:4-90).
TEST PASS: `python -m pytest tests/platformkit/test_g399_qualified_paint_larger_sample.py -q` -> 22 passed in 1.15s.
LOC PASS: sole touched .py is 200 lines, <=300 (test_g399_qualified_paint_larger_sample.py:1-200).
MEMO LIMITS PASS: substantive NOT VERIFIED list is present (memo:49-52).
B1 PASS: planned, decoded and visible denominators are separate (summary.json:25-35).
B2 FAIL: restored runs omit prior per-run `stdout` fields (b7fa84f3a:G399/repeats.json:15,27; repeats.json:29-53).
B3 PASS: ABSENT/UNKNOWN/NO_ANSWER remain explicit and are not adverse recovery (summary.json:9-23; blind_ratings.csv:2-154).
B4 PASS (N/A): static scorer has no claim/reclaim path (g399_score.py:201-224).
B5 PASS: PC-only memo names no deployment (memo:3).
B6 PASS: candidate moves/removes no path; imports remain live (test_g399_qualified_paint_larger_sample.py:4-5,63-90).
B7 PASS: 60 cards are indexed in exact 1..60 order; verifier sample is even (renders/index.json:2-365).
B8 PASS: independent audit, not self-fit, determines recovery (memo:21-26; pairing.csv:2-4).
B9 PASS: 60 unique contexts/frames and three named denominators are non-degenerate (selection.csv:2-61; summary.json:25-35).
B10 PASS: candidate changes no bar; 3 px, 6 px, 60 px and 8/9 remain frozen (g399_protocol.py:7-11).
Q1 PASS: seal validates and commit 92a921e36 predates the measured summary (g399_prereg_2026-09-11.md:69; summary.json:8).
Q2 PASS (N/A): no charged trial is introduced (memo:19-36).
Q3 PASS: protocol bars match the preregistration (g399_protocol.py:7-11; g399_prereg_2026-09-11.md:39-59).
Q4 PASS (N/A): no OOS comparison or meta-learner is scored (memo:24-26).
Q5 PASS (N/A): no AHEAD result is reported (memo:24-26).
Q6 PASS: independent scan of all 184 row text files reports zero hits; receipt reproduces 182/0 (q6_scan.json:2-365; test_g399_qualified_paint_larger_sample.py:62-80).
Q7 PASS: all 60 sampled contexts are retained and the even-order index is exhaustive (selection.csv:2-61; renders/index.json:2-365).
Q8 PASS: same-day premise was independently remeasured and holds (G396/qualification/scores.csv:2-61; source_receipts.csv:2-31).
MINIMAL DIFF: repeats.json:40,52 add the prior `stdout` summary field after `run`; refresh its SHA256SUMS entry and memo:44 digest.
MINIMAL DIFF: memo:35 change scan inventory 178 -> 182.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G399 | premise holds; 60 planned/decoded, 42 visible, 3 candidate pairs, 1 recovered; runs alias omits prior stdout; memo scan count is 178 vs measured 182 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: none.
