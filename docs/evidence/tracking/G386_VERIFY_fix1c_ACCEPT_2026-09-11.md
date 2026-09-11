VERDICT: ACCEPT
Candidate: 3cb70a6455007f4689a55fc38b8ec996197e53b7; scope is G386_spec.md:14-23 plus B1-B10 and Q1-Q8.
ACCEPTANCE PASS: all 30 attempts are accounted for; byte/pixel receipts, zero false CAPTURED rows, identical exports, and 30/21 even sampling reproduce; 6/7 controls keeps the honest result PARTIAL (attempts.csv:2-31; faults.csv:2-8; memo:7-19).
PREMISE PASS: independent census gives claimed 51/1,261 retained sections across 22/196 videos, including 18 live; the three named prior tools contain no receiver/readback route (census.csv:2-1262; memo:5).
HEADLINE PASS: reproduced claimed 30/30 CAPTURED, 30/30 acknowledgement/byte agreement/retention/PC readback/decode, 29 MATCH plus 1 ORIGINAL_ABSENT, and 0 MISMATCH (attempts.csv:2-31; receiver_receipts.csv:2-31; pixel_checks.csv:2-31).
RETENTION PASS: streaming re-hash gives claimed 30/30 objects and 2,323,546,523 bytes; native-frame re-decode gives 30/30 stored digests; max object is 100,578,787 bytes (receiver_receipts.csv:2-31; pixel_checks.csv:2-31).
ROTATION PASS: reproduced claimed present counts 30/29/27/17/17 and live counts 11/11/9/0/0 at minutes 0/15/30/45/60 (rotation_recheck.csv:2-376; memo:23).
RENDERS PASS: reproduced 30 unique names/digests at 1920x1080; even visual sample a01/a07/a13/a18/a24/a30 contains distinct native basketball frames (renders/; summary.json:106-109,128-131).
NOT VERIFIED PASS: the required explicit list is present (memo:25-31).
LOC PASS: candidate touches no .py; referenced modules/tests are 173/124/122/259/174 lines, all <=300 (g386_pin_copy.py:1; g386_pc_receiver.py:1; g386_controls.py:1; g386_capture_run.py:1; test_g386_pin_copy_one_pass.py:1).
ADDITIVITY PASS: no rename/removal occurs; restored receipt blob f8bcd1713 exactly equals 23cd2e397 and preserves its eight fields and old path; no reader module changes (common_receipts/pc_receiver_receipt.csv:1-34; candidate diff).
TEST PASS: `python -m pytest tests/platformkit/test_g386_pin_copy_one_pass.py -q -p no:cacheprovider` -> 14 passed in 1.16s (test_g386_pin_copy_one_pass.py:1-174).
IMPORTER PASS: candidate touches no module; G386 module census finds only test_g386_pin_copy_one_pass.py, run alone (test_g386_pin_copy_one_pass.py:9,76,92,105,115,127,139,169).
B1 PASS: all sampled attempts and all controls remain named; no failing row is excluded (attempts.csv:2-31; faults.csv:2-8).
B2 PASS: the historical receipt and old-path behavior are restored byte-for-byte; no field, status, or reader is removed (common_receipts/pc_receiver_receipt.csv:1-34; memo:3,39).
B3 PASS: absent/changed/short/mismatched inputs remain non-CAPTURED states and no production quarantine is added (g386_pin_copy.py:102-156).
B4 PASS: no claim queue is added; retry versions differ and staging release requires an acknowledged CAPTURED receipt (g386_pin_copy.py:156-171; faults.csv:7-8).
B5 PASS: candidate changes evidence only; no deployed route, flag, registry, daemon, or guard is changed (candidate stat; memo:31).
B6 PASS: no module is moved or retired and the sole importer resolves (candidate name-status; test_g386_pin_copy_one_pass.py:9).
B7 PASS: recomputed even indices 0,2,3,...,47,48,50 exactly match the 30-row draw (draw.csv:2-31; g386_capture_run.py:52-57).
B8 PASS: no model fit or residual is used as independent evidence (g386_prereg_2026-09-10.md:34-42).
B9 PASS: reproduced 30 unique sections, source digests, version IDs, render digests, and retained-frame digests (draw.csv:2-31; source_identity.csv:2-31; summary.json:128-131).
B10 PASS: candidate changes no harness threshold; the unchanged exact-control bar is reported 6/7 and PARTIAL (G386_spec.md:17-23; memo:2,17,24).
Q1 PASS: reproduced seals 517122d0... and 3c092fc6... from sealing blobs; commits 7c01d57e3/d993f48cb predate census epoch 1789100984 (prereg files:1; census_stamp.json:2-12).
Q2 PASS (N/A): no scored comparison, charged trial, or K is present (g386_prereg_2026-09-10.md:34-42).
Q3 PASS: no bar moved; the failed control remains below the exact-controls bar (G386_spec.md:17-23; memo:17,24).
Q4 PASS (N/A): no OOS comparison or meta-learner is scored (g386_prereg_2026-09-10.md:34-42).
Q5 PASS (N/A): no AHEAD result is claimed (memo:1-2).
Q6 PASS: character-built scan of 19 G386 text artifacts plus G386 ledger rows gives 0 non-opaque hits (memo:33).
Q7 PASS: n=30 distinct sampled sections across 21 videos; seven constructed controls are separate (draw.csv:2-31; faults.csv:2-8).
Q8 PASS: premise census precedes draw/measurement and independently reproduces 51/1,261 across 22 videos (census_stamp.json:2-12; memo:5-8).
CORRECTIONS: none.
2026-09-11 | tracking | G386 | premise 51/1,261 retained across 22 videos; sealed draw 30/21; 30/30 captures and retained-object readbacks; retained frames 30/30 re-decoded; receiver-vs-original 29 MATCH plus 1 ORIGINAL_ABSENT; controls 6/7 | PARTIAL (verified: codex-sol, contract A/B/Q)
NEW GAP: contract A1 master 6e849d214 lacks the test and four G386 modules; the exact master command collected 0 tests with file-not-found, while the candidate-worktree command passed 14.
NEW GAP: memo:51 records ledger SHA-256 75ec4872... but the candidate-appended row makes the current digest 72d3ad2f...; all 23 named artifact paths exist and the other 22 digests match.
