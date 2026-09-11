VERDICT: REJECT
Candidate: b7fa84f3a13900753ea8655bdd55abfbb0fb2a82; full 180-path diff reviewed (4294 additions, 1 deletion, 0 deleted/renamed paths).
PREMISE PASS: raw G396 tables reproduce astra 30/30, sol 27/30, joint 27/30 and 3/6 real audit passes; all four instructions, both high configurations and the executable rehash exactly; all 30 sources rehash/resize exactly at 1920x1080 (premise_receipt.json:2-49; runtime_receipts.json:2-50).
HEADLINE PASS: claimed = reproduced: 60 planned, 60 decoded, 42 visible, 153 fragments, 3 candidate pairs, 1 recovered state; recovery is 1/60 planned, 1/60 decoded and 1/42 visible against 30 (summary.json:2-47; pairing.csv:1-4).
ACCEPTANCE-1 PASS: qualified settings and identities hold; 30 sources, 30 sections, 21 videos, 60 unique frames and 360 unique tiles are retained, with all 60 even-order cards present (summary.json:41-48; memo:15-23).
ACCEPTANCE-2 PASS: independent geometry reproduces the same three sealed-rule pairs; nine points for each of six fragment judgments support one passing state, below the supply bar (pairing.csv:1-4; summary.json:25-45).
ACCEPTANCE-3 FAIL: the delivered blind_ratings.csv digest is 73d77ee7... but both repeat receipts name 6772ed5e...; q6_redactions records the post-repeat mutation, so the repeats are not from the delivered immutable answers (repeats.json:3-23; q6_redactions.json:15-19; SHA256SUMS:3).
EYE/EVIDENCE PASS: inspected even contexts 001/011/021/031/041/051/060 and all six candidate point grids; 251/251 manifest entries exist and rehash, with no unlisted evidence file (memo:43-46; audit_points.csv:1-55).
LOC PASS: touched g399_score.py is 224 lines and g399_q6_scan.py is 47 lines, both <=300 (g399_score.py:1-224; g399_q6_scan.py:1-47).
ADDITIVITY FAIL: g399_q6_scan.hits removes prior detection for arbitrary numeric JSON/CSV claim values; the importing test checks only digest/prose cases, not the removed reader behavior (g399_q6_scan.py:19-26; test_g399_qualified_paint_larger_sample.py:62-69).
MEMO LIMITS PASS: a substantive NOT VERIFIED list and necessary-only boundary are present (memo:50-60).
TEST PASS: `python -m pytest tests/platformkit/test_g399_qualified_paint_larger_sample.py -q` -> 20 passed in 0.89s.
TEST SCOPE PASS: repository import census finds that file is the only existing test importing either touched module (test_g399_qualified_paint_larger_sample.py:62-69,95-145).
B1 PASS: all 60 planned rows remain in the primary denominator; visibility is separately conditioned (summary.json:25-35).
B2 FAIL: the scanner reader behavior is narrowed without a compatibility path or a test for numeric claim fields (g399_q6_scan.py:19-26).
B3 PASS: missing answers remain named NO_ANSWER and ABSENT/UNKNOWN states remain accounted (g399_score.py:21-47; summary.json:9-23).
B4 PASS (N/A): this static evidence scorer has no claim/reclaim path (g399_score.py:201-220).
B5 PASS: the row is PC-only and reports no pod or production deployment (memo:3).
B6 PASS: no path is deleted/renamed and both touched modules retain their entry points/importers (g399_score.py:201-224; g399_q6_scan.py:35-47).
B7 PASS: the decision set is all 60 states; render inspection was evenly spread, not a head slice (memo:43-46; renders/index.json:2).
B8 PASS: no fit or orientation inference is claimed; recovery uses independent fragment audits (memo:33-35; g399_score.py:93-105).
B9 PASS: 60 unique contexts/frames and separately named planned, decoded and visible denominators are non-degenerate (summary.json:25-39).
B10 FAIL: the candidate weakens the vocabulary gate by masking every structured numeric value, including claim fields; parent-equivalent detection 1 becomes candidate detection 0 (g399_q6_scan.py:16-26).
Q1 PASS: seal 1ce0d72b... independently reproduces and its commit 92a921e36 predates measurement artifacts (g399_prereg_2026-09-11.md:68-69).
Q2 PASS (N/A): no charged trial or multiplicity count is introduced (memo:48).
Q3 PASS: scientific bars 3 px, 6 px, 60 px, 8/9 and supply 30 remain frozen (g399_protocol.py:6-10; g399_prereg_2026-09-11.md:39-47).
Q4 PASS (N/A): no OOS comparison or meta-learner is scored (memo:48).
Q5 PASS (N/A): no AHEAD result is reported (memo:48).
Q6 PASS: independent scan of all 178 evidence text files and the added ledger line finds 0 current hits (q6_scan.json:3-172).
Q7 PASS: 60 sampled contexts across all 30 retained sections clear the sampling rail (summary.json:4-7,41-44).
Q8 PASS: the same-day premise was independently remeasured and holds (premise_receipt.json:16-49).
REQUIRED DIFF: rerun both repeat processes after the recorded redaction, require every delivered canonical-table digest to match each run, then refresh repeats.json and SHA256SUMS.
REQUIRED DIFF: replace blanket DATUM_RE masking with field-aware non-claim data handling, add a numeric-claim regression test, and retain detection parity for claim fields (g399_q6_scan.py:19-26).
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G399 | premise 30/30 source identities; 60 planned and decoded, 42 visible; 3 audited candidate pairs, 1 recovered state; delivered repeat receipt disagrees with one delivered canonical table | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: q6_scan.json inventories 168 paths but omits all 14 dispatch batch TSV artifacts; the verifier's complete 178-file evidence scan found 0 current hits.
NEW GAP: render_point_grid is newly added and used for the audit grids but has no direct boundary/decode regression test (g399_score.py:172-198).
