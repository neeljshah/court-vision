VERDICT: CLOSED AT LIMIT
Candidate PASS: f646ff42c stat and full diff inspected; only the pre-existing `.g400_local/` was untracked before verification.
PREMISE NUMBER PASS: independent recount is claimed/measured 530 unique old boxes over 27 games; census evidence has 184 sections, 35 ids, 34 eligible (dev_boxes_v3.csv:2; premise.json:11).
ACCEPTANCE identity FAIL: 300 unique states, 30 ids, 30/30 receiver hashes and zero exact old-id overlap reproduce, but 62/67 old identities lack title resolution, so alternate-upload disjointness is not validated (g400_ball_reference_growth_stage1_2026-09-11.md:21).
ACCEPTANCE reliability FAIL: round 1 is n=29, pooled is n=299, round 8 kappa is 0.3605, and median gap 24.021 px exceeds the 13.75 px bar (kappa.csv:2; kappa.csv:9; usability.json:3).
ACCEPTANCE yield PASS: 116 unique audited additions/300 = 0.3867 across 30 ids triggers the specified route closure; no next stage is permitted (yield.csv:2; yield.csv:7; G400_spec.md:25).
REPRODUCED claimed/measured: old 530/27; states 300; receiver 30/30; round-8 0.3605; pooled 0.7505 at n=299; gap 24.021/13.75 px; yield 116/300=0.3867 (summary.json:2; summary.json:25).
EVIDENCE PASS: every spec-named path exists, all 95 SHA256SUMS entries match current bytes, all text entries are LF, and 30 receiver objects match recorded size/hash (SHA256SUMS:1; source_receipts.csv:2).
RENDERS PASS: the 30-card index matches even full-set indices 0,10,...,289,299; cards and conflict sheets 1/10/20 were inspected (eye_index.csv:2; g400_controls.py:83).
MEMO PASS: NOT VERIFIED lists eight limitations, including unresolved upload identity and the missing judgment (g400_ball_reference_growth_stage1_2026-09-11.md:37).
TEST PASS: `python -m pytest tests/platformkit/test_g400_ball_reference_growth.py -q` -> 12 passed in 0.90s (test_g400_ball_reference_growth.py:1).
TEST IMPORTERS PASS: repository search finds no existing test importing touched `g400_finish`; the exact required per-file test list is the single command above (g400_finish.py:1).
LOC PASS: touched g400_finish.py is 154 lines, within the 300-line limit (g400_finish.py:154).
ADDITIVITY PASS: candidate preserves q6/repeat keys and all SHA paths; it only corrects LF normalization and dependent digests, with no renamed/removed field, status, or reader behavior (g400_finish.py:29; q6_scan.json:2).
B1 PASS: the denominator is all 300 planned states; the missing judgment is not excluded from yield (yield.csv:2).
B2 PASS: no schema/status/reader behavior was removed or renamed (g400_finish.py:29).
B3 PASS: the missing judgment remains explicit and separately adjudicated, not converted into adverse evidence (kappa.csv:2).
B4 PASS: no claim or retry path is changed by this candidate (g400_finish.py:29).
B5 PASS: only row scratch and the off-repo receiver are reported; no deployed-tree change is present (g400_ball_reference_growth_stage1_2026-09-11.md:11).
B6 PASS: no module moved or retired (g400_finish.py:1).
B7 PASS: draw and render samples use full-set even formulas, not head slices (G400_spec.md:8; eye_index.csv:2).
B8 PASS: planted controls are identified as scorer controls, not independent detector evidence (G400_spec.md:18).
B9 PASS: units are 300 unique frame keys and 116 unique additions, not recycled identifiers (yield.csv:2).
B10 PASS: fixed 0.60, 0.5, 120, and 300 bars match spec and preregistration (G400_spec.md:23; prereg.md:15).
Q1 PASS: seal eda637cb7eba86bce3b2a9b4b5850c47e140cf5f5bd08e6778bd8bf856c1bfca reproduces; commit 6256cb133 predates measurement (prereg.md:24).
Q2 PASS: no charged trial or model metric is present (prereg.md:19).
Q3 PASS: failed bars remain fixed and are reported without lowering (kappa.csv:9; yield.csv:7).
Q4 PASS: no OOS comparison or meta-learner was run (prereg.md:19).
Q5 PASS: no AHEAD claim or next-stage allocation is made (g400_ball_reference_growth_stage1_2026-09-11.md:33).
Q6 PASS: independent scan reproduces 84 text artifacts, six exempt identifier findings, and zero non-opaque hits (q6_scan.json:30).
Q7 PASS: sub-rail n=29 and n=299 results are marked INCOMPLETE/descriptive; complete sampled batches are n=30 and controls n=30 (kappa.csv:2; kappa.csv:12).
Q8 PASS: the binding recount/census was committed before ratings; 530/27 reproduces, while unresolved new-game identity is retained as an acceptance failure (g400_ball_reference_growth_stage1_2026-09-11.md:7).
RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G400 | reproduced 530/27 premise; 116/300 = 0.3867; round-8 kappa 0.3605; pooled n=299 kappa 0.7505; median gap 24.021 px vs 13.75 px; alternate-upload identity unresolved | CLOSED AT LIMIT (verified: codex-sol, contract A/B/Q)
NEW GAP: repeats.json:7 says summary/q6 were not fresh-process reproductions; its two maps differ from six delivered tables, omit two delivered tables, and name two absent tables, despite the memo claim at g400_ball_reference_growth_stage1_2026-09-11.md:29.
NEW GAP: summary.json:49 says rounds_pass=9 while kappa.csv:2-11 and the memo show eight PASS rows; minimal correction is `9 -> 8`, then prevent extra metadata from overriding derived `rounds_pass` at g400_finish.py:74.
NEW GAP: g400_finish.py:29 has no direct importing test; add a temp-path LF normalization test without changing the acceptance result.
