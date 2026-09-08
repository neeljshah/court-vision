VERDICT: REJECT
ACCEPTANCE FAIL: G332_spec.md:60 requires every reproduced hole's test to fail on old code; g332_harness_hygiene_2026-09-08.md:21 reports and independent master-code testing confirms 5 failed, 2 passed.
A1 PASS: test_g332_harness_hygiene.py:1-9 was run on candidate and an isolated parent archive; `git diff --quiet master 10003848f~1 -- scripts/platformkit tests/platformkit` confirms the parent executable/test tree equals master.
A2 PASS: independently reproduced premise, G327 byte identity, and the full sweep; measured versus claimed is recorded below (g332_harness_hygiene_2026-09-08.md:6-45).
A3 PASS: eye check NONE is required (G332_spec.md:64). A4 PASS: sweep has 237 parsed occurrences/217 unique serialized rows; common comparison has 161 occurrences/154 unique count keys.
A5 PASS: all callers of changed APIs were surveyed; tests import census_recomputable and g327_arms (test_g319_census_recomputable.py:9; test_g327_batch_stability.py:12). A6 PASS: no candidate landing performed. A7 PASS: every named evidence path is tracked (memo:4,25,28).
B1 PASS: all seven premise cases are named before filtering (memo:6-16).
B2 PASS: no field/status removal or rename; old call forms remain tested (census_recomputable.py:131-163; test_g332_harness_hygiene.py:143-145).
B3 PASS: unmatched evidence remains NOT RECOMPUTABLE, not silently lost (census_recomputable.py:207-220).
B4 PASS: no claim lifecycle is introduced (memo:3-4).
B5 PASS: local-only; no deployment occurred (memo:4,56).
B6 PASS: no module was moved or retired; changed callers remain present (g327_report.py:144; g327_detector_batch_stability.py:188).
B7 PASS: all 13 entries are reported, not a head slice (memo:27-45).
B8 PASS: byte comparison and construct checks perform no fitting (memo:4,24-28).
B9 PASS: denominators are exhaustive seven holes and 13 entries (G332_spec.md:63; memo:6,27).
B10 PASS: no executable threshold or gate value changed (g327_report.py:27-28).
Q1 PASS: seal recomputed exactly as 7fc8c90105eb56b820bc8829a01cf656ac309d407a84847db161f4282b2e8d74; prereg-only commit 89ff84be3 predates candidate (g332_prereg_2026-09-08.md:142).
Q2 PASS: no charged trial or K exists for this tooling construct (G332_spec.md:52-58).
Q3 FAIL: spec bar has no exception (G332_spec.md:60), but prereg adds an a1/a2 mutation exception (g332_prereg_2026-09-08.md:115-121); the bar is not byte-identical.
Q4 PASS: no OOS score or meta-learner is used (memo:4,56).
Q5 PASS: no AHEAD claim is made (memo:1).
Q6 PASS: restricted-language scan of every candidate-touched artifact returned zero matches (memo:1-59).
Q7 PASS: n=7 CONSTRUCT enumerates a1,a2,b1,b2,c1,c2,c3 exhaustively (test_g332_harness_hygiene.py:1-9).
Q8 PASS: premise is first and reports all seven before changes (g332_prereg_2026-09-08.md:19-47).
TEST: `python -m pytest tests/platformkit/test_g332_harness_hygiene.py -q -p no:cacheprovider` -> 7 passed.
TEST: `python -m pytest tests/platformkit/test_g62_environment_sidecar.py -q -p no:cacheprovider` -> 7 passed.
TEST: `python -m pytest tests/platformkit/test_g327_batch_stability.py -q -p no:cacheprovider` -> 16 passed.
TEST: `python -m pytest tests/platformkit/test_g319_census_recomputable.py -q -p no:cacheprovider` -> 4 passed.
TEST: `python -m pytest tests/platformkit/test_g310_instance_key.py -q -p no:cacheprovider` -> 10 passed.
TEST: `python -m pytest tests/platformkit/test_g330_panorama_identity.py -q -p no:cacheprovider` -> 17 passed.
TEST: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed; touched Python LOC = 279,296,295,200,107,209, all <=300.
TEST (discarded mixed path): `set PYTHONPATH=C:\Users\neelj\nba-track-a1&& python -m pytest tests/platformkit/test_g332_harness_hygiene.py -q -p no:cacheprovider` -> 7 passed from candidate imports.
TEST (master-code archive): `python -m pytest tests/platformkit/test_g332_harness_hygiene.py -q -p no:cacheprovider` -> 5 failed, 2 passed.
REPRO premise: claimed 7/7 reproduced, 0 closed; measured 7/7, 0 (five old behaviors fail the new assertions; parent grep finds neither runner parity assertion).
REPRO G327: claimed byte-identical; measured byte-identical, hashes c05cb90f80123d4de1df1d4a23167648fc462906bbe0aaad466fb20adbb81b6e and b7da6cb75d3bdeee513d61dd72a3a03d0c07aa7e28175d633e6dc274a28504ce (memo:25).
REPRO sweep: claimed 6/161 transitions and totals 22/0/57/82/0 -> 16/6/57/82/0; measured same across 11 common entries, with 154 unique count keys; regenerated 13-entry CSV is byte-identical (memo:27-45).
CORRECTIONS (minimal diffs): memo:1 `DONE` -> `PARTIAL`; ledger:582 `DONE` -> `PARTIAL`; memo:45 append `161 parsed occurrences; 154 unique count keys`.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G332 | premise 7/7; current tests 62/62; old-code test 5 failed, 2 passed; G327 outputs byte-identical; sweep 6/161 parsed occurrences (154 unique keys) | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: census_recomputable.py:95-103 accepts two successive entries with the same sha256 and no predecessor-reference field; construct measured `snapshot_list_ok(...) == True`.
NEW GAP: g327_detector_batch_stability.py:124-132 reports counts but no missing frame id when a snapshot reloads fewer frames than the sealed list.
